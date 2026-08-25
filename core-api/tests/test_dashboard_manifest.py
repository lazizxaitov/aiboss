"""Tests for Phase 3D dashboard manifest composer."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.agents.ceo.analytics import AIAnalyticsAgent
from app.api.routes.dashboard import get_core_store
from app.core.ai_analytics.models import AIInsightSeverity
from app.core.analytics.dashboard_manifest import DashboardSemanticSize, UserDashboardPreferences
from app.core.analytics.dashboard_manifest_service import DashboardManifestComposerService
from app.core.analytics.engine import BusinessAnalyticsEngine
from app.core.analytics.models import (
    AIInsightCard,
    AnalyticsComparisonMode,
    AnalyticsPeriodPreset,
    AnalyticsQuery,
)
from app.main import app
from tests.test_ai_analytics_seed import seed_ai_analytics_store


def _build_manifest(**preferences):
    store, org_one, org_two = seed_ai_analytics_store()
    sales_report = BusinessAnalyticsEngine(store).build_sales(
        AnalyticsQuery(
            organization_ids=[org_one.organization_id, org_two.organization_id],
            period=AnalyticsPeriodPreset.LAST_30_DAYS,
            comparison_mode=AnalyticsComparisonMode.PREVIOUS_PERIOD,
        )
    )
    ai_result = AIAnalyticsAgent().analyze_canonical(
        store,
        AnalyticsQuery(
            organization_ids=[org_one.organization_id, org_two.organization_id],
            period=AnalyticsPeriodPreset.LAST_30_DAYS,
            comparison_mode=AnalyticsComparisonMode.PREVIOUS_PERIOD,
        ),
        language="ru",
        force_refresh=True,
    )
    manifest = DashboardManifestComposerService().compose(
        snapshot=ai_result.snapshot,
        ai_result=ai_result,
        sales_report=sales_report,
        preferences=UserDashboardPreferences(**preferences),
        language="ru",
        force_refresh=True,
    )
    return store, org_one, org_two, ai_result, manifest


def test_manifest_validates_without_layout_coordinates() -> None:
    _store, _org_one, _org_two, _result, manifest = _build_manifest()

    assert manifest.validation_errors == []
    assert manifest.layout_policy.manifest_has_no_coordinates is True
    assert manifest.widgets
    assert all(not hasattr(widget, "x") for widget in manifest.widgets)


def test_manifest_content_size_policy_is_semantically_correct() -> None:
    _store, _org_one, _org_two, _result, manifest = _build_manifest()
    widgets = {widget.widget_id: widget for widget in manifest.widgets}

    assert widgets["permanent-revenue"].semantic_size in {
        DashboardSemanticSize.XS,
        DashboardSemanticSize.S,
    }
    assert widgets["trend-revenue"].semantic_size in {
        DashboardSemanticSize.L,
        DashboardSemanticSize.XL,
    }
    assert widgets["top-products"].semantic_size in {
        DashboardSemanticSize.L,
        DashboardSemanticSize.XL,
    }
    assert widgets["top-products"].supports_internal_scroll is True
    assert widgets["organization-comparison"].semantic_size == DashboardSemanticSize.XL


def test_manifest_all_organizations_context_keeps_organization_comparison() -> None:
    store, _org_one, _org_two = seed_ai_analytics_store()
    ai_result = AIAnalyticsAgent().analyze_canonical(
        store,
        AnalyticsQuery(
            period=AnalyticsPeriodPreset.LAST_30_DAYS,
            comparison_mode=AnalyticsComparisonMode.PREVIOUS_PERIOD,
        ),
        language="ru",
        force_refresh=True,
    )
    manifest = DashboardManifestComposerService().compose(
        snapshot=ai_result.snapshot,
        ai_result=ai_result,
        sales_report=BusinessAnalyticsEngine(store).build_sales(
            AnalyticsQuery(
                period=AnalyticsPeriodPreset.LAST_30_DAYS,
                comparison_mode=AnalyticsComparisonMode.PREVIOUS_PERIOD,
            )
        ),
        preferences=UserDashboardPreferences(),
        language="ru",
        force_refresh=True,
    )

    widgets = {widget.widget_id: widget for widget in manifest.widgets}

    assert manifest.context.organization_mode == "ALL"
    assert "organization-comparison" in widgets
    assert widgets["organization-comparison"].semantic_size == DashboardSemanticSize.XL


def test_manifest_respects_hidden_widgets() -> None:
    _store, _org_one, _org_two, _result, manifest = _build_manifest(
        hidden_widget_ids=["data-quality", "watchlist"],
    )
    widget_ids = {widget.widget_id for widget in manifest.widgets}

    assert "data-quality" not in widget_ids
    assert "watchlist" not in widget_ids


def test_manifest_respects_locked_and_pinned_widgets() -> None:
    _store, _org_one, _org_two, _result, manifest = _build_manifest(
        pinned_widget_ids=["permanent-revenue"],
        locked_position_widget_ids=["permanent-revenue"],
        locked_size_widget_ids=["permanent-revenue"],
    )
    revenue = next(widget for widget in manifest.widgets if widget.widget_id == "permanent-revenue")

    assert revenue.pinned is True
    assert revenue.source_type == "USER_PINNED"
    assert revenue.locked_position is True
    assert revenue.locked_size is True
    assert revenue.movable_by_ai is False
    assert revenue.resizable_by_ai is False


def test_manifest_provider_disabled_fallback_still_generates_widgets() -> None:
    _store, _org_one, _org_two, result, manifest = _build_manifest()

    assert result.provider_status is not None
    assert result.provider_status.health == "DISABLED"
    assert result.provider_status.used_fallback is True
    assert manifest.provider_status is not None
    assert manifest.widgets
    assert any(widget.source_type == "AI_DYNAMIC" for widget in manifest.widgets)


def test_manifest_dynamic_signal_widgets_follow_ai_signal_lifecycle() -> None:
    store, org_one, org_two = seed_ai_analytics_store()
    agent = AIAnalyticsAgent()
    preferences = UserDashboardPreferences(
        pinned_widget_ids=["permanent-revenue"],
        locked_position_widget_ids=["permanent-revenue"],
        locked_size_widget_ids=["permanent-revenue"],
    )
    ai_result = agent.analyze_canonical(
        store,
        AnalyticsQuery(
            organization_ids=[org_one.organization_id, org_two.organization_id],
            period=AnalyticsPeriodPreset.LAST_30_DAYS,
            comparison_mode=AnalyticsComparisonMode.PREVIOUS_PERIOD,
        ),
        language="ru",
        force_refresh=True,
    )
    critical_insight = AIInsightCard(
        id="critical-stock-transfer",
        type="INVENTORY",
        severity=AIInsightSeverity.CRITICAL,
        priority=7,
        title="Критичный сигнал склада",
        summary="Нужен срочный перенос остатков между организациями.",
        recommendation="Проверьте transfer opportunity и low stock по филиалам.",
        widget_type="inventory_risk",
        entity_type="inventory",
        entity_id="stock-transfer",
        organization_ids=[org_one.organization_id, org_two.organization_id],
        period=ai_result.snapshot.period,
        generated_at=datetime.now(UTC),
    )
    ai_with_extra_signal = ai_result.model_copy(
        update={"top_insights": [critical_insight, *ai_result.top_insights]},
        deep=True,
    )

    manifest_with_signal = DashboardManifestComposerService().compose(
        snapshot=ai_with_extra_signal.snapshot,
        ai_result=ai_with_extra_signal,
        sales_report=BusinessAnalyticsEngine(store).build_sales(
            AnalyticsQuery(
                organization_ids=[org_one.organization_id, org_two.organization_id],
                period=AnalyticsPeriodPreset.LAST_30_DAYS,
                comparison_mode=AnalyticsComparisonMode.PREVIOUS_PERIOD,
            )
        ),
        preferences=preferences,
        language="ru",
        force_refresh=True,
    )
    manifest_without_signal = DashboardManifestComposerService().compose(
        snapshot=ai_result.snapshot,
        ai_result=ai_result,
        sales_report=BusinessAnalyticsEngine(store).build_sales(
            AnalyticsQuery(
                organization_ids=[org_one.organization_id, org_two.organization_id],
                period=AnalyticsPeriodPreset.LAST_30_DAYS,
                comparison_mode=AnalyticsComparisonMode.PREVIOUS_PERIOD,
            )
        ),
        preferences=preferences,
        language="ru",
        force_refresh=True,
    )

    widgets_with_signal = {widget.widget_id: widget for widget in manifest_with_signal.widgets}
    widgets_without_signal = {
        widget.widget_id: widget for widget in manifest_without_signal.widgets
    }
    revenue_with_signal = widgets_with_signal["permanent-revenue"]
    revenue_without_signal = widgets_without_signal["permanent-revenue"]

    assert "dynamic-critical-stock-transfer" in widgets_with_signal
    assert "dynamic-critical-stock-transfer" not in widgets_without_signal
    assert revenue_with_signal.source_type == "USER_PINNED"
    assert revenue_with_signal.locked_position is True
    assert revenue_with_signal.locked_size is True
    assert revenue_with_signal.movable_by_ai is False
    assert revenue_with_signal.resizable_by_ai is False
    assert revenue_with_signal.priority == revenue_without_signal.priority == 0


def test_manifest_route_returns_semantic_manifest() -> None:
    store, org_one, _org_two = seed_ai_analytics_store()
    app.dependency_overrides[get_core_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get(
            "/api/v1/dashboard/manifest",
            params={
                "organization_id": str(org_one.organization_id),
                "language": "ru",
                "hidden_widget_ids": ["watchlist"],
                "locked_position_widget_ids": ["permanent-revenue"],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["manifest_version"] == "phase-3d-v1"
    assert payload["widget_registry_version"] == "phase-3d-v1"
    assert payload["widgets"]
    assert payload["layout_policy"]["manifest_has_no_coordinates"] is True
    assert "watchlist" not in {widget["widget_id"] for widget in payload["widgets"]}


def test_manifest_trend_revenue_payload_uses_by_date_series() -> None:
    _store, _org_one, _org_two, _result, manifest = _build_manifest()
    trend_widget = next(
        widget for widget in manifest.widgets if widget.widget_id == "trend-revenue"
    )
    series = trend_widget.payload["series"]

    assert series
    assert all("date" in point for point in series)
    assert all("organization_name" not in point for point in series)
