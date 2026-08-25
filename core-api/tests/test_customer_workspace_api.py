"""Tests for the canonical Customers / Customer 360 workspace API."""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.data_layer.factory import get_core_store
from app.main import app
from tests.test_analytics_engine import _seed_analytics_store


def _client_for_seed() -> tuple[TestClient, str, str]:
    store, org_one, org_two = _seed_analytics_store()
    app.dependency_overrides[get_core_store] = lambda: store
    return TestClient(app), str(org_one.organization_id), str(org_two.organization_id)


def test_customer_workspace_list_returns_summary_and_rows() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        response = client.get(
            "/api/v1/customers",
            params=[
                ("organization_ids", org_one_id),
                ("organization_ids", org_two_id),
                ("period", "all"),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert Decimal(payload["summary"]["unique_customers"]["value"]) == Decimal("4")
    assert Decimal(payload["summary"]["customers_with_sales"]["value"]) == Decimal("4")
    assert Decimal(payload["summary"]["revenue"]["value"]) == Decimal("607000")
    assert Decimal(payload["summary"]["payments_received"]["value"]) == Decimal("606000")
    assert Decimal(payload["summary"]["return_value"]["value"]) == Decimal("50")
    assert Decimal(payload["summary"]["visits"]["value"]) == Decimal("2")
    assert payload["pagination"]["total_items"] == 4

    top_row = payload["rows"][0]
    assert top_row["customer_name"] == "Current Customer"
    assert top_row["revenue"] == "606000"
    assert top_row["payments_received"] == "606000"
    assert top_row["visits_count"] == "1"
    assert top_row["products_bought_count"] == "1"


def test_customer_workspace_filters_by_payments() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        response = client.get(
            "/api/v1/customers",
            params=[
                ("organization_ids", org_one_id),
                ("organization_ids", org_two_id),
                ("period", "all"),
                ("has_payments", "true"),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total_items"] == 1
    assert payload["rows"][0]["customer_name"] == "Current Customer"


def test_customer_workspace_detail_returns_customer_360_sections() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        list_response = client.get(
            "/api/v1/customers",
            params=[
                ("organization_ids", org_one_id),
                ("organization_ids", org_two_id),
                ("period", "all"),
                ("search", "Current Customer"),
            ],
        )
        customer_id = list_response.json()["rows"][0]["customer_id"]
        response = client.get(
            f"/api/v1/customers/{customer_id}",
            params=[
                ("organization_ids", org_one_id),
                ("organization_ids", org_two_id),
                ("period", "all"),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert payload["row"]["customer_name"] == "Current Customer"
    assert Decimal(payload["overview"]["revenue"]["value"]) == Decimal("606000")
    assert len(payload["sales"]) == 1
    assert payload["sales"][0]["deal_id"] == "268805991"
    assert len(payload["products"]) == 1
    assert payload["products"][0]["product_code"] == "BAL-001"
    assert len(payload["payments"]) == 1
    assert payload["payments"][0]["amount"] == "606000"
    assert len(payload["returns"]) == 1
    assert payload["returns"][0]["returned_quantity"] == "1"
    assert len(payload["visits"]) == 1
    assert len(payload["timeline"]) >= 4
    assert payload["provenance"]["source_endpoint"] == "legal_person$export"
