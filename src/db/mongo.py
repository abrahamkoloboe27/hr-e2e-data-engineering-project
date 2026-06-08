from __future__ import annotations

from pymongo import MongoClient
from pymongo.database import Database

from config.settings import MongoSettings


def get_database(settings: MongoSettings) -> Database:
    client = MongoClient(settings.uri, serverSelectionTimeoutMS=settings.timeout_ms)
    return client[settings.database]
