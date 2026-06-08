from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from pymongo.collection import Collection


class BaseGenerator(ABC):
    collection_name: str

    def __init__(self, collection: Collection, retry_count: int = 3) -> None:
        self.collection = collection
        self.retry_count = retry_count

    @abstractmethod
    def generate_batch(self, batch_size: int, offset: int = 0) -> list[dict[str, Any]]:
        raise NotImplementedError

    def insert_batch(self, documents: list[dict[str, Any]]) -> int:
        if not documents:
            return 0
        attempt = 0
        while attempt < self.retry_count:
            try:
                result = self.collection.insert_many(documents, ordered=False)
                return len(result.inserted_ids)
            except Exception as exc:  # noqa: BLE001
                attempt += 1
                logging.error(
                    "Insert failed for %s (%s/%s): %s",
                    self.collection_name,
                    attempt,
                    self.retry_count,
                    exc,
                )
                if attempt >= self.retry_count:
                    raise
                time.sleep(min(2**attempt, 10))
        return 0
