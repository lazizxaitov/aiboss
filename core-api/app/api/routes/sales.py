"""Canonical Sales / Orders business workspace endpoints."""

from __future__ import annotations

from datetime import date
from logging import getLogger
from time import monotonic
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.routes.analytics import _build_query
from app.core.analytics.models import AnalyticsComparisonMode, AnalyticsPeriodPreset
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.sales_workspace.models import (
    SalesWorkspaceDetail,
    SalesWorkspaceQuery,
    SalesWorkspaceResponse,
    SalesWorkspaceSortBy,
    SalesWorkspaceSortOrder,
)
from app.core.sales_workspace.service import SalesWorkspaceService

router = APIRouter(prefix="/sales")
logger = getLogger(__name__)


@router.get("", response_model=SalesWorkspaceResponse)
def get_sales_workspace(
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
    search: Annotated[str | None, Query()] = None,
    status_filter: Annotated[list[str] | None, Query(alias="status")] = None,
    customer: Annotated[list[str] | None, Query()] = None,
    product: Annotated[str | None, Query()] = None,
    sales_rep: Annotated[list[str] | None, Query()] = None,
    working_zone: Annotated[list[str] | None, Query()] = None,
    realised: Annotated[bool | None, Query()] = None,
    has_returns: Annotated[bool | None, Query()] = None,
    data_quality: Annotated[list[str] | None, Query()] = None,
    amount_min: Annotated[Decimal | None, Query()] = None,
    amount_max: Annotated[Decimal | None, Query()] = None,
    sort_by: Annotated[SalesWorkspaceSortBy, Query()] = SalesWorkspaceSortBy.BUSINESS_DATE,
    sort_order: Annotated[SalesWorkspaceSortOrder, Query()] = SalesWorkspaceSortOrder.DESC,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> SalesWorkspaceResponse:
    analytics_query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    workspace_query = SalesWorkspaceQuery(
        search=search,
        status=status_filter or [],
        customer=customer or [],
        product=product,
        sales_rep=sales_rep or [],
        working_zone=working_zone or [],
        realised=realised,
        has_returns=has_returns,
        data_quality=data_quality or [],
        amount_min=amount_min,
        amount_max=amount_max,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    started_at = monotonic()
    response = SalesWorkspaceService(store).list_workspace(analytics_query, workspace_query)
    elapsed_ms = (monotonic() - started_at) * 1000
    logger.info(
        "BUSINESS_API_LATENCY endpoint=sales query_ms=%.2f serialization_ms=not_measured total_ms=%.2f rows=%s",
        elapsed_ms,
        elapsed_ms,
        len(response.rows),
    )
    return response


@router.get("/{record_id}", response_model=SalesWorkspaceDetail)
def get_sales_workspace_detail(
    record_id: UUID,
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
) -> SalesWorkspaceDetail:
    analytics_query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    detail = SalesWorkspaceService(store).get_detail(record_id, analytics_query)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sales workspace record not found"
        )
    return detail
