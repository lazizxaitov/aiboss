"""Full system data integrity audit helpers for SmartUp-imported data."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.data_explorer import DataExplorerService
from app.integrations.smartup.discovery import SmartUpDiscoveryReport, SmartUpDiscoveryService
from app.integrations.smartup.models import SMARTUP_INTEGRATION_UUID
from app.integrations.smartup.verification import (
    SmartUpVerificationReport,
    SmartUpVerificationService,
)


class SmartUpDataIntegrityAuditRow(BaseModel):
    """One dataset row in the full system audit matrix."""

    dataset: str
    smartup_endpoint: str | None = None
    raw_records: int = 0
    normalized_records: int = 0
    core_records: int = 0
    linked_records: int = 0
    unlinked_records: int = 0
    api_exposed: bool = True
    ui_exposed: str = "unknown"
    analytics_used: str = "unknown"
    organization_coverage: str = "unknown"
    date_coverage: str = "unknown"
    data_quality_status: str = "unknown"
    note: str | None = None


class SmartUpDataIntegrityAuditReport(BaseModel):
    """Combined audit report spanning discovery, coverage and explorer layers."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_system: str = "SmartUp"
    organization_id: UUID | None = None
    organization_name: str | None = None
    dataset_inventory: list[SmartUpDataIntegrityAuditRow] = Field(default_factory=list)
    discovery: SmartUpDiscoveryReport
    coverage: SmartUpVerificationReport
    explorer: dict[str, Any] = Field(default_factory=dict)
    raw_attribution: SmartUpRawAttributionReport | None = None
    notes: list[str] = Field(default_factory=list)


class SmartUpRawAttributionIssue(BaseModel):
    """One raw record with detected organization attribution drift."""

    raw_record_id: UUID
    organization_id: UUID
    organization_name: str
    expected_filial_id: str
    request_filial_id: str | None = None
    batch_request_filial_id: str | None = None
    response_filial_id: str | None = None
    response_filial_ids: list[str] = Field(default_factory=list)
    entity_type: str
    source_endpoint: str | None = None
    external_id: str | None = None
    status: Literal[
        "CONSISTENT",
        "LEGACY_MISSING_REQUEST_CONTEXT",
        "ORGANIZATION_MISMATCH",
        "RESPONSE_FILIAL_DIFFERS",
        "AMBIGUOUS",
    ] = "CONSISTENT"
    reason: str


class SmartUpRawAttributionItem(BaseModel):
    """Per-organization raw organization attribution summary."""

    organization_id: UUID
    organization_name: str
    expected_filial_id: str
    raw_count: int = 0
    matching_rows: int = 0
    organization_mismatch: int = 0
    different_response_filial: int = 0
    missing_filial: int = 0
    ambiguous: int = 0
    foreign_filials: dict[str, int] = Field(default_factory=dict)


class SmartUpRawAttributionReport(BaseModel):
    """Raw attribution diagnostics for SmartUp imported data."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_system: str = "SmartUp"
    total_organizations: int = 0
    raw_records: int = 0
    matching_rows: int = 0
    organization_mismatch: int = 0
    different_response_filial: int = 0
    missing_filial: int = 0
    ambiguous: int = 0
    items: list[SmartUpRawAttributionItem] = Field(default_factory=list)
    issues: list[SmartUpRawAttributionIssue] = Field(default_factory=list)


@dataclass(slots=True)
class SmartUpDataIntegrityAuditService:
    """Build a consolidated system-wide integrity audit for SmartUp data."""

    store: CoreDataStore

    def build_report(self, organization_id: UUID | None = None) -> SmartUpDataIntegrityAuditReport:
        explorer_service = DataExplorerService(self.store)
        discovery = SmartUpDiscoveryService(self.store).build_report(
            organization_id=organization_id,
        )
        coverage = SmartUpVerificationService(self.store).build_coverage_report(
            organization_id=organization_id,
        )
        explorer_stats = explorer_service.build_stats(organization_id=organization_id)
        raw_attribution = self.build_raw_attribution_report(organization_id=organization_id)
        coverage_by_entity = {entity.entity: entity for entity in coverage.entities}
        specs = explorer_service._collection_specs()  # noqa: SLF001 - audit aggregation helper

        dataset_inventory = [
            self._build_row(
                dataset_key=section.key,
                section=section,
                spec=specs[section.key],
                coverage_row=coverage_by_entity.get(_section_key_to_entity(section.key)),
                organization_id=organization_id,
            )
            for section in explorer_stats.sections
        ]
        audit_notes = [
            "Report combines SmartUp Discovery, coverage verification and Data Explorer stats.",
            (
                "ui_exposed/date_coverage remain heuristic until frontend route and "
                "date-range telemetry are audited."
            ),
        ]
        return SmartUpDataIntegrityAuditReport(
            organization_id=organization_id,
            organization_name=coverage.organization_name,
            dataset_inventory=dataset_inventory,
            discovery=discovery,
            coverage=coverage,
            explorer=explorer_stats.model_dump(mode="json"),
            raw_attribution=raw_attribution,
            notes=audit_notes,
        )

    def build_raw_attribution_report(
        self,
        organization_id: UUID | None = None,
    ) -> SmartUpRawAttributionReport:
        organizations = list(
            self.store.list_smartup_organizations(
                integration_id=SMARTUP_INTEGRATION_UUID,
                is_active=None,
            ),
        )
        if organization_id is not None:
            organizations = [org for org in organizations if org.id == organization_id]

        items: list[SmartUpRawAttributionItem] = []
        issues: list[SmartUpRawAttributionIssue] = []
        totals = defaultdict(int)
        for organization in organizations:
            item, item_issues = self._build_raw_attribution_item(organization)
            items.append(item)
            issues.extend(item_issues)
            totals["raw_records"] += item.raw_count
            totals["matching_rows"] += item.matching_rows
            totals["organization_mismatch"] += item.organization_mismatch
            totals["different_response_filial"] += item.different_response_filial
            totals["missing_filial"] += item.missing_filial
            totals["ambiguous"] += item.ambiguous

        return SmartUpRawAttributionReport(
            total_organizations=len(organizations),
            raw_records=totals["raw_records"],
            matching_rows=totals["matching_rows"],
            organization_mismatch=totals["organization_mismatch"],
            different_response_filial=totals["different_response_filial"],
            missing_filial=totals["missing_filial"],
            ambiguous=totals["ambiguous"],
            items=items,
            issues=issues,
        )

    def _build_raw_attribution_item(
        self,
        organization: Any,
    ) -> tuple[SmartUpRawAttributionItem, list[SmartUpRawAttributionIssue]]:
        expected_filial_id = self._clean_text(getattr(organization, "filial_id", None)) or ""
        raw_records = list(
            self.store.list_smartup_raw_records(organization_id=organization.id),
        )
        batches = {
            batch.id: batch
            for batch in self.store.list_migration_batches(organization_id=organization.id)
        }
        item = SmartUpRawAttributionItem(
            organization_id=organization.id,
            organization_name=getattr(organization, "name", str(organization.id)),
            expected_filial_id=expected_filial_id,
        )
        issues: list[SmartUpRawAttributionIssue] = []
        foreign_filials = defaultdict(int)

        for raw_record in raw_records:
            batch = batches.get(raw_record.batch_id) if raw_record.batch_id else None
            batch_request_filial_id = self._batch_metadata_text(
                batch.metadata if batch is not None else None,
                "request_filial_id",
            ) or self._batch_metadata_text(
                batch.metadata if batch is not None else None,
                "filial_id",
            )
            request_filial_id = (
                self._clean_text(getattr(raw_record, "request_filial_id", None))
                or self._clean_text(batch_request_filial_id)
                or self._clean_text(getattr(raw_record, "filial_id", None))
            )
            response_filial_ids = self._collect_filial_ids(
                getattr(raw_record, "response_envelope", None)
                or getattr(raw_record, "response_payload", None),
            )
            response_filial_id = (
                self._clean_text(getattr(raw_record, "response_filial_id", None))
                or (response_filial_ids[0] if response_filial_ids else None)
            )
            explicit_request_context = any(
                (
                    getattr(raw_record, "request_filial_id", None) is not None,
                    getattr(raw_record, "request_company_id", None) is not None,
                    getattr(raw_record, "request_project_code", None) is not None,
                    batch_request_filial_id is not None,
                ),
            )
            status: Literal[
                "CONSISTENT",
                "LEGACY_MISSING_REQUEST_CONTEXT",
                "ORGANIZATION_MISMATCH",
                "RESPONSE_FILIAL_DIFFERS",
                "AMBIGUOUS",
            ]
            reason: str
            if len(set(response_filial_ids)) > 1:
                status = "AMBIGUOUS"
                reason = "Multiple response filial_id values found in one raw response."
                item.ambiguous += 1
            elif request_filial_id and request_filial_id != expected_filial_id:
                status = "ORGANIZATION_MISMATCH"
                reason = "Request filial_id does not match organization filial_id."
                item.organization_mismatch += 1
            elif response_filial_ids and any(
                filial_id and filial_id != expected_filial_id for filial_id in response_filial_ids
            ):
                status = "RESPONSE_FILIAL_DIFFERS"
                reason = "Response filial_id differs from organization filial_id."
                item.different_response_filial += 1
            elif not explicit_request_context:
                status = "LEGACY_MISSING_REQUEST_CONTEXT"
                reason = "Raw record predates explicit request context fields."
                item.missing_filial += 1
            else:
                status = "CONSISTENT"
                reason = "Request and response context align with organization."
                item.matching_rows += 1

            item.raw_count += 1
            for filial_id in response_filial_ids:
                if filial_id and filial_id != expected_filial_id:
                    foreign_filials[filial_id] += 1

            if status != "CONSISTENT":
                issues.append(
                    SmartUpRawAttributionIssue(
                        raw_record_id=raw_record.id,
                        organization_id=organization.id,
                        organization_name=item.organization_name,
                        expected_filial_id=expected_filial_id,
                        request_filial_id=request_filial_id,
                        batch_request_filial_id=batch_request_filial_id,
                        response_filial_id=response_filial_id,
                        response_filial_ids=response_filial_ids,
                        entity_type=raw_record.entity_type,
                        source_endpoint=raw_record.source_endpoint,
                        external_id=raw_record.external_id,
                        status=status,
                        reason=reason,
                    ),
                )

        item.foreign_filials = dict(sorted(foreign_filials.items()))
        return item, issues

    @staticmethod
    def _clean_text(value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _batch_metadata_text(metadata: Any, key: str) -> str | None:
        if not isinstance(metadata, dict):
            return None
        value = metadata.get(key)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _collect_filial_ids(cls, value: object | None) -> list[str]:
        found: list[str] = []
        if isinstance(value, dict):
            direct = cls._clean_text(value.get("filial_id"))
            if direct and direct not in found:
                found.append(direct)
            for nested in value.values():
                for filial_id in cls._collect_filial_ids(nested):
                    if filial_id not in found:
                        found.append(filial_id)
        elif isinstance(value, list):
            for item in value:
                for filial_id in cls._collect_filial_ids(item):
                    if filial_id not in found:
                        found.append(filial_id)
        return found

    def _build_row(
        self,
        *,
        dataset_key: Any,
        section: Any,
        spec: Any,
        coverage_row: Any,
        organization_id: UUID | None,
    ) -> SmartUpDataIntegrityAuditRow:
        raw_records = int(getattr(section, "raw_count", 0) or 0)
        normalized_records = int(getattr(section, "normalized_count", 0) or 0)
        core_records = int(getattr(section, "count", 0) or 0)
        linked_records = int(getattr(coverage_row, "linked", 0) or 0) if coverage_row else 0
        unlinked_records = int(getattr(coverage_row, "unresolved", 0) or 0) if coverage_row else 0
        note = getattr(section, "note", None) or getattr(spec, "note", None)
        return SmartUpDataIntegrityAuditRow(
            dataset=str(dataset_key),
            smartup_endpoint=", ".join(getattr(spec, "raw_endpoint_suffixes", ()) or ()) or None,
            raw_records=raw_records,
            normalized_records=normalized_records,
            core_records=core_records,
            linked_records=linked_records,
            unlinked_records=unlinked_records,
            api_exposed=True,
            ui_exposed="unknown",
            analytics_used="unknown",
            organization_coverage=(
                "all organizations"
                if organization_id is None
                else f"organization:{organization_id}"
            ),
            date_coverage="unknown",
            data_quality_status=str(getattr(section, "state", "unknown")),
            note=note,
        )


def _section_key_to_entity(section_key: str) -> str:
    return section_key.replace("-", "_")
