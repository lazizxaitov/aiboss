"""SmartUp raw-to-core normalization pipeline."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.core_upsert import CoreUpsertService, UpsertOutcome
from app.integrations.smartup.models import (
    NormalizationIssue,
    NormalizationIssueSeverity,
    SmartUpRawRecord,
    SmartUpRawRecordStatus,
)
from app.integrations.smartup.normalizers import NORMALIZER_REGISTRY
from app.integrations.smartup.normalizers.base import NormalizationResult, SmartUpNormalizer
from app.integrations.smartup.resolver import ExternalReferenceResolver

_RESPONSE_KEYS: dict[str, tuple[str, ...]] = {
    "customers": ("legal_person", "natural_person"),
    "sales": ("order",),
    "products": ("inventory", "product"),
    "product_categories": ("product_group",),
    "warehouses": ("room",),
    "payments": ("payment", "cashin"),
    "inventory_balances": ("inventory_balance", "balance"),
    "visits": ("visit",),
    "bank_operations": ("bank_operation",),
}

_NORMALIZER_ALIASES: dict[str, str] = {
    "price_points": "product_prices",
}

_SENSITIVE_KEYS = {
    "password",
    "authorization",
    "cookies",
    "cookie",
    "jsessionid",
    "access_token",
    "refresh_token",
    "session_token",
    "token",
}


@dataclass(slots=True)
class SmartUpNormalizationSummary:
    """Counters produced by a normalization run."""

    raw_saved: int = 0
    normalized: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0
    issues: int = 0


class SmartUpImportPipeline:
    """Persist raw SmartUp data and normalize it into the core layer."""

    def __init__(
        self,
        store: CoreDataStore,
        *,
        upsert_service: CoreUpsertService | None = None,
        resolver: ExternalReferenceResolver | None = None,
        normalizers: dict[str, SmartUpNormalizer] | None = None,
    ) -> None:
        self.store = store
        self.upsert_service = upsert_service or CoreUpsertService(store)
        self.resolver = resolver or ExternalReferenceResolver(store)
        self.normalizers = normalizers or NORMALIZER_REGISTRY

    def ingest_response(
        self,
        *,
        organization_id: UUID,
        filial_id: str,
        request_company_id: str | None = None,
        request_project_code: str | None = None,
        entity_type: str,
        source_endpoint: str,
        response_payload: dict[str, Any] | list[Any],
        request_payload: dict[str, Any] | list[Any] | None = None,
        batch_id: UUID | None = None,
    ) -> SmartUpNormalizationSummary:
        """Persist raw payload rows and normalize them."""

        summary = SmartUpNormalizationSummary()
        rows = self._extract_rows(entity_type, response_payload)
        for row in rows:
            if not isinstance(row, dict):
                continue
            raw_record = self._build_raw_record(
                organization_id=organization_id,
                filial_id=filial_id,
                request_company_id=request_company_id,
                request_project_code=request_project_code,
                entity_type=entity_type,
                source_endpoint=source_endpoint,
                response_row=row,
                response_envelope=response_payload,
                request_payload=request_payload,
                batch_id=batch_id,
            )
            summary.raw_saved += 1
            normalized = self.process_raw_record(raw_record)
            summary.normalized += int(not normalized.skipped)
            summary.inserted += int(normalized.action == "inserted")
            summary.updated += int(normalized.action == "updated")
            summary.unchanged += int(normalized.action == "unchanged")
            summary.skipped += int(normalized.action == "skipped")
            summary.failed += int(normalized.action == "failed")
            summary.issues += normalized.issue_count
        return summary

    def process_raw_record(self, raw_record: SmartUpRawRecord) -> PipelineResult:
        """Normalize one raw SmartUp record."""

        return self.process_raw_record_with_options(raw_record)

    def process_raw_record_with_options(
        self,
        raw_record: SmartUpRawRecord,
        *,
        force: bool = False,
        normalizer: SmartUpNormalizer | None = None,
    ) -> PipelineResult:
        """Normalize one raw record with optional override controls."""

        existing = self.store.get_smartup_raw_record(raw_record.id)
        if (
            not force
            and existing is not None
            and existing.checksum == raw_record.checksum
            and existing.processing_status == SmartUpRawRecordStatus.NORMALIZED
        ):
            return PipelineResult(action="skipped", skipped=True, issue_count=0)

        normalizer = normalizer or self.normalizers.get(raw_record.entity_type)
        if normalizer is None:
            alias = _NORMALIZER_ALIASES.get(raw_record.entity_type)
            if alias is not None:
                normalizer = self.normalizers.get(alias)
        if normalizer is None:
            raw_record = raw_record.model_copy(
                update={
                    "processing_status": SmartUpRawRecordStatus.SKIPPED,
                    "processing_error": "normalizer_not_registered",
                    "updated_at": datetime.now(UTC),
                },
            )
            self.store.upsert_smartup_raw_record(raw_record)
            self._record_issue(
                raw_record=raw_record,
                issue_type="normalizer_not_registered",
                message=f"No normalizer registered for {raw_record.entity_type}",
                severity=NormalizationIssueSeverity.WARNING,
            )
            return PipelineResult(action="skipped", skipped=True, issue_count=1)

        try:
            result = normalizer.normalize(raw_record)
            if result.skipped:
                self._mark_skipped(raw_record, result.skip_reason or "skipped")
                self._maybe_issue_from_skip(raw_record, result)
                warning_count = len(result.warnings)
                return PipelineResult(
                    action="skipped",
                    skipped=True,
                    issue_count=warning_count,
                )

            upsert_outcomes = self._upsert_normalized_result(raw_record, result)
            unresolved_issues = self._check_related_references(raw_record, result)
            self._mark_normalized(raw_record)
            for issue in unresolved_issues:
                self.store.upsert_normalization_issue(issue)
            return PipelineResult(
                action=_summarize_action(upsert_outcomes),
                skipped=False,
                issue_count=len(unresolved_issues) + len(result.warnings),
            )
        except Exception as exc:  # pragma: no cover - defensive safety
            self._mark_failed(raw_record, str(exc))
            self._record_issue(
                raw_record=raw_record,
                issue_type="normalization_failed",
                message=str(exc),
                severity=NormalizationIssueSeverity.ERROR,
            )
            return PipelineResult(action="failed", skipped=False, issue_count=1)

    def reprocess_raw_record(self, record_id: UUID) -> PipelineResult:
        """Re-run normalization for a stored raw record."""

        raw_record = self.store.get_smartup_raw_record(record_id)
        if raw_record is None:
            raise ValueError("Raw SmartUp record not found")
        return self.process_raw_record_with_options(raw_record, force=True)

    def normalize_batch(self, batch_id: UUID) -> SmartUpNormalizationSummary:
        """Normalize every raw record in a batch."""

        summary = SmartUpNormalizationSummary()
        for raw_record in self.store.list_smartup_raw_records(batch_id=batch_id):
            result = self.process_raw_record(raw_record)
            summary.normalized += int(not result.skipped)
            summary.skipped += int(result.skipped or result.action == "skipped")
            summary.failed += int(result.action == "failed")
            summary.issues += result.issue_count
        return summary

    def normalization_summary(self, batch_id: UUID) -> SmartUpNormalizationSummary:
        """Summarize existing normalization statuses for a batch."""

        raw_records = list(self.store.list_smartup_raw_records(batch_id=batch_id))
        raw_record_ids = [record.id for record in raw_records]
        normalized_count = sum(
            1
            for record in raw_records
            if record.processing_status == SmartUpRawRecordStatus.NORMALIZED
        )
        skipped_count = sum(
            1
            for record in raw_records
            if record.processing_status == SmartUpRawRecordStatus.SKIPPED
        )
        failed_count = sum(
            1 for record in raw_records if record.processing_status == SmartUpRawRecordStatus.FAILED
        )
        return SmartUpNormalizationSummary(
            raw_saved=len(raw_records),
            normalized=normalized_count,
            skipped=skipped_count,
            failed=failed_count,
            issues=sum(
                len(list(self.store.list_normalization_issues(raw_record_id=raw_record_id)))
                for raw_record_id in raw_record_ids
            ),
        )

    def _upsert_normalized_result(
        self,
        raw_record: SmartUpRawRecord,
        result: NormalizationResult,
    ) -> list[UpsertOutcome]:
        payload = dict(result.normalized_data)
        payload.setdefault("organization_id", raw_record.organization_id)
        payload.setdefault("source_filial_id", raw_record.filial_id)
        payload.setdefault("source_system", "smartup")
        source_external_id = result.source_external_id or raw_record.external_id
        payload.setdefault("source_external_id", source_external_id)
        payload.setdefault("source_payload_id", source_external_id)
        payload = self._resolve_linked_fields(raw_record, result.entity_type, payload)
        main_outcome = self.upsert_service.upsert_entity(result.entity_type, payload)
        related_payloads: list[tuple[str, dict[str, Any]]] = []
        for item in result.related_entities:
            injected = self._inject_common_fields(raw_record, item.data)
            if item.entity_type == "sale_items":
                injected["sale_id"] = main_outcome.entity_id
            if item.entity_type == "business_document_items":
                injected["document_id"] = main_outcome.entity_id
            injected = self._resolve_linked_fields(raw_record, item.entity_type, injected)
            related_payloads.append((item.entity_type, injected))
        outcomes = [main_outcome]
        if related_payloads:
            outcomes.extend(self.upsert_service.upsert_related_entities(related_payloads))
        return outcomes

    def _resolve_linked_fields(
        self,
        raw_record: SmartUpRawRecord,
        entity_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        resolved = dict(payload)
        if entity_type == "sales":
            customer_external_id = resolved.get("customer_external_id")
            if customer_external_id:
                customer = self.resolver.resolve(
                    "customers",
                    raw_record.organization_id,
                    str(customer_external_id),
                )
                if customer is not None:
                    resolved["customer_id"] = customer.id
        elif entity_type == "visits":
            customer_external_id = resolved.get("customer_external_id")
            if customer_external_id:
                customer = self.resolver.resolve(
                    "customers",
                    raw_record.organization_id,
                    str(customer_external_id),
                )
                if customer is not None:
                    resolved["customer_id"] = customer.id
        elif entity_type == "payments":
            sale_external_id = resolved.get("sale_external_id")
            if sale_external_id:
                sale = self.resolver.resolve(
                    "sales",
                    raw_record.organization_id,
                    str(sale_external_id),
                )
                if sale is not None:
                    resolved["sale_id"] = sale.id
        elif entity_type == "product_prices":
            product_external_id = resolved.get("product_external_id")
            if product_external_id:
                product = self.resolver.resolve(
                    "products",
                    raw_record.organization_id,
                    str(product_external_id),
                )
                if product is not None:
                    resolved["product_id"] = product.id
            price_type_code = resolved.get("price_type_code") or resolved.get("source_external_id")
            if price_type_code:
                price_type = self.resolver.resolve(
                    "price_types",
                    raw_record.organization_id,
                    str(price_type_code),
                )
                if price_type is not None:
                    resolved["price_type_id"] = price_type.id
        elif entity_type == "sale_items":
            product_external_id = resolved.get("product_external_id")
            if product_external_id:
                product = self.resolver.resolve(
                    "products",
                    raw_record.organization_id,
                    str(product_external_id),
                )
                if product is not None:
                    resolved["product_id"] = product.id
        elif entity_type == "inventory_balances":
            product_external_id = resolved.get("product_external_id")
            if product_external_id:
                product = self.resolver.resolve(
                    "products",
                    raw_record.organization_id,
                    str(product_external_id),
                )
                if product is not None:
                    resolved["product_id"] = product.id
            warehouse_external_id = resolved.get("warehouse_external_id")
            if warehouse_external_id:
                warehouse = self.resolver.resolve(
                    "warehouses",
                    raw_record.organization_id,
                    str(warehouse_external_id),
                )
                if warehouse is not None:
                    resolved["warehouse_id"] = warehouse.id
        return resolved

    def _check_related_references(
        self,
        raw_record: SmartUpRawRecord,
        result: NormalizationResult,
    ) -> list[NormalizationIssue]:
        issues: list[NormalizationIssue] = []
        if result.entity_type == "sales":
            customer_external_id = result.normalized_data.get("customer_external_id")
            if customer_external_id:
                resolved = self.resolver.resolve(
                    "customers",
                    raw_record.organization_id,
                    str(customer_external_id),
                )
                if resolved is None:
                    issues.append(
                        self._build_issue(
                            raw_record=raw_record,
                            issue_type="unresolved_reference",
                            field_name="customer_external_id",
                            message="Referenced customer is not normalized yet.",
                            source_value=customer_external_id,
                            severity=NormalizationIssueSeverity.WARNING,
                        ),
                    )
        return issues

    def _mark_normalized(self, raw_record: SmartUpRawRecord) -> None:
        self.store.upsert_smartup_raw_record(
            raw_record.model_copy(
                update={
                    "processing_status": SmartUpRawRecordStatus.NORMALIZED,
                    "processing_error": None,
                    "updated_at": datetime.now(UTC),
                },
            ),
        )

    def _mark_skipped(self, raw_record: SmartUpRawRecord, reason: str) -> None:
        self.store.upsert_smartup_raw_record(
            raw_record.model_copy(
                update={
                    "processing_status": SmartUpRawRecordStatus.SKIPPED,
                    "processing_error": reason,
                    "updated_at": datetime.now(UTC),
                },
            ),
        )

    def _mark_failed(self, raw_record: SmartUpRawRecord, reason: str) -> None:
        self.store.upsert_smartup_raw_record(
            raw_record.model_copy(
                update={
                    "processing_status": SmartUpRawRecordStatus.FAILED,
                    "processing_error": reason,
                    "updated_at": datetime.now(UTC),
                },
            ),
        )

    def _maybe_issue_from_skip(
        self,
        raw_record: SmartUpRawRecord,
        result: NormalizationResult,
    ) -> None:
        issue_type = result.skip_reason or "skipped"
        self._record_issue(
            raw_record=raw_record,
            issue_type=issue_type,
            message=result.skip_reason or "Skipped during normalization.",
            severity=NormalizationIssueSeverity.WARNING,
        )
        for warning in result.warnings:
            self._record_issue(
                raw_record=raw_record,
                issue_type="warning",
                message=warning,
                severity=NormalizationIssueSeverity.INFO,
            )

    def _record_issue(
        self,
        *,
        raw_record: SmartUpRawRecord,
        issue_type: str,
        message: str,
        severity: NormalizationIssueSeverity,
        field_name: str | None = None,
        source_value: object | None = None,
    ) -> None:
        self.store.upsert_normalization_issue(
            self._build_issue(
                raw_record=raw_record,
                issue_type=issue_type,
                field_name=field_name,
                message=message,
                source_value=source_value,
                severity=severity,
            ),
        )

    def _build_issue(
        self,
        *,
        raw_record: SmartUpRawRecord,
        issue_type: str,
        message: str,
        severity: NormalizationIssueSeverity,
        field_name: str | None = None,
        source_value: object | None = None,
    ) -> NormalizationIssue:
        return NormalizationIssue(
            raw_record_id=raw_record.id,
            organization_id=raw_record.organization_id,
            entity_type=raw_record.entity_type,
            issue_type=issue_type,
            field_name=field_name,
            message=message,
            source_value=source_value,
            severity=severity,
        )

    def _build_raw_record(
        self,
        *,
        organization_id: UUID,
        filial_id: str,
        request_company_id: str | None,
        request_project_code: str | None,
        entity_type: str,
        source_endpoint: str,
        response_row: dict[str, Any],
        response_envelope: dict[str, Any] | list[Any],
        request_payload: dict[str, Any] | list[Any] | None,
        batch_id: UUID | None,
    ) -> SmartUpRawRecord:
        sanitized_request = self._sanitize_payload(request_payload)
        sanitized_response = self._sanitize_payload(response_row)
        sanitized_envelope = self._sanitize_payload(response_envelope)
        checksum = self._checksum(sanitized_response)
        source_external_id = self._extract_external_id(entity_type, response_row)
        dedupe_external_id = source_external_id or checksum
        record_id = uuid5(
            NAMESPACE_URL,
            f"smartup:raw:{organization_id}:{entity_type}:{dedupe_external_id}:{checksum}",
        )
        return SmartUpRawRecord(
            id=record_id,
            organization_id=organization_id,
            filial_id=filial_id,
            request_filial_id=filial_id,
            request_company_id=request_company_id,
            request_project_code=request_project_code,
            entity_type=entity_type,
            external_id=source_external_id,
            source_endpoint=source_endpoint,
            request_payload=sanitized_request,
            response_payload=sanitized_response,
            response_envelope=sanitized_envelope,
            response_filial_id=(
                self._extract_filial_id(response_row)
                or self._extract_filial_id(response_envelope)
            ),
            source_created_at=None,
            source_updated_at=None,
            batch_id=batch_id,
            checksum=checksum,
            processing_status=SmartUpRawRecordStatus.PENDING,
        )

    def _extract_rows(
        self,
        entity_type: str,
        response_payload: dict[str, Any] | list[Any],
    ) -> list[dict[str, Any]]:
        if isinstance(response_payload, list):
            return [row for row in response_payload if isinstance(row, dict)]
        if not isinstance(response_payload, dict):
            return []
        keys = _RESPONSE_KEYS.get(entity_type)
        if not keys:
            return [response_payload]
        rows: list[dict[str, Any]] = []
        for key in keys:
            value = response_payload.get(key)
            if isinstance(value, list):
                rows.extend(row for row in value if isinstance(row, dict))
        return rows or [response_payload]

    @staticmethod
    def _inject_common_fields(
        raw_record: SmartUpRawRecord,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(data)
        payload.setdefault("organization_id", raw_record.organization_id)
        payload.setdefault("source_system", "smartup")
        payload.setdefault("source_filial_id", raw_record.filial_id)
        payload.setdefault("request_filial_id", raw_record.request_filial_id)
        source_external_id = payload.get("source_external_id") or raw_record.external_id
        payload.setdefault("source_external_id", source_external_id)
        payload.setdefault("source_payload_id", source_external_id)
        return payload

    @staticmethod
    def _checksum(value: object) -> str:
        canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _sanitize_payload(value: object | None) -> object | None:
        if value is None:
            return None
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                if str(key).casefold() in _SENSITIVE_KEYS:
                    continue
                sanitized[key] = SmartUpImportPipeline._sanitize_payload(item)
            return sanitized
        if isinstance(value, list):
            return [SmartUpImportPipeline._sanitize_payload(item) for item in value]
        return value

    @staticmethod
    def _extract_filial_id(value: object | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, dict):
            direct = value.get("filial_id")
            if direct is not None:
                text = str(direct).strip()
                if text:
                    return text
            for item in value.values():
                found = SmartUpImportPipeline._extract_filial_id(item)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = SmartUpImportPipeline._extract_filial_id(item)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _extract_external_id(entity_type: str, row: dict[str, Any]) -> str | None:
        candidates = {
            "customers": ("person_id", "code", "external_id"),
            "sales": ("deal_id", "external_id"),
            "product_categories": ("product_group_id", "code"),
            "products": ("product_id", "code"),
            "warehouses": ("room_id", "room_code", "code"),
            "payments": ("payment_id", "external_id"),
            "inventory_balances": ("inventory_code", "product_code", "code"),
            "visits": ("visit_id", "external_id"),
            "bank_operations": ("operation_id", "external_id"),
            "sale_items": ("external_id", "deal_id", "product_code"),
            "returns": ("return_id", "deal_id", "external_id"),
            "purchases": ("purchase_id", "external_id"),
            "warehouse_receipts": ("receipt_id", "input_id", "external_id"),
            "return_to_suppliers": ("return_id", "external_id"),
            "stocktakings": ("stocktaking_id", "external_id"),
            "write_offs": ("writeoff_id", "external_id"),
            "cross_organizational_movements": ("movement_id", "external_id"),
            "internal_movements": ("movement_id", "external_id"),
            "logistics": ("logistics_id", "external_id"),
            "equipment_movements": ("movement_id", "external_id"),
            "equipment_requests": ("request_id", "external_id"),
        }.get(entity_type, ("external_id", "id", "code"))
        for key in candidates:
            value = row.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None


@dataclass(slots=True)
class PipelineResult:
    """Result for one raw record normalization run."""

    action: str
    skipped: bool
    issue_count: int = 0


def _summarize_action(outcomes: list[object]) -> str:
    actions = [getattr(outcome, "action", "updated") for outcome in outcomes]
    if any(action == "inserted" for action in actions):
        return "inserted"
    if any(action == "updated" for action in actions):
        return "updated"
    return "unchanged"
