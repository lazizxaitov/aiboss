"""SmartUp organization CRUD, connection checks, and migration orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from time import perf_counter
from threading import Lock, Thread
from typing import Literal
from uuid import UUID, uuid4

import httpx
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.entities import AppSetting, BusinessIdentity
from app.core.data_layer.migrations import SmartUpCanonicalV2FoundationService
from app.integrations.smartup.client import SmartUpApiClient
from app.integrations.smartup.connector import (
    MAX_SMARTUP_HISTORY_WINDOW_DAYS,
    SmartUpConnector,
)
from app.integrations.smartup.filial_codes import (
    discover_verified_filial_code_from_raw_records,
    mark_verified_filial_code,
    resolve_filial_code,
)
from app.integrations.smartup.history import SmartUpHistoricalImportRunner
from app.integrations.smartup.mapping import SMARTUP_CORE_MAPPING_V1
from app.integrations.smartup.models import (
    SMARTUP_INTEGRATION_UUID,
    SmartUpMigrationMode,
    SmartUpMigrationRun,
    SmartUpMigrationStatus,
    SmartUpOrganization,
)
from app.integrations.smartup.settings import SmartUpSettings


class SmartUpAuthPayload(BaseModel):
    """Connection credentials shared by the SmartUp integration."""

    base_url: str = Field(
        default="https://smartup.online",
        validation_alias=AliasChoices("base_url", "baseUrl"),
    )
    username: str = Field(
        default="",
        validation_alias=AliasChoices("username", "login"),
    )
    password: str = Field(
        default="",
        validation_alias=AliasChoices("password", "pass"),
    )
    project_code: str | None = Field(
        default=None,
        validation_alias=AliasChoices("project_code", "projectCode"),
    )
    filial_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("filial_id", "filialId"),
    )
    timeout_seconds: float = Field(
        default=30.0,
        validation_alias=AliasChoices("timeout_seconds", "timeoutSeconds"),
    )
    migration_mode: SmartUpMigrationMode = Field(
        default=SmartUpMigrationMode.FULL_BACKFILL,
        validation_alias=AliasChoices("migration_mode", "migrationMode"),
    )
    datasets: list[str] | None = Field(default=None, description="Internal dataset groups to sync")
    history_start: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("history_start", "historyStart"),
    )
    history_end: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("history_end", "historyEnd"),
    )


SmartUpAccessPayload = SmartUpAuthPayload

_SMARTUP_CREDENTIALS_SETTING_PREFIX = "smartup:organization_credentials:"


@dataclass(frozen=True, slots=True)
class SmartUpResolvedAuth:
    """Resolved SmartUp credentials for a single organization."""

    payload: SmartUpAuthPayload
    source: Literal["payload", "organization_settings", "global", "missing"]
    credentials_available: bool
    client: SmartUpApiClient | None = None


class SmartUpMigrationOrganizationInput(BaseModel):
    """Legacy per-organization request item for history migrations."""

    name: str
    company_id: str = "11300"
    filial_id: str
    filial_code: str | None = None
    project_code: str = "trade"
    selected: bool = True


class SmartUpHistoryMigrationRequest(SmartUpAuthPayload):
    """Legacy history migration request body."""

    history_start: datetime = Field(
        default_factory=lambda: datetime.now(UTC) - timedelta(days=7),
    )
    history_end: datetime | None = None
    chunk_days: int = 7
    organizations: list[SmartUpMigrationOrganizationInput] = Field(default_factory=list)


class SmartUpOrganizationCreateRequest(BaseModel):
    """Payload used to create a SmartUp organization."""

    name: str
    company_id: str = "11300"
    filial_id: str
    filial_code: str | None = None
    project_code: str = "trade"
    is_active: bool = True
    sort_order: int = 0

    model_config = ConfigDict(extra="ignore")


class SmartUpOrganizationUpdateRequest(BaseModel):
    """Payload used to patch a SmartUp organization."""

    name: str | None = None
    company_id: str | None = None
    filial_id: str | None = None
    filial_code: str | None = None
    project_code: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None

    model_config = ConfigDict(extra="ignore")


class SmartUpConnectionCheckResponse(BaseModel):
    """Structured connection probe response."""

    connected: bool
    code: str | None = None
    message: str
    upstream_status: int | None = None
    upstream_response: str = ""
    requested_url: str
    organization_id: UUID | None = None
    organization_name: str | None = None
    company_id: str | None = None
    filial_id: str | None = None
    project_code: str | None = None
    ok: bool | None = None
    status: str | None = None
    latency_ms: float | None = None


class SmartUpMigrationOrganizationResult(BaseModel):
    """Aggregate migration result for one organization."""

    organization_id: UUID
    name: str
    filial_id: str
    company_id: str | None = None
    project_code: str | None = None
    summary: SmartUpMigrationSummary
    counters: dict[str, int]
    runs: list[SmartUpMigrationRun] = Field(default_factory=list)


class SmartUpMigrationSummary(BaseModel):
    """Human-readable totals for a migration run."""

    organizations: int = 0
    businesses: int = 0
    source_systems: int = 0
    contacts: int = 0
    sales: int = 0
    marketing_activities: int = 0
    finance_entries: int = 0
    records: int = 0
    batches: int = 0
    errors: int = 0


class SmartUpBatchImportError(BaseModel):
    """Failure details for one ingestion batch."""

    organization_id: UUID
    organization_name: str
    business_id: UUID
    batch_id: UUID
    batch_name: str
    batch_status: str
    endpoint: str | None = None
    source_endpoint: str | None = None
    requested_url: str | None = None
    payload: dict[str, object] | None = None
    entity_type: str | None = None
    error_code: str
    error_message: str


class SmartUpMigrationAllResponse(BaseModel):
    """Response returned after iterating all active SmartUp organizations."""

    status: Literal["completed", "completed_with_errors"] = "completed"
    message: str
    organizations_count: int
    organizations: list[SmartUpMigrationOrganizationResult] = Field(default_factory=list)
    runs: list[SmartUpMigrationRun] = Field(default_factory=list)
    summary: SmartUpMigrationSummary = Field(default_factory=SmartUpMigrationSummary)
    counters: dict[str, int] = Field(default_factory=dict)
    batch_errors: list[SmartUpBatchImportError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    history_start: datetime | None = None
    history_end: datetime | None = None


class SmartUpMigrationJobResponse(BaseModel):
    """Background migration job state."""

    job_id: UUID
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    message: str
    migration_mode: SmartUpMigrationMode = SmartUpMigrationMode.FULL_BACKFILL
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress_organizations: int = 0
    total_organizations: int = 0
    current_organization_id: UUID | None = None
    current_organization_name: str | None = None
    current_entity_type: str | None = None
    current_entity_label: str | None = None
    current_phase: str | None = None
    result: SmartUpMigrationAllResponse | None = None
    error: str | None = None


class SmartUpResetResponse(BaseModel):
    """Summary returned after clearing imported SmartUp data."""

    status: Literal["completed"] = "completed"
    message: str
    preserved_organizations: int
    cleared_total: int
    cleared_tables: dict[str, int] = Field(default_factory=dict)


class SmartUpOrganizationListResponse(BaseModel):
    """List wrapper for organizations."""

    items: list[SmartUpOrganization]


class SmartUpFilialCodeDiscoveryItem(BaseModel):
    """Discovered filial code for a SmartUp organization."""

    organization: str
    filial_id: str
    filial_code: str | None = None
    source: str = "order_export"
    status: str = "found"


class SmartUpFilialCodeDiscoveryResponse(BaseModel):
    """List response for filial-code discovery."""

    items: list[SmartUpFilialCodeDiscoveryItem] = Field(default_factory=list)


@dataclass(slots=True)
class _SmartUpMigrationJobRegistry:
    jobs: dict[UUID, SmartUpMigrationJobResponse] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)

    def create(self, message: str) -> SmartUpMigrationJobResponse:
        job = SmartUpMigrationJobResponse(job_id=uuid4(), message=message)
        with self.lock:
            self.jobs[job.job_id] = job
        return job

    def get(self, job_id: UUID) -> SmartUpMigrationJobResponse | None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            return job.model_copy(deep=True)

    def active(self) -> SmartUpMigrationJobResponse | None:
        with self.lock:
            for job in reversed(list(self.jobs.values())):
                if job.status in {"pending", "running"}:
                    return job.model_copy(deep=True)
        return None

    def update(self, job_id: UUID, **changes: object) -> SmartUpMigrationJobResponse | None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            updated = job.model_copy(update=changes)
            self.jobs[job_id] = updated
            return updated


_MIGRATION_JOBS = _SmartUpMigrationJobRegistry()
SMARTUP_MIGRATION_LOCK = Lock()


@dataclass(slots=True)
class SmartUpAccountService:
    """Orchestrate SmartUp organization management and migrations."""

    target: CoreDataStore
    settings: SmartUpSettings = field(default_factory=SmartUpSettings)

    def list_organizations(self) -> list[SmartUpOrganization]:
        return sorted(
            self.target.list_smartup_organizations(
                integration_id=SMARTUP_INTEGRATION_UUID,
                is_active=None,
            ),
            key=lambda item: (item.sort_order, item.name.lower(), str(item.id)),
        )

    def create_organization(self, payload: SmartUpOrganizationCreateRequest) -> SmartUpOrganization:
        organization = SmartUpOrganization(
            integration_id=SMARTUP_INTEGRATION_UUID,
            name=payload.name.strip(),
            company_id=payload.company_id.strip(),
            filial_id=payload.filial_id.strip(),
            filial_code=None,
            project_code=payload.project_code.strip(),
            is_active=payload.is_active,
            sort_order=payload.sort_order,
        )
        if payload.filial_code:
            organization = mark_verified_filial_code(
                organization,
                payload.filial_code.strip(),
                source="manual",
            )
        return self.target.upsert_smartup_organization(organization)

    def update_organization(
        self,
        organization_id: UUID,
        payload: SmartUpOrganizationUpdateRequest,
    ) -> SmartUpOrganization:
        organization = self.target.get_smartup_organization(organization_id)
        if organization is None:
            raise ValueError("SmartUp organization not found")
        company_id = payload.company_id.strip() if payload.company_id is not None else None
        filial_code = payload.filial_code.strip() if payload.filial_code is not None else None
        project_code = payload.project_code.strip() if payload.project_code is not None else None
        updated = organization.model_copy(
            update={
                key: value
                for key, value in {
                    "name": payload.name.strip() if payload.name is not None else None,
                    "company_id": company_id,
                    "filial_id": payload.filial_id.strip() if payload.filial_id else None,
                    "filial_code": None if filial_code else None,
                    "project_code": project_code,
                    "is_active": payload.is_active,
                    "sort_order": payload.sort_order,
                    "updated_at": datetime.now(UTC),
                }.items()
                if value is not None
            },
        )
        if filial_code:
            updated = mark_verified_filial_code(
                updated,
                filial_code,
                source="manual",
            )
        return self.target.upsert_smartup_organization(updated)

    def delete_organization(self, organization_id: UUID) -> None:
        self.target.delete_smartup_organization(organization_id)

    def discover_filial_codes(self) -> SmartUpFilialCodeDiscoveryResponse:
        """Populate SmartUp organization filial codes from raw order exports."""

        discovery_items: list[SmartUpFilialCodeDiscoveryItem] = []
        raw_records = list(self.target.list_smartup_raw_records())

        organizations = self.list_organizations()
        for organization in organizations:
            organization_records = [
                record for record in raw_records if record.organization_id == organization.id
            ]
            discovered_code, discovered_raw_record_id = (
                discover_verified_filial_code_from_raw_records(
                    organization_records,
                    organization.filial_id,
                )
            )
            current_code = resolve_filial_code(organization, organization_records)
            resolved_code = discovered_code or current_code
            if resolved_code and resolved_code != current_code:
                updated = mark_verified_filial_code(
                    organization,
                    resolved_code,
                    source="order_export",
                    raw_record_id=discovered_raw_record_id,
                )
                organization = self.target.upsert_smartup_organization(updated)
            discovery_items.append(
                SmartUpFilialCodeDiscoveryItem(
                    organization=organization.name,
                    filial_id=organization.filial_id,
                    filial_code=resolve_filial_code(organization, organization_records),
                    source="verified_raw_order_export",
                    status=(
                        "found"
                        if resolve_filial_code(organization, organization_records)
                        else "not_found"
                    ),
                ),
            )

        return SmartUpFilialCodeDiscoveryResponse(items=discovery_items)

    def reset_imported_data(self) -> SmartUpResetResponse:
        cleared_tables = self._snapshot_reset_counts()
        cleared_total = sum(cleared_tables.values())
        self.target.reset_smartup_data()
        return SmartUpResetResponse(
            message=(
                f"Удалено {cleared_total} записей SmartUp. "
                "Организации и настройки подключения сохранены."
            ),
            preserved_organizations=len(self.list_organizations()),
            cleared_total=cleared_total,
            cleared_tables=cleared_tables,
        )

    def check_connection(self, *args: object) -> SmartUpConnectionCheckResponse:
        started = perf_counter()
        if len(args) == 1:
            payload = self._normalize_auth_payload(args[0])
            organization = self._fallback_organization(payload)
        elif len(args) == 2:
            organization_id = self._require_uuid(args[0])
            payload = self._normalize_auth_payload(args[1])
            organization = self._get_required_organization(organization_id)
        else:  # pragma: no cover - defensive compatibility guard
            msg = "check_connection expects payload or organization_id plus payload"
            raise TypeError(msg)
        endpoint = "/b/anor/mxsx/mrf/room$export"
        resolved_auth = self.resolve_organization_auth(
            organization,
            payload,
            persist_credentials=False,
        )
        resolved_auth = SmartUpResolvedAuth(
            payload=resolved_auth.payload.model_copy(update={"timeout_seconds": 20.0}),
            source=resolved_auth.source,
            credentials_available=resolved_auth.credentials_available,
            client=None,
        )
        client = resolved_auth.client or self.build_client_for_organization(
            organization,
            payload=resolved_auth.payload,
            persist_credentials=False,
        )
        requested_url = client._build_url(endpoint)
        if not organization.filial_id.strip():
            return SmartUpConnectionCheckResponse(
                connected=False,
                code="SMARTUP_FILIAL_ID_REQUIRED",
                message=(
                    "Укажите filial_id организации из профиля SmartUp или получите его "
                    "у администратора SmartUp"
                ),
                upstream_status=None,
                upstream_response="",
                requested_url=requested_url,
                organization_id=organization.id,
                organization_name=organization.name,
                company_id=organization.company_id,
                filial_id=organization.filial_id,
                project_code=organization.project_code,
            )
        if not resolved_auth.credentials_available:
            return SmartUpConnectionCheckResponse(
                connected=False,
                code="SMARTUP_CREDENTIALS_NOT_FOUND",
                message=(
                    "Укажите username/password для проверки подключения SmartUp "
                    "или сохраните их в настройках организации."
                ),
                upstream_status=None,
                upstream_response="",
                requested_url=requested_url,
                organization_id=organization.id,
                organization_name=organization.name,
                company_id=organization.company_id,
                filial_id=organization.filial_id,
                project_code=organization.project_code,
            )
        try:
            request_payload = {}
            organization_filial_code = self._organization_filial_code(organization)
            if organization_filial_code:
                request_payload["filial_code"] = organization_filial_code
            response = client.request_response("POST", endpoint, request_payload)
        except httpx.ReadTimeout:
            return SmartUpConnectionCheckResponse(
                connected=False,
                code="SMARTUP_TIMEOUT",
                message="SmartUp не ответил за 20 секунд. Проверьте доступность сервера и повторите попытку.",
                requested_url=requested_url,
                organization_id=organization.id,
                organization_name=organization.name,
                company_id=organization.company_id,
                filial_id=organization.filial_id,
                project_code=organization.project_code,
                ok=False,
                status="timeout",
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )
        except httpx.RequestError as exc:
            return SmartUpConnectionCheckResponse(
                connected=False,
                code="SMARTUP_UNAVAILABLE",
                message="SmartUp недоступен. Проверьте адрес сервера и повторите попытку.",
                upstream_status=None,
                upstream_response=str(exc),
                requested_url=requested_url,
                organization_id=organization.id,
                organization_name=organization.name,
                company_id=organization.company_id,
                filial_id=organization.filial_id,
                project_code=organization.project_code,
                ok=False,
                status="unavailable",
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )
        if response.status_code in {401, 403}:
            return SmartUpConnectionCheckResponse(
                connected=False,
                code="INVALID_CREDENTIALS",
                message="Неверный логин или пароль SmartUp.",
                upstream_status=response.status_code,
                upstream_response=response.text or response.reason_phrase or "",
                requested_url=requested_url,
                organization_id=organization.id,
                organization_name=organization.name,
                company_id=organization.company_id,
                filial_id=organization.filial_id,
                project_code=organization.project_code,
                ok=False,
                status="invalid_credentials",
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )
        if response.is_success and resolved_auth.source in {"payload", "global"}:
            self._persist_organization_credentials(organization, resolved_auth.payload)
        if response.status_code in {403, 404}:
            return SmartUpConnectionCheckResponse(
                connected=False,
                code="SMARTUP_UNAVAILABLE" if response.status_code == 404 else "SMARTUP_ACCESS_DENIED",
                message=(
                    "Пользователь не имеет доступа к endpoint, проекту или выбранной организации"
                ),
                upstream_status=response.status_code,
                upstream_response=response.text or response.reason_phrase or "",
                requested_url=requested_url,
                organization_id=organization.id,
                organization_name=organization.name,
                company_id=organization.company_id,
                filial_id=organization.filial_id,
                project_code=organization.project_code,
            )
        return SmartUpConnectionCheckResponse(
            connected=response.is_success,
            code="SMARTUP_CONNECTION_OK" if response.is_success else "SMARTUP_CONNECTION_FAILED",
            message="Соединение установлено" if response.is_success else "SmartUp вернул ошибку",
            upstream_status=response.status_code,
            upstream_response=response.text or response.reason_phrase or "",
            requested_url=requested_url,
            organization_id=organization.id,
            organization_name=organization.name,
            company_id=organization.company_id,
            filial_id=organization.filial_id,
            project_code=organization.project_code,
            ok=response.is_success,
            status="connected" if response.is_success else "unavailable",
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    def migrate_all(self, payload: SmartUpAuthPayload) -> SmartUpMigrationAllResponse:
        with SMARTUP_MIGRATION_LOCK:
            self.discover_filial_codes()
            return self._migrate_all_core(payload)

    def start_migration_job(self, payload: SmartUpAuthPayload) -> SmartUpMigrationJobResponse:
        active_job = _MIGRATION_JOBS.active()
        if active_job is not None:
            return active_job
        job = _MIGRATION_JOBS.create("Миграция SmartUp поставлена в очередь.")
        _MIGRATION_JOBS.update(job.job_id, migration_mode=payload.migration_mode)
        thread = Thread(
            target=self._run_migration_job,
            args=(job.job_id, payload.model_dump(mode="python")),
            daemon=True,
        )
        thread.start()
        return job

    def get_migration_job(self, job_id: UUID) -> SmartUpMigrationJobResponse | None:
        return _MIGRATION_JOBS.get(job_id)

    def _run_migration_job(self, job_id: UUID, payload_data: dict[str, object]) -> None:
        payload = SmartUpAuthPayload.model_validate(payload_data)
        with SMARTUP_MIGRATION_LOCK:
            self.discover_filial_codes()
            organizations = self._active_organizations()
            started_at = datetime.now(UTC)
            _MIGRATION_JOBS.update(
                job_id,
                status="running",
                started_at=started_at,
                total_organizations=len(organizations),
                progress_organizations=0,
                message=f"Миграция запущена: {len(organizations)} организаций.",
            )
            try:
                result = self._migrate_all_core(
                    payload,
                    progress_callback=lambda **changes: _MIGRATION_JOBS.update(job_id, **changes),
                )
                _MIGRATION_JOBS.update(
                    job_id,
                    status="completed",
                    completed_at=datetime.now(UTC),
                    progress_organizations=result.organizations_count,
                    total_organizations=result.organizations_count,
                    result=result,
                    message=result.message,
                )
            except Exception as exc:  # pragma: no cover - background safety guard
                _MIGRATION_JOBS.update(
                    job_id,
                    status="failed",
                    completed_at=datetime.now(UTC),
                    error=str(exc),
                    message=f"Миграция SmartUp завершилась с ошибкой: {exc}",
                )

    def _materialize_canonical_v2(
        self,
        organization_ids: list[UUID] | None = None,
    ) -> None:
        service = SmartUpCanonicalV2FoundationService(self.target)
        if organization_ids:
            for organization_id in organization_ids:
                service.backfill_all(organization_id=organization_id)
            return
        service.backfill_all()

    def _migrate_all_core(
        self,
        payload: SmartUpAuthPayload,
        progress_callback: Callable[..., None] | None = None,
    ) -> SmartUpMigrationAllResponse:
        warnings: list[str] = []
        organizations = self._active_organizations()
        if not organizations:
            raise ValueError("Создайте хотя бы одну активную SmartUp организацию.")

        history_end = payload.history_end or datetime.now(UTC)
        history_start = payload.history_start or self._default_history_start(
            payload.migration_mode,
            history_end,
        )
        organization_results: list[SmartUpMigrationOrganizationResult] = []
        all_runs: list[SmartUpMigrationRun] = []
        batch_errors: list[SmartUpBatchImportError] = []
        aggregate_summary = SmartUpMigrationSummary()
        aggregate_counters = {"batches": 0, "records": 0, "errors": 0}
        processed_organizations = 0

        if progress_callback is not None:
            progress_callback(
                progress_organizations=0,
                total_organizations=len(organizations),
                message=f"Подготовка миграции для {len(organizations)} организаций.",
                current_phase="preparing",
            )

        for organization in organizations:
            if progress_callback is not None:
                progress_callback(
                    progress_organizations=processed_organizations,
                    total_organizations=len(organizations),
                    message=f"Обработка организации: {organization.name}",
                    current_organization_id=organization.id,
                    current_organization_name=organization.name,
                    current_entity_type=None,
                    current_entity_label=None,
                    current_phase="organization",
                )
            try:
                client = self._build_client_compat(payload, organization)
                result, runs, errors, counters, summary = self._migrate_organization_with_client(
                    client=client,
                    payload=payload,
                    organization=organization,
                    history_start=history_start,
                    history_end=history_end,
                    migration_mode=payload.migration_mode,
                    chunk_days=self._resolve_chunk_days(payload.migration_mode, None),
                    progress_callback=progress_callback,
                )
            except Exception as exc:  # pragma: no cover - transport/runtime safety
                organization_results.append(
                    SmartUpMigrationOrganizationResult(
                        organization_id=organization.id,
                        name=organization.name,
                        filial_id=organization.filial_id,
                        company_id=organization.company_id,
                        project_code=organization.project_code,
                        summary=SmartUpMigrationSummary(organizations=1, errors=1),
                        counters={"batches": 0, "records": 0, "errors": 1},
                        runs=list(
                            self.target.list_smartup_migration_runs(organization_id=organization.id)
                        ),
                    ),
                )
                warnings.append(f"{organization.name}: {exc}")
                aggregate_summary.organizations += 1
                aggregate_summary.errors += 1
                aggregate_counters["errors"] = aggregate_counters.get("errors", 0) + 1
                processed_organizations += 1
                if progress_callback is not None:
                    progress_callback(
                        progress_organizations=processed_organizations,
                        total_organizations=len(organizations),
                        message=f"Организация {organization.name} завершилась с ошибкой: {exc}",
                        current_organization_id=organization.id,
                        current_organization_name=organization.name,
                        current_entity_type=None,
                        current_entity_label=None,
                        current_phase="organization_failed",
                    )
                continue
            organization_results.append(result)
            all_runs.extend(runs)
            batch_errors.extend(errors)
            aggregate_summary = _add_summary(aggregate_summary, summary)
            for key, value in counters.items():
                aggregate_counters[key] = aggregate_counters.get(key, 0) + value
            self._touch_organization_sync(organization.id)
            processed_organizations += 1
            if progress_callback is not None:
                progress_callback(
                    progress_organizations=processed_organizations,
                    total_organizations=len(organizations),
                    message=(
                        f"Обработано {processed_organizations}/{len(organizations)} организаций: "
                        f"{organization.name}"
                    ),
                    current_organization_id=organization.id,
                    current_organization_name=organization.name,
                    current_entity_type=None,
                    current_entity_label=None,
                    current_phase="organization_completed",
                )

        aggregate_summary.organizations = len(organization_results)
        has_errors = bool(batch_errors) or any((run.failed_count or 0) > 0 for run in all_runs)
        if progress_callback is not None:
            progress_callback(
                progress_organizations=len(organizations),
                total_organizations=len(organizations),
                message="Миграция SmartUp завершена.",
                current_phase="completed",
            )
        self._materialize_canonical_v2([organization.id for organization in organizations])
        return SmartUpMigrationAllResponse(
            status="completed_with_errors" if has_errors else "completed",
            message="Миграция SmartUp завершена."
            if not has_errors
            else "Миграция SmartUp завершена с ошибками.",
            organizations_count=len(organization_results),
            organizations=organization_results,
            runs=all_runs,
            summary=aggregate_summary,
            counters=aggregate_counters,
            batch_errors=batch_errors,
            warnings=warnings,
            history_start=history_start,
            history_end=history_end,
        )

    def migrate_history(
        self,
        payload: SmartUpHistoryMigrationRequest,
    ) -> SmartUpMigrationAllResponse:
        self.discover_filial_codes()
        selected_organizations = [item for item in payload.organizations if item.selected]
        if not selected_organizations:
            raise ValueError(
                "Укажите хотя бы одну организацию вручную и свяжите её через filial_id. "
                "Автозагрузка организаций из SmartUp отключена.",
            )

        warnings: list[str] = []
        history_end = payload.history_end or datetime.now(UTC)
        history_start = (
            self._default_history_start(payload.migration_mode, history_end)
            if payload.migration_mode == SmartUpMigrationMode.ONE_DAY_CHECK
            else payload.history_start
        )
        resolved_chunk_days = self._resolve_chunk_days(payload.migration_mode, payload.chunk_days)
        organization_results: list[SmartUpMigrationOrganizationResult] = []
        all_runs: list[SmartUpMigrationRun] = []
        batch_errors: list[SmartUpBatchImportError] = []
        aggregate_summary = SmartUpMigrationSummary()
        aggregate_counters = {"batches": 0, "records": 0, "errors": 0}

        for item in selected_organizations:
            organization = SmartUpOrganization(
                integration_id=SMARTUP_INTEGRATION_UUID,
                name=item.name,
                company_id=item.company_id,
                filial_id=item.filial_id,
                filial_code=None,
                project_code=item.project_code,
                is_active=True,
                sort_order=0,
            )
            if item.filial_code:
                organization = mark_verified_filial_code(
                    organization,
                    item.filial_code.strip(),
                    source="manual",
                )
            auth_payload = SmartUpAuthPayload(
                base_url=payload.base_url,
                username=payload.username,
                password=payload.password,
                project_code=(
                    item.project_code or payload.project_code or self.settings.project_code
                ),
                filial_id=item.filial_id,
                timeout_seconds=payload.timeout_seconds,
                migration_mode=payload.migration_mode,
                history_start=payload.history_start,
                history_end=payload.history_end,
            )
            client = self._build_client_compat(auth_payload, organization)
            before_summary = self._snapshot_summary(organization.id)
            before_batch_ids = self._snapshot_batch_ids(organization.id)
            runner = SmartUpHistoricalImportRunner(
                client=client,
                target=self.target,
                business_id=organization.id,
                business_name=organization.name,
                business_external_ref=organization.filial_id,
                smartup_filial_id=organization.filial_id,
                smartup_filial_code=self._organization_filial_code(organization),
                connector=SmartUpConnector(
                    base_url=getattr(
                        getattr(client, "settings", None),
                        "base_url",
                        self.settings.base_url,
                    ),
                    mappings=SMARTUP_CORE_MAPPING_V1,
                ),
            )
            run_counters = self._run_history_import(
                runner=runner,
                history_start=history_start,
                history_end=history_end,
                chunk_days=resolved_chunk_days,
                migration_mode=payload.migration_mode,
            )
            after_summary = self._snapshot_summary(organization.id)
            summary = _diff_summary(after_summary, before_summary)
            summary.organizations = 1
            summary.batches = run_counters.get("batches", 0)
            summary.errors = run_counters.get("errors", 0)
            result = SmartUpMigrationOrganizationResult(
                organization_id=organization.id,
                name=organization.name,
                company_id=organization.company_id,
                filial_id=organization.filial_id,
                project_code=organization.project_code,
                summary=summary,
                counters=dict(run_counters),
                runs=list(self.target.list_smartup_migration_runs(organization_id=organization.id)),
            )
            runs = list(self.target.list_smartup_migration_runs(organization_id=organization.id))
            errors = self._collect_batch_errors(
                organization_name=organization.name,
                business_id=organization.id,
                before_batch_ids=before_batch_ids,
            )
            counters = dict(run_counters)
            organization_results.append(result)
            all_runs.extend(runs)
            batch_errors.extend(errors)
            aggregate_summary = _add_summary(aggregate_summary, summary)
            for key, value in counters.items():
                aggregate_counters[key] = aggregate_counters.get(key, 0) + value
            self._touch_organization_sync(organization.id)

        aggregate_summary.organizations = len(organization_results)
        has_errors = bool(batch_errors) or any((run.failed_count or 0) > 0 for run in all_runs)
        self._materialize_canonical_v2([item.organization_id for item in organization_results])
        return SmartUpMigrationAllResponse(
            status="completed_with_errors" if has_errors else "completed",
            message="Миграция SmartUp завершена."
            if not has_errors
            else "Миграция SmartUp завершена с ошибками.",
            organizations_count=len(organization_results),
            organizations=organization_results,
            runs=all_runs,
            summary=aggregate_summary,
            counters=aggregate_counters,
            batch_errors=batch_errors,
            warnings=warnings,
            history_start=history_start,
            history_end=history_end,
        )

    def migrate_organization(
        self,
        organization_id: UUID,
        payload: SmartUpAuthPayload,
    ) -> SmartUpMigrationAllResponse:
        with SMARTUP_MIGRATION_LOCK:
            self.discover_filial_codes()
            organization = self._get_required_organization(organization_id)
            client = self._build_client_compat(payload, organization)
            result, runs, errors, counters, summary = self._migrate_organization_with_client(
            client=client,
            payload=payload,
            organization=organization,
            history_start=payload.history_start
            or self._default_history_start(
                payload.migration_mode,
                payload.history_end or datetime.now(UTC),
            ),
            history_end=payload.history_end or datetime.now(UTC),
            migration_mode=payload.migration_mode,
            chunk_days=self._resolve_chunk_days(payload.migration_mode, None),
            )
            self._touch_organization_sync(organization.id)
            self._materialize_canonical_v2([organization.id])
            return SmartUpMigrationAllResponse(
            status="completed_with_errors" if errors else "completed",
            message="Миграция SmartUp завершена."
            if not errors
            else "Миграция SmartUp завершена с ошибками.",
            organizations_count=1,
            organizations=[result],
            runs=runs,
            summary=summary,
            counters=counters,
            batch_errors=errors,
            warnings=[],
            history_start=payload.history_start
            or self._default_history_start(
                payload.migration_mode,
                payload.history_end or datetime.now(UTC),
            ),
            history_end=payload.history_end or datetime.now(UTC),
        )

    def build_client(
        self,
        payload: SmartUpAuthPayload,
        organization: SmartUpOrganization | None = None,
    ) -> SmartUpApiClient:
        resolved_organization = organization or self._fallback_organization(payload)
        resolved_auth = self.resolve_organization_auth(
            resolved_organization,
            payload,
            persist_credentials=organization is not None,
        )
        company_id = (
            organization.company_id if organization is not None else self.settings.company_id
        )
        project_code = (
            organization.project_code if organization is not None else self.settings.project_code
        )
        return SmartUpApiClient(
            settings=SmartUpSettings(
                base_url=resolved_auth.payload.base_url,
                username=resolved_auth.payload.username,
                password=resolved_auth.payload.password,
                company_id=company_id,
                project_code=project_code,
                filial_id=resolved_organization.filial_id,
                timeout_seconds=resolved_auth.payload.timeout_seconds,
            ),
        )

    def build_client_for_organization(
        self,
        organization: SmartUpOrganization,
        payload: SmartUpAuthPayload | None = None,
        *,
        persist_credentials: bool = False,
    ) -> SmartUpApiClient:
        """Build a SmartUp client using the shared per-organization resolver."""

        resolved_auth = self.resolve_organization_auth(
            organization,
            payload,
            persist_credentials=persist_credentials,
        )
        return SmartUpApiClient(
            settings=SmartUpSettings(
                base_url=resolved_auth.payload.base_url,
                username=resolved_auth.payload.username,
                password=resolved_auth.payload.password,
                company_id=organization.company_id,
                project_code=organization.project_code,
                filial_id=organization.filial_id,
                timeout_seconds=resolved_auth.payload.timeout_seconds,
            ),
        )

    def _build_client_compat(
        self,
        payload: SmartUpAuthPayload,
        organization: SmartUpOrganization | None = None,
    ) -> SmartUpApiClient:
        try:
            if organization is None:
                return self.build_client(payload)
            return self.build_client(payload, organization)
        except TypeError:
            return self.build_client(payload)

    def resolve_organization_auth(
        self,
        organization: SmartUpOrganization,
        payload: SmartUpAuthPayload | None = None,
        *,
        persist_credentials: bool = False,
    ) -> SmartUpResolvedAuth:
        """Resolve org credentials from the same effective path used by manual imports."""

        base_url = self._resolve_base_url(payload.base_url if payload is not None else None)
        timeout_seconds = (
            payload.timeout_seconds if payload is not None else self.settings.timeout_seconds
        )
        payload_username = self._clean_text(payload.username) if payload is not None else None
        payload_password = self._clean_text(payload.password) if payload is not None else None
        if payload_username and payload_password:
            resolved_payload = SmartUpAuthPayload(
                base_url=base_url,
                username=payload_username,
                password=payload_password,
                project_code=(
                    organization.project_code or payload.project_code or self.settings.project_code
                ),
                filial_id=organization.filial_id,
                timeout_seconds=timeout_seconds,
            )
            if persist_credentials:
                self._persist_organization_credentials(organization, resolved_payload)
            return SmartUpResolvedAuth(
                payload=resolved_payload,
                source="payload",
                credentials_available=True,
            )

        stored = self._load_organization_credentials(organization)
        if stored is not None:
            return SmartUpResolvedAuth(
                payload=stored,
                source="organization_settings",
                credentials_available=True,
            )

        global_username = self._clean_text(self.settings.username)
        global_password = self._clean_text(self.settings.password)
        if global_username and global_password:
            return SmartUpResolvedAuth(
                payload=SmartUpAuthPayload(
                    base_url=self.settings.base_url,
                    username=global_username,
                    password=global_password,
                    project_code=organization.project_code or self.settings.project_code,
                    filial_id=organization.filial_id,
                    timeout_seconds=self.settings.timeout_seconds,
                ),
                source="global",
                credentials_available=True,
            )

        return SmartUpResolvedAuth(
            payload=SmartUpAuthPayload(
                base_url=base_url,
                username="",
                password="",
                project_code=organization.project_code or self.settings.project_code,
                filial_id=organization.filial_id,
                timeout_seconds=timeout_seconds,
            ),
            source="missing",
            credentials_available=False,
        )

    def _migrate_organization_with_client(
        self,
        *,
        client: SmartUpApiClient,
        payload: SmartUpAuthPayload,
        organization: SmartUpOrganization,
        history_start: datetime,
        history_end: datetime,
        migration_mode: SmartUpMigrationMode,
        chunk_days: int,
        progress_callback: Callable[..., None] | None = None,
    ) -> tuple[
        SmartUpMigrationOrganizationResult,
        list[SmartUpMigrationRun],
        list[SmartUpBatchImportError],
        dict[str, int],
        SmartUpMigrationSummary,
    ]:
        business_external_ref = self._business_external_ref(organization)
        business_id = organization.id
        before_summary = self._snapshot_summary(business_id)
        before_batch_ids = self._snapshot_batch_ids(business_id)
        entity_runs: list[SmartUpMigrationRun] = []
        batch_errors: list[SmartUpBatchImportError] = []
        counters = {"batches": 0, "records": 0, "errors": 0}

        self.target.register_business(
            BusinessIdentity(
                business_id=business_id,
                name=organization.name,
                display_name=organization.name,
                external_ref=business_external_ref,
                metadata={
                    "smartup_organization_id": str(organization.id),
                    "company_id": organization.company_id,
                    "filial_id": organization.filial_id,
                    "smartup_filial_id": organization.filial_id,
                },
            ),
        )

        selected_datasets = set(payload.datasets or _ENTITY_IMPORT_PLAN)
        for entity_type, mapping_names in _ENTITY_IMPORT_PLAN.items():
            if entity_type not in selected_datasets:
                continue
            if progress_callback is not None:
                progress_callback(
                    current_organization_id=organization.id,
                    current_organization_name=organization.name,
                    current_entity_type=entity_type,
                    current_entity_label=_ENTITY_LABELS.get(entity_type, entity_type),
                    current_phase="entity",
                    message=(
                        f"{organization.name}: {_ENTITY_LABELS.get(entity_type, entity_type)}"
                    ),
                )
            run = SmartUpMigrationRun(
                organization_id=organization.id,
                entity_type=entity_type,
                started_at=datetime.now(UTC),
                status=SmartUpMigrationStatus.RUNNING,
                metadata={
                    "company_id": organization.company_id,
                    "filial_id": organization.filial_id,
                    "smartup_filial_id": organization.filial_id,
                },
            )
            self.target.upsert_smartup_migration_run(run)
            entity_runs.append(run)

            try:
                subset_mappings = tuple(
                    mapping for mapping in SMARTUP_CORE_MAPPING_V1 if mapping.name in mapping_names
                )
                runner = SmartUpHistoricalImportRunner(
                    client=client,
                    target=self.target,
                    business_id=business_id,
                    business_name=organization.name,
                    business_external_ref=business_external_ref,
                    smartup_filial_id=organization.filial_id,
                    smartup_filial_code=self._organization_filial_code(organization),
                    connector=SmartUpConnector(
                        base_url=getattr(
                            getattr(client, "settings", None),
                            "base_url",
                            self.settings.base_url,
                        ),
                        mappings=subset_mappings,
                    ),
                )
                run_counters = self._run_history_import(
                    runner=runner,
                    history_start=history_start,
                    history_end=history_end,
                    chunk_days=chunk_days,
                    migration_mode=migration_mode,
                )
                run.status = SmartUpMigrationStatus.COMPLETED
                run.completed_at = datetime.now(UTC)
                run.imported_count = run_counters.get("records", 0)
                run.updated_count = 0
                run.skipped_count = 0
                run.failed_count = 0
                self.target.upsert_smartup_migration_run(run)
                counters["batches"] += run_counters.get("batches", 0)
                counters["records"] += run_counters.get("records", 0)
                counters["errors"] += run_counters.get("errors", 0)
            except Exception as exc:  # pragma: no cover - transport/runtime safety
                run.status = SmartUpMigrationStatus.FAILED
                run.completed_at = datetime.now(UTC)
                run.failed_count = 1
                run.error_message = str(exc)
                self.target.upsert_smartup_migration_run(run)
                counters["errors"] += 1

        after_summary = self._snapshot_summary(business_id)
        summary = _diff_summary(after_summary, before_summary)
        summary.organizations = 1
        summary.batches = counters["batches"]
        summary.errors = counters["errors"]
        batch_errors.extend(
            self._collect_batch_errors(
                organization_name=organization.name,
                business_id=business_id,
                before_batch_ids=before_batch_ids,
            ),
        )

        return (
            SmartUpMigrationOrganizationResult(
                organization_id=organization.id,
                name=organization.name,
                company_id=organization.company_id,
                filial_id=organization.filial_id,
                project_code=organization.project_code,
                summary=summary,
                counters=counters,
                runs=list(self.target.list_smartup_migration_runs(organization_id=organization.id)),
            ),
            list(self.target.list_smartup_migration_runs(organization_id=organization.id)),
            batch_errors,
            counters,
            summary,
        )

    def _active_organizations(self) -> list[SmartUpOrganization]:
        organizations = list(
            self.target.list_smartup_organizations(
                integration_id=SMARTUP_INTEGRATION_UUID,
                is_active=True,
            ),
        )
        return sorted(
            organizations, key=lambda item: (item.sort_order, item.name.lower(), str(item.id))
        )

    def _get_required_organization(self, organization_id: UUID) -> SmartUpOrganization:
        organization = self.target.get_smartup_organization(organization_id)
        if organization is None:
            raise ValueError("SmartUp organization not found")
        return organization

    def _snapshot_summary(self, business_id: UUID) -> SmartUpMigrationSummary:
        source_systems = list(self.target.list_source_systems(business_id))
        contacts = list(self.target.list_contacts(business_id))
        sales = list(self.target.list_sales(business_id))
        marketing_activities = list(self.target.list_marketing_activities(business_id))
        finance_entries = list(self.target.list_finance_entries(business_id))
        records = list(self.target.list_records(business_id))
        batches = list(self.target.list_ingestion_batches(business_id))
        errors = sum(
            len(list(self.target.list_ingestion_errors(batch.batch_id))) for batch in batches
        )
        return SmartUpMigrationSummary(
            businesses=1 if self.target.get_business(business_id) is not None else 0,
            source_systems=len(source_systems),
            contacts=len(contacts),
            sales=len(sales),
            marketing_activities=len(marketing_activities),
            finance_entries=len(finance_entries),
            records=len(records),
            batches=len(batches),
            errors=errors,
        )

    def _snapshot_reset_counts(self) -> dict[str, int]:
        return {
            "businesses": len(list(self.target.list_businesses())),
            "source_systems": len(list(self.target.list_source_systems())),
            "contacts": len(list(self.target.list_contacts())),
            "sales": len(list(self.target.list_sales())),
            "marketing_activities": len(list(self.target.list_marketing_activities())),
            "finance_entries": len(list(self.target.list_finance_entries())),
            "ingestion_batches": len(list(self.target.list_ingestion_batches())),
            "ingestion_errors": len(list(self.target.list_ingestion_errors())),
            "records": len(list(self.target.list_records())),
            "kpis": len(list(self.target.list_kpis())),
            "smartup_migration_runs": len(list(self.target.list_smartup_migration_runs())),
            "sync_checkpoints": len(list(self.target.list_sync_checkpoints())),
            "migration_batches": len(list(self.target.list_migration_batches())),
            "inventory_snapshots": len(list(self.target.list_inventory_snapshots())),
            "smartup_raw_records": len(list(self.target.list_smartup_raw_records())),
            "normalization_issues": len(list(self.target.list_normalization_issues())),
            "customers": len(list(self.target.list_customers())),
            "product_categories": len(list(self.target.list_product_categories())),
            "products": len(list(self.target.list_products())),
            "warehouses": len(list(self.target.list_warehouses())),
            "sales_v2": len(list(self.target.list_sales_v2())),
            "sale_items": len(list(self.target.list_sale_items())),
            "payments": len(list(self.target.list_payments())),
            "inventory_balances": len(list(self.target.list_inventory_balances())),
            "visits": len(list(self.target.list_visits())),
            "bank_operations": len(list(self.target.list_bank_operations())),
            "business_documents": len(list(self.target.list_business_documents())),
            "business_document_items": len(list(self.target.list_business_document_items())),
        }

    def _snapshot_batch_ids(self, business_id: UUID) -> set[UUID]:
        return {batch.batch_id for batch in self.target.list_ingestion_batches(business_id)}

    def _collect_batch_errors(
        self,
        *,
        organization_name: str,
        business_id: UUID,
        before_batch_ids: set[UUID],
    ) -> list[SmartUpBatchImportError]:
        errors: list[SmartUpBatchImportError] = []
        for batch in self.target.list_ingestion_batches(business_id):
            if batch.batch_id in before_batch_ids:
                continue
            if str(batch.status) != "failed":
                continue
            batch_errors = list(self.target.list_ingestion_errors(batch.batch_id))
            if not batch_errors:
                errors.append(
                    SmartUpBatchImportError(
                        organization_id=business_id,
                        organization_name=organization_name,
                        business_id=business_id,
                        batch_id=batch.batch_id,
                        batch_name=batch.batch_name,
                        batch_status=str(batch.status),
                        endpoint=self._batch_requested_url(batch),
                        source_endpoint=self._batch_source_endpoint(batch),
                        requested_url=self._batch_requested_url(batch),
                        payload=self._batch_payload(batch),
                        entity_type=None,
                        error_code="FAILED",
                        error_message="Batch failed without a recorded ingestion error.",
                    ),
                )
                continue
            for error in batch_errors:
                errors.append(
                    SmartUpBatchImportError(
                        organization_id=business_id,
                        organization_name=organization_name,
                        business_id=business_id,
                        batch_id=batch.batch_id,
                        batch_name=batch.batch_name,
                        batch_status=str(batch.status),
                        endpoint=self._batch_requested_url(batch),
                        source_endpoint=self._batch_source_endpoint(batch),
                        requested_url=self._batch_requested_url(batch),
                        payload=self._batch_payload(batch),
                        entity_type=error.entity_type,
                        error_code=error.error_code,
                        error_message=error.error_message,
                    ),
                )
        return errors

    def _batch_source_endpoint(self, batch: object) -> str | None:
        endpoint = getattr(batch, "endpoint", None)
        if endpoint is not None:
            text = str(endpoint).strip()
            if text:
                return text
        metadata = getattr(batch, "metadata", None)
        if isinstance(metadata, dict):
            endpoint = metadata.get("source_endpoint") or metadata.get("endpoint")
            if endpoint is not None:
                text = str(endpoint).strip()
                if text:
                    return text
        return None

    def _batch_requested_url(self, batch: object) -> str | None:
        requested_url = getattr(batch, "endpoint", None)
        if requested_url is not None:
            text = str(requested_url).strip()
            if text:
                return text
        metadata = getattr(batch, "metadata", None)
        if isinstance(metadata, dict):
            requested_url = metadata.get("requested_url") or metadata.get("endpoint")
            if requested_url is not None:
                text = str(requested_url).strip()
                if text:
                    return text
        return None

    def _batch_payload(self, batch: object) -> dict[str, object] | None:
        request_payload = getattr(batch, "request_payload", None)
        if isinstance(request_payload, dict):
            return request_payload
        if isinstance(request_payload, list):
            return {"items": request_payload}
        metadata = getattr(batch, "metadata", None)
        if isinstance(metadata, dict):
            payload = metadata.get("payload")
            if isinstance(payload, dict):
                return payload
        return None

    def _business_external_ref(self, organization: SmartUpOrganization) -> str:
        return organization.filial_id

    def _organization_filial_code(self, organization: SmartUpOrganization) -> str | None:
        raw_records = list(self.target.list_smartup_raw_records(organization_id=organization.id))
        return resolve_filial_code(organization, raw_records)

    def _has_filial_id_conflict(self, organization_id: UUID, filial_code: str | None) -> bool:
        candidate = self._clean_text(filial_code)
        if not candidate:
            return False
        for organization in self.list_organizations():
            if organization.id == organization_id:
                continue
            if self._clean_text(organization.filial_id) == candidate:
                return True
        return False

    @staticmethod
    def _clean_text(value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _entity_label(entity_type: str) -> str:
        return _ENTITY_LABELS.get(entity_type, entity_type)

    def _resolve_base_url(self, base_url: str | None) -> str:
        candidate = (base_url or "").strip()
        if candidate:
            return candidate.rstrip("/")
        return self.settings.base_url.rstrip("/")

    def _organization_credentials_setting_key(self, organization_id: UUID) -> str:
        return f"{_SMARTUP_CREDENTIALS_SETTING_PREFIX}{organization_id}"

    def _persist_organization_credentials(
        self,
        organization: SmartUpOrganization,
        payload: SmartUpAuthPayload,
    ) -> None:
        username = self._clean_text(payload.username)
        password = self._clean_text(payload.password)
        if not username or not password:
            return
        normalized_base_url = self._resolve_base_url(payload.base_url)
        now = datetime.now(UTC)
        self.target.upsert_app_setting(
            AppSetting(
                setting_key=self._organization_credentials_setting_key(organization.id),
                setting_value={
                    "integration_id": str(organization.integration_id),
                    "organization_id": str(organization.id),
                    "company_id": organization.company_id,
                    "filial_id": organization.filial_id,
                    "project_code": organization.project_code,
                    "base_url": normalized_base_url,
                    "username": username,
                    "password": password,
                    "timeout_seconds": payload.timeout_seconds,
                    "persisted_at": now.isoformat(),
                },
                metadata={
                    "scope": "smartup_organization_credentials",
                    "organization_id": str(organization.id),
                    "integration_id": str(organization.integration_id),
                },
                created_at=now,
                updated_at=now,
            ),
        )

    def _load_organization_credentials(
        self,
        organization: SmartUpOrganization,
    ) -> SmartUpAuthPayload | None:
        setting = self.target.get_app_setting(
            self._organization_credentials_setting_key(organization.id),
        )
        if setting is None:
            return None
        value = setting.setting_value
        if not isinstance(value, dict):
            return None
        if str(value.get("organization_id") or "").strip() != str(organization.id):
            return None
        if str(value.get("integration_id") or "").strip() not in {
            "",
            str(organization.integration_id),
        }:
            return None
        if str(value.get("company_id") or "").strip() not in {"", organization.company_id}:
            return None
        if str(value.get("filial_id") or "").strip() not in {"", organization.filial_id}:
            return None
        if str(value.get("project_code") or "").strip() not in {"", organization.project_code}:
            return None
        username = self._clean_text(value.get("username"))
        password = self._clean_text(value.get("password"))
        if not username or not password:
            return None
        timeout_seconds = value.get("timeout_seconds")
        try:
            resolved_timeout = float(timeout_seconds)
        except (TypeError, ValueError):
            resolved_timeout = self.settings.timeout_seconds
        return SmartUpAuthPayload(
            base_url=self._resolve_base_url(value.get("base_url") or self.settings.base_url),
            username=username,
            password=password,
            project_code=organization.project_code,
            filial_id=organization.filial_id,
            timeout_seconds=resolved_timeout,
        )

    def _fallback_organization(self, payload: SmartUpAuthPayload) -> SmartUpOrganization:
        return SmartUpOrganization(
            integration_id=SMARTUP_INTEGRATION_UUID,
            name="SmartUp",
            filial_id=(payload.filial_id or "").strip(),
            is_active=True,
        )

    def _touch_organization_sync(self, organization_id: UUID) -> None:
        organization = self.target.get_smartup_organization(organization_id)
        if organization is None:
            return
        touched = organization.model_copy(
            update={
                "last_sync_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        )
        self.target.upsert_smartup_organization(touched)

    @staticmethod
    def _default_history_start(mode: SmartUpMigrationMode, history_end: datetime) -> datetime:
        if mode == SmartUpMigrationMode.ONE_DAY_CHECK:
            return history_end - timedelta(days=1)
        if mode == SmartUpMigrationMode.WEEKLY_RECONCILIATION:
            return history_end - timedelta(days=7)
        return history_end - timedelta(days=30)

    @staticmethod
    def _resolve_chunk_days(
        migration_mode: SmartUpMigrationMode,
        requested_chunk_days: int | None,
    ) -> int:
        if migration_mode == SmartUpMigrationMode.ONE_DAY_CHECK:
            return 1
        if migration_mode == SmartUpMigrationMode.FULL_BACKFILL:
            if requested_chunk_days is not None and requested_chunk_days > 0:
                return max(30, requested_chunk_days)
            return 30
        if requested_chunk_days is not None and requested_chunk_days > 0:
            return min(requested_chunk_days, MAX_SMARTUP_HISTORY_WINDOW_DAYS)
        if migration_mode == SmartUpMigrationMode.WEEKLY_RECONCILIATION:
            return 7
        return MAX_SMARTUP_HISTORY_WINDOW_DAYS

    @staticmethod
    def _run_history_import(
        *,
        runner: object,
        history_start: datetime,
        history_end: datetime,
        chunk_days: int,
        migration_mode: SmartUpMigrationMode,
    ) -> dict[str, int]:
        run = runner.run
        try:
            result = run(
                history_start=history_start,
                history_end=history_end,
                chunk_days=chunk_days,
                migration_mode=migration_mode,
            )
        except TypeError as exc:
            if "migration_mode" not in str(exc):
                raise
            result = run(
                history_start=history_start,
                history_end=history_end,
                chunk_days=chunk_days,
            )
        if isinstance(result, dict):
            return result
        return {"batches": 0, "records": 0, "errors": 0}

    @staticmethod
    def _require_uuid(value: object) -> UUID:
        if isinstance(value, UUID):
            return value
        if isinstance(value, str):
            return UUID(value)
        msg = "organization_id must be a UUID"
        raise TypeError(msg)

    @staticmethod
    def _normalize_auth_payload(value: object) -> SmartUpAuthPayload:
        if isinstance(value, SmartUpAuthPayload):
            return value
        if isinstance(value, dict):
            return SmartUpAuthPayload.model_validate(value)
        msg = "payload must be a SmartUpAuthPayload instance or dictionary"
        raise TypeError(msg)


_ENTITY_IMPORT_PLAN: dict[str, tuple[str, ...]] = {
    "customers": ("Legal entities", "Natural persons"),
    "products": (
        "Inventory",
        "Product groups",
        "Producers",
        "Price types",
        "Inventory prices",
        "Service export",
        "Person group export",
        "Return reason export",
    ),
    "sales": ("Orders", "Returns", "Visits", "Client payments"),
    "finance": ("Cash operations", "Bank statements"),
    "stock": (
        "Inventory balance",
        "Stocktaking export",
        "Cross-organizational movement export",
        "Internal movement export",
        "Receipts to warehouse export",
        "Purchase export",
        "Write-off export",
        "Return to suppliers export",
        "Logistics export",
    ),
    "assets": ("Equipment balance", "Movement export", "Request export"),
}

_ENTITY_LABELS: dict[str, str] = {
    "customers": "Контакты",
    "products": "Товары",
    "sales": "Продажи",
    "finance": "Финансы",
    "stock": "Склад",
    "assets": "Активы",
}


def _diff_summary(
    after: SmartUpMigrationSummary,
    before: SmartUpMigrationSummary,
) -> SmartUpMigrationSummary:
    return SmartUpMigrationSummary(
        organizations=max(0, after.organizations - before.organizations),
        businesses=max(0, after.businesses - before.businesses),
        source_systems=max(0, after.source_systems - before.source_systems),
        contacts=max(0, after.contacts - before.contacts),
        sales=max(0, after.sales - before.sales),
        marketing_activities=max(0, after.marketing_activities - before.marketing_activities),
        finance_entries=max(0, after.finance_entries - before.finance_entries),
        records=max(0, after.records - before.records),
        batches=max(0, after.batches - before.batches),
        errors=max(0, after.errors - before.errors),
    )


def _add_summary(
    total: SmartUpMigrationSummary,
    delta: SmartUpMigrationSummary,
) -> SmartUpMigrationSummary:
    return SmartUpMigrationSummary(
        organizations=total.organizations + delta.organizations,
        businesses=total.businesses + delta.businesses,
        source_systems=total.source_systems + delta.source_systems,
        contacts=total.contacts + delta.contacts,
        sales=total.sales + delta.sales,
        marketing_activities=total.marketing_activities + delta.marketing_activities,
        finance_entries=total.finance_entries + delta.finance_entries,
        records=total.records + delta.records,
        batches=total.batches + delta.batches,
        errors=total.errors + delta.errors,
    )
