"""SmartUp mirror endpoints (admin debug only)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.data_explorer import DataExplorerPageResponse
from app.core.data_layer.factory import get_core_store
from app.integrations.smartup.mirror import SmartUpMirrorService
from app.integrations.smartup.verification import (
    SmartUpTraceResponse,
    SmartUpVerificationReport,
)

router = APIRouter(prefix="/smartup", tags=["SmartUp Admin Debug"])


@router.get("/overview", response_model=SmartUpVerificationReport)
def get_smartup_overview(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
) -> SmartUpVerificationReport:
    return SmartUpMirrorService(store).build_overview(organization_id=organization_id)


@router.get("/coverage", response_model=SmartUpVerificationReport)
def get_smartup_coverage(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
) -> SmartUpVerificationReport:
    return SmartUpMirrorService(store).build_coverage(organization_id=organization_id)


@router.get("/orders", response_model=DataExplorerPageResponse)
def get_smartup_orders(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DataExplorerPageResponse:
    return SmartUpMirrorService(store).build_orders_page(
        organization_id=organization_id,
        page=page,
        page_size=page_size,
    )


@router.get("/customers", response_model=DataExplorerPageResponse)
def get_smartup_customers(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DataExplorerPageResponse:
    return SmartUpMirrorService(store).build_customers_page(
        organization_id=organization_id,
        page=page,
        page_size=page_size,
    )


@router.get("/products", response_model=DataExplorerPageResponse)
def get_smartup_products(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DataExplorerPageResponse:
    return SmartUpMirrorService(store).build_products_page(
        organization_id=organization_id,
        page=page,
        page_size=page_size,
    )


@router.get("/visits", response_model=DataExplorerPageResponse)
def get_smartup_visits(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DataExplorerPageResponse:
    return SmartUpMirrorService(store).build_visits_page(
        organization_id=organization_id,
        page=page,
        page_size=page_size,
    )


@router.get("/inventory", response_model=DataExplorerPageResponse)
def get_smartup_inventory(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DataExplorerPageResponse:
    return SmartUpMirrorService(store).build_inventory_page(
        organization_id=organization_id,
        page=page,
        page_size=page_size,
    )


@router.get("/payments", response_model=DataExplorerPageResponse)
def get_smartup_payments(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DataExplorerPageResponse:
    return SmartUpMirrorService(store).build_payments_page(
        organization_id=organization_id,
        page=page,
        page_size=page_size,
    )


@router.get("/returns", response_model=DataExplorerPageResponse)
def get_smartup_returns(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DataExplorerPageResponse:
    return SmartUpMirrorService(store).build_returns_page(
        organization_id=organization_id,
        page=page,
        page_size=page_size,
    )


@router.get("/finance", response_model=DataExplorerPageResponse)
def get_smartup_finance(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DataExplorerPageResponse:
    return SmartUpMirrorService(store).build_finance_page(
        organization_id=organization_id,
        page=page,
        page_size=page_size,
    )


@router.get("/references", response_model=DataExplorerPageResponse)
def get_smartup_references(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DataExplorerPageResponse:
    return SmartUpMirrorService(store).build_references_page(
        organization_id=organization_id,
        page=page,
        page_size=page_size,
    )


@router.get("/raw", response_model=DataExplorerPageResponse)
def get_smartup_raw(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DataExplorerPageResponse:
    return SmartUpMirrorService(store).build_raw_page(
        organization_id=organization_id,
        page=page,
        page_size=page_size,
    )


@router.get("/processing", response_model=DataExplorerPageResponse)
def get_smartup_processing(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DataExplorerPageResponse:
    return SmartUpMirrorService(store).build_processing_page(
        organization_id=organization_id,
        page=page,
        page_size=page_size,
    )


@router.get("/trace/{entity}/{entity_id}", response_model=SmartUpTraceResponse)
def get_smartup_trace(
    entity: str,
    entity_id: str,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> SmartUpTraceResponse:
    return SmartUpMirrorService(store).build_entity_trace(entity, entity_id)
