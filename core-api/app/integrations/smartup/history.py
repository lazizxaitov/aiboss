"""Historical SmartUp import pipeline."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from json import dumps
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx

from app.core.data_layer.contracts import CoreDataWriter
from app.core.data_layer.core_upsert import CoreUpsertService
from app.core.data_layer.entities import (
    BusinessProfile,
    ContactProfile,
    FinanceEntry,
    FinanceEntryType,
    IngestionBatch,
    IngestionBatchStatus,
    IngestionError,
    SaleRecord,
    SaleStage,
    SourceSystem,
)
from app.core.data_layer.models import CoreRecord, CoreRecordKind, DataSourceType
from app.core.data_layer.normalized import (
    BankOperation,
    Customer,
    InventoryBalance,
    Payment,
    Product,
    ProductCategory,
    Sale,
    SaleItem,
    Visit,
    Warehouse,
)
from app.integrations.smartup.client import SmartUpApiClient, _redact_sensitive_text
from app.integrations.smartup.connector import (
    MAX_SMARTUP_HISTORY_WINDOW_DAYS,
    SmartUpConnector,
)
from app.integrations.smartup.filial_codes import (
    discover_verified_filial_code_from_raw_records,
    mark_verified_filial_code,
    resolve_filial_code,
)
from app.integrations.smartup.import_payloads import (
    build_bank_operation_export_payload,
    build_cash_operation_export_payload,
    build_cross_organizational_movement_export_payload,
    build_equipment_balance_export_payload,
    build_input_export_payload,
    build_internal_movement_export_payload,
    build_inventory_balance_export_payload,
    build_order_export_payload,
    build_purchase_export_payload,
    build_return_export_payload,
    build_stocktaking_export_payload,
    build_supplier_return_export_payload,
    build_visit_export_payload,
    build_writeoff_export_payload,
    clean_smartup_export_payload,
)
from app.integrations.smartup.mapping import SmartUpMapping
from app.integrations.smartup.models import (
    InventorySnapshot,
    MigrationBatch,
    SmartUpMigrationMode,
    SmartUpMigrationStatus,
    SmartUpOrganization,
    SmartUpRawRecord,
    SmartUpRawRecordStatus,
    SyncCheckpoint,
)
from app.integrations.smartup.normalizers.base import BaseSmartUpNormalizer
from app.integrations.smartup.normalizers.document import build_business_document_models
from app.integrations.smartup.profiles import SmartUpRequestProfile, get_request_profile

_INTERNAL_PAYLOAD_KEYS = {"source_object", "target_table", "sync_mode", "key_fields"}


class MissingFilialCodeError(ValueError):
    """Raised when Inventory Balance export cannot resolve filial_code."""


@dataclass(slots=True)
class SmartUpHistoricalImportRunner:
    """Run full-history migration jobs from SmartUp into the core layer."""

    client: SmartUpApiClient
    target: CoreDataWriter
    business_id: UUID
    business_name: str
    business_external_ref: str | None = None
    smartup_filial_id: str | None = None
    smartup_filial_code: str | None = None
    connector: SmartUpConnector = field(default_factory=SmartUpConnector)
    contact_index: dict[str, UUID] = field(default_factory=dict)

    def run(
        self,
        history_start: datetime,
        history_end: datetime | None = None,
        chunk_days: int = 7,
        migration_mode: SmartUpMigrationMode = SmartUpMigrationMode.FULL_BACKFILL,
    ) -> dict[str, int]:
        """Run a history import and return counters."""

        chunk_days = max(1, chunk_days)
        if migration_mode == SmartUpMigrationMode.FULL_BACKFILL and chunk_days < 30:
            chunk_days = 30
        elif migration_mode != SmartUpMigrationMode.FULL_BACKFILL:
            chunk_days = min(chunk_days, MAX_SMARTUP_HISTORY_WINDOW_DAYS)
        self.target.register_business(
            BusinessProfile(
                business_id=self.business_id,
                name=self.business_name,
                external_ref=self.business_external_ref or "SmartUp",
                metadata={
                    "source_system": "SmartUp",
                    "smartup_filial_id": self.smartup_filial_id,
                },
            ),
        )
        source_system = self._register_source_system()
        resolved_end = history_end or datetime.now(UTC)
        tasks = self.connector.build_sync_plan(
            migration_mode=migration_mode,
            history_start=history_start,
            history_end=resolved_end,
            chunk_days=chunk_days,
        )
        counters = {"batches": 0, "records": 0, "errors": 0}

        for task in tasks:
            mapping = self._get_mapping(task.mapping_name)
            if mapping is None:
                continue
            profile = get_request_profile(mapping.name)
            if profile is not None and profile.supports_snapshot:
                stats = self._import_snapshot_task(
                    task=task,
                    mapping=mapping,
                    source_system=source_system,
                    migration_mode=migration_mode,
                )
            elif task.window_start is not None and task.window_end is not None:
                stats = self._import_window_task(
                    task=task,
                    mapping=mapping,
                    source_system=source_system,
                    migration_mode=migration_mode,
                )
            else:
                stats = self._import_single_task(
                    task=task,
                    mapping=mapping,
                    source_system=source_system,
                    migration_mode=migration_mode,
                )
            counters["batches"] += stats.get("batches", 0)
            counters["records"] += stats.get("records", 0)
            counters["errors"] += stats.get("errors", 0)

        return counters

    def _import_single_task(
        self,
        *,
        task,
        mapping: SmartUpMapping,
        source_system: SourceSystem,
        migration_mode: SmartUpMigrationMode,
    ) -> dict[str, int]:
        profile = get_request_profile(mapping.name)
        try:
            request_payload = self._build_request_payload(
                task=task,
                mapping=mapping,
                profile=profile,
            )
            batch = self._create_batch(
                task=task,
                mapping=mapping,
                source_system=source_system,
                migration_mode=migration_mode,
                request_payload=request_payload,
            )
            imported, last_external_id = self._execute_mapping_task(
                batch=batch,
                task=task,
                mapping=mapping,
                profile=profile,
                request_payload=request_payload,
            )
            self._finalize_success(
                batch=batch,
                task=task,
                mapping=mapping,
                imported=imported,
                last_external_id=last_external_id,
                migration_mode=migration_mode,
            )
            return {"batches": 1, "records": imported, "errors": 0}
        except httpx.HTTPStatusError as exc:
            response = getattr(exc, "response", None)
            if getattr(response, "status_code", None) == 403:
                self._finalize_permission_denied(
                    batch=batch,
                    task=task,
                    mapping=mapping,
                    migration_mode=migration_mode,
                    response=response,
                    request_payload=request_payload,
                    problematic_date=task.window_start,
                )
                return {"batches": 1, "records": 0, "errors": 1}
            self._finalize_failure(
                batch=batch,
                task=task,
                mapping=mapping,
                exception=exc,
                migration_mode=migration_mode,
                problematic_date=task.window_start,
            )
            return {"batches": 1, "records": 0, "errors": 1}
        except MissingFilialCodeError:
            if mapping.name in {"Inventory balance", "Equipment balance"}:
                request_payload = build_inventory_balance_export_payload()
            batch = self._create_batch(
                task=task,
                mapping=mapping,
                source_system=source_system,
                migration_mode=migration_mode,
                request_payload=request_payload,
            )
            self._finalize_missing_filial_code(
                batch=batch,
                task=task,
                mapping=mapping,
                migration_mode=migration_mode,
                request_payload=request_payload,
                problematic_date=task.window_start,
            )
            return {"batches": 1, "records": 0, "errors": 1}
        except Exception as exc:  # pragma: no cover - transport/runtime safety
            self._finalize_failure(
                batch=batch,
                task=task,
                mapping=mapping,
                exception=exc,
                migration_mode=migration_mode,
                problematic_date=task.window_start,
            )
            return {"batches": 1, "records": 0, "errors": 1}

    def _import_snapshot_task(
        self,
        *,
        task,
        mapping: SmartUpMapping,
        source_system: SourceSystem,
        migration_mode: SmartUpMigrationMode,
    ) -> dict[str, int]:
        return self._import_single_task(
            task=task,
            mapping=mapping,
            source_system=source_system,
            migration_mode=migration_mode,
        )

    def _import_window_task(
        self,
        *,
        task,
        mapping: SmartUpMapping,
        source_system: SourceSystem,
        migration_mode: SmartUpMigrationMode,
    ) -> dict[str, int]:
        if task.window_start is None or task.window_end is None:
            return self._import_single_task(
                task=task,
                mapping=mapping,
                source_system=source_system,
                migration_mode=migration_mode,
            )
        window_days = task.window_days or max(
            1,
            (task.window_end.date() - task.window_start.date()).days or 1,
        )
        return self._import_window_range(
            task=task,
            mapping=mapping,
            source_system=source_system,
            migration_mode=migration_mode,
            window_start=task.window_start,
            window_end=task.window_end,
            window_days=window_days,
        )

    def _import_window_range(
        self,
        *,
        task,
        mapping: SmartUpMapping,
        source_system: SourceSystem,
        migration_mode: SmartUpMigrationMode,
        window_start: datetime,
        window_end: datetime,
        window_days: int,
    ) -> dict[str, int]:
        profile = get_request_profile(mapping.name)
        if profile is None or not profile.supports_history:
            return self._import_single_task(
                task=task,
                mapping=mapping,
                source_system=source_system,
                migration_mode=migration_mode,
            )

        try:
            request_payload = self._build_request_payload(
                task=task,
                mapping=mapping,
                profile=profile,
                window_start=window_start,
                window_end=window_end,
            )
            batch = self._create_batch(
                task=task,
                mapping=mapping,
                source_system=source_system,
                migration_mode=migration_mode,
                window_start=window_start,
                window_end=window_end,
                request_payload=request_payload,
            )
            response = self.client.request_json(mapping, request_payload)
            imported, last_external_id = self._persist_response(batch, mapping, response)
            self._finalize_success(
                batch=batch,
                task=task,
                mapping=mapping,
                imported=imported,
                last_external_id=last_external_id,
                migration_mode=migration_mode,
                window_start=window_start,
                window_end=window_end,
            )
            return {"batches": 1, "records": imported, "errors": 0}
        except httpx.HTTPStatusError as exc:
            response = getattr(exc, "response", None)
            request_payload = locals().get("request_payload", task.payload_template)
            batch = self._create_batch(
                task=task,
                mapping=mapping,
                source_system=source_system,
                migration_mode=migration_mode,
                window_start=window_start,
                window_end=window_end,
                request_payload=request_payload,
            )
            if getattr(response, "status_code", None) == 403:
                self._finalize_permission_denied(
                    batch=batch,
                    task=task,
                    mapping=mapping,
                    migration_mode=migration_mode,
                    response=response,
                    request_payload=request_payload,
                    problematic_date=window_start,
                    window_start=window_start,
                    window_end=window_end,
                )
                return {"batches": 1, "records": 0, "errors": 1}
            self._finalize_failure(
                batch=batch,
                task=task,
                mapping=mapping,
                exception=exc,
                migration_mode=migration_mode,
                problematic_date=window_start,
            )
            return {"batches": 1, "records": 0, "errors": 1}
        except MissingFilialCodeError:
            request_payload = build_inventory_balance_export_payload(
                begin_date=window_start,
                end_date=window_end,
            )
            batch = self._create_batch(
                task=task,
                mapping=mapping,
                source_system=source_system,
                migration_mode=migration_mode,
                window_start=window_start,
                window_end=window_end,
                request_payload=request_payload,
            )
            self._finalize_missing_filial_code(
                batch=batch,
                task=task,
                mapping=mapping,
                migration_mode=migration_mode,
                request_payload=request_payload,
                problematic_date=window_start,
                window_start=window_start,
                window_end=window_end,
            )
            return {"batches": 1, "records": 0, "errors": 1}
        except Exception as exc:  # pragma: no cover - transport/runtime safety
            if self._is_retryable_exception(exc) and window_days > 1:
                smaller = 7 if window_days > 7 else 1
                if smaller < window_days:
                    total = {"batches": 0, "records": 0, "errors": 0}
                    for start, end in self._split_window(window_start, window_end, smaller):
                        subwindow_days = max(1, (end.date() - start.date()).days or 1)
                        child = self._import_window_range(
                            task=task,
                            mapping=mapping,
                            source_system=source_system,
                            migration_mode=migration_mode,
                            window_start=start,
                            window_end=end,
                            window_days=subwindow_days,
                        )
                        for key, value in child.items():
                            total[key] = total.get(key, 0) + value
                    return total
            request_payload = locals().get("request_payload", task.payload_template)
            batch = self._create_batch(
                task=task,
                mapping=mapping,
                source_system=source_system,
                migration_mode=migration_mode,
                window_start=window_start,
                window_end=window_end,
                request_payload=request_payload,
            )
            self._finalize_failure(
                batch=batch,
                task=task,
                mapping=mapping,
                exception=exc,
                migration_mode=migration_mode,
                problematic_date=window_start,
            )
            return {"batches": 1, "records": 0, "errors": 1}

    def _execute_mapping_task(
        self,
        *,
        batch: IngestionBatch,
        task,
        mapping: SmartUpMapping,
        profile: SmartUpRequestProfile | None,
        request_payload: dict[str, object],
    ) -> tuple[int, str | None]:
        if (
            profile is not None
            and profile.page_size
            and profile.offset_param
            and profile.limit_param
        ):
            return self._run_paginated_task(batch, task, mapping, request_payload, profile)
        response = self.client.request_json(mapping, request_payload)
        return self._persist_response(batch, mapping, response)

    def _create_batch(
        self,
        *,
        task,
        mapping: SmartUpMapping,
        source_system: SourceSystem,
        migration_mode: SmartUpMigrationMode,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        request_payload: dict[str, object] | None = None,
    ) -> IngestionBatch:
        batch_name = self._batch_name(task, window_start, window_end, migration_mode)
        started_at = datetime.now(UTC)
        serialized_request_payload = request_payload or task.payload_template
        request_context = self._request_context()
        metadata = {
            "source_endpoint": task.endpoint,
            "endpoint": task.endpoint,
            "requested_url": self._requested_url(mapping.smartup_endpoint),
            "method": task.method,
            "target_table": task.target_table,
            "payload": serialized_request_payload,
            "request_payload": serialized_request_payload,
            "smartup_filial_id": self.smartup_filial_id,
            "filial_id": self.smartup_filial_id,
            **request_context,
            "migration_mode": migration_mode.value,
            "window_start": window_start.isoformat() if window_start else None,
            "window_end": window_end.isoformat() if window_end else None,
        }
        batch = IngestionBatch(
            batch_id=self._stable_batch_uuid(mapping, migration_mode, window_start, window_end),
            business_id=self.business_id,
            source_system_id=source_system.source_system_id,
            batch_name=batch_name,
            started_at=started_at,
            status=IngestionBatchStatus.RUNNING,
            metadata=metadata,
        )
        self.target.upsert_ingestion_batch(batch)
        self.target.upsert_migration_batch(
            MigrationBatch(
                id=batch.batch_id,
                organization_id=self.business_id,
                filial_id=self.smartup_filial_id,
                entity_type=mapping.target_entity,
                endpoint=task.endpoint,
                request_payload=serialized_request_payload,
                migration_mode=migration_mode,
                date_from=window_start or started_at,
                date_to=window_end or started_at,
                status=SmartUpMigrationStatus.RUNNING,
                started_at=started_at,
                metadata=metadata,
            ),
        )
        return batch

    def _finalize_success(
        self,
        *,
        batch: IngestionBatch,
        task,
        mapping: SmartUpMapping,
        imported: int,
        last_external_id: str | None,
        migration_mode: SmartUpMigrationMode,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> None:
        finished_at = datetime.now(UTC)
        result_counts = (
            batch.metadata.get("result_counts") if isinstance(batch.metadata, dict) else None
        )
        inserted_count = imported
        updated_count = 0
        skipped_count = 0
        failed_count = 0
        if isinstance(result_counts, dict):
            inserted_count = int(result_counts.get("inserted", inserted_count) or 0)
            updated_count = int(result_counts.get("updated", 0) or 0)
            skipped_count = int(result_counts.get("skipped", 0) or 0)
            failed_count = int(result_counts.get("failed", 0) or 0)
        batch.status = IngestionBatchStatus.COMPLETED
        batch.finished_at = finished_at
        batch.stats = {"records_imported": imported}
        self.target.upsert_ingestion_batch(batch)
        batch_endpoint = (
            batch.metadata.get("endpoint") if isinstance(batch.metadata, dict) else None
        )
        batch_request_payload = (
            batch.metadata.get("request_payload") if isinstance(batch.metadata, dict) else None
        )

        migration_batch = MigrationBatch(
            id=batch.batch_id,
            organization_id=self.business_id,
            filial_id=self.smartup_filial_id,
            entity_type=mapping.target_entity,
            endpoint=batch_endpoint,
            request_payload=batch_request_payload,
            migration_mode=migration_mode,
            date_from=window_start or finished_at,
            date_to=window_end or finished_at,
            status=SmartUpMigrationStatus.COMPLETED,
            received_count=imported,
            inserted_count=inserted_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            started_at=batch.started_at,
            finished_at=finished_at,
            metadata=batch.metadata,
        )
        self.target.upsert_migration_batch(migration_batch)
        checkpoint = self._load_checkpoint(mapping, migration_mode)
        checkpoint.status = SmartUpMigrationStatus.COMPLETED
        checkpoint.attempts += 1
        checkpoint.last_error = None
        checkpoint.period_start = window_start or checkpoint.period_start
        checkpoint.period_end = window_end or checkpoint.period_end
        checkpoint.last_successful_date = window_end or finished_at
        checkpoint.last_successful_external_id = last_external_id
        checkpoint.updated_at = finished_at
        self.target.upsert_sync_checkpoint(checkpoint)

    def _finalize_failure(
        self,
        *,
        batch: IngestionBatch,
        task,
        mapping: SmartUpMapping,
        exception: Exception,
        migration_mode: SmartUpMigrationMode,
        problematic_date: datetime | None = None,
    ) -> None:
        finished_at = datetime.now(UTC)
        message = str(exception)
        batch_endpoint = (
            batch.metadata.get("endpoint") if isinstance(batch.metadata, dict) else None
        )
        request_payload = (
            batch.metadata.get("request_payload") if isinstance(batch.metadata, dict) else None
        )
        batch.status = IngestionBatchStatus.FAILED
        batch.finished_at = finished_at
        self.target.upsert_ingestion_batch(batch)
        self.target.upsert_migration_batch(
            MigrationBatch(
                id=batch.batch_id,
                organization_id=self.business_id,
                filial_id=self.smartup_filial_id,
                entity_type=mapping.target_entity,
                endpoint=batch_endpoint,
                request_payload=request_payload,
                migration_mode=migration_mode,
                date_from=problematic_date or finished_at,
                date_to=problematic_date or finished_at,
                status=SmartUpMigrationStatus.FAILED,
                received_count=0,
                inserted_count=0,
                updated_count=0,
                skipped_count=0,
                failed_count=1,
                started_at=batch.started_at,
                finished_at=finished_at,
                problematic_date=problematic_date,
                error_message=message,
                metadata=batch.metadata,
            ),
        )
        self.target.record_ingestion_error(
            IngestionError(
                batch_id=batch.batch_id,
                entity_type=mapping.target_entity,
                error_code=type(exception).__name__,
                error_message=message,
                metadata={
                    "endpoint": batch_endpoint or task.endpoint,
                    "payload": request_payload,
                    "request_payload": request_payload,
                    "filial_id": self.smartup_filial_id,
                    "smartup_filial_id": self.smartup_filial_id,
                    "migration_mode": migration_mode.value,
                    "problematic_date": problematic_date.isoformat() if problematic_date else None,
                },
            ),
        )
        checkpoint = self._load_checkpoint(mapping, migration_mode)
        checkpoint.status = SmartUpMigrationStatus.FAILED
        checkpoint.attempts += 1
        checkpoint.last_error = message
        checkpoint.last_successful_date = problematic_date
        checkpoint.updated_at = finished_at
        self.target.upsert_sync_checkpoint(checkpoint)

    def _finalize_permission_denied(
        self,
        *,
        batch: IngestionBatch,
        task,
        mapping: SmartUpMapping,
        migration_mode: SmartUpMigrationMode,
        response: httpx.Response | None,
        request_payload: dict[str, object],
        problematic_date: datetime | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> None:
        finished_at = datetime.now(UTC)
        status_code = getattr(response, "status_code", 403) or 403
        content_type = getattr(getattr(response, "headers", None), "get", lambda _: None)(
            "content-type",
        )
        upstream_response = _redact_sensitive_text(getattr(response, "text", "") or "")
        batch_endpoint = (
            batch.metadata.get("endpoint") if isinstance(batch.metadata, dict) else None
        )
        request_payload = (
            batch.metadata.get("request_payload") if isinstance(batch.metadata, dict) else None
        )
        batch.status = IngestionBatchStatus.PERMISSION_DENIED
        batch.finished_at = finished_at
        batch.metadata = {
            **batch.metadata,
            "upstream_status": status_code,
            "upstream_content_type": content_type,
            "upstream_response": upstream_response,
            "request_payload": request_payload,
        }
        self.target.upsert_ingestion_batch(batch)
        self.target.upsert_migration_batch(
            MigrationBatch(
                id=batch.batch_id,
                organization_id=self.business_id,
                filial_id=self.smartup_filial_id,
                entity_type=mapping.target_entity,
                endpoint=batch_endpoint,
                request_payload=request_payload,
                migration_mode=migration_mode,
                date_from=window_start or problematic_date or finished_at,
                date_to=window_end or problematic_date or finished_at,
                status=SmartUpMigrationStatus.PERMISSION_DENIED,
                received_count=0,
                inserted_count=0,
                updated_count=0,
                skipped_count=0,
                failed_count=0,
                upstream_status=status_code,
                upstream_response=upstream_response,
                started_at=batch.started_at,
                finished_at=finished_at,
                problematic_date=problematic_date,
                error_message="SMARTUP_PERMISSION_DENIED",
                metadata=batch.metadata,
            ),
        )
        self.target.record_ingestion_error(
            IngestionError(
                batch_id=batch.batch_id,
                entity_type=mapping.target_entity,
                error_code="SMARTUP_PERMISSION_DENIED",
                error_message=(
                    "Пользователь не имеет доступа к endpoint, проекту или выбранной организации"
                ),
                metadata={
                    "endpoint": batch_endpoint or task.endpoint,
                    "payload": request_payload,
                    "request_payload": request_payload,
                    "filial_id": self.smartup_filial_id,
                    "smartup_filial_id": self.smartup_filial_id,
                    "migration_mode": migration_mode.value,
                    "problematic_date": problematic_date.isoformat() if problematic_date else None,
                    "upstream_status": status_code,
                    "upstream_response": upstream_response,
                    "content_type": content_type,
                },
            ),
        )
        checkpoint = self._load_checkpoint(mapping, migration_mode)
        checkpoint.status = SmartUpMigrationStatus.PERMISSION_DENIED
        checkpoint.attempts += 1
        checkpoint.last_error = "SMARTUP_PERMISSION_DENIED"
        checkpoint.last_successful_date = problematic_date
        checkpoint.updated_at = finished_at
        self.target.upsert_sync_checkpoint(checkpoint)

    def _finalize_missing_filial_code(
        self,
        *,
        batch: IngestionBatch,
        task,
        mapping: SmartUpMapping,
        migration_mode: SmartUpMigrationMode,
        request_payload: dict[str, object],
        problematic_date: datetime | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> None:
        finished_at = datetime.now(UTC)
        batch_endpoint = (
            batch.metadata.get("endpoint") if isinstance(batch.metadata, dict) else None
        )
        batch.status = IngestionBatchStatus.FAILED
        batch.finished_at = finished_at
        batch.metadata = {
            **batch.metadata,
            "error_code": "missing_filial_code",
            "request_payload": request_payload,
        }
        self.target.upsert_ingestion_batch(batch)
        self.target.upsert_migration_batch(
            MigrationBatch(
                id=batch.batch_id,
                organization_id=self.business_id,
                filial_id=self.smartup_filial_id,
                entity_type=mapping.target_entity,
                endpoint=batch_endpoint,
                request_payload=request_payload,
                migration_mode=migration_mode,
                date_from=window_start or problematic_date or finished_at,
                date_to=window_end or problematic_date or finished_at,
                status=SmartUpMigrationStatus.FAILED,
                received_count=0,
                inserted_count=0,
                updated_count=0,
                skipped_count=0,
                failed_count=1,
                started_at=batch.started_at,
                finished_at=finished_at,
                problematic_date=problematic_date,
                error_message="missing_filial_code",
                metadata=batch.metadata,
            ),
        )
        self.target.record_ingestion_error(
            IngestionError(
                batch_id=batch.batch_id,
                entity_type=mapping.target_entity,
                error_code="missing_filial_code",
                error_message="SmartUp filial_code is required for Inventory Balance export",
                metadata={
                    "endpoint": batch_endpoint or task.endpoint,
                    "payload": request_payload,
                    "request_payload": request_payload,
                    "filial_id": self.smartup_filial_id,
                    "smartup_filial_id": self.smartup_filial_id,
                    "migration_mode": migration_mode.value,
                    "problematic_date": problematic_date.isoformat() if problematic_date else None,
                },
            ),
        )
        checkpoint = self._load_checkpoint(mapping, migration_mode)
        checkpoint.status = SmartUpMigrationStatus.FAILED
        checkpoint.attempts += 1
        checkpoint.last_error = "missing_filial_code"
        checkpoint.last_successful_date = problematic_date
        checkpoint.updated_at = finished_at
        self.target.upsert_sync_checkpoint(checkpoint)

    def _load_checkpoint(
        self,
        mapping: SmartUpMapping,
        migration_mode: SmartUpMigrationMode,
    ) -> SyncCheckpoint:
        existing = self.target.get_sync_checkpoint(
            self.business_id,
            mapping.target_entity,
            migration_mode.value,
        )
        if existing is not None:
            return existing
        now = datetime.now(UTC)
        return SyncCheckpoint(
            id=self._stable_checkpoint_uuid(mapping, migration_mode),
            organization_id=self.business_id,
            entity_type=mapping.target_entity,
            migration_mode=migration_mode,
            period_start=now,
            period_end=now,
            status=SmartUpMigrationStatus.PENDING,
            attempts=0,
            metadata={"smartup_filial_id": self.smartup_filial_id},
        )

    @staticmethod
    def _is_retryable_exception(exc: Exception) -> bool:
        if isinstance(exc, (TimeoutError, ConnectionError, httpx.TimeoutException)):
            return True
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        return status_code is not None and int(status_code) >= 500

    @staticmethod
    def _split_window(
        start: datetime,
        end: datetime,
        chunk_days: int,
    ) -> list[tuple[datetime, datetime]]:
        if chunk_days <= 0:
            return [(start, end)]
        windows: list[tuple[datetime, datetime]] = []
        current = start
        delta = timedelta(days=max(chunk_days, 1))
        while current < end:
            candidate = min(current + delta, end)
            if candidate <= current:
                candidate = end
            windows.append((current, candidate))
            current = candidate
        return windows

    def _register_source_system(self) -> SourceSystem:
        settings = getattr(self.client, "settings", None)
        base_url = getattr(settings, "base_url", "https://smartup.online")
        project_code = getattr(settings, "project_code", None)
        filial_id = self.smartup_filial_id
        external_ref = filial_id or project_code or base_url
        source_system = SourceSystem(
            source_system_id=_stable_source_system_uuid(self.business_id, external_ref),
            business_id=self.business_id,
            name="SmartUp",
            source_type="erp",
            external_ref=external_ref,
            metadata={
                "base_url": base_url,
                "filial_id": filial_id,
                "project_code": project_code,
                "smartup_filial_id": filial_id,
            },
        )
        return self.target.register_source_system(source_system)

    def _requested_url(self, endpoint: str) -> str:
        base_url = getattr(
            getattr(self.client, "settings", None), "base_url", "https://smartup.online"
        )
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        return f"{base_url.rstrip('/')}{endpoint}"

    def _run_paginated_task(
        self,
        batch: IngestionBatch,
        task,
        mapping: SmartUpMapping,
        base_payload: dict[str, object],
        profile: SmartUpRequestProfile,
    ) -> tuple[int, str | None]:
        imported = 0
        last_external_id: str | None = None
        prepared_payload = self._prepare_request_payload(mapping, base_payload)
        offset = int(prepared_payload.get(profile.offset_param or "offset", 0))
        limit = int(prepared_payload.get(profile.limit_param or "limit", profile.page_size or 0))

        while True:
            payload = dict(prepared_payload)
            payload[profile.offset_param or "offset"] = offset
            payload[profile.limit_param or "limit"] = limit
            response = self.client.request_json(mapping, payload)
            page_count, page_last_external_id = self._persist_response(batch, mapping, response)
            imported += page_count
            if page_last_external_id:
                last_external_id = page_last_external_id
            if page_count < limit:
                break
            offset += limit
        return imported, last_external_id

    def _prepare_request_payload(
        self,
        mapping: SmartUpMapping,
        payload: dict[str, object],
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> dict[str, object]:
        prepared = {
            key: value for key, value in payload.items() if key not in _INTERNAL_PAYLOAD_KEYS
        }
        prepared.update(self._documented_request_payload(mapping))
        self._apply_history_window(mapping, prepared, window_start, window_end)
        return clean_smartup_export_payload(prepared)

    def _build_request_payload(
        self,
        *,
        task,
        mapping: SmartUpMapping,
        profile: SmartUpRequestProfile | None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> dict[str, object]:
        if mapping.name == "Orders":
            if window_start is None or window_end is None:
                return build_order_export_payload()
            return build_order_export_payload(
                begin_deal_date=window_start,
                end_deal_date=window_end,
            )
        if mapping.name == "Inventory balance":
            filial_code = self._resolve_inventory_balance_filial_code()
            if filial_code is None:
                raise MissingFilialCodeError("missing_filial_code")
            return build_inventory_balance_export_payload(
                begin_date=window_start,
                end_date=window_end,
                filial_code=filial_code,
            )
        if (
            profile is not None
            and profile.page_size
            and profile.offset_param
            and profile.limit_param
        ):
            return self._prepare_request_payload(mapping, task.payload_template)
        return self._prepare_request_payload(
            mapping,
            task.payload_template,
            window_start,
            window_end,
        )

    def _documented_request_payload(self, mapping: SmartUpMapping) -> dict[str, object]:
        filial_code = self._verified_organization_filial_code()
        filial_codes_array = [{"filial_code": filial_code}] if filial_code else []
        if mapping.name == "Legal entities":
            return {
                "rooms": [{"room_code": ""}],
                "code": "",
                "state": "",
                "begin_created_on": "",
                "end_created_on": "",
                "begin_modified_on": "",
                "end_modified_on": "",
            }
        if mapping.name == "Natural persons":
            return {
                "rooms": [{"room_code": ""}],
                "code": "",
                "begin_created_on": "",
                "end_created_on": "",
                "begin_modified_on": "",
                "end_modified_on": "",
            }
        if mapping.name in {
            "Inventory",
            "Service export",
            "Product groups",
            "Producers",
            "Workspaces",
        }:
            return {
                "code": "",
                "begin_created_on": "",
                "end_created_on": "",
                "begin_modified_on": "",
                "end_modified_on": "",
            }
        if mapping.name == "Price types":
            return {
                "column_list": [
                    "code",
                    "name",
                    "short_name",
                    "with_card",
                    "state",
                    "price_type_kind",
                    "currency_code",
                ],
                "limit": "1000",
                "offset": "0",
            }
        if mapping.name == "Inventory prices":
            return {"price_type_codes": []}
        if mapping.name == "Contracts":
            payload = {
                "code": "",
                "contract_id": "",
                "begin_contract_date": "",
                "end_contract_date": "",
                "begin_created_on": "",
                "end_created_on": "",
                "begin_modified_on": "",
                "end_modified_on": "",
            }
            if filial_codes_array:
                payload["filial_codes"] = filial_codes_array
            return payload
        if mapping.name == "Orders":
            return {}
        if mapping.name == "Returns":
            return build_return_export_payload()
        if mapping.name == "Visits":
            return build_visit_export_payload()
        if mapping.name == "Cross-organizational movement export":
            return build_cross_organizational_movement_export_payload()
        if mapping.name == "Internal movement export":
            return build_internal_movement_export_payload()
        if mapping.name == "Stocktaking export":
            return build_stocktaking_export_payload()
        if mapping.name == "Write-off export":
            return build_writeoff_export_payload()
        if mapping.name == "Return to suppliers export":
            return build_supplier_return_export_payload()
        if mapping.name == "Receipts to warehouse export":
            return build_input_export_payload()
        if mapping.name == "Purchase export":
            return build_purchase_export_payload()
        if mapping.name == "Logistics export":
            return {
                "logistics": [
                    {
                        "logistics_id": "",
                        "external_id": "",
                        "delivery_date": "",
                        "expeditor_code": "",
                        "expeditor_name": "",
                        "van_code": "",
                        "van_name": "",
                        "lap": "",
                        "begin_location": "",
                        "end_location": "",
                        "cash_register_id": "",
                        "cash_register_name": "",
                        "deals": [
                            {
                                "deal_id": "",
                                "status": "",
                                "external_id": "",
                            }
                        ],
                    }
                ],
            }
        if mapping.name in {"Payments from clients", "Client payments"}:
            payload = {
                "external_id": "",
                "cashin_id": "",
                "begin_cashin_date": "",
                "end_cashin_date": "",
                "begin_created_on": "",
                "end_created_on": "",
                "begin_modified_on": "",
                "end_modified_on": "",
            }
            if filial_code:
                payload["filial_code"] = filial_code
            if filial_codes_array:
                payload["filial_codes"] = filial_codes_array
            return payload
        if mapping.name in {"Cash operations", "Bank statements"}:
            builder = (
                build_cash_operation_export_payload
                if mapping.name == "Cash operations"
                else build_bank_operation_export_payload
            )
            return builder(filial_code=filial_code or None)
        if mapping.name == "Inventory balance":
            return build_inventory_balance_export_payload(
                filial_code=self._resolve_inventory_balance_filial_code() or filial_code or None,
            )
        if mapping.name == "Equipment balance":
            resolved_filial_code = self._resolve_inventory_balance_filial_code()
            if resolved_filial_code is None:
                raise MissingFilialCodeError("missing_filial_code")
            return build_equipment_balance_export_payload(
                filial_code=resolved_filial_code,
            )
        if mapping.name == "Movement export":
            payload = {
                "movement_id": "",
                "external_id": "",
                "begin_movement_date": "",
                "end_movement_date": "",
                "begin_created_on": "",
                "end_created_on": "",
                "begin_modified_on": "",
                "end_modified_on": "",
            }
            if filial_codes_array:
                payload["filial_codes"] = filial_codes_array
            return payload
        if mapping.name == "Request export":
            payload = {
                "external_id": "",
                "request_id": "",
                "begin_request_date": "",
                "end_request_date": "",
                "begin_created_on": "",
                "end_created_on": "",
                "begin_modified_on": "",
                "end_modified_on": "",
            }
            if filial_codes_array:
                payload["filial_codes"] = filial_codes_array
            return payload
        if mapping.name == "Return reason export":
            return {}
        return {}

    def _verified_organization_filial_code(self) -> str | None:
        get_organization = getattr(self.target, "get_smartup_organization", None)
        if not callable(get_organization):
            return None
        organization = get_organization(self.business_id)
        if organization is None:
            return None
        raw_records = list(self.target.list_smartup_raw_records(organization_id=self.business_id))
        verified = resolve_filial_code(organization, raw_records)
        if verified:
            self.smartup_filial_code = verified
        return verified

    def _apply_history_window(
        self,
        mapping: SmartUpMapping,
        payload: dict[str, object],
        window_start: datetime | None,
        window_end: datetime | None,
    ) -> None:
        if window_start is None and window_end is None:
            return
        date_from = self._format_smartup_date(window_start) if window_start else None
        date_to = self._format_smartup_date(window_end) if window_end else None
        window_fields: dict[str, tuple[str, ...]] = {
            "Legal entities": (
                "begin_created_on",
                "end_created_on",
                "begin_modified_on",
                "end_modified_on",
            ),
            "Natural persons": (
                "begin_created_on",
                "end_created_on",
                "begin_modified_on",
                "end_modified_on",
            ),
            "Inventory": (
                "begin_created_on",
                "end_created_on",
                "begin_modified_on",
                "end_modified_on",
            ),
            "Service export": (
                "begin_created_on",
                "end_created_on",
                "begin_modified_on",
                "end_modified_on",
            ),
            "Product groups": (
                "begin_created_on",
                "end_created_on",
                "begin_modified_on",
                "end_modified_on",
            ),
            "Producers": (
                "begin_created_on",
                "end_created_on",
                "begin_modified_on",
                "end_modified_on",
            ),
            "Workspaces": (
                "begin_created_on",
                "end_created_on",
                "begin_modified_on",
                "end_modified_on",
            ),
            "Contracts": (
                "begin_contract_date",
                "end_contract_date",
                "begin_created_on",
                "end_created_on",
                "begin_modified_on",
                "end_modified_on",
            ),
            "Orders": (
                "begin_deal_date",
                "end_deal_date",
                "begin_created_on",
                "end_created_on",
                "begin_modified_on",
                "end_modified_on",
            ),
            "Returns": (
                "begin_return_date",
                "end_return_date",
            ),
            "Visits": (
                "begin_visit_date",
                "end_visit_date",
            ),
            "Cross-organizational movement export": (
                "begin_from_date",
                "end_from_date",
            ),
            "Internal movement export": (
                "begin_from_movement_date",
                "end_from_movement_date",
            ),
            "Stocktaking export": (
                "begin_stocktaking_date",
                "end_stocktaking_date",
            ),
            "Write-off export": (
                "begin_writeoff_date",
                "end_writeoff_date",
            ),
            "Return to suppliers export": (
                "begin_return_date",
                "end_return_date",
            ),
            "Receipts to warehouse export": (
                "begin_input_date",
                "end_input_date",
            ),
            "Purchase export": (
                "begin_purchase_date",
                "end_purchase_date",
            ),
            "Payments from clients": (
                "begin_cashin_date",
                "end_cashin_date",
                "begin_created_on",
                "end_created_on",
                "begin_modified_on",
                "end_modified_on",
            ),
            "Client payments": (
                "begin_cashin_date",
                "end_cashin_date",
                "begin_created_on",
                "end_created_on",
                "begin_modified_on",
                "end_modified_on",
            ),
            "Cash operations": (
                "begin_operation_date",
                "end_operation_date",
                "begin_created_on",
                "end_created_on",
                "begin_modified_on",
                "end_modified_on",
            ),
            "Bank statements": (
                "begin_operation_date",
                "end_operation_date",
                "begin_created_on",
                "end_created_on",
                "begin_modified_on",
                "end_modified_on",
            ),
            "Inventory balance": ("begin_date", "end_date"),
            "Movement export": (
                "begin_movement_date",
                "end_movement_date",
                "begin_created_on",
                "end_created_on",
                "begin_modified_on",
                "end_modified_on",
            ),
            "Request export": (
                "begin_request_date",
                "end_request_date",
                "begin_created_on",
                "end_created_on",
                "begin_modified_on",
                "end_modified_on",
            ),
        }
        # Logistics export is documented as a static nested payload without history
        # range fields, so we intentionally do not inject window filters here.
        fields = window_fields.get(mapping.name)
        if fields is None:
            return
        for field_name in fields:
            current_value = payload.get(field_name)
            if field_name.startswith("begin") and date_from is not None and not current_value:
                payload[field_name] = date_from
            elif field_name.startswith("end") and date_to is not None and not current_value:
                payload[field_name] = date_to

    def _resolve_inventory_balance_filial_code(self) -> str | None:
        get_organization = getattr(self.target, "get_smartup_organization", None)
        if callable(get_organization):
            organization = get_organization(self.business_id)
            raw_records = list(
                self.target.list_smartup_raw_records(organization_id=self.business_id),
            )
            organization_code = resolve_filial_code(organization, raw_records)
            if organization_code:
                self.smartup_filial_code = organization_code
                return organization_code

        discovered = self._discover_inventory_balance_filial_code()
        if discovered is None:
            return None

        self.smartup_filial_code = discovered
        self._persist_inventory_balance_filial_code(discovered)
        return discovered

    def _discover_inventory_balance_filial_code(self) -> str | None:
        try:
            raw_records = list(
                self.target.list_smartup_raw_records(
                    organization_id=self.business_id,
                    entity_type="sales",
                    processing_status=SmartUpRawRecordStatus.NORMALIZED,
                ),
            )
        except TypeError:
            raw_records = list(
                self.target.list_smartup_raw_records(organization_id=self.business_id),
            )
        get_organization = getattr(self.target, "get_smartup_organization", None)
        if not callable(get_organization):
            return None
        organization = get_organization(self.business_id)
        if organization is None:
            return None
        organization_records = [
            record
            for record in raw_records
            if getattr(record, "organization_id", None) == self.business_id
        ]
        discovered, raw_record_id = discover_verified_filial_code_from_raw_records(
            organization_records,
            organization.filial_id,
        )
        if discovered:
            organization = mark_verified_filial_code(
                organization,
                discovered,
                source="order_export",
                raw_record_id=raw_record_id,
            )
            self._persist_inventory_balance_filial_code(organization)
            return discovered
        return None

    def _persist_inventory_balance_filial_code(
        self,
        organization_or_code: SmartUpOrganization | str,
    ) -> None:
        get_organization = getattr(self.target, "get_smartup_organization", None)
        upsert_organization = getattr(self.target, "upsert_smartup_organization", None)
        if not callable(get_organization) or not callable(upsert_organization):
            return
        organization = (
            organization_or_code
            if isinstance(organization_or_code, SmartUpOrganization)
            else get_organization(self.business_id)
        )
        if organization is None:
            return
        if isinstance(organization_or_code, str):
            code = self._clean_text(organization_or_code)
            if not code:
                return
            if self._clean_text(getattr(organization, "filial_code", None)) == code:
                return
            updated = organization.model_copy(
                update={
                    "filial_code": code,
                    "updated_at": datetime.now(UTC),
                },
            )
        else:
            updated = organization
        upsert_organization(updated)

    @staticmethod
    def _is_order_export_record(source_endpoint: str, entity_type: str) -> bool:
        endpoint = (source_endpoint or "").strip().casefold()
        entity = (entity_type or "").strip().casefold()
        return "order$export" in endpoint or entity in {"order", "orders", "sales"}

    def _is_trusted_filial_code_record(self, record: SmartUpRawRecord) -> bool:
        expected = self._clean_text(self.smartup_filial_id)
        if not expected:
            return False
        requested = self._clean_text(getattr(record, "request_filial_id", None))
        source = self._clean_text(getattr(record, "filial_id", None))
        response = self._clean_text(getattr(record, "response_filial_id", None))
        return (
            requested in {None, expected}
            and source in {None, expected}
            and response
            in {
                None,
                expected,
            }
        )

    def _has_filial_id_conflict(self, filial_code: str | None) -> bool:
        candidate = self._clean_text(filial_code)
        if not candidate:
            return False
        organizations = getattr(self.target, "list_smartup_organizations", None)
        if not callable(organizations):
            return False
        for organization in organizations():
            if str(getattr(organization, "id", "")) == str(self.business_id):
                continue
            if self._clean_text(getattr(organization, "filial_id", None)) == candidate:
                return True
        return False

    @staticmethod
    def _extract_filial_id(payload: object) -> str | None:
        if isinstance(payload, dict):
            direct = payload.get("filial_id")
            if direct is not None:
                text = str(direct).strip()
                if text:
                    return text
            for item in payload.values():
                discovered = SmartUpHistoricalImportRunner._extract_filial_id(item)
                if discovered:
                    return discovered
        elif isinstance(payload, list):
            for item in payload:
                discovered = SmartUpHistoricalImportRunner._extract_filial_id(item)
                if discovered:
                    return discovered
        return None

    def _persist_response(
        self,
        batch: IngestionBatch,
        mapping: SmartUpMapping,
        response: dict[str, object] | list[object] | str,
    ) -> tuple[int, str | None]:
        profile = get_request_profile(mapping.name)
        rows = self._extract_response_rows(mapping, response, profile)
        if not rows:
            return 0, None
        self._store_raw_rows(batch, mapping, response, rows)

        if mapping.name in {"Legal entities", "Natural persons"}:
            return self._persist_contacts(batch, mapping, rows)
        if mapping.name in {"Inventory", "Service export"}:
            return self._persist_products(batch, mapping, rows)
        if mapping.name in {"Product groups", "Person group export", "Return reason export"}:
            return self._persist_product_categories(batch, mapping, rows)
        if mapping.name == "Producers":
            return self._persist_producers(batch, mapping, rows)
        if mapping.name == "Workspaces":
            return self._persist_warehouses(batch, mapping, rows)
        if mapping.name == "Orders":
            return self._persist_sales(batch, mapping, rows)
        if mapping.name == "Client payments":
            return self._persist_payments(batch, mapping, rows)
        if mapping.name in {"Cash operations", "Bank statements"}:
            return self._persist_bank_operations(batch, mapping, rows)
        if mapping.name == "Visits":
            return self._persist_visits(batch, mapping, rows)
        if mapping.name == "Inventory balance":
            return self._persist_inventory_balance(batch, mapping, rows)
        if mapping.name in {
            "Returns",
            "Purchase export",
            "Receipts to warehouse export",
            "Return to suppliers export",
            "Stocktaking export",
            "Write-off export",
            "Cross-organizational movement export",
            "Internal movement export",
            "Logistics export",
            "Movement export",
            "Request export",
        }:
            return self._persist_business_documents(batch, mapping, rows)
        return self._persist_raw_rows(batch, mapping, rows)

    def _extract_response_rows(
        self,
        mapping: SmartUpMapping,
        response: dict[str, object] | list[object] | str,
        profile: SmartUpRequestProfile | None,
    ) -> list[dict[str, object]]:
        payload = self._coerce_response_payload(response)
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if not isinstance(payload, dict):
            return []

        candidate_keys: list[str] = []
        if profile is not None:
            candidate_keys.append(profile.response_key)
        candidate_keys.extend(
            [
                mapping.smartup_object,
                "data",
                "items",
                "rows",
                "result",
                "records",
                "list",
                "payload",
            ]
        )
        for key in candidate_keys:
            rows = self._coerce_rows_from_value(payload.get(key))
            if rows:
                return rows

        if self._looks_like_primary_row(mapping, payload):
            return [payload]

        rows = self._find_rows_recursively(payload)
        if rows:
            return rows

        if self._looks_like_data_row(payload):
            return [payload]
        return []

    def _looks_like_primary_row(
        self,
        mapping: SmartUpMapping,
        payload: dict[str, object],
    ) -> bool:
        row_keys = set(mapping.key_fields) | {
            "external_id",
            "code",
            "id",
            "person_id",
            "person_code",
            "deal_id",
            "return_id",
            "visit_id",
            "operation_id",
            "movement_id",
            "stocktaking_id",
            "writeoff_id",
            "purchase_id",
            "input_id",
            "cashin_id",
            "logistics_id",
            "request_id",
            "warehouse_code",
            "room_code",
            "product_code",
            "invoice_number",
        }
        return any(
            BaseSmartUpNormalizer._clean_text(payload.get(key)) is not None
            or payload.get(key) not in (None, "", [], {})
            for key in row_keys
        )

    def _coerce_response_payload(
        self,
        response: dict[str, object] | list[object] | str,
    ) -> object:
        if isinstance(response, str):
            parsed = SmartUpApiClient._parse_response_text(response, None)
            return parsed if parsed is not None else response
        if isinstance(response, dict):
            raw_text = response.get("_raw_text")
            if isinstance(raw_text, str):
                parsed = SmartUpApiClient._parse_response_text(
                    raw_text,
                    str(response.get("_content_type") or ""),
                )
                if parsed is not None:
                    return parsed
        return response

    @staticmethod
    def _coerce_rows_from_value(value: object) -> list[dict[str, object]]:
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict) and SmartUpHistoricalImportRunner._looks_like_data_row(value):
            return [value]
        return []

    def _find_rows_recursively(self, value: object) -> list[dict[str, object]]:
        if isinstance(value, list):
            rows = [row for row in value if isinstance(row, dict)]
            if rows:
                return rows
            for item in value:
                nested_rows = self._find_rows_recursively(item)
                if nested_rows:
                    return nested_rows
            return []
        if isinstance(value, dict):
            for nested in value.values():
                nested_rows = self._find_rows_recursively(nested)
                if nested_rows:
                    return nested_rows
        return []

    @staticmethod
    def _looks_like_data_row(value: dict[str, object]) -> bool:
        if not value:
            return False
        control_keys = {
            "_raw_text",
            "_content_type",
            "success",
            "status",
            "message",
            "error",
            "errors",
            "warning",
            "warnings",
            "code",
            "count",
            "total",
        }
        return any(key not in control_keys for key in value)

    def _persist_contacts(
        self,
        batch: IngestionBatch,
        mapping: SmartUpMapping,
        rows: list[object],
    ) -> tuple[int, str | None]:
        imported = 0
        last_external_id: str | None = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = self._build_contact_name(mapping.name, row)
            external_ref = self._row_external_id(row, mapping)
            contact = ContactProfile(
                contact_id=self._stable_entity_uuid("contact", external_ref or name),
                business_id=self.business_id,
                full_name=name,
                email=row.get("email"),
                phone=row.get("main_phone") or row.get("phone"),
                source="SmartUp",
                external_ref=external_ref,
                metadata=self._merge_context(row),
            )
            self.target.upsert_contact(contact)
            for key in (
                "person_id",
                "code",
                "external_id",
                "name",
                "short_name",
                "display_name",
                "person_name",
            ):
                value = row.get(key)
                if value is None:
                    continue
                text = str(value).strip()
                if text:
                    self.contact_index[text] = contact.contact_id
            if external_ref:
                self.contact_index[external_ref] = contact.contact_id
            customer = Customer(
                id=self._stable_entity_uuid("customer", external_ref or name),
                organization_id=self.business_id,
                source_external_id=external_ref or name,
                source_filial_id=self.smartup_filial_id,
                source_payload_id=self._row_external_id(row, mapping),
                name=name,
                display_name=self._pick_text(row, "short_name", "name"),
                phone=self._pick_text(row, "main_phone", "phone"),
                email=self._pick_text(row, "email"),
                metadata=self._merge_context(
                    {
                        **row,
                        "smartup_entity": mapping.name,
                        "customer_kind": (
                            "legal_entity" if mapping.name == "Legal entities" else "natural_person"
                        ),
                    },
                ),
            )
            self.target.upsert_customer(customer)
            self.target.ingest_record(
                self._make_record(batch, mapping, row, self.business_id, CoreRecordKind.CUSTOMER),
            )
            last_external_id = external_ref or last_external_id
            imported += 1
        return imported, last_external_id

    def _persist_products(
        self,
        batch: IngestionBatch,
        mapping: SmartUpMapping,
        rows: list[object],
    ) -> tuple[int, str | None]:
        imported = 0
        last_external_id: str | None = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            external_ref = self._row_external_id(row, mapping)
            name = self._pick_text(row, "name", "short_name", "code") or "Unknown"
            product = Product(
                id=self._stable_entity_uuid("product", external_ref or name),
                organization_id=self.business_id,
                source_external_id=external_ref or name,
                source_filial_id=self.smartup_filial_id,
                source_payload_id=self._pick_text(row, "id", "product_id", "service_id"),
                name=name,
                category_external_id=self._pick_text(
                    row,
                    "product_group_code",
                    "group_code",
                    "groups",
                    "producer_code",
                ),
                sku=self._pick_text(row, "code", "product_code", "service_code", "barcode"),
                unit=self._pick_text(row, "measure_code", "unit_code", "unit"),
                metadata=self._merge_context(row),
            )
            self.target.upsert_product(product)
            self.target.ingest_record(
                self._make_record(batch, mapping, row, self.business_id, CoreRecordKind.EVENT),
            )
            last_external_id = external_ref or last_external_id
            imported += 1
        return imported, last_external_id

    def _persist_product_categories(
        self,
        batch: IngestionBatch,
        mapping: SmartUpMapping,
        rows: list[object],
    ) -> tuple[int, str | None]:
        imported = 0
        last_external_id: str | None = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            external_ref = self._row_external_id(row, mapping)
            name = self._pick_text(row, "name", "short_name", "code") or "Unknown"
            category = ProductCategory(
                id=self._stable_entity_uuid("product-category", external_ref or name),
                organization_id=self.business_id,
                source_external_id=external_ref or name,
                source_filial_id=self.smartup_filial_id,
                source_payload_id=self._pick_text(
                    row,
                    "id",
                    "product_group_id",
                    "person_group_id",
                    "return_reason_id",
                ),
                name=name,
                parent_external_id=self._pick_text(row, "parent_code", "parent_group_code"),
                metadata=self._merge_context(row),
            )
            self.target.upsert_product_category(category)
            self.target.ingest_record(
                self._make_record(batch, mapping, row, self.business_id, CoreRecordKind.EVENT),
            )
            last_external_id = external_ref or last_external_id
            imported += 1
        return imported, last_external_id

    def _persist_producers(
        self,
        batch: IngestionBatch,
        mapping: SmartUpMapping,
        rows: list[object],
    ) -> tuple[int, str | None]:
        imported = 0
        last_external_id: str | None = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            external_ref = self._row_external_id(row, mapping)
            name = self._pick_text(row, "name", "short_name", "code") or "Unknown"
            customer = Customer(
                id=self._stable_entity_uuid("customer", external_ref or name),
                organization_id=self.business_id,
                source_external_id=external_ref or name,
                source_filial_id=self.smartup_filial_id,
                source_payload_id=self._pick_text(row, "id", "person_id"),
                name=name,
                display_name=self._pick_text(row, "short_name", "name"),
                phone=self._pick_text(row, "main_phone", "phone"),
                email=self._pick_text(row, "email"),
                metadata=self._merge_context(
                    {
                        **row,
                        "smartup_entity": mapping.name,
                        "party_kind": "producer",
                    },
                ),
            )
            self.target.upsert_customer(customer)
            self.target.ingest_record(
                self._make_record(batch, mapping, row, self.business_id, CoreRecordKind.CUSTOMER),
            )
            last_external_id = external_ref or last_external_id
            imported += 1
        return imported, last_external_id

    def _persist_warehouses(
        self,
        batch: IngestionBatch,
        mapping: SmartUpMapping,
        rows: list[object],
    ) -> tuple[int, str | None]:
        imported = 0
        last_external_id: str | None = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            external_ref = self._row_external_id(row, mapping)
            name = self._pick_text(row, "room_name", "name", "room_code") or "Unknown"
            warehouse = Warehouse(
                id=self._stable_entity_uuid("warehouse", external_ref or name),
                organization_id=self.business_id,
                source_external_id=external_ref or name,
                source_filial_id=self.smartup_filial_id,
                source_payload_id=self._pick_text(row, "id", "room_id", "room_code"),
                name=name,
                code=self._pick_text(row, "room_code", "code"),
                metadata=self._merge_context(row),
            )
            self.target.upsert_warehouse(warehouse)
            self.target.ingest_record(
                self._make_record(batch, mapping, row, self.business_id, CoreRecordKind.EVENT),
            )
            last_external_id = external_ref or last_external_id
            imported += 1
        return imported, last_external_id

    def _persist_sales(
        self,
        batch: IngestionBatch,
        mapping: SmartUpMapping,
        rows: list[object],
    ) -> tuple[int, str | None]:
        imported = 0
        last_external_id: str | None = None
        sale_counts = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0}
        sale_item_counts = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0}
        for row in rows:
            if not isinstance(row, dict):
                continue
            amount = self._to_decimal(row.get("total_amount") or row.get("amount"))
            contact_ref = str(
                row.get("person_code")
                or row.get("person_id")
                or row.get("person_name")
                or row.get("external_customer_id")
                or "",
            )
            external_ref = self._row_external_id(row, mapping)
            sale = SaleRecord(
                sale_id=self._stable_entity_uuid("sale", external_ref or contact_ref or "sale"),
                business_id=self.business_id,
                contact_id=self.contact_index.get(contact_ref) if contact_ref else None,
                external_ref=external_ref,
                amount=amount,
                currency=str(row.get("currency_code") or row.get("currency") or "USD"),
                stage=SaleStage.WON
                if str(row.get("status") or "").upper() in {"B#V", "A"}
                else SaleStage.LEAD,
                occurred_at=self._parse_datetime(
                    row.get("deal_time")
                    or row.get("delivery_date")
                    or row.get("created_on")
                    or row.get("occurred_at"),
                ),
                source="SmartUp",
                metadata=self._merge_context(row),
            )
            self.target.upsert_sale(sale)
            normalized_sale = Sale(
                id=self._stable_entity_uuid(
                    "normalized-sale",
                    external_ref or contact_ref or "sale",
                ),
                organization_id=self.business_id,
                source_external_id=external_ref or contact_ref or "sale",
                source_filial_id=self.smartup_filial_id,
                source_payload_id=self._row_external_id(row, mapping),
                customer_external_id=contact_ref or None,
                sale_number=self._pick_text(row, "deal_id", "external_id", "code"),
                amount=amount,
                currency=str(row.get("currency_code") or row.get("currency") or "USD"),
                status="won" if sale.stage == SaleStage.WON else "lead",
                sale_at=sale.occurred_at,
                closed_at=sale.occurred_at if sale.stage == SaleStage.WON else None,
                metadata=self._merge_context(row),
            )
            existing_sale = self.target.get_sale_v2(normalized_sale.id)
            if existing_sale is None:
                sale_counts["inserted"] += 1
            elif CoreUpsertService._comparison_payload(
                existing_sale
            ) == CoreUpsertService._comparison_payload(normalized_sale):
                sale_counts["skipped"] += 1
            else:
                sale_counts["updated"] += 1
            self.target.upsert_sale_v2(normalized_sale)

            line_items = row.get("order_products") or row.get("return_products") or row.get("items")
            is_return = isinstance(row.get("return_products"), list)
            sale_external_id = external_ref or contact_ref or "sale"
            self.target.delete_sale_items_for_sale_external_id(self.business_id, sale_external_id)
            if isinstance(line_items, list):
                for index, item in enumerate(line_items, start=1):
                    if not isinstance(item, dict):
                        continue
                    item_external_ref = f"{sale_external_id}:{index}"
                    item_payload_id = self._pick_text(
                        item,
                        "product_code",
                        "inventory_code",
                        "code",
                        "order_item_id",
                        "return_product_id",
                    )
                    item_id = self._stable_entity_uuid("sale-item", item_external_ref)
                    existing_item = self.target.get_sale_item(item_id)
                    sale_item = SaleItem(
                        id=item_id,
                        organization_id=self.business_id,
                        source_system="smartup",
                        source_external_id=item_external_ref,
                        source_filial_id=self.smartup_filial_id,
                        source_payload_id=self._pick_text(
                            item,
                            "order_item_id",
                            "return_product_id",
                            "line_id",
                            "external_id",
                            "product_code",
                        ),
                        source_created_at=None,
                        source_updated_at=None,
                        sale_id=normalized_sale.id,
                        sale_external_id=sale_external_id,
                        product_external_id=item_payload_id,
                        quantity=self._sale_item_quantity(item, allow_return_quant=is_return),
                        unit_price=self._to_decimal(
                            item.get("price") or item.get("product_price"),
                        ),
                        amount=self._to_decimal(
                            item.get("amount")
                            or item.get("sold_amount")
                            or item.get("total_amount"),
                        ),
                        currency=str(row.get("currency_code") or row.get("currency") or "USD"),
                        metadata=self._merge_context({**item, "source_entity": mapping.name}),
                    )
                    if existing_item is None:
                        sale_item_counts["inserted"] += 1
                    elif CoreUpsertService._comparison_payload(
                        existing_item
                    ) == CoreUpsertService._comparison_payload(sale_item):
                        sale_item_counts["skipped"] += 1
                    else:
                        sale_item_counts["updated"] += 1
                    self.target.upsert_sale_item(sale_item)
            self.target.ingest_record(
                self._make_record(batch, mapping, row, self.business_id, CoreRecordKind.SALE),
            )
            last_external_id = external_ref or last_external_id
            imported += 1
        if isinstance(batch.metadata, dict):
            batch.metadata["result_counts"] = sale_counts
            batch.metadata["sale_item_result_counts"] = sale_item_counts
        return imported, last_external_id

    def _sale_item_quantity(
        self,
        item: dict[str, object],
        *,
        allow_return_quant: bool = False,
    ) -> Decimal:
        details = item.get("details")
        if isinstance(details, list):
            sold_quant_total = Decimal("0")
            sold_quant_found = False
            for detail in details:
                if not isinstance(detail, dict):
                    continue
                if "sold_quant" not in detail:
                    continue
                sold_quant_total += self._to_decimal(detail.get("sold_quant"))
                sold_quant_found = True
            if sold_quant_found:
                return sold_quant_total

        if item.get("order_quant") is not None:
            return self._to_decimal(item.get("order_quant"))
        if item.get("quantity") is not None:
            return self._to_decimal(item.get("quantity"))
        if allow_return_quant and item.get("return_quant") is not None:
            return self._to_decimal(item.get("return_quant"))
        return Decimal("0")

    def _persist_payments(
        self,
        batch: IngestionBatch,
        mapping: SmartUpMapping,
        rows: list[object],
    ) -> tuple[int, str | None]:
        imported = 0
        last_external_id: str | None = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            external_ref = self._row_external_id(row, mapping)
            entry = FinanceEntry(
                entry_id=self._stable_entity_uuid("finance", external_ref or "entry"),
                business_id=self.business_id,
                external_ref=external_ref,
                entry_type=FinanceEntryType.REVENUE
                if "cashin" in mapping.name.lower()
                else FinanceEntryType.EXPENSE,
                category=mapping.name,
                amount=self._to_decimal(row.get("amount")),
                currency=str(row.get("currency_code") or row.get("currency") or "USD"),
                occurred_at=self._parse_datetime(
                    row.get("cashin_date") or row.get("operation_date") or row.get("created_on")
                ),
                source="SmartUp",
                metadata=self._merge_context(row),
            )
            self.target.upsert_finance_entry(entry)
            payment = Payment(
                id=self._stable_entity_uuid("payment", external_ref or "payment"),
                organization_id=self.business_id,
                source_external_id=external_ref or "payment",
                source_filial_id=self.smartup_filial_id,
                source_payload_id=self._row_external_id(row, mapping),
                sale_external_id=self._pick_text(row, "deal_id", "order_id", "sale_id"),
                amount=self._to_decimal(row.get("amount")),
                currency=str(row.get("currency_code") or row.get("currency") or "USD"),
                paid_at=self._parse_datetime(
                    row.get("cashin_date") or row.get("payment_date") or row.get("created_on")
                ),
                method=self._pick_text(row, "payment_type", "method", "cashbox_code"),
                metadata=self._merge_context(row),
            )
            self.target.upsert_payment(payment)
            self.target.ingest_record(
                self._make_record(batch, mapping, row, self.business_id, CoreRecordKind.FINANCE),
            )
            last_external_id = external_ref or last_external_id
            imported += 1
        return imported, last_external_id

    def _persist_bank_operations(
        self,
        batch: IngestionBatch,
        mapping: SmartUpMapping,
        rows: list[object],
    ) -> tuple[int, str | None]:
        imported = 0
        last_external_id: str | None = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            external_ref = self._row_external_id(row, mapping)
            entry = FinanceEntry(
                entry_id=self._stable_entity_uuid("finance", external_ref or "entry"),
                business_id=self.business_id,
                external_ref=external_ref,
                entry_type=FinanceEntryType.REVENUE
                if "bank" in mapping.name.lower()
                else FinanceEntryType.EXPENSE,
                category=mapping.name,
                amount=self._to_decimal(row.get("amount")),
                currency=str(row.get("currency_code") or row.get("currency") or "USD"),
                occurred_at=self._parse_datetime(
                    row.get("operation_date") or row.get("created_on") or row.get("date")
                ),
                source="SmartUp",
                metadata=self._merge_context(row),
            )
            self.target.upsert_finance_entry(entry)
            bank_operation = BankOperation(
                id=self._stable_entity_uuid("bank-operation", external_ref or "operation"),
                organization_id=self.business_id,
                source_external_id=external_ref or "operation",
                source_filial_id=self.smartup_filial_id,
                source_payload_id=self._row_external_id(row, mapping),
                amount=self._to_decimal(row.get("amount")),
                currency=str(row.get("currency_code") or row.get("currency") or "USD"),
                occurred_at=self._parse_datetime(
                    row.get("operation_date") or row.get("created_on") or row.get("date")
                ),
                operation_type=mapping.name.lower().replace(" ", "_"),
                description=self._pick_text(row, "description", "comment", "name"),
                metadata=self._merge_context(row),
            )
            self.target.upsert_bank_operation(bank_operation)
            self.target.ingest_record(
                self._make_record(batch, mapping, row, self.business_id, CoreRecordKind.FINANCE),
            )
            last_external_id = external_ref or last_external_id
            imported += 1
        return imported, last_external_id

    def _persist_visits(
        self,
        batch: IngestionBatch,
        mapping: SmartUpMapping,
        rows: list[object],
    ) -> tuple[int, str | None]:
        imported = 0
        last_external_id: str | None = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            visited_at = self._parse_datetime(
                row.get("visit_date") or row.get("created_on") or row.get("occurred_at"),
            )
            visit = Visit(
                id=self._stable_entity_uuid(
                    "visit",
                    self._row_external_id(row, mapping) or visited_at.isoformat(),
                ),
                organization_id=self.business_id,
                source_external_id=self._row_external_id(row, mapping) or visited_at.isoformat(),
                source_filial_id=self.smartup_filial_id,
                source_payload_id=self._row_external_id(row, mapping),
                customer_external_id=self._pick_text(
                    row,
                    "person_code",
                    "customer_code",
                    "external_customer_id",
                ),
                visited_at=visited_at,
                status=self._pick_text(row, "status", "state"),
                metadata=self._merge_context(row),
            )
            self.target.upsert_visit(visit)
            last_external_id = self._row_external_id(row, mapping) or last_external_id
            self.target.ingest_record(
                self._make_record(batch, mapping, row, self.business_id, CoreRecordKind.EVENT),
            )
            imported += 1
        return imported, last_external_id

    def _persist_inventory_balance(
        self,
        batch: IngestionBatch,
        mapping: SmartUpMapping,
        rows: list[object],
    ) -> tuple[int, str | None]:
        imported = 0
        last_external_id: str | None = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            warehouse_external_id = str(
                row.get("warehouse_code")
                or row.get("warehouse_external_id")
                or row.get("warehouse")
                or "",
            )
            product_external_id = str(
                row.get("product_code")
                or row.get("product_external_id")
                or row.get("product")
                or "",
            )
            snapshot_date = self._parse_datetime(
                row.get("date") or row.get("snapshot_date") or row.get("created_on"),
            )
            snapshot = InventorySnapshot(
                id=self._stable_entity_uuid(
                    "inventory-snapshot",
                    f"{warehouse_external_id}:{product_external_id}:{snapshot_date.isoformat()}",
                ),
                organization_id=self.business_id,
                warehouse_external_id=warehouse_external_id,
                product_external_id=product_external_id,
                quantity=self._to_decimal(row.get("quantity")),
                snapshot_date=snapshot_date,
                metadata=self._merge_context(row),
            )
            self.target.upsert_inventory_snapshot(snapshot)
            inventory_balance = InventoryBalance(
                id=self._stable_entity_uuid(
                    "inventory-balance",
                    f"{warehouse_external_id}:{product_external_id}:{snapshot_date.isoformat()}",
                ),
                organization_id=self.business_id,
                source_external_id=f"{warehouse_external_id}:{product_external_id}",
                source_filial_id=self.smartup_filial_id,
                source_payload_id=self._row_external_id(row, mapping),
                warehouse_external_id=warehouse_external_id,
                product_external_id=product_external_id,
                quantity=self._to_decimal(row.get("quantity")),
                balance_at=snapshot_date,
                metadata=self._merge_context(row),
            )
            self.target.upsert_inventory_balance(inventory_balance)
            self.target.ingest_record(
                self._make_record(batch, mapping, row, self.business_id, CoreRecordKind.EVENT),
            )
            last_external_id = f"{warehouse_external_id}:{product_external_id}" or last_external_id
            imported += 1
        return imported, last_external_id

    def _persist_business_documents(
        self,
        batch: IngestionBatch,
        mapping: SmartUpMapping,
        rows: list[object],
    ) -> tuple[int, str | None]:
        imported = 0
        last_external_id: str | None = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            context = build_business_document_models(
                organization_id=self.business_id,
                filial_id=self.smartup_filial_id or "",
                source_system="smartup",
                source_endpoint=mapping.smartup_endpoint,
                entity_type=self._raw_entity_type(mapping),
                row=row,
                imported_at=datetime.now(UTC),
            )
            if context is None:
                self.target.ingest_record(
                    self._make_record(batch, mapping, row, self.business_id, CoreRecordKind.EVENT),
                )
                imported += 1
                continue
            document = context.document
            self.target.upsert_business_document(document)
            for item in context.items:
                self.target.upsert_business_document_item(item)
            self.target.ingest_record(
                self._make_record(batch, mapping, row, self.business_id, CoreRecordKind.DOCUMENT),
            )
            last_external_id = context.source_external_id or last_external_id
            imported += 1
        return imported, last_external_id

    def _persist_raw_rows(
        self,
        batch: IngestionBatch,
        mapping: SmartUpMapping,
        rows: list[object],
    ) -> tuple[int, str | None]:
        imported = 0
        last_external_id: str | None = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            last_external_id = self._row_external_id(row, mapping) or last_external_id
            self.target.ingest_record(
                self._make_record(batch, mapping, row, self.business_id, CoreRecordKind.EVENT),
            )
            imported += 1
        return imported, last_external_id

    def _store_raw_rows(
        self,
        batch: IngestionBatch,
        mapping: SmartUpMapping,
        response: object,
        rows: list[object],
    ) -> None:
        for row in rows:
            if not isinstance(row, dict):
                continue
            raw_record = self._build_raw_record(
                batch=batch,
                mapping=mapping,
                row=row,
                response_envelope=response,
            )
            self.target.upsert_smartup_raw_record(raw_record)

    def _make_record(
        self,
        batch: IngestionBatch,
        mapping: SmartUpMapping,
        row: dict[str, object],
        business_id: UUID,
        kind: CoreRecordKind,
    ) -> CoreRecord:
        external_ref = self._row_external_id(row, mapping) or ""
        return CoreRecord(
            record_id=self._stable_entity_uuid(
                f"record:{kind.value}", external_ref or str(batch.batch_id)
            ),
            business_id=business_id,
            source=mapping.name,
            source_type=DataSourceType.IMPORT,
            kind=kind,
            payload=row,
            occurred_at=self._parse_datetime(
                row.get("created_on")
                or row.get("modified_on")
                or row.get("delivery_date")
                or row.get("deal_time")
                or row.get("occurred_at")
            ),
            ingested_at=datetime.now(UTC),
            metadata=self._merge_context(
                {"batch_id": str(batch.batch_id), "endpoint": mapping.smartup_endpoint}
            ),
        )

    def _build_raw_record(
        self,
        *,
        batch: IngestionBatch,
        mapping: SmartUpMapping,
        row: dict[str, object],
        response_envelope: object,
    ) -> SmartUpRawRecord:
        external_id = self._row_external_id(row, mapping)
        sanitized_row = self._sanitize_payload(row)
        sanitized_envelope = self._sanitize_payload(response_envelope)
        checksum = self._checksum(sanitized_row)
        record_id = uuid5(
            NAMESPACE_URL,
            (
                f"smartup:raw:{self.business_id}:{self._raw_entity_type(mapping)}:"
                f"{external_id or checksum}:{checksum}"
            ),
        )
        return SmartUpRawRecord(
            id=record_id,
            organization_id=self.business_id,
            filial_id=self.smartup_filial_id or "",
            request_filial_id=self._request_filial_id(batch),
            request_company_id=self._request_company_id(batch),
            request_project_code=self._request_project_code(batch),
            entity_type=self._raw_entity_type(mapping),
            external_id=external_id,
            source_endpoint=mapping.smartup_endpoint,
            request_payload=self._merge_context(batch.metadata.get("payload", {})),
            response_payload=sanitized_row,
            response_envelope=sanitized_envelope,
            response_filial_id=(
                self._extract_filial_id(row)
                or self._extract_filial_id(response_envelope)
                or self.smartup_filial_id
            ),
            source_created_at=self._parse_datetime(
                row.get("created_on")
                or row.get("created_at")
                or row.get("created_date")
                or row.get("deal_time")
                or row.get("occurred_at")
            ),
            source_updated_at=self._parse_datetime(
                row.get("modified_on")
                or row.get("updated_at")
                or row.get("modified_at")
                or row.get("deal_time")
            ),
            imported_at=datetime.now(UTC),
            batch_id=batch.batch_id,
            checksum=checksum,
            processing_status=SmartUpRawRecordStatus.PENDING,
        )

    def _record_error(
        self,
        batch: IngestionBatch,
        mapping: SmartUpMapping,
        index: int,
        message: str,
        row: dict[str, object],
    ) -> None:
        self.target.record_ingestion_error(
            IngestionError(
                batch_id=batch.batch_id,
                source_row_key=str(index),
                entity_type=mapping.target_entity,
                error_code="validation_error",
                error_message=message,
                raw_payload=row,
                metadata={"mapping": mapping.name},
            ),
        )

    def _merge_context(self, payload: dict[str, object]) -> dict[str, object]:
        merged = dict(payload)
        merged.setdefault("source_system", "smartup")
        merged.setdefault("smartup_filial_id", self.smartup_filial_id)
        merged.setdefault("request_filial_id", self.smartup_filial_id)
        merged.setdefault("request_company_id", self._client_setting("company_id"))
        merged.setdefault("request_project_code", self._client_setting("project_code"))
        return merged

    def _request_context(self) -> dict[str, object | None]:
        return {
            "request_filial_id": self.smartup_filial_id,
            "request_company_id": self._client_setting("company_id"),
            "request_project_code": self._client_setting("project_code"),
        }

    def _client_setting(self, key: str) -> str | None:
        settings = getattr(self.client, "settings", None)
        if settings is None:
            return None
        value = getattr(settings, key, None)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _request_filial_id(self, batch: IngestionBatch) -> str | None:
        metadata = batch.metadata if isinstance(batch.metadata, dict) else {}
        value = metadata.get("request_filial_id") or metadata.get("filial_id")
        if value is None:
            return self.smartup_filial_id
        text = str(value).strip()
        return text or self.smartup_filial_id

    def _request_company_id(self, batch: IngestionBatch) -> str | None:
        metadata = batch.metadata if isinstance(batch.metadata, dict) else {}
        value = metadata.get("request_company_id")
        if value is None:
            return self._client_setting("company_id")
        text = str(value).strip()
        return text or self._client_setting("company_id")

    def _request_project_code(self, batch: IngestionBatch) -> str | None:
        metadata = batch.metadata if isinstance(batch.metadata, dict) else {}
        value = metadata.get("request_project_code")
        if value is None:
            return self._client_setting("project_code")
        text = str(value).strip()
        return text or self._client_setting("project_code")

    @staticmethod
    def _parse_datetime(value: object | None) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(value, fmt).replace(tzinfo=UTC)
                except ValueError:
                    continue
        return datetime.now(UTC)

    @staticmethod
    def _to_decimal(value: object | None) -> Decimal:
        if isinstance(value, Decimal):
            return value
        if value is None:
            return Decimal("0")
        return Decimal(str(value))

    @staticmethod
    def _build_contact_name(mapping_name: str, row: dict[str, object]) -> str:
        if mapping_name == "Natural persons":
            parts = [
                str(row.get("first_name") or "").strip(),
                str(row.get("last_name") or "").strip(),
                str(row.get("middle_name") or "").strip(),
            ]
            name = " ".join(part for part in parts if part)
            if name:
                return name
        return str(
            row.get("name")
            or row.get("short_name")
            or row.get("person_name")
            or row.get("code")
            or row.get("person_id")
            or "Unknown",
        )

    @staticmethod
    def _first_text_value(value: object | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if isinstance(value, dict):
            for key in ("name", "short_name", "code", "value", "id"):
                text = SmartUpHistoricalImportRunner._first_text_value(value.get(key))
                if text:
                    return text
            for nested in value.values():
                text = SmartUpHistoricalImportRunner._first_text_value(nested)
                if text:
                    return text
            return None
        if isinstance(value, (list, tuple, set)):
            for item in value:
                text = SmartUpHistoricalImportRunner._first_text_value(item)
                if text:
                    return text
            return None
        text = str(value).strip()
        return text or None

    def _pick_text(self, row: dict[str, object], *keys: str) -> str | None:
        for key in keys:
            text = self._first_text_value(row.get(key))
            if text:
                return text
        return None

    def _get_mapping(self, mapping_name: str) -> SmartUpMapping | None:
        return next(
            (mapping for mapping in self.connector.mappings if mapping.name == mapping_name), None
        )

    def _batch_name(
        self,
        task,
        window_start: datetime | None,
        window_end: datetime | None,
        migration_mode: SmartUpMigrationMode,
    ) -> str:
        label = f"{task.mapping_name} {migration_mode.value}"
        if window_start is not None and window_end is not None:
            return f"{label} {window_start.date().isoformat()}..{window_end.date().isoformat()}"
        return label

    def _stable_batch_uuid(
        self,
        mapping: SmartUpMapping,
        migration_mode: SmartUpMigrationMode,
        window_start: datetime | None,
        window_end: datetime | None,
    ) -> UUID:
        window_key = (
            f"{window_start.isoformat()}:{window_end.isoformat()}"
            if window_start is not None and window_end is not None
            else "snapshot"
        )
        return uuid5(
            NAMESPACE_URL,
            f"smartup:batch:{self.business_id}:{mapping.name}:{migration_mode.value}:{window_key}",
        )

    def _stable_checkpoint_uuid(
        self,
        mapping: SmartUpMapping,
        migration_mode: SmartUpMigrationMode,
    ) -> UUID:
        return uuid5(
            NAMESPACE_URL,
            f"smartup:checkpoint:{self.business_id}:{mapping.name}:{migration_mode.value}",
        )

    def _stable_entity_uuid(self, scope: str, external_ref: str | None) -> UUID:
        reference = external_ref or "missing"
        filial_ref = self.smartup_filial_id or self.business_external_ref or "smartup"
        return uuid5(
            NAMESPACE_URL,
            f"smartup:{scope}:{self.business_id}:{filial_ref}:{reference}",
        )

    def _row_external_id(self, row: dict[str, object], mapping: SmartUpMapping) -> str | None:
        candidates = (
            *mapping.key_fields,
            "external_id",
            "code",
            "id",
            "person_id",
            "purchase_id",
            "return_id",
            "receipt_id",
            "stocktaking_id",
            "writeoff_id",
            "operation_id",
            "deal_id",
            "logistics_id",
            "movement_id",
            "request_id",
            "room_code",
            "warehouse_code",
            "product_code",
            "invoice_number",
        )
        for key in candidates:
            value = row.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    @staticmethod
    def _checksum(value: object) -> str:
        canonical = dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _sanitize_payload(value: object | None) -> object | None:
        if value is None:
            return None
        if isinstance(value, dict):
            return {
                key: SmartUpHistoricalImportRunner._sanitize_payload(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [SmartUpHistoricalImportRunner._sanitize_payload(item) for item in value]
        return value

    @staticmethod
    def _format_smartup_date(value: datetime) -> str:
        return value.date().strftime("%d.%m.%Y")

    @staticmethod
    def _raw_entity_type(mapping: SmartUpMapping) -> str:
        if mapping.name in {"Legal entities", "Natural persons"}:
            return "customers"
        if mapping.name in {"Inventory", "Service export", "Producers"}:
            return "products"
        if mapping.name in {"Product groups", "Person group export", "Return reason export"}:
            return "product_categories"
        if mapping.name == "Workspaces":
            return "warehouses"
        if mapping.name == "Orders":
            return "sales"
        if mapping.name == "Returns":
            return "returns"
        if mapping.name == "Purchase export":
            return "purchases"
        if mapping.name == "Receipts to warehouse export":
            return "warehouse_receipts"
        if mapping.name == "Return to suppliers export":
            return "return_to_suppliers"
        if mapping.name == "Stocktaking export":
            return "stocktakings"
        if mapping.name == "Write-off export":
            return "write_offs"
        if mapping.name == "Cross-organizational movement export":
            return "cross_organizational_movements"
        if mapping.name == "Internal movement export":
            return "internal_movements"
        if mapping.name == "Logistics export":
            return "logistics"
        if mapping.name == "Movement export":
            return "equipment_movements"
        if mapping.name == "Request export":
            return "equipment_requests"
        if mapping.name in {"Payments from clients", "Client payments"}:
            return "payments"
        if mapping.name == "Visits":
            return "visits"
        if mapping.name == "Inventory balance":
            return "inventory_balances"
        if mapping.name in {"Cash operations", "Bank statements"}:
            return "bank_operations"
        return mapping.target_table or mapping.name.lower().replace(" ", "_")

    @staticmethod
    def _clean_text(value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


def _stable_source_system_uuid(business_id: UUID, external_ref: str | None) -> UUID:
    reference = external_ref or "smartup"
    return uuid5(NAMESPACE_URL, f"smartup:source-system:{business_id}:{reference}")
