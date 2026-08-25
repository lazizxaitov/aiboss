"""Tests for Phase 3C AI analytics API contract."""

from fastapi.testclient import TestClient

from app.api.routes.ai_analytics import get_core_store
from app.main import app
from tests.test_ai_analytics_seed import seed_ai_analytics_store


def _client_for_store(store):
    app.dependency_overrides[get_core_store] = lambda: store
    return TestClient(app)


def test_ai_analytics_brief_route_returns_provider_status_and_cache_metadata() -> None:
    store, organization, _other_organization = seed_ai_analytics_store()
    client = _client_for_store(store)

    try:
        response = client.get(
            "/api/v1/ai-analytics/brief",
            params={"organization_id": str(organization.organization_id), "language": "ru"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["executive_brief"]["headline"]
    assert payload["provider_status"]["health"] in {
        "DISABLED",
        "AVAILABLE",
        "DEGRADED",
        "UNAVAILABLE",
    }
    assert payload["cache_metadata"]["cache_key"]
    assert payload["cache_metadata"]["analytics_context_hash"]


def test_ai_analytics_insights_route_returns_semantic_feed() -> None:
    store, organization, _other_organization = seed_ai_analytics_store()
    client = _client_for_store(store)

    try:
        response = client.get(
            "/api/v1/ai-analytics/insights",
            params={"organization_id": str(organization.organization_id), "language": "ru"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["top_insights"]
    assert payload["dashboard_feed"]
    assert payload["provider_status"]["provider"]
