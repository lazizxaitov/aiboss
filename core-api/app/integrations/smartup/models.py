"""SmartUp-specific persistence models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import BaseModel, Field

SMARTUP_INTEGRATION_UUID = uuid5(NAMESPACE_URL, "smartup:default-integration")


class SmartUpMigrationStatus(StrEnum):
    """Lifecycle states for an organization-level migration run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PERMISSION_DENIED = "permission_denied"


class SmartUpMigrationMode(StrEnum):
    """Supported synchronization modes for SmartUp imports."""

    FULL_BACKFILL = "full_backfill"
    WEEKLY_RECONCILIATION = "weekly_reconciliation"
    ONE_DAY_CHECK = "one_day_check"
    LIVE_SYNC = "live_sync"  # Legacy compatibility for already persisted rows.


class SmartUpRawRecordStatus(StrEnum):
    """Processing states for raw SmartUp records."""

    PENDING = "pending"
    NORMALIZED = "normalized"
    SKIPPED = "skipped"
    FAILED = "failed"


class NormalizationIssueSeverity(StrEnum):
    """Severity levels for normalization diagnostics."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class SmartUpOrganization(BaseModel):
    """SmartUp organization connected to the platform."""

    id: UUID = Field(default_factory=uuid4)
    integration_id: UUID = Field(default_factory=lambda: SMARTUP_INTEGRATION_UUID)
    name: str
    company_id: str = "11300"
    filial_id: str
    filial_code: str | None = None
    project_code: str = "trade"
    is_active: bool = True
    sort_order: int = 0
    last_sync_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class SmartUpMigrationRun(BaseModel):
    """Status record for one SmartUp import step."""

    run_id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    entity_type: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    status: SmartUpMigrationStatus = SmartUpMigrationStatus.PENDING
    imported_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def id(self) -> UUID:
        """Compatibility alias for the canonical run identifier."""

        return self.run_id

    @property
    def finished_at(self) -> datetime | None:
        """Compatibility alias for the canonical completion timestamp."""

        return self.completed_at

    @finished_at.setter
    def finished_at(self, value: datetime | None) -> None:
        self.completed_at = value


class SyncCheckpoint(BaseModel):
    """Persistent checkpoint for incremental SmartUp synchronization."""

    id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    entity_type: str
    migration_mode: SmartUpMigrationMode = SmartUpMigrationMode.FULL_BACKFILL
    period_start: datetime
    period_end: datetime
    last_successful_date: datetime | None = None
    last_successful_external_id: str | None = None
    status: SmartUpMigrationStatus = SmartUpMigrationStatus.PENDING
    attempts: int = 0
    last_error: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class MigrationBatch(BaseModel):
    """Traceable SmartUp import batch for a time window."""

    id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    filial_id: str | None = None
    entity_type: str
    endpoint: str | None = None
    request_payload: dict[str, Any] | list[Any] | None = None
    migration_mode: SmartUpMigrationMode = SmartUpMigrationMode.FULL_BACKFILL
    date_from: datetime
    date_to: datetime
    status: SmartUpMigrationStatus = SmartUpMigrationStatus.PENDING
    received_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    upstream_status: int | None = None
    upstream_response: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    problematic_date: datetime | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InventorySnapshot(BaseModel):
    """Inventory snapshot imported from SmartUp balance endpoints."""

    id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    warehouse_external_id: str
    product_external_id: str
    quantity: Decimal
    snapshot_date: datetime
    source_system: str = "SmartUp"
    imported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class SmartUpRawRecord(BaseModel):
    """Raw SmartUp response record kept close to the original payload."""

    id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    filial_id: str
    request_filial_id: str | None = None
    request_company_id: str | None = None
    request_project_code: str | None = None
    entity_type: str
    external_id: str | None = None
    source_endpoint: str
    request_payload: dict[str, Any] | list[Any] | None = None
    response_payload: dict[str, Any] | list[Any]
    response_envelope: dict[str, Any] | list[Any] | None = None
    response_filial_id: str | None = None
    source_created_at: datetime | None = None
    source_updated_at: datetime | None = None
    imported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    batch_id: UUID | None = None
    checksum: str | None = None
    processing_status: SmartUpRawRecordStatus = SmartUpRawRecordStatus.PENDING
    processing_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def dedupe_key(self) -> tuple[UUID, str, str | None, str | None]:
        """Return the deduplication key for this raw record."""

        return self.organization_id, self.entity_type, self.external_id, self.checksum


class NormalizationIssue(BaseModel):
    """Normalization diagnostics captured for a raw SmartUp record."""

    id: UUID = Field(default_factory=uuid4)
    raw_record_id: UUID
    organization_id: UUID
    entity_type: str
    issue_type: str
    field_name: str | None = None
    message: str
    source_value: dict[str, Any] | list[Any] | str | int | float | None = None
    severity: NormalizationIssueSeverity = NormalizationIssueSeverity.WARNING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
