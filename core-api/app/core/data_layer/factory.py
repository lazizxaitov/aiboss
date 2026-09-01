"""Core data store factory."""

from __future__ import annotations

from functools import cache
from threading import Lock
from typing import Any

from app.core.config import get_settings
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.storage.postgres import PostgresCoreStore


_schema_initialization_lock = Lock()
_initialized_store_ids: set[int] = set()


@cache
def get_core_store(
    storage_backend: str | None = None,
    postgres_dsn: str | None = None,
) -> CoreDataStore:
    """Return the configured core data store."""

    settings = get_settings()
    backend = storage_backend or settings.storage_backend

    if backend == "memory":
        return InMemoryCoreDataLayer()

    if backend == "postgres":
        dsn = postgres_dsn or settings.postgres_dsn
        if not dsn:
            msg = "postgres_dsn is required when storage_backend is postgres"
            raise ValueError(msg)
        return PostgresCoreStore.from_dsn(dsn)

    msg = f"Unsupported storage backend: {backend}"
    raise ValueError(msg)


def initialize_core_store(store: Any) -> None:
    """Initialize schema once from an application/bootstrap context.

    Request dependencies must only return the cached store. The process has a
    single backend worker, so a process-local lock is sufficient here; the
    database DDL remains idempotent for explicit CLI/deployment invocations.
    """

    ensure_schema = getattr(store, "ensure_schema", None)
    if not callable(ensure_schema):
        return

    store_id = id(store)
    with _schema_initialization_lock:
        if store_id in _initialized_store_ids:
            return
        ensure_schema()
        _initialized_store_ids.add(store_id)
