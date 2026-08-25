"""Dashboard endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.agents.ceo import AIAnalyticsAgent, AIDashboardComposer
from app.core.analytics.dashboard_manifest import DashboardManifest, UserDashboardPreferences
from app.core.analytics.dashboard_manifest_service import DashboardManifestComposerService
from app.core.analytics.engine import BusinessAnalyticsEngine
from app.core.analytics.models import (
    AIDashboardWorkspace,
    AnalyticsComparisonMode,
    AnalyticsPeriodPreset,
    AnalyticsQuery,
)
from app.core.analytics.snapshot import BusinessAnalyticsSnapshotService
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.dashboard import (
    DashboardOverviewResponse,
    DashboardPeriod,
    build_dashboard_overview,
)
from app.core.data_layer.entities import MarketingChannel
from app.core.data_layer.factory import get_core_store
from app.core.organization_context import OrganizationContextService

router = APIRouter()


def _build_manifest_preferences(
    *,
    pinned_widget_ids: list[str] | None,
    hidden_widget_ids: list[str] | None,
    locked_position_widget_ids: list[str] | None,
    locked_size_widget_ids: list[str] | None,
) -> UserDashboardPreferences:
    return UserDashboardPreferences(
        pinned_widget_ids=list(dict.fromkeys(pinned_widget_ids or [])),
        hidden_widget_ids=list(dict.fromkeys(hidden_widget_ids or [])),
        locked_position_widget_ids=list(dict.fromkeys(locked_position_widget_ids or [])),
        locked_size_widget_ids=list(dict.fromkeys(locked_size_widget_ids or [])),
    )


@router.get("/dashboard/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    business_id: Annotated[UUID | None, Query()] = None,
    organization_id: Annotated[UUID | None, Query()] = None,
    organization_ids: Annotated[list[UUID] | None, Query()] = None,
    period: Annotated[DashboardPeriod, Query()] = DashboardPeriod.LAST_12_MONTHS,
    channel: Annotated[MarketingChannel | None, Query()] = None,
) -> DashboardOverviewResponse:
    """Return a dashboard-ready overview of the core data layer."""

    context = OrganizationContextService(store)
    selected_organization_ids = context.resolve_organization_ids(
        organization_id=organization_id,
        organization_ids=organization_ids,
    )
    return build_dashboard_overview(
        store,
        business_id=business_id,
        organization_ids=selected_organization_ids,
        period=period,
        channel=channel,
    )


@router.get("/dashboard/executive-workspace", response_model=AIDashboardWorkspace)
def get_dashboard_executive_workspace(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    business_id: Annotated[UUID | None, Query()] = None,
    organization_id: Annotated[UUID | None, Query()] = None,
    organization_ids: Annotated[list[UUID] | None, Query()] = None,
    period: Annotated[DashboardPeriod, Query()] = DashboardPeriod.LAST_12_MONTHS,
) -> AIDashboardWorkspace:
    """Return the AI executive workspace payload for the dashboard."""

    context = OrganizationContextService(store)
    selected_organization_ids = context.resolve_organization_ids(
        organization_id=organization_id,
        organization_ids=organization_ids,
    )
    snapshot = BusinessAnalyticsSnapshotService(store).build_snapshot(
        business_id=business_id,
        organization_ids=selected_organization_ids,
        period_key=period.value,
    )
    insights = AIAnalyticsAgent().generate_insights(snapshot)
    return AIDashboardComposer().compose(snapshot, insights)


@router.get("/dashboard/manifest", response_model=DashboardManifest)
def get_dashboard_manifest(
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
    language: Annotated[str, Query()] = "ru",
    force_refresh: Annotated[bool, Query()] = False,
    pinned_widget_ids: Annotated[list[str] | None, Query()] = None,
    hidden_widget_ids: Annotated[list[str] | None, Query()] = None,
    locked_position_widget_ids: Annotated[list[str] | None, Query()] = None,
    locked_size_widget_ids: Annotated[list[str] | None, Query()] = None,
) -> DashboardManifest:
    """Return the semantic dashboard manifest for the future layout engine."""

    context = OrganizationContextService(store)
    selected_organization_ids = context.resolve_organization_ids(
        organization_id=organization_id,
        organization_ids=organization_ids,
    ) or []
    resolved_organization_id = organization_id
    if resolved_organization_id is None and len(selected_organization_ids) == 1:
        resolved_organization_id = selected_organization_ids[0]

    query = AnalyticsQuery(
        organization_id=resolved_organization_id,
        organization_ids=selected_organization_ids,
        date_from=date_from,
        date_to=date_to,
        period=period,
        comparison_mode=comparison_mode,
    )
    ai_result = AIAnalyticsAgent().analyze_canonical(
        store,
        query,
        language=language,
        force_refresh=force_refresh,
    )
    preferences = _build_manifest_preferences(
        pinned_widget_ids=pinned_widget_ids,
        hidden_widget_ids=hidden_widget_ids,
        locked_position_widget_ids=locked_position_widget_ids,
        locked_size_widget_ids=locked_size_widget_ids,
    )
    sales_report = BusinessAnalyticsEngine(store).build_sales(query)
    return DashboardManifestComposerService().compose(
        snapshot=ai_result.snapshot,
        ai_result=ai_result,
        sales_report=sales_report,
        preferences=preferences,
        language=language,
        force_refresh=force_refresh,
    )
