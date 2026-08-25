"""Tests for the canonical Finance workspace API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.data_layer.canonical_v2 import (
    CanonicalDataQualityStatus,
    CanonicalFinancialDirection,
    CanonicalFinancialOperation,
    CanonicalPayment,
    canonical_row_uuid,
)
from app.core.data_layer.factory import get_core_store
from app.main import app
from tests.test_analytics_engine import _seed_analytics_store


def _client_for_seed() -> tuple[TestClient, str, str]:
    store, org_one, org_two = _seed_analytics_store()
    app.dependency_overrides[get_core_store] = lambda: store
    return TestClient(app), str(org_one.organization_id), str(org_two.organization_id)


def test_finance_workspace_overview_returns_status_aware_summary() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        response = client.get(
            "/api/v1/finance",
            params=[
                ("organization_ids", org_one_id),
                ("organization_ids", org_two_id),
                ("period", "all"),
                ("view", "overview"),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert payload["active_view"] == "overview"
    assert Decimal(payload["summary"]["payments_received"]["value"]) == Decimal("606000")
    assert Decimal(payload["summary"]["verified_cash_in"]["value"]) == Decimal("606000")
    assert Decimal(payload["summary"]["verified_cash_out"]["value"]) == Decimal("100000")
    assert Decimal(payload["summary"]["net_cash_flow"]["value"]) == Decimal("506000")
    assert Decimal(payload["summary"]["customer_return_value"]["value"]) == Decimal("50")
    assert payload["pagination"]["total_items"] == 2
    assert any(item["label"] == "Денежные расходы" for item in payload["coverage"])


def test_finance_workspace_payments_exposes_allocation_status() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        response = client.get(
            "/api/v1/finance",
            params=[
                ("organization_ids", org_one_id),
                ("organization_ids", org_two_id),
                ("period", "all"),
                ("view", "payments"),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    row = payload["rows"]["payments"][0]

    assert row["payment_type"] == "cash"
    assert row["allocation_status"] == "Связан с конкретным заказом"
    assert row["linked_order_external_id"] == "sale-current"
    assert row["currency_code"] == "UZS"


def test_finance_workspace_cash_flow_keeps_no_verified_data_regression_guard() -> None:
    store, org_one, _org_two = _seed_analytics_store()

    # Remove verified outflows to reproduce the old false-zero / negative-cashflow regression.
    for key, value in list(store.canonical_financial_operations.items()):
        if value.direction == CanonicalFinancialDirection.OUTFLOW:
            del store.canonical_financial_operations[key]

    target_amount = Decimal("346923200")
    now = datetime.now(UTC)
    store.upsert_canonical_payment(
        CanonicalPayment(
            id=canonical_row_uuid("payment", org_one.organization_id, "phase4g-payment"),
            organization_id=org_one.organization_id,
            source_endpoint="cashin$export",
            source_external_id="phase4g-payment",
            payment_id="pay-phase4g",
            cashin_id="cashin-phase4g",
            paid_at=now - timedelta(days=1),
            customer_name="MODAILY PAYMENT",
            normalized_payment_type="cash",
            amount=target_amount,
            currency_code="UZS",
            source_currency_code="860",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    store.upsert_canonical_financial_operation(
        CanonicalFinancialOperation(
            id=canonical_row_uuid("fin-op", org_one.organization_id, "phase4g-cashin"),
            organization_id=org_one.organization_id,
            source_endpoint="cashin$export",
            source_external_id="phase4g-cashin",
            operation_id="op-phase4g",
            operation_date=now - timedelta(days=1),
            normalized_operation_type="customer_payment",
            direction=CanonicalFinancialDirection.INFLOW,
            amount=target_amount,
            currency_code="UZS",
            source_currency_code="860",
            is_internal_transfer=False,
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )

    app.dependency_overrides[get_core_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get(
            "/api/v1/finance",
            params=[
                ("organization_ids", str(org_one.organization_id)),
                ("period", "all"),
                ("view", "overview"),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert Decimal(payload["summary"]["payments_received"]["value"]) == Decimal("347529200")
    assert payload["summary"]["verified_cash_out"]["value"] is None
    assert payload["summary"]["verified_cash_out"]["data_status"] == "NO_VERIFIED_DATA"
    assert payload["summary"]["net_cash_flow"]["value"] is None
    assert payload["summary"]["net_cash_flow"]["data_status"] == "NO_VERIFIED_DATA"
    cash_out_coverage = next(item for item in payload["coverage"] if item["key"] == "cash_out")
    assert cash_out_coverage["message"] == "Нет подтверждённых данных о денежных расходах"


def test_finance_workspace_operations_filters_by_direction() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        response = client.get(
            "/api/v1/finance",
            params=[
                ("organization_ids", org_one_id),
                ("organization_ids", org_two_id),
                ("period", "all"),
                ("view", "financial_operations"),
                ("direction", "OUTFLOW"),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert payload["pagination"]["total_items"] == 1
    row = payload["rows"]["financial_operations"][0]
    assert row["direction"] == "OUTFLOW"
    assert row["source_type"] == "cash_operation"
    assert row["overlaps_customer_payment"] is False
