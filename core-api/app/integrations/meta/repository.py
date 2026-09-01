"""Allowlisted normalized Meta persistence, shared by SQL adapters and tests."""

from __future__ import annotations

from typing import Any
from app.integrations.meta.schema import META_TABLES


class MetaRepository:
    def __init__(self, store: Any) -> None:
        self.store = store

    def upsert(self, table: str, values: dict[str, Any], keys: tuple[str, ...]) -> None:
        if table not in META_TABLES or not set(values).issubset(META_TABLES[table]):
            raise ValueError("Unsupported Meta persistence shape")
        method = getattr(self.store, "upsert_meta_record", None)
        if not callable(method):
            raise RuntimeError("Core store does not support Meta persistence")
        method(table, values, keys)

    def list(self, table: str, organization_id: str | None = None) -> list[dict[str, Any]]:
        if table not in META_TABLES:
            raise ValueError("Unsupported Meta table")
        method = getattr(self.store, "list_meta_records", None)
        if not callable(method):
            return []
        return method(table, organization_id)
