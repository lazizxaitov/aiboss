"""Tests for SmartUp core rebuild from stored raw records."""

from decimal import Decimal
from uuid import UUID, uuid4

from app.core.data_layer.service import InMemoryCoreDataLayer
from app.integrations.smartup.models import (
    SMARTUP_INTEGRATION_UUID,
    SmartUpOrganization,
    SmartUpRawRecord,
)
from app.integrations.smartup.rebuild import SmartUpCoreRebuildService


def _seed_smartup_rebuild_store() -> tuple[InMemoryCoreDataLayer, SmartUpOrganization]:
    store = InMemoryCoreDataLayer()
    organization = store.upsert_smartup_organization(
        SmartUpOrganization(
            id=UUID("11111111-1111-1111-1111-111111111111"),
            integration_id=SMARTUP_INTEGRATION_UUID,
            name="MODAILY",
            company_id="11300",
            filial_id="16114091",
            project_code="trade",
            is_active=True,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            organization_id=organization.id,
            filial_id=organization.filial_id,
            entity_type="products",
            external_id="P-1",
            source_endpoint="/b/trade/txs/tinv/inventory$export",
            response_payload={
                "product_id": "P-1",
                "code": "P-1",
                "name": "Product One",
                "measure_code": "pcs",
            },
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            organization_id=organization.id,
            filial_id=organization.filial_id,
            entity_type="sales",
            external_id="D-1",
            source_endpoint="/b/trade/txs/tdeal/order$export",
            response_payload={
                "deal_id": "D-1",
                "external_id": "D-1",
                "person_id": "CUST-1",
                "person_name": "Acme Shop",
                "room_id": "WH-1",
                "room_name": "Main Warehouse",
                "total_amount": "200",
                "currency_code": "860",
                "status": "B#N",
                "deal_time": "2026-08-03 10:15:00",
                "delivery_date": "03.08.2026",
                "order_products": [
                    {
                        "product_code": "P-1",
                        "product_name": "Product One",
                        "order_quant": "2",
                        "sold_amount": "200",
                        "product_price": "100",
                        "details": [{"sold_quant": "2"}],
                    },
                ],
            },
        ),
    )
    return store, organization


def test_smartup_core_rebuild_populates_core_from_raw_records() -> None:
    store, organization = _seed_smartup_rebuild_store()

    report = SmartUpCoreRebuildService(store).rebuild_all(force=True)

    assert report.organizations == 1
    assert report.raw_records >= 2
    assert report.after_core["customers"] == 1
    assert report.after_core["products"] == 1
    assert report.after_core["warehouses"] == 1
    assert report.after_core["sales"] == 1
    assert report.after_core["sale_items"] == 1

    customers = list(store.list_customers(organization_id=organization.id))
    products = list(store.list_products(organization_id=organization.id))
    warehouses = list(store.list_warehouses(organization_id=organization.id))
    sales = list(store.list_sales_v2(organization_id=organization.id))
    sale_items = list(store.list_sale_items(organization_id=organization.id))

    assert len(customers) == 1
    assert len(products) == 1
    assert len(warehouses) == 1
    assert len(sales) == 1
    assert len(sale_items) == 1

    sale = sales[0]
    sale_item = sale_items[0]
    assert sale.customer_id is not None
    assert sale.customer_external_id == "CUST-1"
    assert sale.amount == Decimal("200")
    assert sale.currency == "860"
    assert sale_item.sale_id == sale.id
    assert sale_item.product_id is not None
    assert sale_item.quantity == Decimal("2")
    assert sale_item.unit_price == Decimal("100")
    assert sale_item.amount == Decimal("200")


def test_smartup_core_rebuild_is_idempotent() -> None:
    store, _organization = _seed_smartup_rebuild_store()
    service = SmartUpCoreRebuildService(store)

    first = service.rebuild_all(force=True)
    second = service.rebuild_all(force=False)

    assert first.after_core == second.after_core
    assert second.inserted == 0
    assert second.updated == 0
