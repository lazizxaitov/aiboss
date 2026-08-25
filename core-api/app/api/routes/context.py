"""Global organization context endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.organization_context import (
    AnalyticsContextState,
    AnalyticsContextUpdate,
    OrganizationContextService,
)

router = APIRouter()


@router.get("/organization-context", response_model=AnalyticsContextState)
def get_organization_context(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> AnalyticsContextState:
    """Return the persisted global organization context."""

    return OrganizationContextService(store).get_context()


@router.put("/organization-context", response_model=AnalyticsContextState)
def update_organization_context(
    payload: AnalyticsContextUpdate,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> AnalyticsContextState:
    """Persist a new global organization context."""

    return OrganizationContextService(store).update_context(payload)


@router.delete("/organization-context", response_model=AnalyticsContextState)
def reset_organization_context(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> AnalyticsContextState:
    """Reset the global organization context to its defaults."""

    return OrganizationContextService(store).reset_context()
