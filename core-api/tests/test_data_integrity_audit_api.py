"""Tests for the full system SmartUp data integrity audit."""

from fastapi.testclient import TestClient

from app.api.routes.dashboard import get_core_store
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.main import app


def test_data_integrity_audit_endpoint_returns_combined_report() -> None:
    store = InMemoryCoreDataLayer()
    app.dependency_overrides[get_core_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get("/api/v1/data/audit")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_system"] == "SmartUp"
    assert "dataset_inventory" in payload
    assert "discovery" in payload
    assert "coverage" in payload
    assert "explorer" in payload
    assert isinstance(payload["dataset_inventory"], list)
