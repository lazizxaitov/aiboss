"""Tests for the global organization context."""

from fastapi.testclient import TestClient

from app.api.routes.dashboard import get_core_store
from app.core.data_layer.entities import BusinessProfile
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.main import app


def test_organization_context_round_trip_is_persisted() -> None:
    store = InMemoryCoreDataLayer()
    first = store.register_business(BusinessProfile(name="Acme LLC", legal_name="Acme LLC"))
    second = store.register_business(BusinessProfile(name="Beta LLC", legal_name="Beta LLC"))

    app.dependency_overrides[get_core_store] = lambda: store
    client = TestClient(app)

    try:
        update_response = client.put(
            "/api/v1/organization-context",
            json={
                "organization_context": {
                    "mode": "multiple",
                    "organization_ids": [
                        str(first.business_id),
                        str(second.business_id),
                    ],
                },
                "period_context": {
                    "preset": "30d",
                    "date_from": None,
                    "date_to": None,
                },
            },
        )
        assert update_response.status_code == 200
        update_payload = update_response.json()
        assert update_payload["organization_context"]["mode"] == "multiple"
        assert len(update_payload["organization_context"]["organization_ids"]) == 2

        get_response = client.get("/api/v1/organization-context")
        assert get_response.status_code == 200
        get_payload = get_response.json()
        assert get_payload["organization_context"]["mode"] == "multiple"
        assert len(get_payload["organization_context"]["organization_ids"]) == 2
        assert store.get_app_setting("global_analytics_context") is not None
    finally:
        app.dependency_overrides.clear()


def test_dashboard_overview_uses_persisted_organization_context() -> None:
    store = InMemoryCoreDataLayer()
    first = store.register_business(BusinessProfile(name="Acme LLC", legal_name="Acme LLC"))
    second = store.register_business(BusinessProfile(name="Beta LLC", legal_name="Beta LLC"))

    app.dependency_overrides[get_core_store] = lambda: store
    client = TestClient(app)

    try:
        client.put(
            "/api/v1/organization-context",
            json={
                "organization_context": {
                    "mode": "single",
                    "organization_ids": [str(second.business_id)],
                },
            },
        )

        response = client.get("/api/v1/dashboard/overview")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["businesses"]) == 1
        assert payload["businesses"][0]["name"] == second.name
        assert payload["analytics_snapshot"]["business_count"] == 1
        assert payload["analytics_snapshot"]["organization_ids"] == [
            str(second.business_id),
        ]

        app.dependency_overrides[get_core_store] = lambda: store
        reset_response = client.delete("/api/v1/organization-context")
        assert reset_response.status_code == 200
        reset_payload = reset_response.json()
        assert reset_payload["organization_context"]["mode"] == "all"

        overview_response = client.get("/api/v1/dashboard/overview")
        assert overview_response.status_code == 200
        overview_payload = overview_response.json()
        assert len(overview_payload["businesses"]) == 2
        assert {item["name"] for item in overview_payload["businesses"]} == {
            first.name,
            second.name,
        }
    finally:
        app.dependency_overrides.clear()
