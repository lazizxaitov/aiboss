"""Pydantic contracts for the Finance workspace."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.analytics.models import (
    AnalyticsDataQualityReport,
    AnalyticsDataStatus,
    AnalyticsMetricValue,
    AnalyticsPeriodWindow,
)
from app.core.data_layer.canonical_v2 import CanonicalDataQualityStatus


class FinanceWorkspaceView(StrEnum):
    OVERVIEW = "overview"
    PAYMENTS = "payments"
    CASH_OPERATIONS = "cash_operations"
    BANK_OPERATIONS = "bank_operations"
    FINANCIAL_OPERATIONS = "financial_operations"
    RETURNS = "returns"
    ACCOUNTS = "accounts"


class FinanceWorkspaceSortBy(StrEnum):
    DATE = "date"
    AMOUNT = "amount"
    ORGANIZATION = "organization"
    OPERATION_TYPE = "operation_type"
    DIRECTION = "direction"
    CUSTOMER = "customer"
    ACCOUNT = "account"


class FinanceWorkspaceSortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class FinanceWorkspaceCapabilityStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    NO_DATA = "NO_DATA"
    NO_VERIFIED_DATA = "NO_VERIFIED_DATA"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    UNRESOLVED = "UNRESOLVED"


class FinanceWorkspaceDirection(StrEnum):
    INFLOW = "INFLOW"
    OUTFLOW = "OUTFLOW"
    TRANSFER = "TRANSFER"
    UNKNOWN = "UNKNOWN"


class FinanceWorkspaceFilterOption(BaseModel):
    value: str
    label: str
    count: int = 0


class FinanceWorkspaceFiltersMetadata(BaseModel):
    organizations: list[FinanceWorkspaceFilterOption] = Field(default_factory=list)
    directions: list[FinanceWorkspaceFilterOption] = Field(default_factory=list)
    operation_types: list[FinanceWorkspaceFilterOption] = Field(default_factory=list)
    payment_types: list[FinanceWorkspaceFilterOption] = Field(default_factory=list)
    counterparties: list[FinanceWorkspaceFilterOption] = Field(default_factory=list)
    accounts: list[FinanceWorkspaceFilterOption] = Field(default_factory=list)
    currencies: list[FinanceWorkspaceFilterOption] = Field(default_factory=list)
    data_quality: list[FinanceWorkspaceFilterOption] = Field(default_factory=list)


class FinanceWorkspacePagination(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class FinanceWorkspaceQuery(BaseModel):
    view: FinanceWorkspaceView = FinanceWorkspaceView.OVERVIEW
    search: str | None = None
    direction: list[FinanceWorkspaceDirection] = Field(default_factory=list)
    operation_type: list[str] = Field(default_factory=list)
    payment_type: list[str] = Field(default_factory=list)
    counterparty: list[str] = Field(default_factory=list)
    account: list[str] = Field(default_factory=list)
    currency: list[str] = Field(default_factory=list)
    data_quality: list[CanonicalDataQualityStatus] = Field(default_factory=list)
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    sort_by: FinanceWorkspaceSortBy = FinanceWorkspaceSortBy.DATE
    sort_order: FinanceWorkspaceSortOrder = FinanceWorkspaceSortOrder.DESC
    page: int = 1
    page_size: int = 25


class FinanceWorkspaceSummary(BaseModel):
    payments_received: AnalyticsMetricValue
    verified_cash_in: AnalyticsMetricValue
    verified_cash_out: AnalyticsMetricValue
    net_cash_flow: AnalyticsMetricValue
    customer_return_value: AnalyticsMetricValue
    financial_operations_count: AnalyticsMetricValue


class FinanceWorkspaceCoverageItem(BaseModel):
    key: str
    label: str
    status: FinanceWorkspaceCapabilityStatus
    message: str
    affected_domains: list[str] = Field(default_factory=list)


class FinanceWorkspaceTabStatus(BaseModel):
    view: FinanceWorkspaceView
    label: str
    count: int = 0
    status: FinanceWorkspaceCapabilityStatus
    note: str | None = None


class FinanceWorkspaceProvenance(BaseModel):
    source_endpoint: str
    source_external_id: str
    source_raw_record_id: UUID | None = None
    request_filial_id: str | None = None
    response_filial_id: str | None = None
    request_company_id: str | None = None
    request_project_code: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class FinanceWorkspaceOverviewRow(BaseModel):
    organization_id: UUID
    organization_name: str
    payments_received: Decimal | None = None
    verified_cash_in: Decimal | None = None
    verified_cash_out: Decimal | None = None
    customer_return_value: Decimal | None = None
    financial_operations_count: int = 0
    payments_count: int = 0
    returns_count: int = 0
    purchases_count: int = 0
    writeoffs_count: int = 0
    data_status: AnalyticsDataStatus


class FinanceWorkspacePaymentRow(BaseModel):
    payment_id: UUID
    source_external_id: str
    payment_number: str | None = None
    paid_at: datetime | None = None
    organization_id: UUID
    organization_name: str
    customer_id: UUID | None = None
    customer_name: str | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    payment_type: str | None = None
    cashbox_or_account: str | None = None
    purpose: str | None = None
    allocation_status: str
    linked_order_id: UUID | None = None
    linked_order_external_id: str | None = None
    linked_sale_id: UUID | None = None
    linked_sale_external_id: str | None = None
    linked_order_number: str | None = None
    data_quality_status: CanonicalDataQualityStatus
    data_status: AnalyticsDataStatus
    provenance: FinanceWorkspaceProvenance


class FinanceWorkspaceOperationRow(BaseModel):
    operation_id: UUID
    source_external_id: str
    source_type: str
    source_label: str
    operation_number: str | None = None
    operation_at: datetime | None = None
    organization_id: UUID
    organization_name: str
    operation_type: str | None = None
    direction: FinanceWorkspaceDirection
    account_id: UUID | None = None
    account_label: str | None = None
    counterparty_type: str | None = None
    counterparty_id: UUID | None = None
    counterparty_name: str | None = None
    purpose: str | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    posted: str | None = None
    is_internal_transfer: bool = False
    overlaps_customer_payment: bool = False
    overlap_note: str | None = None
    source_document_type: str | None = None
    source_document_external_id: str | None = None
    data_quality_status: CanonicalDataQualityStatus
    data_status: AnalyticsDataStatus
    provenance: FinanceWorkspaceProvenance


class FinanceWorkspaceReturnRow(BaseModel):
    customer_return_id: UUID
    source_external_id: str
    return_number: str | None = None
    return_at: datetime | None = None
    organization_id: UUID
    organization_name: str
    customer_id: UUID | None = None
    customer_name: str | None = None
    value: Decimal | None = None
    currency_code: str | None = None
    returned_units: Decimal | None = None
    products_count: int = 0
    reason_code: str | None = None
    status: str | None = None
    cash_refund_status: str
    data_quality_status: CanonicalDataQualityStatus
    data_status: AnalyticsDataStatus
    provenance: FinanceWorkspaceProvenance


class FinanceWorkspaceAccountRow(BaseModel):
    account_id: UUID
    source_external_id: str
    organization_id: UUID
    organization_name: str
    account_code: str
    account_name: str | None = None
    account_type: str | None = None
    currency_code: str | None = None
    bank_name: str | None = None
    bank_account_code: str | None = None
    cashbox_code: str | None = None
    data_quality_status: CanonicalDataQualityStatus
    data_status: AnalyticsDataStatus
    provenance: FinanceWorkspaceProvenance


class FinanceWorkspaceRows(BaseModel):
    overview: list[FinanceWorkspaceOverviewRow] = Field(default_factory=list)
    payments: list[FinanceWorkspacePaymentRow] = Field(default_factory=list)
    cash_operations: list[FinanceWorkspaceOperationRow] = Field(default_factory=list)
    bank_operations: list[FinanceWorkspaceOperationRow] = Field(default_factory=list)
    financial_operations: list[FinanceWorkspaceOperationRow] = Field(default_factory=list)
    returns: list[FinanceWorkspaceReturnRow] = Field(default_factory=list)
    accounts: list[FinanceWorkspaceAccountRow] = Field(default_factory=list)


class FinanceWorkspaceResponse(BaseModel):
    period: AnalyticsPeriodWindow
    active_view: FinanceWorkspaceView
    summary: FinanceWorkspaceSummary
    coverage: list[FinanceWorkspaceCoverageItem] = Field(default_factory=list)
    tabs: list[FinanceWorkspaceTabStatus] = Field(default_factory=list)
    filters: FinanceWorkspaceFiltersMetadata
    data_quality: AnalyticsDataQualityReport
    rows: FinanceWorkspaceRows
    pagination: FinanceWorkspacePagination
