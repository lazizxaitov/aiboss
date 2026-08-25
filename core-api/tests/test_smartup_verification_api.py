"""Tests for SmartUp verification and mirror APIs."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.routes.data import get_core_store
from app.core.data_layer.normalized import (
    BankOperation,
    BusinessDocument,
    BusinessDocumentItem,
    Customer,
    InventoryBalance,
    Payment,
    PriceType,
    Product,
    ProductPrice,
    Sale,
    SaleItem,
    Visit,
    Warehouse,
)
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.integrations.smartup.models import (
    MigrationBatch,
    NormalizationIssue,
    NormalizationIssueSeverity,
    SmartUpMigrationStatus,
    SmartUpOrganization,
    SmartUpRawRecord,
)
from app.main import app


def _seed_store() -> tuple[InMemoryCoreDataLayer, SmartUpOrganization]:
    store = InMemoryCoreDataLayer()
    organization = store.upsert_smartup_organization(
        SmartUpOrganization(
            name="MODAILY",
            company_id="11300",
            filial_id="16114091",
            project_code="trade",
            is_active=True,
        ),
    )

    customer = store.upsert_customer(
        Customer(
            organization_id=organization.id,
            source_external_id="cust-001",
            name="John Smith",
            phone="+998901234567",
        ),
    )
    product = store.upsert_product(
        Product(
            organization_id=organization.id,
            source_external_id="prod-001",
            name="Balance Purifying Gel",
            category_external_id="cat-001",
            sku="SKU-001",
            unit="pcs",
        ),
    )
    warehouse = store.upsert_warehouse(
        Warehouse(
            organization_id=organization.id,
            source_external_id="wh-001",
            name="Main Warehouse",
            code="WH-001",
        ),
    )
    price_type = store.upsert_price_type(
        PriceType(
            organization_id=organization.id,
            source_external_id="price-type-001",
            code="retail",
            name="Retail",
            currency_code="UZS",
            status="active",
        ),
    )
    store.upsert_product_price(
        ProductPrice(
            organization_id=organization.id,
            source_external_id="price-point-001",
            product_id=product.id,
            product_external_id=product.source_external_id,
            price_type_id=price_type.id,
            price_type_code=price_type.code,
            price=Decimal("151500"),
            currency_code="UZS",
        ),
    )
    sale = store.upsert_sale_v2(
        Sale(
            organization_id=organization.id,
            source_external_id="268805991",
            sale_number="268805991",
            customer_id=customer.id,
            customer_external_id=customer.source_external_id,
            amount=Decimal("606000"),
            currency="UZS",
            status="won",
            sale_at=datetime(2026, 8, 10, tzinfo=UTC),
        ),
    )
    store.upsert_sale_item(
        SaleItem(
            organization_id=organization.id,
            source_external_id="268805991:1",
            sale_id=sale.id,
            sale_external_id=sale.source_external_id,
            product_id=product.id,
            product_external_id=product.source_external_id,
            quantity=Decimal("4"),
            unit_price=Decimal("151500"),
            amount=Decimal("606000"),
            currency="UZS",
        ),
    )
    payment = store.upsert_payment(
        Payment(
            organization_id=organization.id,
            source_external_id="pay-001",
            sale_id=sale.id,
            sale_external_id=sale.source_external_id,
            amount=Decimal("606000"),
            currency="UZS",
            paid_at=datetime(2026, 8, 10, tzinfo=UTC),
            method="cash",
        ),
    )
    visit = store.upsert_visit(
        Visit(
            organization_id=organization.id,
            source_external_id="visit-001",
            customer_id=customer.id,
            customer_external_id=customer.source_external_id,
            visited_at=datetime(2026, 8, 10, tzinfo=UTC),
            status="completed",
        ),
    )
    inventory = store.upsert_inventory_balance(
        InventoryBalance(
            organization_id=organization.id,
            source_external_id="inv-001",
            warehouse_id=warehouse.id,
            product_id=product.id,
            warehouse_external_id=warehouse.source_external_id,
            product_external_id=product.source_external_id,
            quantity=Decimal("12"),
            balance_at=datetime(2026, 8, 10, tzinfo=UTC),
        ),
    )
    document = store.upsert_business_document(
        BusinessDocument(
            organization_id=organization.id,
            source_external_id="ret-001",
            document_type="return",
            document_number="RET-001",
            status="completed",
            document_at=datetime(2026, 8, 9, tzinfo=UTC),
            counterparty_external_id=customer.source_external_id,
            warehouse_external_id=warehouse.source_external_id,
            product_external_id=product.source_external_id,
            quantity=Decimal("1"),
            amount=Decimal("151500"),
            currency="UZS",
        ),
    )
    store.upsert_business_document_item(
        BusinessDocumentItem(
            organization_id=organization.id,
            source_external_id="ret-001:1",
            document_id=document.id,
            line_number=1,
            product_external_id=product.source_external_id,
            warehouse_external_id=warehouse.source_external_id,
            counterparty_external_id=customer.source_external_id,
            quantity=Decimal("1"),
            unit_price=Decimal("151500"),
            amount=Decimal("151500"),
            currency="UZS",
        ),
    )
    store.upsert_bank_operation(
        BankOperation(
            organization_id=organization.id,
            source_external_id="bank-001",
            amount=Decimal("606000"),
            currency="UZS",
            occurred_at=datetime(2026, 8, 10, tzinfo=UTC),
            operation_type="bank",
            description="Bank settlement",
        ),
    )
    store.upsert_bank_operation(
        BankOperation(
            organization_id=organization.id,
            source_external_id="cash-001",
            amount=Decimal("606000"),
            currency="UZS",
            occurred_at=datetime(2026, 8, 10, tzinfo=UTC),
            operation_type="cash",
            description="Cash receipt",
        ),
    )

    raw_sale_payload = {
        "deal_id": "268805991",
        "total_amount": "606000",
        "currency_code": "UZS",
        "status": "A",
        "order_products": [
            {
                "product_code": "prod-001",
                "order_quant": "4",
                "product_price": "151500",
                "sold_amount": "606000",
                "details": [{"sold_quant": "4"}],
            },
        ],
    }
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization.id,
            filial_id=organization.filial_id,
            entity_type="sales",
            external_id="268805991",
            source_endpoint="/b/trade/txs/tdeal/order$export",
            request_payload={"begin_deal_date": "01.08.2026", "end_deal_date": "02.08.2026"},
            response_payload=raw_sale_payload,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization.id,
            filial_id=organization.filial_id,
            entity_type="customers",
            external_id=customer.source_external_id,
            source_endpoint="/b/anor/mxsx/mr/legal_person$export",
            request_payload={},
            response_payload={"person_code": customer.source_external_id, "name": customer.name},
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization.id,
            filial_id=organization.filial_id,
            entity_type="visits",
            external_id=visit.source_external_id,
            source_endpoint="/b/trade/txs/tvt/visit$export",
            request_payload={},
            response_payload={
                "visit_id": visit.source_external_id,
                "person_id": customer.source_external_id,
            },
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization.id,
            filial_id=organization.filial_id,
            entity_type="products",
            external_id=product.source_external_id,
            source_endpoint="/b/anor/mxsx/mkw/inventory$export",
            request_payload={},
            response_payload={"product_code": product.source_external_id, "name": product.name},
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization.id,
            filial_id=organization.filial_id,
            entity_type="payments",
            external_id=payment.source_external_id,
            source_endpoint="/b/trade/txs/tcs/cashin$export",
            request_payload={},
            response_payload={
                "payment_id": payment.source_external_id,
                "sale_id": sale.source_external_id,
            },
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization.id,
            filial_id=organization.filial_id,
            entity_type="inventory_balances",
            external_id=inventory.source_external_id,
            source_endpoint="/b/anor/mxsx/mkw/balance$export",
            request_payload={},
            response_payload={
                "warehouse_code": warehouse.source_external_id,
                "product_code": product.source_external_id,
            },
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization.id,
            filial_id=organization.filial_id,
            entity_type="returns",
            external_id=document.source_external_id,
            source_endpoint="/b/anor/mxsx/mdeal/return$export",
            request_payload={},
            response_payload={
                "return_id": document.source_external_id,
                "deal_id": sale.source_external_id,
            },
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization.id,
            filial_id=organization.filial_id,
            entity_type="bank_operations",
            external_id="bank-001",
            source_endpoint="/b/anor/mxsx/mkcs/bank_operation$export",
            request_payload={},
            response_payload={"operation_id": "bank-001"},
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization.id,
            filial_id=organization.filial_id,
            entity_type="cash_operations",
            external_id="cash-001",
            source_endpoint="/b/anor/mxsx/mkcs/cash_operation$export",
            request_payload={},
            response_payload={"operation_id": "cash-001"},
        ),
    )

    store.upsert_migration_batch(
        MigrationBatch(
            organization_id=organization.id,
            filial_id=organization.filial_id,
            entity_type="cash_operations",
            endpoint="/b/anor/mxsx/mkcs/cash_operation$export",
            date_from=datetime(2026, 8, 1, tzinfo=UTC),
            date_to=datetime(2026, 8, 10, tzinfo=UTC),
            status=SmartUpMigrationStatus.PERMISSION_DENIED,
            upstream_status=403,
            upstream_response="Forbidden",
        ),
    )
    store.upsert_normalization_issue(
        NormalizationIssue(
            raw_record_id=next(iter(store.list_smartup_raw_records())).id,
            organization_id=organization.id,
            entity_type="sales",
            issue_type="quantity_mapping",
            field_name="quantity",
            message="Mapped from sold_quant",
            source_value={"sold_quant": "4"},
            severity=NormalizationIssueSeverity.INFO,
        ),
    )
    return store, organization


def _client_for_store(store: InMemoryCoreDataLayer, monkeypatch) -> TestClient:  # noqa: ANN001
    monkeypatch.setattr("app.main.get_core_store", lambda: store)
    app.dependency_overrides[get_core_store] = lambda: store
    return TestClient(app)


def test_data_coverage_and_mirror_overview_report_linked_entities(monkeypatch) -> None:
    store, organization = _seed_store()
    client = _client_for_store(store, monkeypatch)

    response = client.get(
        "/api/v1/data/coverage",
        params={"organization_id": str(organization.id)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["organization_name"] == "MODAILY"
    assert payload["raw_total"] > 0
    assert payload["core_total"] > 0
    assert payload["permission_restricted"] == 1
    assert payload["unresolved_references"] >= 1

    entities = {item["entity"]: item for item in payload["entities"]}
    assert entities["customers"]["raw"] == 1
    assert entities["customers"]["core"] == 1
    assert entities["customers"]["linked"] == 1
    assert entities["sales"]["core"] == 1
    assert entities["sales"]["linked"] == 1
    assert entities["sale_items"]["linked"] == 1
    assert entities["visits"]["linked"] == 1
    assert entities["inventory"]["linked"] == 1
    assert entities["price_types"]["linked"] == 1
    assert entities["price_points"]["linked"] == 1
    assert entities["cash_operations"]["status"] == "permission_denied"
    assert entities["bank_operations"]["linked"] == 1
    assert entities["business_documents"]["linked"] == 1

    mirror_response = client.get(
        "/api/v1/smartup/coverage",
        params={"organization_id": str(organization.id)},
    )
    assert mirror_response.status_code == 200
    mirror_payload = mirror_response.json()
    assert mirror_payload["organization_name"] == "MODAILY"
    assert mirror_payload["entities"][3]["entity"] == "sales"
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("entity", "entity_id"),
    [
        ("sale", "268805991"),
        ("customer", "cust-001"),
        ("visit", "visit-001"),
        ("product", "prod-001"),
        ("payment", "pay-001"),
    ],
)
def test_data_trace_endpoint_returns_real_chain(monkeypatch, entity: str, entity_id: str) -> None:
    store, _organization = _seed_store()
    client = _client_for_store(store, monkeypatch)

    try:
        response = client.get(f"/api/v1/data/trace/{entity}/{entity_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity"]
    assert payload["raw_summary"]
    assert payload["organization_name"] == "MODAILY"
    assert payload["source_mapping"]["normalized_id"]

    if entity == "sale":
        assert payload["raw_summary"]["total_amount_raw"] == "606000"
        assert payload["raw_summary"]["order_products_count"] == 1
        assert payload["normalized_entity"]["amount"] == "606000"
        kinds = {item["kind"] for item in payload["related_entities"]}
        assert {"customer", "sale_item", "payment", "raw_record"} <= kinds
    elif entity == "customer":
        kinds = {item["kind"] for item in payload["related_entities"]}
        assert {"sale", "visit", "return", "raw_record"} <= kinds
    elif entity == "visit":
        kinds = {item["kind"] for item in payload["related_entities"]}
        assert {"customer", "visit", "raw_record"} <= kinds
    elif entity == "product":
        kinds = {item["kind"] for item in payload["related_entities"]}
        assert {"product", "price_point", "inventory_balance", "sale_item", "raw_record"} <= kinds
    elif entity == "payment":
        kinds = {item["kind"] for item in payload["related_entities"]}
        assert {"sale", "customer", "payment", "raw_record"} <= kinds


def test_smartup_orders_page_is_dense_and_scrolled_list(monkeypatch) -> None:
    store, organization = _seed_store()
    client = _client_for_store(store, monkeypatch)

    try:
        response = client.get(
            "/api/v1/smartup/orders",
            params={"organization_id": str(organization.id), "page_size": 10},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset"] == "orders"
    assert payload["total"] == 1
    assert payload["items"][0]["deal_id"] == "268805991"
    assert payload["items"][0]["items_count"] == 1
    assert payload["items"][0]["amount"] == "606000"
