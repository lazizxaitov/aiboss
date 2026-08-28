"""SmartUp operational endpoints."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.integrations.smartup.bootstrap import (
    SmartUpEnvBootstrapResponse,
    bootstrap_smartup_organizations_from_env,
)
from app.integrations.smartup.diagnostics import (
    SmartUpCompletenessReport,
    SmartUpNormalizationSummaryResponse,
    SmartUpRawDataService,
    SmartUpRawRecordSummary,
    SmartUpReprocessResponse,
)
from app.integrations.smartup.discovery import (
    SmartUpDiscoveryReport,
    SmartUpDiscoveryService,
)
from app.integrations.smartup.operations import (
    SmartUpAccountService,
    SmartUpAuthPayload,
    SmartUpConnectionCheckResponse,
    SmartUpFilialCodeDiscoveryResponse,
    SmartUpHistoryMigrationRequest,
    SmartUpMigrationAllResponse,
    SmartUpMigrationJobResponse,
    SmartUpOrganizationListResponse,
    SmartUpResetResponse,
    SMARTUP_MIGRATION_LOCK,
)
from app.integrations.smartup.live_sync import (
    SmartUpLiveSyncService,
    SmartUpLiveSyncStatus,
    wake_smartup_live_sync,
)
from app.integrations.smartup.models import SmartUpMigrationMode
from app.integrations.smartup.rebuild import (
    SmartUpCoreRebuildReport,
    SmartUpCoreRebuildService,
)

router = APIRouter()


class SmartUpPageSyncRequest(BaseModel):
    page: Literal["sales", "visits", "products", "customers", "inventory", "finance"]


PAGE_DATASETS: dict[str, list[str]] = {
    "sales": ["sales"],
    "visits": ["sales"],
    "products": ["products"],
    "customers": ["customers"],
    "inventory": ["stock"],
    "finance": ["finance"],
}


@router.get("/smartup/live-sync/status", response_model=SmartUpLiveSyncStatus)
def get_smartup_live_sync_status(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> SmartUpLiveSyncStatus:
    """Return the persisted status of the automatic SmartUp sync."""

    return SmartUpLiveSyncService(store).status()


@router.post("/smartup/sync-page", response_model=SmartUpMigrationJobResponse)
def sync_smartup_page(
    payload: SmartUpPageSyncRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> SmartUpMigrationJobResponse:
    """Queue a short recent-window sync for one supported data module."""

    if SMARTUP_MIGRATION_LOCK.locked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SYNC_ALREADY_RUNNING",
        )
    now = datetime.now(UTC)
    migration = SmartUpAuthPayload(
        migration_mode=SmartUpMigrationMode.ONE_DAY_CHECK,
        history_start=now - timedelta(days=1),
        history_end=now,
        datasets=PAGE_DATASETS[payload.page],
    )
    return SmartUpAccountService(target=store).start_migration_job(migration)


@router.post("/smartup/rebuild-core", response_model=SmartUpCoreRebuildReport)
def rebuild_smartup_core(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    dry_run: bool = Query(default=False),
    force: bool = Query(default=False),
    organization_id: UUID | None = None,
    entity_type: str | None = None,
) -> SmartUpCoreRebuildReport:
    service = SmartUpCoreRebuildService(store)
    return service.rebuild_all(
        dry_run=dry_run,
        force=force,
        organization_id=organization_id,
        entity_type=entity_type,
    )


@router.post(
    "/smartup/rebuild-core/organization/{organization_id}",
    response_model=SmartUpCoreRebuildReport,
)
def rebuild_smartup_core_for_organization(
    organization_id: UUID,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    dry_run: bool = Query(default=False),
    force: bool = Query(default=False),
    entity_type: str | None = None,
) -> SmartUpCoreRebuildReport:
    service = SmartUpCoreRebuildService(store)
    return service.rebuild_organization(
        organization_id,
        dry_run=dry_run,
        force=force,
        entity_type=entity_type,
    )


@router.post(
    "/smartup/rebuild-core/{entity_type}",
    response_model=SmartUpCoreRebuildReport,
)
def rebuild_smartup_core_entity(
    entity_type: str,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    dry_run: bool = Query(default=False),
    force: bool = Query(default=False),
    organization_id: UUID | None = None,
) -> SmartUpCoreRebuildReport:
    service = SmartUpCoreRebuildService(store)
    return service.rebuild_entity(
        entity_type,
        dry_run=dry_run,
        force=force,
        organization_id=organization_id,
    )


@router.post(
    "/smartup/raw-records/{record_id}/rebuild-core",
    response_model=SmartUpCoreRebuildReport,
)
def rebuild_smartup_raw_record_core(
    record_id: UUID,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    dry_run: bool = Query(default=False),
    force: bool = Query(default=False),
) -> SmartUpCoreRebuildReport:
    service = SmartUpCoreRebuildService(store)
    try:
        return service.rebuild_raw_record(record_id, dry_run=dry_run, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/smartup/organizations", response_model=SmartUpOrganizationListResponse)
def list_smartup_organizations(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> SmartUpOrganizationListResponse:
    bootstrap_smartup_organizations_from_env(store)
    service = SmartUpAccountService(target=store)
    return SmartUpOrganizationListResponse(items=service.list_organizations())


@router.post("/smartup/organizations")
def create_smartup_organization(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> None:
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="SmartUp organizations are managed from SMARTUP_ORGANIZATIONS only.",
    )


@router.post(
    "/smartup/organizations/sync-from-env",
    response_model=SmartUpEnvBootstrapResponse,
)
def sync_smartup_organizations_from_env(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> SmartUpEnvBootstrapResponse:
    result = bootstrap_smartup_organizations_from_env(store)
    return SmartUpEnvBootstrapResponse(
        loaded=len(result.organizations),
        organizations=result.organizations,
    )


@router.post(
    "/smartup/discover-filial-codes",
    response_model=SmartUpFilialCodeDiscoveryResponse,
)
def discover_smartup_filial_codes(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> SmartUpFilialCodeDiscoveryResponse:
    service = SmartUpAccountService(target=store)
    return service.discover_filial_codes()


@router.get(
    "/smartup/discovery",
    response_model=SmartUpDiscoveryReport,
)
def discover_smartup_data(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
) -> SmartUpDiscoveryReport:
    """Return the SmartUp discovery matrix for AI Business OS."""

    service = SmartUpDiscoveryService(store)
    return service.build_report(organization_id=organization_id)


@router.patch("/smartup/organizations/{organization_id}")
def update_smartup_organization(
    organization_id: UUID,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> None:
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="SmartUp organizations are managed from SMARTUP_ORGANIZATIONS only.",
    )


@router.delete("/smartup/organizations/{organization_id}")
def delete_smartup_organization(
    organization_id: UUID,
) -> None:
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="SmartUp organizations are managed from SMARTUP_ORGANIZATIONS only.",
    )


@router.post(
    "/smartup/reset-data",
    response_model=SmartUpResetResponse,
)
def reset_smartup_data(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> SmartUpResetResponse:
    service = SmartUpAccountService(target=store)
    return service.reset_imported_data()


@router.post(
    "/smartup/organizations/{organization_id}/test",
    response_model=SmartUpConnectionCheckResponse,
)
def test_smartup_organization_connection(
    organization_id: UUID,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    payload: SmartUpAuthPayload,
) -> SmartUpConnectionCheckResponse:
    service = SmartUpAccountService(target=store)
    try:
        response = service.check_connection(organization_id, payload)
        if response.connected:
            wake_smartup_live_sync()
        return response
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/smartup/organizations/{organization_id}/test-connection",
    response_model=SmartUpConnectionCheckResponse,
)
def test_smartup_organization_connection_legacy(
    organization_id: UUID,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    payload: SmartUpAuthPayload,
) -> SmartUpConnectionCheckResponse:
    service = SmartUpAccountService(target=store)
    try:
        response = service.check_connection(organization_id, payload)
        if response.connected:
            wake_smartup_live_sync()
        return response
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/smartup/raw-records",
    response_model=list[SmartUpRawRecordSummary],
)
def list_smartup_raw_records(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: UUID | None = None,
    entity_type: str | None = None,
    batch_id: UUID | None = None,
    processing_status: str | None = Query(default=None),
) -> list[SmartUpRawRecordSummary]:
    service = SmartUpRawDataService(store)
    return service.list_raw_records(
        organization_id=organization_id,
        entity_type=entity_type,
        batch_id=batch_id,
        processing_status=processing_status,
    )


@router.get("/smartup/raw-records/{record_id}")
def get_smartup_raw_record(
    record_id: UUID,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
):
    service = SmartUpRawDataService(store)
    record = service.get_raw_record(record_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Raw record not found")
    return record


@router.post("/smartup/raw-records/{record_id}/reprocess", response_model=SmartUpReprocessResponse)
def reprocess_smartup_raw_record(
    record_id: UUID,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> SmartUpReprocessResponse:
    service = SmartUpRawDataService(store)
    try:
        return service.reprocess_raw_record(record_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/smartup/batches/{batch_id}/normalize",
    response_model=SmartUpNormalizationSummaryResponse,
)
def normalize_smartup_batch(
    batch_id: UUID,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> SmartUpNormalizationSummaryResponse:
    service = SmartUpRawDataService(store)
    return service.normalize_batch(batch_id)


@router.get(
    "/smartup/batches/{batch_id}/normalization-summary",
    response_model=SmartUpNormalizationSummaryResponse,
)
def get_smartup_batch_normalization_summary(
    batch_id: UUID,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> SmartUpNormalizationSummaryResponse:
    service = SmartUpRawDataService(store)
    return service.normalization_summary(batch_id)


@router.get(
    "/smartup/migration/completeness",
    response_model=SmartUpCompletenessReport,
)
def get_smartup_migration_completeness(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: UUID | None = None,
    entity_type: str | None = None,
    migration_mode: str | None = None,
) -> SmartUpCompletenessReport:
    service = SmartUpRawDataService(store)
    mode = None
    if migration_mode:
        from app.integrations.smartup.models import SmartUpMigrationMode

        mode = SmartUpMigrationMode(migration_mode)
    return service.migration_completeness(
        organization_id=organization_id,
        entity_type=entity_type,
        migration_mode=mode,
    )


@router.post(
    "/smartup/organizations/{organization_id}/migrate", response_model=SmartUpMigrationAllResponse
)
def migrate_smartup_organization(
    organization_id: UUID,
    payload: SmartUpAuthPayload,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> SmartUpMigrationAllResponse:
    service = SmartUpAccountService(target=store)
    try:
        return service.migrate_organization(organization_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - transport/runtime safety
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SmartUp migration failed: {exc}",
        ) from exc


@router.post(
    "/smartup/migrate-all",
    response_model=SmartUpMigrationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def migrate_all_smartup_organizations(
    payload: SmartUpAuthPayload,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> SmartUpMigrationJobResponse:
    service = SmartUpAccountService(target=store)
    try:
        return service.start_migration_job(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - transport/runtime safety
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SmartUp migration failed: {exc}",
        ) from exc


@router.get(
    "/smartup/migration-jobs/{job_id}",
    response_model=SmartUpMigrationJobResponse,
)
def get_smartup_migration_job(
    job_id: UUID,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> SmartUpMigrationJobResponse:
    service = SmartUpAccountService(target=store)
    job = service.get_migration_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Migration job not found")
    return job


@router.post("/smartup/test-connection", response_model=SmartUpConnectionCheckResponse)
def test_smartup_connection_legacy(
    payload: SmartUpAuthPayload,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> SmartUpConnectionCheckResponse:
    service = SmartUpAccountService(target=store)
    response = service.check_connection(payload)
    if response.connected:
        wake_smartup_live_sync()
    return response


@router.post("/smartup/migration/history", response_model=SmartUpMigrationAllResponse)
def migrate_smartup_history_legacy(
    payload: SmartUpHistoryMigrationRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> SmartUpMigrationAllResponse:
    service = SmartUpAccountService(target=store)
    try:
        with SMARTUP_MIGRATION_LOCK:
            return service.migrate_history(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
