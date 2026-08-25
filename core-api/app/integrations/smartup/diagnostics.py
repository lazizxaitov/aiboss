"""Diagnostics and raw-record access for SmartUp imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.data_layer.contracts import CoreDataStore
from app.integrations.smartup.models import (
    SMARTUP_INTEGRATION_UUID,
    MigrationBatch,
    SmartUpMigrationMode,
    SmartUpRawRecord,
)
from app.integrations.smartup.pipeline import SmartUpImportPipeline, SmartUpNormalizationSummary


class SmartUpRawRecordSummary(BaseModel):
    """Compact raw-record listing item."""

    id: UUID
    organization_id: UUID
    filial_id: str
    entity_type: str
    external_id: str | None = None
    source_endpoint: str
    processing_status: str
    imported_at: datetime
    batch_id: UUID | None = None
    checksum: str | None = None
    processing_error: str | None = None


class SmartUpReprocessResponse(BaseModel):
    """Response returned after reprocessing one raw record."""

    record_id: UUID
    action: str
    skipped: bool = False
    issue_count: int = 0


class SmartUpNormalizationSummaryResponse(BaseModel):
    """Response returned for batch normalization summaries."""

    batch_id: UUID
    raw_saved: int = 0
    normalized: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0
    issues: int = 0


class SmartUpCompletenessGap(BaseModel):
    """A missing or uncovered time interval in the import coverage."""

    period_start: datetime
    period_end: datetime


class SmartUpCompletenessItem(BaseModel):
    """Per-organization and per-entity completeness report."""

    organization_id: UUID
    organization_name: str
    entity_type: str
    migration_mode: str | None = None
    batch_count: int = 0
    completed_batches: int = 0
    failed_batches: int = 0
    raw_records: int = 0
    core_records: int = 0
    first_period_start: datetime | None = None
    last_period_end: datetime | None = None
    missing_intervals: list[SmartUpCompletenessGap] = Field(default_factory=list)
    status: Literal["empty", "complete", "partial", "failed"] = "empty"


class SmartUpCompletenessReport(BaseModel):
    """Aggregated coverage report for SmartUp migrations."""

    total_organizations: int = 0
    total_entities: int = 0
    completed_entities: int = 0
    partial_entities: int = 0
    failed_entities: int = 0
    raw_records: int = 0
    core_records: int = 0
    items: list[SmartUpCompletenessItem] = Field(default_factory=list)


@dataclass(slots=True)
class SmartUpRawDataService:
    """Read and reprocess SmartUp raw records."""

    store: CoreDataStore
    pipeline: SmartUpImportPipeline = field(init=False)

    def __post_init__(self) -> None:
        self.pipeline = SmartUpImportPipeline(self.store)

    def list_raw_records(
        self,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
        batch_id: UUID | None = None,
        processing_status: str | None = None,
    ) -> list[SmartUpRawRecordSummary]:
        records = self.store.list_smartup_raw_records(
            organization_id=organization_id,
            entity_type=entity_type,
            batch_id=batch_id,
            processing_status=processing_status,
        )
        return [
            SmartUpRawRecordSummary(
                id=record.id,
                organization_id=record.organization_id,
                filial_id=record.filial_id,
                entity_type=record.entity_type,
                external_id=record.external_id,
                source_endpoint=record.source_endpoint,
                processing_status=str(record.processing_status),
                imported_at=record.imported_at,
                batch_id=record.batch_id,
                checksum=record.checksum,
                processing_error=record.processing_error,
            )
            for record in records
        ]

    def get_raw_record(self, record_id: UUID) -> SmartUpRawRecord | None:
        return self.store.get_smartup_raw_record(record_id)

    def reprocess_raw_record(self, record_id: UUID) -> SmartUpReprocessResponse:
        result = self.pipeline.reprocess_raw_record(record_id)
        return SmartUpReprocessResponse(
            record_id=record_id,
            action=result.action,
            skipped=result.skipped,
            issue_count=result.issue_count,
        )

    def normalize_batch(self, batch_id: UUID) -> SmartUpNormalizationSummaryResponse:
        summary = self.pipeline.normalize_batch(batch_id)
        return self._summary_response(batch_id=batch_id, summary=summary)

    def normalization_summary(self, batch_id: UUID) -> SmartUpNormalizationSummaryResponse:
        summary = self.pipeline.normalization_summary(batch_id)
        return self._summary_response(batch_id=batch_id, summary=summary)

    def migration_completeness(
        self,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
        migration_mode: SmartUpMigrationMode | None = None,
    ) -> SmartUpCompletenessReport:
        organizations = list(
            self.store.list_smartup_organizations(
                integration_id=SMARTUP_INTEGRATION_UUID,
                is_active=None,
            ),
        )
        if organization_id is not None:
            organizations = [org for org in organizations if org.id == organization_id]

        items: list[SmartUpCompletenessItem] = []
        total_core_records = 0
        for organization in organizations:
            organization_core_records = len(
                list(self.store.list_records(business_id=organization.id)),
            )
            total_core_records += organization_core_records
            batches = list(
                self.store.list_migration_batches(
                    organization_id=organization.id,
                    entity_type=entity_type,
                    migration_mode=migration_mode.value if migration_mode else None,
                ),
            )
            if entity_type is None:
                entity_types = sorted({batch.entity_type for batch in batches})
                if not entity_types:
                    entity_types = ["*"]
            else:
                entity_types = [entity_type]

            for current_entity in entity_types:
                entity_batches = [
                    batch for batch in batches if batch.entity_type == current_entity
                ]
                missing_intervals = self._missing_intervals(entity_batches)
                failed_batches = sum(1 for batch in entity_batches if str(batch.status) == "failed")
                completed_batches = sum(
                    1 for batch in entity_batches if str(batch.status) == "completed"
                )
                raw_records = len(
                    list(
                        self.store.list_smartup_raw_records(
                            organization_id=organization.id,
                            entity_type=None if current_entity == "*" else current_entity,
                        ),
                    ),
                )
                core_records = organization_core_records
                first_period_start = (
                    min((batch.date_from for batch in entity_batches), default=None)
                    if entity_batches
                    else None
                )
                last_period_end = (
                    max((batch.date_to for batch in entity_batches), default=None)
                    if entity_batches
                    else None
                )
                if not entity_batches:
                    status: Literal["empty", "complete", "partial", "failed"] = "empty"
                elif failed_batches:
                    status = "failed"
                elif missing_intervals:
                    status = "partial"
                else:
                    status = "complete"
                items.append(
                    SmartUpCompletenessItem(
                        organization_id=organization.id,
                        organization_name=organization.name,
                        entity_type=current_entity,
                        migration_mode=migration_mode.value if migration_mode else None,
                        batch_count=len(entity_batches),
                        completed_batches=completed_batches,
                        failed_batches=failed_batches,
                        raw_records=raw_records,
                        core_records=core_records,
                        first_period_start=first_period_start,
                        last_period_end=last_period_end,
                        missing_intervals=missing_intervals,
                        status=status,
                    ),
                )

        return SmartUpCompletenessReport(
            total_organizations=len(organizations),
            total_entities=len(items),
            completed_entities=sum(1 for item in items if item.status == "complete"),
            partial_entities=sum(1 for item in items if item.status == "partial"),
            failed_entities=sum(1 for item in items if item.status == "failed"),
            raw_records=sum(item.raw_records for item in items),
            core_records=total_core_records,
            items=items,
        )

    @staticmethod
    def _summary_response(
        *,
        batch_id: UUID,
        summary: SmartUpNormalizationSummary,
    ) -> SmartUpNormalizationSummaryResponse:
        return SmartUpNormalizationSummaryResponse(
            batch_id=batch_id,
            raw_saved=summary.raw_saved,
            normalized=summary.normalized,
            inserted=summary.inserted,
            updated=summary.updated,
            unchanged=summary.unchanged,
            skipped=summary.skipped,
            failed=summary.failed,
            issues=summary.issues,
        )

    @staticmethod
    def _missing_intervals(batches: list[MigrationBatch]) -> list[SmartUpCompletenessGap]:
        if not batches:
            return []
        gaps: list[SmartUpCompletenessGap] = []
        ordered = sorted(batches, key=lambda batch: (batch.date_from, batch.date_to, str(batch.id)))
        previous_end = ordered[0].date_to
        for batch in ordered[1:]:
            if batch.date_from > previous_end:
                gaps.append(
                    SmartUpCompletenessGap(period_start=previous_end, period_end=batch.date_from),
                )
            if batch.date_to > previous_end:
                previous_end = batch.date_to
        return gaps
