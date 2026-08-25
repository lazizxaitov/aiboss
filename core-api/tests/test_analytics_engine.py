"""Tests for Canonical V2 analytics engine and API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.data_layer.canonical_v2 import (
    CanonicalCrossOrgMovement,
    CanonicalCustomer,
    CanonicalCustomerReturn,
    CanonicalCustomerReturnItem,
    CanonicalDataQualityStatus,
    CanonicalFinancialDirection,
    CanonicalFinancialOperation,
    CanonicalInternalMovement,
    CanonicalInventoryBalance,
    CanonicalOrder,
    CanonicalOrganization,
    CanonicalPayment,
    CanonicalPaymentAllocation,
    CanonicalProduct,
    CanonicalProductCategory,
    CanonicalPurchase,
    CanonicalSale,
    CanonicalSaleItem,
    CanonicalSalesRep,
    CanonicalStocktaking,
    CanonicalSupplierReturn,
    CanonicalVisit,
    CanonicalWarehouse,
    CanonicalWarehouseReceipt,
    CanonicalWorkingZone,
    CanonicalWriteoff,
    canonical_row_uuid,
)
from app.core.data_layer.factory import get_core_store
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.main import app


def _metric_value(payload: dict, *path: str) -> Decimal:
    value: object = payload
    for key in path:
        assert isinstance(value, dict)
        value = value[key]
    return Decimal(str(value))


def _seed_analytics_store() -> tuple[
    InMemoryCoreDataLayer,
    CanonicalOrganization,
    CanonicalOrganization,
]:
    store = InMemoryCoreDataLayer()
    now = datetime.now(UTC)

    org_one = store.upsert_canonical_organization(
        CanonicalOrganization(
            organization_id=canonical_row_uuid("org", "alpha"),
            name="Alpha LLC",
            company_id="11300",
            filial_id="14475622",
            filial_code="ALPHA",
            project_code="trade",
            source_external_id="alpha",
            sort_order=1,
        )
    )
    org_two = store.upsert_canonical_organization(
        CanonicalOrganization(
            organization_id=canonical_row_uuid("org", "beta"),
            name="Beta LLC",
            company_id="11300",
            filial_id="16114091",
            filial_code="BETA",
            project_code="trade",
            source_external_id="beta",
            sort_order=2,
        )
    )

    category_a = store.upsert_canonical_product_category(
        CanonicalProductCategory(
            id=canonical_row_uuid("category", org_one.organization_id, "cat-a"),
            organization_id=org_one.organization_id,
            source_endpoint="product_group$export",
            source_external_id="cat-a",
            code="SKIN",
            name="Skincare",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    category_b = store.upsert_canonical_product_category(
        CanonicalProductCategory(
            id=canonical_row_uuid("category", org_two.organization_id, "cat-b"),
            organization_id=org_two.organization_id,
            source_endpoint="product_group$export",
            source_external_id="cat-b",
            code="GADGET",
            name="Gadgets",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )

    customer_current = store.upsert_canonical_customer(
        CanonicalCustomer(
            id=canonical_row_uuid("customer", org_one.organization_id, "cust-current"),
            organization_id=org_one.organization_id,
            source_endpoint="legal_person$export",
            source_external_id="cust-current",
            person_id="1001",
            code="CUST-1",
            name="Current Customer",
            data_quality_status=CanonicalDataQualityStatus.PARTIAL,
        )
    )
    customer_prev = store.upsert_canonical_customer(
        CanonicalCustomer(
            id=canonical_row_uuid("customer", org_two.organization_id, "cust-prev"),
            organization_id=org_two.organization_id,
            source_endpoint="legal_person$export",
            source_external_id="cust-prev",
            person_id="2001",
            code="CUST-2",
            name="Previous Customer",
            data_quality_status=CanonicalDataQualityStatus.PARTIAL,
        )
    )
    customer_lost = store.upsert_canonical_customer(
        CanonicalCustomer(
            id=canonical_row_uuid("customer", org_two.organization_id, "cust-lost"),
            organization_id=org_two.organization_id,
            source_endpoint="legal_person$export",
            source_external_id="cust-lost",
            person_id="2002",
            code="CUST-3",
            name="Lost Customer",
            data_quality_status=CanonicalDataQualityStatus.PARTIAL,
        )
    )
    customer_risk = store.upsert_canonical_customer(
        CanonicalCustomer(
            id=canonical_row_uuid("customer", org_two.organization_id, "cust-risk"),
            organization_id=org_two.organization_id,
            source_endpoint="legal_person$export",
            source_external_id="cust-risk",
            person_id="2003",
            code="CUST-4",
            name="At Risk Customer",
            data_quality_status=CanonicalDataQualityStatus.PARTIAL,
        )
    )

    product_a = store.upsert_canonical_product(
        CanonicalProduct(
            id=canonical_row_uuid("product", org_one.organization_id, "prod-a"),
            organization_id=org_one.organization_id,
            source_endpoint="inventory$export",
            source_external_id="prod-a",
            product_id="3001",
            code="BAL-001",
            name="Balance Purifying Gel",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
            metadata={"primary_group_id": category_a.id},
        )
    )
    product_b = store.upsert_canonical_product(
        CanonicalProduct(
            id=canonical_row_uuid("product", org_two.organization_id, "prod-b"),
            organization_id=org_two.organization_id,
            source_endpoint="inventory$export",
            source_external_id="prod-b",
            product_id="3002",
            code="DEC-001",
            name="Declining Product",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
            metadata={"primary_group_id": category_b.id},
        )
    )
    product_c = store.upsert_canonical_product(
        CanonicalProduct(
            id=canonical_row_uuid("product", org_two.organization_id, "prod-c"),
            organization_id=org_two.organization_id,
            source_endpoint="inventory$export",
            source_external_id="prod-c",
            product_id="3003",
            code="LST-001",
            name="Lost Product",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
            metadata={"primary_group_id": category_b.id},
        )
    )

    rep_one = store.upsert_canonical_sales_rep(
        CanonicalSalesRep(
            id=canonical_row_uuid("rep", org_one.organization_id, "rep-1"),
            organization_id=org_one.organization_id,
            source_endpoint="order$export",
            source_external_id="rep-1",
            sales_manager_id="rep-1",
            sales_manager_code="REP-1",
            sales_manager_name="Rep One",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    rep_two = store.upsert_canonical_sales_rep(
        CanonicalSalesRep(
            id=canonical_row_uuid("rep", org_two.organization_id, "rep-2"),
            organization_id=org_two.organization_id,
            source_endpoint="order$export",
            source_external_id="rep-2",
            sales_manager_id="rep-2",
            sales_manager_code="REP-2",
            sales_manager_name="Rep Two",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    zone_one = store.upsert_canonical_working_zone(
        CanonicalWorkingZone(
            id=canonical_row_uuid("zone", org_one.organization_id, "zone-1"),
            organization_id=org_one.organization_id,
            source_endpoint="order$export",
            source_external_id="zone-1",
            room_id="room-1",
            room_code="R-1",
            room_name="Ташкент центр",
            data_quality_status=CanonicalDataQualityStatus.PARTIAL,
        )
    )

    warehouse_one = store.upsert_canonical_warehouse(
        CanonicalWarehouse(
            id=canonical_row_uuid("warehouse", org_one.organization_id, "wh-1"),
            organization_id=org_one.organization_id,
            source_endpoint="warehouse$export",
            source_external_id="wh-1",
            warehouse_id="wh-1",
            warehouse_code="WH-1",
            warehouse_name="Центральный склад",
            source_kind="warehouse",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    warehouse_two = store.upsert_canonical_warehouse(
        CanonicalWarehouse(
            id=canonical_row_uuid("warehouse", org_two.organization_id, "wh-2"),
            organization_id=org_two.organization_id,
            source_endpoint="warehouse$export",
            source_external_id="wh-2",
            warehouse_id="wh-2",
            warehouse_code="WH-2",
            warehouse_name="Склад филиала",
            source_kind="warehouse",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )

    order_current = store.upsert_canonical_order(
        CanonicalOrder(
            id=canonical_row_uuid("order", org_one.organization_id, "sale-current"),
            organization_id=org_one.organization_id,
            source_endpoint="order$export",
            source_external_id="sale-current",
            order_id="ord-1",
            deal_id="268805991",
            order_number="268805991",
            order_at=now - timedelta(days=1),
            customer_id=customer_current.id,
            customer_external_id=customer_current.source_external_id,
            customer_name=customer_current.name,
            sales_rep_id=rep_one.id,
            sales_rep_external_id=rep_one.source_external_id,
            working_zone_id=zone_one.id,
            working_zone_external_id=zone_one.source_external_id,
            normalized_status="approved",
            display_status="APPROVED",
            total_amount=Decimal("606000"),
            currency_code="UZS",
            source_currency_code="860",
            item_count=1,
            sold_quantity=Decimal("4"),
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    order_previous = store.upsert_canonical_order(
        CanonicalOrder(
            id=canonical_row_uuid("order", org_two.organization_id, "sale-previous"),
            organization_id=org_two.organization_id,
            source_endpoint="order$export",
            source_external_id="sale-previous",
            order_id="ord-2",
            deal_id="268802974",
            order_number="268802974",
            order_at=now - timedelta(days=35),
            customer_id=customer_prev.id,
            customer_external_id=customer_prev.source_external_id,
            customer_name=customer_prev.name,
            sales_rep_id=rep_two.id,
            sales_rep_external_id=rep_two.source_external_id,
            normalized_status="approved",
            display_status="APPROVED",
            total_amount=Decimal("500"),
            currency_code="UZS",
            source_currency_code="860",
            item_count=1,
            sold_quantity=Decimal("2"),
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )

    sale_current = store.upsert_canonical_sale(
        CanonicalSale(
            id=canonical_row_uuid("sale", org_one.organization_id, "sale-current"),
            organization_id=org_one.organization_id,
            source_endpoint="order$export",
            source_external_id="sale-current",
            sale_id="sale-1",
            order_id=order_current.id,
            order_external_id=order_current.source_external_id,
            deal_id="268805991",
            sale_number="268805991",
            sale_at=now - timedelta(days=1),
            customer_id=customer_current.id,
            customer_external_id=customer_current.source_external_id,
            customer_name=customer_current.name,
            sales_rep_id=rep_one.id,
            sales_rep_external_id=rep_one.source_external_id,
            working_zone_id=zone_one.id,
            working_zone_external_id=zone_one.source_external_id,
            normalized_status="approved",
            display_status="APPROVED",
            total_amount=Decimal("606000"),
            currency_code="UZS",
            source_currency_code="860",
            item_count=1,
            sold_quantity=Decimal("4"),
            realization_basis="sold_quant",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    store.upsert_canonical_sale(
        CanonicalSale(
            id=canonical_row_uuid("sale", org_two.organization_id, "sale-previous"),
            organization_id=org_two.organization_id,
            source_endpoint="order$export",
            source_external_id="sale-previous",
            sale_id="sale-2",
            order_id=order_previous.id,
            order_external_id=order_previous.source_external_id,
            deal_id="268802974",
            sale_number="268802974",
            sale_at=now - timedelta(days=35),
            customer_id=customer_prev.id,
            customer_external_id=customer_prev.source_external_id,
            customer_name=customer_prev.name,
            sales_rep_id=rep_two.id,
            sales_rep_external_id=rep_two.source_external_id,
            normalized_status="approved",
            display_status="APPROVED",
            total_amount=Decimal("500"),
            currency_code="UZS",
            source_currency_code="860",
            item_count=1,
            sold_quantity=Decimal("2"),
            realization_basis="sold_quant",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    store.upsert_canonical_sale(
        CanonicalSale(
            id=canonical_row_uuid("sale", org_two.organization_id, "sale-lost"),
            organization_id=org_two.organization_id,
            source_endpoint="order$export",
            source_external_id="sale-lost",
            sale_id="sale-3",
            order_id=None,
            order_external_id=None,
            deal_id="268799001",
            sale_number="268799001",
            sale_at=now - timedelta(days=200),
            customer_id=customer_lost.id,
            customer_external_id=customer_lost.source_external_id,
            customer_name=customer_lost.name,
            sales_rep_id=rep_two.id,
            sales_rep_external_id=rep_two.source_external_id,
            normalized_status="approved",
            display_status="APPROVED",
            total_amount=Decimal("300"),
            currency_code="UZS",
            source_currency_code="860",
            item_count=1,
            sold_quantity=Decimal("1"),
            realization_basis="sold_quant",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    store.upsert_canonical_sale(
        CanonicalSale(
            id=canonical_row_uuid("sale", org_two.organization_id, "sale-risk"),
            organization_id=org_two.organization_id,
            source_endpoint="order$export",
            source_external_id="sale-risk",
            sale_id="sale-4",
            order_id=None,
            order_external_id=None,
            deal_id="268799002",
            sale_number="268799002",
            sale_at=now - timedelta(days=70),
            customer_id=customer_risk.id,
            customer_external_id=customer_risk.source_external_id,
            customer_name=customer_risk.name,
            sales_rep_id=rep_two.id,
            sales_rep_external_id=rep_two.source_external_id,
            normalized_status="approved",
            display_status="APPROVED",
            total_amount=Decimal("200"),
            currency_code="UZS",
            source_currency_code="860",
            item_count=1,
            sold_quantity=Decimal("1"),
            realization_basis="sold_quant",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )

    store.upsert_canonical_sale_item(
        CanonicalSaleItem(
            id=canonical_row_uuid("sale-item", org_one.organization_id, "sale-item-current"),
            organization_id=org_one.organization_id,
            source_endpoint="order$export",
            source_external_id="sale-item-current",
            sale_id=sale_current.id,
            order_id=order_current.id,
            sale_external_id=sale_current.source_external_id,
            order_external_id=order_current.source_external_id,
            line_number=1,
            product_id=product_a.id,
            product_external_id=product_a.source_external_id,
            product_code=product_a.code,
            product_name=product_a.name,
            sold_quantity=Decimal("4"),
            ordered_quantity=Decimal("4"),
            unit_price=Decimal("151500"),
            amount=Decimal("606000"),
            currency_code="UZS",
            source_currency_code="860",
            has_realization_evidence=True,
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    store.upsert_canonical_sale_item(
        CanonicalSaleItem(
            id=canonical_row_uuid("sale-item", org_two.organization_id, "sale-item-previous"),
            organization_id=org_two.organization_id,
            source_endpoint="order$export",
            source_external_id="sale-item-previous",
            sale_id=canonical_row_uuid("sale", org_two.organization_id, "sale-previous"),
            order_id=order_previous.id,
            sale_external_id="sale-previous",
            order_external_id=order_previous.source_external_id,
            line_number=1,
            product_id=product_b.id,
            product_external_id=product_b.source_external_id,
            product_code=product_b.code,
            product_name=product_b.name,
            sold_quantity=Decimal("2"),
            ordered_quantity=Decimal("2"),
            unit_price=Decimal("250"),
            amount=Decimal("500"),
            currency_code="UZS",
            source_currency_code="860",
            has_realization_evidence=True,
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    store.upsert_canonical_sale_item(
        CanonicalSaleItem(
            id=canonical_row_uuid("sale-item", org_two.organization_id, "sale-item-lost"),
            organization_id=org_two.organization_id,
            source_endpoint="order$export",
            source_external_id="sale-item-lost",
            sale_id=canonical_row_uuid("sale", org_two.organization_id, "sale-lost"),
            order_id=None,
            sale_external_id="sale-lost",
            order_external_id=None,
            line_number=1,
            product_id=product_c.id,
            product_external_id=product_c.source_external_id,
            product_code=product_c.code,
            product_name=product_c.name,
            sold_quantity=Decimal("1"),
            ordered_quantity=Decimal("1"),
            unit_price=Decimal("300"),
            amount=Decimal("300"),
            currency_code="UZS",
            source_currency_code="860",
            has_realization_evidence=True,
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    store.upsert_canonical_sale_item(
        CanonicalSaleItem(
            id=canonical_row_uuid("sale-item", org_two.organization_id, "sale-item-risk"),
            organization_id=org_two.organization_id,
            source_endpoint="order$export",
            source_external_id="sale-item-risk",
            sale_id=canonical_row_uuid("sale", org_two.organization_id, "sale-risk"),
            order_id=None,
            sale_external_id="sale-risk",
            order_external_id=None,
            line_number=1,
            product_id=product_b.id,
            product_external_id=product_b.source_external_id,
            product_code=product_b.code,
            product_name=product_b.name,
            sold_quantity=Decimal("1"),
            ordered_quantity=Decimal("1"),
            unit_price=Decimal("200"),
            amount=Decimal("200"),
            currency_code="UZS",
            source_currency_code="860",
            has_realization_evidence=True,
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )

    store.upsert_canonical_payment(
        CanonicalPayment(
            id=canonical_row_uuid("payment", org_one.organization_id, "payment-current"),
            organization_id=org_one.organization_id,
            source_endpoint="cashin$export",
            source_external_id="payment-current",
            payment_id="pay-1",
            cashin_id="cashin-1",
            paid_at=now - timedelta(days=1),
            customer_id=customer_current.id,
            customer_external_id=customer_current.source_external_id,
            customer_name=customer_current.name,
            normalized_payment_type="cash",
            amount=Decimal("606000"),
            currency_code="UZS",
            source_currency_code="860",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    store.upsert_canonical_payment_allocation(
        CanonicalPaymentAllocation(
            id=canonical_row_uuid("payment-allocation", org_one.organization_id, "alloc-current"),
            organization_id=org_one.organization_id,
            source_endpoint="cashin$export",
            source_external_id="alloc-current",
            payment_id=canonical_row_uuid("payment", org_one.organization_id, "payment-current"),
            sale_id=sale_current.id,
            sale_external_id=sale_current.source_external_id,
            order_id=order_current.id,
            order_external_id=order_current.source_external_id,
            allocated_amount=Decimal("606000"),
            currency_code="UZS",
            allocation_type="verified_sale_link",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )

    current_return = store.upsert_canonical_customer_return(
        CanonicalCustomerReturn(
            id=canonical_row_uuid("return", org_one.organization_id, "return-current"),
            organization_id=org_one.organization_id,
            source_endpoint="return$export",
            source_external_id="return-current",
            return_id="ret-1",
            deal_id="ret-1",
            return_at=now - timedelta(days=2),
            customer_id=customer_current.id,
            customer_external_id=customer_current.source_external_id,
            customer_name=customer_current.name,
            total_amount=Decimal("50"),
            currency_code="UZS",
            source_currency_code="860",
            returned_quantity=Decimal("1"),
            linked_order_id=order_current.id,
            linked_order_external_id=order_current.source_external_id,
            linked_sale_id=sale_current.id,
            linked_sale_external_id=sale_current.source_external_id,
            normalized_status="approved",
            display_status="APPROVED",
            data_quality_status=CanonicalDataQualityStatus.PARTIAL,
        )
    )
    store.upsert_canonical_customer_return_item(
        CanonicalCustomerReturnItem(
            id=canonical_row_uuid("return-item", org_one.organization_id, "return-item-current"),
            organization_id=org_one.organization_id,
            source_endpoint="return$export",
            source_external_id="return-item-current",
            customer_return_id=current_return.id,
            return_external_id=current_return.source_external_id,
            line_number=1,
            product_id=product_a.id,
            product_external_id=product_a.source_external_id,
            product_code=product_a.code,
            product_name=product_a.name,
            returned_quantity=Decimal("1"),
            unit_price=Decimal("50"),
            amount=Decimal("50"),
            currency_code="UZS",
            linked_order_id=order_current.id,
            linked_sale_id=sale_current.id,
            data_quality_status=CanonicalDataQualityStatus.PARTIAL,
        )
    )

    store.upsert_canonical_financial_operation(
        CanonicalFinancialOperation(
            id=canonical_row_uuid("fin-op", org_one.organization_id, "cash-in"),
            organization_id=org_one.organization_id,
            source_endpoint="cashin$export",
            source_external_id="fin-cash-in",
            operation_id="fin-1",
            operation_date=now - timedelta(days=1),
            normalized_operation_type="customer_payment",
            direction=CanonicalFinancialDirection.INFLOW,
            amount=Decimal("606000"),
            currency_code="UZS",
            source_currency_code="860",
            is_internal_transfer=False,
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    store.upsert_canonical_financial_operation(
        CanonicalFinancialOperation(
            id=canonical_row_uuid("fin-op", org_one.organization_id, "cash-out"),
            organization_id=org_one.organization_id,
            source_endpoint="cash_operation$export",
            source_external_id="fin-cash-out",
            operation_id="fin-2",
            operation_date=now - timedelta(days=1),
            normalized_operation_type="expense",
            direction=CanonicalFinancialDirection.OUTFLOW,
            amount=Decimal("100000"),
            currency_code="UZS",
            source_currency_code="860",
            is_internal_transfer=False,
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )

    store.upsert_canonical_inventory_balance(
        CanonicalInventoryBalance(
            id=canonical_row_uuid("inventory", org_one.organization_id, "inv-a"),
            organization_id=org_one.organization_id,
            source_endpoint="balance$export",
            source_external_id="inv-a",
            snapshot_date=now - timedelta(days=1),
            product_id=product_a.id,
            product_external_id=product_a.source_external_id,
            product_code=product_a.code,
            product_name=product_a.name,
            warehouse_id=warehouse_one.id,
            warehouse_code="WH-1",
            quantity=Decimal("0"),
            valuation_amount=Decimal("0"),
            currency_code="UZS",
            source_currency_code="860",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    store.upsert_canonical_inventory_balance(
        CanonicalInventoryBalance(
            id=canonical_row_uuid("inventory", org_two.organization_id, "inv-b"),
            organization_id=org_two.organization_id,
            source_endpoint="balance$export",
            source_external_id="inv-b",
            snapshot_date=now - timedelta(days=1),
            product_id=product_b.id,
            product_external_id=product_b.source_external_id,
            product_code=product_b.code,
            product_name=product_b.name,
            warehouse_id=warehouse_two.id,
            warehouse_code="WH-2",
            quantity=Decimal("5"),
            valuation_amount=Decimal("1000"),
            currency_code="UZS",
            source_currency_code="860",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    store.upsert_canonical_inventory_balance(
        CanonicalInventoryBalance(
            id=canonical_row_uuid("inventory", org_two.organization_id, "inv-c"),
            organization_id=org_two.organization_id,
            source_endpoint="balance$export",
            source_external_id="inv-c",
            snapshot_date=now - timedelta(days=1),
            product_id=product_c.id,
            product_external_id=product_c.source_external_id,
            product_code=product_c.code,
            product_name=product_c.name,
            warehouse_id=warehouse_two.id,
            warehouse_code="WH-2",
            quantity=Decimal("1"),
            valuation_amount=Decimal("300"),
            currency_code="UZS",
            source_currency_code="860",
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )

    store.upsert_canonical_purchase(
        CanonicalPurchase(
            id=canonical_row_uuid("purchase", org_one.organization_id, "purchase-1"),
            organization_id=org_one.organization_id,
            source_endpoint="purchase$export",
            source_external_id="purchase-1",
            document_id="purchase-1",
            document_number="PUR-001",
            document_at=now - timedelta(days=3),
            purchase_id="purchase-1",
            purchase_number="PUR-001",
            supplier_external_id="supp-1",
            supplier_code="SUP-001",
            warehouse_id=warehouse_one.id,
            warehouse_code=warehouse_one.warehouse_code,
            total_amount=Decimal("450000"),
            currency_code="UZS",
            source_currency_code="860",
            item_count=2,
            total_quantity=Decimal("12"),
            posted="Y",
            data_quality_status=CanonicalDataQualityStatus.PARTIAL,
            metadata={
                "product_linkage_coverage": "0.5",
                "warehouse_linkage_coverage": "1",
                "coverage_note": "1 из 2 строк связана с товаром.",
            },
        )
    )
    store.upsert_canonical_warehouse_receipt(
        CanonicalWarehouseReceipt(
            id=canonical_row_uuid("receipt", org_one.organization_id, "receipt-1"),
            organization_id=org_one.organization_id,
            source_endpoint="input$export",
            source_external_id="receipt-1",
            document_id="receipt-1",
            document_number="RCV-001",
            document_at=now - timedelta(days=2),
            receipt_id="receipt-1",
            receipt_number="RCV-001",
            supplier_external_id="supp-1",
            supplier_code="SUP-001",
            warehouse_id=warehouse_one.id,
            warehouse_code=warehouse_one.warehouse_code,
            total_amount=Decimal("450000"),
            currency_code="UZS",
            source_currency_code="860",
            item_count=2,
            total_quantity=Decimal("12"),
            data_quality_status=CanonicalDataQualityStatus.PARTIAL,
            metadata={
                "linked_purchase_external_id": "purchase-1",
                "coverage_note": "Связь с закупкой подтверждена по purchase item.",
            },
        )
    )
    store.upsert_canonical_writeoff(
        CanonicalWriteoff(
            id=canonical_row_uuid("writeoff", org_one.organization_id, "writeoff-1"),
            organization_id=org_one.organization_id,
            source_endpoint="writeoff$export",
            source_external_id="writeoff-1",
            document_id="writeoff-1",
            document_number="WR-001",
            document_at=now - timedelta(days=1),
            writeoff_id="writeoff-1",
            writeoff_number="WR-001",
            writeoff_date=now - timedelta(days=1),
            warehouse_id=warehouse_one.id,
            warehouse_code=warehouse_one.warehouse_code,
            reason_code="DAMAGED",
            total_amount=Decimal("50000"),
            currency_code="UZS",
            source_currency_code="860",
            item_count=1,
            total_quantity=Decimal("1"),
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    store.upsert_canonical_supplier_return(
        CanonicalSupplierReturn(
            id=canonical_row_uuid("supplier-return", org_one.organization_id, "supplier-return-1"),
            organization_id=org_one.organization_id,
            source_endpoint="supplier_return$export",
            source_external_id="supplier-return-1",
            document_id="supplier-return-1",
            document_number="SR-001",
            document_at=now - timedelta(days=4),
            supplier_return_id="supplier-return-1",
            supplier_return_number="SR-001",
            supplier_external_id="supp-1",
            supplier_code="SUP-001",
            warehouse_id=warehouse_one.id,
            warehouse_code=warehouse_one.warehouse_code,
            reason_code="DEFECT",
            total_amount=Decimal("75000"),
            currency_code="UZS",
            source_currency_code="860",
            item_count=1,
            total_quantity=Decimal("2"),
            data_quality_status=CanonicalDataQualityStatus.PARTIAL,
        )
    )
    store.upsert_canonical_stocktaking(
        CanonicalStocktaking(
            id=canonical_row_uuid("stocktaking", org_one.organization_id, "stocktaking-1"),
            organization_id=org_one.organization_id,
            source_endpoint="stocktaking$export",
            source_external_id="stocktaking-1",
            document_id="stocktaking-1",
            document_number="STK-001",
            document_at=now - timedelta(days=5),
            stocktaking_id="stocktaking-1",
            stocktaking_number="STK-001",
            warehouse_id=warehouse_one.id,
            warehouse_code=warehouse_one.warehouse_code,
            item_count=3,
            total_quantity=Decimal("18"),
            data_quality_status=CanonicalDataQualityStatus.PARTIAL,
        )
    )
    store.upsert_canonical_internal_movement(
        CanonicalInternalMovement(
            id=canonical_row_uuid("movement", org_one.organization_id, "movement-1"),
            organization_id=org_one.organization_id,
            source_endpoint="movement$export",
            source_external_id="movement-1",
            document_id="movement-1",
            document_number="MOV-001",
            document_at=now - timedelta(days=6),
            movement_id="movement-1",
            movement_number="MOV-001",
            source_warehouse_id=warehouse_one.id,
            source_warehouse_code=warehouse_one.warehouse_code,
            destination_warehouse_id=warehouse_one.id,
            destination_warehouse_code="WH-1A",
            total_amount=Decimal("0"),
            currency_code="UZS",
            source_currency_code="860",
            item_count=1,
            total_quantity=Decimal("3"),
            data_quality_status=CanonicalDataQualityStatus.PARTIAL,
        )
    )
    store.upsert_canonical_cross_org_movement(
        CanonicalCrossOrgMovement(
            id=canonical_row_uuid("cross-movement", org_one.organization_id, "cross-movement-1"),
            organization_id=org_one.organization_id,
            source_endpoint="cross_movement$export",
            source_external_id="cross-movement-1",
            document_id="cross-movement-1",
            document_number="XORG-001",
            document_at=now - timedelta(days=7),
            movement_id="cross-movement-1",
            delivery_number="XORG-001",
            source_filial_code=org_one.filial_code,
            destination_filial_code=org_two.filial_code,
            source_warehouse_id=warehouse_one.id,
            source_warehouse_code=warehouse_one.warehouse_code,
            destination_warehouse_id=warehouse_two.id,
            destination_warehouse_code=warehouse_two.warehouse_code,
            total_amount=Decimal("90000"),
            currency_code="UZS",
            source_currency_code="860",
            item_count=1,
            total_quantity=Decimal("2"),
            data_quality_status=CanonicalDataQualityStatus.PARTIAL,
        )
    )

    store.upsert_canonical_visit(
        CanonicalVisit(
            id=canonical_row_uuid("visit", org_one.organization_id, "visit-current"),
            organization_id=org_one.organization_id,
            source_endpoint="visit$export",
            source_external_id="visit-current",
            visit_id="visit-1",
            customer_id=customer_current.id,
            customer_external_id=customer_current.source_external_id,
            customer_name=customer_current.name,
            sales_rep_id=rep_one.id,
            sales_rep_external_id=rep_one.source_external_id,
            visit_date=now - timedelta(days=1),
            visited_at=now - timedelta(days=1),
            duration_seconds=900,
            normalized_status="completed",
            display_status="COMPLETED",
            is_planned=True,
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )
    store.upsert_canonical_visit(
        CanonicalVisit(
            id=canonical_row_uuid("visit", org_two.organization_id, "visit-lost"),
            organization_id=org_two.organization_id,
            source_endpoint="visit$export",
            source_external_id="visit-lost",
            visit_id="visit-2",
            customer_id=customer_lost.id,
            customer_external_id=customer_lost.source_external_id,
            customer_name=customer_lost.name,
            sales_rep_id=rep_two.id,
            sales_rep_external_id=rep_two.source_external_id,
            visit_date=now - timedelta(days=200),
            visited_at=now - timedelta(days=200),
            duration_seconds=600,
            normalized_status="completed",
            display_status="COMPLETED",
            is_planned=False,
            data_quality_status=CanonicalDataQualityStatus.VERIFIED,
        )
    )

    return store, org_one, org_two


def _client_for_store(store: InMemoryCoreDataLayer) -> TestClient:
    app.dependency_overrides[get_core_store] = lambda: store
    return TestClient(app)


def _analytics_params(
    org_one: CanonicalOrganization,
    org_two: CanonicalOrganization,
) -> list[tuple[str, str]]:
    today = datetime.now(UTC).date()
    return [
        ("organization_ids", str(org_one.organization_id)),
        ("organization_ids", str(org_two.organization_id)),
        ("period", "custom"),
        ("comparison_mode", "previous_period"),
        ("date_from", (today - timedelta(days=30)).isoformat()),
        ("date_to", today.isoformat()),
    ]


def test_analytics_summary_separates_sales_revenue_and_cash_flow() -> None:
    store, org_one, org_two = _seed_analytics_store()
    client = _client_for_store(store)

    try:
        response = client.get(
            "/api/v1/analytics/summary",
            params=_analytics_params(org_one, org_two),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert _metric_value(payload, "business", "revenue", "value") == Decimal("606000")
    assert _metric_value(payload, "business", "orders", "value") == Decimal("1")
    assert _metric_value(payload, "business", "sold_units", "value") == Decimal("4")
    assert _metric_value(payload, "business", "average_order", "value") == Decimal("606000")
    assert _metric_value(payload, "business", "payments_received", "value") == Decimal("606000")
    assert _metric_value(payload, "business", "returns", "value") == Decimal("50")
    assert _metric_value(payload, "business", "expenses", "value") == Decimal("100000")
    assert _metric_value(payload, "business", "cash_flow", "value") == Decimal("506000")
    assert payload["data_quality"]["overall_status"] == "AVAILABLE"
    assert len(payload["organization_comparison"]) == 2
    organization_names = {row["organization_name"] for row in payload["organization_comparison"]}
    assert organization_names == {"Alpha LLC", "Beta LLC"}


def test_analytics_products_cover_decline_velocity_and_stockout() -> None:
    store, org_one, org_two = _seed_analytics_store()
    client = _client_for_store(store)

    try:
        response = client.get(
            "/api/v1/analytics/products",
            params=_analytics_params(org_one, org_two),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert len(payload["items"]) >= 3
    product_a = next(item for item in payload["items"] if item["product_external_id"] == "prod-a")
    product_b = next(item for item in payload["items"] if item["product_external_id"] == "prod-b")

    assert _metric_value(product_a, "sold_units", "value") == Decimal("4")
    assert _metric_value(product_a, "revenue", "value") == Decimal("606000")
    assert product_a["stockout_risk"] == "critical"

    assert _metric_value(product_b, "revenue_change_pct", "value") == Decimal("-100")
    assert product_b["classification"] in {"DECLINING", "DEAD_STOCK", "UNCLASSIFIED", "STABLE"}
    assert product_b["sales_velocity_30d"]["value"] in {
        "0.1",
        "0.06666666666666666666666666667",
        None,
    }
    assert payload["top"]
    assert payload["top"][0]["product_external_id"] == "prod-a"


def test_analytics_customers_detects_lost_and_at_risk_segments() -> None:
    store, org_one, org_two = _seed_analytics_store()
    client = _client_for_store(store)

    try:
        response = client.get(
            "/api/v1/analytics/customers",
            params=[
                ("organization_ids", str(org_one.organization_id)),
                ("organization_ids", str(org_two.organization_id)),
                ("period", "all"),
                ("comparison_mode", "previous_period"),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert len(payload["items"]) >= 3
    segments = payload["segments"]
    assert "LOST" in segments
    assert any(item["customer_external_id"] == "cust-lost" for item in segments["LOST"])
    assert "AT_RISK" in segments
    assert any(item["customer_external_id"] == "cust-risk" for item in segments["AT_RISK"])


def test_analytics_finance_and_snapshot_return_structured_payloads() -> None:
    store, org_one, org_two = _seed_analytics_store()
    client = _client_for_store(store)

    try:
        finance_response = client.get(
            "/api/v1/analytics/finance",
            params=_analytics_params(org_one, org_two),
        )
        snapshot_response = client.get(
            "/api/v1/analytics/snapshot",
            params=_analytics_params(org_one, org_two),
        )
    finally:
        app.dependency_overrides.clear()

    assert finance_response.status_code == 200
    finance_payload = finance_response.json()
    assert _metric_value(finance_payload, "sales_revenue", "value") == Decimal("606000")
    assert _metric_value(finance_payload, "payments_received", "value") == Decimal("606000")
    assert _metric_value(finance_payload, "expenses", "value") == Decimal("100000")
    assert _metric_value(finance_payload, "cash_flow", "value") == Decimal("506000")

    assert snapshot_response.status_code == 200
    snapshot_payload = snapshot_response.json()
    assert snapshot_payload["business"]["revenue"]["value"] == "606000"
    assert len(snapshot_payload["top_products"]) >= 1
    assert len(snapshot_payload["top_customers"]) >= 1
    assert len(snapshot_payload["metric_registry"]) >= 5
    assert snapshot_payload["validation_notes"]
