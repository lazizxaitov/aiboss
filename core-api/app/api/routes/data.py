"""Data Explorer endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.data_explorer import (
    DataExplorerCollection,
    DataExplorerPageResponse,
    DataExplorerService,
    DataExplorerStatsResponse,
)
from app.core.data_layer.factory import get_core_store
from app.integrations.smartup.audit import (
    SmartUpDataIntegrityAuditReport,
    SmartUpDataIntegrityAuditService,
)
from app.integrations.smartup.verification import (
    SmartUpTraceResponse,
    SmartUpVerificationReport,
    SmartUpVerificationService,
)

router = APIRouter()


@router.get("/data/stats", response_model=DataExplorerStatsResponse)
def get_data_stats(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
) -> DataExplorerStatsResponse:
    """Return Data Explorer summary cards and counts."""

    return DataExplorerService(store).build_stats(organization_id=organization_id)


@router.get("/data/overview", response_model=DataExplorerStatsResponse)
def get_data_overview(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
) -> DataExplorerStatsResponse:
    """Return the overview page data for the Data Explorer section."""

    return DataExplorerService(store).build_stats(organization_id=organization_id)


@router.get("/data/coverage", response_model=SmartUpVerificationReport)
def get_data_coverage(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
) -> SmartUpVerificationReport:
    """Return the SmartUp coverage verification report."""

    return SmartUpVerificationService(store).build_coverage_report(organization_id=organization_id)


@router.get("/data/trace/{entity}/{entity_id}", response_model=SmartUpTraceResponse)
def get_data_trace(
    entity: str,
    entity_id: str,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> SmartUpTraceResponse:
    """Return a detailed trace for one SmartUp entity instance."""

    return SmartUpVerificationService(store).trace_entity(entity, entity_id)


@router.get("/data/audit", response_model=SmartUpDataIntegrityAuditReport)
def get_data_integrity_audit(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
) -> SmartUpDataIntegrityAuditReport:
    """Return the consolidated SmartUp data integrity audit."""

    return SmartUpDataIntegrityAuditService(store).build_report(organization_id=organization_id)


@router.get("/data/{collection}", response_model=DataExplorerPageResponse)
def get_data_collection(
    collection: DataExplorerCollection,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DataExplorerPageResponse:
    """Return one paginated Data Explorer collection."""

    if collection == DataExplorerCollection.OVERVIEW:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use /api/v1/data/overview for the overview page.",
        )
    return DataExplorerService(store).build_page(
        collection,
        organization_id=organization_id,
        page=page,
        page_size=page_size,
    )
