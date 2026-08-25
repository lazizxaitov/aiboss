"""Provider-assisted AI analytics endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.agents.ceo.analytics import AIAnalyticsAgent
from app.core.ai_analytics.models import (
    AIAnalyticsBriefResponse,
    AIAnalyticsInsightsResponse,
)
from app.core.analytics.models import AnalyticsComparisonMode, AnalyticsPeriodPreset, AnalyticsQuery
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.organization_context import OrganizationContextService

router = APIRouter(prefix="/ai-analytics")


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


@router.get("/brief", response_model=AIAnalyticsBriefResponse)
def get_ai_analytics_brief(
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
) -> AIAnalyticsBriefResponse:
    """Return provider-assisted executive brief with deterministic fallback."""

    result = AIAnalyticsAgent().analyze_canonical(
        store,
        _build_query(
            store,
            organization_id,
            organization_ids,
            date_from,
            date_to,
            period,
            comparison_mode,
        ),
        language=language,
        force_refresh=force_refresh,
    )
    return AIAnalyticsBriefResponse(
        generated_at=result.generated_at,
        executive_brief=result.executive_brief,
        provider_status=result.provider_status,
        cache_metadata=result.cache_metadata,
        rejected_provider_insights=result.rejected_provider_insights,
    )


@router.get("/insights", response_model=AIAnalyticsInsightsResponse)
def get_ai_analytics_insights(
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
) -> AIAnalyticsInsightsResponse:
    """Return validated provider-assisted insight set and dashboard feed."""

    result = AIAnalyticsAgent().analyze_canonical(
        store,
        _build_query(
            store,
            organization_id,
            organization_ids,
            date_from,
            date_to,
            period,
            comparison_mode,
        ),
        language=language,
        force_refresh=force_refresh,
    )
    return AIAnalyticsInsightsResponse(
        generated_at=result.generated_at,
        top_insights=result.top_insights,
        watchlist=result.watchlist,
        opportunities=result.opportunities,
        data_warnings=result.data_warnings,
        dashboard_feed=result.dashboard_feed,
        provider_status=result.provider_status,
        cache_metadata=result.cache_metadata,
        rejected_provider_insights=result.rejected_provider_insights,
    )
