"""Tests for the canonical Sales / Orders workspace API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.data_layer.canonical_v2 import (
    CanonicalDataQualityStatus,
    CanonicalOrder,
    canonical_row_uuid,
)
from app.core.data_layer.factory import get_core_store
from app.main import app
from tests.test_analytics_engine import _seed_analytics_store


def _client_for_seed() -> tuple[TestClient, str, str]:
    store, org_one, org_two = _seed_analytics_store()
    store.upsert_canonical_order(
        CanonicalOrder(
            id=canonical_row_uuid("order", org_one.organization_id, "order-unrealised"),
            organization_id=org_one.organization_id,
            source_endpoint="order$export",
            source_external_id="order-unrealised",
            order_id="ord-3",
            deal_id="268899999",
            order_number="268899999",
            order_at=datetime.now(UTC) - timedelta(days=3),
            customer_external_id="cust-current",
            customer_name="Current Customer",
            normalized_status="new",
            display_status="NEW",
            total_amount=Decimal("125000"),
            currency_code="UZS",
            source_currency_code="860",
            item_count=1,
            ordered_quantity=Decimal("5"),
            sold_quantity=Decimal("0"),
            data_quality_status=CanonicalDataQualityStatus.PARTIAL,
        )
    )
    app.dependency_overrides[get_core_store] = lambda: store
    return TestClient(app), str(org_one.organization_id), str(org_two.organization_id)


def test_sales_workspace_list_returns_summary_and_rows() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        response = client.get(
            "/api/v1/sales",
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

    assert Decimal(payload["summary"]["revenue"]["value"]) == Decimal("607000")
    assert Decimal(payload["summary"]["orders"]["value"]) == Decimal("3")
    assert Decimal(payload["summary"]["realised_sales"]["value"]) == Decimal("4")
    assert Decimal(payload["summary"]["sold_units"]["value"]) == Decimal("8")
    assert Decimal(payload["summary"]["payments_received"]["value"]) == Decimal("606000")
    assert Decimal(payload["summary"]["return_value"]["value"]) == Decimal("50")
    assert payload["pagination"]["total_items"] >= 5

    realised_row = next((row for row in payload["rows"] if row["deal_id"] == "268805991"), None)
    assert realised_row is not None
    assert realised_row["row_kind"] == "order"
    assert realised_row["realised"] is True
    assert realised_row["realised_amount"] == "606000"
    assert realised_row["sold_units"] == "4"
    assert realised_row["returned_units"] == "1"


def test_sales_workspace_preserves_order_vs_sale_semantics() -> None:
    client, org_one_id, _ = _client_for_seed()

    try:
        response = client.get(
            "/api/v1/sales",
            params=[
                ("organization_ids", org_one_id),
                ("period", "all"),
                ("search", "268899999"),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total_items"] == 1
    row = payload["rows"][0]
    assert row["deal_id"] == "268899999"
    assert row["row_kind"] == "order"
    assert row["realised"] is False
    assert row["realised_amount"] is None
    assert row["order_amount"] == "125000"
    assert row["data_status"] == "PARTIAL"


def test_sales_workspace_filters_realised_rows() -> None:
    client, org_one_id, _ = _client_for_seed()

    try:
        response = client.get(
            "/api/v1/sales",
            params=[
                ("organization_ids", org_one_id),
                ("period", "all"),
                ("realised", "true"),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert all(row["realised"] for row in payload["rows"])
    assert all(row["realised_amount"] is not None for row in payload["rows"])


def test_sales_workspace_detail_returns_line_items_returns_and_payments() -> None:
    client, org_one_id, _ = _client_for_seed()

    try:
        list_response = client.get(
            "/api/v1/sales",
            params=[
                ("organization_ids", org_one_id),
                ("period", "all"),
                ("search", "268805991"),
            ],
        )
        record_id = list_response.json()["rows"][0]["record_id"]
        response = client.get(
            f"/api/v1/sales/{record_id}",
            params=[
                ("organization_ids", org_one_id),
                ("period", "all"),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert payload["row"]["deal_id"] == "268805991"
    assert len(payload["items"]) == 1
    assert payload["items"][0]["product_code"] == "BAL-001"
    assert payload["items"][0]["ordered_quantity"] == "4"
    assert payload["items"][0]["sold_quantity"] == "4"
    assert payload["items"][0]["amount"] == "606000"
    assert len(payload["returns"]) == 1
    assert payload["returns"][0]["returned_quantity"] == "1"
    assert len(payload["payments"]) == 1
    assert payload["payments"][0]["amount"] == "606000"
    assert payload["provenance"]["source_endpoint"] == "order$export"
