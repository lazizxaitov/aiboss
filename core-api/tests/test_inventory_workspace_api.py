"""Tests for the canonical Inventory / Warehouse workspace API."""

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


def test_inventory_workspace_current_stock_returns_summary_and_rows() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        response = client.get(
            "/api/v1/inventory",
            params=[
                ("organization_ids", org_one_id),
                ("organization_ids", org_two_id),
                ("period", "all"),
                ("view", "current_stock"),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert payload["active_view"] == "current_stock"
    assert Decimal(payload["summary"]["current_stock_quantity"]["value"]) == Decimal("6")
    assert Decimal(payload["summary"]["products_in_stock"]["value"]) == Decimal("2")
    assert Decimal(payload["summary"]["warehouses"]["value"]) == Decimal("2")
    assert payload["pagination"]["total_items"] == 3
    assert any(tab["view"] == "purchases" and tab["count"] == 1 for tab in payload["tabs"])

    first_row = payload["rows"]["current_stock"][0]
    assert "product_name" in first_row
    assert "stock_status" in first_row
    assert first_row["organization_name"] in {"Alpha LLC", "Beta LLC"}


def test_inventory_workspace_warehouse_view_returns_rows() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        response = client.get(
            "/api/v1/inventory",
            params=[
                ("organization_ids", org_one_id),
                ("organization_ids", org_two_id),
                ("period", "all"),
                ("view", "warehouses"),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert payload["active_view"] == "warehouses"
    assert payload["pagination"]["total_items"] >= 2
    row = payload["rows"]["warehouses"][0]
    assert "warehouse_key" in row
    assert "products_count" in row
    assert "organization_name" in row


def test_inventory_workspace_purchase_view_exposes_document_rows() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        response = client.get(
            "/api/v1/inventory",
            params=[
                ("organization_ids", org_one_id),
                ("organization_ids", org_two_id),
                ("period", "all"),
                ("view", "purchases"),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert payload["active_view"] == "purchases"
    assert payload["pagination"]["total_items"] == 1
    purchase = payload["rows"]["purchases"][0]
    assert purchase["document_number"] == "PUR-001"
    assert purchase["supplier_code"] == "SUP-001"
    assert purchase["product_linkage_coverage"] == "0.5"
    assert purchase["quality_note"] is not None


def test_inventory_current_stock_detail_returns_related_sections() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        list_response = client.get(
            "/api/v1/inventory",
            params=[
                ("organization_ids", org_one_id),
                ("organization_ids", org_two_id),
                ("period", "all"),
                ("view", "current_stock"),
                ("search", "BAL-001"),
            ],
        )
        inventory_balance_id = list_response.json()["rows"]["current_stock"][0][
            "inventory_balance_id"
        ]
        response = client.get(
            f"/api/v1/inventory/current-stock/{inventory_balance_id}",
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
    assert isinstance(payload["recent_snapshots"], list)
    assert isinstance(payload["recent_receipts"], list)
    assert isinstance(payload["recent_writeoffs"], list)
    assert isinstance(payload["recent_movements"], list)


def test_inventory_warehouse_detail_returns_warehouse_360_sections() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        list_response = client.get(
            "/api/v1/inventory",
            params=[
                ("organization_ids", org_one_id),
                ("organization_ids", org_two_id),
                ("period", "all"),
                ("view", "warehouses"),
                ("search", "Центральный склад"),
            ],
        )
        warehouse_key = list_response.json()["rows"]["warehouses"][0]["warehouse_key"]
        response = client.get(
            f"/api/v1/inventory/warehouses/{warehouse_key}",
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

    assert payload["row"]["warehouse_name"] == "Центральный склад"
    assert isinstance(payload["current_stock"], list)
    assert isinstance(payload["purchases"], list)
    assert isinstance(payload["receipts"], list)
    assert isinstance(payload["writeoffs"], list)
    assert isinstance(payload["movements"], list)
