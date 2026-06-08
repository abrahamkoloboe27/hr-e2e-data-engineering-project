from __future__ import annotations


def make_unique_id(prefix: str, index: int) -> str:
    return f"{prefix}-{index:08d}"
