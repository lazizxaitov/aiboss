"""Tests for SmartUp environment bootstrap."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.data_layer.factory import get_core_store
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.integrations.smartup.bootstrap import bootstrap_smartup_organizations_from_env
from app.integrations.smartup.settings import SmartUpOrganizationConfig, SmartUpSettings
from app.main import app


def test_bootstrap_smartup_organizations_from_env_seeds_store() -> None:
    store = InMemoryCoreDataLayer()
    settings = SmartUpSettings(
        organizations=[
            SmartUpOrganizationConfig(
                name="MODAILY",
                company_id="11300",
                filial_id="16114091",
                project_code="trade",
            ),
            SmartUpOrganizationConfig(
                name="SAMO SERVIS",
                company_id="11300",
                filial_id="14479324",
                project_code="trade",
            ),
        ],
    )

    result = bootstrap_smartup_organizations_from_env(store, settings)

    assert len(result.organizations) == 2
    organizations = list(store.list_smartup_organizations())
    assert [organization.name for organization in organizations] == ["MODAILY", "SAMO SERVIS"]
    assert organizations[0].filial_id == "16114091"
    assert organizations[1].filial_id == "14479324"
    assert organizations[0].metadata["bootstrap_source"] == "env"


def test_sync_smartup_organizations_from_env_endpoint_uses_store_override() -> None:
    store = InMemoryCoreDataLayer()
    app.dependency_overrides[get_core_store] = lambda: store
    try:
        client = TestClient(app)
        response = client.post("/api/v1/smartup/organizations/sync-from-env")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["loaded"] >= 0


def test_app_startup_materializes_canonical_v2_after_bootstrap(monkeypatch) -> None:
    store = InMemoryCoreDataLayer()
    calls: list[str] = []

    def fake_get_core_store() -> InMemoryCoreDataLayer:
        return store

    def fake_bootstrap(target_store: InMemoryCoreDataLayer) -> SimpleNamespace:
        assert target_store is store
        calls.append("bootstrap")
        return SimpleNamespace(organizations=[object()])

    class FakeCanonicalService:
        def __init__(self, target_store: InMemoryCoreDataLayer) -> None:
            assert target_store is store
            calls.append("service_init")

        def backfill_all(self) -> list[object]:
            calls.append("backfill_all")
            return [object()]

    monkeypatch.setattr("app.main.get_core_store", fake_get_core_store)
    monkeypatch.setattr(
        "app.main.bootstrap_smartup_organizations_from_env",
        fake_bootstrap,
    )
    monkeypatch.setattr(
        "app.main.SmartUpCanonicalV2FoundationService",
        FakeCanonicalService,
    )

    with TestClient(app) as client:
        assert client.get("/").status_code == 200

    assert calls == ["bootstrap", "service_init", "backfill_all"]


def test_get_core_store_raises_when_postgres_unavailable(monkeypatch) -> None:
    class FakeSettings:
        storage_backend = "postgres"
        postgres_dsn = "postgresql://postgres:postgres@localhost:5432/ai_business_os"

    def fake_get_settings() -> FakeSettings:
        return FakeSettings()

    def fake_from_dsn(dsn: str):  # noqa: ANN001
        raise RuntimeError(f"connection refused for {dsn}")

    get_core_store.cache_clear()
    monkeypatch.setattr("app.core.data_layer.factory.get_settings", fake_get_settings)
    monkeypatch.setattr(
        "app.core.data_layer.factory.PostgresCoreStore.from_dsn",
        staticmethod(fake_from_dsn),
    )

    with pytest.raises(RuntimeError, match="connection refused"):
        get_core_store()

    get_core_store.cache_clear()
