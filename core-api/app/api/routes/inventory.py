"""Canonical Inventory / Warehouse workspace endpoints."""

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
from app.core.inventory_workspace.models import (
    InventoryWorkspaceCurrentStockDetail,
    InventoryWorkspaceQuery,
    InventoryWorkspaceResponse,
    InventoryWorkspaceSortBy,
    InventoryWorkspaceSortOrder,
    InventoryWorkspaceStockStatus,
    InventoryWorkspaceView,
    InventoryWorkspaceWarehouseDetail,
)
from app.core.inventory_workspace.service import InventoryWorkspaceService

router = APIRouter(prefix="/inventory")


@router.get("", response_model=InventoryWorkspaceResponse)
def get_inventory_workspace(
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
    view: Annotated[InventoryWorkspaceView, Query()] = InventoryWorkspaceView.CURRENT_STOCK,
    search: Annotated[str | None, Query()] = None,
    warehouse_id: Annotated[list[str] | None, Query()] = None,
    product_id: Annotated[list[UUID] | None, Query()] = None,
    category_id: Annotated[list[UUID] | None, Query()] = None,
    stock_status: Annotated[list[InventoryWorkspaceStockStatus] | None, Query()] = None,
    has_stock: Annotated[bool | None, Query()] = None,
    zero_stock: Annotated[bool | None, Query()] = None,
    negative_stock: Annotated[bool | None, Query()] = None,
    data_quality: Annotated[list[CanonicalDataQualityStatus] | None, Query()] = None,
    sort_by: Annotated[
        InventoryWorkspaceSortBy,
        Query(),
    ] = InventoryWorkspaceSortBy.SNAPSHOT_DATE,
    sort_order: Annotated[
        InventoryWorkspaceSortOrder,
        Query(),
    ] = InventoryWorkspaceSortOrder.DESC,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> InventoryWorkspaceResponse:
    analytics_query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    workspace_query = InventoryWorkspaceQuery(
        view=view,
        search=search,
        warehouse_id=warehouse_id or [],
        product_id=product_id or [],
        category_id=category_id or [],
        stock_status=stock_status or [],
        has_stock=has_stock,
        zero_stock=zero_stock,
        negative_stock=negative_stock,
        data_quality=data_quality or [],
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return InventoryWorkspaceService(store).list_workspace(analytics_query, workspace_query)


@router.get(
    "/current-stock/{inventory_balance_id}",
    response_model=InventoryWorkspaceCurrentStockDetail,
)
def get_inventory_current_stock_detail(
    inventory_balance_id: UUID,
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
) -> InventoryWorkspaceCurrentStockDetail:
    analytics_query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    detail = InventoryWorkspaceService(store).get_current_stock_detail(
        inventory_balance_id,
        analytics_query,
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory current stock record not found",
        )
    return detail


@router.get("/warehouses/{warehouse_key}", response_model=InventoryWorkspaceWarehouseDetail)
def get_inventory_warehouse_detail(
    warehouse_key: str,
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
) -> InventoryWorkspaceWarehouseDetail:
    analytics_query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    detail = InventoryWorkspaceService(store).get_warehouse_detail(warehouse_key, analytics_query)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory warehouse record not found",
        )
    return detail
