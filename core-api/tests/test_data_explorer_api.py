"""Tests for the Data Explorer API."""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.routes.dashboard import get_core_store
from app.core.data_layer.normalized import Sale as NormalizedSale
from app.core.data_layer.normalized import SaleItem as NormalizedSaleItem
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.integrations.smartup.models import SmartUpOrganization, SmartUpRawRecord
from app.main import app


def _build_store() -> tuple[InMemoryCoreDataLayer, SmartUpOrganization, NormalizedSale]:
    store = InMemoryCoreDataLayer()
    organization = store.upsert_smartup_organization(
        SmartUpOrganization(
            name="MODAILY",
            filial_id="16114091",
            company_id="11300",
            project_code="trade",
            is_active=True,
        ),
    )
    sale = store.upsert_sale_v2(
        NormalizedSale(
            organization_id=organization.id,
            source_external_id="268805991",
            sale_number="268805991",
            amount=Decimal("606000"),
            currency="UZS",
            status="won",
            sale_at=datetime(2026, 8, 10, tzinfo=UTC),
        ),
    )
    store.upsert_sale_item(
        NormalizedSaleItem(
            organization_id=organization.id,
            source_external_id="268805991:1",
            sale_id=sale.id,
            sale_external_id="268805991",
            product_external_id="BALANCE PURIFYING G...",
            quantity=Decimal("4"),
            unit_price=Decimal("151500"),
            amount=Decimal("606000"),
            currency="UZS",
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization.id,
            filial_id=organization.filial_id,
            entity_type="sales",
            external_id="268805991",
            source_endpoint="/b/trade/txs/tdeal/order$export",
            request_payload={"begin_deal_date": "01.08.2026", "end_deal_date": "02.08.2026"},
            response_payload=[{"deal_id": "268805991", "order_products": [{"product_code": "1"}]}],
        ),
    )
    return store, organization, sale


def test_data_stats_endpoint_returns_raw_and_normalized_counts() -> None:
    store, organization, _sale = _build_store()

    app.dependency_overrides[get_core_store] = lambda: store
    client = TestClient(app)
    try:
        response = client.get("/api/v1/data/stats")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert payload["source_system"] == "SmartUp"
    assert payload["organizations"] == 1
    assert payload["raw_records"] == 1
    assert payload["normalized_records"] >= 2
    assert payload["processing_records"] == 0

    sections = {section["key"]: section for section in payload["sections"]}
    assert sections["organizations"]["count"] == 1
    assert sections["organizations"]["state"] == "available"
    assert sections["sales"]["raw_count"] == 1
    assert sections["sales"]["normalized_count"] == 1
    assert sections["sales"]["state"] == "available"
    assert sections["sales"]["href"] == "/api/v1/data/sales"
    assert sections["smartup-raw"]["raw_count"] == 1
    assert sections["smartup-raw"]["state"] == "available"
    assert sections["processing"]["count"] == 0
    assert sections["processing"]["state"] == "empty"


def test_data_sales_collection_paginates_records() -> None:
    store = InMemoryCoreDataLayer()
    organization = store.upsert_smartup_organization(
        SmartUpOrganization(
            name="MODAILY",
            filial_id="16114091",
            company_id="11300",
            project_code="trade",
            is_active=True,
        ),
    )
    sale_1 = store.upsert_sale_v2(
        NormalizedSale(
            organization_id=organization.id,
            source_external_id="268805991",
            sale_number="268805991",
            amount=Decimal("606000"),
            currency="UZS",
            status="won",
            sale_at=datetime(2026, 8, 10, tzinfo=UTC),
        ),
    )
    sale_2 = store.upsert_sale_v2(
        NormalizedSale(
            organization_id=organization.id,
            source_external_id="268802974",
            sale_number="268802974",
            amount=Decimal("381100"),
            currency="UZS",
            status="won",
            sale_at=datetime(2026, 8, 9, tzinfo=UTC),
        ),
    )
    store.upsert_sale_item(
        NormalizedSaleItem(
            organization_id=organization.id,
            source_external_id="268805991:1",
            sale_id=sale_1.id,
            sale_external_id="268805991",
            product_external_id="BALANCE PURIFYING G...",
            quantity=Decimal("4"),
            unit_price=Decimal("151500"),
            amount=Decimal("606000"),
            currency="UZS",
        ),
    )
    store.upsert_sale_item(
        NormalizedSaleItem(
            organization_id=organization.id,
            source_external_id="268802974:1",
            sale_id=sale_2.id,
            sale_external_id="268802974",
            product_external_id="OTHER PRODUCT",
            quantity=Decimal("2"),
            unit_price=Decimal("190550"),
            amount=Decimal("381100"),
            currency="UZS",
        ),
    )

    app.dependency_overrides[get_core_store] = lambda: store
    client = TestClient(app)
    try:
        response = client.get("/api/v1/data/sales", params={"page": 1, "page_size": 1})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset"] == "sales"
    assert payload["page"] == 1
    assert payload["page_size"] == 1
    assert payload["total"] == 2
    assert payload["total_pages"] == 2
    assert len(payload["items"]) == 1
    assert payload["items"][0]["organization_name"] == "MODAILY"
    assert payload["items"][0]["items_count"] == 1
    assert payload["items"][0]["products_count"] == 1
    assert payload["items"][0]["amount"] == "606000"
