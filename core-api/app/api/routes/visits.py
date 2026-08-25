"""Canonical Visits / Field Sales workspace endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.routes.analytics import _build_query
from app.core.analytics.models import AnalyticsComparisonMode, AnalyticsPeriodPreset
from app.core.data_layer.canonical_v2 import CanonicalDataQualityStatus
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.visits_workspace.models import (
    VisitsWorkspaceDetail,
    VisitsWorkspaceQuery,
    VisitsWorkspaceResponse,
    VisitsWorkspaceSortBy,
    VisitsWorkspaceSortOrder,
    VisitsWorkspaceTab,
)
from app.core.visits_workspace.service import VisitsWorkspaceService

router = APIRouter(prefix="/visits")


@router.get("", response_model=VisitsWorkspaceResponse)
def get_visits_workspace(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
    organization_ids: Annotated[list[UUID] | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    period: Annotated[AnalyticsPeriodPreset, Query()] = AnalyticsPeriodPreset.LAST_30_DAYS,
    comparison_mode: Annotated[
        AnalyticsComparisonMode,
        Query(),
    ] = AnalyticsComparisonMode.PREVIOUS_PERIOD,
    tab: Annotated[VisitsWorkspaceTab, Query()] = VisitsWorkspaceTab.VISITS,
    search: Annotated[str | None, Query()] = None,
    customer: Annotated[list[str] | None, Query()] = None,
    sales_rep: Annotated[list[str] | None, Query()] = None,
    working_zone: Annotated[list[str] | None, Query()] = None,
    status_filter: Annotated[list[str] | None, Query(alias="status")] = None,
    planned: Annotated[list[str] | None, Query()] = None,
    data_quality: Annotated[list[CanonicalDataQualityStatus] | None, Query()] = None,
    sort_by: Annotated[VisitsWorkspaceSortBy, Query()] = VisitsWorkspaceSortBy.DATE,
    sort_order: Annotated[VisitsWorkspaceSortOrder, Query()] = VisitsWorkspaceSortOrder.DESC,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> VisitsWorkspaceResponse:
    analytics_query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    workspace_query = VisitsWorkspaceQuery(
        tab=tab,
        search=search,
        customer=customer or [],
        sales_rep=sales_rep or [],
        working_zone=working_zone or [],
        status=status_filter or [],
        planned=planned or [],
        data_quality=data_quality or [],
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return VisitsWorkspaceService(store).list_workspace(analytics_query, workspace_query)


@router.get("/{visit_id}", response_model=VisitsWorkspaceDetail)
def get_visits_workspace_detail(
    visit_id: UUID,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
    organization_ids: Annotated[list[UUID] | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    period: Annotated[AnalyticsPeriodPreset, Query()] = AnalyticsPeriodPreset.LAST_30_DAYS,
    comparison_mode: Annotated[
        AnalyticsComparisonMode,
        Query(),
    ] = AnalyticsComparisonMode.PREVIOUS_PERIOD,
) -> VisitsWorkspaceDetail:
    analytics_query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    detail = VisitsWorkspaceService(store).get_detail(visit_id, analytics_query)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Visits workspace record not found",
        )
    return detail
