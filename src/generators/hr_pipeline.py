from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
import math
import random
import time
from typing import Any

from faker import Faker
from pymongo import UpdateOne
from pymongo.database import Database
from tqdm import tqdm

from config.settings import GenerationSettings
from generators.base import BaseGenerator
from models.reference_data import (
    COUNTRY_SALARY_MULTIPLIER,
    DEPARTMENTS,
    DEPARTMENT_TURNOVER,
    LEVEL_WEIGHTS,
    OFFICES,
    POSITIONS,
)
from utils.ids import make_unique_id


COLLECTION_ORDER = [
    "offices",
    "departments",
    "positions",
    "employees",
    "teams",
    "recruitments",
    "payrolls",
    "absences",
    "trainings",
    "training_participations",
    "performance_reviews",
    "promotions",
    "engagement_surveys",
    "employee_assets",
    "exits",
]


@dataclass(slots=True)
class PipelineMetrics:
    generated: int = 0
    inserted: int = 0


class StaticGenerator(BaseGenerator):
    def __init__(self, collection, rows: list[dict[str, Any]], retry_count: int = 3) -> None:
        super().__init__(collection, retry_count)
        self.rows = rows
        self.collection_name = collection.name

    def generate_batch(self, batch_size: int, offset: int = 0) -> list[dict[str, Any]]:
        if offset > 0:
            return []
        return self.rows


class EmployeeGenerator(BaseGenerator):
    def __init__(
        self,
        collection,
        settings: GenerationSettings,
        faker: Faker,
        rng: random.Random,
        reference_now: datetime,
        offices: list[dict[str, Any]],
        departments: list[dict[str, Any]],
        positions: list[dict[str, Any]],
    ) -> None:
        super().__init__(collection, settings.retry_count)
        self.collection_name = collection.name
        self.settings = settings
        self.faker = faker
        self.rng = rng
        self.offices = offices
        self.departments = departments
        self.positions = positions
        self.base_date = reference_now
        self.manager_pool: dict[str, list[str]] = defaultdict(list)

    def _pick_level(self) -> str:
        levels, weights = zip(*LEVEL_WEIGHTS.items(), strict=False)
        return self.rng.choices(list(levels), weights=list(weights), k=1)[0]

    def _pick_position(self, level: str) -> dict[str, Any]:
        matching = [p for p in self.positions if p["level"] == level]
        if not matching:
            matching = self.positions
        return self.rng.choice(matching)

    def generate_batch(self, batch_size: int, offset: int = 0) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        for i in range(batch_size):
            idx = offset + i + 1
            emp_id = make_unique_id("EMP", idx)
            department = self.rng.choice(self.departments)
            office = self.rng.choice(self.offices)
            level = self._pick_level()
            position = self._pick_position(level)

            hire_days_ago = self.rng.randint(30, 3650)
            hire_date = (self.base_date - timedelta(days=hire_days_ago)).date()
            age_years = self.rng.randint(22, 60)
            birth_date = (self.base_date - timedelta(days=age_years * 365 + self.rng.randint(0, 364))).date()

            salary_floor = position["salary_min"] * COUNTRY_SALARY_MULTIPLIER.get(office["country"], 1.0)
            salary_ceiling = position["salary_max"] * COUNTRY_SALARY_MULTIPLIER.get(office["country"], 1.0)
            current_salary = round(self.rng.uniform(salary_floor, salary_ceiling), 2)

            turnover_rate = DEPARTMENT_TURNOVER.get(department["name"], 0.08)
            status = "active"
            if self.rng.random() < turnover_rate:
                status = self.rng.choice(["terminated", "resigned"])

            manager_candidates = self.manager_pool[department["unique_id"]]
            manager_unique_id = self.rng.choice(manager_candidates) if manager_candidates else None

            if level in {"Senior", "Lead", "Director"} and self.rng.random() < 0.45:
                self.manager_pool[department["unique_id"]].append(emp_id)

            first_name = self.faker.first_name()
            last_name = self.faker.last_name()
            docs.append(
                {
                    "unique_id": emp_id,
                    "employee_number": f"E{idx:07d}",
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": f"{first_name.lower()}.{last_name.lower()}.{idx}@example-corp.com",
                    "phone": self.faker.phone_number(),
                    "gender": self.rng.choice(["M", "F", "Other"]),
                    "birth_date": birth_date.isoformat(),
                    "nationality": office["country"],
                    "marital_status": self.rng.choice(["Single", "Married", "Divorced", "Widowed"]),
                    "hire_date": hire_date.isoformat(),
                    "employment_type": self.rng.choice(["Full-time", "Part-time", "Contract"]),
                    "status": status,
                    "department_unique_id": department["unique_id"],
                    "team_unique_id": None,
                    "manager_unique_id": manager_unique_id,
                    "position_unique_id": position["unique_id"],
                    "office_unique_id": office["unique_id"],
                    "salary_band": f"{level}-{office['country']}",
                    "current_salary": current_salary,
                    "remote_type": self.rng.choices(["Onsite", "Hybrid", "Remote"], weights=[0.35, 0.45, 0.2], k=1)[0],
                    "created_at": self.base_date.isoformat(),
                }
            )
        return docs


class HRDataPipeline:
    def __init__(self, db: Database, settings: GenerationSettings) -> None:
        self.db = db
        self.settings = settings
        self.faker = Faker()
        self.faker.seed_instance(settings.seed)
        self.rng = random.Random(settings.seed)
        self.reference_now = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=settings.seed)
        self.metrics: dict[str, PipelineMetrics] = {name: PipelineMetrics() for name in COLLECTION_ORDER}

    def _existing(self, collection_name: str) -> int:
        return self.db[collection_name].estimated_document_count()

    def _should_skip(self, collection_name: str) -> bool:
        return self.settings.resume and self._existing(collection_name) > 0

    def _insert_and_track(self, collection_name: str, generator: BaseGenerator, docs: list[dict[str, Any]]) -> None:
        inserted = generator.insert_batch(docs)
        self.metrics[collection_name].generated += len(docs)
        self.metrics[collection_name].inserted += inserted
        logging.info("Inserted %s %s", inserted, collection_name)

    def _build_offices(self) -> list[dict[str, Any]]:
        rows = []
        now = self.reference_now.isoformat()
        for idx, (name, country, city, timezone, capacity) in enumerate(OFFICES, start=1):
            rows.append(
                {
                    "unique_id": make_unique_id("OFF", idx),
                    "office_name": name,
                    "country": country,
                    "city": city,
                    "timezone": timezone,
                    "capacity": capacity,
                    "opening_date": (self.reference_now - timedelta(days=self.rng.randint(1000, 7000))).date().isoformat(),
                    "created_at": now,
                }
            )
        return rows

    def _build_departments(self) -> list[dict[str, Any]]:
        rows = []
        now = self.reference_now.isoformat()
        for idx, (name, description) in enumerate(DEPARTMENTS, start=1):
            rows.append(
                {
                    "unique_id": make_unique_id("DEP", idx),
                    "name": name,
                    "description": description,
                    "budget": round(self.rng.uniform(500000, 9500000), 2),
                    "director_unique_id": None,
                    "location": self.rng.choice([o[2] for o in OFFICES]),
                    "created_at": now,
                }
            )
        return rows

    def _build_positions(self) -> list[dict[str, Any]]:
        rows = []
        now = self.reference_now.isoformat()
        for idx, (title, job_family, level, salary_min, salary_max) in enumerate(POSITIONS, start=1):
            rows.append(
                {
                    "unique_id": make_unique_id("POS", idx),
                    "title": title,
                    "job_family": job_family,
                    "level": level,
                    "salary_min": salary_min,
                    "salary_max": salary_max,
                    "created_at": now,
                }
            )
        return rows

    def _generate_static_collection(self, name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._should_skip(name):
            logging.info("Skipping %s (resume mode)", name)
            return list(self.db[name].find({}, {"_id": 0}))
        generator = StaticGenerator(self.db[name], rows, self.settings.retry_count)
        docs = generator.generate_batch(self.settings.batch_size)
        self._insert_and_track(name, generator, docs)
        return docs

    def _generate_employees(
        self,
        offices: list[dict[str, Any]],
        departments: list[dict[str, Any]],
        positions: list[dict[str, Any]],
    ) -> None:
        if self._should_skip("employees"):
            logging.info("Skipping employees (resume mode)")
            return

        generator = EmployeeGenerator(
            collection=self.db["employees"],
            settings=self.settings,
            faker=self.faker,
            rng=self.rng,
            reference_now=self.reference_now,
            offices=offices,
            departments=departments,
            positions=positions,
        )
        total = self.settings.employees
        batches = math.ceil(total / self.settings.batch_size)
        progress = tqdm(total=total, desc="employees", unit="docs")
        for batch_idx in range(batches):
            current_size = min(self.settings.batch_size, total - batch_idx * self.settings.batch_size)
            logging.info("Generating employees batch %s/%s", batch_idx + 1, batches)
            docs = generator.generate_batch(current_size, offset=batch_idx * self.settings.batch_size)
            self._insert_and_track("employees", generator, docs)
            progress.update(len(docs))
        progress.close()

    def _generate_teams(self, departments: list[dict[str, Any]]) -> None:
        if self._should_skip("teams"):
            logging.info("Skipping teams (resume mode)")
            return
        total_employees = max(self._existing("employees"), self.settings.employees)
        target_teams = max(12, total_employees // 25)
        docs: list[dict[str, Any]] = []
        for idx in range(1, target_teams + 1):
            dep = departments[(idx - 1) % len(departments)]
            manager = self.db["employees"].find_one(
                {
                    "department_unique_id": dep["unique_id"],
                    "position_unique_id": {"$exists": True},
                    "status": "active",
                },
                {"unique_id": 1, "_id": 0},
            )
            docs.append(
                {
                    "unique_id": make_unique_id("TEAM", idx),
                    "department_unique_id": dep["unique_id"],
                    "manager_unique_id": manager["unique_id"] if manager else None,
                    "team_name": f"{dep['name']} Team {idx:03d}",
                    "description": f"Operational team for {dep['name']}",
                    "created_at": self.reference_now.isoformat(),
                }
            )
        generator = StaticGenerator(self.db["teams"], docs, self.settings.retry_count)
        self._insert_and_track("teams", generator, docs)

    def _assign_teams_to_employees(self) -> None:
        department_teams: dict[str, list[str]] = defaultdict(list)
        for team in self.db["teams"].find({}, {"unique_id": 1, "department_unique_id": 1, "_id": 0}):
            department_teams[team["department_unique_id"]].append(team["unique_id"])

        cursor = self.db["employees"].find(
            {},
            {"_id": 1, "department_unique_id": 1},
            no_cursor_timeout=True,
        ).batch_size(self.settings.batch_size)
        operations: list[UpdateOne] = []
        updated = 0
        for emp in cursor:
            teams = department_teams.get(emp["department_unique_id"], [])
            if not teams:
                continue
            operations.append(UpdateOne({"_id": emp["_id"]}, {"$set": {"team_unique_id": self.rng.choice(teams)}}))
            if len(operations) >= self.settings.batch_size:
                self.db["employees"].bulk_write(operations, ordered=False)
                updated += len(operations)
                operations = []
        if operations:
            self.db["employees"].bulk_write(operations, ordered=False)
            updated += len(operations)
        cursor.close()
        logging.info("Updated %s employees with team assignments", updated)

    def _yield_employee_chunks(self, projection: dict[str, int]) -> list[dict[str, Any]]:
        chunk: list[dict[str, Any]] = []
        cursor = self.db["employees"].find({}, projection, no_cursor_timeout=True).batch_size(self.settings.batch_size)
        for row in cursor:
            row.pop("_id", None)
            chunk.append(row)
            if len(chunk) >= self.settings.batch_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk
        cursor.close()

    def _score(self, base: float, spread: float = 12.0) -> float:
        score = self.rng.gauss(base, spread)
        return round(max(1.0, min(5.0, score / 20.0)), 2)

    def _insert_dynamic_collection(self, name: str, builder) -> None:  # noqa: ANN001
        if self._should_skip(name):
            logging.info("Skipping %s (resume mode)", name)
            return

        generator = StaticGenerator(self.db[name], [], self.settings.retry_count)
        progress = tqdm(desc=name, unit="docs")
        total_docs = 0
        for docs in builder():
            if docs:
                inserted = generator.insert_batch(docs)
                self.metrics[name].generated += len(docs)
                self.metrics[name].inserted += inserted
                total_docs += len(docs)
                progress.update(len(docs))
        progress.close()
        logging.info("Inserted %s %s", total_docs, name)

    def _build_recruitments(self):
        target = max(100, int(self.settings.employees * 0.22))
        generated = 0
        position_ids = [p["unique_id"] for p in self.db["positions"].find({}, {"unique_id": 1, "_id": 0})]
        recruiters = [e["unique_id"] for e in self.db["employees"].find({"department_unique_id": make_unique_id("DEP", 5)}, {"unique_id": 1, "_id": 0}).limit(200)]
        while generated < target:
            docs = []
            batch = min(self.settings.batch_size, target - generated)
            for _ in range(batch):
                idx = generated + _ + 1
                final_status = self.rng.choices(["hired", "rejected", "withdrawn"], weights=[0.28, 0.56, 0.16], k=1)[0]
                hired = self.db["employees"].find_one({"status": "active"}, {"unique_id": 1, "_id": 0})
                docs.append(
                    {
                        "unique_id": make_unique_id("REC", idx),
                        "candidate_name": self.faker.name(),
                        "candidate_email": self.faker.email(),
                        "applied_position_unique_id": self.rng.choice(position_ids),
                        "source": self.rng.choice(["LinkedIn", "Referral", "Career Site", "Agency", "Campus"]),
                        "recruiter_unique_id": self.rng.choice(recruiters) if recruiters else None,
                        "application_date": (self.reference_now - timedelta(days=self.rng.randint(15, 800))).date().isoformat(),
                        "interview_count": self.rng.randint(1, 6),
                        "final_status": final_status,
                        "offered_salary": round(self.rng.uniform(45000, 180000), 2),
                        "hired_employee_unique_id": hired["unique_id"] if final_status == "hired" and hired else None,
                    }
                )
            generated += len(docs)
            yield docs

    def _build_payrolls(self):
        idx = 1
        for chunk in self._yield_employee_chunks(
            {"_id": 0, "unique_id": 1, "current_salary": 1, "status": 1, "hire_date": 1}
        ):
            docs = []
            for emp in chunk:
                if emp["status"] not in {"active", "resigned"}:
                    continue
                for month_offset in range(self.settings.payroll_months):
                    payroll_date = (self.reference_now - timedelta(days=month_offset * 30)).date()
                    bonus = round(max(0.0, self.rng.gauss(800, 1200)), 2)
                    deductions = round(emp["current_salary"] * self.rng.uniform(0.08, 0.2), 2)
                    gross = round(emp["current_salary"], 2)
                    net = round(gross + bonus - deductions, 2)
                    docs.append(
                        {
                            "unique_id": make_unique_id("PAY", idx),
                            "employee_unique_id": emp["unique_id"],
                            "payroll_month": payroll_date.strftime("%Y-%m"),
                            "gross_salary": gross,
                            "bonus": bonus,
                            "deductions": deductions,
                            "net_salary": net,
                            "payment_date": payroll_date.isoformat(),
                        }
                    )
                    idx += 1
            if docs:
                yield docs

    def _build_absences(self):
        idx = 1
        absence_types = ["Vacation", "Vacation", "Vacation", "Sick Leave", "Personal Leave", "Maternity Leave"]
        for chunk in self._yield_employee_chunks({"_id": 0, "unique_id": 1, "status": 1, "hire_date": 1}):
            docs = []
            for emp in chunk:
                if emp["status"] != "active":
                    continue
                event_count = self.rng.choices([0, 1, 2, 3], weights=[0.18, 0.48, 0.26, 0.08], k=1)[0]
                for _ in range(event_count):
                    start_date = self.reference_now - timedelta(days=self.rng.randint(10, 720))
                    days_count = self.rng.randint(1, 15)
                    end_date = start_date + timedelta(days=days_count)
                    docs.append(
                        {
                            "unique_id": make_unique_id("ABS", idx),
                            "employee_unique_id": emp["unique_id"],
                            "absence_type": self.rng.choice(absence_types),
                            "start_date": start_date.date().isoformat(),
                            "end_date": end_date.date().isoformat(),
                            "days_count": days_count,
                            "approval_status": self.rng.choices(
                                ["approved", "pending", "rejected"], weights=[0.82, 0.14, 0.04], k=1
                            )[0],
                        }
                    )
                    idx += 1
            if docs:
                yield docs

    def _build_trainings(self):
        titles = [
            "Advanced SQL for Analytics",
            "Leadership Essentials",
            "Cloud Fundamentals",
            "Data Governance",
            "Effective Stakeholder Communication",
            "Secure Coding Basics",
            "Project Management Practitioner",
            "Sales Negotiation Masterclass",
            "HR Compliance Global",
            "Product Discovery Workshop",
            "MLOps in Production",
            "Financial Planning for Managers",
        ]
        docs = []
        for idx, title in enumerate(titles, start=1):
            docs.append(
                {
                    "unique_id": make_unique_id("TRN", idx),
                    "title": title,
                    "provider": self.rng.choice(["Coursera", "Udemy", "Pluralsight", "Internal Academy"]),
                    "category": self.rng.choice(["Technical", "Leadership", "Compliance", "Business"]),
                    "duration_hours": self.rng.randint(2, 36),
                    "certification_available": self.rng.random() < 0.68,
                    "cost": round(self.rng.uniform(80, 2500), 2),
                    "created_at": self.reference_now.isoformat(),
                }
            )
        yield docs

    def _build_training_participations(self):
        idx = 1
        trainings = [t["unique_id"] for t in self.db["trainings"].find({}, {"unique_id": 1, "_id": 0})]
        for chunk in self._yield_employee_chunks({"_id": 0, "unique_id": 1, "department_unique_id": 1, "status": 1}):
            docs = []
            for emp in chunk:
                if emp["status"] != "active":
                    continue
                dept_code = int(emp["department_unique_id"].split("-")[1])
                enrollment_prob = 0.68 if dept_code in {1, 2, 7} else 0.42
                if self.rng.random() > enrollment_prob:
                    continue
                enrollment_date = self.reference_now - timedelta(days=self.rng.randint(20, 540))
                completion_rate = round(max(0.35, min(1.0, self.rng.gauss(0.83, 0.16))), 2)
                score = round(max(45, min(100, self.rng.gauss(78, 11))), 1)
                docs.append(
                    {
                        "unique_id": make_unique_id("ENR", idx),
                        "employee_unique_id": emp["unique_id"],
                        "training_unique_id": self.rng.choice(trainings),
                        "enrollment_date": enrollment_date.date().isoformat(),
                        "completion_date": (enrollment_date + timedelta(days=self.rng.randint(1, 120))).date().isoformat(),
                        "completion_rate": completion_rate,
                        "score": score,
                        "certificate_earned": completion_rate >= 0.8,
                    }
                )
                idx += 1
            if docs:
                yield docs

    def _build_performance_reviews(self):
        idx = 1
        review_period = f"{self.reference_now.year - 1}-Annual"
        for chunk in self._yield_employee_chunks(
            {"_id": 0, "unique_id": 1, "manager_unique_id": 1, "status": 1, "hire_date": 1}
        ):
            docs = []
            for emp in chunk:
                if emp["status"] != "active":
                    continue
                technical = self._score(72)
                communication = self._score(70)
                leadership = self._score(68)
                overall = round((technical + communication + leadership) / 3, 2)
                docs.append(
                    {
                        "unique_id": make_unique_id("REV", idx),
                        "employee_unique_id": emp["unique_id"],
                        "reviewer_unique_id": emp["manager_unique_id"],
                        "review_period": review_period,
                        "technical_score": technical,
                        "communication_score": communication,
                        "leadership_score": leadership,
                        "overall_score": overall,
                        "promotion_recommended": overall >= 4.3 and self.rng.random() < 0.35,
                        "review_date": (self.reference_now - timedelta(days=self.rng.randint(10, 340))).date().isoformat(),
                    }
                )
                idx += 1
            if docs:
                yield docs

    def _build_promotions(self):
        idx = 1
        promotions_by_employee = {
            doc["employee_unique_id"]: doc
            for doc in self.db["performance_reviews"].find(
                {"promotion_recommended": True}, {"employee_unique_id": 1, "overall_score": 1, "_id": 0}
            )
        }
        employee_projection = {
            "_id": 0,
            "unique_id": 1,
            "position_unique_id": 1,
            "current_salary": 1,
            "hire_date": 1,
        }
        positions = [p for p in self.db["positions"].find({}, {"unique_id": 1, "salary_min": 1, "salary_max": 1, "_id": 0})]
        for chunk in self._yield_employee_chunks(employee_projection):
            docs = []
            for emp in chunk:
                review = promotions_by_employee.get(emp["unique_id"])
                if not review or self.rng.random() > 0.18:
                    continue
                new_position = self.rng.choice(positions)
                new_salary = round(max(emp["current_salary"] * 1.05, self.rng.uniform(new_position["salary_min"], new_position["salary_max"])), 2)
                docs.append(
                    {
                        "unique_id": make_unique_id("PRO", idx),
                        "employee_unique_id": emp["unique_id"],
                        "old_position_unique_id": emp["position_unique_id"],
                        "new_position_unique_id": new_position["unique_id"],
                        "old_salary": round(emp["current_salary"], 2),
                        "new_salary": new_salary,
                        "promotion_date": (self.reference_now - timedelta(days=self.rng.randint(20, 900))).date().isoformat(),
                        "promotion_reason": self.rng.choice(
                            ["Outstanding performance", "Expanded responsibilities", "Leadership impact"]
                        ),
                    }
                )
                idx += 1
            if docs:
                yield docs

    def _build_engagement_surveys(self):
        idx = 1
        perf = {
            doc["employee_unique_id"]: doc["overall_score"]
            for doc in self.db["performance_reviews"].find({}, {"employee_unique_id": 1, "overall_score": 1, "_id": 0})
        }
        for chunk in self._yield_employee_chunks({"_id": 0, "unique_id": 1, "hire_date": 1, "status": 1}):
            docs = []
            for emp in chunk:
                if emp["status"] != "active":
                    continue
                hire_date = datetime.fromisoformat(emp["hire_date"])
                tenure_years = max(0.1, (self.reference_now.replace(tzinfo=None) - hire_date).days / 365)
                perf_score = perf.get(emp["unique_id"], 3.4)
                base = min(5.0, max(2.0, (perf_score * 0.55) + min(tenure_years / 5, 0.8)))
                engagement = round(max(1.0, min(5.0, self.rng.gauss(base, 0.45))), 2)
                docs.append(
                    {
                        "unique_id": make_unique_id("ENG", idx),
                        "employee_unique_id": emp["unique_id"],
                        "survey_date": (self.reference_now - timedelta(days=self.rng.randint(10, 180))).date().isoformat(),
                        "engagement_score": engagement,
                        "satisfaction_score": round(max(1.0, min(5.0, engagement + self.rng.uniform(-0.35, 0.45))), 2),
                        "work_life_balance_score": round(max(1.0, min(5.0, engagement + self.rng.uniform(-0.6, 0.5))), 2),
                        "manager_score": round(max(1.0, min(5.0, engagement + self.rng.uniform(-0.45, 0.4))), 2),
                        "comment": self.rng.choice(
                            [
                                "Great team collaboration and clear goals.",
                                "Need better balance in peak delivery periods.",
                                "Strong support from manager and peers.",
                                "Would like more growth opportunities.",
                            ]
                        ),
                    }
                )
                idx += 1
            if docs:
                yield docs

    def _build_employee_assets(self):
        idx = 1
        asset_types = {
            "Laptop": ["Dell XPS", "MacBook Pro", "Lenovo ThinkPad"],
            "Monitor": ["Dell UltraSharp", "LG Ergo", "Samsung Smart Monitor"],
            "Smartphone": ["iPhone", "Pixel", "Samsung Galaxy"],
        }
        for chunk in self._yield_employee_chunks({"_id": 0, "unique_id": 1, "status": 1}):
            docs = []
            for emp in chunk:
                if emp["status"] != "active":
                    continue
                equipment_count = self.rng.choices([1, 2, 3], weights=[0.1, 0.72, 0.18], k=1)[0]
                chosen = self.rng.sample(list(asset_types.keys()), k=equipment_count)
                for asset_type in chosen:
                    docs.append(
                        {
                            "unique_id": make_unique_id("AST", idx),
                            "employee_unique_id": emp["unique_id"],
                            "asset_type": asset_type,
                            "asset_name": self.rng.choice(asset_types[asset_type]),
                            "serial_number": f"SN-{self.rng.randint(1000000, 9999999)}",
                            "assignment_date": (self.reference_now - timedelta(days=self.rng.randint(30, 1600))).date().isoformat(),
                            "status": self.rng.choices(["assigned", "maintenance", "returned"], weights=[0.9, 0.08, 0.02], k=1)[0],
                        }
                    )
                    idx += 1
            if docs:
                yield docs

    def _build_exits(self):
        idx = 1
        cursor = self.db["employees"].find(
            {"status": {"$in": ["terminated", "resigned"]}},
            {"unique_id": 1, "hire_date": 1, "status": 1, "_id": 0},
            no_cursor_timeout=True,
        ).batch_size(self.settings.batch_size)
        docs: list[dict[str, Any]] = []
        for emp in cursor:
            hire_date = datetime.fromisoformat(emp["hire_date"])
            exit_date = self.reference_now.replace(tzinfo=None) - timedelta(days=self.rng.randint(1, 900))
            if exit_date < hire_date:
                exit_date = hire_date + timedelta(days=self.rng.randint(30, 365))
            tenure = max(1, int((exit_date - hire_date).days / 30))
            docs.append(
                {
                    "unique_id": make_unique_id("EXT", idx),
                    "employee_unique_id": emp["unique_id"],
                    "exit_date": exit_date.date().isoformat(),
                    "exit_reason": self.rng.choice(
                        [
                            "Career growth elsewhere",
                            "Compensation",
                            "Relocation",
                            "Work-life balance",
                            "Role mismatch",
                        ]
                    ),
                    "tenure_months": tenure,
                    "rehirable": self.rng.random() < 0.7,
                    "exit_interview_score": round(max(1.0, min(5.0, self.rng.gauss(3.5, 0.8))), 2),
                }
            )
            idx += 1
            if len(docs) >= self.settings.batch_size:
                yield docs
                docs = []
        if docs:
            yield docs
        cursor.close()

    def _update_department_directors(self) -> None:
        for dep in self.db["departments"].find({}, {"unique_id": 1, "name": 1, "_id": 0}):
            director = self.db["employees"].find_one(
                {
                    "department_unique_id": dep["unique_id"],
                    "status": "active",
                    "$or": [
                        {"salary_band": {"$regex": "Director"}},
                        {"salary_band": {"$regex": "Senior"}},
                    ],
                },
                {"unique_id": 1, "_id": 0},
            )
            if director:
                self.db["departments"].update_one(
                    {"unique_id": dep["unique_id"]},
                    {"$set": {"director_unique_id": director["unique_id"]}},
                )

    def _create_indexes(self) -> None:
        index_fields = [
            ("unique_id", True),
            ("employee_unique_id", False),
            ("department_unique_id", False),
            ("team_unique_id", False),
            ("manager_unique_id", False),
            ("position_unique_id", False),
        ]
        for name in COLLECTION_ORDER:
            collection = self.db[name]
            for field, unique in index_fields:
                try:
                    collection.create_index(field, unique=unique if field == "unique_id" else False)
                except Exception as exc:  # noqa: BLE001
                    logging.warning("Unable to create index on %s.%s: %s", name, field, exc)

    def run(self) -> None:
        if self.settings.drop_existing and not self.settings.resume:
            for name in COLLECTION_ORDER:
                self.db[name].drop()

        start = time.perf_counter()

        offices = self._generate_static_collection("offices", self._build_offices())
        departments = self._generate_static_collection("departments", self._build_departments())
        self._generate_static_collection("positions", self._build_positions())
        self._generate_employees(offices, departments, list(self.db["positions"].find({}, {"_id": 0})))
        self._generate_teams(departments)
        self._assign_teams_to_employees()
        self._update_department_directors()

        self._insert_dynamic_collection("recruitments", self._build_recruitments)
        self._insert_dynamic_collection("payrolls", self._build_payrolls)
        self._insert_dynamic_collection("absences", self._build_absences)
        self._insert_dynamic_collection("trainings", self._build_trainings)
        self._insert_dynamic_collection("training_participations", self._build_training_participations)
        self._insert_dynamic_collection("performance_reviews", self._build_performance_reviews)
        self._insert_dynamic_collection("promotions", self._build_promotions)
        self._insert_dynamic_collection("engagement_surveys", self._build_engagement_surveys)
        self._insert_dynamic_collection("employee_assets", self._build_employee_assets)
        self._insert_dynamic_collection("exits", self._build_exits)

        self._create_indexes()

        elapsed = time.perf_counter() - start
        inserted_total = sum(metric.inserted for metric in self.metrics.values())
        generated_total = sum(metric.generated for metric in self.metrics.values())
        speed = inserted_total / elapsed if elapsed else 0
        logging.info("Generation completed")
        logging.info("Documents generated: %s", generated_total)
        logging.info("Documents inserted: %s", inserted_total)
        logging.info("Execution time: %.2fs", elapsed)
        logging.info("Generation speed: %.2f docs/s", speed)
