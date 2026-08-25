"""Tests for the canonical Visits / Field Sales workspace API."""

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


def test_visits_workspace_list_returns_summary_and_rows() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        response = client.get(
            "/api/v1/visits",
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

    assert Decimal(payload["summary"]["visits"]["value"]) == Decimal("2")
    assert Decimal(payload["summary"]["unique_customers"]["value"]) == Decimal("2")
    assert Decimal(payload["summary"]["sales_reps"]["value"]) == Decimal("2")
    assert Decimal(payload["summary"]["working_zones"]["value"]) == Decimal("0")
    assert payload["summary"]["visit_conversion"]["data_status"] == "NOT_AVAILABLE"
    assert payload["active_tab"] == "visits"
    assert payload["pagination"]["total_items"] == 2
    assert len(payload["rows"]["visits"]) == 2
    first_row = payload["rows"]["visits"][0]
    assert first_row["customer_name"] in {"Current Customer", "Previous Customer"}
    assert first_row["sales_rep_name"] in {"Rep One", "Rep Two"}


def test_visits_workspace_supports_reps_tab() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        response = client.get(
            "/api/v1/visits",
            params=[
                ("organization_ids", org_one_id),
                ("organization_ids", org_two_id),
                ("period", "all"),
                ("tab", "sales_reps"),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_tab"] == "sales_reps"
    assert payload["pagination"]["total_items"] == 2
    assert len(payload["rows"]["sales_reps"]) == 2
    assert payload["rows"]["sales_reps"][0]["visit_conversion"]["data_status"] == "NOT_AVAILABLE"


def test_visits_workspace_detail_returns_visit_360_sections() -> None:
    client, org_one_id, org_two_id = _client_for_seed()

    try:
        list_response = client.get(
            "/api/v1/visits",
            params=[
                ("organization_ids", org_one_id),
                ("organization_ids", org_two_id),
                ("period", "all"),
                ("search", "Current Customer"),
            ],
        )
        visit_id = list_response.json()["rows"]["visits"][0]["visit_id"]
        response = client.get(
            f"/api/v1/visits/{visit_id}",
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
    assert payload["customer"]["customer_name"] == "Current Customer"
    assert payload["sales_rep"]["sales_rep_name"] == "Rep One"
    assert payload["working_zone"]["working_zone_name"] is None
    assert payload["related_sales_status"] == "NOT_AVAILABLE"
    assert "Детерминированная связь визит → заказ/продажа" in " ".join(payload["limitations"])
