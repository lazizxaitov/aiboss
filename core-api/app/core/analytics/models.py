"""Structured analytics models used by the executive dashboard."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AnalyticsPeriodWindow(BaseModel):
    """Current and previous time windows used for comparisons."""

    current_start: datetime | None = None
    current_end: datetime | None = None
    previous_start: datetime | None = None
    previous_end: datetime | None = None
    label: str
    comparison_label: str


class AnalyticsKPI(BaseModel):
    """A permanent executive KPI with comparison context."""

    key: str
    label: str
    current_value: Decimal
    previous_value: Decimal | None = None
    absolute_delta: Decimal | None = None
    percent_delta: Decimal | None = None
    trend: list[Decimal] = Field(default_factory=list)
    details_href: str | None = None
    unit: str = "count"
    direction: str = "flat"
    status: str = "stable"
    data_status: str = "available"


class AnalyticsDomainSummary(BaseModel):
    """High-level data coverage and performance summary for one business domain."""

    key: str
    label: str
    current_count: int = 0
    previous_count: int = 0
    current_amount: Decimal = Decimal("0")
    previous_amount: Decimal = Decimal("0")
    count_delta: int = 0
    amount_delta: Decimal = Decimal("0")
    count_percent_delta: Decimal | None = None
    amount_percent_delta: Decimal | None = None
    top_entities: list[str] = Field(default_factory=list)
    details_href: str | None = None
    note: str | None = None
    unit: str = "count"
    data_status: str = "available"


class AIInsightMetric(BaseModel):
    """Metric used to explain an insight."""

    label: str
    current: str | None = None
    previous: str | None = None
    delta: str | None = None
    direction: str | None = None


class AIInsightCard(BaseModel):
    """Structured insight produced by the AI analytics agent."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: str
    severity: str
    priority: int = 0
    title: str
    summary: str
    metrics: list[AIInsightMetric] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    recommendation: str
    widget_type: str = "ai_insight"
    entity_type: str | None = None
    entity_id: str | None = None
    organization_ids: list[UUID] = Field(default_factory=list)
    period: AnalyticsPeriodWindow | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DashboardWidgetType(StrEnum):
    """Widget types supported by the AI dashboard composer."""

    KPI = "kpi"
    TREND = "trend"
    LINE_CHART = "line_chart"
    BAR_CHART = "bar_chart"
    RANKING = "ranking"
    TABLE = "table"
    ALERT = "alert"
    PRODUCT_ALERT = "product_alert"
    CUSTOMER_ALERT = "customer_alert"
    INVENTORY_ALERT = "inventory_alert"
    WATCHLIST = "watchlist"
    ORGANIZATION_COMPARISON = "organization_comparison"
    PRODUCT_RANKING = "product_ranking"
    CUSTOMER_RANKING = "customer_ranking"
    INVENTORY_RISK = "inventory_risk"
    VISIT_SUMMARY = "visit_summary"
    DATA_QUALITY = "data_quality"
    SALES_REP_PERFORMANCE = "sales_rep_performance"
    AI_INSIGHT = "ai_insight"
    AI_RECOMMENDATION = "ai_recommendation"
    PHOTO_ALERT = "photo_alert"


class DashboardWidgetPlacement(BaseModel):
    """Placement recommendation for one dashboard widget."""

    widget_id: str
    widget_type: DashboardWidgetType
    title: str
    x: int
    y: int
    w: int
    h: int
    priority: int = 0
    locked: bool = False
    source_insight_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    summary: str | None = None


class BusinessAnalyticsSnapshot(BaseModel):
    """Structured data snapshot consumed by the AI analytics agent."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    period: AnalyticsPeriodWindow
    organization_ids: list[UUID] = Field(default_factory=list)
    organization_names: list[str] = Field(default_factory=list)
    business_count: int = 0
    smartup_organization_count: int = 0
    kpis: list[AnalyticsKPI] = Field(default_factory=list)
    sales: AnalyticsDomainSummary
    products: AnalyticsDomainSummary
    customers: AnalyticsDomainSummary
    organizations: AnalyticsDomainSummary
    sales_reps: AnalyticsDomainSummary
    inventory: AnalyticsDomainSummary
    finance: AnalyticsDomainSummary
    returns: AnalyticsDomainSummary
    visits: AnalyticsDomainSummary
    merchandising: AnalyticsDomainSummary
    coverage: dict[str, int] = Field(default_factory=dict)
    top_products: list[str] = Field(default_factory=list)
    top_sales_reps: list[str] = Field(default_factory=list)
    top_customers: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AIDashboardWorkspace(BaseModel):
    """End-user workspace payload returned by the AI executive layer."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    period: AnalyticsPeriodWindow
    snapshot: BusinessAnalyticsSnapshot
    insights: list[AIInsightCard] = Field(default_factory=list)
    widgets: list[DashboardWidgetPlacement] = Field(default_factory=list)
    widget_registry: list[DashboardWidgetType] = Field(default_factory=list)
    widget_locks_supported: bool = True


class AnalyticsDataStatus(StrEnum):
    """Deterministic analytics data status."""

    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    NO_DATA = "NO_DATA"
    NO_VERIFIED_DATA = "NO_VERIFIED_DATA"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    PERMISSION_RESTRICTED = "PERMISSION_RESTRICTED"
    UNRESOLVED = "UNRESOLVED"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    ANALYSIS_PENDING = "ANALYSIS_PENDING"


class AnalyticsPeriodPreset(StrEnum):
    """Supported analytics period presets."""

    TODAY = "today"
    YESTERDAY = "yesterday"
    LAST_7_DAYS = "7d"
    LAST_30_DAYS = "30d"
    CURRENT_MONTH = "current_month"
    PREVIOUS_MONTH = "previous_month"
    CUSTOM = "custom"
    ALL = "all"


class AnalyticsComparisonMode(StrEnum):
    """Comparison modes for analytics queries."""

    PREVIOUS_PERIOD = "previous_period"
    PREVIOUS_WEEK = "previous_week"
    PREVIOUS_MONTH = "previous_month"
    PREVIOUS_YEAR = "previous_year"


class AnalyticsQuery(BaseModel):
    """Reusable analytics query parameters."""

    organization_id: UUID | None = None
    organization_ids: list[UUID] = Field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    period: AnalyticsPeriodPreset = AnalyticsPeriodPreset.LAST_30_DAYS
    comparison_mode: AnalyticsComparisonMode = AnalyticsComparisonMode.PREVIOUS_PERIOD


class AnalyticsMetricValue(BaseModel):
    """Deterministic metric value with quality context."""

    value: Decimal | None = None
    previous_value: Decimal | None = None
    delta: Decimal | None = None
    percent_delta: Decimal | None = None
    unit: str = "count"
    status: AnalyticsDataStatus = AnalyticsDataStatus.NO_DATA
    data_status: AnalyticsDataStatus = AnalyticsDataStatus.NO_DATA
    coverage: float | None = None
    confidence: float | None = None
    currency: str | None = None
    record_count: int = 0
    period: AnalyticsPeriodWindow | None = None
    supported_dimensions: list[str] = Field(default_factory=list)
    drilldown: list[str] = Field(default_factory=list)
    note: str | None = None


class MetricDefinition(BaseModel):
    """Registry entry defining one analytics metric."""

    metric_key: str
    display_name: str
    description: str
    canonical_sources: list[str] = Field(default_factory=list)
    source_entities: list[str] = Field(default_factory=list)
    formula: str
    required_quality: str = "VERIFIED"
    authoritative_date_field: str | None = None
    required_fields: list[str] = Field(default_factory=list)
    supported_dimensions: list[str] = Field(default_factory=list)
    currency_behavior: str = "preserve"
    null_behavior: str = "NO_DATA"
    drilldown_target: str | None = None


class AnalyticsDimensionRow(BaseModel):
    """Generic grouped analytics row."""

    dimension: str
    key: str
    label: str
    metrics: dict[str, AnalyticsMetricValue] = Field(default_factory=dict)
    data_status: AnalyticsDataStatus = AnalyticsDataStatus.AVAILABLE
    drilldown: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class AnalyticsDataQualityEntry(BaseModel):
    """One data-quality check result."""

    metric_key: str
    data_status: AnalyticsDataStatus
    coverage: float | None = None
    confidence: float | None = None
    message: str | None = None
    missing_fields: list[str] = Field(default_factory=list)


class AnalyticsDataQualityReport(BaseModel):
    """Aggregated data-quality state for analytics output."""

    overall_status: AnalyticsDataStatus = AnalyticsDataStatus.NO_DATA
    items: list[AnalyticsDataQualityEntry] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AnalyticsBusinessSummary(BaseModel):
    """Business-level KPI bundle."""

    revenue: AnalyticsMetricValue
    orders: AnalyticsMetricValue
    realised_sales: AnalyticsMetricValue
    sold_units: AnalyticsMetricValue
    average_order: AnalyticsMetricValue
    unique_customers: AnalyticsMetricValue
    unique_products: AnalyticsMetricValue
    payments_received: AnalyticsMetricValue
    customer_return_value: AnalyticsMetricValue
    current_stock: AnalyticsMetricValue
    visits: AnalyticsMetricValue
    verified_cash_in: AnalyticsMetricValue
    verified_cash_out: AnalyticsMetricValue
    returns: AnalyticsMetricValue
    expenses: AnalyticsMetricValue
    cash_flow: AnalyticsMetricValue
    customers: AnalyticsMetricValue


class AnalyticsOrganizationItem(BaseModel):
    """Organization-level analytics row."""

    organization_id: UUID
    organization_name: str
    metrics: AnalyticsBusinessSummary
    comparison: dict[str, AnalyticsMetricValue] = Field(default_factory=dict)
    products_sold: AnalyticsMetricValue
    sales_reps: AnalyticsMetricValue
    visits: AnalyticsMetricValue
    stock: AnalyticsMetricValue
    data_status: AnalyticsDataStatus = AnalyticsDataStatus.AVAILABLE


class AnalyticsProductItem(BaseModel):
    """Product-level analytics row."""

    product_id: UUID | None = None
    product_external_id: str
    product_name: str
    organization_id: UUID
    organization_name: str
    sold_units: AnalyticsMetricValue
    revenue: AnalyticsMetricValue
    orders_count: AnalyticsMetricValue
    customers_count: AnalyticsMetricValue
    average_selling_price: AnalyticsMetricValue
    returns_quantity: AnalyticsMetricValue
    returns_amount: AnalyticsMetricValue
    return_rate: AnalyticsMetricValue
    current_stock: AnalyticsMetricValue
    stock_value: AnalyticsMetricValue
    sales_velocity_7d: AnalyticsMetricValue
    sales_velocity_30d: AnalyticsMetricValue
    days_of_stock: AnalyticsMetricValue
    first_sale_date: datetime | None = None
    last_sale_date: datetime | None = None
    sales_change_pct: AnalyticsMetricValue
    units_change_pct: AnalyticsMetricValue
    revenue_change_pct: AnalyticsMetricValue
    classification: str | None = None
    classification_tags: list[str] = Field(default_factory=list)
    stockout_risk: str | None = None
    data_status: AnalyticsDataStatus = AnalyticsDataStatus.AVAILABLE


class AnalyticsInventoryTransferOpportunity(BaseModel):
    """Possible stock transfer between organizations."""

    product_external_id: str
    product_name: str
    from_organization_id: UUID
    from_organization_name: str
    to_organization_id: UUID
    to_organization_name: str
    source_stock: AnalyticsMetricValue
    destination_stock: AnalyticsMetricValue
    source_days: AnalyticsMetricValue
    destination_days: AnalyticsMetricValue
    source_velocity: AnalyticsMetricValue
    destination_velocity: AnalyticsMetricValue
    reason: str


class AnalyticsCustomerItem(BaseModel):
    """Customer-level analytics row."""

    customer_external_id: str
    customer_name: str
    organization_ids: list[UUID] = Field(default_factory=list)
    orders_count: AnalyticsMetricValue
    revenue: AnalyticsMetricValue
    sold_units: AnalyticsMetricValue
    average_order_value: AnalyticsMetricValue
    first_order_date: datetime | None = None
    last_order_date: datetime | None = None
    days_since_last_order: AnalyticsMetricValue
    purchase_frequency: AnalyticsMetricValue
    returns_count: AnalyticsMetricValue
    returns_amount: AnalyticsMetricValue
    visits_count: AnalyticsMetricValue
    products_count: AnalyticsMetricValue
    organizations_count: AnalyticsMetricValue
    segment: str
    customer_value_score: AnalyticsMetricValue
    data_status: AnalyticsDataStatus = AnalyticsDataStatus.AVAILABLE


class AnalyticsSalesRepItem(BaseModel):
    """Sales-representative analytics row."""

    sales_rep_key: str
    sales_rep_name: str
    revenue: AnalyticsMetricValue
    orders: AnalyticsMetricValue
    sold_units: AnalyticsMetricValue
    customers: AnalyticsMetricValue
    new_customers: AnalyticsMetricValue
    average_order: AnalyticsMetricValue
    returns: AnalyticsMetricValue
    visits: AnalyticsMetricValue
    completed_visits: AnalyticsMetricValue
    orders_after_visit: AnalyticsMetricValue
    visit_conversion: AnalyticsMetricValue
    revenue_after_visits: AnalyticsMetricValue
    data_status: AnalyticsDataStatus = AnalyticsDataStatus.AVAILABLE


class AnalyticsVisitItem(BaseModel):
    """Visit analytics row."""

    organization_id: UUID
    organization_name: str
    sales_rep_key: str | None = None
    customer_external_id: str | None = None
    visits_count: AnalyticsMetricValue
    completed_visits: AnalyticsMetricValue
    planned_visits: AnalyticsMetricValue
    unplanned_visits: AnalyticsMetricValue
    unique_customers: AnalyticsMetricValue
    average_duration: AnalyticsMetricValue
    data_status: AnalyticsDataStatus = AnalyticsDataStatus.AVAILABLE


class AnalyticsFinanceItem(BaseModel):
    """Finance analytics row."""

    metric_key: str
    label: str
    value: AnalyticsMetricValue
    data_status: AnalyticsDataStatus = AnalyticsDataStatus.AVAILABLE


class AnalyticsReturnItem(BaseModel):
    """Return analytics row."""

    return_key: str
    label: str
    amount: AnalyticsMetricValue
    quantity: AnalyticsMetricValue
    rate: AnalyticsMetricValue
    data_status: AnalyticsDataStatus = AnalyticsDataStatus.AVAILABLE


class AnalyticsBusinessSnapshot(BaseModel):
    """Unified deterministic analytics snapshot for AI and dashboard consumers."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    period: AnalyticsPeriodWindow
    query: AnalyticsQuery
    business: AnalyticsBusinessSummary
    organizations: list[AnalyticsOrganizationItem] = Field(default_factory=list)
    products: list[AnalyticsProductItem] = Field(default_factory=list)
    customers: list[AnalyticsCustomerItem] = Field(default_factory=list)
    inventory: list[AnalyticsInventoryTransferOpportunity] = Field(default_factory=list)
    sales_reps: list[AnalyticsSalesRepItem] = Field(default_factory=list)
    visits: list[AnalyticsVisitItem] = Field(default_factory=list)
    finance: list[AnalyticsFinanceItem] = Field(default_factory=list)
    returns: list[AnalyticsReturnItem] = Field(default_factory=list)
    metric_registry: list[MetricDefinition] = Field(default_factory=list)
    data_quality: AnalyticsDataQualityReport
    validation_notes: list[str] = Field(default_factory=list)
    top_products: list[AnalyticsProductItem] = Field(default_factory=list)
    slow_products: list[AnalyticsProductItem] = Field(default_factory=list)
    growing_products: list[AnalyticsProductItem] = Field(default_factory=list)
    declining_products: list[AnalyticsProductItem] = Field(default_factory=list)
    low_stock_products: list[AnalyticsProductItem] = Field(default_factory=list)
    overstock_products: list[AnalyticsProductItem] = Field(default_factory=list)
    stockout_risk_products: list[AnalyticsProductItem] = Field(default_factory=list)
    top_customers: list[AnalyticsCustomerItem] = Field(default_factory=list)
    at_risk_customers: list[AnalyticsCustomerItem] = Field(default_factory=list)
    lost_customers: list[AnalyticsCustomerItem] = Field(default_factory=list)
    organization_comparison: list[AnalyticsOrganizationItem] = Field(default_factory=list)
    top_sales_reps: list[AnalyticsSalesRepItem] = Field(default_factory=list)


class AnalyticsSummaryResponse(BaseModel):
    """Compact summary endpoint payload."""

    period: AnalyticsPeriodWindow
    business: AnalyticsBusinessSummary
    data_quality: AnalyticsDataQualityReport
    metric_registry: list[MetricDefinition] = Field(default_factory=list)
    organization_comparison: list[AnalyticsOrganizationItem] = Field(default_factory=list)
    top_products: list[AnalyticsProductItem] = Field(default_factory=list)
    top_customers: list[AnalyticsCustomerItem] = Field(default_factory=list)
    top_sales_reps: list[AnalyticsSalesRepItem] = Field(default_factory=list)


class AnalyticsSalesReport(BaseModel):
    """Sales analytics endpoint payload."""

    period: AnalyticsPeriodWindow
    summary: AnalyticsBusinessSummary
    by_date: list[AnalyticsDimensionRow] = Field(default_factory=list)
    by_organization: list[AnalyticsDimensionRow] = Field(default_factory=list)
    by_customer: list[AnalyticsDimensionRow] = Field(default_factory=list)
    by_product: list[AnalyticsDimensionRow] = Field(default_factory=list)
    by_category: list[AnalyticsDimensionRow] = Field(default_factory=list)
    by_sales_rep: list[AnalyticsDimensionRow] = Field(default_factory=list)
    by_working_zone: list[AnalyticsDimensionRow] = Field(default_factory=list)
    by_payment_type: list[AnalyticsDimensionRow] = Field(default_factory=list)
    by_order_status: list[AnalyticsDimensionRow] = Field(default_factory=list)
    data_quality: AnalyticsDataQualityReport


class AnalyticsProductReport(BaseModel):
    """Product analytics endpoint payload."""

    period: AnalyticsPeriodWindow
    items: list[AnalyticsProductItem] = Field(default_factory=list)
    top: list[AnalyticsProductItem] = Field(default_factory=list)
    growing: list[AnalyticsProductItem] = Field(default_factory=list)
    declining: list[AnalyticsProductItem] = Field(default_factory=list)
    slow_movers: list[AnalyticsProductItem] = Field(default_factory=list)
    dead_stock: list[AnalyticsProductItem] = Field(default_factory=list)
    low_stock: list[AnalyticsProductItem] = Field(default_factory=list)
    overstock: list[AnalyticsProductItem] = Field(default_factory=list)
    stockout_risk: list[AnalyticsProductItem] = Field(default_factory=list)
    transfer_opportunities: list[AnalyticsInventoryTransferOpportunity] = Field(
        default_factory=list
    )
    data_quality: AnalyticsDataQualityReport


class AnalyticsCustomerReport(BaseModel):
    """Customer analytics endpoint payload."""

    period: AnalyticsPeriodWindow
    items: list[AnalyticsCustomerItem] = Field(default_factory=list)
    top: list[AnalyticsCustomerItem] = Field(default_factory=list)
    growing: list[AnalyticsCustomerItem] = Field(default_factory=list)
    at_risk: list[AnalyticsCustomerItem] = Field(default_factory=list)
    lost: list[AnalyticsCustomerItem] = Field(default_factory=list)
    segments: dict[str, list[AnalyticsCustomerItem]] = Field(default_factory=dict)
    data_quality: AnalyticsDataQualityReport


class AnalyticsInventoryReport(BaseModel):
    """Inventory analytics endpoint payload."""

    period: AnalyticsPeriodWindow
    items: list[AnalyticsProductItem] = Field(default_factory=list)
    low_stock: list[AnalyticsProductItem] = Field(default_factory=list)
    overstock: list[AnalyticsProductItem] = Field(default_factory=list)
    stockout_risk: list[AnalyticsProductItem] = Field(default_factory=list)
    transfer_opportunities: list[AnalyticsInventoryTransferOpportunity] = Field(
        default_factory=list
    )
    data_quality: AnalyticsDataQualityReport


class AnalyticsOrganizationReport(BaseModel):
    """Organization analytics endpoint payload."""

    period: AnalyticsPeriodWindow
    items: list[AnalyticsOrganizationItem] = Field(default_factory=list)
    comparison: list[AnalyticsOrganizationItem] = Field(default_factory=list)
    data_quality: AnalyticsDataQualityReport


class AnalyticsSalesRepReport(BaseModel):
    """Sales representative analytics endpoint payload."""

    period: AnalyticsPeriodWindow
    items: list[AnalyticsSalesRepItem] = Field(default_factory=list)
    top: list[AnalyticsSalesRepItem] = Field(default_factory=list)
    data_quality: AnalyticsDataQualityReport


class AnalyticsVisitReport(BaseModel):
    """Visit analytics endpoint payload."""

    period: AnalyticsPeriodWindow
    items: list[AnalyticsVisitItem] = Field(default_factory=list)
    by_organization: list[AnalyticsDimensionRow] = Field(default_factory=list)
    by_sales_rep: list[AnalyticsDimensionRow] = Field(default_factory=list)
    by_customer: list[AnalyticsDimensionRow] = Field(default_factory=list)
    by_working_zone: list[AnalyticsDimensionRow] = Field(default_factory=list)
    data_quality: AnalyticsDataQualityReport


class AnalyticsFinanceReport(BaseModel):
    """Finance analytics endpoint payload."""

    period: AnalyticsPeriodWindow
    sales_revenue: AnalyticsMetricValue
    payments_received: AnalyticsMetricValue
    cash_operations: AnalyticsMetricValue
    bank_operations: AnalyticsMetricValue
    expenses: AnalyticsMetricValue
    cash_flow: AnalyticsMetricValue
    by_type: list[AnalyticsDimensionRow] = Field(default_factory=list)
    by_category: list[AnalyticsDimensionRow] = Field(default_factory=list)
    data_quality: AnalyticsDataQualityReport


class AnalyticsReturnReport(BaseModel):
    """Return analytics endpoint payload."""

    period: AnalyticsPeriodWindow
    count: AnalyticsMetricValue
    amount: AnalyticsMetricValue
    rate: AnalyticsMetricValue
    top_sources: list[str] = Field(default_factory=list)
    data_quality: AnalyticsDataQualityReport
