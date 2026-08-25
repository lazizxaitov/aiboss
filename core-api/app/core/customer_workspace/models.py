"""Pydantic contracts for the Customers / Customer 360 business workspace."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.analytics.models import (
    AnalyticsDataStatus,
    AnalyticsMetricValue,
    AnalyticsPeriodWindow,
)
from app.core.data_layer.canonical_v2 import CanonicalDataQualityStatus


class CustomerWorkspaceSortBy(StrEnum):
    """Supported sort fields for the customers workspace."""

    CUSTOMER_NAME = "customer_name"
    REVENUE = "revenue"
    ORDERS = "orders"
    SOLD_UNITS = "sold_units"
    AVERAGE_ORDER = "average_order"
    PAYMENTS = "payments"
    RETURNS = "returns"
    VISITS = "visits"
    LAST_PURCHASE = "last_purchase"


class CustomerWorkspaceSortOrder(StrEnum):
    """Supported sort directions for the customers workspace."""

    ASC = "asc"
    DESC = "desc"


class CustomerWorkspaceFilterOption(BaseModel):
    """Selectable filter option."""

    value: str
    label: str
    count: int = 0


class CustomerWorkspaceFilterMetadata(BaseModel):
    """Available filters for the current customers scope."""

    organizations: list[CustomerWorkspaceFilterOption] = Field(default_factory=list)
    customer_types: list[CustomerWorkspaceFilterOption] = Field(default_factory=list)
    sales_reps: list[CustomerWorkspaceFilterOption] = Field(default_factory=list)
    working_zones: list[CustomerWorkspaceFilterOption] = Field(default_factory=list)
    data_quality: list[CustomerWorkspaceFilterOption] = Field(default_factory=list)


class CustomerWorkspacePagination(BaseModel):
    """Page metadata for the customers table."""

    page: int
    page_size: int
    total_items: int
    total_pages: int


class CustomerWorkspaceQuery(BaseModel):
    """Query filters for the customers workspace."""

    search: str | None = None
    has_sales: bool | None = None
    has_payments: bool | None = None
    has_returns: bool | None = None
    has_visits: bool | None = None
    customer_type: list[str] = Field(default_factory=list)
    sales_rep: list[str] = Field(default_factory=list)
    working_zone: list[str] = Field(default_factory=list)
    data_quality: list[CanonicalDataQualityStatus] = Field(default_factory=list)
    revenue_min: Decimal | None = None
    revenue_max: Decimal | None = None
    sort_by: CustomerWorkspaceSortBy = CustomerWorkspaceSortBy.REVENUE
    sort_order: CustomerWorkspaceSortOrder = CustomerWorkspaceSortOrder.DESC
    page: int = 1
    page_size: int = 25


class CustomerWorkspaceSummary(BaseModel):
    """Top summary strip for the customers page."""

    unique_customers: AnalyticsMetricValue
    customers_with_sales: AnalyticsMetricValue
    revenue: AnalyticsMetricValue
    average_revenue_per_customer: AnalyticsMetricValue
    payments_received: AnalyticsMetricValue
    return_value: AnalyticsMetricValue
    visits: AnalyticsMetricValue
    active_customers: AnalyticsMetricValue


class CustomerWorkspaceRow(BaseModel):
    """One row in the customers business table."""

    customer_id: UUID
    customer_external_id: str
    customer_code: str | None = None
    customer_name: str
    organization_ids: list[UUID] = Field(default_factory=list)
    organization_names: list[str] = Field(default_factory=list)
    customer_type: str | None = None
    orders_count: Decimal | None = None
    realised_sales_count: Decimal | None = None
    revenue: Decimal | None = None
    sold_units: Decimal | None = None
    average_order_value: Decimal | None = None
    payments_received: Decimal | None = None
    return_value: Decimal | None = None
    visits_count: Decimal | None = None
    first_purchase: datetime | None = None
    last_purchase: datetime | None = None
    days_since_last_purchase: Decimal | None = None
    products_bought_count: Decimal | None = None
    sales_rep_names: list[str] = Field(default_factory=list)
    working_zone_names: list[str] = Field(default_factory=list)
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    group_names: list[str] = Field(default_factory=list)
    segment: str | None = None
    data_quality_status: CanonicalDataQualityStatus
    data_status: AnalyticsDataStatus


class CustomerWorkspaceProductRow(BaseModel):
    """Product ranking row inside Customer 360."""

    product_id: UUID | None = None
    product_code: str | None = None
    product_name: str | None = None
    sold_units: Decimal | None = None
    revenue: Decimal | None = None
    orders_count: Decimal | None = None
    return_quantity: Decimal | None = None
    last_purchase: datetime | None = None
    currency_code: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class CustomerWorkspaceSaleRow(BaseModel):
    """Order / sale row inside Customer 360."""

    record_id: UUID
    order_id: UUID | None = None
    sale_id: UUID | None = None
    deal_id: str | None = None
    order_number: str | None = None
    sale_number: str | None = None
    organization_id: UUID
    organization_name: str
    business_date: datetime | None = None
    normalized_status: str
    display_status: str
    order_amount: Decimal | None = None
    realised_amount: Decimal | None = None
    sold_units: Decimal | None = None
    currency_code: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class CustomerWorkspacePaymentRow(BaseModel):
    """Payment row inside Customer 360."""

    payment_id: UUID
    organization_id: UUID
    organization_name: str
    paid_at: datetime | None = None
    payment_number: str | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    normalized_payment_type: str | None = None
    allocation_type: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class CustomerWorkspaceReturnRow(BaseModel):
    """Return row inside Customer 360."""

    return_id: UUID
    organization_id: UUID
    organization_name: str
    return_number: str | None = None
    return_at: datetime | None = None
    amount: Decimal | None = None
    returned_quantity: Decimal | None = None
    currency_code: str | None = None
    status: str | None = None
    products: list[str] = Field(default_factory=list)
    data_quality_status: CanonicalDataQualityStatus


class CustomerWorkspaceVisitRow(BaseModel):
    """Visit row inside Customer 360."""

    visit_id: UUID
    organization_id: UUID
    organization_name: str
    visit_date: datetime | None = None
    sales_rep_name: str | None = None
    working_zone_name: str | None = None
    status: str
    duration_seconds: int | None = None
    data_quality_status: CanonicalDataQualityStatus


class CustomerWorkspaceTimelineEvent(BaseModel):
    """Chronological customer activity event."""

    event_id: str
    event_type: str
    title: str
    happened_at: datetime | None = None
    organization_name: str | None = None
    amount: Decimal | None = None
    quantity: Decimal | None = None
    currency_code: str | None = None
    reference_id: UUID | None = None
    reference_type: str | None = None
    drilldown_target: str | None = None
    description: str | None = None


class CustomerWorkspaceProvenance(BaseModel):
    """Admin/debug provenance for a canonical customer."""

    canonical_customer_id: UUID
    source_endpoint: str
    source_external_id: str
    source_raw_record_id: UUID | None = None
    request_filial_id: str | None = None
    response_filial_id: str | None = None
    request_company_id: str | None = None
    request_project_code: str | None = None
    data_quality_status: CanonicalDataQualityStatus
    reference_sources: list[str] = Field(default_factory=list)


class CustomerWorkspaceDetail(BaseModel):
    """Customer 360 payload."""

    customer_id: UUID
    row: CustomerWorkspaceRow
    overview: CustomerWorkspaceSummary
    sales: list[CustomerWorkspaceSaleRow] = Field(default_factory=list)
    products: list[CustomerWorkspaceProductRow] = Field(default_factory=list)
    payments: list[CustomerWorkspacePaymentRow] = Field(default_factory=list)
    returns: list[CustomerWorkspaceReturnRow] = Field(default_factory=list)
    visits: list[CustomerWorkspaceVisitRow] = Field(default_factory=list)
    timeline: list[CustomerWorkspaceTimelineEvent] = Field(default_factory=list)
    ai_summary: str | None = None
    provenance: CustomerWorkspaceProvenance
    limitations: list[str] = Field(default_factory=list)


class CustomerWorkspaceResponse(BaseModel):
    """Top-level response for the customers page."""

    period: AnalyticsPeriodWindow
    summary: CustomerWorkspaceSummary
    filters: CustomerWorkspaceFilterMetadata
    rows: list[CustomerWorkspaceRow]
    pagination: CustomerWorkspacePagination
