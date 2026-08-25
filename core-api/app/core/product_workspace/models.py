"""Pydantic contracts for the Products / Product 360 business workspace."""

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


class ProductWorkspaceSortBy(StrEnum):
    """Supported sort fields for the products workspace."""

    PRODUCT_NAME = "product_name"
    REVENUE = "revenue"
    SOLD_UNITS = "sold_units"
    ORDERS = "orders"
    CUSTOMERS = "customers"
    CURRENT_STOCK = "current_stock"
    LAST_SALE = "last_sale"
    RETURN_QUANTITY = "return_quantity"


class ProductWorkspaceSortOrder(StrEnum):
    """Supported sort directions for the products workspace."""

    ASC = "asc"
    DESC = "desc"


class ProductWorkspaceStockStatus(StrEnum):
    """Deterministic product stock status."""

    IN_STOCK = "IN_STOCK"
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    OVERSTOCK = "OVERSTOCK"


class ProductWorkspaceFilterOption(BaseModel):
    """Selectable filter option."""

    value: str
    label: str
    count: int = 0


class ProductWorkspaceFilterMetadata(BaseModel):
    """Available filters for the current products scope."""

    organizations: list[ProductWorkspaceFilterOption] = Field(default_factory=list)
    categories: list[ProductWorkspaceFilterOption] = Field(default_factory=list)
    stock_statuses: list[ProductWorkspaceFilterOption] = Field(default_factory=list)
    data_quality: list[ProductWorkspaceFilterOption] = Field(default_factory=list)


class ProductWorkspacePagination(BaseModel):
    """Page metadata for the products table."""

    page: int
    page_size: int
    total_items: int
    total_pages: int


class ProductWorkspaceQuery(BaseModel):
    """Query filters for the products workspace."""

    search: str | None = None
    category_id: list[UUID] = Field(default_factory=list)
    stock_status: list[ProductWorkspaceStockStatus] = Field(default_factory=list)
    has_sales: bool | None = None
    has_returns: bool | None = None
    data_quality: list[CanonicalDataQualityStatus] = Field(default_factory=list)
    revenue_min: Decimal | None = None
    revenue_max: Decimal | None = None
    sold_units_min: Decimal | None = None
    sold_units_max: Decimal | None = None
    sort_by: ProductWorkspaceSortBy = ProductWorkspaceSortBy.REVENUE
    sort_order: ProductWorkspaceSortOrder = ProductWorkspaceSortOrder.DESC
    page: int = 1
    page_size: int = 25


class ProductWorkspaceSummary(BaseModel):
    """Top summary strip for the products page."""

    products: AnalyticsMetricValue
    products_sold: AnalyticsMetricValue
    sold_units: AnalyticsMetricValue
    revenue: AnalyticsMetricValue
    average_selling_price: AnalyticsMetricValue
    current_stock: AnalyticsMetricValue
    out_of_stock: AnalyticsMetricValue
    low_stock: AnalyticsMetricValue
    overstock: AnalyticsMetricValue
    return_quantity: AnalyticsMetricValue
    return_value: AnalyticsMetricValue


class ProductWorkspaceRow(BaseModel):
    """One row in the products business table."""

    product_id: UUID
    product_external_id: str
    product_code: str | None = None
    product_name: str
    category_id: UUID | None = None
    category_name: str | None = None
    organization_ids: list[UUID] = Field(default_factory=list)
    organization_names: list[str] = Field(default_factory=list)
    measure_code: str | None = None
    producer_code: str | None = None
    article_code: str | None = None
    barcodes: list[str] = Field(default_factory=list)
    sold_units: Decimal | None = None
    revenue: Decimal | None = None
    orders_count: Decimal | None = None
    customers_count: Decimal | None = None
    average_selling_price: Decimal | None = None
    current_stock: Decimal | None = None
    last_sale: datetime | None = None
    first_sale: datetime | None = None
    return_quantity: Decimal | None = None
    return_value: Decimal | None = None
    stock_status: ProductWorkspaceStockStatus | None = None
    stock_status_reason: str | None = None
    data_quality_status: CanonicalDataQualityStatus
    data_status: AnalyticsDataStatus


class ProductWorkspaceSaleRow(BaseModel):
    """Sales row inside Product 360."""

    sale_item_id: UUID
    sale_id: UUID | None = None
    order_id: UUID | None = None
    business_date: datetime | None = None
    organization_id: UUID
    organization_name: str
    order_number: str | None = None
    sale_number: str | None = None
    deal_id: str | None = None
    customer_id: UUID | None = None
    customer_name: str | None = None
    sold_quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    display_status: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class ProductWorkspaceOrganizationRow(BaseModel):
    """Per-organization product breakdown."""

    organization_id: UUID
    organization_name: str
    revenue: Decimal | None = None
    sold_units: Decimal | None = None
    orders_count: Decimal | None = None
    customers_count: Decimal | None = None
    current_stock: Decimal | None = None
    last_sale: datetime | None = None
    stock_status: ProductWorkspaceStockStatus | None = None
    data_quality_status: CanonicalDataQualityStatus


class ProductWorkspaceCustomerRow(BaseModel):
    """Customer buyers row inside Product 360."""

    customer_id: UUID
    customer_name: str
    organization_id: UUID
    organization_name: str
    sold_units: Decimal | None = None
    revenue: Decimal | None = None
    orders_count: Decimal | None = None
    last_purchase: datetime | None = None
    data_quality_status: CanonicalDataQualityStatus


class ProductWorkspaceInventoryRow(BaseModel):
    """Current stock row inside Product 360."""

    inventory_balance_id: UUID
    organization_id: UUID
    organization_name: str
    warehouse_id: UUID | None = None
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    snapshot_date: datetime | None = None
    quantity: Decimal | None = None
    available_quantity: Decimal | None = None
    reserved_quantity: Decimal | None = None
    input_price: Decimal | None = None
    valuation_amount: Decimal | None = None
    currency_code: str | None = None
    batch_number: str | None = None
    card_code: str | None = None
    serial_number: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class ProductWorkspacePriceRow(BaseModel):
    """Price row inside Product 360."""

    price_id: UUID | None = None
    source_type: str
    organization_id: UUID
    organization_name: str
    price_type_code: str | None = None
    price_type_name: str | None = None
    price: Decimal | None = None
    currency_code: str | None = None
    effective_date: datetime | None = None
    note: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class ProductWorkspaceReturnRow(BaseModel):
    """Return row inside Product 360."""

    return_item_id: UUID
    return_id: UUID
    organization_id: UUID
    organization_name: str
    return_number: str | None = None
    return_at: datetime | None = None
    customer_id: UUID | None = None
    customer_name: str | None = None
    returned_quantity: Decimal | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    status: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class ProductWorkspaceTimelineEvent(BaseModel):
    """Chronological product activity event."""

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


class ProductWorkspaceProvenance(BaseModel):
    """Admin/debug provenance for a canonical product."""

    canonical_product_id: UUID
    source_endpoint: str
    source_external_id: str
    source_raw_record_id: UUID | None = None
    request_filial_id: str | None = None
    response_filial_id: str | None = None
    request_company_id: str | None = None
    request_project_code: str | None = None
    data_quality_status: CanonicalDataQualityStatus
    reference_sources: list[str] = Field(default_factory=list)


class ProductWorkspaceDetail(BaseModel):
    """Product 360 payload."""

    product_id: UUID
    row: ProductWorkspaceRow
    overview: ProductWorkspaceSummary
    sales: list[ProductWorkspaceSaleRow] = Field(default_factory=list)
    organizations: list[ProductWorkspaceOrganizationRow] = Field(default_factory=list)
    customers: list[ProductWorkspaceCustomerRow] = Field(default_factory=list)
    inventory: list[ProductWorkspaceInventoryRow] = Field(default_factory=list)
    prices: list[ProductWorkspacePriceRow] = Field(default_factory=list)
    returns: list[ProductWorkspaceReturnRow] = Field(default_factory=list)
    timeline: list[ProductWorkspaceTimelineEvent] = Field(default_factory=list)
    ai_summary: str | None = None
    provenance: ProductWorkspaceProvenance
    limitations: list[str] = Field(default_factory=list)


class ProductWorkspaceResponse(BaseModel):
    """Top-level response for the products page."""

    period: AnalyticsPeriodWindow
    summary: ProductWorkspaceSummary
    filters: ProductWorkspaceFilterMetadata
    rows: list[ProductWorkspaceRow]
    pagination: ProductWorkspacePagination
