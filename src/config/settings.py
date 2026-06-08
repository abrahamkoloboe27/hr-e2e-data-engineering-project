from __future__ import annotations

from dataclasses import dataclass
from dotenv import load_dotenv
import os


@dataclass(slots=True)
class MongoSettings:
    uri: str
    database: str
    timeout_ms: int = 20000


@dataclass(slots=True)
class GenerationSettings:
    employees: int
    batch_size: int = 5000
    seed: int = 42
    retry_count: int = 3
    payroll_months: int = 6
    resume: bool = False
    drop_existing: bool = False


def load_mongo_settings() -> MongoSettings:
    load_dotenv()
    uri = os.getenv("MONGODB_URI")
    database = os.getenv("MONGODB_DATABASE", "hr_synthetic")
    timeout = int(os.getenv("MONGODB_TIMEOUT_MS", "20000"))
    if not uri:
        raise ValueError("MONGODB_URI is required. Configure it in .env or environment variables.")
    return MongoSettings(uri=uri, database=database, timeout_ms=timeout)
