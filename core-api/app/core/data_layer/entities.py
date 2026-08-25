"""Canonical business entities stored in the core data layer."""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SaleStage(StrEnum):
    """Normalized sale lifecycle states."""

    LEAD = "lead"
    QUALIFIED = "qualified"
    WON = "won"
    LOST = "lost"
    REFUNDED = "refunded"


class MarketingChannel(StrEnum):
    """Supported marketing source channels."""

    META_ADS = "meta_ads"
    YOUTUBE = "youtube"
    TELEGRAM = "telegram"
    OTHER = "other"


class FinanceEntryType(StrEnum):
    """Canonical finance entry types."""

    REVENUE = "revenue"
    EXPENSE = "expense"
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"


class IngestionBatchStatus(StrEnum):
    """Lifecycle status for data migration batches."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PERMISSION_DENIED = "permission_denied"


class BusinessProfile(BaseModel):
    """Master business record in the single source of truth."""

    business_id: UUID = Field(default_factory=uuid4)
    name: str
    legal_name: str | None = None
    external_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceSystem(BaseModel):
    """External source connected to a business in the core layer."""

    source_system_id: UUID = Field(default_factory=uuid4)
    business_id: UUID
    name: str
    source_type: str
    external_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContactProfile(BaseModel):
    """Normalized customer or contact profile."""

    contact_id: UUID = Field(default_factory=uuid4)
    business_id: UUID
    full_name: str
    email: str | None = None
    phone: str | None = None
    source: str | None = None
    external_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SaleRecord(BaseModel):
    """Normalized sale fact."""

    sale_id: UUID = Field(default_factory=uuid4)
    business_id: UUID
    contact_id: UUID | None = None
    external_ref: str | None = None
    amount: Decimal
    currency: str = "USD"
    stage: SaleStage = SaleStage.WON
    occurred_at: datetime
    closed_at: datetime | None = None
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarketingActivity(BaseModel):
    """Normalized marketing activity snapshot."""

    activity_id: UUID = Field(default_factory=uuid4)
    business_id: UUID
    external_ref: str | None = None
    channel: MarketingChannel
    campaign_name: str
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    spend: Decimal = Decimal("0")
    occurred_at: datetime
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FinanceEntry(BaseModel):
    """Normalized finance ledger entry."""

    entry_id: UUID = Field(default_factory=uuid4)
    business_id: UUID
    external_ref: str | None = None
    entry_type: FinanceEntryType
    category: str
    amount: Decimal
    currency: str = "USD"
    occurred_at: datetime
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionBatch(BaseModel):
    """A single migration or synchronization batch."""

    batch_id: UUID = Field(default_factory=uuid4)
    business_id: UUID | None = None
    source_system_id: UUID | None = None
    batch_name: str
    status: IngestionBatchStatus = IngestionBatchStatus.PENDING
    started_at: datetime
    finished_at: datetime | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionError(BaseModel):
    """Validation or transport error captured during ingestion."""

    error_id: UUID = Field(default_factory=uuid4)
    batch_id: UUID
    business_id: UUID | None = None
    source_row_key: str | None = None
    entity_type: str
    error_code: str
    error_message: str
    raw_payload: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AppSetting(BaseModel):
    """Application-level key/value setting stored in the core data layer."""

    setting_id: UUID = Field(default_factory=uuid4)
    setting_key: str
    setting_value: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


BusinessIdentity = BusinessProfile
