"""Tests for Canonical Data Layer V2 foundation backfill."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from app.core.data_layer.migrations import SmartUpCanonicalV2FoundationService
from app.core.data_layer.canonical_v2 import CanonicalDataQualityStatus
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.integrations.smartup.models import (
    SMARTUP_INTEGRATION_UUID,
    SmartUpOrganization,
    SmartUpRawRecord,
)


def _seed_canonical_v2_store() -> tuple[InMemoryCoreDataLayer, SmartUpOrganization]:
    store = InMemoryCoreDataLayer()
    organization = store.upsert_smartup_organization(
        SmartUpOrganization(
            id=UUID("11111111-1111-1111-1111-111111111111"),
            integration_id=SMARTUP_INTEGRATION_UUID,
            name="MODAILY",
            company_id="11300",
            filial_id="16114091",
            filial_code="MODAILY-FILIAL",
            project_code="trade",
            is_active=True,
        ),
    )

    base_context = {
        "organization_id": organization.id,
        "filial_id": organization.filial_id,
        "request_filial_id": organization.filial_id,
        "request_company_id": organization.company_id,
        "request_project_code": organization.project_code,
        "response_filial_id": organization.filial_id,
        "source_created_at": datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
        "source_updated_at": datetime(2026, 8, 10, 8, 30, tzinfo=UTC),
    }

    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="product_categories",
            external_id="PG-1",
            source_endpoint="https://smartup.online/b/trade/mxsx/mpr/person_group$export",
            response_payload={
                "person_group": [
                    {
                        "person_group_id": "PG-1",
                        "code": "PG-1",
                        "name": "Retail customers",
                        "person_kind": "client",
                        "state": "A",
                        "person_group_types": [{"code": "client"}],
                    }
                ]
            },
            **base_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="customers",
            external_id="CUST-1",
            source_endpoint="https://smartup.online/b/trade/mxsx/mpr/legal_person$export",
            response_payload={
                "legal_person": [
                    {
                        "person_id": "CUST-1",
                        "code": "CUST-1",
                        "name": "Acme Shop",
                        "short_name": "Acme",
                        "main_phone": "+998901234567",
                        "email": "acme@example.com",
                        "address": "Tashkent",
                        "groups": [{"code": "PG-1"}],
                        "state": "A",
                        "person_kind": "legal",
                        "tin": "123456789",
                    }
                ]
            },
            **base_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="product_categories",
            external_id="CAT-1",
            source_endpoint="https://smartup.online/b/trade/mxsx/mkw/product_group$export",
            response_payload={
                "product_group": [
                    {
                        "product_group_id": "CAT-1",
                        "code": "CAT-1",
                        "name": "Beverages",
                        "product_kind": "inventory",
                        "state": "A",
                        "group_types": [{"code": "inventory"}],
                    }
                ]
            },
            **base_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="products",
            external_id="PROD-1",
            source_endpoint="https://smartup.online/b/trade/txs/tinv/inventory$export",
            response_payload={
                "inventory": [
                    {
                        "product_id": "PROD-1",
                        "inventory_code": "PROD-1",
                        "code": "PROD-1",
                        "name": "Water 1L",
                        "short_name": "Water",
                        "measure_code": "pcs",
                        "article_code": "ART-1",
                        "producer_code": "PR-1",
                        "barcodes": ["1234567890123"],
                        "inventory_kinds": [{"kind": "inventory"}],
                        "groups": [{"code": "CAT-1"}],
                        "state": "A",
                        "gtin": "gtin-1",
                        "box_quant": "12",
                        "box_type_code": "box",
                        "litr": "1",
                        "marking_group_code": "mg-1",
                        "sector_codes": [{"code": "sector-1"}],
                        "tnved": "2201",
                        "weight_brutto": "1.2",
                        "weight_netto": "1.0",
                    }
                ]
            },
            **base_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="price_types",
            external_id="PRICE-1",
            source_endpoint="https://smartup.online/b/trade/mxsx/mpr/price_type$export",
            response_payload={
                "price_type": [
                    {
                        "price_type_id": "PRICE-1",
                        "code": "PRICE-1",
                        "name": "Default price",
                        "short_name": "Default",
                        "currency_code": "860",
                        "price_type_kind": "retail",
                        "with_card": "N",
                        "state": "A",
                    }
                ]
            },
            **base_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="price_points",
            external_id="PROD-1:PRICE-1",
            source_endpoint="https://smartup.online/b/trade/mxsx/mpr/price_point$export",
            response_payload={
                "inventory_code": "PROD-1",
                "inventory_barcode": "1234567890123",
                "currency_code": "860",
                "state": "A",
                "price_type": [
                    {
                        "price_type_code": "PRICE-1",
                        "card_code": "CARD-1",
                        "price": "151500",
                    }
                ],
            },
            **base_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="sales",
            external_id="SALE-1",
            source_endpoint="https://smartup.online/b/trade/txs/tdeal/order$export",
            response_payload={
                "deal_id": "SALE-1",
                "external_id": "SALE-1",
                "person_id": "CUST-1",
                "person_name": "Acme Shop",
                "room_id": "WH-1",
                "room_code": "WH-1",
                "room_name": "Main Warehouse",
                "sales_manager_id": "REP-1",
                "sales_manager_code": "REP-1",
                "sales_manager_name": "Alice Agent",
                "total_amount": "606000",
                "currency_code": "860",
                "status": "B#N",
                "deal_time": "2026-08-10 10:15:00",
                "delivery_date": "10.08.2026",
                "order_products": [
                    {
                        "product_code": "PROD-1",
                        "product_name": "Water 1L",
                        "order_quant": "4",
                        "sold_amount": "606000",
                        "product_price": "151500",
                        "details": [{"sold_quant": "4"}],
                    }
                ],
            },
            **base_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="visits",
            external_id="VISIT-1",
            source_endpoint="https://smartup.online/b/trade/txs/tvt/visit$export",
            response_payload={
                "visit_headers": [
                    {
                        "visit_id": "VISIT-1",
                        "person_id": "CUST-1",
                        "person_code": "CUST-1",
                        "person_name": "Acme Shop",
                        "room_id": "WH-2",
                        "room_code": "WH-2",
                        "room_name": "South Outlet",
                        "sales_manager_id": "REP-1",
                        "sales_manager_code": "REP-1",
                        "sales_manager_name": "Alice Agent",
                        "visit_status": "C",
                        "visit_date": "10.08.2026",
                        "visit_start_time": "2026-08-10 09:00:00",
                        "visit_end_time": "2026-08-10 09:15:00",
                        "visit_start_location": "41.2426277,69.1641819",
                        "visit_end_location": "41.24261,69.1648853",
                        "time_at_retail_outlet_sec": "900",
                        "spent_time": "900",
                        "is_planned": "Y",
                        "person_types": [{"code": "retail"}],
                        "supervisor_id": "",
                    }
                ],
                "quizzes": [{"quiz_sets": []}],
                "stocks": [],
                "comments": [],
                "equipments": [],
                "merchandisings": [],
                "note": "Shelf checked",
            },
            **base_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="payments",
            external_id="PAY-1",
            source_endpoint="https://smartup.online/b/trade/txs/tcs/cashin$export",
            response_payload={
                "cashin_id": "PAY-1",
                "cashin_number": "0001",
                "cashin_date": "10.08.2026",
                "cashin_time": "10.08.2026 12:00:00",
                "client_id": "CUST-1",
                "client_code": "CUST-1",
                "client_name": "Acme Shop",
                "amount": "606000",
                "currency_code": "860",
                "payment_type_code": "PYMT:1",
                "posted": "Y",
                "purpose": "Order payment",
                "cashbox_code": "CASH-1",
            },
            **base_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="returns",
            external_id="RET-1",
            source_endpoint="https://smartup.online/b/anor/mxsx/mdeal/return$export",
            response_payload={
                "deal_id": "RET-1",
                "external_id": "RET-1",
                "order_deal_id": "SALE-1",
                "person_id": "CUST-1",
                "person_code": "CUST-1",
                "person_name": "Acme Shop",
                "status": "A",
                "deal_time": "10.08.2026 13:00:00",
                "booked_date": "10.08.2026",
                "delivery_date": "10.08.2026",
                "total_amount": "-151500",
                "currency_code": "860",
                "return_reason_id": "14861",
                "return_reason_code": "DEFECT",
                "sales_manager_code": "REP-1",
                "return_products": [
                    {
                        "product_code": "PROD-1",
                        "product_name": "Water 1L",
                        "return_quant": "1",
                        "product_price": "151500",
                        "sold_amount": "-151500",
                        "warehouse_code": "WH-1",
                        "price_type_code": "PRICE-1",
                    }
                ],
            },
            **base_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="inventory_balances",
            external_id="BAL-1",
            source_endpoint="https://smartup.online/b/anor/mxsx/mkw/balance$export",
            response_payload={
                "warehouse_id": "WH-1",
                "warehouse_code": "WH-1",
                "warehouse_name": "Main Warehouse",
                "product_code": "PROD-1",
                "product_name": "Water 1L",
                "quantity": "18",
                "currency_code": "860",
                "date": "10.08.2026",
            },
            **base_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="sales",
            external_id="SALE-foreign",
            source_endpoint="https://smartup.online/b/trade/txs/tdeal/order$export",
            request_filial_id=organization.filial_id,
            request_company_id=organization.company_id,
            request_project_code=organization.project_code,
            response_filial_id="19330532",
            response_payload={
                "deal_id": "SALE-foreign",
                "external_id": "SALE-foreign",
                "person_id": "CUST-X",
                "person_name": "Foreign response",
                "total_amount": "100",
                "currency_code": "860",
                "status": "B#N",
                "order_products": [],
            },
            organization_id=organization.id,
            filial_id=organization.filial_id,
            source_created_at=datetime(2026, 8, 10, 9, 0, tzinfo=UTC),
            source_updated_at=datetime(2026, 8, 10, 9, 0, tzinfo=UTC),
        ),
    )

    return store, organization


def test_canonical_v2_foundation_populates_dimensions_and_excludes_unsafe_rows() -> None:
    store, organization = _seed_canonical_v2_store()

    report = SmartUpCanonicalV2FoundationService(store).backfill_phase1()
    tables = report.table_map()

    assert report.organization_scope == "MODAILY"
    assert tables["canonical_organizations"].canonical_count == 1
    assert tables["canonical_customer_groups"].canonical_count == 1
    assert tables["canonical_customers"].canonical_count == 1
    assert tables["canonical_product_categories"].canonical_count == 1
    assert tables["canonical_products"].canonical_count == 1
    assert tables["canonical_warehouses"].canonical_count == 1
    assert tables["canonical_price_types"].canonical_count == 1
    assert tables["canonical_product_prices"].canonical_count == 1
    assert tables["canonical_sales_reps"].canonical_count == 1
    assert tables["canonical_working_zones"].canonical_count == 2

    canonical_customers = list(store.list_canonical_customers(organization_id=organization.id))
    canonical_products = list(store.list_canonical_products(organization_id=organization.id))
    canonical_prices = list(store.list_canonical_product_prices(organization_id=organization.id))
    canonical_reps = list(store.list_canonical_sales_reps(organization_id=organization.id))
    canonical_zones = list(store.list_canonical_working_zones(organization_id=organization.id))
    canonical_warehouses = list(store.list_canonical_warehouses(organization_id=organization.id))

    assert len(canonical_customers) == 1
    assert len(canonical_products) == 1
    assert len(canonical_prices) == 1
    assert len(canonical_reps) == 1
    assert len(canonical_zones) == 2
    assert len(canonical_warehouses) == 1

    price = canonical_prices[0]
    assert price.price == Decimal("151500")
    assert price.currency_code == "860"

    product = canonical_products[0]
    assert product.name == "Water 1L"
    assert product.source_kind == "inventory"

    warehouse_names = {warehouse.warehouse_name for warehouse in canonical_warehouses}
    assert "Main Warehouse" in warehouse_names

def test_canonical_v2_foundation_is_idempotent() -> None:
    store, _organization = _seed_canonical_v2_store()
    service = SmartUpCanonicalV2FoundationService(store)

    first = service.backfill_phase1()
    second = service.backfill_phase1()

    assert first.table_map()["canonical_products"].canonical_count == second.table_map()[
        "canonical_products"
    ].canonical_count
    assert len(list(store.list_canonical_products())) == 1
    assert len(list(store.list_canonical_product_prices())) == 1


def test_canonical_v2_discovers_customers_from_sales_references() -> None:
    store = InMemoryCoreDataLayer()
    organization = store.upsert_smartup_organization(
        SmartUpOrganization(
            id=UUID("22222222-2222-2222-2222-222222222222"),
            integration_id=SMARTUP_INTEGRATION_UUID,
            name="ADMIN",
            company_id="11300",
            filial_id="14475622",
            project_code="trade",
            is_active=True,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="sales",
            external_id="SALE-2",
            source_endpoint="https://smartup.online/b/trade/txs/tdeal/order$export",
            response_payload={
                "deal_id": "SALE-2",
                "external_id": "SALE-2",
                "person_id": "CUST-2",
                "person_name": "Referenced Customer",
                "total_amount": "100",
                "currency_code": "860",
                "status": "B#N",
                "order_products": [],
            },
            organization_id=organization.id,
            filial_id=organization.filial_id,
            request_filial_id=organization.filial_id,
            request_company_id=organization.company_id,
            request_project_code=organization.project_code,
            response_filial_id=organization.filial_id,
            source_created_at=datetime(2026, 8, 10, 9, 0, tzinfo=UTC),
            source_updated_at=datetime(2026, 8, 10, 9, 0, tzinfo=UTC),
        ),
    )

    report = SmartUpCanonicalV2FoundationService(store).backfill_phase1()
    assert report.table_map()["canonical_customers"].canonical_count == 1
    customer = list(store.list_canonical_customers(organization_id=organization.id))[0]
    assert customer.source_external_id == "CUST-2"
    assert customer.metadata["customer_source_kind"] == "sale"


def test_canonical_v2_phase2_materializes_orders_sales_and_sale_items() -> None:
    store, organization = _seed_canonical_v2_store()
    service = SmartUpCanonicalV2FoundationService(store)

    service.backfill_phase1()
    report = service.backfill_phase2_sales()
    tables = report.table_map()

    assert tables["canonical_orders"].canonical_count == 1
    assert tables["canonical_sales"].canonical_count == 1
    assert tables["canonical_sale_items"].canonical_count == 1

    order = list(store.list_canonical_orders(organization_id=organization.id))[0]
    sale = list(store.list_canonical_sales(organization_id=organization.id))[0]
    sale_item = list(store.list_canonical_sale_items(organization_id=organization.id))[0]

    assert order.total_amount == Decimal("606000")
    assert order.currency_code == "UZS"
    assert order.ordered_quantity == Decimal("4")
    assert order.sold_quantity == Decimal("4")
    assert order.has_realization_evidence is True
    assert order.customer_external_id == "CUST-1"
    assert order.order_at == datetime(2026, 8, 10, 10, 15, 0, tzinfo=UTC)
    assert order.delivery_date == datetime(2026, 8, 10, 0, 0, 0, tzinfo=UTC)

    assert sale.total_amount == Decimal("606000")
    assert sale.currency_code == "UZS"
    assert sale.ordered_quantity == Decimal("4")
    assert sale.sold_quantity == Decimal("4")
    assert sale.realization_basis == "sold_quant"
    assert sale.order_id == order.id
    assert sale.sale_at == datetime(2026, 8, 10, 10, 15, 0, tzinfo=UTC)
    assert sale.closed_at == datetime(2026, 8, 10, 0, 0, 0, tzinfo=UTC)

    assert sale_item.sale_id == sale.id
    assert sale_item.order_id == order.id
    assert sale_item.product_code == "PROD-1"
    assert sale_item.ordered_quantity == Decimal("4")
    assert sale_item.sold_quantity == Decimal("4")
    assert sale_item.unit_price == Decimal("151500")
    assert sale_item.amount == Decimal("606000")
    assert sale_item.currency_code == "UZS"

    second = service.backfill_phase2_sales()
    assert second.table_map()["canonical_sale_items"].canonical_count == 1
    assert len(list(store.list_canonical_orders(organization_id=organization.id))) == 1
    assert len(list(store.list_canonical_sales(organization_id=organization.id))) == 1
    assert len(list(store.list_canonical_sale_items(organization_id=organization.id))) == 1


def test_canonical_v2_phase2b_materializes_payments_and_customer_returns() -> None:
    store, organization = _seed_canonical_v2_store()
    service = SmartUpCanonicalV2FoundationService(store)

    service.backfill_phase1()
    service.backfill_phase2_sales()
    report = service.backfill_phase2_payments_returns()
    tables = report.table_map()

    assert tables["canonical_payments"].canonical_count == 1
    assert tables["canonical_payment_allocations"].canonical_count == 0
    assert tables["canonical_customer_returns"].canonical_count == 1
    assert tables["canonical_customer_return_items"].canonical_count == 1

    payment = list(store.list_canonical_payments(organization_id=organization.id))[0]
    customer_return = list(store.list_canonical_customer_returns(organization_id=organization.id))[0]
    return_item = list(store.list_canonical_customer_return_items(organization_id=organization.id))[0]
    sale = list(store.list_canonical_sales(organization_id=organization.id))[0]

    assert payment.customer_external_id == "CUST-1"
    assert payment.customer_id is not None
    assert payment.amount == Decimal("606000")
    assert payment.currency_code == "UZS"
    assert payment.normalized_payment_type == "unknown"
    assert payment.paid_at == datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC)

    assert customer_return.customer_external_id == "CUST-1"
    assert customer_return.customer_id is not None
    assert customer_return.linked_order_external_id == "SALE-1"
    assert customer_return.linked_order_id is not None
    assert customer_return.linked_sale_id == sale.id
    assert customer_return.total_amount == Decimal("-151500")
    assert customer_return.returned_quantity == Decimal("1")
    assert customer_return.return_at == datetime(2026, 8, 10, 13, 0, 0, tzinfo=UTC)
    assert customer_return.booked_at == datetime(2026, 8, 10, 0, 0, 0, tzinfo=UTC)
    assert customer_return.delivery_date == datetime(2026, 8, 10, 0, 0, 0, tzinfo=UTC)

    assert return_item.customer_return_id == customer_return.id
    assert return_item.product_code == "PROD-1"
    assert return_item.product_id is not None
    assert return_item.returned_quantity == Decimal("1")
    assert return_item.unit_price == Decimal("151500")
    assert return_item.amount == Decimal("-151500")
    assert return_item.linked_sale_id == sale.id

    second = service.backfill_phase2_payments_returns()
    assert second.table_map()["canonical_payments"].canonical_count == 1
    assert second.table_map()["canonical_customer_returns"].canonical_count == 1
    assert len(list(store.list_canonical_payments(organization_id=organization.id))) == 1
    assert len(list(store.list_canonical_customer_returns(organization_id=organization.id))) == 1
    assert len(list(store.list_canonical_customer_return_items(organization_id=organization.id))) == 1


def test_canonical_v2_phase2e_materializes_financial_operations_without_duplicates() -> None:
    store, organization = _seed_canonical_v2_store()
    service = SmartUpCanonicalV2FoundationService(store)

    base_context = {
        "organization_id": organization.id,
        "filial_id": organization.filial_id,
        "request_filial_id": organization.filial_id,
        "request_company_id": organization.company_id,
        "request_project_code": organization.project_code,
        "response_filial_id": organization.filial_id,
        "source_created_at": datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
        "source_updated_at": datetime(2026, 8, 10, 8, 30, tzinfo=UTC),
    }

    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="bank_operations",
            external_id="CASHOP-1",
            source_endpoint="https://smartup.online/b/anor/mxsx/mkcs/cash_operation$export",
            response_payload={
                "operation_id": "96359183",
                "operation_number": "0000000456",
                "operation_date": "10.08.2026",
                "amount": "606000",
                "currency_code": "860",
                "cashflow_kind": "I",
                "corr_person_code": "CUST-1",
                "corr_coa_code": "6310",
                "ref_codes": [
                    {"ref_type": "1010", "ref_id": "CUST-1"},
                    {"ref_type": "1012", "ref_id": "13545"},
                ],
                "note": "payment reflected in cash operation",
                "posted": "Y",
            },
            **base_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="bank_operations",
            external_id="BANK-empty",
            source_endpoint="https://smartup.online/b/anor/mxsx/mkcs/bank_operation$export",
            response_payload={"bank_operation": [], "limits": {"has_limit": "Y"}},
            **base_context,
        ),
    )

    service.backfill_phase1()
    service.backfill_phase2_payments_returns()
    report = service.backfill_phase2_finance()
    tables = report.table_map()

    assert tables["canonical_financial_accounts"].canonical_count >= 1
    assert tables["canonical_financial_operations"].canonical_count == 2

    operations = list(store.list_canonical_financial_operations(organization_id=organization.id))
    payment_operation = next(item for item in operations if item.source_document_type == "cashin")
    cash_operation = next(item for item in operations if item.source_document_type == "cash_operation")

    assert payment_operation.direction.value == "INFLOW"
    assert payment_operation.amount == Decimal("606000")
    assert payment_operation.currency_code == "UZS"
    assert payment_operation.counterparty_external_id == "CUST-1"
    assert payment_operation.data_quality_status == CanonicalDataQualityStatus.VERIFIED

    assert cash_operation.direction.value == "INFLOW"
    assert cash_operation.amount == Decimal("606000")
    assert cash_operation.currency_code == "UZS"
    assert cash_operation.counterparty_external_id == "CUST-1"
    assert cash_operation.data_quality_status == CanonicalDataQualityStatus.PARTIAL
    assert cash_operation.metadata["overlaps_payment"] is True

    second = service.backfill_phase2_finance()
    assert second.table_map()["canonical_financial_operations"].canonical_count == 2
    assert len(list(store.list_canonical_financial_operations(organization_id=organization.id))) == 2


def test_canonical_v2_phase2c_materializes_inventory_and_warehouse_domains() -> None:
    store, organization = _seed_canonical_v2_store()
    service = SmartUpCanonicalV2FoundationService(store)

    base_context = {
        "organization_id": organization.id,
        "filial_id": organization.filial_id,
        "request_filial_id": organization.filial_id,
        "request_company_id": organization.company_id,
        "request_project_code": organization.project_code,
        "response_filial_id": organization.filial_id,
        "source_created_at": datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
        "source_updated_at": datetime(2026, 8, 10, 8, 30, tzinfo=UTC),
    }

    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="purchases",
            external_id="PUR-1",
            source_endpoint="https://smartup.online/b/anor/mxsx/mkw/purchase$export",
            response_payload={
                "purchase_id": "PUR-1",
                "purchase_number": "P-0001",
                "purchase_time": "10.08.2026",
                "warehouse_code": "WH-1",
                "supplier_code": "SUP-1",
                "currency_code": "860",
                "purchase_items": [
                    {
                        "purchase_item_id": "PUR-1-1",
                        "product_code": "PROD-1",
                        "quantity": "5",
                        "price": "100000",
                        "base_price": "95000",
                    }
                ],
            },
            **base_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="warehouse_receipts",
            external_id="REC-1",
            source_endpoint="https://smartup.online/b/anor/mxsx/mkw/input$export",
            response_payload={
                "input_id": "REC-1",
                "input_number": "IN-0001",
                "input_time": "10.08.2026",
                "warehouse_code": "WH-1",
                "supplier_codes": [{"supplier_code": "SUP-1"}],
                "input_items": [
                    {
                        "input_item_id": "REC-1-1",
                        "product_code": "PROD-1",
                        "quantity": "5",
                        "price": "100000",
                        "purchase_id": "PUR-1",
                        "purchase_item_id": "PUR-1-1",
                    }
                ],
            },
            **base_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="write_offs",
            external_id="WO-1",
            source_endpoint="https://smartup.online/b/anor/mxsx/mkw/writeoff$export",
            response_payload={
                "writeoff_id": "WO-1",
                "writeoff_number": "WO-0001",
                "writeoff_date": "10.08.2026",
                "warehouse_code": "WH-1",
                "currency_code": "860",
                "c_amount": "100000",
                "writeoff_items": [
                    {
                        "writeoff_item_id": "WO-1-1",
                        "product_code": "PROD-1",
                        "quantity": "1",
                    }
                ],
            },
            **base_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="cross_organizational_movements",
            external_id="XORG-1",
            source_endpoint="https://smartup.online/b/anor/mxsx/mfm/movement$export",
            response_payload={
                "movement_id": "XORG-1",
                "delivery_number": "MV-0001",
                "from_time": "10.08.2026",
                "from_filial_code": "ADMIN",
                "to_filial_code": "MODAILY",
                "from_warehouse_code": "WH-1",
                "to_warehouse_code": "WH-DEST",
                "currency_code": "860",
                "movement_items": [
                    {
                        "movement_unit_id": "XORG-1-1",
                        "product_code": "PROD-1",
                        "quantity": "2",
                        "price": "110000",
                    }
                ],
            },
            **base_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="return_to_suppliers",
            external_id="SUPRET-empty",
            source_endpoint="https://smartup.online/b/anor/mxsx/mkw/return$export",
            response_payload={"return": [], "limits": {"has_limit": "Y"}},
            **base_context,
        ),
    )

    service.backfill_phase1()
    report = service.backfill_phase2_inventory_warehouse()
    tables = report.table_map()

    assert tables["canonical_inventory_balances"].canonical_count == 1
    assert tables["canonical_purchases"].canonical_count == 1
    assert tables["canonical_purchase_items"].canonical_count == 1
    assert tables["canonical_warehouse_receipts"].canonical_count == 1
    assert tables["canonical_warehouse_receipt_items"].canonical_count == 1
    assert tables["canonical_writeoffs"].canonical_count == 1
    assert tables["canonical_writeoff_items"].canonical_count == 1
    assert tables["canonical_cross_org_movements"].canonical_count == 1
    assert tables["canonical_cross_org_movement_items"].canonical_count == 1
    assert tables["canonical_supplier_returns"].canonical_count == 0
    assert tables["canonical_stocktakings"].canonical_count == 0
    assert tables["canonical_internal_movements"].canonical_count == 0

    balance = list(store.list_canonical_inventory_balances(organization_id=organization.id))[0]
    purchase = list(store.list_canonical_purchases(organization_id=organization.id))[0]
    purchase_item = list(store.list_canonical_purchase_items(organization_id=organization.id))[0]
    receipt = list(store.list_canonical_warehouse_receipts(organization_id=organization.id))[0]
    writeoff = list(store.list_canonical_writeoffs(organization_id=organization.id))[0]
    cross_org = list(store.list_canonical_cross_org_movements(organization_id=organization.id))[0]
    cross_org_item = list(store.list_canonical_cross_org_movement_items(organization_id=organization.id))[0]

    assert balance.quantity == Decimal("18")
    assert purchase.total_quantity == Decimal("5")
    assert purchase.currency_code == "UZS"
    assert purchase_item.quantity == Decimal("5")
    assert purchase_item.unit_price == Decimal("100000")
    assert purchase_item.amount == Decimal("500000")
    assert receipt.total_quantity == Decimal("5")
    assert writeoff.total_amount == Decimal("100000")
    assert cross_org.source_filial_code == "ADMIN"
    assert cross_org.destination_filial_code == "MODAILY"


def test_canonical_v2_phase2d_materializes_visits_from_visit_headers() -> None:
    store, organization = _seed_canonical_v2_store()
    service = SmartUpCanonicalV2FoundationService(store)

    service.backfill_phase1()
    report = service.backfill_phase2_visits()
    tables = report.table_map()

    assert tables["canonical_visits"].canonical_count == 1
    assert tables["canonical_visit_stocks"].canonical_count == 0
    assert tables["canonical_visit_quiz_answers"].canonical_count == 0
    assert tables["canonical_visit_equipments"].canonical_count == 0
    assert tables["canonical_visit_comments"].canonical_count == 0
    assert tables["canonical_media_assets"].canonical_count == 0

    visit = list(store.list_canonical_visits(organization_id=organization.id))[0]
    assert visit.customer_external_id == "CUST-1"
    assert visit.customer_id is not None
    assert visit.sales_rep_external_id == "REP-1"
    assert visit.sales_rep_id is not None
    assert visit.working_zone_external_id == "WH-2"
    assert visit.working_zone_id is not None
    assert visit.normalized_status == "completed"
    assert visit.is_planned is True
    assert visit.visit_start_time == datetime(
        2026, 8, 10, 9, 0, tzinfo=ZoneInfo("Asia/Tashkent")
    )
    assert visit.visit_end_time == datetime(
        2026, 8, 10, 9, 15, tzinfo=ZoneInfo("Asia/Tashkent")
    )
    assert visit.visited_at == visit.visit_start_time
    assert visit.duration_seconds == 900
    assert visit.derived_duration_seconds == 900
    assert visit.note == "Shelf checked"
    assert visit.start_latitude == Decimal("41.2426277")
    assert visit.start_longitude == Decimal("69.1641819")
    assert visit.end_latitude == Decimal("41.24261")
    assert visit.end_longitude == Decimal("69.1648853")
    assert visit.person_types == [{"code": "retail"}]


def test_canonical_v2_phase2d_is_idempotent() -> None:
    store, organization = _seed_canonical_v2_store()
    service = SmartUpCanonicalV2FoundationService(store)

    service.backfill_phase1()
    first = service.backfill_phase2_visits()
    second = service.backfill_phase2_visits()

    assert first.table_map()["canonical_visits"].canonical_count == 1
    assert second.table_map()["canonical_visits"].canonical_count == 1
    assert len(list(store.list_canonical_visits(organization_id=organization.id))) == 1


def test_canonical_v2_parse_source_datetime_supports_real_smartup_formats() -> None:
    service = SmartUpCanonicalV2FoundationService(InMemoryCoreDataLayer())

    assert service._parse_source_datetime("05.08.2026 15:18:00") == datetime(
        2026, 8, 5, 15, 18, 0, tzinfo=UTC
    )
    assert service._parse_source_datetime("05.08.26 15:18:00") == datetime(
        2026, 8, 5, 15, 18, 0, tzinfo=UTC
    )
    assert service._parse_source_datetime("2026-08-05T15:18:00") == datetime(
        2026, 8, 5, 15, 18, 0, tzinfo=UTC
    )


def test_canonical_v2_visit_datetimes_preserve_business_local_wall_clock() -> None:
    service = SmartUpCanonicalV2FoundationService(InMemoryCoreDataLayer())
    tashkent = ZoneInfo("Asia/Tashkent")

    start = service._parse_visit_datetime("02.09.2026 21:25:43")
    end = service._parse_visit_datetime("02.09.2026 21:26:36")

    assert start == datetime(2026, 9, 2, 21, 25, 43, tzinfo=tashkent)
    assert end == datetime(2026, 9, 2, 21, 26, 36, tzinfo=tashkent)
    assert (end - start).total_seconds() == 53
    assert start.date() == datetime(2026, 9, 2).date()

    # Explicit timezone input already identifies an instant and must not be
    # reinterpreted as a naive Asia/Tashkent wall-clock value.
    assert service._parse_visit_datetime("2026-09-02T21:25:43+00:00") == datetime(
        2026, 9, 2, 21, 25, 43, tzinfo=UTC
    )
    assert service._parse_visit_datetime(datetime(2026, 9, 2, 21, 25, 43)) == start


def test_canonical_v2_visit_date_keeps_date_only_contract() -> None:
    service = SmartUpCanonicalV2FoundationService(InMemoryCoreDataLayer())

    # Date-only fields remain on the existing canonical date contract. The
    # local wall-clock fix applies only to event start/end timestamps.
    assert service._parse_source_datetime("02.09.2026") == datetime(
        2026, 9, 2, tzinfo=UTC
    )


def test_receipt_item_inherits_product_from_purchase_item_when_raw_has_no_product_identity() -> None:
    store = InMemoryCoreDataLayer()
    service = SmartUpCanonicalV2FoundationService(store)
    organization = SmartUpOrganization(
        id=uuid4(),
        integration_id=SMARTUP_INTEGRATION_UUID,
        name="Admin",
        company_id="11300",
        filial_id="14475622",
        project_code="trade",
        is_active=True,
    )
    store.upsert_smartup_organization(organization)
    imported_at = datetime(2026, 8, 12, tzinfo=UTC)
    raw_context = dict(
        organization_id=organization.id,
        filial_id=organization.filial_id,
        imported_at=imported_at,
        source_created_at=imported_at,
        source_updated_at=imported_at,
        request_company_id="11300",
        request_project_code="trade",
        request_filial_id="14475622",
        response_filial_id="14475622",
        batch_id=uuid4(),
    )

    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="products",
            external_id="935",
            source_endpoint="https://smartup.online/b/anor/mxsx/mr/inventory$export",
            response_payload={
                "product_id": "3992533",
                "code": "935",
                "name": "Balance Purifying Gel",
                "barcode": "5068245676935",
            },
            **raw_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="purchases",
            external_id="2340761",
            source_endpoint="https://smartup.online/b/anor/mxsx/mkw/purchase$export",
            response_payload={
                "purchase_id": "2340761",
                "purchase_number": "0000000015",
                "warehouse_code": "123",
                "currency_code": "860",
                "purchase_time": "05.08.2026 16:39:32",
                "purchase_items": [
                    {
                        "purchase_item_id": "91857982",
                        "product_code": "935",
                        "quantity": "1",
                        "price": "1000",
                    }
                ],
            },
            **raw_context,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=uuid4(),
            entity_type="warehouse_receipts",
            external_id="2218442",
            source_endpoint="https://smartup.online/b/anor/mxsx/mkw/input$export",
            response_payload={
                "input_id": "2218442",
                "input_number": "0000000015",
                "warehouse_code": "123",
                "input_time": "05.08.2026 16:39:32",
                "input_items": [
                    {
                        "input_item_id": "89031922",
                        "purchase_id": "2340761",
                        "purchase_item_id": "91857982",
                        "quantity": "1",
                        "price": "1000",
                    }
                ],
            },
            **raw_context,
        ),
    )

    service.backfill_phase1()
    service.backfill_phase2_inventory_warehouse()

    receipt_item = list(store.list_canonical_warehouse_receipt_items(organization_id=organization.id))[0]
    purchase_item = list(store.list_canonical_purchase_items(organization_id=organization.id))[0]

    assert purchase_item.product_id is not None
    assert receipt_item.purchase_item_external_id == "91857982"
    assert receipt_item.product_id == purchase_item.product_id


def test_inventory_phase_freezes_unresolved_source_limitations_without_fake_links() -> None:
    store = InMemoryCoreDataLayer()
    service = SmartUpCanonicalV2FoundationService(store)
    organization = SmartUpOrganization(
        id=uuid4(),
        integration_id=SMARTUP_INTEGRATION_UUID,
        name="Администрация",
        company_id="11300",
        filial_id="14475622",
        project_code="trade",
        is_active=True,
    )
    store.upsert_smartup_organization(organization)
    imported_at = datetime(2026, 8, 12, tzinfo=UTC)
    raw_context = dict(
        organization_id=organization.id,
        filial_id=organization.filial_id,
        imported_at=imported_at,
        source_created_at=imported_at,
        source_updated_at=imported_at,
        request_company_id="11300",
        request_project_code="trade",
        request_filial_id="14475622",
        response_filial_id="14475622",
        batch_id=uuid4(),
    )

    purchase_raw = SmartUpRawRecord(
        id=uuid4(),
        entity_type="purchases",
        external_id="PUR-UNRES-1",
        source_endpoint="https://smartup.online/b/anor/mxsx/mkw/purchase$export",
        response_payload={
            "purchase_id": "PUR-UNRES-1",
            "purchase_number": "00015",
            "purchase_time": "05.08.2026 16:39:32",
            "currency_code": "860",
            "total_amount": "1000",
            "purchase_items": [
                {
                    "purchase_item_id": "PUR-ITEM-1",
                    "quantity": "1",
                    "price": "1000",
                    "serial_number": "SN-1",
                    "inventory_kind": "E",
                },
            ],
        },
        **raw_context,
    )
    receipt_raw = SmartUpRawRecord(
        id=uuid4(),
        entity_type="warehouse_receipts",
        external_id="REC-UNRES-1",
        source_endpoint="https://smartup.online/b/anor/mxsx/mkw/input$export",
        response_payload={
            "input_id": "REC-UNRES-1",
            "input_number": "00015",
            "input_time": "05.08.2026 16:39:32",
            "input_items": [
                {
                    "input_item_id": "REC-ITEM-1",
                    "purchase_id": "PUR-UNRES-1",
                    "purchase_item_id": "PUR-ITEM-1",
                    "quantity": "1",
                    "price": "1000",
                    "serial_number": "SN-1",
                    "inventory_kind": "E",
                },
            ],
        },
        **raw_context,
    )
    store.upsert_smartup_raw_record(purchase_raw)
    store.upsert_smartup_raw_record(receipt_raw)

    report = service.backfill_phase2_inventory_warehouse()

    purchase = list(store.list_canonical_purchases(organization_id=organization.id))[0]
    purchase_item = list(store.list_canonical_purchase_items(organization_id=organization.id))[0]
    receipt = list(store.list_canonical_warehouse_receipts(organization_id=organization.id))[0]
    receipt_item = list(store.list_canonical_warehouse_receipt_items(organization_id=organization.id))[0]
    issues = list(store.list_normalization_issues(organization_id=organization.id))

    assert purchase.data_quality_status == CanonicalDataQualityStatus.PARTIAL
    assert purchase.warehouse_id is None
    assert purchase.metadata["unresolved_reason"] == "UNRESOLVED_SOURCE_REFERENCE"
    assert purchase_item.data_quality_status == CanonicalDataQualityStatus.UNRESOLVED
    assert purchase_item.product_id is None
    assert receipt.data_quality_status == CanonicalDataQualityStatus.PARTIAL
    assert receipt.warehouse_id is None
    assert receipt_item.data_quality_status == CanonicalDataQualityStatus.UNRESOLVED
    assert receipt_item.product_id is None
    assert receipt_item.metadata["unresolved_reason"] == "UNRESOLVED_SOURCE_REFERENCE"
    assert purchase_item.metadata["coverage"]["product_linkage_coverage"]["resolved"] == 0
    assert purchase.metadata["coverage"]["warehouse_linkage_coverage"]["resolved"] == 0
    assert any(issue.issue_type == "SMARTUP_SOURCE_IDENTIFIER_MISSING" and issue.entity_type == "purchases" for issue in issues)
    assert any(issue.issue_type == "SMARTUP_SOURCE_IDENTIFIER_MISSING" and issue.entity_type == "warehouse_receipts" for issue in issues)
    assert "product_linkage_coverage" in " ".join(report.table_map()["canonical_purchase_items"].notes)
