"""Ranking and grouping logic for deterministic AI insights."""

from __future__ import annotations

from collections import defaultdict

from app.core.ai_analytics.models import (
    AIDashboardFeedItem,
    AIDashboardSemanticSize,
    AIInsightCard,
    AIInsightSeverity,
    AIInsightType,
    AISignal,
)
from app.core.analytics.models import DashboardWidgetType


def rank_signals(signals: list[AISignal]) -> list[AISignal]:
    """Sort signals by deterministic business priority."""

    return sorted(
        signals,
        key=lambda signal: (
            -_severity_score(signal.severity),
            -_impact_score(signal),
            -signal.confidence,
            signal.signal_type.value,
            signal.signal_id,
        ),
    )


def deduplicate_signals(signals: list[AISignal]) -> list[AISignal]:
    """Collapse duplicate underlying events for the same entity and metric."""

    grouped: dict[tuple[str, str | None, str | None, str], list[AISignal]] = defaultdict(list)
    for signal in signals:
        grouped[
            (
                signal.entity_type or "global",
                signal.entity_id,
                str(signal.organization_id) if signal.organization_id else None,
                signal.metric_key,
            )
        ].append(signal)

    deduplicated: list[AISignal] = []
    for items in grouped.values():
        items = rank_signals(items)
        deduplicated.append(items[0])
    return rank_signals(deduplicated)


def build_dashboard_feed(insights: list[AIInsightCard]) -> list[AIDashboardFeedItem]:
    """Build semantic widget manifest for the future layout engine."""

    return [
        AIDashboardFeedItem(
            insight_id=insight.id,
            priority=insight.priority,
            suggested_widget_type=_widget_type_for_insight(insight),
            suggested_size=_size_hint_for_insight(insight),
        )
        for insight in insights
    ]


def _severity_score(severity: AIInsightSeverity) -> int:
    return {
        AIInsightSeverity.CRITICAL: 5,
        AIInsightSeverity.HIGH: 4,
        AIInsightSeverity.MEDIUM: 3,
        AIInsightSeverity.LOW: 2,
        AIInsightSeverity.INFO: 1,
    }[severity]


def _impact_score(signal: AISignal) -> float:
    values = [
        abs(float(signal.current_value)) if signal.current_value is not None else 0.0,
        abs(float(signal.absolute_change)) if signal.absolute_change is not None else 0.0,
        abs(float(signal.percentage_change)) if signal.percentage_change is not None else 0.0,
    ]
    return max(values)


def _widget_type_for_insight(insight: AIInsightCard) -> DashboardWidgetType:
    try:
        return DashboardWidgetType(insight.widget_type)
    except ValueError:
        if insight.type in {AIInsightType.RISK.value, AIInsightType.DATA_QUALITY.value}:
            return DashboardWidgetType.INVENTORY_ALERT
        if insight.type == AIInsightType.PRODUCT.value:
            return DashboardWidgetType.RANKING
        if insight.type == AIInsightType.FINANCE.value:
            return DashboardWidgetType.AI_RECOMMENDATION
        return DashboardWidgetType.AI_INSIGHT


def _size_hint_for_insight(insight: AIInsightCard) -> AIDashboardSemanticSize:
    widget_type = _widget_type_for_insight(insight)
    if widget_type in {DashboardWidgetType.KPI}:
        return AIDashboardSemanticSize.SMALL
    if widget_type in {DashboardWidgetType.RANKING, DashboardWidgetType.SALES_REP_PERFORMANCE}:
        return AIDashboardSemanticSize.TALL
    if widget_type in {
        DashboardWidgetType.LINE_CHART,
        DashboardWidgetType.BAR_CHART,
        DashboardWidgetType.TABLE,
        DashboardWidgetType.ORGANIZATION_COMPARISON,
    }:
        return AIDashboardSemanticSize.LARGE
    if insight.priority <= 2:
        return AIDashboardSemanticSize.MEDIUM
    return AIDashboardSemanticSize.SMALL
