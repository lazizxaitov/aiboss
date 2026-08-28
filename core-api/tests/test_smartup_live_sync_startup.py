from types import SimpleNamespace
from uuid import uuid4

from app.core.data_layer.service import InMemoryCoreDataLayer
from app.integrations.smartup.live_sync import SmartUpLiveSyncService
from app.integrations.smartup.models import SmartUpOrganization
from app.integrations.smartup.operations import SmartUpConnectionCheckResponse


def _response(organization: SmartUpOrganization, connected: bool) -> SmartUpConnectionCheckResponse:
    return SmartUpConnectionCheckResponse(
        connected=connected,
        code="SMARTUP_CONNECTION_OK" if connected else "SMARTUP_UNAVAILABLE",
        message="Соединение установлено" if connected else "SmartUp недоступен",
        requested_url="https://smartup.example.test",
        organization_id=organization.id,
        organization_name=organization.name,
        status="connected" if connected else "unavailable",
    )


def _service_with_organizations(monkeypatch, organizations, connection_results):
    store = InMemoryCoreDataLayer()
    for organization in organizations:
        store.upsert_smartup_organization(organization)
    calls = []

    class FakeAccountService:
        def __init__(self, target):
            assert target is store

        def list_organizations(self):
            return organizations

        def resolve_organization_auth(self, organization):
            return SimpleNamespace(credentials_available=True)

        def check_connection(self, organization_id, payload):
            calls.append((organization_id, payload))
            result = connection_results[len(calls) - 1]
            return result

    monkeypatch.setattr(
        "app.integrations.smartup.live_sync.SmartUpAccountService",
        FakeAccountService,
    )
    return SmartUpLiveSyncService(store), calls


def test_start_only_schedules_background_loop(monkeypatch):
    store = InMemoryCoreDataLayer()
    service = SmartUpLiveSyncService(store)
    called = []
    monkeypatch.setattr(service, "_run_loop", lambda: called.append(True))

    service.start()
    service._thread.join(timeout=1)

    assert called == [True]
    service.stop()


def test_startup_verifies_each_organization_and_keeps_partial_success(monkeypatch):
    organizations = [
        SmartUpOrganization(id=uuid4(), name="One", filial_id="1"),
        SmartUpOrganization(id=uuid4(), name="Two", filial_id="2"),
    ]
    service, calls = _service_with_organizations(
        monkeypatch,
        organizations,
        [_response(organizations[0], True), _response(organizations[1], False)],
    )

    assert service._verify_startup_connections() is True
    status = service.status()

    assert [call[0] for call in calls] == [item.id for item in organizations]
    assert [item.status for item in status.organization_connections] == ["connected", "retry_wait"]
    assert status.organization_connections[0].sync_available is True
    assert status.organization_connections[1].sync_available is False


def test_retry_verification_restores_organization(monkeypatch):
    organization = SmartUpOrganization(id=uuid4(), name="One", filial_id="1")
    service, _ = _service_with_organizations(
        monkeypatch,
        [organization],
        [_response(organization, False)],
    )
    assert service._verify_startup_connections() is False
    assert service.status().status == "retry_wait"

    class RestoredAccountService:
        def __init__(self, target):
            pass

        def list_organizations(self):
            return [organization]

        def resolve_organization_auth(self, item):
            return SimpleNamespace(credentials_available=True)

        def check_connection(self, organization_id, payload):
            return _response(organization, True)

    monkeypatch.setattr(
        "app.integrations.smartup.live_sync.SmartUpAccountService",
        RestoredAccountService,
    )

    assert service._verify_startup_connections() is True
    restored = service.status().organization_connections[0]
    assert restored.status == "connected"
    assert restored.sync_available is True
