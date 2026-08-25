"""Dashboard overview helpers for the business core."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.agents.ceo.analytics import AIAnalyticsAgent
from app.agents.ceo.composer import AIDashboardComposer
from app.core.analytics.models import (
    AIDashboardWorkspace,
    BusinessAnalyticsSnapshot,
)
from app.core.analytics.snapshot import BusinessAnalyticsSnapshotService
from app.core.data_layer.contracts import CoreDataReader
from app.core.data_layer.entities import FinanceEntryType, MarketingChannel, SaleStage
from app.core.data_layer.normalized import (
    BusinessDocument,
    InventoryBalance,
    Payment,
    Product,
    ProductCategory,
    Sale,
    SaleItem,
    Warehouse,
)

MONTH_LABELS = ("янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")
STRUCTURE_COLORS = ("#6d5efc", "#0ea5e9", "#10b981", "#a78bfa")
NUMERIC_CURRENCY_LABELS = {
    "643": "RUB",
    "760": "SYP",
    "784": "AED",
    "810": "USD",
    "840": "USD",
    "858": "UYU",
    "860": "UZS",
    "978": "EUR",
}


class DataAvailabilityStatus(StrEnum):
    """Availability state for dashboard blocks."""

    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    SYNCING = "syncing"
    ERROR = "error"


class DashboardDirection(StrEnum):
    """Directional change for KPI and trend cards."""

    UP = "up"
    DOWN = "down"
    FLAT = "flat"
    NONE = "none"


class DashboardCard(BaseModel):
    """Compact card used across the dashboard overview."""

    label: str
    value: str
    note: str
    details_href: str | None = None
    status: DataAvailabilityStatus = DataAvailabilityStatus.AVAILABLE
    previous_value: str | None = None
    change: str | None = None


class DashboardMetric(BaseModel):
    """Business metric shown in the main KPI row."""

    label: str
    value: str
    note: str
    details_href: str | None = None
    previous_value: str | None = None
    change_percent: str | None = None
    direction: DashboardDirection = DashboardDirection.NONE
    status: str | None = None
    data_status: DataAvailabilityStatus = DataAvailabilityStatus.AVAILABLE


class DashboardSignal(BaseModel):
    """Operational signal for the AI and management view."""

    severity: str = "info"
    title: str
    badge: str
    note: str
    organization: str | None = None
    period: str | None = None
    details_href: str | None = None
    metrics: list[str] = Field(default_factory=list)


class DashboardTrend(BaseModel):
    """Monthly trend line rendered in the overview chart."""

    title: str
    description: str
    badge: str
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)
    comparison_labels: list[str] = Field(default_factory=list)
    comparison_values: list[float] = Field(default_factory=list)
    secondary_label: str | None = None
    secondary_values: list[float] = Field(default_factory=list)
    granularity: str = "month"


class DashboardStructureItem(BaseModel):
    """Share of the business data structure."""

    label: str
    value: str
    note: str
    color: str


class DashboardBusinessCard(BaseModel):
    """Business-level breakdown for UI and AI routing."""

    business_id: UUID
    name: str
    external_ref: str | None = None
    source_systems: int = 0
    contacts: int = 0
    sales: int = 0
    marketing_activities: int = 0
    finance_entries: int = 0
    revenue: str = "0 USD"
    expense: str = "0 USD"
    net_flow: str = "0 USD"
    rank: int | None = None
    change_percent: str | None = None
    direction: DashboardDirection = DashboardDirection.NONE
    sold_units: str = "0"
    average_check: str = "—"
    returns: str = "0"
    cash_received: str = "0"
    trend_labels: list[str] = Field(default_factory=list)
    trend_values: list[float] = Field(default_factory=list)
    data_status: DataAvailabilityStatus = DataAvailabilityStatus.AVAILABLE


class DashboardSaleItemCard(BaseModel):
    """Detailed sale item row for the overview."""

    sale_id: UUID
    sale_number: str
    business_id: UUID
    business_name: str
    contact_name: str | None = None
    external_ref: str | None = None
    amount: str
    currency: str
    stage: str
    sale_at: datetime
    items_count: int = 0
    products_count: int = 0


class DashboardProductCard(BaseModel):
    """Detailed product row for the overview."""

    product_id: UUID
    business_id: UUID
    business_name: str
    name: str
    category: str | None = None
    sku: str | None = None
    unit: str | None = None
    sold_quantity: str
    sold_amount: str
    stock_quantity: str
    last_sold_at: datetime | None = None
    share: str | None = None
    change_percent: str | None = None
    direction: DashboardDirection = DashboardDirection.NONE
    no_sales_days: int | None = None
    stock_days: str | None = None
    status: str | None = None
    details_href: str | None = None
    data_status: DataAvailabilityStatus = DataAvailabilityStatus.AVAILABLE


class DashboardInventoryCard(BaseModel):
    """Inventory snapshot row for the overview."""

    warehouse_name: str
    product_name: str
    business_id: UUID
    business_name: str
    quantity: str
    balance_at: datetime
    average_daily_sales: str | None = None
    days_of_stock: str | None = None
    risk_level: str | None = None
    last_sold_at: datetime | None = None
    details_href: str | None = None
    data_status: DataAvailabilityStatus = DataAvailabilityStatus.AVAILABLE


class DashboardPaymentCard(BaseModel):
    """Recent payment row for the overview."""

    payment_id: UUID
    business_id: UUID
    business_name: str
    sale_number: str | None = None
    amount: str
    currency: str
    paid_at: datetime
    method: str | None = None
    entry_type: str | None = None
    category: str | None = None
    details_href: str | None = None
    data_status: DataAvailabilityStatus = DataAvailabilityStatus.AVAILABLE


class DashboardAvailabilityCard(BaseModel):
    """Availability and sync-state card for a business data domain."""

    label: str
    value: str
    note: str
    status: DataAvailabilityStatus = DataAvailabilityStatus.UNAVAILABLE
    details_href: str | None = None


class DashboardOverviewResponse(BaseModel):
    """Dashboard payload consumed by the frontend."""

    generated_at: datetime
    analysis_engine: str
    analysis_note: str
    freshness: str
    data_summary: list[DashboardCard] = Field(default_factory=list)
    executive_summary: list[DashboardCard] = Field(default_factory=list)
    business_metrics: list[DashboardMetric] = Field(default_factory=list)
    trend: DashboardTrend
    signals: list[DashboardSignal] = Field(default_factory=list)
    action_center: list[DashboardSignal] = Field(default_factory=list)
    structure: list[DashboardStructureItem] = Field(default_factory=list)
    businesses: list[DashboardBusinessCard] = Field(default_factory=list)
    organization_performance: list[DashboardBusinessCard] = Field(default_factory=list)
    recent_sales: list[DashboardSaleItemCard] = Field(default_factory=list)
    top_products: list[DashboardProductCard] = Field(default_factory=list)
    inventory: list[DashboardInventoryCard] = Field(default_factory=list)
    recent_payments: list[DashboardPaymentCard] = Field(default_factory=list)
    dead_stock: list[DashboardProductCard] = Field(default_factory=list)
    returns_summary: list[DashboardCard] = Field(default_factory=list)
    cash_flow: list[DashboardCard] = Field(default_factory=list)
    customers_summary: list[DashboardCard] = Field(default_factory=list)
    seller_performance: list[DashboardCard] = Field(default_factory=list)
    recommendations: list[DashboardCard] = Field(default_factory=list)
    availability: list[DashboardAvailabilityCard] = Field(default_factory=list)
    ai_insights: list[str] = Field(default_factory=list)
    analytics_snapshot: BusinessAnalyticsSnapshot | None = None
    ai_workspace: AIDashboardWorkspace | None = None


class DashboardPeriod(StrEnum):
    """Supported dashboard date filters."""

    ALL = "all"
    LAST_30_DAYS = "30d"
    LAST_90_DAYS = "90d"
    LAST_12_MONTHS = "12m"


@dataclass(frozen=True, slots=True)
class DashboardPeriodWindow:
    """Current and previous time windows for comparative analytics."""

    current_start: datetime | None
    current_end: datetime | None
    previous_start: datetime | None
    previous_end: datetime | None
    label: str
    comparison_label: str


class BusinessAIAnalyticsEngine:
    """AI-style analytics layer that turns stored history into dashboard output."""

    def __init__(self, store: CoreDataReader) -> None:
        self.store = store

    def build_overview(
        self,
        *,
        business_id: UUID | None = None,
        organization_ids: list[UUID] | None = None,
        period: DashboardPeriod = DashboardPeriod.LAST_12_MONTHS,
        channel: MarketingChannel | None = None,
    ) -> DashboardOverviewResponse:
        """Build a presentation-ready dashboard overview from the core store."""

        businesses = list(self.store.list_businesses())
        contacts = list(self.store.list_contacts())
        raw_sales = list(self.store.list_sales())
        marketing_activities = list(self.store.list_marketing_activities())
        finance_entries = list(self.store.list_finance_entries())
        source_systems = list(self.store.list_source_systems())
        ingestion_batches = list(self.store.list_ingestion_batches())
        _smartup_organizations = list(self.store.list_smartup_organizations(is_active=True))
        product_categories = list(self.store.list_product_categories())
        products = list(self.store.list_products())
        warehouses = list(self.store.list_warehouses())
        sales_v2 = list(self.store.list_sales_v2())
        sale_items = list(self.store.list_sale_items())
        payments = list(self.store.list_payments())
        inventory_balances = list(self.store.list_inventory_balances())
        business_documents = list(self.store.list_business_documents())
        raw_records = list(self.store.list_smartup_raw_records())

        selected_business_ids = list(dict.fromkeys(organization_ids or []))
        if not selected_business_ids and business_id is not None:
            selected_business_ids = [business_id]

        if selected_business_ids:
            selected_set = set(selected_business_ids)
            businesses = [
                business
                for business in businesses
                if business.business_id in selected_set
            ]
            contacts = [
                contact for contact in contacts if contact.business_id in selected_set
            ]
            raw_sales = [sale for sale in raw_sales if sale.business_id in selected_set]
            marketing_activities = [
                activity
                for activity in marketing_activities
                if activity.business_id in selected_set
            ]
            finance_entries = [
                entry for entry in finance_entries if entry.business_id in selected_set
            ]
            source_systems = [
                source_system
                for source_system in source_systems
                if source_system.business_id in selected_set
            ]
            ingestion_batches = [
                batch for batch in ingestion_batches if batch.business_id in selected_set
            ]
            product_categories = [
                category
                for category in product_categories
                if category.organization_id in selected_set
            ]
            products = [
                product for product in products if product.organization_id in selected_set
            ]
            warehouses = [
                warehouse for warehouse in warehouses if warehouse.organization_id in selected_set
            ]
            sales_v2 = [sale for sale in sales_v2 if sale.organization_id in selected_set]
            sale_items = [item for item in sale_items if item.organization_id in selected_set]
            payments = [payment for payment in payments if payment.organization_id in selected_set]
            inventory_balances = [
                balance for balance in inventory_balances if balance.organization_id in selected_set
            ]
            business_documents = [
                document
                for document in business_documents
                if document.organization_id in selected_set
            ]
            raw_records = [
                record for record in raw_records if record.organization_id in selected_set
            ]

        window = _dashboard_period_window(period)
        current_sales = _period_filter(
            sales_v2,
            timestamp_getter=lambda sale: sale.sale_at.astimezone(UTC),
            window=window,
        )
        previous_sales = _previous_period_filter(
            sales_v2,
            timestamp_getter=lambda sale: sale.sale_at.astimezone(UTC),
            window=window,
        )
        current_raw_sales = _period_filter(
            raw_sales,
            timestamp_getter=lambda sale: sale.occurred_at.astimezone(UTC),
            window=window,
        )
        previous_raw_sales = _previous_period_filter(
            raw_sales,
            timestamp_getter=lambda sale: sale.occurred_at.astimezone(UTC),
            window=window,
        )
        current_marketing = _period_filter(
            marketing_activities,
            timestamp_getter=lambda activity: activity.occurred_at.astimezone(UTC),
            window=window,
        )
        previous_marketing = _previous_period_filter(
            marketing_activities,
            timestamp_getter=lambda activity: activity.occurred_at.astimezone(UTC),
            window=window,
        )
        current_finance = _period_filter(
            finance_entries,
            timestamp_getter=lambda entry: entry.occurred_at.astimezone(UTC),
            window=window,
        )
        previous_finance = _previous_period_filter(
            finance_entries,
            timestamp_getter=lambda entry: entry.occurred_at.astimezone(UTC),
            window=window,
        )
        current_payments = _period_filter(
            payments,
            timestamp_getter=lambda payment: payment.paid_at.astimezone(UTC),
            window=window,
        )
        previous_payments = _previous_period_filter(
            payments,
            timestamp_getter=lambda payment: payment.paid_at.astimezone(UTC),
            window=window,
        )
        current_inventory = _period_filter(
            inventory_balances,
            timestamp_getter=lambda balance: balance.balance_at.astimezone(UTC),
            window=window,
        )
        previous_inventory = _previous_period_filter(
            inventory_balances,
            timestamp_getter=lambda balance: balance.balance_at.astimezone(UTC),
            window=window,
        )
        current_documents = _period_filter(
            business_documents,
            timestamp_getter=lambda document: document.document_at.astimezone(UTC),
            window=window,
        )
        previous_documents = _previous_period_filter(
            business_documents,
            timestamp_getter=lambda document: document.document_at.astimezone(UTC),
            window=window,
        )

        current_completed_sales = [sale for sale in current_sales if _is_completed_sale(sale)]
        previous_completed_sales = [sale for sale in previous_sales if _is_completed_sale(sale)]
        current_returned_sales = [
            sale for sale in current_sales if (sale.status or "").strip().casefold() == "refunded"
        ]
        previous_returned_sales = [
            sale for sale in previous_sales if (sale.status or "").strip().casefold() == "refunded"
        ]
        current_open_sales = [
            sale
            for sale in current_sales
            if (sale.status or "").strip().casefold() not in {"won", "refunded"}
        ]
        _previous_open_sales = [
            sale
            for sale in previous_sales
            if (sale.status or "").strip().casefold() not in {"won", "refunded"}
        ]

        current_completed_sale_ids = {sale.id for sale in current_completed_sales}
        current_completed_sale_external_ids = {
            sale.source_external_id for sale in current_completed_sales if sale.source_external_id
        }
        previous_completed_sale_ids = {sale.id for sale in previous_completed_sales}
        previous_completed_sale_external_ids = {
            sale.source_external_id for sale in previous_completed_sales if sale.source_external_id
        }
        current_completed_sale_items = [
            item
            for item in sale_items
            if _sale_item_belongs_to_completed_sale(
                item,
                sale_ids=current_completed_sale_ids,
                sale_external_ids=current_completed_sale_external_ids,
            )
        ]
        previous_completed_sale_items = [
            item
            for item in sale_items
            if _sale_item_belongs_to_completed_sale(
                item,
                sale_ids=previous_completed_sale_ids,
                sale_external_ids=previous_completed_sale_external_ids,
            )
        ]

        current_currency = _dominant_currency(
            current_completed_sales,
            current_sales,
            current_finance,
            current_payments,
            current_completed_sale_items,
        )
        previous_currency = _dominant_currency(
            previous_completed_sales,
            previous_sales,
            previous_finance,
            previous_payments,
            previous_completed_sale_items,
        )
        currency = current_currency or previous_currency or "USD"

        gross_sales_current = sum((sale.amount for sale in current_completed_sales), Decimal("0"))
        gross_sales_previous = sum((sale.amount for sale in previous_completed_sales), Decimal("0"))
        return_docs_current = [
            document
            for document in current_documents
            if document.document_type in {"return", "return_to_supplier"}
        ]
        return_docs_previous = [
            document
            for document in previous_documents
            if document.document_type in {"return", "return_to_supplier"}
        ]
        returns_current = sum((sale.amount for sale in current_returned_sales), Decimal("0")) + sum(
            (document.amount for document in return_docs_current), Decimal("0")
        )
        returns_previous = sum(
            (sale.amount for sale in previous_returned_sales), Decimal("0")
        ) + sum((document.amount for document in return_docs_previous), Decimal("0"))
        sales_revenue_current = gross_sales_current - returns_current
        sales_revenue_previous = gross_sales_previous - returns_previous
        cash_received_current = sum(
            (
                entry.amount
                for entry in current_finance
                if entry.entry_type == FinanceEntryType.REVENUE
            ),
            Decimal("0"),
        )
        cash_received_previous = sum(
            (
                entry.amount
                for entry in previous_finance
                if entry.entry_type == FinanceEntryType.REVENUE
            ),
            Decimal("0"),
        )
        expense_current = sum(
            (
                entry.amount
                for entry in current_finance
                if entry.entry_type == FinanceEntryType.EXPENSE
            ),
            Decimal("0"),
        )
        expense_previous = sum(
            (
                entry.amount
                for entry in previous_finance
                if entry.entry_type == FinanceEntryType.EXPENSE
            ),
            Decimal("0"),
        )
        net_cash_flow_current = cash_received_current - expense_current
        net_cash_flow_previous = cash_received_previous - expense_previous
        sold_units_current = sum(
            (item.quantity for item in current_completed_sale_items), Decimal("0")
        )
        sold_units_previous = sum(
            (item.quantity for item in previous_completed_sale_items), Decimal("0")
        )
        current_products_sold = len(
            {
                item.product_external_id
                for item in current_completed_sale_items
                if item.product_external_id
            },
        )
        deals_current = len(current_sales)
        deals_previous = len(previous_sales)
        buyers_current = len(
            {
                sale.customer_external_id
                for sale in current_completed_sales
                if sale.customer_external_id
            }
        )
        buyers_previous = len(
            {
                sale.customer_external_id
                for sale in previous_completed_sales
                if sale.customer_external_id
            }
        )
        repeat_buyers_current = len(
            [
                contact_id
                for contact_id, count in Counter(
                    sale.customer_external_id
                    for sale in current_completed_sales
                    if sale.customer_external_id is not None
                ).items()
                if count > 1
            ],
        )
        repeat_buyers_previous = len(
            [
                contact_id
                for contact_id, count in Counter(
                    sale.customer_external_id
                    for sale in previous_completed_sales
                    if sale.customer_external_id is not None
                ).items()
                if count > 1
            ],
        )
        avg_check_current = (
            gross_sales_current / Decimal(len(current_completed_sales))
            if current_completed_sales
            else Decimal("0")
        )
        avg_check_previous = (
            gross_sales_previous / Decimal(len(previous_completed_sales))
            if previous_completed_sales
            else Decimal("0")
        )
        revenue_change = _change_percent(gross_sales_current, gross_sales_previous)
        cash_change = _change_percent(cash_received_current, cash_received_previous)
        expense_change = _change_percent(expense_current, expense_previous)
        cash_flow_change = _change_percent(net_cash_flow_current, net_cash_flow_previous)
        deals_change = _change_percent(Decimal(deals_current), Decimal(deals_previous))
        sold_units_change = _change_percent(sold_units_current, sold_units_previous)
        avg_check_change = _change_percent(avg_check_current, avg_check_previous)
        returns_change = _change_percent(returns_current, returns_previous)
        buyers_change = _change_percent(Decimal(buyers_current), Decimal(buyers_previous))
        buyer_conversion_current = (
            (Decimal(buyers_current) / Decimal(len(contacts))) * Decimal("100")
            if contacts
            else Decimal("0")
        )
        buyer_conversion_previous = (
            (Decimal(buyers_previous) / Decimal(len(contacts))) * Decimal("100")
            if contacts
            else Decimal("0")
        )

        revenue_available = bool(current_sales or previous_sales or raw_sales)
        cash_available = bool(current_finance or previous_finance or current_sales or raw_sales)
        expense_available = bool(current_finance or previous_finance or current_sales or raw_sales)
        sold_units_available = bool(
            current_completed_sale_items
            or previous_completed_sale_items
            or current_sales
            or raw_sales
        )
        deals_available = bool(current_sales or previous_sales or raw_sales)
        avg_check_available = bool(current_completed_sales or previous_completed_sales)
        returns_available = bool(
            current_returned_sales
            or previous_returned_sales
            or return_docs_current
            or return_docs_previous
            or current_sales
            or previous_sales
        )
        customers_available = bool(contacts)

        latest_activity_at = _latest_activity_at(
            sales=raw_sales,
            marketing_activities=marketing_activities,
            finance_entries=finance_entries,
            ingestion_batches=ingestion_batches,
        )
        freshness = _humanize_freshness(latest_activity_at)

        revenue_trend = _build_revenue_trend(current_completed_sales or sales_v2)
        growth_badge = _growth_badge(revenue_trend.values)

        if channel is not None:
            current_marketing = [
                activity for activity in current_marketing if activity.channel == channel
            ]
            previous_marketing = [
                activity for activity in previous_marketing if activity.channel == channel
            ]

        _marketing_spend_current = sum(
            (activity.spend for activity in current_marketing), Decimal("0")
        )
        _marketing_spend_previous = sum(
            (activity.spend for activity in previous_marketing),
            Decimal("0"),
        )
        _marketing_conversions_current = sum(activity.conversions for activity in current_marketing)
        _marketing_conversions_previous = sum(
            activity.conversions for activity in previous_marketing
        )

        sale_by_external: dict[str, Sale] = {
            sale.source_external_id: sale for sale in current_sales if sale.source_external_id
        }
        previous_sale_by_external: dict[str, Sale] = {
            sale.source_external_id: sale for sale in previous_sales if sale.source_external_id
        }
        product_categories_by_id = {
            category.source_external_id: category for category in product_categories
        }
        product_by_id = {product.source_external_id: product for product in products}
        warehouse_by_id = {warehouse.source_external_id: warehouse for warehouse in warehouses}
        contact_by_external_id = {
            contact.external_ref or str(contact.contact_id): contact.full_name
            for contact in contacts
        }
        business_by_id = {business.business_id: business for business in businesses}

        data_summary = [
            DashboardCard(
                label="Выручка",
                value=_format_money(gross_sales_current, currency)
                if revenue_available
                else "Нет данных",
                note=f"{window.label} · {window.comparison_label}",
                details_href="/api/v1/data/sales",
                previous_value=_format_money(gross_sales_previous, currency)
                if revenue_available
                else None,
                change=_format_change(revenue_change),
                status=_availability_from_counts(
                    normalized_count=len(current_completed_sales),
                    raw_count=_raw_entity_count(raw_records, "sale", "order"),
                ),
            ),
            DashboardCard(
                label="Получено денег",
                value=_format_money(cash_received_current, currency)
                if cash_available
                else "Нет данных",
                note="по поступлениям и оплатам",
                details_href="/api/v1/data/payments",
                previous_value=_format_money(cash_received_previous, currency)
                if cash_available
                else None,
                change=_format_change(cash_change),
                status=_availability_from_counts(
                    normalized_count=len(current_finance) + len(current_payments),
                    raw_count=_raw_entity_count(raw_records, "payment", "cash", "bank"),
                ),
            ),
            DashboardCard(
                label="Расходы",
                value=_format_money(expense_current, currency)
                if expense_available
                else "Нет данных",
                note="по расходным операциям",
                details_href="/api/v1/data/processing",
                previous_value=_format_money(expense_previous, currency)
                if expense_available
                else None,
                change=_format_change(expense_change),
                status=_availability_from_counts(
                    normalized_count=len(current_finance),
                    raw_count=_raw_entity_count(
                        raw_records, "expense", "cash_operation", "bank_operation"
                    ),
                ),
            ),
            DashboardCard(
                label="Чистый денежный поток",
                value=_format_money(net_cash_flow_current, currency)
                if cash_available
                else "Нет данных",
                note="получено денег минус расходы",
                details_href="/api/v1/data/overview",
                previous_value=_format_money(net_cash_flow_previous, currency)
                if cash_available
                else None,
                change=_format_change(cash_flow_change),
                status=_availability_from_counts(
                    normalized_count=len(current_finance),
                    raw_count=_raw_entity_count(raw_records, "cash", "bank", "payment"),
                ),
            ),
            DashboardCard(
                label="Сделки",
                value=str(deals_current) if deals_available else "Нет данных",
                note=f"{len(current_completed_sales)} закрыто, {len(current_open_sales)} в работе",
                details_href="/api/v1/data/sales",
                previous_value=str(deals_previous) if deals_available else None,
                change=_format_change(deals_change),
                status=_availability_from_counts(
                    normalized_count=len(current_sales),
                    raw_count=_raw_entity_count(raw_records, "sale", "order"),
                ),
            ),
            DashboardCard(
                label="Продано единиц",
                value=_format_decimal(sold_units_current) if sold_units_available else "Нет данных",
                note=f"{current_products_sold} уникальных товаров",
                details_href="/api/v1/data/sale-items",
                previous_value=_format_decimal(sold_units_previous)
                if sold_units_available
                else None,
                change=_format_change(sold_units_change),
                status=_availability_from_counts(
                    normalized_count=len(current_completed_sale_items),
                    raw_count=_raw_entity_count(raw_records, "sale", "order"),
                ),
            ),
            DashboardCard(
                label="Средний чек",
                value=_format_money(avg_check_current, currency)
                if avg_check_available
                else "Нет данных",
                note="выручка / закрытые сделки",
                details_href="/api/v1/data/sales",
                previous_value=_format_money(avg_check_previous, currency)
                if avg_check_available
                else None,
                change=_format_change(avg_check_change),
                status=_availability_from_counts(
                    normalized_count=len(current_completed_sales),
                    raw_count=_raw_entity_count(raw_records, "sale", "order"),
                ),
            ),
            DashboardCard(
                label="Возвраты",
                value=_format_money(returns_current, currency)
                if returns_available
                else "Нет данных",
                note="клиентские и товарные возвраты",
                details_href="/api/v1/data/returns",
                previous_value=_format_money(returns_previous, currency)
                if returns_available
                else None,
                change=_format_change(returns_change),
                status=_availability_from_counts(
                    normalized_count=len(current_returned_sales) + len(return_docs_current),
                    raw_count=_raw_entity_count(raw_records, "return"),
                ),
            ),
            DashboardCard(
                label="Клиенты",
                value=str(len(contacts)) if customers_available else "Нет данных",
                note=f"{buyers_current} покупающих клиентов",
                details_href="/api/v1/data/customers",
                previous_value=str(len(contacts)) if customers_available else None,
                change=_format_change(buyers_change),
                status=_availability_from_counts(
                    normalized_count=len(contacts),
                    raw_count=_raw_entity_count(raw_records, "customer", "contact", "person"),
                ),
            ),
        ]

        executive_summary = [
            DashboardCard(
                label="Рост выручки",
                value=_format_change(revenue_change) or "Нет данных",
                note=window.comparison_label,
                details_href="/api/v1/data/sales",
                previous_value=_format_money(gross_sales_previous, currency)
                if revenue_available
                else None,
                change=_format_change(revenue_change),
                status=_availability_from_counts(
                    normalized_count=len(current_completed_sales),
                    raw_count=_raw_entity_count(raw_records, "sale", "order"),
                ),
            ),
            DashboardCard(
                label="Денежный поток",
                value=_format_money(net_cash_flow_current, currency)
                if cash_available
                else "Нет данных",
                note="поступления минус расходы",
                details_href="/api/v1/data/overview",
                previous_value=_format_money(net_cash_flow_previous, currency)
                if cash_available
                else None,
                change=_format_change(cash_flow_change),
                status=_availability_from_counts(
                    normalized_count=len(current_finance),
                    raw_count=_raw_entity_count(raw_records, "cash", "bank", "payment"),
                ),
            ),
            DashboardCard(
                label="Складской риск",
                value=str(
                    len(
                        [
                            balance
                            for balance in current_inventory
                            if _inventory_risk_level(
                                balance=balance,
                                sales_items=current_completed_sale_items,
                                product_external_ids=product_by_id,
                            )
                            in {"Высокий", "Критический"}
                        ],
                    )
                )
                if inventory_balances
                else "Нет данных",
                note="товары с риском дефицита или залеживания",
                details_href="/api/v1/data/inventory",
                status=_availability_from_counts(
                    normalized_count=len(current_inventory),
                    raw_count=_raw_entity_count(raw_records, "inventory", "balance", "stock"),
                ),
            ),
            DashboardCard(
                label="Клиентская активность",
                value=f"{buyers_current} покупателей" if customers_available else "Нет данных",
                note=f"конверсия {_format_percentage(buyer_conversion_current)}",
                details_href="/api/v1/data/customers",
                previous_value=f"{buyers_previous} покупателей" if customers_available else None,
                change=_format_change(
                    _change_percent(buyer_conversion_current, buyer_conversion_previous)
                ),
                status=_availability_from_counts(
                    normalized_count=len(contacts),
                    raw_count=_raw_entity_count(raw_records, "customer", "contact", "person"),
                ),
            ),
        ]

        business_metrics = [
            DashboardMetric(
                label="Выручка",
                value=_format_money(sales_revenue_current, currency)
                if revenue_available
                else "Нет данных",
                note=f"{window.label} · закрытые продажи",
                details_href="/api/v1/data/sales",
                previous_value=_format_money(sales_revenue_previous, currency)
                if revenue_available
                else None,
                change_percent=_format_change(revenue_change),
                direction=_direction_from_change(revenue_change),
                status=_status_from_change(revenue_change, sales_revenue_current),
                data_status=_availability_from_counts(
                    normalized_count=len(current_completed_sales),
                    raw_count=_raw_entity_count(raw_records, "sale", "order"),
                ),
            ),
            DashboardMetric(
                label="Получено денег",
                value=_format_money(cash_received_current, currency)
                if cash_available
                else "Нет данных",
                note="по поступлениям и оплатам",
                details_href="/api/v1/data/payments",
                previous_value=_format_money(cash_received_previous, currency)
                if cash_available
                else None,
                change_percent=_format_change(cash_change),
                direction=_direction_from_change(cash_change),
                status=_status_from_change(cash_change, cash_received_current),
                data_status=_availability_from_counts(
                    normalized_count=len(current_finance) + len(current_payments),
                    raw_count=_raw_entity_count(raw_records, "payment", "cash", "bank"),
                ),
            ),
            DashboardMetric(
                label="Расходы",
                value=_format_money(expense_current, currency)
                if expense_available
                else "Нет данных",
                note="по расходным операциям",
                details_href="/api/v1/data/processing",
                previous_value=_format_money(expense_previous, currency)
                if expense_available
                else None,
                change_percent=_format_change(expense_change),
                direction=_direction_from_change(expense_change),
                status=_status_from_change(expense_change, expense_current),
                data_status=_availability_from_counts(
                    normalized_count=len(current_finance),
                    raw_count=_raw_entity_count(
                        raw_records, "expense", "cash_operation", "bank_operation"
                    ),
                ),
            ),
            DashboardMetric(
                label="Чистый денежный поток",
                value=_format_money(net_cash_flow_current, currency)
                if cash_available
                else "Нет данных",
                note="получено денег минус расходы",
                details_href="/api/v1/data/overview",
                previous_value=_format_money(net_cash_flow_previous, currency)
                if cash_available
                else None,
                change_percent=_format_change(cash_flow_change),
                direction=_direction_from_change(cash_flow_change),
                status=_status_from_change(cash_flow_change, net_cash_flow_current),
                data_status=_availability_from_counts(
                    normalized_count=len(current_finance),
                    raw_count=_raw_entity_count(raw_records, "cash", "bank", "payment"),
                ),
            ),
            DashboardMetric(
                label="Продано единиц",
                value=_format_decimal(sold_units_current) if sold_units_available else "Нет данных",
                note=f"{current_products_sold} уникальных товаров",
                details_href="/api/v1/data/sale-items",
                previous_value=_format_decimal(sold_units_previous)
                if sold_units_available
                else None,
                change_percent=_format_change(sold_units_change),
                direction=_direction_from_change(sold_units_change),
                status=_status_from_change(sold_units_change, sold_units_current),
                data_status=_availability_from_counts(
                    normalized_count=len(current_completed_sale_items),
                    raw_count=_raw_entity_count(raw_records, "sale", "order"),
                ),
            ),
            DashboardMetric(
                label="Средний чек",
                value=_format_money(avg_check_current, currency)
                if avg_check_available
                else "Нет данных",
                note="выручка / закрытые сделки",
                details_href="/api/v1/data/sales",
                previous_value=_format_money(avg_check_previous, currency)
                if avg_check_available
                else None,
                change_percent=_format_change(avg_check_change),
                direction=_direction_from_change(avg_check_change),
                status=_status_from_change(avg_check_change, avg_check_current),
                data_status=_availability_from_counts(
                    normalized_count=len(current_completed_sales),
                    raw_count=_raw_entity_count(raw_records, "sale", "order"),
                ),
            ),
        ]

        structure = _build_structure_cards(
            gross_sales=gross_sales_current,
            cash_received=cash_received_current,
            expenses=expense_current,
            returns=returns_current,
        )
        businesses_detail = _build_business_cards(
            businesses=businesses,
            contacts=contacts,
            sales=current_sales,
            previous_sales=previous_sales,
            sale_items=current_completed_sale_items,
            previous_sale_items=previous_completed_sale_items,
            finance_entries=current_finance,
            previous_finance_entries=previous_finance,
            documents=current_documents,
            previous_documents=previous_documents,
            source_systems=source_systems,
        )
        product_categories_by_id = {
            category.source_external_id: category for category in product_categories
        }
        product_by_id = {product.source_external_id: product for product in products}
        warehouse_by_id = {warehouse.source_external_id: warehouse for warehouse in warehouses}
        contact_by_external_id = {
            contact.external_ref or str(contact.contact_id): contact.full_name
            for contact in contacts
        }
        business_by_id = {business.business_id: business for business in businesses}
        sale_by_external: dict[str, Sale] = {
            sale.source_external_id: sale for sale in current_sales if sale.source_external_id
        }

        recent_sales = _build_recent_sales_cards(
            sales=current_sales,
            contacts=contact_by_external_id,
            businesses=business_by_id,
            sale_items=current_completed_sale_items,
        )
        top_products = _build_top_products_cards(
            products=products,
            categories=product_categories_by_id,
            businesses=business_by_id,
            sale_items=current_completed_sale_items,
            previous_sale_items=previous_completed_sale_items,
            sales_by_external=sale_by_external,
            previous_sales_by_external=previous_sale_by_external,
            inventory_balances=current_inventory,
            previous_inventory_balances=previous_inventory,
        )
        inventory_cards = _build_inventory_cards(
            inventory_balances=current_inventory,
            products=product_by_id,
            warehouses=warehouse_by_id,
            businesses=business_by_id,
            sale_items=current_completed_sale_items,
            sales_by_external=sale_by_external,
        )
        recent_payments = _build_recent_payment_cards(
            payments=current_payments,
            sales_by_external=sale_by_external,
            businesses=business_by_id,
        )

        signals = _build_signals(
            freshness=freshness,
            revenue_change=revenue_change,
            cash_flow_change=cash_flow_change,
            expense_change=expense_change,
            sold_units_change=sold_units_change,
            returns_change=returns_change,
            inventory_risk_count=len(
                [
                    balance
                    for balance in current_inventory
                    if _inventory_risk_level(
                        balance=balance,
                        sales_items=current_completed_sale_items,
                        product_external_ids=product_by_id,
                    )
                    in {"Высокий", "Критический"}
                ],
            ),
            customers_available=customers_available,
        )
        action_center = _build_action_center_cards(
            signals=signals,
            top_products=top_products,
            dead_stock_count=len(
                [
                    card
                    for card in top_products
                    if card.no_sales_days is not None and card.no_sales_days >= 30
                ],
            ),
            returns_current=returns_current,
            cash_flow_current=net_cash_flow_current,
        )
        dead_stock = [
            card
            for card in top_products
            if card.no_sales_days is not None
            and card.no_sales_days >= 30
            and card.stock_quantity != "0"
        ]
        returns_summary = _build_returns_summary_cards(
            current_returns=returns_current,
            previous_returns=returns_previous,
            current_return_sales=current_returned_sales,
            previous_return_sales=previous_returned_sales,
            current_return_documents=return_docs_current,
            previous_return_documents=return_docs_previous,
            currency=currency,
        )
        cash_flow = _build_cash_flow_cards(
            revenue_current=sales_revenue_current,
            revenue_previous=sales_revenue_previous,
            cash_current=cash_received_current,
            cash_previous=cash_received_previous,
            expense_current=expense_current,
            expense_previous=expense_previous,
            net_cash_current=net_cash_flow_current,
            net_cash_previous=net_cash_flow_previous,
            currency=currency,
        )
        customers_summary = _build_customers_summary_cards(
            contacts=contacts,
            buyers_current=buyers_current,
            buyers_previous=buyers_previous,
            repeat_buyers_current=repeat_buyers_current,
            repeat_buyers_previous=repeat_buyers_previous,
            conversion_current=buyer_conversion_current,
            conversion_previous=buyer_conversion_previous,
        )
        seller_performance = _build_seller_performance_cards(
            raw_sales=current_raw_sales,
            previous_raw_sales=previous_raw_sales,
            sale_items=current_completed_sale_items,
            previous_sale_items=previous_completed_sale_items,
            businesses=business_by_id,
            currency=currency,
        )
        recommendations = _build_recommendations_cards(
            revenue_change=revenue_change,
            cash_flow_change=cash_flow_change,
            returns_change=returns_change,
            inventory_risk_count=len(dead_stock),
            customers_available=customers_available,
            sales_available=deals_available,
        )
        availability = _build_availability_cards(
            revenue_available=revenue_available,
            cash_available=cash_available,
            expense_available=expense_available,
            returns_available=returns_available,
            customers_available=customers_available,
            sold_units_available=sold_units_available,
            inventory_available=bool(current_inventory or previous_inventory or inventory_balances),
            sales_available=deals_available,
            raw_records=raw_records,
        )

        analytics_snapshot = BusinessAnalyticsSnapshotService(self.store).build_snapshot(
            business_id=business_id,
            organization_ids=selected_business_ids or None,
            period_key=period.value,
        )
        ai_workspace = AIDashboardComposer().compose(
            analytics_snapshot,
            AIAnalyticsAgent().generate_insights(analytics_snapshot),
        )
        ai_insights = [insight.summary for insight in ai_workspace.insights[:4]]

        return DashboardOverviewResponse(
            generated_at=datetime.now(UTC),
            analysis_engine="Бизнес-аналитика",
            analysis_note=(
                "AI-управляемая сводка по продажам, деньгам, складу, клиентам и рискам."
            ),
            freshness=freshness,
            data_summary=data_summary,
            executive_summary=executive_summary,
            business_metrics=business_metrics,
            trend=revenue_trend.model_copy(
                update={"badge": growth_badge if any(revenue_trend.values) else "Без данных"},
            ),
            signals=signals,
            action_center=action_center,
            structure=structure,
            businesses=businesses_detail,
            organization_performance=businesses_detail,
            recent_sales=recent_sales,
            top_products=top_products,
            inventory=inventory_cards,
            recent_payments=recent_payments,
            dead_stock=dead_stock,
            returns_summary=returns_summary,
            cash_flow=cash_flow,
            customers_summary=customers_summary,
            seller_performance=seller_performance,
            recommendations=recommendations,
            availability=availability,
            ai_insights=ai_insights,
            analytics_snapshot=analytics_snapshot,
            ai_workspace=ai_workspace,
        )


def build_dashboard_overview(
    store: CoreDataReader,
    *,
    business_id: UUID | None = None,
    organization_ids: list[UUID] | None = None,
    period: DashboardPeriod = DashboardPeriod.LAST_12_MONTHS,
    channel: MarketingChannel | None = None,
) -> DashboardOverviewResponse:
    """Build a presentation-ready dashboard overview from the core store."""

    return BusinessAIAnalyticsEngine(store).build_overview(
        business_id=business_id,
        organization_ids=organization_ids,
        period=period,
        channel=channel,
    )


def _build_revenue_trend(items: list) -> DashboardTrend:
    now = datetime.now(UTC)
    window = _last_12_months(now)
    monthly_totals = {key: Decimal("0") for key in window}

    for item in items:
        occurred_at = getattr(item, "occurred_at", None) or getattr(item, "sale_at", None)
        if occurred_at is None:
            continue
        timestamp = occurred_at.astimezone(UTC)
        key = (timestamp.year, timestamp.month)
        if key in monthly_totals:
            amount = getattr(item, "amount", None)
            if amount is None:
                continue
            monthly_totals[key] += Decimal(amount)

    labels = [MONTH_LABELS[month - 1] for year, month in window]
    values = [float(total) for total in monthly_totals.values()]
    source_label = "финансового ядра" if items and hasattr(items[0], "entry_type") else "продаж"

    return DashboardTrend(
        title="Динамика бизнеса",
        description=f"Выручка за последние 12 месяцев из {source_label}.",
        badge="Без данных" if not any(values) else "Последние 12 мес.",
        labels=labels,
        values=values,
    )


def _period_start(period: DashboardPeriod) -> datetime | None:
    now = datetime.now(UTC)
    if period == DashboardPeriod.ALL:
        return None
    if period == DashboardPeriod.LAST_30_DAYS:
        return now - timedelta(days=30)
    if period == DashboardPeriod.LAST_90_DAYS:
        return now - timedelta(days=90)
    return now - timedelta(days=365)


def _batch_timestamp(batch) -> datetime | None:
    if batch.finished_at is not None:
        return batch.finished_at.astimezone(UTC)
    if batch.started_at is not None:
        return batch.started_at.astimezone(UTC)
    return None


def _item_last_activity_at(item: SaleItem) -> datetime:
    if item.source_updated_at is not None:
        return item.source_updated_at.astimezone(UTC)
    if item.source_created_at is not None:
        return item.source_created_at.astimezone(UTC)
    return item.imported_at.astimezone(UTC)


def _build_structure_cards(
    *,
    sales: list,
    finance_entries: list,
    marketing_activities: list,
    contacts: list,
) -> list[DashboardStructureItem]:
    revenue_count = sum(
        1 for entry in finance_entries if entry.entry_type == FinanceEntryType.REVENUE
    )
    marketing_conversions = sum(activity.conversions for activity in marketing_activities)
    counts = [
        (
            "Продажи",
            len(sales),
            f"{sum(1 for sale in sales if sale.stage == SaleStage.WON)} закрыто",
        ),
        (
            "Финансы",
            len(finance_entries),
            f"{revenue_count} доходов",
        ),
        (
            "Маркетинг",
            len(marketing_activities),
            f"{marketing_conversions} конверсий",
        ),
        ("Контакты", len(contacts), "связанные CRM-записи"),
    ]
    total = sum(count for _, count, _ in counts)
    total = total or 1

    cards: list[DashboardStructureItem] = []
    for index, (label, count, note) in enumerate(counts):
        share = round(count / total * 100)
        cards.append(
            DashboardStructureItem(
                label=label,
                value=f"{share}%",
                note=f"{count} записей • {note}",
                color=STRUCTURE_COLORS[index],
            ),
        )
    return cards


def _build_business_cards(
    *,
    businesses: list,
    contacts: list,
    sales: list,
    marketing_activities: list,
    finance_entries: list,
    source_systems: list,
) -> list[DashboardBusinessCard]:
    contact_counts = Counter(contact.business_id for contact in contacts)
    sales_counts = Counter(sale.business_id for sale in sales)
    marketing_counts = Counter(activity.business_id for activity in marketing_activities)
    finance_counts = Counter(entry.business_id for entry in finance_entries)
    source_counts = Counter(source_system.business_id for source_system in source_systems)

    revenue_by_business: dict[UUID, Decimal] = {}
    expense_by_business: dict[UUID, Decimal] = {}
    for entry in finance_entries:
        if entry.entry_type == FinanceEntryType.REVENUE:
            revenue_by_business[entry.business_id] = (
                revenue_by_business.get(
                    entry.business_id,
                    Decimal("0"),
                )
                + entry.amount
            )
        elif entry.entry_type == FinanceEntryType.EXPENSE:
            expense_by_business[entry.business_id] = (
                expense_by_business.get(
                    entry.business_id,
                    Decimal("0"),
                )
                + entry.amount
            )

    cards: list[DashboardBusinessCard] = []
    for business in sorted(
        businesses,
        key=lambda item: ((item.name or "").casefold(), (item.external_ref or "").casefold()),
    ):
        revenue_total = revenue_by_business.get(business.business_id, Decimal("0"))
        expense_total = expense_by_business.get(business.business_id, Decimal("0"))
        business_currency = _dominant_currency(
            [entry for entry in finance_entries if entry.business_id == business.business_id],
        )
        cards.append(
            DashboardBusinessCard(
                business_id=business.business_id,
                name=business.name,
                external_ref=business.external_ref,
                source_systems=source_counts.get(business.business_id, 0),
                contacts=contact_counts.get(business.business_id, 0),
                sales=sales_counts.get(business.business_id, 0),
                marketing_activities=marketing_counts.get(business.business_id, 0),
                finance_entries=finance_counts.get(business.business_id, 0),
                revenue=_format_money(revenue_total, business_currency),
                expense=_format_money(expense_total, business_currency),
                net_flow=_format_money(revenue_total - expense_total, business_currency),
            ),
        )
    return cards


def _build_recent_sales_cards(
    *,
    sales: list[Sale],
    contacts: dict[str, str],
    businesses: dict[UUID, object],
    sale_items: list[SaleItem],
) -> list[DashboardSaleItemCard]:
    item_counts = Counter(item.sale_external_id for item in sale_items)
    product_counts: dict[str, set[str]] = {}
    for item in sale_items:
        product_counts.setdefault(item.sale_external_id, set()).add(item.product_external_id or "")

    cards: list[DashboardSaleItemCard] = []
    for sale in sorted(sales, key=lambda item: item.sale_at, reverse=True):
        business = businesses.get(sale.organization_id)
        cards.append(
            DashboardSaleItemCard(
                sale_id=sale.id,
                sale_number=sale.sale_number or sale.source_external_id,
                business_id=sale.organization_id,
                business_name=getattr(business, "name", "Бизнес") or "Бизнес",
                contact_name=contacts.get(sale.customer_external_id or ""),
                external_ref=sale.source_external_id,
                amount=_format_money(sale.amount, sale.currency),
                currency=sale.currency,
                stage=_sale_status_label(sale.status),
                sale_at=sale.sale_at,
                items_count=item_counts.get(sale.source_external_id, 0),
                products_count=len(
                    {item for item in product_counts.get(sale.source_external_id, set()) if item}
                ),
            ),
        )
    return cards[:8]


def _build_top_products_cards(
    *,
    products: list[Product],
    categories: dict[str, ProductCategory],
    businesses: dict[UUID, object],
    sale_items: list[SaleItem],
    sales_by_external: dict[str, Sale],
    inventory_balances: list[InventoryBalance],
) -> list[DashboardProductCard]:
    sold_quantity_by_product: dict[str, Decimal] = {}
    sold_amount_by_product: dict[str, Decimal] = {}
    last_sold_at_by_product: dict[str, datetime] = {}
    for item in sale_items:
        if item.product_external_id is None:
            continue
        sold_quantity_by_product[item.product_external_id] = (
            sold_quantity_by_product.get(
                item.product_external_id,
                Decimal("0"),
            )
            + item.quantity
        )
        sold_amount_by_product[item.product_external_id] = (
            sold_amount_by_product.get(
                item.product_external_id,
                Decimal("0"),
            )
            + item.amount
        )
        sale = sales_by_external.get(item.sale_external_id)
        if sale is not None:
            current_last = last_sold_at_by_product.get(item.product_external_id)
            if current_last is None or sale.sale_at > current_last:
                last_sold_at_by_product[item.product_external_id] = sale.sale_at

    stock_by_product: dict[str, Decimal] = {}
    for balance in inventory_balances:
        stock_by_product[balance.product_external_id] = (
            stock_by_product.get(
                balance.product_external_id,
                Decimal("0"),
            )
            + balance.quantity
        )

    cards: list[DashboardProductCard] = []
    for product in sorted(
        products,
        key=lambda item: (
            -(sold_amount_by_product.get(item.source_external_id, Decimal("0"))),
            (item.name or "").casefold(),
        ),
    ):
        business = businesses.get(product.organization_id)
        category = categories.get(product.category_external_id or "")
        cards.append(
            DashboardProductCard(
                product_id=product.id,
                business_id=product.organization_id,
                business_name=getattr(business, "name", "Бизнес") or "Бизнес",
                name=product.name,
                category=category.name if category is not None else None,
                sku=product.sku,
                unit=product.unit,
                sold_quantity=_format_decimal(
                    sold_quantity_by_product.get(product.source_external_id, Decimal("0")),
                ),
                sold_amount=_format_money(
                    sold_amount_by_product.get(product.source_external_id, Decimal("0")),
                    _dominant_currency(sale_items),
                ),
                stock_quantity=_format_decimal(
                    stock_by_product.get(product.source_external_id, Decimal("0")),
                ),
                last_sold_at=last_sold_at_by_product.get(product.source_external_id),
            ),
        )
    return cards[:8]


def _build_inventory_cards(
    *,
    inventory_balances: list[InventoryBalance],
    products: dict[str, Product],
    warehouses: dict[str, Warehouse],
    businesses: dict[UUID, object],
) -> list[DashboardInventoryCard]:
    cards: list[DashboardInventoryCard] = []
    for balance in sorted(
        inventory_balances,
        key=lambda item: (item.quantity, item.balance_at),
        reverse=True,
    ):
        product = products.get(balance.product_external_id)
        warehouse = warehouses.get(balance.warehouse_external_id)
        business = businesses.get(balance.organization_id)
        cards.append(
            DashboardInventoryCard(
                warehouse_name=(
                    getattr(warehouse, "name", "Склад") if warehouse is not None else "Склад"
                ),
                product_name=(
                    getattr(product, "name", "Товар") if product is not None else "Товар"
                ),
                business_id=balance.organization_id,
                business_name=getattr(business, "name", "Бизнес") or "Бизнес",
                quantity=_format_decimal(balance.quantity),
                balance_at=balance.balance_at,
            ),
        )
    return cards[:8]


def _build_recent_payment_cards(
    *,
    payments: list[Payment],
    sales_by_external: dict[str, Sale],
    businesses: dict[UUID, object],
) -> list[DashboardPaymentCard]:
    cards: list[DashboardPaymentCard] = []
    for payment in sorted(payments, key=lambda item: item.paid_at, reverse=True):
        sale = sales_by_external.get(payment.sale_external_id or "")
        business = businesses.get(payment.organization_id)
        cards.append(
            DashboardPaymentCard(
                payment_id=payment.id,
                business_id=payment.organization_id,
                business_name=getattr(business, "name", "Бизнес") or "Бизнес",
                sale_number=sale.sale_number if sale is not None else payment.sale_external_id,
                amount=_format_money(payment.amount, payment.currency),
                currency=payment.currency,
                paid_at=payment.paid_at,
                method=payment.method,
            ),
        )
    return cards[:8]


def _build_signals(
    *,
    freshness: str,
    net_cash_flow: Decimal,
    marketing_spend_total: Decimal,
    marketing_conversions: int,
    open_sales: int,
    won_sales: int,
    businesses: int,
) -> list[DashboardSignal]:
    signals: list[DashboardSignal] = []

    if businesses == 0:
        signals.append(
            DashboardSignal(
                title="История ещё не загружена",
                badge="Пусто",
                note="Подключите SmartUp-историю или импортируйте бандл.",
            ),
        )
    else:
        signals.append(
            DashboardSignal(
                title="Данные загружены",
                badge="ОК",
                note=f"Свежесть ядра: {freshness}.",
            ),
        )

    if net_cash_flow < 0:
        signals.append(
            DashboardSignal(
                title="Отрицательный денежный поток",
                badge="Финансы",
                note="Расходы выше выручки, нужно проверить структуру затрат.",
            ),
        )
    else:
        signals.append(
            DashboardSignal(
                title="Денежный поток под контролем",
                badge="Финансы",
                note="Выручка перекрывает расходы в текущем периоде.",
            ),
        )

    if open_sales > won_sales:
        signals.append(
            DashboardSignal(
                title="Воронка требует внимания",
                badge="Продажи",
                note=f"{open_sales} сделок в работе против {won_sales} закрытых.",
            ),
        )
    else:
        signals.append(
            DashboardSignal(
                title="Воронка стабильна",
                badge="Продажи",
                note=f"{won_sales} закрытых сделок и {open_sales} активных.",
            ),
        )

    if marketing_spend_total > 0 and marketing_conversions == 0:
        signals.append(
            DashboardSignal(
                title="Маркетинг без конверсий",
                badge="Рост",
                note="Есть расходы на продвижение, но нет подтверждённых конверсий.",
            ),
        )
    elif marketing_spend_total > 0:
        signals.append(
            DashboardSignal(
                title="Маркетинг даёт результат",
                badge="Рост",
                note=f"{marketing_conversions} конверсий при активном бюджете.",
            ),
        )
    else:
        signals.append(
            DashboardSignal(
                title="Маркетинг пока не загружен",
                badge="Пусто",
                note="После миграции здесь появятся каналы и эффективность.",
            ),
        )

    return signals[:4]


def _build_ai_insights(
    *,
    businesses: int,
    contacts: int,
    source_systems: int,
    open_sales: int,
    won_sales: int,
    net_cash_flow: Decimal,
    marketing_spend_total: Decimal,
    marketing_conversions: int,
    cash_currency: str,
    freshness: str,
) -> list[str]:
    insights = [
        (
            "База содержит "
            f"{businesses} бизнесов, {contacts} контактов и {source_systems} источников."
        ),
        f"Сделок в работе: {open_sales}, закрытых: {won_sales}.",
        f"Чистый поток: {_format_money(net_cash_flow, cash_currency)}.",
    ]

    if marketing_spend_total > 0:
        marketing_line = (
            f"Маркетинг потратил {_format_money(marketing_spend_total, cash_currency)} "
            f"и дал {marketing_conversions} конверсий."
        )
        insights.append(marketing_line)
    else:
        insights.append("Маркетинговые данные пока не загружены.")

    insights.append(f"Свежесть ядра: {freshness}.")
    return insights[:4]


def _latest_activity_at(
    *,
    sales: list,
    marketing_activities: list,
    finance_entries: list,
    ingestion_batches: list,
) -> datetime | None:
    timestamps: list[datetime] = []
    for item in (*sales, *marketing_activities, *finance_entries):
        occurred_at = getattr(item, "occurred_at", None)
        if occurred_at is not None:
            timestamps.append(occurred_at.astimezone(UTC))
    for batch in ingestion_batches:
        for attribute in ("finished_at", "started_at"):
            value = getattr(batch, attribute, None)
            if value is not None:
                timestamps.append(value.astimezone(UTC))
                break
    if not timestamps:
        return None
    return max(timestamps)


def _humanize_freshness(latest_activity_at: datetime | None) -> str:
    if latest_activity_at is None:
        return "История не загружена"

    delta = datetime.now(UTC) - latest_activity_at
    if delta < timedelta(minutes=1):
        return "только что"
    if delta < timedelta(hours=1):
        return f"{max(1, round(delta.total_seconds() / 60))} мин назад"
    if delta < timedelta(days=1):
        return f"{max(1, round(delta.total_seconds() / 3600))} ч назад"
    return f"{delta.days} дн назад"


def _last_12_months(now: datetime) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    year = now.year
    month = now.month
    for _ in range(12):
        months.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    months.reverse()
    return months


def _growth_badge(values: list[float]) -> str:
    if len(values) < 2:
        return "Новые данные"
    previous = values[-2]
    current = values[-1]
    if previous == 0:
        return "Новый рост" if current > 0 else "Без роста"
    delta = (current - previous) / previous * 100
    return f"{delta:+.0f}%"


def _dominant_currency(*collections: list) -> str | None:
    currencies = [
        getattr(item, "currency", None)
        for collection in collections
        for item in collection
        if getattr(item, "currency", None)
    ]
    if not currencies:
        return None
    return Counter(currencies).most_common(1)[0][0]


def _normalize_currency_label(currency: str | None) -> str | None:
    if currency is None:
        return None

    text = str(currency).strip()
    if not text:
        return None

    return NUMERIC_CURRENCY_LABELS.get(text, text.upper())


def _format_money(amount: Decimal, currency: str | None) -> str:
    text = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    if text.endswith(",00"):
        text = text[:-3]
    currency = _normalize_currency_label(currency)
    return f"{text} {currency}" if currency else text


def _format_decimal(amount: Decimal) -> str:
    text = f"{amount:f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _format_ratio(amount: Decimal, divisor: int, currency: str | None) -> str:
    if divisor == 0:
        return "—"
    return _format_money(amount / Decimal(divisor), currency)


def _format_percentage(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value:.0f}%".replace(".", ",")


def _sale_status_label(value: str) -> str:
    mapping = {
        "won": "Закрыта",
        "lost": "Потеряна",
        "refunded": "Возврат",
        "qualified": "Квалификация",
        "lead": "Лид",
    }
    return mapping.get(value.lower(), value or "Неизвестно")


def _is_completed_sale(sale: Sale) -> bool:
    status = (sale.status or "").strip().casefold()
    return status in {SaleStage.WON.value, SaleStage.QUALIFIED.value, "new", "approved"}


def _sale_item_belongs_to_completed_sale(
    item: SaleItem,
    *,
    sale_ids: set[UUID],
    sale_external_ids: set[str],
) -> bool:
    if item.sale_id is not None and item.sale_id in sale_ids:
        return True
    return bool(item.sale_external_id and item.sale_external_id in sale_external_ids)


def _romi(revenue_total: Decimal, marketing_spend_total: Decimal) -> Decimal | None:
    if marketing_spend_total <= 0:
        return None
    return ((revenue_total - marketing_spend_total) / marketing_spend_total) * Decimal("100")


def _dashboard_period_window(period: DashboardPeriod) -> DashboardPeriodWindow:
    now = datetime.now(UTC)
    if period == DashboardPeriod.ALL:
        return DashboardPeriodWindow(
            current_start=None,
            current_end=None,
            previous_start=None,
            previous_end=None,
            label="за всё время",
            comparison_label="исторически",
        )

    if period == DashboardPeriod.LAST_30_DAYS:
        current_start = now - timedelta(days=30)
        previous_start = now - timedelta(days=60)
        previous_end = current_start
        return DashboardPeriodWindow(
            current_start=current_start,
            current_end=now,
            previous_start=previous_start,
            previous_end=previous_end,
            label="за 30 дней",
            comparison_label="к предыдущим 30 дням",
        )

    if period == DashboardPeriod.LAST_90_DAYS:
        current_start = now - timedelta(days=90)
        previous_start = now - timedelta(days=180)
        previous_end = current_start
        return DashboardPeriodWindow(
            current_start=current_start,
            current_end=now,
            previous_start=previous_start,
            previous_end=previous_end,
            label="за 90 дней",
            comparison_label="к предыдущим 90 дням",
        )

    current_start = now - timedelta(days=365)
    previous_start = now - timedelta(days=730)
    previous_end = current_start
    return DashboardPeriodWindow(
        current_start=current_start,
        current_end=now,
        previous_start=previous_start,
        previous_end=previous_end,
        label="за 12 месяцев",
        comparison_label="к предыдущим 12 месяцам",
    )


def _period_filter(
    items: list[Any], *, timestamp_getter, window: DashboardPeriodWindow
) -> list[Any]:
    if window.current_start is None:
        return list(items)
    filtered = []
    for item in items:
        timestamp = timestamp_getter(item)
        if timestamp is None:
            continue
        if timestamp < window.current_start:
            continue
        if window.current_end is not None and timestamp > window.current_end:
            continue
        filtered.append(item)
    return filtered


def _previous_period_filter(
    items: list[Any],
    *,
    timestamp_getter,
    window: DashboardPeriodWindow,
) -> list[Any]:
    if window.previous_start is None:
        return []
    filtered = []
    for item in items:
        timestamp = timestamp_getter(item)
        if timestamp is None:
            continue
        if timestamp < window.previous_start:
            continue
        if window.previous_end is not None and timestamp > window.previous_end:
            continue
        filtered.append(item)
    return filtered


def _change_percent(current: Decimal, previous: Decimal) -> Decimal | None:
    if previous == 0:
        return None
    return ((current - previous) / previous) * Decimal("100")


def _direction_from_change(change: Decimal | None) -> DashboardDirection:
    if change is None:
        return DashboardDirection.NONE
    if change > 0:
        return DashboardDirection.UP
    if change < 0:
        return DashboardDirection.DOWN
    return DashboardDirection.FLAT


def _status_from_change(change: Decimal | None, current_value: Decimal) -> str:
    if change is None:
        return "Недостаточно данных"
    if change > 15:
        return "Сильный рост"
    if change > 0:
        return "Рост"
    if change < -15:
        return "Сильное снижение"
    if change < 0:
        return "Снижение"
    if current_value == 0:
        return "Нет движения"
    return "Стабильно"


def _format_change(change: Decimal | None) -> str | None:
    if change is None:
        return None
    sign = "+" if change > 0 else ""
    return f"{sign}{change:.1f}%".replace(".", ",")


def _format_change_arrow(change: Decimal | None) -> str:
    if change is None:
        return "→"
    if change > 0:
        return "↑"
    if change < 0:
        return "↓"
    return "→"


def _availability_from_counts(
    *,
    normalized_count: int,
    raw_count: int,
    error_count: int = 0,
) -> DataAvailabilityStatus:
    if error_count > 0 and normalized_count == 0 and raw_count == 0:
        return DataAvailabilityStatus.ERROR
    if normalized_count > 0 and raw_count > 0:
        return DataAvailabilityStatus.AVAILABLE
    if normalized_count > 0:
        return DataAvailabilityStatus.AVAILABLE
    if raw_count > 0:
        return DataAvailabilityStatus.SYNCING
    return DataAvailabilityStatus.UNAVAILABLE


def _business_date(item: Any) -> datetime | None:
    for attribute in (
        "sale_at",
        "occurred_at",
        "paid_at",
        "balance_at",
        "visited_at",
        "document_at",
    ):
        value = getattr(item, attribute, None)
        if value is not None:
            return value.astimezone(UTC)
    return None


def _month_bucket(timestamp: datetime) -> tuple[int, int]:
    timestamp = timestamp.astimezone(UTC)
    return timestamp.year, timestamp.month


def _raw_entity_count(raw_records: list[Any], *needles: str) -> int:
    terms = tuple(needle.casefold() for needle in needles if needle)
    if not terms:
        return 0
    count = 0
    for record in raw_records:
        entity_type = getattr(record, "entity_type", "") or ""
        entity_text = entity_type.casefold()
        if any(term in entity_text for term in terms):
            count += 1
    return count


def _inventory_risk_level(
    *,
    balance: InventoryBalance,
    sales_items: list[SaleItem],
    product_external_ids: dict[str, Product],
) -> str:
    if balance.quantity <= 0:
        return "Нет"

    if balance.product_external_id not in product_external_ids:
        return "Нет данных"

    sold_quantity = sum(
        item.quantity
        for item in sales_items
        if item.product_external_id == balance.product_external_id
    )
    if sold_quantity <= 0:
        return "Критический"

    avg_daily_sales = sold_quantity / Decimal("30")
    if avg_daily_sales <= 0:
        return "Критический"

    days_of_stock = balance.quantity / avg_daily_sales
    if days_of_stock >= 90:
        return "Критический"
    if days_of_stock >= 45:
        return "Высокий"
    if days_of_stock >= 15:
        return "Средний"
    return "Низкий"


def _build_structure_cards(
    *,
    gross_sales: Decimal,
    cash_received: Decimal,
    expenses: Decimal,
    returns: Decimal,
) -> list[DashboardStructureItem]:
    amounts = [
        ("Продажи", gross_sales),
        ("Деньги", cash_received),
        ("Расходы", expenses),
        ("Возвраты", returns),
    ]
    total = sum((amount for _, amount in amounts), Decimal("0"))
    if total <= 0:
        return [
            DashboardStructureItem(
                label=label, value="0%", note="Нет данных", color=STRUCTURE_COLORS[index]
            )
            for index, (label, _) in enumerate(amounts)
        ]

    cards: list[DashboardStructureItem] = []
    for index, (label, amount) in enumerate(amounts):
        share = round((amount / total) * Decimal("100"))
        cards.append(
            DashboardStructureItem(
                label=label,
                value=f"{share}%",
                note=_format_money(amount, None),
                color=STRUCTURE_COLORS[index],
            ),
        )
    return cards


def _build_business_cards(
    *,
    businesses: list,
    contacts: list,
    sales: list[Sale],
    previous_sales: list[Sale],
    sale_items: list[SaleItem],
    previous_sale_items: list[SaleItem],
    finance_entries: list,
    previous_finance_entries: list,
    documents: list,
    previous_documents: list,
    source_systems: list,
) -> list[DashboardBusinessCard]:
    contact_counts = Counter(contact.business_id for contact in contacts)
    sales_counts = Counter(sale.organization_id for sale in sales)
    finance_counts = Counter(entry.business_id for entry in finance_entries)
    source_counts = Counter(source_system.business_id for source_system in source_systems)

    revenue_by_business: dict[UUID, Decimal] = {}
    previous_revenue_by_business: dict[UUID, Decimal] = {}
    expense_by_business: dict[UUID, Decimal] = {}
    previous_expense_by_business: dict[UUID, Decimal] = {}
    cash_by_business: dict[UUID, Decimal] = {}
    previous_cash_by_business: dict[UUID, Decimal] = {}
    returns_by_business: dict[UUID, Decimal] = {}
    previous_returns_by_business: dict[UUID, Decimal] = {}
    sold_units_by_business: dict[UUID, Decimal] = {}
    previous_sold_units_by_business: dict[UUID, Decimal] = {}
    completed_sales_by_business: Counter[UUID] = Counter()
    previous_completed_sales_by_business: Counter[UUID] = Counter()

    for sale in sales:
        if _is_completed_sale(sale):
            revenue_by_business[sale.organization_id] = (
                revenue_by_business.get(sale.organization_id, Decimal("0")) + sale.amount
            )
            completed_sales_by_business[sale.organization_id] += 1
        elif (sale.status or "").strip().casefold() == "refunded":
            returns_by_business[sale.organization_id] = (
                returns_by_business.get(sale.organization_id, Decimal("0")) + sale.amount
            )

    for sale in previous_sales:
        if _is_completed_sale(sale):
            previous_revenue_by_business[sale.organization_id] = (
                previous_revenue_by_business.get(sale.organization_id, Decimal("0")) + sale.amount
            )
            previous_completed_sales_by_business[sale.organization_id] += 1
        elif (sale.status or "").strip().casefold() == "refunded":
            previous_returns_by_business[sale.organization_id] = (
                previous_returns_by_business.get(sale.organization_id, Decimal("0")) + sale.amount
            )

    for entry in finance_entries:
        if entry.entry_type == FinanceEntryType.EXPENSE:
            expense_by_business[entry.business_id] = (
                expense_by_business.get(entry.business_id, Decimal("0")) + entry.amount
            )
        elif entry.entry_type == FinanceEntryType.REVENUE:
            cash_by_business[entry.business_id] = (
                cash_by_business.get(entry.business_id, Decimal("0")) + entry.amount
            )

    for entry in previous_finance_entries:
        if entry.entry_type == FinanceEntryType.EXPENSE:
            previous_expense_by_business[entry.business_id] = (
                previous_expense_by_business.get(entry.business_id, Decimal("0")) + entry.amount
            )
        elif entry.entry_type == FinanceEntryType.REVENUE:
            previous_cash_by_business[entry.business_id] = (
                previous_cash_by_business.get(entry.business_id, Decimal("0")) + entry.amount
            )

    for item in sale_items:
        sold_units_by_business[item.organization_id] = (
            sold_units_by_business.get(item.organization_id, Decimal("0")) + item.quantity
        )

    for item in previous_sale_items:
        previous_sold_units_by_business[item.organization_id] = (
            previous_sold_units_by_business.get(item.organization_id, Decimal("0")) + item.quantity
        )

    for document in documents:
        if document.document_type in {"return", "return_to_supplier"}:
            returns_by_business[document.organization_id] = (
                returns_by_business.get(document.organization_id, Decimal("0")) + document.amount
            )

    for document in previous_documents:
        if document.document_type in {"return", "return_to_supplier"}:
            previous_returns_by_business[document.organization_id] = (
                previous_returns_by_business.get(document.organization_id, Decimal("0"))
                + document.amount
            )

    cards: list[DashboardBusinessCard] = []
    for rank, business in enumerate(
        sorted(
            businesses,
            key=lambda item: (
                -(revenue_by_business.get(item.business_id, Decimal("0"))),
                (item.name or "").casefold(),
            ),
        ),
        start=1,
    ):
        revenue_current = revenue_by_business.get(business.business_id, Decimal("0"))
        revenue_previous = previous_revenue_by_business.get(business.business_id, Decimal("0"))
        change = _change_percent(revenue_current, revenue_previous)
        completed_sales_count = completed_sales_by_business.get(business.business_id, 0)
        previous_completed_sales_count = previous_completed_sales_by_business.get(
            business.business_id, 0
        )
        business_currency = _dominant_currency(
            [entry for entry in finance_entries if entry.business_id == business.business_id],
            [sale for sale in sales if sale.organization_id == business.business_id],
        )
        if business_currency is None:
            business_currency = _dominant_currency(
                [
                    entry
                    for entry in previous_finance_entries
                    if entry.business_id == business.business_id
                ],
                [sale for sale in previous_sales if sale.organization_id == business.business_id],
            )

        cards.append(
            DashboardBusinessCard(
                business_id=business.business_id,
                name=business.name,
                external_ref=business.external_ref,
                source_systems=source_counts.get(business.business_id, 0),
                contacts=contact_counts.get(business.business_id, 0),
                sales=sales_counts.get(business.business_id, 0),
                marketing_activities=0,
                finance_entries=finance_counts.get(business.business_id, 0),
                revenue=_format_money(revenue_current, business_currency),
                expense=_format_money(
                    expense_by_business.get(business.business_id, Decimal("0")), business_currency
                ),
                net_flow=_format_money(
                    revenue_current
                    + cash_by_business.get(business.business_id, Decimal("0"))
                    - expense_by_business.get(business.business_id, Decimal("0")),
                    business_currency,
                ),
                rank=rank,
                change_percent=_format_change(change),
                direction=_direction_from_change(change),
                sold_units=_format_decimal(
                    sold_units_by_business.get(business.business_id, Decimal("0"))
                ),
                average_check=_format_money(
                    revenue_current / Decimal(completed_sales_count)
                    if completed_sales_count
                    else Decimal("0"),
                    business_currency,
                )
                if completed_sales_count
                else "—",
                returns=_format_money(
                    returns_by_business.get(business.business_id, Decimal("0")), business_currency
                ),
                cash_received=_format_money(
                    cash_by_business.get(business.business_id, Decimal("0")), business_currency
                ),
                data_status=DataAvailabilityStatus.AVAILABLE
                if revenue_current
                or revenue_previous
                or sales_counts.get(business.business_id, 0)
                or previous_completed_sales_count
                else DataAvailabilityStatus.UNAVAILABLE,
            ),
        )
    return cards


def _build_top_products_cards(
    *,
    products: list[Product],
    categories: dict[str, ProductCategory],
    businesses: dict[UUID, object],
    sale_items: list[SaleItem],
    previous_sale_items: list[SaleItem],
    sales_by_external: dict[str, Sale],
    previous_sales_by_external: dict[str, Sale],
    inventory_balances: list[InventoryBalance],
    previous_inventory_balances: list[InventoryBalance],
) -> list[DashboardProductCard]:
    sold_quantity_by_product: dict[str, Decimal] = {}
    sold_amount_by_product: dict[str, Decimal] = {}
    previous_sold_quantity_by_product: dict[str, Decimal] = {}
    previous_sold_amount_by_product: dict[str, Decimal] = {}
    last_sold_at_by_product: dict[str, datetime] = {}
    for item in sale_items:
        if item.product_external_id is None:
            continue
        sold_quantity_by_product[item.product_external_id] = (
            sold_quantity_by_product.get(item.product_external_id, Decimal("0")) + item.quantity
        )
        sold_amount_by_product[item.product_external_id] = (
            sold_amount_by_product.get(item.product_external_id, Decimal("0")) + item.amount
        )
        sale = sales_by_external.get(item.sale_external_id)
        if sale is not None:
            current_last = last_sold_at_by_product.get(item.product_external_id)
            if current_last is None or sale.sale_at > current_last:
                last_sold_at_by_product[item.product_external_id] = sale.sale_at

    for item in previous_sale_items:
        if item.product_external_id is None:
            continue
        previous_sold_quantity_by_product[item.product_external_id] = (
            previous_sold_quantity_by_product.get(item.product_external_id, Decimal("0"))
            + item.quantity
        )
        previous_sold_amount_by_product[item.product_external_id] = (
            previous_sold_amount_by_product.get(item.product_external_id, Decimal("0"))
            + item.amount
        )
        sale = previous_sales_by_external.get(item.sale_external_id)
        if sale is not None:
            current_last = last_sold_at_by_product.get(item.product_external_id)
            if current_last is None or sale.sale_at > current_last:
                last_sold_at_by_product[item.product_external_id] = sale.sale_at

    stock_by_product: dict[str, Decimal] = {}
    for balance in inventory_balances:
        stock_by_product[balance.product_external_id] = (
            stock_by_product.get(balance.product_external_id, Decimal("0")) + balance.quantity
        )

    previous_stock_by_product: dict[str, Decimal] = {}
    for balance in previous_inventory_balances:
        previous_stock_by_product[balance.product_external_id] = (
            previous_stock_by_product.get(balance.product_external_id, Decimal("0"))
            + balance.quantity
        )

    total_sold_amount = sum(sold_amount_by_product.values(), Decimal("0")) or Decimal("1")
    cards: list[DashboardProductCard] = []
    for product in sorted(
        products,
        key=lambda item: (
            -(sold_amount_by_product.get(item.source_external_id, Decimal("0"))),
            (item.name or "").casefold(),
        ),
    ):
        business = businesses.get(product.organization_id)
        category = categories.get(product.category_external_id or "")
        current_amount = sold_amount_by_product.get(product.source_external_id, Decimal("0"))
        previous_amount = previous_sold_amount_by_product.get(
            product.source_external_id, Decimal("0")
        )
        current_quantity = sold_quantity_by_product.get(product.source_external_id, Decimal("0"))
        stock_quantity = stock_by_product.get(product.source_external_id, Decimal("0"))
        previous_stock = previous_stock_by_product.get(product.source_external_id, Decimal("0"))
        last_sold_at = last_sold_at_by_product.get(product.source_external_id)
        no_sales_days = (
            (datetime.now(UTC) - last_sold_at).days if last_sold_at is not None else None
        )
        average_daily_sales = (
            current_quantity / Decimal("30") if current_quantity > 0 else Decimal("0")
        )
        stock_days = None
        if average_daily_sales > 0:
            stock_days = _format_decimal(stock_quantity / average_daily_sales)
        change_percent = _change_percent(current_amount, previous_amount)
        if current_quantity <= 0 and stock_quantity > 0:
            status = "Нет продаж"
        elif no_sales_days is not None and no_sales_days >= 60:
            status = "Залеживается"
        elif current_amount >= previous_amount:
            status = "Бестселлер"
        else:
            status = "Стабильно"

        cards.append(
            DashboardProductCard(
                product_id=product.id,
                business_id=product.organization_id,
                business_name=getattr(business, "name", "Бизнес") or "Бизнес",
                name=product.name,
                category=category.name if category is not None else None,
                sku=product.sku,
                unit=product.unit,
                sold_quantity=_format_decimal(current_quantity),
                sold_amount=_format_money(
                    current_amount, _dominant_currency(sale_items, previous_sale_items)
                ),
                stock_quantity=_format_decimal(stock_quantity),
                last_sold_at=last_sold_at,
                share=f"{round((current_amount / total_sold_amount) * Decimal('100'))}%"
                if current_amount > 0
                else "0%",
                change_percent=_format_change(change_percent),
                direction=_direction_from_change(change_percent),
                no_sales_days=no_sales_days,
                stock_days=stock_days,
                status=status,
                details_href="/api/v1/data/products",
                data_status=DataAvailabilityStatus.AVAILABLE
                if current_amount or stock_quantity or previous_amount or previous_stock
                else DataAvailabilityStatus.UNAVAILABLE,
            ),
        )
    return cards[:8]


def _build_inventory_cards(
    *,
    inventory_balances: list[InventoryBalance],
    products: dict[str, Product],
    warehouses: dict[str, Warehouse],
    businesses: dict[UUID, object],
    sale_items: list[SaleItem],
    sales_by_external: dict[str, Sale],
) -> list[DashboardInventoryCard]:
    sold_quantity_by_product: dict[str, Decimal] = {}
    last_sold_at_by_product: dict[str, datetime] = {}
    for item in sale_items:
        if item.product_external_id is None:
            continue
        sold_quantity_by_product[item.product_external_id] = (
            sold_quantity_by_product.get(item.product_external_id, Decimal("0")) + item.quantity
        )
        sale = sales_by_external.get(item.sale_external_id)
        if sale is not None:
            current_last = last_sold_at_by_product.get(item.product_external_id)
            if current_last is None or sale.sale_at > current_last:
                last_sold_at_by_product[item.product_external_id] = sale.sale_at

    cards: list[DashboardInventoryCard] = []
    for balance in sorted(
        inventory_balances,
        key=lambda item: (item.quantity, item.balance_at),
        reverse=True,
    ):
        product = products.get(balance.product_external_id)
        warehouse = warehouses.get(balance.warehouse_external_id)
        business = businesses.get(balance.organization_id)
        sold_quantity = sold_quantity_by_product.get(balance.product_external_id, Decimal("0"))
        average_daily_sales = sold_quantity / Decimal("30") if sold_quantity > 0 else Decimal("0")
        days_of_stock = None
        if average_daily_sales > 0:
            days_of_stock = _format_decimal(balance.quantity / average_daily_sales)
        risk_level = _inventory_risk_level(
            balance=balance,
            sales_items=sale_items,
            product_external_ids=products,
        )
        cards.append(
            DashboardInventoryCard(
                warehouse_name=getattr(warehouse, "name", "Склад")
                if warehouse is not None
                else "Склад",
                product_name=getattr(product, "name", "Товар") if product is not None else "Товар",
                business_id=balance.organization_id,
                business_name=getattr(business, "name", "Бизнес") or "Бизнес",
                quantity=_format_decimal(balance.quantity),
                balance_at=balance.balance_at,
                average_daily_sales=_format_decimal(average_daily_sales)
                if average_daily_sales > 0
                else None,
                days_of_stock=days_of_stock,
                risk_level=risk_level,
                last_sold_at=last_sold_at_by_product.get(balance.product_external_id),
                details_href="/api/v1/data/inventory",
                data_status=DataAvailabilityStatus.AVAILABLE
                if balance.quantity > 0
                else DataAvailabilityStatus.UNAVAILABLE,
            ),
        )
    return cards[:8]


def _build_signals(
    *,
    freshness: str,
    revenue_change: Decimal | None,
    cash_flow_change: Decimal | None,
    expense_change: Decimal | None,
    sold_units_change: Decimal | None,
    returns_change: Decimal | None,
    inventory_risk_count: int,
    customers_available: bool,
) -> list[DashboardSignal]:
    signals: list[DashboardSignal] = []

    if revenue_change is None:
        signals.append(
            DashboardSignal(
                severity="warning",
                title="Выручка пока не сравнивается",
                badge="Период",
                note="Нужны данные за предыдущий аналогичный период для оценки динамики.",
                metrics=["Продажи", freshness],
            ),
        )
    elif revenue_change < 0:
        signals.append(
            DashboardSignal(
                severity="critical",
                title="Выручка просела",
                badge="Продажи",
                note="Нужно проверить ассортимент, воронку и ключевые товары.",
                metrics=[f"{_format_change(revenue_change)} к прошлому периоду"],
            ),
        )
    else:
        signals.append(
            DashboardSignal(
                severity="info",
                title="Выручка растёт",
                badge="Продажи",
                note="Сравнение с предыдущим периодом показывает положительную динамику.",
                metrics=[f"{_format_change(revenue_change)} к прошлому периоду"],
            ),
        )

    if cash_flow_change is not None and cash_flow_change < 0:
        signals.append(
            DashboardSignal(
                severity="warning",
                title="Денежный поток под давлением",
                badge="Финансы",
                note="Поступления не перекрывают расходы в выбранном периоде.",
                metrics=[f"{_format_change(cash_flow_change)} cash flow"],
            ),
        )
    else:
        signals.append(
            DashboardSignal(
                severity="info",
                title="Денежный поток устойчив",
                badge="Финансы",
                note="Поступления и расходы находятся под контролем.",
                metrics=[f"{_format_change(cash_flow_change) or '0,0%'} cash flow"],
            ),
        )

    if inventory_risk_count > 0:
        signals.append(
            DashboardSignal(
                severity="warning",
                title="На складе есть рискованные позиции",
                badge="Склад",
                note=(
                    f"{inventory_risk_count} позиций требуют внимания "
                    "по запасу или оборачиваемости."
                ),
                metrics=[f"{inventory_risk_count} рискованных позиций"],
            ),
        )
    else:
        signals.append(
            DashboardSignal(
                severity="info",
                title="Склад без явных рисков",
                badge="Склад",
                note="Критических остатков и залеживания не видно.",
                metrics=["Склад стабилен"],
            ),
        )

    if customers_available:
        signals.append(
            DashboardSignal(
                severity="info",
                title="Клиентская база загружена",
                badge="Клиенты",
                note="Можно строить повторные продажи и сегментацию.",
                metrics=["CRM готова к анализу"],
            ),
        )
    else:
        signals.append(
            DashboardSignal(
                severity="warning",
                title="Клиентская база пустая",
                badge="Клиенты",
                note="Для точной аналитики нужны контакты и привязка покупателей.",
                metrics=["Нет клиентских данных"],
            ),
        )

    if returns_change is not None and returns_change > 0:
        signals.append(
            DashboardSignal(
                severity="warning",
                title="Возвраты растут",
                badge="Возвраты",
                note="Проверьте причины возвратов и проблемные позиции.",
                metrics=[f"{_format_change(returns_change)} по возвратам"],
            ),
        )
    else:
        signals.append(
            DashboardSignal(
                severity="info",
                title="Возвраты под контролем",
                badge="Возвраты",
                note="Доля возвратов не выделяется как критичная.",
                metrics=[f"{_format_change(returns_change) or '0,0%'} по возвратам"],
            ),
        )

    return signals[:4]


def _build_action_center_cards(
    *,
    signals: list[DashboardSignal],
    top_products: list[DashboardProductCard],
    dead_stock_count: int,
    returns_current: Decimal,
    cash_flow_current: Decimal,
) -> list[DashboardSignal]:
    actions: list[DashboardSignal] = []

    actions.append(
        DashboardSignal(
            severity="warning" if cash_flow_current < 0 else "info",
            title="Проверить денежный поток",
            badge="Деньги",
            note="Свести продажи, поступления и расходы в один управленческий обзор.",
            metrics=[f"Чистый поток: {_format_money(cash_flow_current, None)}"],
        ),
    )
    actions.append(
        DashboardSignal(
            severity="warning" if returns_current > 0 else "info",
            title="Разобрать возвраты",
            badge="Возвраты",
            note="Посмотреть причины возвратов и проблемные товары.",
            metrics=[f"Возвратов: {_format_money(returns_current, None)}"],
        ),
    )
    actions.append(
        DashboardSignal(
            severity="warning" if dead_stock_count > 0 else "info",
            title="Сократить залежавшийся запас",
            badge="Склад",
            note="Вытащить товары без движения и ускорить оборачиваемость.",
            metrics=[f"Мёртвых позиций: {dead_stock_count}"],
        ),
    )
    actions.append(
        DashboardSignal(
            severity="info",
            title="Усилить ключевые товары",
            badge="Продажи",
            note="Сфокусироваться на SKU, которые дают основную часть выручки.",
            metrics=[top_products[0].name if top_products else "Нет данных"],
        ),
    )
    return actions[:4]


def _build_returns_summary_cards(
    *,
    current_returns: Decimal,
    previous_returns: Decimal,
    current_return_sales: list[Sale],
    previous_return_sales: list[Sale],
    current_return_documents: list[BusinessDocument],
    previous_return_documents: list[BusinessDocument],
    currency: str,
) -> list[DashboardCard]:
    return [
        DashboardCard(
            label="Возвраты клиентов",
            value=str(len(current_return_sales))
            if current_return_sales or previous_return_sales
            else "Нет данных",
            note="отменённые и возвращённые продажи",
            details_href="/api/v1/data/returns",
            previous_value=str(len(previous_return_sales))
            if current_return_sales or previous_return_sales
            else None,
            change=_format_change(
                _change_percent(
                    Decimal(len(current_return_sales)), Decimal(len(previous_return_sales))
                )
            ),
            status=DataAvailabilityStatus.AVAILABLE
            if (current_return_sales or previous_return_sales)
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
        DashboardCard(
            label="Возврат поставщику",
            value=str(len(current_return_documents))
            if current_return_documents or previous_return_documents
            else "Нет данных",
            note="документы возврата поставщикам",
            details_href="/api/v1/data/returns",
            previous_value=str(len(previous_return_documents))
            if current_return_documents or previous_return_documents
            else None,
            change=_format_change(
                _change_percent(
                    Decimal(len(current_return_documents)), Decimal(len(previous_return_documents))
                )
            ),
            status=DataAvailabilityStatus.AVAILABLE
            if (current_return_documents or previous_return_documents)
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
        DashboardCard(
            label="Сумма возвратов",
            value=_format_money(current_returns, currency)
            if (current_returns or previous_returns)
            else "Нет данных",
            note="денежный объём возвратов",
            details_href="/api/v1/data/returns",
            previous_value=_format_money(previous_returns, currency)
            if (current_returns or previous_returns)
            else None,
            change=_format_change(_change_percent(current_returns, previous_returns)),
            status=DataAvailabilityStatus.AVAILABLE
            if (current_returns or previous_returns)
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
        DashboardCard(
            label="Динамика возвратов",
            value=_format_change(_change_percent(current_returns, previous_returns)) or "0%",
            note="к прошлому периоду",
            details_href="/api/v1/data/returns",
            previous_value=_format_money(previous_returns, currency)
            if (current_returns or previous_returns)
            else None,
            change=_format_change(_change_percent(current_returns, previous_returns)),
            status=DataAvailabilityStatus.AVAILABLE
            if (current_returns or previous_returns)
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
    ]


def _build_cash_flow_cards(
    *,
    revenue_current: Decimal,
    revenue_previous: Decimal,
    cash_current: Decimal,
    cash_previous: Decimal,
    expense_current: Decimal,
    expense_previous: Decimal,
    net_cash_current: Decimal,
    net_cash_previous: Decimal,
    currency: str,
) -> list[DashboardCard]:
    return [
        DashboardCard(
            label="Выручка",
            value=_format_money(revenue_current, currency)
            if revenue_current or revenue_previous
            else "Нет данных",
            note="по закрытым продажам",
            details_href="/api/v1/data/sales",
            previous_value=_format_money(revenue_previous, currency)
            if revenue_current or revenue_previous
            else None,
            change=_format_change(_change_percent(revenue_current, revenue_previous)),
            status=DataAvailabilityStatus.AVAILABLE
            if (revenue_current or revenue_previous)
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
        DashboardCard(
            label="Получено денег",
            value=_format_money(cash_current, currency)
            if cash_current or cash_previous
            else "Нет данных",
            note="по оплатам и поступлениям",
            details_href="/api/v1/data/payments",
            previous_value=_format_money(cash_previous, currency)
            if cash_current or cash_previous
            else None,
            change=_format_change(_change_percent(cash_current, cash_previous)),
            status=DataAvailabilityStatus.AVAILABLE
            if (cash_current or cash_previous)
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
        DashboardCard(
            label="Расходы",
            value=_format_money(expense_current, currency)
            if expense_current or expense_previous
            else "Нет данных",
            note="по расходным операциям",
            details_href="/api/v1/data/processing",
            previous_value=_format_money(expense_previous, currency)
            if expense_current or expense_previous
            else None,
            change=_format_change(_change_percent(expense_current, expense_previous)),
            status=DataAvailabilityStatus.AVAILABLE
            if (expense_current or expense_previous)
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
        DashboardCard(
            label="Чистый денежный поток",
            value=_format_money(net_cash_current, currency)
            if net_cash_current or net_cash_previous
            else "Нет данных",
            note="поступления минус расходы",
            details_href="/api/v1/data/overview",
            previous_value=_format_money(net_cash_previous, currency)
            if net_cash_current or net_cash_previous
            else None,
            change=_format_change(_change_percent(net_cash_current, net_cash_previous)),
            status=DataAvailabilityStatus.AVAILABLE
            if (net_cash_current or net_cash_previous)
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
    ]


def _build_customers_summary_cards(
    *,
    contacts: list,
    buyers_current: int,
    buyers_previous: int,
    repeat_buyers_current: int,
    repeat_buyers_previous: int,
    conversion_current: Decimal,
    conversion_previous: Decimal,
) -> list[DashboardCard]:
    contact_total = len(contacts)
    return [
        DashboardCard(
            label="Клиенты",
            value=str(contact_total) if contact_total else "Нет данных",
            note="все контакты в ядре",
            details_href="/api/v1/data/customers",
            previous_value=str(contact_total) if contact_total else None,
            change=None,
            status=DataAvailabilityStatus.AVAILABLE
            if contact_total
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
        DashboardCard(
            label="Покупающие клиенты",
            value=str(buyers_current) if contact_total else "Нет данных",
            note="клиенты с покупками в периоде",
            details_href="/api/v1/data/customers",
            previous_value=str(buyers_previous) if contact_total else None,
            change=_format_change(
                _change_percent(Decimal(buyers_current), Decimal(buyers_previous))
            ),
            status=DataAvailabilityStatus.AVAILABLE
            if contact_total
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
        DashboardCard(
            label="Повторные покупки",
            value=str(repeat_buyers_current) if contact_total else "Нет данных",
            note="клиенты с более чем одной покупкой",
            details_href="/api/v1/data/customers",
            previous_value=str(repeat_buyers_previous) if contact_total else None,
            change=_format_change(
                _change_percent(Decimal(repeat_buyers_current), Decimal(repeat_buyers_previous))
            ),
            status=DataAvailabilityStatus.AVAILABLE
            if contact_total
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
        DashboardCard(
            label="Конверсия в покупку",
            value=f"{_format_percentage(conversion_current)}" if contact_total else "Нет данных",
            note="покупатели / клиенты",
            details_href="/api/v1/data/customers",
            previous_value=f"{_format_percentage(conversion_previous)}" if contact_total else None,
            change=_format_change(_change_percent(conversion_current, conversion_previous)),
            status=DataAvailabilityStatus.AVAILABLE
            if contact_total
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
    ]


def _build_seller_performance_cards(
    *,
    raw_sales: list,
    previous_raw_sales: list,
    sale_items: list[SaleItem],
    previous_sale_items: list[SaleItem],
    businesses: dict[UUID, object],
    currency: str,
) -> list[DashboardCard]:
    def _manager_code(record) -> str | None:
        metadata = getattr(record, "metadata", {}) or {}
        for key in (
            "sales_manager_code",
            "responsible_person_code",
            "person_code",
            "owner_person_code",
        ):
            value = metadata.get(key)
            if value:
                text = str(value).strip()
                if text:
                    return text
        return None

    current_rows: dict[str, dict[str, Decimal | int]] = {}
    previous_rows: dict[str, dict[str, Decimal | int]] = {}
    for sale in raw_sales:
        manager = _manager_code(sale) or "Без кода"
        row = current_rows.setdefault(
            manager, {"revenue": Decimal("0"), "deals": 0, "units": Decimal("0")}
        )
        if sale.stage == SaleStage.WON:
            row["revenue"] = row["revenue"] + sale.amount
        row["deals"] = int(row["deals"]) + 1
    for sale in previous_raw_sales:
        manager = _manager_code(sale) or "Без кода"
        row = previous_rows.setdefault(
            manager, {"revenue": Decimal("0"), "deals": 0, "units": Decimal("0")}
        )
        if sale.stage == SaleStage.WON:
            row["revenue"] = row["revenue"] + sale.amount
        row["deals"] = int(row["deals"]) + 1

    units_by_manager: dict[str, Decimal] = {}
    for item in sale_items:
        manager = None
        for sale in raw_sales:
            if sale.external_ref == item.sale_external_id:
                manager = _manager_code(sale) or "Без кода"
                break
        if manager is None:
            manager = "Без кода"
        units_by_manager[manager] = units_by_manager.get(manager, Decimal("0")) + item.quantity

    previous_units_by_manager: dict[str, Decimal] = {}
    for item in previous_sale_items:
        manager = None
        for sale in previous_raw_sales:
            if sale.external_ref == item.sale_external_id:
                manager = _manager_code(sale) or "Без кода"
                break
        if manager is None:
            manager = "Без кода"
        previous_units_by_manager[manager] = (
            previous_units_by_manager.get(manager, Decimal("0")) + item.quantity
        )

    if not current_rows and not previous_rows:
        return [
            DashboardCard(
                label="Менеджеры продаж",
                value="Нет данных",
                note="SmartUp не передал sales_manager_code",
                details_href="/api/v1/data/sales",
                status=DataAvailabilityStatus.UNAVAILABLE,
            ),
        ]

    cards: list[DashboardCard] = []
    for manager, values in sorted(
        current_rows.items(), key=lambda item: (-item[1]["revenue"], item[0])
    )[:4]:
        previous_values = previous_rows.get(manager, {"revenue": Decimal("0"), "deals": 0})
        revenue_current = values["revenue"]
        revenue_previous = previous_values["revenue"]
        deals_current = int(values["deals"])
        _deals_previous = int(previous_values["deals"])
        units_current = units_by_manager.get(manager, Decimal("0"))
        _units_previous = previous_units_by_manager.get(manager, Decimal("0"))
        cards.append(
            DashboardCard(
                label=manager,
                value=_format_money(revenue_current, currency),
                note=f"{deals_current} сделок · {_format_decimal(units_current)} единиц",
                previous_value=_format_money(revenue_previous, currency),
                change=_format_change(_change_percent(revenue_current, revenue_previous)),
                details_href="/api/v1/data/sales",
                status=DataAvailabilityStatus.AVAILABLE,
            ),
        )

    return cards or [
        DashboardCard(
            label="Менеджеры продаж",
            value="Нет данных",
            note="SmartUp не передал sales_manager_code",
            details_href="/api/v1/data/sales",
            status=DataAvailabilityStatus.UNAVAILABLE,
        ),
    ]


def _build_recommendations_cards(
    *,
    revenue_change: Decimal | None,
    cash_flow_change: Decimal | None,
    returns_change: Decimal | None,
    inventory_risk_count: int,
    customers_available: bool,
    sales_available: bool,
) -> list[DashboardCard]:
    recommendations = [
        DashboardCard(
            label="Фокус на выручке",
            value=_format_change(revenue_change) or "Нет данных",
            note="сравните динамику продаж и проверьте просадку по каналам",
            details_href="/api/v1/data/sales",
        ),
        DashboardCard(
            label="Фокус на деньгах",
            value=_format_change(cash_flow_change) or "Нет данных",
            note="денежный поток должен расти быстрее расходов",
            details_href="/api/v1/data/overview",
        ),
        DashboardCard(
            label="Фокус на возвратах",
            value=_format_change(returns_change) or "0%",
            note="разберите причины возвратов и слабые SKU",
            details_href="/api/v1/data/returns",
        ),
        DashboardCard(
            label="Фокус на складе",
            value=str(inventory_risk_count),
            note="сократите зависшие позиции и дефицитные остатки",
            details_href="/api/v1/data/inventory",
        ),
    ]
    if not customers_available:
        recommendations.append(
            DashboardCard(
                label="Фокус на клиентах",
                value="Нет данных",
                note="нужны контакты и покупатели для сегментации",
                details_href="/api/v1/data/customers",
            ),
        )
    elif sales_available:
        recommendations.append(
            DashboardCard(
                label="Фокус на повторных продажах",
                value="Готово",
                note="можно запускать upsell по существующей базе",
                details_href="/api/v1/data/customers",
            ),
        )
    return recommendations[:4]


def _build_availability_cards(
    *,
    revenue_available: bool,
    cash_available: bool,
    expense_available: bool,
    returns_available: bool,
    customers_available: bool,
    sold_units_available: bool,
    inventory_available: bool,
    sales_available: bool,
    raw_records: list[Any],
) -> list[DashboardAvailabilityCard]:
    def _state(
        available: bool, normalized: int, raw_terms: tuple[str, ...]
    ) -> DataAvailabilityStatus:
        raw_count = _raw_entity_count(raw_records, *raw_terms)
        if available:
            return DataAvailabilityStatus.AVAILABLE
        if raw_count > 0:
            return DataAvailabilityStatus.SYNCING
        return DataAvailabilityStatus.UNAVAILABLE

    return [
        DashboardAvailabilityCard(
            label="Продажи",
            value="Готово" if revenue_available or sales_available else "Нет данных",
            note="данные по заказам и выручке",
            status=DataAvailabilityStatus.AVAILABLE
            if revenue_available or sales_available
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
        DashboardAvailabilityCard(
            label="Деньги",
            value="Готово" if cash_available or expense_available else "Нет данных",
            note="поступления и расходы",
            status=DataAvailabilityStatus.AVAILABLE
            if cash_available or expense_available
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
        DashboardAvailabilityCard(
            label="Возвраты",
            value="Готово" if returns_available else "Нет данных",
            note="клиентские и складские возвраты",
            status=DataAvailabilityStatus.AVAILABLE
            if returns_available
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
        DashboardAvailabilityCard(
            label="Склад",
            value="Готово" if inventory_available else "Нет данных",
            note="остатки и рискованные позиции",
            status=DataAvailabilityStatus.AVAILABLE
            if inventory_available
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
        DashboardAvailabilityCard(
            label="Клиенты",
            value="Готово" if customers_available else "Нет данных",
            note="контакты и повторные продажи",
            status=DataAvailabilityStatus.AVAILABLE
            if customers_available
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
        DashboardAvailabilityCard(
            label="Проданные единицы",
            value="Готово" if sold_units_available else "Нет данных",
            note="количество проданных позиций",
            status=DataAvailabilityStatus.AVAILABLE
            if sold_units_available
            else DataAvailabilityStatus.UNAVAILABLE,
        ),
    ]


def _build_ai_insights(
    *,
    businesses: int,
    contacts: int,
    source_systems: int,
    open_sales: int,
    won_sales: int,
    net_cash_flow: Decimal,
    marketing_spend_total: Decimal,
    marketing_conversions: int,
    cash_currency: str,
    freshness: str,
    revenue_current: Decimal,
    revenue_previous: Decimal,
    cash_current: Decimal,
    cash_previous: Decimal,
    inventory_risk_count: int,
    customers_current: int,
    buyers_current: int,
) -> list[str]:
    insights = [
        f"AI CEO видит {won_sales} закрытых сделок и {open_sales} активных в текущем окне.",
        (
            f"Выручка: {_format_money(revenue_current, cash_currency)} "
            f"против {_format_money(revenue_previous, cash_currency)} ранее."
        ),
        (
            f"Получено денег: {_format_money(cash_current, cash_currency)} "
            f"против {_format_money(cash_previous, cash_currency)} ранее."
        ),
        (
            f"Чистый поток: {_format_money(net_cash_flow, cash_currency)}; "
            f"складовых рисков: {inventory_risk_count}."
        ),
    ]

    if marketing_spend_total > 0:
        insights.append(
            (
                f"Маркетинг потратил {_format_money(marketing_spend_total, cash_currency)} "
                f"и дал {marketing_conversions} конверсий."
            ),
        )
    else:
        insights.append("Маркетинговые данные пока не загружены.")

    insights.append(
        (
            "Клиентская база: "
            f"{customers_current} контактов, {buyers_current} покупателей, "
            f"{businesses} бизнесов и {source_systems} источников."
        ),
    )
    insights.append(f"Свежесть ядра: {freshness}.")
    return insights[:4]
