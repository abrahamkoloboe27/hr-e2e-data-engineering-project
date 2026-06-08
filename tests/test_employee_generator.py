from __future__ import annotations

from datetime import UTC, datetime
import random

from faker import Faker

from config.settings import GenerationSettings
from generators.hr_pipeline import EmployeeGenerator


class _FakeCollection:
    name = "employees"


def _sample_refs():
    offices = [
        {"unique_id": "OFF-00000001", "country": "France"},
        {"unique_id": "OFF-00000002", "country": "Germany"},
    ]
    departments = [
        {"unique_id": "DEP-00000001", "name": "Engineering"},
        {"unique_id": "DEP-00000002", "name": "Sales"},
    ]
    positions = [
        {"unique_id": "POS-00000001", "title": "Software Engineer", "level": "Junior", "salary_min": 50000, "salary_max": 80000},
        {"unique_id": "POS-00000002", "title": "Software Engineer", "level": "Senior", "salary_min": 120000, "salary_max": 165000},
    ]
    return offices, departments, positions


def test_employee_batch_seed_reproducible():
    settings = GenerationSettings(employees=10, seed=7)
    offices, departments, positions = _sample_refs()

    faker1 = Faker()
    faker1.seed_instance(7)
    reference_now = datetime(2026, 1, 1, tzinfo=UTC)
    gen1 = EmployeeGenerator(
        _FakeCollection(), settings, faker1, random.Random(7), reference_now, offices, departments, positions
    )

    faker2 = Faker()
    faker2.seed_instance(7)
    gen2 = EmployeeGenerator(
        _FakeCollection(), settings, faker2, random.Random(7), reference_now, offices, departments, positions
    )

    batch1 = gen1.generate_batch(5, offset=0)
    batch2 = gen2.generate_batch(5, offset=0)

    assert batch1 == batch2


def test_employee_batch_relationship_fields_present():
    settings = GenerationSettings(employees=10, seed=10)
    offices, departments, positions = _sample_refs()

    faker = Faker()
    faker.seed_instance(10)
    gen = EmployeeGenerator(
        _FakeCollection(),
        settings,
        faker,
        random.Random(10),
        datetime(2026, 1, 1, tzinfo=UTC),
        offices,
        departments,
        positions,
    )

    batch = gen.generate_batch(20, offset=0)

    dept_ids = {d["unique_id"] for d in departments}
    office_ids = {o["unique_id"] for o in offices}
    pos_ids = {p["unique_id"] for p in positions}

    assert all(doc["department_unique_id"] in dept_ids for doc in batch)
    assert all(doc["office_unique_id"] in office_ids for doc in batch)
    assert all(doc["position_unique_id"] in pos_ids for doc in batch)
    assert all(doc["current_salary"] > 0 for doc in batch)
    assert all(doc["team_unique_id"] is None for doc in batch)
