"""Deterministic business analytics endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.analytics.engine import BusinessAnalyticsEngine
from app.core.analytics.models import (
    AnalyticsBusinessSnapshot,
    AnalyticsComparisonMode,
    AnalyticsCustomerReport,
    AnalyticsFinanceReport,
    AnalyticsInventoryReport,
    AnalyticsOrganizationReport,
    AnalyticsPeriodPreset,
    AnalyticsProductReport,
    AnalyticsQuery,
    AnalyticsSalesReport,
    AnalyticsSalesRepReport,
    AnalyticsSummaryResponse,
    AnalyticsVisitReport,
)
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.organization_context import OrganizationContextService

router = APIRouter(prefix="/analytics")


def _build_query(
    store: CoreDataStore,
    organization_id: UUID | None,
    organization_ids: list[UUID] | None,
    date_from: date | None,
    date_to: date | None,
    period: AnalyticsPeriodPreset,
    comparison_mode: AnalyticsComparisonMode,
) -> AnalyticsQuery:
    selected_ids = list(dict.fromkeys(organization_ids or []))
    if organization_id is not None:
        selected_ids = [organization_id]
    elif not selected_ids:
        selected_ids = OrganizationContextService(store).resolve_organization_ids() or []

    resolved_organization_id = organization_id
    if resolved_organization_id is None and len(selected_ids) == 1:
        resolved_organization_id = selected_ids[0]

    return AnalyticsQuery(
        organization_id=resolved_organization_id,
        organization_ids=selected_ids,
        date_from=date_from,
        date_to=date_to,
        period=period,
        comparison_mode=comparison_mode,
    )


@router.get("/summary", response_model=AnalyticsSummaryResponse)
def get_analytics_summary(
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
) -> AnalyticsSummaryResponse:
    """Return the executive analytics summary."""

    query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    return BusinessAnalyticsEngine(store).build_summary(query)


@router.get("/sales", response_model=AnalyticsSalesReport)
def get_analytics_sales(
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
) -> AnalyticsSalesReport:
    """Return sales analytics."""

    query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    return BusinessAnalyticsEngine(store).build_sales(query)


@router.get("/products", response_model=AnalyticsProductReport)
def get_analytics_products(
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
) -> AnalyticsProductReport:
    """Return product analytics."""

    query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    return BusinessAnalyticsEngine(store).build_products(query)


@router.get("/customers", response_model=AnalyticsCustomerReport)
def get_analytics_customers(
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
) -> AnalyticsCustomerReport:
    """Return customer analytics."""

    query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    return BusinessAnalyticsEngine(store).build_customers(query)


@router.get("/inventory", response_model=AnalyticsInventoryReport)
def get_analytics_inventory(
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
) -> AnalyticsInventoryReport:
    """Return inventory analytics."""

    query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    return BusinessAnalyticsEngine(store).build_inventory(query)


@router.get("/organizations", response_model=AnalyticsOrganizationReport)
def get_analytics_organizations(
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
) -> AnalyticsOrganizationReport:
    """Return organization analytics."""

    query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    return BusinessAnalyticsEngine(store).build_organizations(query)


@router.get("/sales-reps", response_model=AnalyticsSalesRepReport)
def get_analytics_sales_reps(
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
) -> AnalyticsSalesRepReport:
    """Return sales-representative analytics."""

    query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    return BusinessAnalyticsEngine(store).build_sales_reps(query)


@router.get("/visits", response_model=AnalyticsVisitReport)
def get_analytics_visits(
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
) -> AnalyticsVisitReport:
    """Return visit analytics."""

    query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    return BusinessAnalyticsEngine(store).build_visits(query)


@router.get("/finance", response_model=AnalyticsFinanceReport)
def get_analytics_finance(
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
) -> AnalyticsFinanceReport:
    """Return finance analytics."""

    query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    return BusinessAnalyticsEngine(store).build_finance(query)


@router.get("/snapshot", response_model=AnalyticsBusinessSnapshot)
def get_analytics_snapshot(
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
) -> AnalyticsBusinessSnapshot:
    """Return the unified analytics snapshot."""

    query = _build_query(
        store,
        organization_id,
        organization_ids,
        date_from,
        date_to,
        period,
        comparison_mode,
    )
    return BusinessAnalyticsEngine(store).build_snapshot(query)
