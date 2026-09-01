"""Tests for the Core store lifecycle boundaries."""

from concurrent.futures import ThreadPoolExecutor

from app.core.data_layer import factory


class _Store:
    def __init__(self) -> None:
        self.ensure_calls = 0

    def ensure_schema(self) -> None:
        self.ensure_calls += 1


def test_initialize_core_store_runs_schema_once() -> None:
    store = _Store()
    factory._initialized_store_ids.discard(id(store))

    factory.initialize_core_store(store)
    factory.initialize_core_store(store)

    assert store.ensure_calls == 1


def test_initialize_core_store_ignores_runtime_store_without_schema() -> None:
    class RuntimeStore:
        pass

    factory.initialize_core_store(RuntimeStore())


def test_get_core_store_does_not_initialize_postgres_schema(monkeypatch) -> None:
    class FakeSettings:
        storage_backend = "postgres"
        postgres_dsn = "postgresql://example"

    store = _Store()
    factory.get_core_store.cache_clear()
    factory._initialized_store_ids.discard(id(store))
    monkeypatch.setattr(factory, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(
        factory.PostgresCoreStore,
        "from_dsn",
        staticmethod(lambda dsn: store),
    )

    assert factory.get_core_store() is store
    assert store.ensure_calls == 0
    factory.get_core_store.cache_clear()


def test_concurrent_runtime_store_access_performs_no_schema_initialization(monkeypatch) -> None:
    class FakeSettings:
        storage_backend = "postgres"
        postgres_dsn = "postgresql://example"

    store = _Store()
    factory.get_core_store.cache_clear()
    factory._initialized_store_ids.discard(id(store))
    monkeypatch.setattr(factory, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(
        factory.PostgresCoreStore,
        "from_dsn",
        staticmethod(lambda dsn: store),
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        stores = list(executor.map(lambda _: factory.get_core_store(), range(32)))

    assert all(runtime_store is store for runtime_store in stores)
    assert store.ensure_calls == 0
    factory.get_core_store.cache_clear()
