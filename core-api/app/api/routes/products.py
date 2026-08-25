"""Canonical Products / Product 360 business workspace endpoints."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.routes.analytics import _build_query
from app.core.analytics.models import AnalyticsComparisonMode, AnalyticsPeriodPreset
from app.core.data_layer.canonical_v2 import CanonicalDataQualityStatus
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.product_workspace.models import (
    ProductWorkspaceDetail,
    ProductWorkspaceQuery,
    ProductWorkspaceResponse,
    ProductWorkspaceSortBy,
    ProductWorkspaceSortOrder,
    ProductWorkspaceStockStatus,
)
from app.core.product_workspace.service import ProductWorkspaceService

router = APIRouter(prefix="/products")


@router.get("", response_model=ProductWorkspaceResponse)
def get_products_workspace(
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
    category_id: Annotated[list[UUID] | None, Query()] = None,
    stock_status: Annotated[list[ProductWorkspaceStockStatus] | None, Query()] = None,
    has_sales: Annotated[bool | None, Query()] = None,
    has_returns: Annotated[bool | None, Query()] = None,
    data_quality: Annotated[list[CanonicalDataQualityStatus] | None, Query()] = None,
    revenue_min: Annotated[Decimal | None, Query()] = None,
    revenue_max: Annotated[Decimal | None, Query()] = None,
    sold_units_min: Annotated[Decimal | None, Query()] = None,
    sold_units_max: Annotated[Decimal | None, Query()] = None,
    sort_by: Annotated[ProductWorkspaceSortBy, Query()] = ProductWorkspaceSortBy.REVENUE,
    sort_order: Annotated[
        ProductWorkspaceSortOrder,
        Query(),
    ] = ProductWorkspaceSortOrder.DESC,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ProductWorkspaceResponse:
    analytics_query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    workspace_query = ProductWorkspaceQuery(
        search=search,
        category_id=category_id or [],
        stock_status=stock_status or [],
        has_sales=has_sales,
        has_returns=has_returns,
        data_quality=data_quality or [],
        revenue_min=revenue_min,
        revenue_max=revenue_max,
        sold_units_min=sold_units_min,
        sold_units_max=sold_units_max,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return ProductWorkspaceService(store).list_workspace(analytics_query, workspace_query)


@router.get("/{product_id}", response_model=ProductWorkspaceDetail)
def get_product_workspace_detail(
    product_id: UUID,
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
) -> ProductWorkspaceDetail:
    analytics_query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    detail = ProductWorkspaceService(store).get_detail(product_id, analytics_query)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product workspace record not found",
        )
    return detail
