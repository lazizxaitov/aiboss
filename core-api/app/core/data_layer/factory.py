"""Core data store factory."""

from __future__ import annotations

from functools import cache

from app.core.config import get_settings
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.storage.postgres import PostgresCoreStore


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
        store = PostgresCoreStore.from_dsn(dsn)
        store.ensure_schema()
        return store

    msg = f"Unsupported storage backend: {backend}"
    raise ValueError(msg)
