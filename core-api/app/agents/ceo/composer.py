"""Compose AI dashboard widgets from structured analytics and insights."""

from __future__ import annotations

from collections.abc import Sequence
from math import ceil

from app.core.analytics.models import (
    AIDashboardWorkspace,
    AIInsightCard,
    AnalyticsKPI,
    BusinessAnalyticsSnapshot,
    DashboardWidgetPlacement,
    DashboardWidgetType,
)


class AIDashboardComposer:
    """Turn AI insights into a grid-ready dashboard workspace."""

    GRID_COLUMNS = 12

    def compose(
        self,
        snapshot: BusinessAnalyticsSnapshot,
        insights: Sequence[AIInsightCard],
        *,
        locked_widget_ids: set[str] | None = None,
    ) -> AIDashboardWorkspace:
        locked_widget_ids = locked_widget_ids or set()
        kpi_widgets, kpi_rows = self._build_kpi_widgets(snapshot.kpis, locked_widget_ids)
        insight_widgets = self._build_insight_widgets(
            insights,
            locked_widget_ids,
            top_offset=kpi_rows,
        )
        supporting_widgets = self._build_supporting_widgets(
            snapshot,
            insights,
            locked_widget_ids,
            top_offset=kpi_rows + max(1, ceil(len(insights[:5]) / 2)),
        )

        widgets = self._pack_widgets([*kpi_widgets, *insight_widgets, *supporting_widgets])

        return AIDashboardWorkspace(
            period=snapshot.period,
            snapshot=snapshot,
            insights=list(insights)[:10],
            widgets=widgets,
            widget_registry=list(DashboardWidgetType),
        )

    def _build_kpi_widgets(
        self,
        kpis: Sequence[AnalyticsKPI],
        locked_widget_ids: set[str],
    ) -> tuple[list[DashboardWidgetPlacement], int]:
        widgets: list[DashboardWidgetPlacement] = []
        visible_kpis = list(kpis[:12])
        for index, kpi in enumerate(visible_kpis):
            widgets.append(
                DashboardWidgetPlacement(
                    widget_id=f"kpi-{kpi.key}",
                    widget_type=DashboardWidgetType.KPI,
                    title=kpi.label,
                    x=(index % 6) * 2,
                    y=index // 6,
                    w=2,
                    h=1,
                    priority=index + 1,
                    locked=f"kpi-{kpi.key}" in locked_widget_ids,
                    summary=f"{kpi.current_value}",
                    entity_type="kpi",
                    entity_id=kpi.key,
                ),
            )
        return widgets, max(1, ceil(len(visible_kpis) / 6))

    def _build_insight_widgets(
        self,
        insights: Sequence[AIInsightCard],
        locked_widget_ids: set[str],
        *,
        top_offset: int,
    ) -> list[DashboardWidgetPlacement]:
        widgets: list[DashboardWidgetPlacement] = []
        for index, insight in enumerate(insights[:5]):
            widgets.append(
                DashboardWidgetPlacement(
                    widget_id=f"insight-{insight.id}",
                    widget_type=self._widget_type_from_insight(insight),
                    title=insight.title,
                    x=0,
                    y=top_offset,
                    w=8 if index == 0 else 4,
                    h=3 if index == 0 else 2,
                    priority=insight.priority,
                    locked=f"insight-{insight.id}" in locked_widget_ids,
                    source_insight_id=insight.id,
                    entity_type=insight.entity_type,
                    entity_id=insight.entity_id,
                    summary=insight.summary,
                ),
            )
        return widgets

    def _build_supporting_widgets(
        self,
        snapshot: BusinessAnalyticsSnapshot,
        insights: Sequence[AIInsightCard],
        locked_widget_ids: set[str],
        *,
        top_offset: int,
    ) -> list[DashboardWidgetPlacement]:
        widgets: list[DashboardWidgetPlacement] = []
        widgets.append(
            DashboardWidgetPlacement(
                widget_id="trend-revenue",
                widget_type=DashboardWidgetType.LINE_CHART,
                title="Динамика выручки",
                x=0,
                y=top_offset,
                w=8,
                h=3,
                priority=1,
                locked="trend-revenue" in locked_widget_ids,
                summary="Линия по выручке и сравнению периодов",
                entity_type="sales",
                entity_id="revenue",
            ),
        )
        widgets.append(
            DashboardWidgetPlacement(
                widget_id="ranking-top-products",
                widget_type=DashboardWidgetType.RANKING,
                title="Топ товаров",
                x=8,
                y=top_offset,
                w=4,
                h=max(3, min(6, len(snapshot.top_products) + 1)),
                priority=2,
                locked="ranking-top-products" in locked_widget_ids,
                summary="Самые продаваемые SKU",
                entity_type="products",
                entity_id=None,
            ),
        )
        widgets.append(
            DashboardWidgetPlacement(
                widget_id="table-recent-sales",
                widget_type=DashboardWidgetType.TABLE,
                title="Последние продажи",
                x=0,
                y=top_offset + 3,
                w=8,
                h=max(3, min(6, len(snapshot.sales.top_entities) + 2)),
                priority=3,
                locked="table-recent-sales" in locked_widget_ids,
                summary="Последние продажи и суммы",
                entity_type="sales",
                entity_id=None,
            ),
        )
        widgets.append(
            DashboardWidgetPlacement(
                widget_id="alert-inventory",
                widget_type=DashboardWidgetType.INVENTORY_ALERT,
                title="Складовые риски",
                x=8,
                y=top_offset + 3,
                w=4,
                h=max(3, min(5, len(snapshot.inventory.top_entities) + 1)),
                priority=4,
                locked="alert-inventory" in locked_widget_ids,
                summary="Рискованные позиции по остаткам",
                entity_type="inventory",
                entity_id=None,
            ),
        )
        widgets.append(
            DashboardWidgetPlacement(
                widget_id="ai-recommendations",
                widget_type=DashboardWidgetType.AI_RECOMMENDATION,
                title="AI рекомендации",
                x=0,
                y=top_offset + 6,
                w=8,
                h=max(3, min(5, len(insights[:4]) + 1)),
                priority=5,
                locked="ai-recommendations" in locked_widget_ids,
                summary="Сводные рекомендации AI",
                entity_type="core",
                entity_id=None,
            ),
        )
        widgets.append(
            DashboardWidgetPlacement(
                widget_id="sales-reps-performance",
                widget_type=DashboardWidgetType.SALES_REP_PERFORMANCE,
                title="Торговые представители",
                x=8,
                y=top_offset + 6,
                w=4,
                h=max(3, min(5, len(snapshot.top_sales_reps) + 1)),
                priority=6,
                locked="sales-reps-performance" in locked_widget_ids,
                summary="Эффективность менеджеров",
                entity_type="sales_reps",
                entity_id=None,
            ),
        )
        return widgets

    def _pack_widgets(
        self, widgets: Sequence[DashboardWidgetPlacement]
    ) -> list[DashboardWidgetPlacement]:
        packed: list[DashboardWidgetPlacement] = []
        occupied: set[tuple[int, int]] = set()
        for widget in sorted(
            widgets, key=lambda item: (item.y, item.x, item.priority, item.widget_id)
        ):
            if widget.locked:
                self._mark_occupied(occupied, widget.x, widget.y, widget.w, widget.h)
                packed.append(widget)
                continue
            x, y = self._find_next_slot(occupied, widget.w, widget.h)
            packed.append(widget.model_copy(update={"x": x, "y": y}))
            self._mark_occupied(occupied, x, y, widget.w, widget.h)
        return packed

    def _find_next_slot(
        self,
        occupied: set[tuple[int, int]],
        w: int,
        h: int,
    ) -> tuple[int, int]:
        y = 0
        while True:
            for x in range(0, self.GRID_COLUMNS - w + 1):
                if self._fits(occupied, x, y, w, h):
                    return x, y
            y += 1

    def _fits(self, occupied: set[tuple[int, int]], x: int, y: int, w: int, h: int) -> bool:
        for row in range(y, y + h):
            for column in range(x, x + w):
                if (column, row) in occupied:
                    return False
        return True

    def _mark_occupied(
        self,
        occupied: set[tuple[int, int]],
        x: int,
        y: int,
        w: int,
        h: int,
    ) -> None:
        for row in range(y, y + h):
            for column in range(x, x + w):
                occupied.add((column, row))

    def _widget_type_from_insight(self, insight: AIInsightCard) -> DashboardWidgetType:
        try:
            return DashboardWidgetType(insight.widget_type)
        except ValueError:
            return DashboardWidgetType.AI_INSIGHT
