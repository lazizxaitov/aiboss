"""Tests for the canonical Products / Product 360 workspace API."""

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


def test_product_workspace_list_returns_summary_and_rows() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        response = client.get(
            "/api/v1/products",
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

    assert Decimal(payload["summary"]["products"]["value"]) == Decimal("3")
    assert Decimal(payload["summary"]["products_sold"]["value"]) == Decimal("3")
    assert Decimal(payload["summary"]["sold_units"]["value"]) == Decimal("8")
    assert Decimal(payload["summary"]["revenue"]["value"]) == Decimal("607000")
    assert Decimal(payload["summary"]["return_quantity"]["value"]) == Decimal("1")
    assert Decimal(payload["summary"]["return_value"]["value"]) == Decimal("50")
    assert payload["pagination"]["total_items"] == 3

    top_row = payload["rows"][0]
    assert top_row["product_code"] == "BAL-001"
    assert top_row["product_name"] == "Balance Purifying Gel"
    assert top_row["revenue"] == "606000"
    assert top_row["sold_units"] == "4"
    assert top_row["customers_count"] == "1"
    assert top_row["return_quantity"] == "1"
    assert top_row["stock_status"] == "OUT_OF_STOCK"


def test_product_workspace_filters_by_stock_status() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        response = client.get(
            "/api/v1/products",
            params=[
                ("organization_ids", org_one_id),
                ("organization_ids", org_two_id),
                ("period", "all"),
                ("stock_status", "OUT_OF_STOCK"),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total_items"] == 1
    assert payload["rows"][0]["product_code"] == "BAL-001"


def test_product_workspace_detail_returns_product_360_sections() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        list_response = client.get(
            "/api/v1/products",
            params=[
                ("organization_ids", org_one_id),
                ("organization_ids", org_two_id),
                ("period", "all"),
                ("search", "BAL-001"),
            ],
        )
        product_id = list_response.json()["rows"][0]["product_id"]
        response = client.get(
            f"/api/v1/products/{product_id}",
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

    assert payload["row"]["product_code"] == "BAL-001"
    assert Decimal(payload["overview"]["revenue"]["value"]) == Decimal("606000")
    assert Decimal(payload["overview"]["sold_units"]["value"]) == Decimal("4")
    assert len(payload["sales"]) == 1
    assert payload["sales"][0]["deal_id"] == "268805991"
    assert len(payload["customers"]) == 1
    assert payload["customers"][0]["customer_name"] == "Current Customer"
    assert len(payload["inventory"]) == 1
    assert payload["inventory"][0]["warehouse_code"] == "WH-1"
    assert len(payload["returns"]) == 1
    assert payload["returns"][0]["returned_quantity"] == "1"
    assert len(payload["prices"]) == 1
    assert payload["prices"][0]["source_type"] == "observed_sale_price"
    assert payload["prices"][0]["price"] == "151500"
    assert payload["ai_summary"] is not None
    assert "Нет подтверждённой прайс-лист цены." in payload["limitations"]
