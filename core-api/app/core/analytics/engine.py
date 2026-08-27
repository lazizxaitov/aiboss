"""Deterministic Canonical V2 analytics engine."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.analytics.models import (
    AnalyticsBusinessSnapshot,
    AnalyticsBusinessSummary,
    AnalyticsComparisonMode,
    AnalyticsCustomerItem,
    AnalyticsCustomerReport,
    AnalyticsDataQualityEntry,
    AnalyticsDataQualityReport,
    AnalyticsDataStatus,
    AnalyticsDimensionRow,
    AnalyticsFinanceItem,
    AnalyticsFinanceReport,
    AnalyticsInventoryReport,
    AnalyticsInventoryTransferOpportunity,
    AnalyticsMetricValue,
    AnalyticsOrganizationItem,
    AnalyticsOrganizationReport,
    AnalyticsPeriodPreset,
    AnalyticsPeriodWindow,
    AnalyticsProductItem,
    AnalyticsProductReport,
    AnalyticsQuery,
    AnalyticsReturnItem,
    AnalyticsSalesRepItem,
    AnalyticsSalesReport,
    AnalyticsSalesRepReport,
    AnalyticsSummaryResponse,
    AnalyticsVisitItem,
    AnalyticsVisitReport,
    MetricDefinition,
)
from app.core.data_layer.canonical_v2 import (
    CanonicalCustomer,
    CanonicalCustomerReturn,
    CanonicalDataQualityStatus,
    CanonicalFinancialDirection,
    CanonicalFinancialOperation,
    CanonicalInventoryBalance,
    CanonicalOrder,
    CanonicalOrganization,
    CanonicalPayment,
    CanonicalProduct,
    CanonicalProductCategory,
    CanonicalSale,
    CanonicalSaleItem,
    CanonicalSalesRep,
    CanonicalVisit,
    CanonicalWarehouse,
    CanonicalWorkingZone,
)
from app.core.data_layer.contracts import CoreDataReader


@dataclass(slots=True)
class AnalyticsThresholds:
    fast_growing_percent: Decimal = Decimal("20")
    declining_percent: Decimal = Decimal("-20")
    low_stock_days: int = 7
    overstock_days: int = 120
    active_customer_days: int = 30
    at_risk_customer_days: int = 60
    lost_customer_days: int = 120


@dataclass(slots=True)
class _PreparedContext:
    query: AnalyticsQuery
    window: AnalyticsPeriodWindow
    organization_ids: list[UUID]
    organizations: list[CanonicalOrganization]
    sales: list[CanonicalSale]
    sale_items: list[CanonicalSaleItem]
    orders: list[CanonicalOrder]
    customers: list[CanonicalCustomer]
    products: list[CanonicalProduct]
    product_categories: list[CanonicalProductCategory]
    inventory_balances: list[CanonicalInventoryBalance]
    payments: list[CanonicalPayment]
    financial_operations: list[CanonicalFinancialOperation]
    customer_returns: list[CanonicalCustomerReturn]
    visits: list[CanonicalVisit]
    sales_reps: list[CanonicalSalesRep]
    working_zones: list[CanonicalWorkingZone]
    warehouses: list[CanonicalWarehouse]
    current_sales: list[CanonicalSale]
    previous_sales: list[CanonicalSale]
    current_sale_items: list[CanonicalSaleItem]
    previous_sale_items: list[CanonicalSaleItem]
    current_orders: list[CanonicalOrder]
    previous_orders: list[CanonicalOrder]
    current_payments: list[CanonicalPayment]
    previous_payments: list[CanonicalPayment]
    current_financial_operations: list[CanonicalFinancialOperation]
    previous_financial_operations: list[CanonicalFinancialOperation]
    current_customer_returns: list[CanonicalCustomerReturn]
    previous_customer_returns: list[CanonicalCustomerReturn]
    current_visits: list[CanonicalVisit]
    previous_visits: list[CanonicalVisit]
    current_inventory_balances: list[CanonicalInventoryBalance]
    previous_inventory_balances: list[CanonicalInventoryBalance]


class BusinessAnalyticsEngine:
    """Deterministic analytics over Canonical V2 only."""

    def __init__(
        self,
        store: CoreDataReader,
        thresholds: AnalyticsThresholds | None = None,
    ) -> None:
        self.store = store
        self.thresholds = thresholds or AnalyticsThresholds()

    def build_summary(self, query: AnalyticsQuery) -> AnalyticsSummaryResponse:
        prepared = self._prepare(query)
        return AnalyticsSummaryResponse(
            period=prepared.window,
            business=self._build_business_summary(prepared),
            data_quality=self._build_data_quality(prepared),
            metric_registry=self.metric_registry(),
            organization_comparison=self._build_organization_items(prepared),
            top_products=self._build_product_items(prepared)[:10],
            top_customers=self._build_customer_items(prepared)[:10],
            top_sales_reps=self._build_sales_rep_items(prepared)[:10],
        )

    def build_sales(self, query: AnalyticsQuery) -> AnalyticsSalesReport:
        prepared = self._prepare(query)
        return AnalyticsSalesReport(
            period=prepared.window,
            summary=self._build_business_summary(prepared),
            by_date=self._sales_by_date(prepared),
            by_organization=self._sales_by_organization(prepared),
            by_customer=self._sales_by_customer(prepared),
            by_product=self._sales_by_product(prepared),
            by_category=self._sales_by_category(prepared),
            by_sales_rep=self._sales_by_sales_rep(prepared),
            by_working_zone=self._sales_by_working_zone(prepared),
            by_payment_type=self._sales_by_payment_type(prepared),
            by_order_status=self._sales_by_order_status(prepared),
            data_quality=self._build_data_quality(prepared),
        )

    def build_products(self, query: AnalyticsQuery) -> AnalyticsProductReport:
        prepared = self._prepare(query)
        items = self._build_product_items(prepared)
        return AnalyticsProductReport(
            period=prepared.window,
            items=items,
            top=items[:10],
            growing=[
                item
                for item in items
                if _metric_decimal(item.revenue_change_pct) is not None
                and _metric_decimal(item.revenue_change_pct) >= self.thresholds.fast_growing_percent
            ],
            declining=[
                item
                for item in items
                if _metric_decimal(item.revenue_change_pct) is not None
                and _metric_decimal(item.revenue_change_pct) <= self.thresholds.declining_percent
            ],
            slow_movers=[item for item in items if item.classification in {"DECLINING", "DEAD_STOCK"}],
            dead_stock=[item for item in items if item.classification == "DEAD_STOCK"],
            low_stock=[item for item in items if item.stockout_risk in {"critical", "high", "medium"}],
            overstock=[item for item in items if "OVERSTOCK" in item.classification_tags],
            stockout_risk=[item for item in items if item.stockout_risk in {"critical", "high"}],
            transfer_opportunities=self._build_inventory_opportunities(prepared),
            data_quality=self._build_data_quality(prepared),
        )

    def build_customers(self, query: AnalyticsQuery) -> AnalyticsCustomerReport:
        prepared = self._prepare(query)
        items = self._build_customer_items(prepared)
        segments: dict[str, list[AnalyticsCustomerItem]] = defaultdict(list)
        for item in items:
            segments[item.segment].append(item)
        return AnalyticsCustomerReport(
            period=prepared.window,
            items=items,
            top=items[:10],
            growing=[
                item
                for item in items
                if item.revenue.percent_delta is not None and item.revenue.percent_delta > 0
            ],
            at_risk=[item for item in items if item.segment in {"AT_RISK", "DECLINING"}],
            lost=[item for item in items if item.segment == "LOST"],
            segments=dict(segments),
            data_quality=self._build_data_quality(prepared),
        )

    def build_inventory(self, query: AnalyticsQuery) -> AnalyticsInventoryReport:
        prepared = self._prepare(query)
        items = self._build_product_items(prepared)
        return AnalyticsInventoryReport(
            period=prepared.window,
            items=items,
            low_stock=[item for item in items if item.stockout_risk in {"critical", "high", "medium"}],
            overstock=[item for item in items if "OVERSTOCK" in item.classification_tags],
            stockout_risk=[item for item in items if item.stockout_risk in {"critical", "high"}],
            transfer_opportunities=self._build_inventory_opportunities(prepared),
            data_quality=self._build_data_quality(prepared),
        )

    def build_organizations(self, query: AnalyticsQuery) -> AnalyticsOrganizationReport:
        prepared = self._prepare(query)
        items = self._build_organization_items(prepared)
        return AnalyticsOrganizationReport(
            period=prepared.window,
            items=items,
            comparison=items,
            data_quality=self._build_data_quality(prepared),
        )

    def build_sales_reps(self, query: AnalyticsQuery) -> AnalyticsSalesRepReport:
        prepared = self._prepare(query)
        items = self._build_sales_rep_items(prepared)
        return AnalyticsSalesRepReport(
            period=prepared.window,
            items=items,
            top=items[:10],
            data_quality=self._build_data_quality(prepared),
        )

    def build_visits(self, query: AnalyticsQuery) -> AnalyticsVisitReport:
        prepared = self._prepare(query)
        return AnalyticsVisitReport(
            period=prepared.window,
            items=self._build_visit_items(prepared),
            by_organization=self._visit_by_organization(prepared),
            by_sales_rep=self._visit_by_sales_rep(prepared),
            by_customer=self._visit_by_customer(prepared),
            by_working_zone=self._visit_by_working_zone(prepared),
            data_quality=self._build_data_quality(prepared),
        )

    def build_finance(self, query: AnalyticsQuery) -> AnalyticsFinanceReport:
        prepared = self._prepare(query)
        sales_revenue = self._sales_revenue_metric(prepared)
        payments_received = self._payments_received_metric(prepared)
        expenses = self._expenses_metric(prepared)
        cash_in = self._cash_in_metric(prepared)
        cash_out = self._cash_out_metric(prepared)
        return AnalyticsFinanceReport(
            period=prepared.window,
            sales_revenue=sales_revenue,
            payments_received=payments_received,
            cash_operations=self._financial_metric_by_type(prepared, {"cash_operation"}),
            bank_operations=self._financial_metric_by_type(prepared, {"bank_operation"}),
            expenses=expenses,
            cash_flow=self._net_cash_flow_metric(cash_in, cash_out, prepared.window),
            by_type=self._finance_by_type(prepared),
            by_category=self._finance_by_category(prepared),
            data_quality=self._build_data_quality(prepared),
        )

    def build_snapshot(self, query: AnalyticsQuery) -> AnalyticsBusinessSnapshot:
        prepared = self._prepare(query)
        products = self._build_product_items(prepared)
        customers = self._build_customer_items(prepared)
        organizations = self._build_organization_items(prepared)
        sales_reps = self._build_sales_rep_items(prepared)
        return AnalyticsBusinessSnapshot(
            period=prepared.window,
            query=prepared.query,
            business=self._build_business_summary(prepared),
            organizations=organizations,
            products=products,
            customers=customers,
            inventory=self._build_inventory_opportunities(prepared),
            sales_reps=sales_reps,
            visits=self._build_visit_items(prepared),
            finance=self._build_finance_items(prepared),
            returns=self._build_return_items(prepared),
            metric_registry=self.metric_registry(),
            data_quality=self._build_data_quality(prepared),
            validation_notes=self._build_validation_notes(prepared),
            top_products=products[:10],
            slow_products=[item for item in products if item.classification in {"DECLINING", "DEAD_STOCK"}],
            growing_products=[
                item
                for item in products
                if _metric_decimal(item.revenue_change_pct) is not None
                and _metric_decimal(item.revenue_change_pct) >= self.thresholds.fast_growing_percent
            ],
            declining_products=[
                item
                for item in products
                if _metric_decimal(item.revenue_change_pct) is not None
                and _metric_decimal(item.revenue_change_pct) <= self.thresholds.declining_percent
            ],
            low_stock_products=[item for item in products if item.stockout_risk in {"critical", "high", "medium"}],
            overstock_products=[item for item in products if "OVERSTOCK" in item.classification_tags],
            stockout_risk_products=[item for item in products if item.stockout_risk in {"critical", "high"}],
            top_customers=customers[:10],
            at_risk_customers=[item for item in customers if item.segment in {"AT_RISK", "DECLINING"}],
            lost_customers=[item for item in customers if item.segment == "LOST"],
            organization_comparison=organizations,
            top_sales_reps=sales_reps[:10],
        )

    def metric_registry(self) -> list[MetricDefinition]:
        return [
            MetricDefinition(
                metric_key="revenue",
                display_name="Revenue",
                description="Verified realised sales amount from canonical sales.",
                canonical_sources=["canonical_sales"],
                source_entities=["canonical_sales"],
                formula="SUM(canonical_sales.total_amount WHERE quality=VERIFIED AND sold_quantity>0 AND normalized_status!='cancelled')",
                required_quality="VERIFIED",
                authoritative_date_field="sale_at",
                supported_dimensions=[
                    "organization",
                    "date",
                    "customer",
                    "product",
                    "category",
                    "sales_rep",
                    "working_zone",
                    "normalized_status",
                ],
                currency_behavior="preserve",
                null_behavior="NO_VERIFIED_DATA",
                drilldown_target="sales",
            ),
            MetricDefinition(
                metric_key="orders",
                display_name="Orders",
                description="Canonical order documents in selected period.",
                canonical_sources=["canonical_orders"],
                source_entities=["canonical_orders"],
                formula="COUNT(canonical_orders)",
                required_quality="PARTIAL",
                authoritative_date_field="order_at",
                supported_dimensions=[
                    "organization",
                    "date",
                    "customer",
                    "sales_rep",
                    "working_zone",
                    "normalized_status",
                ],
                currency_behavior="preserve",
                null_behavior="NO_DATA",
                drilldown_target="sales",
            ),
            MetricDefinition(
                metric_key="realised_sales",
                display_name="Realised Sales",
                description="Count of verified realised canonical sales.",
                canonical_sources=["canonical_sales"],
                source_entities=["canonical_sales"],
                formula="COUNT(canonical_sales WHERE quality=VERIFIED AND sold_quantity>0 AND normalized_status!='cancelled')",
                required_quality="VERIFIED",
                authoritative_date_field="sale_at",
                supported_dimensions=["organization", "date", "customer", "sales_rep", "working_zone"],
                currency_behavior="preserve",
                null_behavior="NO_VERIFIED_DATA",
                drilldown_target="sales",
            ),
            MetricDefinition(
                metric_key="sold_units",
                display_name="Sold Units",
                description="Verified sold quantity from canonical sale items.",
                canonical_sources=["canonical_sale_items"],
                source_entities=["canonical_sale_items"],
                formula="SUM(canonical_sale_items.sold_quantity WHERE quality=VERIFIED)",
                required_quality="VERIFIED",
                authoritative_date_field="sale_at",
                supported_dimensions=[
                    "organization",
                    "date",
                    "product",
                    "category",
                    "sales_rep",
                    "working_zone",
                ],
                currency_behavior="preserve",
                null_behavior="NO_VERIFIED_DATA",
                drilldown_target="sales",
            ),
            MetricDefinition(
                metric_key="average_order",
                display_name="Average Order",
                description="Average verified realised sales amount per canonical order in selected period.",
                canonical_sources=["canonical_sales", "canonical_orders"],
                source_entities=["canonical_sales", "canonical_orders"],
                formula="revenue / orders",
                required_quality="VERIFIED",
                authoritative_date_field="sale_at",
                supported_dimensions=["organization", "date", "customer", "sales_rep"],
                currency_behavior="preserve",
                null_behavior="NO_DATA",
                drilldown_target="sales",
            ),
            MetricDefinition(
                metric_key="unique_customers",
                display_name="Unique Customers",
                description="Distinct customers linked to verified canonical sales.",
                canonical_sources=["canonical_sales"],
                source_entities=["canonical_sales"],
                formula="COUNT(DISTINCT canonical_sales.customer_id)",
                required_quality="VERIFIED",
                authoritative_date_field="sale_at",
                supported_dimensions=["organization", "date", "sales_rep", "working_zone"],
                currency_behavior="preserve",
                null_behavior="NO_DATA",
                drilldown_target="customers",
            ),
            MetricDefinition(
                metric_key="unique_products",
                display_name="Unique Products",
                description="Distinct products sold in verified canonical sale items.",
                canonical_sources=["canonical_sale_items"],
                source_entities=["canonical_sale_items"],
                formula="COUNT(DISTINCT canonical_sale_items.product_id)",
                required_quality="VERIFIED",
                authoritative_date_field="sale_at",
                supported_dimensions=["organization", "date", "category", "sales_rep", "working_zone"],
                currency_behavior="preserve",
                null_behavior="NO_DATA",
                drilldown_target="products",
            ),
            MetricDefinition(
                metric_key="payments_received",
                display_name="Payments Received",
                description="Canonical customer payments.",
                canonical_sources=["canonical_payments"],
                source_entities=["canonical_payments"],
                formula="SUM(canonical_payments.amount)",
                required_quality="PARTIAL",
                authoritative_date_field="paid_at",
                supported_dimensions=["organization", "date", "customer", "payment_type"],
                currency_behavior="preserve",
                null_behavior="NO_DATA",
                drilldown_target="finance",
            ),
            MetricDefinition(
                metric_key="customer_return_value",
                display_name="Customer Return Value",
                description="Canonical customer returns value.",
                canonical_sources=["canonical_customer_returns"],
                source_entities=["canonical_customer_returns"],
                formula="SUM(canonical_customer_returns.total_amount)",
                required_quality="PARTIAL",
                authoritative_date_field="return_at",
                supported_dimensions=["organization", "date", "customer", "sales_rep", "normalized_status"],
                currency_behavior="preserve",
                null_behavior="NO_DATA",
                drilldown_target="finance",
            ),
            MetricDefinition(
                metric_key="current_stock",
                display_name="Current Stock",
                description="Latest verified inventory snapshot quantity for selected scope.",
                canonical_sources=["canonical_inventory_balances"],
                source_entities=["canonical_inventory_balances"],
                formula="SUM(latest canonical_inventory_balances.quantity BY organization, warehouse, product)",
                required_quality="VERIFIED",
                authoritative_date_field="snapshot_date",
                supported_dimensions=["organization", "warehouse", "product", "category"],
                currency_behavior="preserve",
                null_behavior="NO_VERIFIED_DATA",
                drilldown_target="inventory",
            ),
            MetricDefinition(
                metric_key="visits",
                display_name="Visits",
                description="Canonical field visits in selected period.",
                canonical_sources=["canonical_visits"],
                source_entities=["canonical_visits"],
                formula="COUNT(canonical_visits)",
                required_quality="PARTIAL",
                authoritative_date_field="visited_at",
                supported_dimensions=["organization", "date", "customer", "sales_rep", "working_zone"],
                currency_behavior="preserve",
                null_behavior="NO_DATA",
                drilldown_target="visits",
            ),
            MetricDefinition(
                metric_key="cash_in",
                display_name="Cash In",
                description="Verified external inflow financial operations.",
                canonical_sources=["canonical_financial_operations"],
                source_entities=["canonical_financial_operations"],
                formula="SUM(canonical_financial_operations.amount WHERE quality=VERIFIED AND direction=INFLOW)",
                required_quality="VERIFIED",
                authoritative_date_field="operation_date",
                supported_dimensions=["organization", "date", "operation_type"],
                currency_behavior="preserve",
                null_behavior="NO_VERIFIED_DATA",
                drilldown_target="finance",
            ),
            MetricDefinition(
                metric_key="verified_cash_in",
                display_name="Verified Cash In",
                description="Verified external inflow financial operations.",
                canonical_sources=["canonical_financial_operations"],
                source_entities=["canonical_financial_operations"],
                formula="SUM(canonical_financial_operations.amount WHERE quality=VERIFIED AND direction=INFLOW)",
                required_quality="VERIFIED",
                authoritative_date_field="operation_date",
                supported_dimensions=["organization", "date", "operation_type"],
                currency_behavior="preserve",
                null_behavior="NO_VERIFIED_DATA",
                drilldown_target="finance",
            ),
            MetricDefinition(
                metric_key="cash_out",
                display_name="Cash Out",
                description="Verified external outflow financial operations.",
                canonical_sources=["canonical_financial_operations"],
                source_entities=["canonical_financial_operations"],
                formula="SUM(canonical_financial_operations.amount WHERE quality=VERIFIED AND direction=OUTFLOW)",
                required_quality="VERIFIED",
                authoritative_date_field="operation_date",
                supported_dimensions=["organization", "date", "operation_type"],
                currency_behavior="preserve",
                null_behavior="NO_VERIFIED_DATA",
                drilldown_target="finance",
            ),
            MetricDefinition(
                metric_key="verified_cash_out",
                display_name="Verified Cash Out",
                description="Verified external outflow financial operations.",
                canonical_sources=["canonical_financial_operations"],
                source_entities=["canonical_financial_operations"],
                formula="SUM(canonical_financial_operations.amount WHERE quality=VERIFIED AND direction=OUTFLOW)",
                required_quality="VERIFIED",
                authoritative_date_field="operation_date",
                supported_dimensions=["organization", "date", "operation_type"],
                currency_behavior="preserve",
                null_behavior="NO_VERIFIED_DATA",
                drilldown_target="finance",
            ),
            MetricDefinition(
                metric_key="net_cash_flow",
                display_name="Net Cash Flow",
                description="Cash in minus cash out when both sides are verified.",
                canonical_sources=["canonical_financial_operations"],
                source_entities=["canonical_financial_operations"],
                formula="cash_in - cash_out when both metrics AVAILABLE",
                required_quality="VERIFIED",
                authoritative_date_field="operation_date",
                supported_dimensions=["organization", "date"],
                currency_behavior="preserve",
                null_behavior="NO_VERIFIED_DATA",
                drilldown_target="finance",
            ),
        ]

    def _prepare(self, query: AnalyticsQuery) -> _PreparedContext:
        window = _build_period_window(query)
        organizations = list(self.store.list_canonical_organizations())
        selected_ids = list(dict.fromkeys(query.organization_ids or []))
        if query.organization_id is not None:
            selected_ids = [query.organization_id]
        if not selected_ids:
            selected_ids = [organization.organization_id for organization in organizations]
        selected_set = set(selected_ids)
        organizations = [row for row in organizations if row.organization_id in selected_set]

        sales = _filter_org(self.store.list_canonical_sales(), selected_set)
        sale_items = _filter_org(self.store.list_canonical_sale_items(), selected_set)
        orders = _filter_org(self.store.list_canonical_orders(), selected_set)
        customers = _filter_org(self.store.list_canonical_customers(), selected_set)
        products = _filter_org(self.store.list_canonical_products(), selected_set)
        product_categories = _filter_org(self.store.list_canonical_product_categories(), selected_set)
        inventory_balances = _filter_org(self.store.list_canonical_inventory_balances(), selected_set)
        payments = _filter_org(self.store.list_canonical_payments(), selected_set)
        financial_operations = _filter_org(
            self.store.list_canonical_financial_operations(),
            selected_set,
        )
        customer_returns = _filter_org(self.store.list_canonical_customer_returns(), selected_set)
        visits = _filter_org(self.store.list_canonical_visits(), selected_set)
        sales_reps = _filter_org(self.store.list_canonical_sales_reps(), selected_set)
        working_zones = _filter_org(self.store.list_canonical_working_zones(), selected_set)
        warehouses = _filter_org(self.store.list_canonical_warehouses(), selected_set)

        current_sales = _filter_by_window(sales, window, lambda row: row.sale_at)
        previous_sales = _filter_previous_window(sales, window, lambda row: row.sale_at)
        current_orders = _filter_by_window(orders, window, lambda row: row.order_at)
        previous_orders = _filter_previous_window(orders, window, lambda row: row.order_at)
        current_payments = _filter_by_window(payments, window, lambda row: row.paid_at)
        previous_payments = _filter_previous_window(payments, window, lambda row: row.paid_at)
        current_financial_operations = _filter_by_window(
            financial_operations,
            window,
            lambda row: row.operation_date or row.operation_at,
        )
        previous_financial_operations = _filter_previous_window(
            financial_operations,
            window,
            lambda row: row.operation_date or row.operation_at,
        )
        current_customer_returns = _filter_by_window(customer_returns, window, lambda row: row.return_at)
        previous_customer_returns = _filter_previous_window(
            customer_returns,
            window,
            lambda row: row.return_at,
        )
        current_visits = _filter_by_window(visits, window, lambda row: row.visited_at or row.visit_date)
        previous_visits = _filter_previous_window(
            visits,
            window,
            lambda row: row.visited_at or row.visit_date,
        )
        current_inventory_balances = _filter_by_window(
            inventory_balances,
            window,
            lambda row: row.snapshot_date,
        )
        previous_inventory_balances = _filter_previous_window(
            inventory_balances,
            window,
            lambda row: row.snapshot_date,
        )

        current_sale_ids = {row.id for row in current_sales}
        previous_sale_ids = {row.id for row in previous_sales}
        current_sale_items = [row for row in sale_items if row.sale_id in current_sale_ids]
        previous_sale_items = [row for row in sale_items if row.sale_id in previous_sale_ids]

        return _PreparedContext(
            query=query,
            window=window,
            organization_ids=selected_ids,
            organizations=organizations,
            sales=sales,
            sale_items=sale_items,
            orders=orders,
            customers=customers,
            products=products,
            product_categories=product_categories,
            inventory_balances=inventory_balances,
            payments=payments,
            financial_operations=financial_operations,
            customer_returns=customer_returns,
            visits=visits,
            sales_reps=sales_reps,
            working_zones=working_zones,
            warehouses=warehouses,
            current_sales=current_sales,
            previous_sales=previous_sales,
            current_sale_items=current_sale_items,
            previous_sale_items=previous_sale_items,
            current_orders=current_orders,
            previous_orders=previous_orders,
            current_payments=current_payments,
            previous_payments=previous_payments,
            current_financial_operations=current_financial_operations,
            previous_financial_operations=previous_financial_operations,
            current_customer_returns=current_customer_returns,
            previous_customer_returns=previous_customer_returns,
            current_visits=current_visits,
            previous_visits=previous_visits,
            current_inventory_balances=current_inventory_balances,
            previous_inventory_balances=previous_inventory_balances,
        )

    def _build_business_summary(self, prepared: _PreparedContext) -> AnalyticsBusinessSummary:
        revenue = self._sales_revenue_metric(prepared)
        orders = self._orders_metric(prepared)
        realised_sales = self._realised_sales_metric(prepared)
        sold_units = self._sold_units_metric(prepared)
        unique_customers = self._unique_customers_metric(prepared)
        unique_products = self._products_sold_metric(prepared)
        payments_received = self._payments_received_metric(prepared)
        customer_return_value = self._returns_metric(prepared)
        current_stock = self._inventory_quantity_metric(prepared)
        visits = self._visits_count_metric(prepared)
        cash_in = self._cash_in_metric(prepared)
        cash_out = self._cash_out_metric(prepared)
        return AnalyticsBusinessSummary(
            revenue=revenue,
            orders=orders,
            realised_sales=realised_sales,
            sold_units=sold_units,
            average_order=self._average_order_metric(revenue, orders, prepared.window),
            unique_customers=unique_customers,
            unique_products=unique_products,
            payments_received=payments_received,
            customer_return_value=customer_return_value,
            current_stock=current_stock,
            visits=visits,
            verified_cash_in=cash_in,
            verified_cash_out=cash_out,
            returns=customer_return_value,
            expenses=self._expenses_metric(prepared),
            cash_flow=self._net_cash_flow_metric(cash_in, cash_out, prepared.window),
            customers=unique_customers,
        )

    def _build_data_quality(self, prepared: _PreparedContext) -> AnalyticsDataQualityReport:
        items = [
            self._quality_entry("sales", prepared.current_sales),
            self._quality_entry("sale_items", prepared.current_sale_items),
            self._quality_entry("orders", prepared.current_orders),
            self._quality_entry("payments", prepared.current_payments),
            self._quality_entry("returns", prepared.current_customer_returns),
            self._quality_entry("visits", prepared.current_visits),
            self._quality_entry("inventory", prepared.current_inventory_balances),
            self._quality_entry("financial_operations", prepared.current_financial_operations),
        ]
        return AnalyticsDataQualityReport(
            overall_status=_overall_data_status([item.data_status for item in items]),
            items=items,
            notes=self._build_validation_notes(prepared),
        )

    def _build_validation_notes(self, prepared: _PreparedContext) -> list[str]:
        notes = ["Canonical V2 analytics uses only canonical business entities."]
        if not any(_is_verified_realised_sale(row) for row in prepared.current_sales):
            notes.append("Revenue uses only verified realised canonical sales.")
        if not any(_is_verified_outflow(row) for row in prepared.current_financial_operations):
            notes.append("Verified cash out is unavailable in current canonical financial operations.")
        if prepared.window.previous_start is None or prepared.window.previous_end is None:
            notes.append("Comparison period is unavailable for the selected preset.")
        return notes

    def _build_organization_items(self, prepared: _PreparedContext) -> list[AnalyticsOrganizationItem]:
        rows: list[AnalyticsOrganizationItem] = []
        for organization in sorted(prepared.organizations, key=lambda item: item.sort_order):
            scoped = self._scoped_prepared_context(prepared, organization.organization_id)
            metrics = self._build_business_summary(scoped)
            rows.append(
                AnalyticsOrganizationItem(
                    organization_id=organization.organization_id,
                    organization_name=organization.name,
                    metrics=metrics,
                    comparison={
                        "revenue_change": _delta_metric(metrics.revenue),
                        "orders_change": _delta_metric(metrics.orders),
                        "sold_units_change": _delta_metric(metrics.sold_units),
                    },
                    products_sold=metrics.unique_products,
                    sales_reps=self._sales_rep_count_metric(scoped),
                    visits=metrics.visits,
                    stock=metrics.current_stock,
                    data_status=_worst_status(
                        [
                            metrics.revenue.data_status,
                            metrics.orders.data_status,
                            metrics.sold_units.data_status,
                        ]
                    ),
                )
            )
        return rows

    def _scoped_prepared_context(
        self,
        prepared: _PreparedContext,
        organization_id: UUID,
    ) -> _PreparedContext:
        selected_set = {organization_id}
        organizations = [row for row in prepared.organizations if row.organization_id == organization_id]
        return _PreparedContext(
            query=AnalyticsQuery(
                organization_id=organization_id,
                organization_ids=[organization_id],
                date_from=prepared.query.date_from,
                date_to=prepared.query.date_to,
                period=prepared.query.period,
                comparison_mode=prepared.query.comparison_mode,
            ),
            window=prepared.window,
            organization_ids=[organization_id],
            organizations=organizations,
            sales=[row for row in prepared.sales if row.organization_id in selected_set],
            sale_items=[row for row in prepared.sale_items if row.organization_id in selected_set],
            orders=[row for row in prepared.orders if row.organization_id in selected_set],
            customers=[row for row in prepared.customers if row.organization_id in selected_set],
            products=[row for row in prepared.products if row.organization_id in selected_set],
            product_categories=[
                row for row in prepared.product_categories if row.organization_id in selected_set
            ],
            inventory_balances=[
                row for row in prepared.inventory_balances if row.organization_id in selected_set
            ],
            payments=[row for row in prepared.payments if row.organization_id in selected_set],
            financial_operations=[
                row for row in prepared.financial_operations if row.organization_id in selected_set
            ],
            customer_returns=[
                row for row in prepared.customer_returns if row.organization_id in selected_set
            ],
            visits=[row for row in prepared.visits if row.organization_id in selected_set],
            sales_reps=[row for row in prepared.sales_reps if row.organization_id in selected_set],
            working_zones=[row for row in prepared.working_zones if row.organization_id in selected_set],
            warehouses=[row for row in prepared.warehouses if row.organization_id in selected_set],
            current_sales=[row for row in prepared.current_sales if row.organization_id in selected_set],
            previous_sales=[row for row in prepared.previous_sales if row.organization_id in selected_set],
            current_sale_items=[
                row for row in prepared.current_sale_items if row.organization_id in selected_set
            ],
            previous_sale_items=[
                row for row in prepared.previous_sale_items if row.organization_id in selected_set
            ],
            current_orders=[row for row in prepared.current_orders if row.organization_id in selected_set],
            previous_orders=[row for row in prepared.previous_orders if row.organization_id in selected_set],
            current_payments=[
                row for row in prepared.current_payments if row.organization_id in selected_set
            ],
            previous_payments=[
                row for row in prepared.previous_payments if row.organization_id in selected_set
            ],
            current_financial_operations=[
                row
                for row in prepared.current_financial_operations
                if row.organization_id in selected_set
            ],
            previous_financial_operations=[
                row
                for row in prepared.previous_financial_operations
                if row.organization_id in selected_set
            ],
            current_customer_returns=[
                row for row in prepared.current_customer_returns if row.organization_id in selected_set
            ],
            previous_customer_returns=[
                row for row in prepared.previous_customer_returns if row.organization_id in selected_set
            ],
            current_visits=[row for row in prepared.current_visits if row.organization_id in selected_set],
            previous_visits=[
                row for row in prepared.previous_visits if row.organization_id in selected_set
            ],
            current_inventory_balances=[
                row
                for row in prepared.current_inventory_balances
                if row.organization_id in selected_set
            ],
            previous_inventory_balances=[
                row
                for row in prepared.previous_inventory_balances
                if row.organization_id in selected_set
            ],
        )

    def _build_product_items(self, prepared: _PreparedContext) -> list[AnalyticsProductItem]:
        category_lookup = {row.id: row for row in prepared.product_categories}
        current_items_by_product = _group_by(prepared.current_sale_items, lambda row: row.product_id)
        previous_items_by_product = _group_by(prepared.previous_sale_items, lambda row: row.product_id)
        current_stock_by_product = _group_by(
            prepared.current_inventory_balances,
            lambda row: row.product_id,
        )
        previous_stock_by_product = _group_by(
            prepared.previous_inventory_balances,
            lambda row: row.product_id,
        )
        rows: list[AnalyticsProductItem] = []
        for product in prepared.products:
            current_items = current_items_by_product.get(product.id, [])
            previous_items = previous_items_by_product.get(product.id, [])
            current_units = sum((row.sold_quantity for row in current_items), Decimal("0"))
            previous_units = sum((row.sold_quantity for row in previous_items), Decimal("0"))
            current_revenue = sum((row.amount for row in current_items), Decimal("0"))
            previous_revenue = sum((row.amount for row in previous_items), Decimal("0"))
            current_orders = len({row.sale_id for row in current_items if row.sale_id is not None})
            previous_orders = len({row.sale_id for row in previous_items if row.sale_id is not None})
            current_customers = {
                sale.customer_id
                for sale in prepared.current_sales
                if sale.id in {item.sale_id for item in current_items if item.sale_id is not None}
                and sale.customer_id is not None
            }
            stock_rows = current_stock_by_product.get(product.id, [])
            previous_stock_rows = previous_stock_by_product.get(product.id, [])
            current_stock = sum((row.quantity for row in stock_rows), Decimal("0"))
            previous_stock = sum((row.quantity for row in previous_stock_rows), Decimal("0"))
            stock_value = sum(
                (row.valuation_amount or Decimal("0") for row in stock_rows),
                Decimal("0"),
            )
            avg_price = (current_revenue / current_units) if current_units > 0 else None
            velocity_30 = (current_units / Decimal("30")) if current_units > 0 else None
            velocity_7 = (current_units / Decimal("7")) if current_units > 0 else None
            days_of_stock = (current_stock / velocity_30) if velocity_30 and velocity_30 > 0 else None
            classification, tags, stockout_risk = self._classify_product(
                current_stock,
                days_of_stock,
                current_revenue,
                previous_revenue,
            )
            category_name = None
            primary_group_id = product.metadata.get("primary_group_id")
            if primary_group_id is not None:
                category = category_lookup.get(primary_group_id)
                category_name = category.name if category is not None else None
            rows.append(
                AnalyticsProductItem(
                    product_id=product.id,
                    product_external_id=product.source_external_id,
                    product_name=product.name,
                    organization_id=product.organization_id,
                    organization_name=self._organization_name(prepared, product.organization_id),
                    sold_units=_metric(
                        current_units,
                        previous_units,
                        unit="units",
                        source_count=len(current_items),
                        previous_source_count=len(previous_items),
                        status=_status_from_quality_rows(
                            current_items,
                            none_status=AnalyticsDataStatus.NO_VERIFIED_DATA,
                        ),
                        period=prepared.window,
                    ),
                    revenue=_metric(
                        current_revenue,
                        previous_revenue,
                        unit="money",
                        source_count=len(current_items),
                        previous_source_count=len(previous_items),
                        status=_status_from_quality_rows(
                            current_items,
                            none_status=AnalyticsDataStatus.NO_VERIFIED_DATA,
                        ),
                        currency="UZS",
                        period=prepared.window,
                    ),
                    orders_count=_metric(
                        Decimal(current_orders),
                        Decimal(previous_orders),
                        unit="count",
                        source_count=current_orders,
                        previous_source_count=previous_orders,
                        status=AnalyticsDataStatus.AVAILABLE if current_orders else AnalyticsDataStatus.NO_DATA,
                        period=prepared.window,
                    ),
                    customers_count=_metric(
                        Decimal(len(current_customers)),
                        None,
                        unit="count",
                        source_count=len(current_customers),
                        status=AnalyticsDataStatus.AVAILABLE if current_customers else AnalyticsDataStatus.NO_DATA,
                        period=prepared.window,
                    ),
                    average_selling_price=_metric(
                        avg_price,
                        None,
                        unit="money",
                        source_count=len(current_items),
                        status=AnalyticsDataStatus.AVAILABLE if avg_price is not None else AnalyticsDataStatus.NO_DATA,
                        currency="UZS",
                        period=prepared.window,
                    ),
                    returns_quantity=_metric(
                        Decimal("0"),
                        None,
                        unit="units",
                        source_count=0,
                        status=AnalyticsDataStatus.NO_DATA,
                        period=prepared.window,
                    ),
                    returns_amount=_metric(
                        Decimal("0"),
                        None,
                        unit="money",
                        source_count=0,
                        status=AnalyticsDataStatus.NO_DATA,
                        currency="UZS",
                        period=prepared.window,
                    ),
                    return_rate=_metric(
                        None,
                        None,
                        unit="percent",
                        source_count=0,
                        status=AnalyticsDataStatus.NO_DATA,
                        period=prepared.window,
                    ),
                    current_stock=_metric(
                        current_stock,
                        previous_stock,
                        unit="units",
                        source_count=len(stock_rows),
                        previous_source_count=len(previous_stock_rows),
                        status=_status_from_quality_rows(stock_rows),
                        period=prepared.window,
                    ),
                    stock_value=_metric(
                        stock_value,
                        None,
                        unit="money",
                        source_count=len(stock_rows),
                        status=_status_from_quality_rows(stock_rows),
                        currency="UZS",
                        period=prepared.window,
                    ),
                    sales_velocity_7d=_metric(
                        velocity_7,
                        None,
                        unit="units_per_day",
                        source_count=len(current_items),
                        status=AnalyticsDataStatus.AVAILABLE if velocity_7 is not None else AnalyticsDataStatus.NO_DATA,
                        period=prepared.window,
                    ),
                    sales_velocity_30d=_metric(
                        velocity_30,
                        None,
                        unit="units_per_day",
                        source_count=len(current_items),
                        status=AnalyticsDataStatus.AVAILABLE if velocity_30 is not None else AnalyticsDataStatus.NO_DATA,
                        period=prepared.window,
                    ),
                    days_of_stock=_metric(
                        days_of_stock,
                        None,
                        unit="days",
                        source_count=len(stock_rows),
                        status=AnalyticsDataStatus.AVAILABLE if days_of_stock is not None else AnalyticsDataStatus.NO_DATA,
                        period=prepared.window,
                    ),
                    first_sale_date=min(
                        (
                            sale.sale_at
                            for sale in prepared.sales
                            if sale.customer_id is not None
                            and sale.id in {item.sale_id for item in current_items if item.sale_id is not None}
                            and sale.sale_at is not None
                        ),
                        default=None,
                    ),
                    last_sale_date=max(
                        (
                            sale.sale_at
                            for sale in prepared.sales
                            if sale.id in {item.sale_id for item in current_items if item.sale_id is not None}
                            and sale.sale_at is not None
                        ),
                        default=None,
                    ),
                    sales_change_pct=_percent_change_metric(
                        Decimal(current_orders),
                        Decimal(previous_orders),
                        prepared.window,
                    ),
                    units_change_pct=_percent_change_metric(current_units, previous_units, prepared.window),
                    revenue_change_pct=_percent_change_metric(
                        current_revenue,
                        previous_revenue,
                        prepared.window,
                    ),
                    classification=classification,
                    classification_tags=tags + ([category_name] if category_name else []),
                    stockout_risk=stockout_risk,
                    data_status=_worst_status(
                        [
                            _status_from_quality_rows(current_items),
                            _status_from_quality_rows(stock_rows),
                        ]
                    ),
                )
            )
        rows.sort(key=lambda item: item.revenue.value or Decimal("0"), reverse=True)
        return rows

    def _build_customer_items(self, prepared: _PreparedContext) -> list[AnalyticsCustomerItem]:
        current_sales_by_customer = _group_by(prepared.current_sales, lambda row: row.customer_id)
        previous_sales_by_customer = _group_by(prepared.previous_sales, lambda row: row.customer_id)
        current_visits_by_customer = _group_by(prepared.current_visits, lambda row: row.customer_id)
        current_returns_by_customer = _group_by(
            prepared.current_customer_returns,
            lambda row: row.customer_id,
        )
        rows: list[AnalyticsCustomerItem] = []
        for customer in prepared.customers:
            current_sales = current_sales_by_customer.get(customer.id, [])
            previous_sales = previous_sales_by_customer.get(customer.id, [])
            current_sale_ids = {row.id for row in current_sales}
            current_items = [row for row in prepared.current_sale_items if row.sale_id in current_sale_ids]
            revenue = sum((row.total_amount for row in current_sales), Decimal("0"))
            previous_revenue = sum((row.total_amount for row in previous_sales), Decimal("0"))
            sold_units = sum((row.sold_quantity for row in current_items), Decimal("0"))
            visits = current_visits_by_customer.get(customer.id, [])
            customer_returns = current_returns_by_customer.get(customer.id, [])
            returns_amount = sum((row.total_amount for row in customer_returns), Decimal("0"))
            last_order = max(
                (row.sale_at for row in prepared.sales if row.customer_id == customer.id and row.sale_at is not None),
                default=None,
            )
            first_order = min(
                (row.sale_at for row in prepared.sales if row.customer_id == customer.id and row.sale_at is not None),
                default=None,
            )
            days_since_last_order = None
            if last_order is not None:
                days_since_last_order = Decimal((datetime.now(UTC) - last_order).days)
            segment = self._classify_customer_segment(days_since_last_order)
            organization_ids = sorted(
                {
                    row.organization_id
                    for row in prepared.sales
                    if row.customer_id == customer.id
                }
            )
            rows.append(
                AnalyticsCustomerItem(
                    customer_external_id=customer.source_external_id,
                    customer_name=customer.name,
                    organization_ids=organization_ids,
                    orders_count=_metric(
                        Decimal(len(current_sales)),
                        Decimal(len(previous_sales)),
                        unit="count",
                        source_count=len(current_sales),
                        previous_source_count=len(previous_sales),
                        status=_status_from_quality_rows(current_sales),
                        period=prepared.window,
                    ),
                    revenue=_metric(
                        revenue,
                        previous_revenue,
                        unit="money",
                        source_count=len(current_sales),
                        previous_source_count=len(previous_sales),
                        status=_status_from_quality_rows(
                            current_sales,
                            none_status=AnalyticsDataStatus.NO_VERIFIED_DATA,
                        ),
                        currency="UZS",
                        period=prepared.window,
                    ),
                    sold_units=_metric(
                        sold_units,
                        None,
                        unit="units",
                        source_count=len(current_items),
                        status=_status_from_quality_rows(current_items),
                        period=prepared.window,
                    ),
                    average_order_value=_metric(
                        (revenue / Decimal(len(current_sales))) if current_sales else None,
                        None,
                        unit="money",
                        source_count=len(current_sales),
                        status=AnalyticsDataStatus.AVAILABLE if current_sales else AnalyticsDataStatus.NO_DATA,
                        currency="UZS",
                        period=prepared.window,
                    ),
                    first_order_date=first_order,
                    last_order_date=last_order,
                    days_since_last_order=_metric(
                        days_since_last_order,
                        None,
                        unit="days",
                        source_count=1 if last_order else 0,
                        status=AnalyticsDataStatus.AVAILABLE if days_since_last_order is not None else AnalyticsDataStatus.NO_DATA,
                        period=prepared.window,
                    ),
                    purchase_frequency=_metric(
                        _frequency_metric_value(prepared.window, len(current_sales)),
                        None,
                        unit="orders_per_day",
                        source_count=len(current_sales),
                        status=AnalyticsDataStatus.AVAILABLE if current_sales else AnalyticsDataStatus.NO_DATA,
                        period=prepared.window,
                    ),
                    returns_count=_metric(
                        Decimal(len(customer_returns)),
                        None,
                        unit="count",
                        source_count=len(customer_returns),
                        status=_status_from_quality_rows(customer_returns),
                        period=prepared.window,
                    ),
                    returns_amount=_metric(
                        returns_amount,
                        None,
                        unit="money",
                        source_count=len(customer_returns),
                        status=_status_from_quality_rows(customer_returns),
                        currency="UZS",
                        period=prepared.window,
                    ),
                    visits_count=_metric(
                        Decimal(len(visits)),
                        None,
                        unit="count",
                        source_count=len(visits),
                        status=_status_from_quality_rows(visits),
                        period=prepared.window,
                    ),
                    products_count=_metric(
                        Decimal(
                            len(
                                {
                                    row.product_id
                                    for row in current_items
                                    if row.product_id is not None
                                }
                            )
                        ),
                        None,
                        unit="count",
                        source_count=len(current_items),
                        status=_status_from_quality_rows(current_items),
                        period=prepared.window,
                    ),
                    organizations_count=_metric(
                        Decimal(len(organization_ids)),
                        None,
                        unit="count",
                        source_count=len(organization_ids),
                        status=AnalyticsDataStatus.AVAILABLE if organization_ids else AnalyticsDataStatus.NO_DATA,
                        period=prepared.window,
                    ),
                    segment=segment,
                    customer_value_score=_metric(
                        revenue + sold_units,
                        None,
                        unit="score",
                        source_count=len(current_sales),
                        status=_status_from_quality_rows(current_sales),
                        period=prepared.window,
                    ),
                    data_status=_worst_status(
                        [
                            _status_from_quality_rows(current_sales),
                            _status_from_quality_rows(visits),
                        ]
                    ),
                )
            )
        rows.sort(key=lambda item: item.revenue.value or Decimal("0"), reverse=True)
        return rows

    def _build_sales_rep_items(self, prepared: _PreparedContext) -> list[AnalyticsSalesRepItem]:
        sales_by_rep = _group_by(prepared.current_sales, lambda row: row.sales_rep_id)
        visits_by_rep = _group_by(prepared.current_visits, lambda row: row.sales_rep_id)
        rows: list[AnalyticsSalesRepItem] = []
        for rep in prepared.sales_reps:
            sales = sales_by_rep.get(rep.id, [])
            visits = visits_by_rep.get(rep.id, [])
            sale_ids = {row.id for row in sales}
            sale_items = [row for row in prepared.current_sale_items if row.sale_id in sale_ids]
            revenue = sum((row.total_amount for row in sales), Decimal("0"))
            sold_units = sum((row.sold_quantity for row in sale_items), Decimal("0"))
            completed_visits = [
                row for row in visits if row.normalized_status in {"completed", "approved"}
            ]
            rows.append(
                AnalyticsSalesRepItem(
                    sales_rep_key=rep.source_external_id,
                    sales_rep_name=rep.sales_manager_name or rep.sales_manager_code or rep.source_external_id,
                    revenue=_metric(
                        revenue,
                        None,
                        unit="money",
                        source_count=len(sales),
                        status=_status_from_quality_rows(sales),
                        currency="UZS",
                        period=prepared.window,
                    ),
                    orders=_metric(
                        Decimal(len(sales)),
                        None,
                        unit="count",
                        source_count=len(sales),
                        status=_status_from_quality_rows(sales),
                        period=prepared.window,
                    ),
                    sold_units=_metric(
                        sold_units,
                        None,
                        unit="units",
                        source_count=len(sale_items),
                        status=_status_from_quality_rows(sale_items),
                        period=prepared.window,
                    ),
                    customers=_metric(
                        Decimal(len({row.customer_id for row in sales if row.customer_id is not None})),
                        None,
                        unit="count",
                        source_count=len(sales),
                        status=_status_from_quality_rows(sales),
                        period=prepared.window,
                    ),
                    new_customers=_metric(
                        None,
                        None,
                        unit="count",
                        source_count=0,
                        status=AnalyticsDataStatus.NOT_AVAILABLE,
                        period=prepared.window,
                    ),
                    average_order=_metric(
                        (revenue / Decimal(len(sales))) if sales else None,
                        None,
                        unit="money",
                        source_count=len(sales),
                        status=AnalyticsDataStatus.AVAILABLE if sales else AnalyticsDataStatus.NO_DATA,
                        currency="UZS",
                        period=prepared.window,
                    ),
                    returns=_metric(
                        None,
                        None,
                        unit="money",
                        source_count=0,
                        status=AnalyticsDataStatus.NOT_AVAILABLE,
                        currency="UZS",
                        period=prepared.window,
                    ),
                    visits=_metric(
                        Decimal(len(visits)),
                        None,
                        unit="count",
                        source_count=len(visits),
                        status=_status_from_quality_rows(visits),
                        period=prepared.window,
                    ),
                    completed_visits=_metric(
                        Decimal(len(completed_visits)),
                        None,
                        unit="count",
                        source_count=len(completed_visits),
                        status=_status_from_quality_rows(completed_visits),
                        period=prepared.window,
                    ),
                    orders_after_visit=_metric(
                        Decimal(len(sales)),
                        None,
                        unit="count",
                        source_count=len(sales),
                        status=_status_from_quality_rows(sales),
                        period=prepared.window,
                    ),
                    visit_conversion=_metric(
                        _safe_percent(Decimal(len(sales)), Decimal(len(completed_visits)))
                        if completed_visits
                        else None,
                        None,
                        unit="percent",
                        source_count=len(visits),
                        status=AnalyticsDataStatus.AVAILABLE if completed_visits else AnalyticsDataStatus.NO_DATA,
                        period=prepared.window,
                    ),
                    revenue_after_visits=_metric(
                        revenue,
                        None,
                        unit="money",
                        source_count=len(sales),
                        status=_status_from_quality_rows(sales),
                        currency="UZS",
                        period=prepared.window,
                    ),
                    data_status=_worst_status(
                        [_status_from_quality_rows(sales), _status_from_quality_rows(visits)]
                    ),
                )
            )
        rows.sort(key=lambda item: item.revenue.value or Decimal("0"), reverse=True)
        return rows

    def _build_visit_items(self, prepared: _PreparedContext) -> list[AnalyticsVisitItem]:
        rows: list[AnalyticsVisitItem] = []
        for organization in prepared.organizations:
            visits = [row for row in prepared.current_visits if row.organization_id == organization.organization_id]
            completed = [row for row in visits if row.normalized_status in {"completed", "approved"}]
            planned = [row for row in visits if row.is_planned is True]
            unplanned = [row for row in visits if row.is_planned is False]
            unique_customers = {row.customer_id for row in visits if row.customer_id is not None}
            durations = [
                Decimal(row.duration_seconds or row.derived_duration_seconds or 0)
                for row in visits
                if (row.duration_seconds or row.derived_duration_seconds) is not None
            ]
            avg_duration = (sum(durations, Decimal("0")) / Decimal(len(durations))) if durations else None
            rows.append(
                AnalyticsVisitItem(
                    organization_id=organization.organization_id,
                    organization_name=organization.name,
                    visits_count=_metric(
                        Decimal(len(visits)),
                        None,
                        unit="count",
                        source_count=len(visits),
                        status=_status_from_quality_rows(visits),
                        period=prepared.window,
                    ),
                    completed_visits=_metric(
                        Decimal(len(completed)),
                        None,
                        unit="count",
                        source_count=len(completed)),
                    planned_visits=_metric(
                        Decimal(len(planned)),
                        None,
                        unit="count",
                        source_count=len(planned),
                        status=_status_from_quality_rows(planned),
                        period=prepared.window,
                    ),
                    unplanned_visits=_metric(
                        Decimal(len(unplanned)),
                        None,
                        unit="count",
                        source_count=len(unplanned),
                        status=_status_from_quality_rows(unplanned),
                        period=prepared.window,
                    ),
                    unique_customers=_metric(
                        Decimal(len(unique_customers)),
                        None,
                        unit="count",
                        source_count=len(unique_customers),
                        status=AnalyticsDataStatus.AVAILABLE if unique_customers else AnalyticsDataStatus.NO_DATA,
                        period=prepared.window,
                    ),
                    average_duration=_metric(
                        avg_duration,
                        None,
                        unit="seconds",
                        source_count=len(durations),
                        status=AnalyticsDataStatus.AVAILABLE if avg_duration is not None else AnalyticsDataStatus.NO_DATA,
                        period=prepared.window,
                    ),
                    data_status=_status_from_quality_rows(visits),
                )
            )
        return rows

    def _build_finance_items(self, prepared: _PreparedContext) -> list[AnalyticsFinanceItem]:
        cash_in = self._cash_in_metric(prepared)
        cash_out = self._cash_out_metric(prepared)
        return [
            AnalyticsFinanceItem(metric_key="sales_revenue", label="Sales Revenue", value=self._sales_revenue_metric(prepared)),
            AnalyticsFinanceItem(metric_key="payments_received", label="Payments Received", value=self._payments_received_metric(prepared)),
            AnalyticsFinanceItem(metric_key="cash_in", label="Cash In", value=cash_in),
            AnalyticsFinanceItem(metric_key="cash_out", label="Cash Out", value=cash_out),
            AnalyticsFinanceItem(metric_key="expenses", label="Expenses", value=self._expenses_metric(prepared)),
            AnalyticsFinanceItem(metric_key="net_cash_flow", label="Net Cash Flow", value=self._net_cash_flow_metric(cash_in, cash_out, prepared.window)),
        ]

    def _build_return_items(self, prepared: _PreparedContext) -> list[AnalyticsReturnItem]:
        rows: list[AnalyticsReturnItem] = []
        for organization in prepared.organizations:
            returns = [row for row in prepared.current_customer_returns if row.organization_id == organization.organization_id]
            amount = sum((row.total_amount for row in returns), Decimal("0"))
            quantity = sum((row.returned_quantity for row in returns), Decimal("0"))
            revenue = sum(
                (row.total_amount for row in prepared.current_sales if row.organization_id == organization.organization_id),
                Decimal("0"),
            )
            rows.append(
                AnalyticsReturnItem(
                    return_key=str(organization.organization_id),
                    label=organization.name,
                    amount=_metric(
                        amount,
                        None,
                        unit="money",
                        source_count=len(returns),
                        status=_status_from_quality_rows(returns),
                        currency="UZS",
                        period=prepared.window,
                    ),
                    quantity=_metric(
                        quantity,
                        None,
                        unit="units",
                        source_count=len(returns),
                        status=_status_from_quality_rows(returns),
                        period=prepared.window,
                    ),
                    rate=_metric(
                        _safe_percent(amount, revenue) if revenue else None,
                        None,
                        unit="percent",
                        source_count=len(returns),
                        status=AnalyticsDataStatus.AVAILABLE if revenue and returns else AnalyticsDataStatus.NO_DATA,
                        period=prepared.window,
                    ),
                    data_status=_status_from_quality_rows(returns),
                )
            )
        return rows

    def _build_inventory_opportunities(
        self,
        prepared: _PreparedContext,
    ) -> list[AnalyticsInventoryTransferOpportunity]:
        by_product_org: dict[tuple[UUID, UUID], Decimal] = defaultdict(lambda: Decimal("0"))
        for row in prepared.current_inventory_balances:
            if row.product_id is None:
                continue
            by_product_org[(row.product_id, row.organization_id)] += row.quantity

        product_names = {row.id: row.name for row in prepared.products}
        rows_by_product: dict[UUID, list[tuple[UUID, Decimal]]] = defaultdict(list)
        for (product_id, organization_id), quantity in by_product_org.items():
            rows_by_product[product_id].append((organization_id, quantity))

        results: list[AnalyticsInventoryTransferOpportunity] = []
        for product_id, items in rows_by_product.items():
            if len(items) < 2:
                continue
            from_org, from_qty = max(items, key=lambda row: row[1])
            to_org, to_qty = min(items, key=lambda row: row[1])
            if from_qty <= to_qty:
                continue
            results.append(
                AnalyticsInventoryTransferOpportunity(
                    product_external_id=str(product_id),
                    product_name=product_names.get(product_id, str(product_id)),
                    from_organization_id=from_org,
                    from_organization_name=self._organization_name(prepared, from_org),
                    to_organization_id=to_org,
                    to_organization_name=self._organization_name(prepared, to_org),
                    source_stock=_metric(
                        from_qty,
                        None,
                        unit="units",
                        source_count=1,
                        status=AnalyticsDataStatus.AVAILABLE,
                        period=prepared.window,
                    ),
                    destination_stock=_metric(
                        to_qty,
                        None,
                        unit="units",
                        source_count=1,
                        status=AnalyticsDataStatus.AVAILABLE,
                        period=prepared.window,
                    ),
                    source_days=_metric(
                        None,
                        None,
                        unit="days",
                        source_count=0,
                        status=AnalyticsDataStatus.UNRESOLVED,
                        period=prepared.window,
                        note="Velocity-based source days not materialized yet.",
                    ),
                    destination_days=_metric(
                        None,
                        None,
                        unit="days",
                        source_count=0,
                        status=AnalyticsDataStatus.UNRESOLVED,
                        period=prepared.window,
                        note="Velocity-based destination days not materialized yet.",
                    ),
                    source_velocity=_metric(
                        None,
                        None,
                        unit="units_per_day",
                        source_count=0,
                        status=AnalyticsDataStatus.UNRESOLVED,
                        period=prepared.window,
                    ),
                    destination_velocity=_metric(
                        None,
                        None,
                        unit="units_per_day",
                        source_count=0,
                        status=AnalyticsDataStatus.UNRESOLVED,
                        period=prepared.window,
                    ),
                    reason="Cross-organization stock imbalance detected from current inventory snapshots.",
                )
            )
        return results

    def _sales_revenue_metric(self, prepared: _PreparedContext) -> AnalyticsMetricValue:
        current = [row for row in prepared.current_sales if _is_verified_realised_sale(row)]
        previous = [row for row in prepared.previous_sales if _is_verified_realised_sale(row)]
        return _metric(
            sum((row.total_amount for row in current), Decimal("0")),
            sum((row.total_amount for row in previous), Decimal("0")),
            unit="money",
            source_count=len(current),
            previous_source_count=len(previous),
            status=_status_from_quality_rows(current, none_status=AnalyticsDataStatus.NO_VERIFIED_DATA),
            currency="UZS",
            period=prepared.window,
            supported_dimensions=["organization", "date", "customer", "product", "category", "sales_rep", "working_zone"],
            drilldown=["sales"],
            note="Verified realised canonical sales only.",
        )

    def _orders_metric(self, prepared: _PreparedContext) -> AnalyticsMetricValue:
        return _metric(
            Decimal(len(prepared.current_orders)),
            Decimal(len(prepared.previous_orders)),
            unit="count",
            source_count=len(prepared.current_orders),
            previous_source_count=len(prepared.previous_orders),
            status=_status_from_quality_rows(prepared.current_orders),
            period=prepared.window,
            supported_dimensions=["organization", "date", "customer", "sales_rep", "working_zone", "normalized_status"],
            drilldown=["sales"],
        )

    def _realised_sales_metric(self, prepared: _PreparedContext) -> AnalyticsMetricValue:
        current = [row for row in prepared.current_sales if _is_verified_realised_sale(row)]
        previous = [row for row in prepared.previous_sales if _is_verified_realised_sale(row)]
        return _metric(
            Decimal(len(current)),
            Decimal(len(previous)),
            unit="count",
            source_count=len(current),
            previous_source_count=len(previous),
            status=_status_from_quality_rows(current, none_status=AnalyticsDataStatus.NO_VERIFIED_DATA),
            period=prepared.window,
            supported_dimensions=["organization", "date", "customer", "sales_rep", "working_zone"],
            drilldown=["sales"],
            note="Verified realised canonical sales only.",
        )

    def _sold_units_metric(self, prepared: _PreparedContext) -> AnalyticsMetricValue:
        current = [row for row in prepared.current_sale_items if _is_verified(row)]
        previous = [row for row in prepared.previous_sale_items if _is_verified(row)]
        return _metric(
            sum((row.sold_quantity for row in current), Decimal("0")),
            sum((row.sold_quantity for row in previous), Decimal("0")),
            unit="units",
            source_count=len(current),
            previous_source_count=len(previous),
            status=_status_from_quality_rows(current, none_status=AnalyticsDataStatus.NO_VERIFIED_DATA),
            period=prepared.window,
            supported_dimensions=["organization", "date", "product", "category", "sales_rep", "working_zone"],
            drilldown=["sales"],
        )

    def _average_order_metric(
        self,
        revenue: AnalyticsMetricValue,
        orders: AnalyticsMetricValue,
        period: AnalyticsPeriodWindow,
    ) -> AnalyticsMetricValue:
        current = None
        previous = None
        if revenue.value is not None and orders.value not in {None, Decimal("0")}:
            current = revenue.value / orders.value
        if revenue.previous_value is not None and orders.previous_value not in {None, Decimal("0")}:
            previous = revenue.previous_value / orders.previous_value
        return _metric(
            current,
            previous,
            unit="money",
            source_count=revenue.record_count,
            previous_source_count=orders.record_count,
            status=revenue.data_status if current is not None else AnalyticsDataStatus.NO_DATA,
            currency="UZS",
            period=period,
            supported_dimensions=["organization", "date", "customer", "sales_rep"],
            drilldown=["sales"],
        )

    def _payments_received_metric(self, prepared: _PreparedContext) -> AnalyticsMetricValue:
        current = [
            row
            for row in prepared.current_payments
            if row.data_quality_status in {CanonicalDataQualityStatus.VERIFIED, CanonicalDataQualityStatus.PARTIAL}
        ]
        previous = [
            row
            for row in prepared.previous_payments
            if row.data_quality_status in {CanonicalDataQualityStatus.VERIFIED, CanonicalDataQualityStatus.PARTIAL}
        ]
        return _metric(
            sum((row.amount for row in current), Decimal("0")),
            sum((row.amount for row in previous), Decimal("0")),
            unit="money",
            source_count=len(current),
            previous_source_count=len(previous),
            status=_status_from_quality_rows(current),
            currency="UZS",
            period=prepared.window,
            supported_dimensions=["organization", "date", "customer", "payment_type"],
            drilldown=["finance"],
        )

    def _returns_metric(self, prepared: _PreparedContext) -> AnalyticsMetricValue:
        return _metric(
            sum((row.total_amount for row in prepared.current_customer_returns), Decimal("0")),
            sum((row.total_amount for row in prepared.previous_customer_returns), Decimal("0")),
            unit="money",
            source_count=len(prepared.current_customer_returns),
            previous_source_count=len(prepared.previous_customer_returns),
            status=_status_from_quality_rows(prepared.current_customer_returns),
            currency="UZS",
            period=prepared.window,
            supported_dimensions=["organization", "date", "customer", "sales_rep", "normalized_status"],
            drilldown=["finance"],
        )

    def _expenses_metric(self, prepared: _PreparedContext) -> AnalyticsMetricValue:
        current = [row for row in prepared.current_financial_operations if _is_verified_outflow(row)]
        previous = [row for row in prepared.previous_financial_operations if _is_verified_outflow(row)]
        return _metric(
            sum((row.amount for row in current), Decimal("0")) if current else None,
            sum((row.amount for row in previous), Decimal("0")) if previous else None,
            unit="money",
            source_count=len(current),
            previous_source_count=len(previous),
            status=_status_from_quality_rows(current, none_status=AnalyticsDataStatus.NO_VERIFIED_DATA),
            currency="UZS",
            period=prepared.window,
            supported_dimensions=["organization", "date", "operation_type"],
            drilldown=["finance"],
            note="Verified outflow financial operations only.",
        )

    def _cash_in_metric(self, prepared: _PreparedContext) -> AnalyticsMetricValue:
        current = [row for row in prepared.current_financial_operations if _is_verified_inflow(row)]
        previous = [row for row in prepared.previous_financial_operations if _is_verified_inflow(row)]
        return _metric(
            sum((row.amount for row in current), Decimal("0")) if current else None,
            sum((row.amount for row in previous), Decimal("0")) if previous else None,
            unit="money",
            source_count=len(current),
            previous_source_count=len(previous),
            status=_status_from_quality_rows(current, none_status=AnalyticsDataStatus.NO_VERIFIED_DATA),
            currency="UZS",
            period=prepared.window,
            supported_dimensions=["organization", "date", "operation_type"],
            drilldown=["finance"],
        )

    def _cash_out_metric(self, prepared: _PreparedContext) -> AnalyticsMetricValue:
        return self._expenses_metric(prepared)

    def _net_cash_flow_metric(
        self,
        cash_in: AnalyticsMetricValue,
        cash_out: AnalyticsMetricValue,
        period: AnalyticsPeriodWindow,
    ) -> AnalyticsMetricValue:
        if cash_in.data_status != AnalyticsDataStatus.AVAILABLE or cash_out.data_status != AnalyticsDataStatus.AVAILABLE:
            return _metric(
                None,
                None,
                unit="money",
                source_count=0,
                status=AnalyticsDataStatus.NO_VERIFIED_DATA,
                currency="UZS",
                period=period,
                drilldown=["finance"],
                note="Net cash flow requires verified cash in and verified cash out.",
            )
        previous = None
        if cash_in.previous_value is not None and cash_out.previous_value is not None:
            previous = cash_in.previous_value - cash_out.previous_value
        return _metric(
            (cash_in.value or Decimal("0")) - (cash_out.value or Decimal("0")),
            previous,
            unit="money",
            source_count=cash_in.record_count + cash_out.record_count,
            status=AnalyticsDataStatus.AVAILABLE,
            currency="UZS",
            period=period,
            drilldown=["finance"],
        )

    def _unique_customers_metric(self, prepared: _PreparedContext) -> AnalyticsMetricValue:
        current = {row.customer_id for row in prepared.current_sales if row.customer_id is not None}
        previous = {row.customer_id for row in prepared.previous_sales if row.customer_id is not None}
        return _metric(
            Decimal(len(current)),
            Decimal(len(previous)),
            unit="count",
            source_count=len(current),
            previous_source_count=len(previous),
            status=AnalyticsDataStatus.AVAILABLE if current else AnalyticsDataStatus.NO_DATA,
            period=prepared.window,
        )

    def _products_sold_metric(self, prepared: _PreparedContext) -> AnalyticsMetricValue:
        current = {row.product_id for row in prepared.current_sale_items if row.product_id is not None}
        previous = {row.product_id for row in prepared.previous_sale_items if row.product_id is not None}
        return _metric(
            Decimal(len(current)),
            Decimal(len(previous)),
            unit="count",
            source_count=len(current),
            previous_source_count=len(previous),
            status=AnalyticsDataStatus.AVAILABLE if current else AnalyticsDataStatus.NO_DATA,
            period=prepared.window,
        )

    def _sales_rep_count_metric(self, prepared: _PreparedContext) -> AnalyticsMetricValue:
        current = {row.sales_rep_id for row in prepared.current_sales if row.sales_rep_id is not None}
        return _metric(
            Decimal(len(current)),
            None,
            unit="count",
            source_count=len(current),
            status=AnalyticsDataStatus.AVAILABLE if current else AnalyticsDataStatus.NO_DATA,
            period=prepared.window,
        )

    def _visits_count_metric(self, prepared: _PreparedContext) -> AnalyticsMetricValue:
        return _metric(
            Decimal(len(prepared.current_visits)),
            Decimal(len(prepared.previous_visits)),
            unit="count",
            source_count=len(prepared.current_visits),
            previous_source_count=len(prepared.previous_visits),
            status=_status_from_quality_rows(prepared.current_visits),
            period=prepared.window,
        )

    def _inventory_quantity_metric(self, prepared: _PreparedContext) -> AnalyticsMetricValue:
        current = _latest_inventory_rows(prepared.current_inventory_balances)
        previous = _latest_inventory_rows(prepared.previous_inventory_balances)
        return _metric(
            sum((row.quantity for row in current), Decimal("0")) if current else None,
            sum((row.quantity for row in previous), Decimal("0")) if previous else None,
            unit="units",
            source_count=len(current),
            previous_source_count=len(previous),
            status=_status_from_quality_rows(current, none_status=AnalyticsDataStatus.NO_VERIFIED_DATA),
            period=prepared.window,
        )

    def _financial_metric_by_type(
        self,
        prepared: _PreparedContext,
        normalized_types: set[str],
    ) -> AnalyticsMetricValue:
        current = [
            row
            for row in prepared.current_financial_operations
            if row.normalized_operation_type in normalized_types
        ]
        previous = [
            row
            for row in prepared.previous_financial_operations
            if row.normalized_operation_type in normalized_types
        ]
        return _metric(
            sum((row.amount for row in current), Decimal("0")),
            sum((row.amount for row in previous), Decimal("0")),
            unit="money",
            source_count=len(current),
            previous_source_count=len(previous),
            status=_status_from_quality_rows(current),
            currency="UZS",
            period=prepared.window,
        )

    def _sales_by_date(self, prepared: _PreparedContext) -> list[AnalyticsDimensionRow]:
        rows: dict[str, list[CanonicalSale]] = defaultdict(list)
        for sale in prepared.current_sales:
            if sale.sale_at is not None and _is_verified_realised_sale(sale):
                rows[sale.sale_at.date().isoformat()].append(sale)
        return [
            self._sales_dimension_row("date", key, key, value, prepared.window)
            for key, value in sorted(rows.items())
        ]

    def _sales_by_organization(self, prepared: _PreparedContext) -> list[AnalyticsDimensionRow]:
        rows: dict[UUID, list[CanonicalSale]] = defaultdict(list)
        for sale in prepared.current_sales:
            rows[sale.organization_id].append(sale)
        return [
            self._sales_dimension_row(
                "organization",
                str(key),
                self._organization_name(prepared, key),
                value,
                prepared.window,
            )
            for key, value in rows.items()
        ]

    def _sales_by_customer(self, prepared: _PreparedContext) -> list[AnalyticsDimensionRow]:
        rows: dict[str, list[CanonicalSale]] = defaultdict(list)
        for sale in prepared.current_sales:
            if sale.customer_external_id:
                rows[sale.customer_external_id].append(sale)
        return [
            self._sales_dimension_row("customer", key, key, value, prepared.window)
            for key, value in rows.items()
        ]

    def _sales_by_product(self, prepared: _PreparedContext) -> list[AnalyticsDimensionRow]:
        rows: dict[str, list[CanonicalSaleItem]] = defaultdict(list)
        for item in prepared.current_sale_items:
            if item.product_external_id:
                rows[item.product_external_id].append(item)
        return [
            AnalyticsDimensionRow(
                dimension="product",
                key=key,
                label=key,
                metrics={
                    "sold_units": _metric(
                        sum((row.sold_quantity for row in items), Decimal("0")),
                        None,
                        unit="units",
                        source_count=len(items),
                        status=_status_from_quality_rows(items),
                        period=prepared.window,
                    ),
                    "revenue": _metric(
                        sum((row.amount for row in items), Decimal("0")),
                        None,
                        unit="money",
                        source_count=len(items),
                        status=_status_from_quality_rows(items),
                        currency="UZS",
                        period=prepared.window,
                    ),
                    "returns": _metric(
                        sum((row.returned_quantity for row in items), Decimal("0")),
                        None,
                        unit="units",
                        source_count=len(items),
                        status=_status_from_quality_rows(items),
                        period=prepared.window,
                    ),
                },
                data_status=_status_from_quality_rows(items),
            )
            for key, items in rows.items()
        ]

    def _sales_by_category(self, prepared: _PreparedContext) -> list[AnalyticsDimensionRow]:
        category_by_product = {
            row.id: str(row.metadata.get("primary_group_id") or "uncategorized")
            for row in prepared.products
        }
        rows: dict[str, list[CanonicalSaleItem]] = defaultdict(list)
        for item in prepared.current_sale_items:
            rows[category_by_product.get(item.product_id, "uncategorized")].append(item)
        return [
            AnalyticsDimensionRow(
                dimension="category",
                key=key,
                label=key,
                metrics={
                    "sold_units": _metric(
                        sum((row.sold_quantity for row in items), Decimal("0")),
                        None,
                        unit="units",
                        source_count=len(items),
                        status=_status_from_quality_rows(items),
                        period=prepared.window,
                    ),
                    "revenue": _metric(
                        sum((row.amount for row in items), Decimal("0")),
                        None,
                        unit="money",
                        source_count=len(items),
                        status=_status_from_quality_rows(items),
                        currency="UZS",
                        period=prepared.window,
                    ),
                    "returns": _metric(
                        sum((row.returned_quantity for row in items), Decimal("0")),
                        None,
                        unit="units",
                        source_count=len(items),
                        status=_status_from_quality_rows(items),
                        period=prepared.window,
                    ),
                },
                data_status=_status_from_quality_rows(items),
            )
            for key, items in rows.items()
        ]

    def _sales_by_sales_rep(self, prepared: _PreparedContext) -> list[AnalyticsDimensionRow]:
        rows: dict[str, list[CanonicalSale]] = defaultdict(list)
        for sale in prepared.current_sales:
            rows[sale.sales_rep_external_id or "unassigned"].append(sale)
        return [
            self._sales_dimension_row("sales_rep", key, key, value, prepared.window)
            for key, value in rows.items()
        ]

    def _sales_by_working_zone(self, prepared: _PreparedContext) -> list[AnalyticsDimensionRow]:
        rows: dict[str, list[CanonicalSale]] = defaultdict(list)
        for sale in prepared.current_sales:
            rows[sale.working_zone_external_id or "unassigned"].append(sale)
        return [
            self._sales_dimension_row("working_zone", key, key, value, prepared.window)
            for key, value in rows.items()
        ]

    def _sales_by_payment_type(self, prepared: _PreparedContext) -> list[AnalyticsDimensionRow]:
        rows: dict[str, list[CanonicalPayment]] = defaultdict(list)
        for payment in prepared.current_payments:
            rows[payment.normalized_payment_type or "unknown"].append(payment)
        return [
            AnalyticsDimensionRow(
                dimension="payment_type",
                key=key,
                label=key,
                metrics={
                    "payments_received": _metric(
                        sum((row.amount for row in value), Decimal("0")),
                        None,
                        unit="money",
                        source_count=len(value),
                        status=_status_from_quality_rows(value),
                        currency="UZS",
                        period=prepared.window,
                    )
                },
                data_status=_status_from_quality_rows(value),
            )
            for key, value in rows.items()
        ]

    def _sales_by_order_status(self, prepared: _PreparedContext) -> list[AnalyticsDimensionRow]:
        rows: dict[str, list[CanonicalOrder]] = defaultdict(list)
        for order in prepared.current_orders:
            rows[order.normalized_status or "unmapped"].append(order)
        return [
            AnalyticsDimensionRow(
                dimension="order_status",
                key=key,
                label=key,
                metrics={
                    "orders": _metric(
                        Decimal(len(value)),
                        None,
                        unit="count",
                        source_count=len(value),
                        status=_status_from_quality_rows(value),
                        period=prepared.window,
                    ),
                    "order_amount": _metric(
                        sum((row.total_amount for row in value), Decimal("0")),
                        None,
                        unit="money",
                        source_count=len(value),
                        status=_status_from_quality_rows(value),
                        currency="UZS",
                        period=prepared.window,
                    ),
                },
                data_status=_status_from_quality_rows(value),
            )
            for key, value in rows.items()
        ]

    def _visit_by_organization(self, prepared: _PreparedContext) -> list[AnalyticsDimensionRow]:
        rows: dict[UUID, list[CanonicalVisit]] = defaultdict(list)
        for visit in prepared.current_visits:
            rows[visit.organization_id].append(visit)
        return [
            AnalyticsDimensionRow(
                dimension="organization",
                key=str(key),
                label=self._organization_name(prepared, key),
                metrics={
                    "visits": _metric(
                        Decimal(len(value)),
                        None,
                        unit="count",
                        source_count=len(value),
                        status=_status_from_quality_rows(value),
                        period=prepared.window,
                    )
                },
                data_status=_status_from_quality_rows(value),
            )
            for key, value in rows.items()
        ]

    def _visit_by_sales_rep(self, prepared: _PreparedContext) -> list[AnalyticsDimensionRow]:
        rows: dict[str, list[CanonicalVisit]] = defaultdict(list)
        for visit in prepared.current_visits:
            rows[visit.sales_rep_external_id or "unassigned"].append(visit)
        return [
            AnalyticsDimensionRow(
                dimension="sales_rep",
                key=key,
                label=key,
                metrics={
                    "visits": _metric(
                        Decimal(len(value)),
                        None,
                        unit="count",
                        source_count=len(value),
                        status=_status_from_quality_rows(value),
                        period=prepared.window,
                    )
                },
                data_status=_status_from_quality_rows(value),
            )
            for key, value in rows.items()
        ]

    def _visit_by_customer(self, prepared: _PreparedContext) -> list[AnalyticsDimensionRow]:
        rows: dict[str, list[CanonicalVisit]] = defaultdict(list)
        for visit in prepared.current_visits:
            rows[visit.customer_external_id or "unassigned"].append(visit)
        return [
            AnalyticsDimensionRow(
                dimension="customer",
                key=key,
                label=key,
                metrics={
                    "visits": _metric(
                        Decimal(len(value)),
                        None,
                        unit="count",
                        source_count=len(value),
                        status=_status_from_quality_rows(value),
                        period=prepared.window,
                    )
                },
                data_status=_status_from_quality_rows(value),
            )
            for key, value in rows.items()
        ]

    def _visit_by_working_zone(self, prepared: _PreparedContext) -> list[AnalyticsDimensionRow]:
        rows: dict[str, list[CanonicalVisit]] = defaultdict(list)
        for visit in prepared.current_visits:
            rows[visit.working_zone_external_id or "unassigned"].append(visit)
        return [
            AnalyticsDimensionRow(
                dimension="working_zone",
                key=key,
                label=key,
                metrics={
                    "visits": _metric(
                        Decimal(len(value)),
                        None,
                        unit="count",
                        source_count=len(value),
                        status=_status_from_quality_rows(value),
                        period=prepared.window,
                    )
                },
                data_status=_status_from_quality_rows(value),
            )
            for key, value in rows.items()
        ]

    def _finance_by_type(self, prepared: _PreparedContext) -> list[AnalyticsDimensionRow]:
        rows: dict[str, list[CanonicalFinancialOperation]] = defaultdict(list)
        for operation in prepared.current_financial_operations:
            rows[operation.normalized_operation_type or "unknown"].append(operation)
        return [
            AnalyticsDimensionRow(
                dimension="operation_type",
                key=key,
                label=key,
                metrics={
                    "amount": _metric(
                        sum((row.amount for row in value), Decimal("0")),
                        None,
                        unit="money",
                        source_count=len(value),
                        status=_status_from_quality_rows(value),
                        currency="UZS",
                        period=prepared.window,
                    )
                },
                data_status=_status_from_quality_rows(value),
            )
            for key, value in rows.items()
        ]

    def _finance_by_category(self, prepared: _PreparedContext) -> list[AnalyticsDimensionRow]:
        rows: dict[str, list[CanonicalFinancialOperation]] = defaultdict(list)
        for operation in prepared.current_financial_operations:
            category = operation.metadata.get("cashflow_reason_code") if isinstance(operation.metadata, dict) else None
            rows[str(category or "uncategorized")].append(operation)
        return [
            AnalyticsDimensionRow(
                dimension="category",
                key=key,
                label=key,
                metrics={
                    "amount": _metric(
                        sum((row.amount for row in value), Decimal("0")),
                        None,
                        unit="money",
                        source_count=len(value),
                        status=_status_from_quality_rows(value),
                        currency="UZS",
                        period=prepared.window,
                    )
                },
                data_status=_status_from_quality_rows(value),
            )
            for key, value in rows.items()
        ]

    def _sales_dimension_row(
        self,
        dimension: str,
        key: str,
        label: str,
        sales: list[CanonicalSale],
        period: AnalyticsPeriodWindow,
    ) -> AnalyticsDimensionRow:
        return AnalyticsDimensionRow(
            dimension=dimension,
            key=key,
            label=label,
            metrics={
                "revenue": _metric(
                    sum((row.total_amount for row in sales), Decimal("0")),
                    None,
                    unit="money",
                    source_count=len(sales),
                    status=_status_from_quality_rows(sales),
                    currency="UZS",
                    period=period,
                ),
                "orders": _metric(
                    Decimal(len(sales)),
                    None,
                    unit="count",
                    source_count=len(sales),
                    status=_status_from_quality_rows(sales),
                    period=period,
                ),
                "sold_units": _metric(
                    sum((row.sold_quantity for row in sales), Decimal("0")),
                    None,
                    unit="units",
                    source_count=len(sales),
                    status=_status_from_quality_rows(sales),
                    period=period,
                ),
                "returns": _metric(
                    sum((row.returned_quantity for row in sales), Decimal("0")),
                    None,
                    unit="units",
                    source_count=len(sales),
                    status=_status_from_quality_rows(sales),
                    period=period,
                ),
            },
            data_status=_status_from_quality_rows(sales),
        )

    def _quality_entry(self, metric_key: str, rows: list[Any]) -> AnalyticsDataQualityEntry:
        status = _status_from_quality_rows(rows)
        return AnalyticsDataQualityEntry(
            metric_key=metric_key,
            data_status=status,
            coverage=_coverage_from_rows(rows),
            confidence=_confidence(status),
            message=f"{len(rows)} canonical rows in selected period.",
        )

    def _classify_product(
        self,
        current_stock: Decimal,
        days_of_stock: Decimal | None,
        current_revenue: Decimal,
        previous_revenue: Decimal,
    ) -> tuple[str, list[str], str]:
        tags: list[str] = []
        if current_revenue > previous_revenue:
            tags.append("GROWING")
        elif current_revenue < previous_revenue:
            tags.append("DECLINING")

        if current_stock <= 0:
            return "DEAD_STOCK", tags + ["NO_STOCK"], "critical"
        if days_of_stock is None:
            return "UNCLASSIFIED", tags, "medium"
        if days_of_stock <= self.thresholds.low_stock_days:
            return "FAST_MOVING", tags + ["LOW_STOCK"], "critical"
        if days_of_stock >= self.thresholds.overstock_days:
            return "OVERSTOCK", tags + ["OVERSTOCK"], "low"
        if current_revenue <= 0:
            return "DEAD_STOCK", tags + ["NO_REVENUE"], "low"
        if current_revenue < previous_revenue:
            return "DECLINING", tags, "medium"
        return "STABLE", tags, "low"

    def _classify_customer_segment(self, days_since_last_order: Decimal | None) -> str:
        if days_since_last_order is None:
            return "NEW"
        days = int(days_since_last_order)
        if days >= self.thresholds.lost_customer_days:
            return "LOST"
        if days >= self.thresholds.at_risk_customer_days:
            return "AT_RISK"
        if days >= self.thresholds.active_customer_days:
            return "DECLINING"
        return "ACTIVE"

    def _organization_name(self, prepared: _PreparedContext, organization_id: UUID) -> str:
        for organization in prepared.organizations:
            if organization.organization_id == organization_id:
                return organization.name
        return str(organization_id)


SalesAnalyticsService = BusinessAnalyticsEngine
ProductAnalyticsService = BusinessAnalyticsEngine
CustomerAnalyticsService = BusinessAnalyticsEngine
InventoryAnalyticsService = BusinessAnalyticsEngine
OrganizationAnalyticsService = BusinessAnalyticsEngine
SalesRepAnalyticsService = BusinessAnalyticsEngine
VisitAnalyticsService = BusinessAnalyticsEngine
FinanceAnalyticsService = BusinessAnalyticsEngine


def _build_period_window(query: AnalyticsQuery) -> AnalyticsPeriodWindow:
    now = datetime.now(UTC)
    today = now.date()

    if query.period == AnalyticsPeriodPreset.CUSTOM and query.date_from and query.date_to:
        current_start = datetime.combine(query.date_from, time.min, tzinfo=UTC)
        current_end = datetime.combine(query.date_to, time.max, tzinfo=UTC)
        span = max(1, (query.date_to - query.date_from).days + 1)
        previous_end = current_start - timedelta(seconds=1)
        previous_start = previous_end - timedelta(days=span - 1)
        return AnalyticsPeriodWindow(
            current_start=current_start,
            current_end=current_end,
            previous_start=previous_start,
            previous_end=previous_end,
            label=f"{query.date_from.isoformat()} – {query.date_to.isoformat()}",
            comparison_label="previous equivalent period",
        )

    if query.period == AnalyticsPeriodPreset.TODAY:
        current_start = datetime.combine(today, time.min, tzinfo=UTC)
        current_end = datetime.combine(today, time.max, tzinfo=UTC)
    elif query.period == AnalyticsPeriodPreset.YESTERDAY:
        target = today - timedelta(days=1)
        current_start = datetime.combine(target, time.min, tzinfo=UTC)
        current_end = datetime.combine(target, time.max, tzinfo=UTC)
    elif query.period == AnalyticsPeriodPreset.LAST_7_DAYS:
        current_start = datetime.combine(today - timedelta(days=6), time.min, tzinfo=UTC)
        current_end = datetime.combine(today, time.max, tzinfo=UTC)
    elif query.period == AnalyticsPeriodPreset.CURRENT_MONTH:
        current_start = datetime.combine(today.replace(day=1), time.min, tzinfo=UTC)
        current_end = datetime.combine(today, time.max, tzinfo=UTC)
    elif query.period == AnalyticsPeriodPreset.PREVIOUS_MONTH:
        month_start = today.replace(day=1)
        prev_end = month_start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
        current_start = datetime.combine(prev_start, time.min, tzinfo=UTC)
        current_end = datetime.combine(prev_end, time.max, tzinfo=UTC)
    elif query.period == AnalyticsPeriodPreset.ALL:
        return AnalyticsPeriodWindow(
            current_start=None,
            current_end=None,
            previous_start=None,
            previous_end=None,
            label="all time",
            comparison_label="not available",
        )
    else:
        current_start = datetime.combine(today - timedelta(days=29), time.min, tzinfo=UTC)
        current_end = datetime.combine(today, time.max, tzinfo=UTC)

    span = max(1, (current_end.date() - current_start.date()).days + 1)
    previous_end = current_start - timedelta(seconds=1)
    comparison_label = "previous equivalent period"

    if query.comparison_mode == AnalyticsComparisonMode.PREVIOUS_MONTH:
        month_end = current_start.date().replace(day=1) - timedelta(days=1)
        month_start = month_end.replace(day=1)
        previous_start = datetime.combine(month_start, time.min, tzinfo=UTC)
        previous_end = datetime.combine(month_end, time.max, tzinfo=UTC)
        comparison_label = "previous month"
    elif query.comparison_mode == AnalyticsComparisonMode.PREVIOUS_YEAR:
        try:
            previous_start = current_start.replace(year=current_start.year - 1)
            previous_end = current_end.replace(year=current_end.year - 1)
            comparison_label = "previous year"
        except ValueError:
            previous_start = None
            previous_end = None
            comparison_label = "insufficient history"
    elif query.comparison_mode == AnalyticsComparisonMode.PREVIOUS_WEEK:
        previous_start = current_start - timedelta(days=7)
        previous_end = current_end - timedelta(days=7)
        comparison_label = "previous week"
    else:
        previous_start = previous_end - timedelta(days=span - 1)

    return AnalyticsPeriodWindow(
        current_start=current_start,
        current_end=current_end,
        previous_start=previous_start,
        previous_end=previous_end,
        label=query.period.value,
        comparison_label=comparison_label,
    )


def _filter_org(rows: Any, organization_ids: set[UUID]) -> list[Any]:
    return [row for row in rows if row.organization_id in organization_ids]


def _filter_by_window(
    rows: list[Any],
    window: AnalyticsPeriodWindow,
    field_getter: Any,
) -> list[Any]:
    if window.current_start is None or window.current_end is None:
        return list(rows)
    return [
        row
        for row in rows
        if (value := field_getter(row)) is not None and window.current_start <= value <= window.current_end
    ]


def _filter_previous_window(
    rows: list[Any],
    window: AnalyticsPeriodWindow,
    field_getter: Any,
) -> list[Any]:
    if window.previous_start is None or window.previous_end is None:
        return []
    return [
        row
        for row in rows
        if (value := field_getter(row)) is not None and window.previous_start <= value <= window.previous_end
    ]


def _group_by(rows: list[Any], key_fn: Any) -> dict[Any, list[Any]]:
    grouped: dict[Any, list[Any]] = defaultdict(list)
    for row in rows:
        grouped[key_fn(row)].append(row)
    return grouped


def _is_verified(row: Any) -> bool:
    return getattr(row, "data_quality_status", None) == CanonicalDataQualityStatus.VERIFIED


def _is_verified_realised_sale(row: CanonicalSale) -> bool:
    return _is_verified(row) and row.normalized_status != "cancelled" and row.sold_quantity > 0


def _is_verified_inflow(row: CanonicalFinancialOperation) -> bool:
    return (
        _is_verified(row)
        and row.direction == CanonicalFinancialDirection.INFLOW
        and not row.is_internal_transfer
    )


def _is_verified_outflow(row: CanonicalFinancialOperation) -> bool:
    return (
        _is_verified(row)
        and row.direction == CanonicalFinancialDirection.OUTFLOW
        and not row.is_internal_transfer
    )


def _safe_percent(value: Decimal, baseline: Decimal) -> Decimal | None:
    if baseline == 0:
        return None
    return (value / baseline) * Decimal("100")


def _frequency_metric_value(window: AnalyticsPeriodWindow, count: int) -> Decimal | None:
    if window.current_start is None or window.current_end is None or count == 0:
        return None
    days = max(1, (window.current_end.date() - window.current_start.date()).days + 1)
    return Decimal(count) / Decimal(days)


def _metric_decimal(metric: AnalyticsMetricValue) -> Decimal | None:
    return metric.value


def _status_from_quality_rows(
    rows: list[Any],
    *,
    none_status: AnalyticsDataStatus = AnalyticsDataStatus.NO_DATA,
) -> AnalyticsDataStatus:
    if not rows:
        return none_status
    statuses = {getattr(row, "data_quality_status", None) for row in rows}
    if statuses == {CanonicalDataQualityStatus.VERIFIED}:
        return AnalyticsDataStatus.AVAILABLE
    if CanonicalDataQualityStatus.VERIFIED in statuses:
        return AnalyticsDataStatus.PARTIAL
    if CanonicalDataQualityStatus.PARTIAL in statuses:
        return AnalyticsDataStatus.PARTIAL
    if CanonicalDataQualityStatus.UNRESOLVED in statuses:
        return AnalyticsDataStatus.UNRESOLVED
    return AnalyticsDataStatus.NOT_AVAILABLE


def _coverage_from_rows(rows: list[Any]) -> float:
    if not rows:
        return 0.0
    verified = sum(1 for row in rows if getattr(row, "data_quality_status", None) == CanonicalDataQualityStatus.VERIFIED)
    partial = sum(1 for row in rows if getattr(row, "data_quality_status", None) == CanonicalDataQualityStatus.PARTIAL)
    return (verified + partial * 0.5) / len(rows)


def _confidence(status: AnalyticsDataStatus) -> float:
    mapping = {
        AnalyticsDataStatus.AVAILABLE: 1.0,
        AnalyticsDataStatus.PARTIAL: 0.66,
        AnalyticsDataStatus.UNRESOLVED: 0.25,
        AnalyticsDataStatus.INSUFFICIENT_HISTORY: 0.25,
        AnalyticsDataStatus.NO_DATA: 0.0,
        AnalyticsDataStatus.NO_VERIFIED_DATA: 0.0,
        AnalyticsDataStatus.NOT_AVAILABLE: 0.0,
        AnalyticsDataStatus.PERMISSION_RESTRICTED: 0.0,
        AnalyticsDataStatus.NOT_SUPPORTED: 0.0,
        AnalyticsDataStatus.ANALYSIS_PENDING: 0.0,
    }
    return mapping.get(status, 0.0)


def _worst_status(statuses: list[AnalyticsDataStatus]) -> AnalyticsDataStatus:
    priority = {
        AnalyticsDataStatus.NOT_AVAILABLE: 9,
        AnalyticsDataStatus.PERMISSION_RESTRICTED: 8,
        AnalyticsDataStatus.UNRESOLVED: 7,
        AnalyticsDataStatus.NO_VERIFIED_DATA: 6,
        AnalyticsDataStatus.INSUFFICIENT_HISTORY: 5,
        AnalyticsDataStatus.NO_DATA: 4,
        AnalyticsDataStatus.PARTIAL: 3,
        AnalyticsDataStatus.ANALYSIS_PENDING: 2,
        AnalyticsDataStatus.NOT_SUPPORTED: 2,
        AnalyticsDataStatus.AVAILABLE: 1,
    }
    return max(statuses, key=lambda item: priority.get(item, 0), default=AnalyticsDataStatus.NO_DATA)


def _overall_data_status(statuses: list[AnalyticsDataStatus]) -> AnalyticsDataStatus:
    filtered = [status for status in statuses if status != AnalyticsDataStatus.NO_DATA]
    if not filtered:
        return AnalyticsDataStatus.NO_DATA
    blocking = {
        AnalyticsDataStatus.NOT_AVAILABLE,
        AnalyticsDataStatus.PERMISSION_RESTRICTED,
        AnalyticsDataStatus.UNRESOLVED,
        AnalyticsDataStatus.NO_VERIFIED_DATA,
        AnalyticsDataStatus.INSUFFICIENT_HISTORY,
    }
    worst = _worst_status(filtered)
    if worst in blocking:
        return worst
    if AnalyticsDataStatus.AVAILABLE in filtered:
        return AnalyticsDataStatus.AVAILABLE
    if AnalyticsDataStatus.PARTIAL in filtered:
        return AnalyticsDataStatus.PARTIAL
    return worst


def _latest_inventory_rows(
    rows: list[CanonicalInventoryBalance],
) -> list[CanonicalInventoryBalance]:
    latest: dict[tuple[UUID, UUID | None, str | None, str | None], CanonicalInventoryBalance] = {}
    for row in rows:
        key = (
            row.organization_id,
            row.product_id,
            row.product_code,
            row.warehouse_code,
        )
        current = latest.get(key)
        if current is None:
            latest[key] = row
            continue
        current_date = current.snapshot_date or datetime.min.replace(tzinfo=UTC)
        row_date = row.snapshot_date or datetime.min.replace(tzinfo=UTC)
        if row_date >= current_date:
            latest[key] = row
    return list(latest.values())


def _metric(
    value: Decimal | None,
    previous_value: Decimal | None = None,
    *,
    unit: str = "count",
    source_count: int = 0,
    previous_source_count: int = 0,
    supported_dimensions: list[str] | None = None,
    drilldown: list[str] | None = None,
    status: AnalyticsDataStatus | None = None,
    note: str | None = None,
    currency: str | None = None,
    period: AnalyticsPeriodWindow | None = None,
) -> AnalyticsMetricValue:
    if status is None:
        if value is None and source_count == 0 and previous_source_count == 0:
            status = AnalyticsDataStatus.NO_DATA
        elif value is None:
            status = AnalyticsDataStatus.PARTIAL
        else:
            status = AnalyticsDataStatus.AVAILABLE
    delta = None
    percent_delta = None
    if value is not None and previous_value is not None:
        delta = value - previous_value
        if previous_value != 0:
            percent_delta = (delta / previous_value) * Decimal("100")
    return AnalyticsMetricValue(
        value=value,
        previous_value=previous_value,
        delta=delta,
        percent_delta=percent_delta,
        unit=unit,
        status=status,
        data_status=status,
        coverage=float(source_count if source_count > 0 else previous_source_count),
        confidence=_confidence(status),
        currency=currency,
        record_count=source_count,
        period=period,
        supported_dimensions=supported_dimensions or [],
        drilldown=drilldown or [],
        note=note,
    )


def _percent_change_metric(
    current_value: Decimal,
    previous_value: Decimal,
    period: AnalyticsPeriodWindow,
) -> AnalyticsMetricValue:
    if previous_value == 0 and current_value > 0:
        return _metric(
            None,
            None,
            unit="percent",
            source_count=1,
            status=AnalyticsDataStatus.INSUFFICIENT_HISTORY,
            period=period,
        )
    if previous_value == 0:
        return _metric(
            None,
            None,
            unit="percent",
            source_count=0,
            status=AnalyticsDataStatus.NO_DATA,
            period=period,
        )
    delta = current_value - previous_value
    return _metric(
        (delta / previous_value) * Decimal("100"),
        None,
        unit="percent",
        source_count=1,
        status=AnalyticsDataStatus.AVAILABLE,
        period=period,
    )


def _delta_metric(metric: AnalyticsMetricValue) -> AnalyticsMetricValue:
    return AnalyticsMetricValue(
        value=metric.percent_delta,
        previous_value=metric.previous_value,
        delta=metric.delta,
        percent_delta=metric.percent_delta,
        unit="percent",
        status=metric.data_status,
        data_status=metric.data_status,
        coverage=metric.coverage,
        confidence=metric.confidence,
        currency=metric.currency,
        record_count=metric.record_count,
        period=metric.period,
        note=metric.note,
    )
