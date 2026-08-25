"""API tests for SmartUp operational endpoints."""

from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.routes.smartup import get_core_store
from app.core.data_layer.entities import BusinessIdentity
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.integrations.smartup.bootstrap import SmartUpEnvBootstrapResult
from app.integrations.smartup.models import (
    SMARTUP_INTEGRATION_UUID,
    SmartUpMigrationRun,
    SmartUpOrganization,
    SmartUpRawRecord,
)
from app.integrations.smartup.operations import (
    SmartUpAccountService,
    SmartUpConnectionCheckResponse,
    SmartUpFilialCodeDiscoveryItem,
    SmartUpFilialCodeDiscoveryResponse,
    SmartUpHistoryMigrationRequest,
)
from app.main import app


def test_smartup_test_connection_route_returns_structured_probe(monkeypatch) -> None:
    def fake_check_connection(self, payload):  # noqa: ANN001
        return SmartUpConnectionCheckResponse(
            connected=False,
            code="SMARTUP_ACCESS_DENIED",
            message="Пользователь не имеет доступа к endpoint, проекту или выбранной организации",
            upstream_status=404,
            upstream_response="Forbidden",
            requested_url="https://smartup.online/b/anor/mxsx/mrf/room$export",
            project_code="trade",
            filial_id="86401",
        )

    monkeypatch.setattr(SmartUpAccountService, "check_connection", fake_check_connection)

    client = TestClient(app)
    response = client.post(
        "/api/v1/smartup/test-connection",
        json={
            "base_url": "https://api.greenwhite.uz",
            "username": "demo",
            "password": "secret",
            "filial_id": "86401",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["connected"] is False
    assert payload["code"] == "SMARTUP_ACCESS_DENIED"
    assert (
        payload["message"]
        == "Пользователь не имеет доступа к endpoint, проекту или выбранной организации"
    )
    assert payload["upstream_status"] == 404
    assert payload["upstream_response"] == "Forbidden"
    assert payload["requested_url"] == "https://smartup.online/b/anor/mxsx/mrf/room$export"
    assert payload["project_code"] == "trade"
    assert payload["filial_id"] == "86401"


def test_smartup_discover_filial_codes_route_returns_discovery_items(monkeypatch) -> None:
    store = InMemoryCoreDataLayer()

    def fake_discover_filial_codes(self):  # noqa: ANN001
        return SmartUpFilialCodeDiscoveryResponse(
            items=[
                SmartUpFilialCodeDiscoveryItem(
                    organization="MODAILY",
                    filial_id="16114091",
                    filial_code="16114091",
                    source="order_export",
                    status="found",
                ),
            ],
        )

    monkeypatch.setattr(SmartUpAccountService, "discover_filial_codes", fake_discover_filial_codes)
    monkeypatch.setattr("app.main.get_core_store", lambda: store)
    app.dependency_overrides[get_core_store] = lambda: store

    client = TestClient(app)
    try:
        response = client.post("/api/v1/smartup/discover-filial-codes")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["organization"] == "MODAILY"
    assert payload["items"][0]["filial_code"] == "16114091"


def test_smartup_organization_test_route_uses_same_persisted_organization_id(monkeypatch) -> None:
    store = InMemoryCoreDataLayer()
    organization = store.upsert_smartup_organization(
        SmartUpOrganization(
            id=UUID("164d4e9b-b1b0-5480-b91d-e4e0f39590aa"),
            integration_id=SMARTUP_INTEGRATION_UUID,
            name="Администрация",
            company_id="11300",
            filial_id="14475622",
            project_code="trade",
            is_active=True,
        ),
    )

    monkeypatch.setattr(
        "app.api.routes.smartup.bootstrap_smartup_organizations_from_env",
        lambda _store: SmartUpEnvBootstrapResult(organizations=[]),
    )
    app.dependency_overrides[get_core_store] = lambda: store

    class _DummyClient:
        def __init__(self, organization_arg):
            self.organization_id = organization_arg.id

        def _build_url(self, endpoint: str) -> str:  # noqa: D401
            return f"https://smartup.online{endpoint}"

        def request_response(self, method: str, endpoint: str, payload: dict[str, object]):  # noqa: ANN001
            return SimpleNamespace(
                status_code=200,
                text="{}",
                reason_phrase="OK",
                is_success=True,
            )

    def fake_resolve_organization_auth(self, organization_arg, payload=None, **kwargs):  # noqa: ANN001
        assert organization_arg.id == organization.id
        return SimpleNamespace(
            payload=SimpleNamespace(
                base_url="https://smartup.online",
                username="demo",
                password="secret",
                project_code=organization_arg.project_code,
                filial_id=organization_arg.filial_id,
                timeout_seconds=30.0,
            ),
            source="payload",
            credentials_available=True,
            client=None,
        )

    def fake_build_client_for_organization(self, organization_arg, payload=None, **kwargs):  # noqa: ANN001
        assert organization_arg.id == organization.id
        return _DummyClient(organization_arg)

    monkeypatch.setattr(
        SmartUpAccountService,
        "resolve_organization_auth",
        fake_resolve_organization_auth,
    )
    monkeypatch.setattr(
        SmartUpAccountService,
        "build_client_for_organization",
        fake_build_client_for_organization,
    )

    client = TestClient(app)
    try:
        list_response = client.get("/api/v1/smartup/organizations")
        test_response = client.post(
            f"/api/v1/smartup/organizations/{organization.id}/test",
            json={},
        )
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["id"] == str(organization.id)
    assert test_response.status_code == 200
    payload = test_response.json()
    assert payload["organization_id"] == str(organization.id)
    assert payload["organization_name"] == "Администрация"
    assert payload["connected"] is True


def test_smartup_organization_test_route_returns_404_for_unknown_id(monkeypatch) -> None:
    store = InMemoryCoreDataLayer()
    monkeypatch.setattr(
        "app.api.routes.smartup.bootstrap_smartup_organizations_from_env",
        lambda _store: SmartUpEnvBootstrapResult(organizations=[]),
    )
    app.dependency_overrides[get_core_store] = lambda: store

    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/smartup/organizations/164d4e9b-b1b0-5480-b91d-e4e0f39590aa/test",
            json={},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "SmartUp organization not found"


def test_smartup_migration_requires_manual_organizations(monkeypatch) -> None:
    def fake_migrate_history(self, payload):  # noqa: ANN001
        assert isinstance(payload, SmartUpHistoryMigrationRequest)
        raise ValueError(
            "Укажите хотя бы одну организацию вручную и свяжите её через filial_id. "
            "Автозагрузка организаций из SmartUp отключена."
        )

    monkeypatch.setattr(SmartUpAccountService, "migrate_history", fake_migrate_history)

    client = TestClient(app)
    response = client.post(
        "/api/v1/smartup/migration/history",
        json={
            "base_url": "https://smartup.online",
            "username": "demo",
            "password": "secret",
            "filial_id": "86401",
            "organizations": [],
        },
    )

    assert response.status_code == 422


def test_smartup_reset_data_clears_imported_tables_but_keeps_organizations() -> None:
    store = InMemoryCoreDataLayer()
    store.register_business(
        BusinessIdentity(
            name="Acme",
            legal_name="Acme",
            external_ref="acme",
        ),
    )
    organization = store.upsert_smartup_organization(
        SmartUpOrganization(
            id=UUID("11111111-1111-1111-1111-111111111111"),
            integration_id=SMARTUP_INTEGRATION_UUID,
            name="MODAILY",
            company_id="11300",
            filial_id="16114091",
            project_code="trade",
            is_active=True,
        ),
    )
    store.upsert_smartup_migration_run(
        SmartUpMigrationRun(
            organization_id=organization.id,
            entity_type="sales",
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization.id,
            filial_id=organization.filial_id,
            entity_type="sales",
            source_endpoint="/b/trade/txs/tdeal/order$export",
            response_payload=[{"id": "1"}],
        ),
    )

    app.dependency_overrides[get_core_store] = lambda: store
    client = TestClient(app)
    try:
        response = client.post("/api/v1/smartup/reset-data")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["cleared_total"] > 0
    assert payload["preserved_organizations"] == 1
    assert list(store.list_smartup_organizations())[0].name == "MODAILY"
    assert list(store.list_businesses()) == []
    assert list(store.list_smartup_raw_records()) == []

