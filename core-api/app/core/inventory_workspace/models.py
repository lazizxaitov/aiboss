"""Pydantic contracts for the Inventory / Warehouse workspace."""

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


class InventoryWorkspaceView(StrEnum):
    CURRENT_STOCK = "current_stock"
    WAREHOUSES = "warehouses"
    PURCHASES = "purchases"
    RECEIPTS = "receipts"
    WRITEOFFS = "writeoffs"
    MOVEMENTS = "movements"
    STOCKTAKING = "stocktaking"
    SUPPLIER_RETURNS = "supplier_returns"


class InventoryWorkspaceSortBy(StrEnum):
    PRODUCT_NAME = "product_name"
    WAREHOUSE = "warehouse"
    ORGANIZATION = "organization"
    QUANTITY = "quantity"
    SNAPSHOT_DATE = "snapshot_date"
    STOCK_STATUS = "stock_status"
    DOCUMENT_DATE = "document_date"
    AMOUNT = "amount"


class InventoryWorkspaceSortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class InventoryWorkspaceStockStatus(StrEnum):
    IN_STOCK = "IN_STOCK"
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    OVERSTOCK = "OVERSTOCK"
    STOCKOUT_RISK = "STOCKOUT_RISK"
    NEGATIVE_STOCK = "NEGATIVE_STOCK"


class InventoryWorkspaceCapabilityStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    NO_DATA = "NO_DATA"
    NO_VERIFIED_DATA = "NO_VERIFIED_DATA"
    NOT_IMPORTED = "NOT_IMPORTED"
    SOURCE_NOT_AVAILABLE = "SOURCE_NOT_AVAILABLE"
    PERMISSION_RESTRICTED = "PERMISSION_RESTRICTED"
    UNRESOLVED = "UNRESOLVED"


class InventoryWorkspaceFilterOption(BaseModel):
    value: str
    label: str
    count: int = 0


class InventoryWorkspaceFiltersMetadata(BaseModel):
    organizations: list[InventoryWorkspaceFilterOption] = Field(default_factory=list)
    warehouses: list[InventoryWorkspaceFilterOption] = Field(default_factory=list)
    categories: list[InventoryWorkspaceFilterOption] = Field(default_factory=list)
    products: list[InventoryWorkspaceFilterOption] = Field(default_factory=list)
    stock_statuses: list[InventoryWorkspaceFilterOption] = Field(default_factory=list)
    data_quality: list[InventoryWorkspaceFilterOption] = Field(default_factory=list)


class InventoryWorkspacePagination(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class InventoryWorkspaceQuery(BaseModel):
    view: InventoryWorkspaceView = InventoryWorkspaceView.CURRENT_STOCK
    search: str | None = None
    warehouse_id: list[str] = Field(default_factory=list)
    product_id: list[UUID] = Field(default_factory=list)
    category_id: list[UUID] = Field(default_factory=list)
    stock_status: list[InventoryWorkspaceStockStatus] = Field(default_factory=list)
    has_stock: bool | None = None
    zero_stock: bool | None = None
    negative_stock: bool | None = None
    data_quality: list[CanonicalDataQualityStatus] = Field(default_factory=list)
    sort_by: InventoryWorkspaceSortBy = InventoryWorkspaceSortBy.SNAPSHOT_DATE
    sort_order: InventoryWorkspaceSortOrder = InventoryWorkspaceSortOrder.DESC
    page: int = 1
    page_size: int = 25


class InventoryWorkspaceSummary(BaseModel):
    current_stock_quantity: AnalyticsMetricValue
    products_in_stock: AnalyticsMetricValue
    warehouses: AnalyticsMetricValue
    zero_stock_products: AnalyticsMetricValue
    negative_stock_products: AnalyticsMetricValue
    low_stock_signals: AnalyticsMetricValue
    overstock_signals: AnalyticsMetricValue
    inventory_value: AnalyticsMetricValue


class InventoryWorkspaceTabStatus(BaseModel):
    view: InventoryWorkspaceView
    label: str
    count: int = 0
    status: InventoryWorkspaceCapabilityStatus
    note: str | None = None


class InventoryWorkspaceCurrentStockRow(BaseModel):
    inventory_balance_id: UUID
    organization_id: UUID
    organization_name: str
    warehouse_id: UUID | None = None
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    product_id: UUID | None = None
    product_code: str | None = None
    product_name: str
    category_id: UUID | None = None
    category_name: str | None = None
    quantity: Decimal | None = None
    available_quantity: Decimal | None = None
    reserved_quantity: Decimal | None = None
    snapshot_date: datetime | None = None
    valuation_amount: Decimal | None = None
    currency_code: str | None = None
    sales_velocity_30d: Decimal | None = None
    days_of_stock: Decimal | None = None
    stock_status: InventoryWorkspaceStockStatus
    stock_status_reason: str | None = None
    data_quality_status: CanonicalDataQualityStatus
    data_status: AnalyticsDataStatus
    batch_number: str | None = None
    expiry_date: datetime | None = None
    inventory_kind: str | None = None


class InventoryWorkspaceWarehouseRow(BaseModel):
    warehouse_key: str
    warehouse_id: UUID | None = None
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    organization_id: UUID
    organization_name: str
    products_count: int = 0
    current_quantity: Decimal | None = None
    last_snapshot: datetime | None = None
    low_stock_count: int = 0
    out_of_stock_count: int = 0
    overstock_count: int = 0
    negative_stock_count: int = 0
    data_quality_status: CanonicalDataQualityStatus


class InventoryWorkspacePurchaseRow(BaseModel):
    purchase_id: UUID
    source_external_id: str
    document_number: str | None = None
    document_date: datetime | None = None
    organization_id: UUID
    organization_name: str
    warehouse_id: UUID | None = None
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    supplier_code: str | None = None
    supplier_external_id: str | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    status: str | None = None
    items_count: int = 0
    total_quantity: Decimal | None = None
    product_linkage_coverage: Decimal | None = None
    warehouse_linkage_coverage: Decimal | None = None
    data_quality_status: CanonicalDataQualityStatus
    quality_note: str | None = None


class InventoryWorkspaceReceiptRow(BaseModel):
    receipt_id: UUID
    source_external_id: str
    document_number: str | None = None
    document_date: datetime | None = None
    organization_id: UUID
    organization_name: str
    warehouse_id: UUID | None = None
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    supplier_code: str | None = None
    supplier_external_id: str | None = None
    linked_purchase_external_id: str | None = None
    items_count: int = 0
    total_quantity: Decimal | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    data_quality_status: CanonicalDataQualityStatus
    quality_note: str | None = None


class InventoryWorkspaceWriteoffRow(BaseModel):
    writeoff_id: UUID
    source_external_id: str
    document_number: str | None = None
    document_date: datetime | None = None
    organization_id: UUID
    organization_name: str
    warehouse_id: UUID | None = None
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    reason_code: str | None = None
    items_count: int = 0
    total_quantity: Decimal | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    status: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class InventoryWorkspaceMovementRow(BaseModel):
    movement_id: UUID
    movement_type: str
    source_external_id: str
    document_number: str | None = None
    document_date: datetime | None = None
    organization_id: UUID
    organization_name: str
    source_organization_name: str | None = None
    source_warehouse_code: str | None = None
    source_warehouse_name: str | None = None
    destination_organization_name: str | None = None
    destination_warehouse_code: str | None = None
    destination_warehouse_name: str | None = None
    total_quantity: Decimal | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    direction: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class InventoryWorkspaceStocktakingRow(BaseModel):
    stocktaking_id: UUID
    source_external_id: str
    document_number: str | None = None
    document_date: datetime | None = None
    organization_id: UUID
    organization_name: str
    warehouse_id: UUID | None = None
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    items_count: int = 0
    total_quantity: Decimal | None = None
    data_quality_status: CanonicalDataQualityStatus


class InventoryWorkspaceSupplierReturnRow(BaseModel):
    supplier_return_id: UUID
    source_external_id: str
    document_number: str | None = None
    document_date: datetime | None = None
    organization_id: UUID
    organization_name: str
    warehouse_id: UUID | None = None
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    supplier_code: str | None = None
    supplier_external_id: str | None = None
    reason_code: str | None = None
    items_count: int = 0
    total_quantity: Decimal | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class InventoryWorkspaceRows(BaseModel):
    current_stock: list[InventoryWorkspaceCurrentStockRow] = Field(default_factory=list)
    warehouses: list[InventoryWorkspaceWarehouseRow] = Field(default_factory=list)
    purchases: list[InventoryWorkspacePurchaseRow] = Field(default_factory=list)
    receipts: list[InventoryWorkspaceReceiptRow] = Field(default_factory=list)
    writeoffs: list[InventoryWorkspaceWriteoffRow] = Field(default_factory=list)
    movements: list[InventoryWorkspaceMovementRow] = Field(default_factory=list)
    stocktaking: list[InventoryWorkspaceStocktakingRow] = Field(default_factory=list)
    supplier_returns: list[InventoryWorkspaceSupplierReturnRow] = Field(default_factory=list)


class InventoryWorkspaceCurrentStockDetail(BaseModel):
    row: InventoryWorkspaceCurrentStockRow
    recent_snapshots: list[InventoryWorkspaceCurrentStockRow] = Field(default_factory=list)
    recent_receipts: list[InventoryWorkspaceReceiptRow] = Field(default_factory=list)
    recent_writeoffs: list[InventoryWorkspaceWriteoffRow] = Field(default_factory=list)
    recent_movements: list[InventoryWorkspaceMovementRow] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class InventoryWorkspaceWarehouseDetail(BaseModel):
    row: InventoryWorkspaceWarehouseRow
    current_stock: list[InventoryWorkspaceCurrentStockRow] = Field(default_factory=list)
    purchases: list[InventoryWorkspacePurchaseRow] = Field(default_factory=list)
    receipts: list[InventoryWorkspaceReceiptRow] = Field(default_factory=list)
    writeoffs: list[InventoryWorkspaceWriteoffRow] = Field(default_factory=list)
    movements: list[InventoryWorkspaceMovementRow] = Field(default_factory=list)
    stocktaking: list[InventoryWorkspaceStocktakingRow] = Field(default_factory=list)
    supplier_returns: list[InventoryWorkspaceSupplierReturnRow] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class InventoryWorkspaceResponse(BaseModel):
    period: AnalyticsPeriodWindow
    active_view: InventoryWorkspaceView
    summary: InventoryWorkspaceSummary
    tabs: list[InventoryWorkspaceTabStatus] = Field(default_factory=list)
    filters: InventoryWorkspaceFiltersMetadata
    pagination: InventoryWorkspacePagination
    rows: InventoryWorkspaceRows
