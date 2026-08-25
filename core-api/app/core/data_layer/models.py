"""Canonical data contracts for the core data layer."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class DataSourceType(StrEnum):
    """High-level data ingestion source types."""

    MANUAL = "manual"
    API = "api"
    IMPORT = "import"
    STREAM = "stream"


class CoreRecordKind(StrEnum):
    """Canonical business record families."""

    CUSTOMER = "customer"
    SALE = "sale"
    MARKETING = "marketing"
    FINANCE = "finance"
    DOCUMENT = "document"
    EVENT = "event"


class BusinessIdentity(BaseModel):
    """Single business identity in the shared core layer."""

    business_id: UUID = Field(default_factory=uuid4)
    name: str
    display_name: str | None = None
    external_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CoreRecord(BaseModel):
    """Generic normalized record stored in the system of record."""

    record_id: UUID = Field(default_factory=uuid4)
    business_id: UUID
    source: str
    source_type: DataSourceType = DataSourceType.API
    kind: CoreRecordKind
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class KPIValue(BaseModel):
    """Normalized KPI snapshot for dashboard and agents."""

    business_id: UUID
    metric_key: str
    value: float
    unit: str
    period_start: datetime | None = None
    period_end: datetime | None = None
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)
