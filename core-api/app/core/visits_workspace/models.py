"""Pydantic contracts for the Visits / Field Sales workspace."""

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


class VisitsWorkspaceSortBy(StrEnum):
    """Supported sort fields for the visits workspace."""

    DATE = "date"
    CUSTOMER = "customer"
    SALES_REP = "sales_rep"
    WORKING_ZONE = "working_zone"
    STATUS = "status"
    ORGANIZATION = "organization"


class VisitsWorkspaceSortOrder(StrEnum):
    """Supported sort directions for the visits workspace."""

    ASC = "asc"
    DESC = "desc"


class VisitsWorkspaceTab(StrEnum):
    """Top-level full-width workspace tabs."""

    VISITS = "visits"
    SALES_REPS = "sales_reps"
    WORKING_ZONES = "working_zones"
    CAPABILITIES = "capabilities"


class VisitsWorkspaceCapabilityStatus(StrEnum):
    """Capability state surfaced to the UI."""

    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    NO_DATA = "NO_DATA"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    NO_DATA_IN_CURRENT_RAW = "NO_DATA_IN_CURRENT_RAW"


class VisitsWorkspaceFilterOption(BaseModel):
    """Selectable filter option."""

    value: str
    label: str
    count: int = 0


class VisitsWorkspaceFiltersMetadata(BaseModel):
    """Available filters for the current visits scope."""

    organizations: list[VisitsWorkspaceFilterOption] = Field(default_factory=list)
    customers: list[VisitsWorkspaceFilterOption] = Field(default_factory=list)
    sales_reps: list[VisitsWorkspaceFilterOption] = Field(default_factory=list)
    working_zones: list[VisitsWorkspaceFilterOption] = Field(default_factory=list)
    statuses: list[VisitsWorkspaceFilterOption] = Field(default_factory=list)
    planned: list[VisitsWorkspaceFilterOption] = Field(default_factory=list)
    data_quality: list[VisitsWorkspaceFilterOption] = Field(default_factory=list)


class VisitsWorkspacePagination(BaseModel):
    """Page metadata for visits tables."""

    page: int
    page_size: int
    total_items: int
    total_pages: int


class VisitsWorkspaceQuery(BaseModel):
    """Query filters for the visits workspace."""

    tab: VisitsWorkspaceTab = VisitsWorkspaceTab.VISITS
    search: str | None = None
    customer: list[str] = Field(default_factory=list)
    sales_rep: list[str] = Field(default_factory=list)
    working_zone: list[str] = Field(default_factory=list)
    status: list[str] = Field(default_factory=list)
    planned: list[str] = Field(default_factory=list)
    data_quality: list[CanonicalDataQualityStatus] = Field(default_factory=list)
    sort_by: VisitsWorkspaceSortBy = VisitsWorkspaceSortBy.DATE
    sort_order: VisitsWorkspaceSortOrder = VisitsWorkspaceSortOrder.DESC
    page: int = 1
    page_size: int = 25


class VisitsWorkspaceSummary(BaseModel):
    """Top summary strip for field sales workspace."""

    visits: AnalyticsMetricValue
    unique_customers: AnalyticsMetricValue
    sales_reps: AnalyticsMetricValue
    working_zones: AnalyticsMetricValue
    planned_visits: AnalyticsMetricValue
    completed_visits: AnalyticsMetricValue
    average_duration: AnalyticsMetricValue
    visit_conversion: AnalyticsMetricValue


class VisitsWorkspaceTabStatus(BaseModel):
    """Availability and count for one subview."""

    tab: VisitsWorkspaceTab
    label: str
    count: int = 0
    status: VisitsWorkspaceCapabilityStatus
    note: str | None = None


class VisitsWorkspaceVisitRow(BaseModel):
    """One visit row in the main workspace table."""

    visit_id: UUID
    source_visit_id: str | None = None
    source_external_id: str
    business_date: datetime | None = None
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
    normalized_status: str
    display_status: str
    is_planned: bool | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_seconds: int | None = None
    has_comments: bool = False
    has_media: bool = False
    has_visit_stock: bool = False
    has_quiz_answers: bool = False
    has_equipment: bool = False
    data_quality_status: CanonicalDataQualityStatus
    data_status: AnalyticsDataStatus


class VisitsWorkspaceSalesRepRow(BaseModel):
    """Visits-centric sales rep row."""

    sales_rep_id: UUID
    sales_rep_key: str
    sales_rep_name: str
    organization_ids: list[UUID] = Field(default_factory=list)
    organization_names: list[str] = Field(default_factory=list)
    visits: AnalyticsMetricValue
    unique_customers: AnalyticsMetricValue
    working_zones: AnalyticsMetricValue
    completed_visits: AnalyticsMetricValue
    planned_visits: AnalyticsMetricValue
    visit_conversion: AnalyticsMetricValue
    data_status: AnalyticsDataStatus


class VisitsWorkspaceWorkingZoneRow(BaseModel):
    """Visits-centric working zone row."""

    working_zone_id: UUID
    working_zone_key: str
    working_zone_name: str
    organization_ids: list[UUID] = Field(default_factory=list)
    organization_names: list[str] = Field(default_factory=list)
    visits: AnalyticsMetricValue
    unique_customers: AnalyticsMetricValue
    sales_reps: AnalyticsMetricValue
    data_status: AnalyticsDataStatus


class VisitsWorkspaceCapabilityItem(BaseModel):
    """Business-friendly capability/data coverage row."""

    key: str
    label: str
    status: VisitsWorkspaceCapabilityStatus
    message: str
    count: int | None = None


class VisitsWorkspaceRows(BaseModel):
    """Rows for all tabs."""

    visits: list[VisitsWorkspaceVisitRow] = Field(default_factory=list)
    sales_reps: list[VisitsWorkspaceSalesRepRow] = Field(default_factory=list)
    working_zones: list[VisitsWorkspaceWorkingZoneRow] = Field(default_factory=list)
    capabilities: list[VisitsWorkspaceCapabilityItem] = Field(default_factory=list)


class VisitsWorkspaceProvenance(BaseModel):
    """Admin/debug provenance for one canonical visit."""

    source_endpoint: str
    source_external_id: str
    source_raw_record_id: UUID | None = None
    request_filial_id: str | None = None
    response_filial_id: str | None = None
    request_company_id: str | None = None
    request_project_code: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class VisitsWorkspaceNestedStockRow(BaseModel):
    """Stock observed during visit."""

    line_number: int
    product_id: UUID | None = None
    product_external_id: str | None = None
    product_code: str | None = None
    product_name: str | None = None
    quantity: Decimal | None = None
    expiry_date: datetime | None = None
    card_code: str | None = None
    serial_number: str | None = None
    inventory_kind: str | None = None
    unavailable_reason: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class VisitsWorkspaceNestedQuizRow(BaseModel):
    """Quiz answer captured during visit."""

    line_number: int
    quiz_external_id: str | None = None
    quiz_name: str | None = None
    question_external_id: str | None = None
    question_text: str | None = None
    answer_value: str | None = None
    answer_type: str | None = None
    photo_sha: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class VisitsWorkspaceNestedEquipmentRow(BaseModel):
    """Equipment record attached to visit."""

    line_number: int
    equipment_external_id: str | None = None
    equipment_code: str | None = None
    equipment_name: str | None = None
    serial_number: str | None = None
    status_code: str | None = None
    note: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class VisitsWorkspaceNestedCommentRow(BaseModel):
    """Structured comment attached to visit."""

    line_number: int
    comment_text: str | None = None
    comment_type: str | None = None
    created_by_external_id: str | None = None
    created_at_source: datetime | None = None
    data_quality_status: CanonicalDataQualityStatus


class VisitsWorkspaceNestedMediaRow(BaseModel):
    """Media reference preserved from SmartUp source evidence."""

    media_id: str | None = None
    media_type: str | None = None
    source_sha: str | None = None
    source_reference: str | None = None
    download_status: str
    local_path: str | None = None
    mime_type: str | None = None
    data_quality_status: CanonicalDataQualityStatus


class VisitsWorkspaceRelatedCustomer(BaseModel):
    """Customer block in Visit 360."""

    customer_id: UUID | None = None
    customer_external_id: str | None = None
    customer_code: str | None = None
    customer_name: str | None = None
    detail_href: str | None = None


class VisitsWorkspaceRelatedSalesRep(BaseModel):
    """Sales rep block in Visit 360."""

    sales_rep_id: UUID | None = None
    sales_rep_external_id: str | None = None
    sales_rep_code: str | None = None
    sales_rep_name: str | None = None


class VisitsWorkspaceRelatedWorkingZone(BaseModel):
    """Working zone block in Visit 360."""

    working_zone_id: UUID | None = None
    working_zone_external_id: str | None = None
    working_zone_code: str | None = None
    working_zone_name: str | None = None


class VisitsWorkspaceDetail(BaseModel):
    """Visit 360 payload."""

    visit_id: UUID
    row: VisitsWorkspaceVisitRow
    customer: VisitsWorkspaceRelatedCustomer
    sales_rep: VisitsWorkspaceRelatedSalesRep
    working_zone: VisitsWorkspaceRelatedWorkingZone
    visit_stocks: list[VisitsWorkspaceNestedStockRow] = Field(default_factory=list)
    quiz_answers: list[VisitsWorkspaceNestedQuizRow] = Field(default_factory=list)
    equipments: list[VisitsWorkspaceNestedEquipmentRow] = Field(default_factory=list)
    comments: list[VisitsWorkspaceNestedCommentRow] = Field(default_factory=list)
    media_assets: list[VisitsWorkspaceNestedMediaRow] = Field(default_factory=list)
    related_sales_status: AnalyticsDataStatus
    provenance: VisitsWorkspaceProvenance
    limitations: list[str] = Field(default_factory=list)


class VisitsWorkspaceResponse(BaseModel):
    """Top-level response for the Visits / Field Sales workspace."""

    period: AnalyticsPeriodWindow
    active_tab: VisitsWorkspaceTab
    summary: VisitsWorkspaceSummary
    filters: VisitsWorkspaceFiltersMetadata
    tabs: list[VisitsWorkspaceTabStatus] = Field(default_factory=list)
    rows: VisitsWorkspaceRows
    pagination: VisitsWorkspacePagination
    data_quality: AnalyticsDataQualityReport
