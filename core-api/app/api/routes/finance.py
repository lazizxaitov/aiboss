"""Canonical Finance workspace endpoints."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.routes.analytics import _build_query
from app.core.analytics.models import AnalyticsComparisonMode, AnalyticsPeriodPreset
from app.core.data_layer.canonical_v2 import CanonicalDataQualityStatus
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.finance_workspace.models import (
    FinanceWorkspaceDirection,
    FinanceWorkspaceQuery,
    FinanceWorkspaceResponse,
    FinanceWorkspaceSortBy,
    FinanceWorkspaceSortOrder,
    FinanceWorkspaceView,
)
from app.core.finance_workspace.service import FinanceWorkspaceService

router = APIRouter(prefix="/finance")


@router.get("", response_model=FinanceWorkspaceResponse)
def get_finance_workspace(
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
    view: Annotated[FinanceWorkspaceView, Query()] = FinanceWorkspaceView.OVERVIEW,
    search: Annotated[str | None, Query()] = None,
    direction: Annotated[list[FinanceWorkspaceDirection] | None, Query()] = None,
    operation_type: Annotated[list[str] | None, Query()] = None,
    payment_type: Annotated[list[str] | None, Query()] = None,
    counterparty: Annotated[list[str] | None, Query()] = None,
    account: Annotated[list[str] | None, Query()] = None,
    currency: Annotated[list[str] | None, Query()] = None,
    data_quality: Annotated[list[CanonicalDataQualityStatus] | None, Query()] = None,
    amount_min: Annotated[Decimal | None, Query()] = None,
    amount_max: Annotated[Decimal | None, Query()] = None,
    sort_by: Annotated[FinanceWorkspaceSortBy, Query()] = FinanceWorkspaceSortBy.DATE,
    sort_order: Annotated[
        FinanceWorkspaceSortOrder,
        Query(),
    ] = FinanceWorkspaceSortOrder.DESC,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> FinanceWorkspaceResponse:
    analytics_query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    workspace_query = FinanceWorkspaceQuery(
        view=view,
        search=search,
        direction=direction or [],
        operation_type=operation_type or [],
        payment_type=payment_type or [],
        counterparty=counterparty or [],
        account=account or [],
        currency=currency or [],
        data_quality=data_quality or [],
        amount_min=amount_min,
        amount_max=amount_max,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return FinanceWorkspaceService(store).list_workspace(analytics_query, workspace_query)
