"""Canonical Customers / Customer 360 business workspace endpoints."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.routes.analytics import _build_query
from app.core.analytics.models import AnalyticsComparisonMode, AnalyticsPeriodPreset
from app.core.customer_workspace.models import (
    CustomerWorkspaceDetail,
    CustomerWorkspaceQuery,
    CustomerWorkspaceResponse,
    CustomerWorkspaceSortBy,
    CustomerWorkspaceSortOrder,
)
from app.core.customer_workspace.service import CustomerWorkspaceService
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store

router = APIRouter(prefix="/customers")


@router.get("", response_model=CustomerWorkspaceResponse)
def get_customers_workspace(
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
    has_sales: Annotated[bool | None, Query()] = None,
    has_payments: Annotated[bool | None, Query()] = None,
    has_returns: Annotated[bool | None, Query()] = None,
    has_visits: Annotated[bool | None, Query()] = None,
    customer_type: Annotated[list[str] | None, Query()] = None,
    sales_rep: Annotated[list[str] | None, Query()] = None,
    working_zone: Annotated[list[str] | None, Query()] = None,
    data_quality: Annotated[list[str] | None, Query()] = None,
    revenue_min: Annotated[Decimal | None, Query()] = None,
    revenue_max: Annotated[Decimal | None, Query()] = None,
    sort_by: Annotated[CustomerWorkspaceSortBy, Query()] = CustomerWorkspaceSortBy.REVENUE,
    sort_order: Annotated[CustomerWorkspaceSortOrder, Query()] = CustomerWorkspaceSortOrder.DESC,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> CustomerWorkspaceResponse:
    analytics_query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    workspace_query = CustomerWorkspaceQuery(
        search=search,
        has_sales=has_sales,
        has_payments=has_payments,
        has_returns=has_returns,
        has_visits=has_visits,
        customer_type=customer_type or [],
        sales_rep=sales_rep or [],
        working_zone=working_zone or [],
        data_quality=data_quality or [],
        revenue_min=revenue_min,
        revenue_max=revenue_max,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return CustomerWorkspaceService(store).list_workspace(analytics_query, workspace_query)


@router.get("/{customer_id}", response_model=CustomerWorkspaceDetail)
def get_customer_workspace_detail(
    customer_id: UUID,
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
) -> CustomerWorkspaceDetail:
    analytics_query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    detail = CustomerWorkspaceService(store).get_detail(customer_id, analytics_query)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer workspace record not found",
        )
    return detail
