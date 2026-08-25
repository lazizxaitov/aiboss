"""Pydantic contracts for the Sales / Orders business workspace."""

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


class SalesWorkspaceSortBy(StrEnum):
    """Supported sort fields for the sales workspace."""

    BUSINESS_DATE = "business_date"
    ORDER_AMOUNT = "order_amount"
    REALISED_AMOUNT = "realised_amount"
    SOLD_UNITS = "sold_units"
    CUSTOMER = "customer"
    ORGANIZATION = "organization"
    STATUS = "status"


class SalesWorkspaceSortOrder(StrEnum):
    """Supported sort directions for the sales workspace."""

    ASC = "asc"
    DESC = "desc"


class SalesWorkspaceRowKind(StrEnum):
    """Primary semantic kind of a workspace row."""

    ORDER = "order"
    SALE = "sale"


class SalesWorkspaceFilterOption(BaseModel):
    """Selectable filter option."""

    value: str
    label: str
    count: int = 0


class SalesWorkspaceFilterMetadata(BaseModel):
    """Available filters for the current organization + period scope."""

    organizations: list[SalesWorkspaceFilterOption] = Field(default_factory=list)
    statuses: list[SalesWorkspaceFilterOption] = Field(default_factory=list)
    customers: list[SalesWorkspaceFilterOption] = Field(default_factory=list)
    sales_reps: list[SalesWorkspaceFilterOption] = Field(default_factory=list)
    working_zones: list[SalesWorkspaceFilterOption] = Field(default_factory=list)
    data_quality: list[SalesWorkspaceFilterOption] = Field(default_factory=list)


class SalesWorkspacePagination(BaseModel):
    """Page metadata for large business tables."""

    page: int
    page_size: int
    total_items: int
    total_pages: int


class SalesWorkspaceQuery(BaseModel):
    """Query filters for the sales workspace."""

    search: str | None = None
    status: list[str] = Field(default_factory=list)
    customer: list[str] = Field(default_factory=list)
    product: str | None = None
    sales_rep: list[str] = Field(default_factory=list)
    working_zone: list[str] = Field(default_factory=list)
    realised: bool | None = None
    has_returns: bool | None = None
    data_quality: list[CanonicalDataQualityStatus] = Field(default_factory=list)
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    sort_by: SalesWorkspaceSortBy = SalesWorkspaceSortBy.BUSINESS_DATE
    sort_order: SalesWorkspaceSortOrder = SalesWorkspaceSortOrder.DESC
    page: int = 1
    page_size: int = 25


class SalesWorkspaceSummary(BaseModel):
    """Top summary strip for the Sales / Orders page."""

    revenue: AnalyticsMetricValue
    orders: AnalyticsMetricValue
    realised_sales: AnalyticsMetricValue
    sold_units: AnalyticsMetricValue
    average_order: AnalyticsMetricValue
    unique_customers: AnalyticsMetricValue
    payments_received: AnalyticsMetricValue
    return_value: AnalyticsMetricValue


class SalesWorkspaceTableRow(BaseModel):
    """One row in the Sales / Orders business table."""

    record_id: UUID
    row_kind: SalesWorkspaceRowKind
    order_id: UUID | None = None
    sale_id: UUID | None = None
    order_external_id: str | None = None
    sale_external_id: str | None = None
    deal_id: str | None = None
    order_number: str | None = None
    sale_number: str | None = None
    business_date: datetime | None = None
    delivery_date: datetime | None = None
    last_modified_at: datetime | None = None
    organization_id: UUID
    organization_name: str
    customer_id: UUID | None = None
    customer_external_id: str | None = None
    customer_code: str | None = None
    customer_name: str | None = None
    sales_rep_id: UUID | None = None
    sales_rep_name: str | None = None
    working_zone_id: UUID | None = None
    working_zone_name: str | None = None
    source_status_code: str | None = None
    source_status_name: str | None = None
    normalized_status: str
    display_status: str
    order_amount: Decimal | None = None
    realised_amount: Decimal | None = None
    return_value: Decimal | None = None
    linked_payment_amount: Decimal | None = None
    ordered_units: Decimal | None = None
    sold_units: Decimal | None = None
    returned_units: Decimal | None = None
    item_count: int = 0
    currency_code: str | None = None
    realised: bool = False
    data_quality_status: CanonicalDataQualityStatus
    data_status: AnalyticsDataStatus


class SalesWorkspaceLineItem(BaseModel):
    """Detailed order/sale line item."""

    line_number: int
    product_id: UUID | None = None
    product_external_id: str | None = None
    product_code: str | None = None
    product_name: str | None = None
    warehouse_id: UUID | None = None
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    price_type_code: str | None = None
    ordered_quantity: Decimal | None = None
    sold_quantity: Decimal | None = None
    returned_quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    vat_percent: Decimal | None = None
    vat_amount: Decimal | None = None
    margin_amount: Decimal | None = None
    currency_code: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class SalesWorkspaceReturnItem(BaseModel):
    """Linked return line."""

    return_id: UUID
    return_number: str | None = None
    return_at: datetime | None = None
    product_code: str | None = None
    product_name: str | None = None
    returned_quantity: Decimal | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    reason_code: str | None = None
    status: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class SalesWorkspacePaymentItem(BaseModel):
    """Deterministically linked payment allocation."""

    payment_id: UUID
    payment_number: str | None = None
    paid_at: datetime | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    normalized_payment_type: str | None = None
    allocation_type: str
    data_quality_status: CanonicalDataQualityStatus


class SalesWorkspaceProvenance(BaseModel):
    """Debug/admin provenance for one canonical business record."""

    source_endpoint: str
    source_external_id: str
    source_raw_record_id: UUID | None = None
    request_filial_id: str | None = None
    response_filial_id: str | None = None
    request_company_id: str | None = None
    request_project_code: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class SalesWorkspaceDetail(BaseModel):
    """Order / Sale 360 detail payload."""

    record_id: UUID
    row: SalesWorkspaceTableRow
    items: list[SalesWorkspaceLineItem] = Field(default_factory=list)
    returns: list[SalesWorkspaceReturnItem] = Field(default_factory=list)
    payments: list[SalesWorkspacePaymentItem] = Field(default_factory=list)
    provenance: SalesWorkspaceProvenance
    limitations: list[str] = Field(default_factory=list)


class SalesWorkspaceResponse(BaseModel):
    """Top-level response for the Sales / Orders page."""

    period: AnalyticsPeriodWindow
    summary: SalesWorkspaceSummary
    filters: SalesWorkspaceFilterMetadata
    rows: list[SalesWorkspaceTableRow]
    pagination: SalesWorkspacePagination
