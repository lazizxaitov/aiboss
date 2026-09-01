"""Dashboard endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

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
from app.core.analytics.widget_builder import WidgetBuilderService
from app.core.auto_business_analytics import AutoBusinessAnalyticsService, AutoAnalyticsRun, apply_dashboard_plan
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

DASHBOARD_LAUNCHER_STATE_KEY = "dashboard:launcher_state:v1"


class DashboardLauncherState(BaseModel):
    """Persistent user dashboard layout and custom-widget placement."""

    state: dict[str, Any] = Field(default_factory=dict)
    custom_widget_ids: list[str] = Field(default_factory=list)


def _read_launcher_state(store: CoreDataStore) -> DashboardLauncherState:
    setting = store.get_app_setting(DASHBOARD_LAUNCHER_STATE_KEY)
    if setting is None or not isinstance(setting.setting_value, dict):
        return DashboardLauncherState()
    value = setting.setting_value
    raw_state = value.get("state")
    raw_ids = value.get("custom_widget_ids")
    return DashboardLauncherState(
        state=raw_state if isinstance(raw_state, dict) else {},
        custom_widget_ids=list(dict.fromkeys(item for item in raw_ids or [] if isinstance(item, str))),
    )


@router.get("/dashboard/launcher-state", response_model=DashboardLauncherState)
def get_dashboard_launcher_state(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> DashboardLauncherState:
    return _read_launcher_state(store)


@router.put("/dashboard/launcher-state", response_model=DashboardLauncherState)
def save_dashboard_launcher_state(
    payload: DashboardLauncherState,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> DashboardLauncherState:
    normalized = DashboardLauncherState(
        state=payload.state,
        custom_widget_ids=list(dict.fromkeys(payload.custom_widget_ids)),
    )
    from app.core.data_layer.entities import AppSetting

    now = datetime.now(UTC)
    store.upsert_app_setting(
        AppSetting(
            setting_key=DASHBOARD_LAUNCHER_STATE_KEY,
            setting_value=normalized.model_dump(mode="json"),
            metadata={"scope": "owner", "kind": "dashboard_launcher_state"},
            created_at=now,
            updated_at=now,
        ),
    )
    return normalized


@router.get("/dashboard/auto-analysis/latest", response_model=AutoAnalyticsRun | None)
def get_latest_auto_analysis(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> AutoAnalyticsRun | None:
    return AutoBusinessAnalyticsService(store).latest_successful()


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
    custom_widget_ids: Annotated[list[str] | None, Query()] = None,
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
    analytics_engine = BusinessAnalyticsEngine(store)
    ai_result = AIAnalyticsAgent().analyze_canonical(
        store,
        query,
        language=language,
        force_refresh=force_refresh,
        include_provider=False,
        engine=analytics_engine,
    )
    preferences = _build_manifest_preferences(
        pinned_widget_ids=pinned_widget_ids,
        hidden_widget_ids=hidden_widget_ids,
        locked_position_widget_ids=locked_position_widget_ids,
        locked_size_widget_ids=locked_size_widget_ids,
    )
    sales_report = analytics_engine.build_sales(query)
    manifest = DashboardManifestComposerService().compose(
        snapshot=ai_result.snapshot,
        ai_result=ai_result,
        sales_report=sales_report,
        preferences=preferences,
        language=language,
        force_refresh=force_refresh,
    ).model_copy(deep=True)
    # A failed or running retry must not hide the last successful AI analysis.
    # The dashboard should continue showing the latest usable result while the
    # next role-routed business analytics run is in progress.
    manifest = apply_dashboard_plan(manifest, AutoBusinessAnalyticsService(store).latest_successful())
    custom_widgets_service = WidgetBuilderService(store)
    custom_widgets = custom_widgets_service.append_custom_widgets(
        manifest.widgets,
        organization_ids=selected_organization_ids,
        widget_ids=custom_widget_ids or [],
    )
    if custom_widgets != manifest.widgets:
        manifest.widgets = custom_widgets
        manifest.layout_policy.permanent_widget_ids = list(
            dict.fromkeys(
                [
                    *manifest.layout_policy.permanent_widget_ids,
                    *[widget.widget_id for widget in custom_widgets if widget.widget_id not in manifest.layout_policy.permanent_widget_ids],
                ],
            ),
        )
        manifest.layout_policy.notes = [
            *manifest.layout_policy.notes,
            "User-created widgets from AI Widget Builder are included.",
        ]
    return manifest
