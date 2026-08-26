"""Dashboard manifest composer service for Phase 3D."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from json import dumps
from time import perf_counter
from uuid import UUID

from app.core.ai_analytics.models import AIAnalyticsResult, AIProviderHealth
from app.core.analytics.dashboard_manifest import (
    MANIFEST_VERSION,
    WIDGET_REGISTRY_VERSION,
    DashboardDrilldown,
    DashboardManifest,
    DashboardManifestCacheMetadata,
    DashboardManifestContext,
    DashboardManifestDataQuality,
    DashboardManifestWidget,
    DashboardOrganizationMode,
    DashboardWidgetRegistryEntry,
    DashboardWidgetSourceType,
    UserDashboardPreferences,
    default_widget_registry,
    semantic_size_rank,
)
from app.core.analytics.models import (
    AIInsightCard,
    AnalyticsBusinessSnapshot,
    AnalyticsCustomerItem,
    AnalyticsDataQualityEntry,
    AnalyticsDataStatus,
    AnalyticsDimensionRow,
    AnalyticsInventoryTransferOpportunity,
    AnalyticsMetricValue,
    AnalyticsOrganizationItem,
    AnalyticsProductItem,
    AnalyticsSalesRepItem,
    AnalyticsSalesReport,
    DashboardWidgetType,
)
from app.core.config import settings


class DashboardManifestComposerService:
    """Convert deterministic analytics + AI signals into a stable dashboard manifest."""

    _cache: dict[str, DashboardManifest] = {}

    def __init__(self, registry: list[DashboardWidgetRegistryEntry] | None = None) -> None:
        self.registry = registry or default_widget_registry()
        self.registry_by_type = {entry.widget_type: entry for entry in self.registry}

    def compose(
        self,
        *,
        snapshot: AnalyticsBusinessSnapshot,
        ai_result: AIAnalyticsResult,
        sales_report: AnalyticsSalesReport | None = None,
        preferences: UserDashboardPreferences | None = None,
        language: str = "ru",
        force_refresh: bool = False,
    ) -> DashboardManifest:
        started = perf_counter()
        preferences = preferences or UserDashboardPreferences()
        context = self._build_context(snapshot, language)
        analytics_context_hash = self._analytics_context_hash(snapshot)
        ai_context_hash = self._ai_context_hash(ai_result)
        preferences_hash = self._preferences_hash(preferences)
        cache_key = self._cache_key(
            analytics_context_hash=analytics_context_hash,
            ai_context_hash=ai_context_hash,
            preferences_hash=preferences_hash,
            context=context,
        )

        if not force_refresh:
            cached = self._cache.get(cache_key)
            if cached and cached.cache_metadata and (
                cached.cache_metadata.expires_at is None
                or cached.cache_metadata.expires_at >= datetime.now(UTC)
            ):
                return cached

        widgets = self._build_widgets(snapshot, ai_result, preferences, sales_report)
        validation_errors = self._validate_widgets(widgets, context)
        manifest = DashboardManifest(
            context=context,
            analytics_context_hash=analytics_context_hash,
            ai_context_hash=ai_context_hash,
            widgets=widgets,
            widget_registry=self.registry,
            layout_policy=self._layout_policy(widgets),
            data_quality=self._data_quality(snapshot.data_quality.items, snapshot.validation_notes),
            provider_status=ai_result.provider_status,
            cache_metadata=DashboardManifestCacheMetadata(
                cache_key=cache_key,
                analytics_context_hash=analytics_context_hash,
                ai_context_hash=ai_context_hash,
                preferences_hash=preferences_hash,
                manifest_version=MANIFEST_VERSION,
                widget_registry_version=WIDGET_REGISTRY_VERSION,
                generated_at=datetime.now(UTC),
                expires_at=datetime.now(UTC)
                + timedelta(seconds=settings.ai_analytics_cache_ttl_seconds),
            ),
            validation_errors=validation_errors,
        )
        if manifest.cache_metadata is not None and manifest.provider_status is not None:
            manifest.provider_status.latency_ms = round((perf_counter() - started) * 1000, 2)
        self._cache[cache_key] = manifest
        return manifest

    def _build_context(
        self,
        snapshot: AnalyticsBusinessSnapshot,
        language: str,
    ) -> DashboardManifestContext:
        if not snapshot.query.organization_ids:
            mode = DashboardOrganizationMode.ALL
        elif len(snapshot.query.organization_ids) == 1:
            mode = DashboardOrganizationMode.SINGLE
        else:
            mode = DashboardOrganizationMode.MULTIPLE
        return DashboardManifestContext(
            organization_mode=mode,
            organization_ids=list(snapshot.query.organization_ids),
            organization_names=[item.organization_name for item in snapshot.organization_comparison]
            or [
                item.organization_name
                for item in snapshot.organizations
            ],
            period=snapshot.period,
            language=language,
        )

    def _build_widgets(
        self,
        snapshot: AnalyticsBusinessSnapshot,
        ai_result: AIAnalyticsResult,
        preferences: UserDashboardPreferences,
        sales_report: AnalyticsSalesReport | None,
    ) -> list[DashboardManifestWidget]:
        widgets: list[DashboardManifestWidget] = []
        widgets.extend(self._permanent_kpi_widgets(snapshot, preferences))
        widgets.extend(self._contextual_analytics_widgets(snapshot, preferences, sales_report))
        widgets.extend(self._dynamic_ai_widgets(snapshot, ai_result, preferences))
        filtered = [
            widget
            for widget in widgets
            if widget.widget_id not in preferences.hidden_widget_ids
        ]
        filtered.sort(
            key=lambda item: (
                -int(item.pinned),
                item.priority,
                item.widget_id,
            )
        )
        return filtered

    def _permanent_kpi_widgets(
        self,
        snapshot: AnalyticsBusinessSnapshot,
        preferences: UserDashboardPreferences,
    ) -> list[DashboardManifestWidget]:
        permanent = [
            ("revenue", "Выручка", 1),
            ("orders", "Заказы", 2),
            ("sold_units", "Продано единиц", 3),
            ("average_order", "Средний заказ", 4),
            ("payments_received", "Поступления", 5),
        ]
        widgets: list[DashboardManifestWidget] = []
        for metric_key, title, priority in permanent:
            metric = ai_result_metrics(snapshot).get(metric_key)
            widget = self._widget(
                widget_id=f"permanent-{metric_key}",
                widget_type=DashboardWidgetType.KPI,
                source_type=DashboardWidgetSourceType.PERMANENT,
                title=title,
                metric_keys=[metric_key],
                organization_ids=list(snapshot.query.organization_ids),
                priority=priority,
                priority_reason="Permanent executive KPI",
                preferences=preferences,
                drilldown=DashboardDrilldown(
                    target="analytics",
                    entity_type="metric",
                    entity_id=metric_key,
                    organization_ids=list(snapshot.query.organization_ids),
                    filters={"metric": metric_key},
                ),
                summary=None if metric is None else metric,
                data_status=getattr(snapshot.business, metric_key).data_status,
                payload={
                    "metric": self._serialize_metric_value(getattr(snapshot.business, metric_key)),
                    "metric_key": metric_key,
                },
            )
            widgets.append(widget)
        return widgets

    def _contextual_analytics_widgets(
        self,
        snapshot: AnalyticsBusinessSnapshot,
        preferences: UserDashboardPreferences,
        sales_report: AnalyticsSalesReport | None,
    ) -> list[DashboardManifestWidget]:
        widgets: list[DashboardManifestWidget] = []
        widgets.append(
            self._widget(
                widget_id="trend-revenue",
                widget_type=DashboardWidgetType.LINE_CHART,
                source_type=DashboardWidgetSourceType.PERMANENT,
                title="Динамика выручки",
                subtitle=self._period_label(snapshot),
                metric_keys=["revenue"],
                organization_ids=list(snapshot.query.organization_ids),
                priority=10,
                priority_reason="Core trend widget for executive revenue tracking",
                preferences=preferences,
                drilldown=DashboardDrilldown(
                    target="sales",
                    entity_type="metric",
                    entity_id="revenue",
                    organization_ids=list(snapshot.query.organization_ids),
                    filters={"view": "trend"},
                ),
                summary="Тренд выручки по выбранному периоду.",
                data_status=snapshot.business.revenue.data_status,
                payload={
                    "period_label": self._period_label(snapshot),
                    "metric_key": "revenue",
                    "currency": snapshot.business.revenue.currency,
                    "granularity": self._revenue_series_granularity(sales_report),
                    "series": self._build_revenue_series(snapshot, sales_report),
                    "metric": self._serialize_metric_value(snapshot.business.revenue),
                },
            )
        )

        if snapshot.organization_comparison and len(snapshot.organization_comparison) > 1:
            widgets.append(
                self._widget(
                    widget_id="organization-comparison",
                    widget_type=DashboardWidgetType.ORGANIZATION_COMPARISON,
                    source_type=DashboardWidgetSourceType.PERMANENT,
                    title="Сравнение организаций",
                    metric_keys=["revenue", "orders", "sold_units", "payments_received", "returns"],
                    organization_ids=list(snapshot.query.organization_ids),
                    priority=11,
                    priority_reason="Comparison required for multi-organization context",
                    preferences=preferences,
                    drilldown=DashboardDrilldown(
                        target="organizations",
                        organization_ids=list(snapshot.query.organization_ids),
                        filters={"mode": "comparison"},
                    ),
                    summary="Сравнение выручки, заказов и клиентов по организациям.",
                    data_status=self._worst_status(
                        [item.data_status for item in snapshot.organization_comparison]
                    ),
                    payload={
                        "rows": [
                            self._serialize_organization_item(item)
                            for item in snapshot.organization_comparison
                        ]
                    },
                )
            )

        if snapshot.top_products:
            widgets.append(
                self._widget(
                    widget_id="top-products",
                    widget_type=DashboardWidgetType.PRODUCT_RANKING,
                    source_type=DashboardWidgetSourceType.PERMANENT,
                    title="Топ товаров",
                    metric_keys=["product_revenue", "sold_units", "current_stock"],
                    organization_ids=list(snapshot.query.organization_ids),
                    priority=20,
                    priority_reason="Top products are core executive merchandise view",
                    preferences=preferences,
                    drilldown=DashboardDrilldown(
                        target="products",
                        organization_ids=list(snapshot.query.organization_ids),
                        filters={"ranking": "top"},
                    ),
                    summary="Лидеры по выручке, продажам и остаткам.",
                    data_status=self._worst_status(
                        [item.data_status for item in snapshot.top_products]
                    ),
                    payload={
                        "rows": [
                            self._serialize_product_item(item)
                            for item in snapshot.top_products
                        ]
                    },
                )
            )

        customer_candidates = snapshot.top_customers or snapshot.at_risk_customers
        if customer_candidates:
            widgets.append(
                self._widget(
                    widget_id="customer-watch",
                    widget_type=DashboardWidgetType.CUSTOMER_RANKING,
                    source_type=DashboardWidgetSourceType.PERMANENT,
                    title="Клиенты",
                    metric_keys=["customer_revenue", "orders_count", "days_since_last_order"],
                    organization_ids=list(snapshot.query.organization_ids),
                    priority=21,
                    priority_reason="Customer concentration and risk view",
                    preferences=preferences,
                    drilldown=DashboardDrilldown(
                        target="customers",
                        organization_ids=list(snapshot.query.organization_ids),
                    ),
                    summary="Топ и рискованные клиенты по текущему периоду.",
                    data_status=self._worst_status(
                        [item.data_status for item in customer_candidates]
                    ),
                    payload={
                        "rows": [
                            self._serialize_customer_item(item)
                            for item in customer_candidates[:10]
                        ]
                    },
                )
            )

        if snapshot.low_stock_products or snapshot.stockout_risk_products or snapshot.inventory:
            widgets.append(
                self._widget(
                    widget_id="inventory-risk",
                    widget_type=DashboardWidgetType.INVENTORY_RISK,
                    source_type=DashboardWidgetSourceType.PERMANENT,
                    title="Риски склада",
                    metric_keys=["current_stock", "days_of_stock"],
                    organization_ids=list(snapshot.query.organization_ids),
                    priority=22,
                    priority_reason="Inventory exceptions should remain visible",
                    preferences=preferences,
                    drilldown=DashboardDrilldown(
                        target="inventory",
                        organization_ids=list(snapshot.query.organization_ids),
                    ),
                    summary="Низкий остаток, overstock и transfer opportunities.",
                    data_status=self._inventory_widget_status(snapshot),
                    payload={
                        "low_stock": [
                            self._serialize_product_item(item)
                            for item in snapshot.low_stock_products[:10]
                        ],
                        "overstock": [
                            self._serialize_product_item(item)
                            for item in snapshot.overstock_products[:10]
                        ],
                        "stockout_risk": [
                            self._serialize_product_item(item)
                            for item in snapshot.stockout_risk_products[:10]
                        ],
                        "transfer_opportunities": [
                            self._serialize_inventory_opportunity(item)
                            for item in snapshot.inventory[:10]
                        ],
                    },
                )
            )

        if snapshot.sales_reps or snapshot.visits:
            widgets.append(
                self._widget(
                    widget_id="visit-summary",
                    widget_type=DashboardWidgetType.VISIT_SUMMARY,
                    source_type=DashboardWidgetSourceType.PERMANENT,
                    title="Полевая команда",
                    metric_keys=["visits", "visit_conversion"],
                    organization_ids=list(snapshot.query.organization_ids),
                    priority=23,
                    priority_reason="Visits and sales reps matter in field-sales contexts",
                    preferences=preferences,
                    drilldown=DashboardDrilldown(
                        target="visits",
                        organization_ids=list(snapshot.query.organization_ids),
                    ),
                    summary="Визиты, конверсия и активность торговых представителей.",
                    data_status=self._worst_status(
                        [snapshot.business.visits.data_status]
                        + [item.data_status for item in snapshot.sales_reps]
                    ),
                    payload={
                        "metric": self._serialize_metric_value(snapshot.business.visits),
                        "sales_reps": [
                            self._serialize_sales_rep_item(item)
                            for item in snapshot.top_sales_reps[:10]
                        ],
                    },
                )
            )

        material_quality = self._material_quality_items(snapshot.data_quality.items)
        if material_quality:
            widgets.append(
                self._widget(
                    widget_id="data-quality",
                    widget_type=DashboardWidgetType.DATA_QUALITY,
                    source_type=DashboardWidgetSourceType.PERMANENT,
                    title="Ограничения данных",
                    metric_keys=[item.metric_key for item in material_quality],
                    organization_ids=list(snapshot.query.organization_ids),
                    priority=40,
                    priority_reason="Material data-quality limitations surfaced explicitly",
                    preferences=preferences,
                    drilldown=DashboardDrilldown(
                        target="data-quality",
                        organization_ids=list(snapshot.query.organization_ids),
                    ),
                    summary="Только значимые ограничения качества данных.",
                    data_status=snapshot.data_quality.overall_status,
                    payload={
                        "items": [
                            {
                                "metric_key": item.metric_key,
                                "data_status": item.data_status,
                                "coverage": item.coverage,
                                "confidence": item.confidence,
                                "message": item.message,
                                "missing_fields": item.missing_fields,
                            }
                            for item in material_quality
                        ],
                        "notes": snapshot.data_quality.notes,
                    },
                )
            )

        return widgets

    def _dynamic_ai_widgets(
        self,
        snapshot: AnalyticsBusinessSnapshot,
        ai_result: AIAnalyticsResult,
        preferences: UserDashboardPreferences,
    ) -> list[DashboardManifestWidget]:
        widgets: list[DashboardManifestWidget] = []

        widgets.append(
            self._widget(
                widget_id="executive-brief",
                widget_type=DashboardWidgetType.AI_INSIGHT,
                source_type=DashboardWidgetSourceType.PERMANENT,
                title="Краткая сводка",
                subtitle=ai_result.executive_brief.business_status,
                metric_keys=["revenue", "orders", "sold_units", "payments_received"],
                signal_ids=[item.id for item in ai_result.executive_brief.top_insights[:3]],
                organization_ids=list(ai_result.input_contract.context.organization_ids),
                priority=6,
                priority_reason="Executive brief remains near the top of dashboard",
                preferences=preferences,
                drilldown=DashboardDrilldown(
                    target="ai-analytics",
                    organization_ids=list(ai_result.input_contract.context.organization_ids),
                    filters={"view": "brief"},
                ),
                summary=ai_result.executive_brief.headline,
                data_status=AnalyticsDataStatus.AVAILABLE,
                removable_by_ai=False,
                payload={
                    "headline": ai_result.executive_brief.headline,
                    "business_status": ai_result.executive_brief.business_status,
                    "key_numbers": self._executive_key_numbers(snapshot, ai_result),
                    "top_insights": [
                        self._serialize_ai_insight_card(item)
                        for item in ai_result.executive_brief.top_insights[:4]
                    ],
                    "risks": [
                        self._serialize_ai_insight_card(item)
                        for item in ai_result.executive_brief.risks[:4]
                    ],
                    "opportunities": [
                        self._serialize_ai_insight_card(item)
                        for item in ai_result.executive_brief.opportunities[:4]
                    ],
                    "data_warnings": [
                        self._serialize_ai_insight_card(item)
                        for item in ai_result.executive_brief.data_warnings[:4]
                    ],
                },
            )
        )

        for insight in ai_result.top_insights[:4]:
            widgets.append(
                self._widget(
                    widget_id=f"dynamic-{insight.id}",
                    widget_type=self._dynamic_widget_type(insight),
                    source_type=DashboardWidgetSourceType.AI_DYNAMIC,
                    title=insight.title,
                    subtitle=insight.severity,
                    metric_keys=[
                        metric.label for metric in insight.metrics if metric.label
                    ],
                    signal_ids=[insight.id],
                    entity_type=insight.entity_type,
                    entity_id=insight.entity_id,
                    organization_ids=list(insight.organization_ids),
                    priority=max(7, insight.priority),
                    priority_reason=f"Dynamic AI signal: {insight.type}",
                    preferences=preferences,
                    drilldown=DashboardDrilldown(
                        target="ai-analytics",
                        entity_type=insight.entity_type,
                        entity_id=insight.entity_id,
                        organization_ids=list(insight.organization_ids),
                        filters={"insight_id": insight.id},
                    ),
                    summary=insight.summary,
                    data_status=AnalyticsDataStatus.AVAILABLE,
                    removable_by_ai=True,
                    payload=self._serialize_ai_insight_card(insight),
                )
            )

        if ai_result.watchlist:
            widgets.append(
                self._widget(
                    widget_id="watchlist",
                    widget_type=DashboardWidgetType.WATCHLIST,
                    source_type=DashboardWidgetSourceType.AI_DYNAMIC,
                    title="Watchlist",
                    metric_keys=[],
                    signal_ids=[item.id for item in ai_result.watchlist[:5]],
                    organization_ids=list(ai_result.input_contract.context.organization_ids),
                    priority=30,
                    priority_reason="Aggregated dynamic watchlist of secondary risks",
                    preferences=preferences,
                    drilldown=DashboardDrilldown(
                        target="ai-analytics",
                        organization_ids=list(ai_result.input_contract.context.organization_ids),
                        filters={"view": "watchlist"},
                    ),
                    summary=f"{len(ai_result.watchlist)} сигналов в наблюдении",
                    data_status=AnalyticsDataStatus.AVAILABLE,
                    removable_by_ai=True,
                    payload={
                        "rows": [
                            self._serialize_ai_insight_card(item)
                            for item in ai_result.watchlist[:10]
                        ]
                    },
                )
            )

        return widgets

    def _executive_key_numbers(
        self,
        snapshot: AnalyticsBusinessSnapshot,
        ai_result: AIAnalyticsResult,
    ) -> list[dict[str, object | None]]:
        """Prefer successful AI output and keep canonical KPI values as fallback."""

        provider_status = ai_result.provider_status
        if (
            provider_status is not None
            and provider_status.health == AIProviderHealth.AVAILABLE
            and ai_result.executive_brief.key_numbers
        ):
            return [
                {
                    "label": metric.label,
                    "current": metric.current,
                    "previous": metric.previous,
                    "delta": metric.delta,
                    "direction": metric.direction,
                }
                for metric in ai_result.executive_brief.key_numbers
            ]

        metrics = [
            ("Выручка", snapshot.business.revenue),
            ("Заказы", snapshot.business.orders),
            ("Средний заказ", snapshot.business.average_order),
            ("Продано единиц", snapshot.business.sold_units),
            ("Возвраты", snapshot.business.returns),
            ("Клиенты", snapshot.business.customers),
            ("Товары", snapshot.business.unique_products),
            ("Визиты", snapshot.business.visits),
        ]
        return [
            {
                "label": label,
                "current": self._decimal_to_string(metric.value),
                "previous": self._decimal_to_string(metric.previous_value),
                "delta": self._decimal_to_string(metric.delta),
                "direction": "up" if metric.delta is not None and metric.delta > 0 else "down" if metric.delta is not None and metric.delta < 0 else "flat",
            }
            for label, metric in metrics
        ]

    def _widget(
        self,
        *,
        widget_id: str,
        widget_type: DashboardWidgetType,
        source_type: DashboardWidgetSourceType,
        title: str,
        priority: int,
        priority_reason: str,
        preferences: UserDashboardPreferences,
        subtitle: str | None = None,
        metric_keys: list[str] | None = None,
        signal_ids: list[str] | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        organization_ids: list[UUID] | None = None,
        drilldown: DashboardDrilldown | None = None,
        summary: str | None = None,
        data_status: AnalyticsDataStatus = AnalyticsDataStatus.AVAILABLE,
        removable_by_ai: bool = True,
        payload: dict[str, object] | None = None,
    ) -> DashboardManifestWidget:
        entry = self.registry_by_type[widget_type]
        preferred_size = preferences.preferred_sizes.get(
            widget_id,
            entry.capabilities.preferred_size,
        )
        widget = DashboardManifestWidget(
            widget_id=widget_id,
            widget_type=widget_type,
            source_type=DashboardWidgetSourceType.USER_PINNED
            if widget_id in preferences.pinned_widget_ids
            else source_type,
            title=title,
            subtitle=subtitle,
            metric_keys=metric_keys or [],
            signal_ids=signal_ids or [],
            entity_type=entity_type,
            entity_id=entity_id,
            organization_ids=organization_ids or [],
            semantic_size=preferred_size,
            priority=preferences.widget_order_preferences.get(widget_id, priority),
            priority_reason=priority_reason,
            min_size=entry.capabilities.min_size,
            preferred_size=entry.capabilities.preferred_size,
            max_size=entry.capabilities.max_size,
            supports_horizontal_expand=entry.capabilities.supports_horizontal_expand,
            supports_vertical_expand=entry.capabilities.supports_vertical_expand,
            supports_internal_scroll=entry.capabilities.supports_internal_scroll,
            flow=entry.capabilities.flow,
            preferred_aspect=entry.capabilities.preferred_aspect,
            content_density=entry.capabilities.content_density,
            scroll_behavior=entry.capabilities.scroll_behavior,
            removable_by_ai=removable_by_ai and widget_id not in preferences.pinned_widget_ids,
            movable_by_ai=widget_id not in preferences.locked_position_widget_ids,
            resizable_by_ai=widget_id not in preferences.locked_size_widget_ids,
            locked_position=widget_id in preferences.locked_position_widget_ids,
            locked_size=widget_id in preferences.locked_size_widget_ids,
            pinned=widget_id in preferences.pinned_widget_ids,
            hidden=widget_id in preferences.hidden_widget_ids,
            drilldown=drilldown,
            summary=summary,
            data_status=data_status,
            payload=payload or {},
        )
        if widget.pinned:
            widget.priority = min(widget.priority, 0)
        return widget

    def _build_revenue_series(
        self,
        snapshot: AnalyticsBusinessSnapshot,
        sales_report: AnalyticsSalesReport | None,
    ) -> list[dict[str, object]]:
        if sales_report is None:
            return []
        if snapshot.business.revenue.data_status in {
            AnalyticsDataStatus.NO_DATA,
            AnalyticsDataStatus.NO_VERIFIED_DATA,
            AnalyticsDataStatus.INSUFFICIENT_HISTORY,
        }:
            return []
        rows: list[dict[str, object]] = []
        for item in sales_report.by_date:
            revenue_metric = item.metrics.get("revenue")
            rows.append(self._serialize_revenue_series_point(item, revenue_metric))
        return rows

    def _revenue_series_granularity(self, sales_report: AnalyticsSalesReport | None) -> str:
        if sales_report is None or not sales_report.by_date:
            return "day"
        return "day"

    def _serialize_revenue_series_point(
        self,
        row: AnalyticsDimensionRow,
        metric: AnalyticsMetricValue | None,
    ) -> dict[str, object | None]:
        return {
            "date": row.key,
            "label": row.label,
            "value": self._decimal_to_string(None if metric is None else metric.value),
            "status": row.data_status if metric is None else metric.data_status,
            "currency": None if metric is None else metric.currency,
            "record_count": None if metric is None else metric.record_count,
        }

    def _serialize_metric_value(self, metric: AnalyticsMetricValue) -> dict[str, object | None]:
        return {
            "value": self._decimal_to_string(metric.value),
            "previous_value": self._decimal_to_string(metric.previous_value),
            "delta": self._decimal_to_string(metric.delta),
            "percent_delta": self._decimal_to_string(metric.percent_delta),
            "unit": metric.unit,
            "status": metric.status,
            "data_status": metric.data_status,
            "coverage": metric.coverage,
            "confidence": metric.confidence,
            "currency": metric.currency,
            "record_count": metric.record_count,
            "note": metric.note,
        }

    def _serialize_product_item(self, item: AnalyticsProductItem) -> dict[str, object | None]:
        return {
            "product_id": None if item.product_id is None else str(item.product_id),
            "product_external_id": item.product_external_id,
            "product_name": item.product_name,
            "organization_id": str(item.organization_id),
            "organization_name": item.organization_name,
            "sold_units": self._serialize_metric_value(item.sold_units),
            "revenue": self._serialize_metric_value(item.revenue),
            "orders_count": self._serialize_metric_value(item.orders_count),
            "customers_count": self._serialize_metric_value(item.customers_count),
            "average_selling_price": self._serialize_metric_value(item.average_selling_price),
            "returns_quantity": self._serialize_metric_value(item.returns_quantity),
            "returns_amount": self._serialize_metric_value(item.returns_amount),
            "return_rate": self._serialize_metric_value(item.return_rate),
            "current_stock": self._serialize_metric_value(item.current_stock),
            "stock_value": self._serialize_metric_value(item.stock_value),
            "sales_velocity_7d": self._serialize_metric_value(item.sales_velocity_7d),
            "sales_velocity_30d": self._serialize_metric_value(item.sales_velocity_30d),
            "days_of_stock": self._serialize_metric_value(item.days_of_stock),
            "sales_change_pct": self._serialize_metric_value(item.sales_change_pct),
            "units_change_pct": self._serialize_metric_value(item.units_change_pct),
            "revenue_change_pct": self._serialize_metric_value(item.revenue_change_pct),
            "classification": item.classification,
            "classification_tags": item.classification_tags,
            "stockout_risk": item.stockout_risk,
            "first_sale_date": (
                None if item.first_sale_date is None else item.first_sale_date.isoformat()
            ),
            "last_sale_date": (
                None if item.last_sale_date is None else item.last_sale_date.isoformat()
            ),
            "data_status": item.data_status,
        }

    def _serialize_customer_item(self, item: AnalyticsCustomerItem) -> dict[str, object | None]:
        return {
            "customer_external_id": item.customer_external_id,
            "customer_name": item.customer_name,
            "organization_ids": [str(org_id) for org_id in item.organization_ids],
            "orders_count": self._serialize_metric_value(item.orders_count),
            "revenue": self._serialize_metric_value(item.revenue),
            "sold_units": self._serialize_metric_value(item.sold_units),
            "average_order_value": self._serialize_metric_value(item.average_order_value),
            "days_since_last_order": self._serialize_metric_value(item.days_since_last_order),
            "purchase_frequency": self._serialize_metric_value(item.purchase_frequency),
            "returns_count": self._serialize_metric_value(item.returns_count),
            "returns_amount": self._serialize_metric_value(item.returns_amount),
            "visits_count": self._serialize_metric_value(item.visits_count),
            "products_count": self._serialize_metric_value(item.products_count),
            "organizations_count": self._serialize_metric_value(item.organizations_count),
            "customer_value_score": self._serialize_metric_value(item.customer_value_score),
            "segment": item.segment,
            "first_order_date": (
                None if item.first_order_date is None else item.first_order_date.isoformat()
            ),
            "last_order_date": (
                None if item.last_order_date is None else item.last_order_date.isoformat()
            ),
            "data_status": item.data_status,
        }

    def _serialize_organization_item(self, item: AnalyticsOrganizationItem) -> dict[str, object]:
        return {
            "organization_id": str(item.organization_id),
            "organization_name": item.organization_name,
            "metrics": {
                "revenue": self._serialize_metric_value(item.metrics.revenue),
                "orders": self._serialize_metric_value(item.metrics.orders),
                "sold_units": self._serialize_metric_value(item.metrics.sold_units),
                "payments_received": self._serialize_metric_value(item.metrics.payments_received),
                "returns": self._serialize_metric_value(item.metrics.returns),
                "customers": self._serialize_metric_value(item.metrics.customers),
                "visits": self._serialize_metric_value(item.metrics.visits),
                "current_stock": self._serialize_metric_value(item.metrics.current_stock),
            },
            "products_sold": self._serialize_metric_value(item.products_sold),
            "sales_reps": self._serialize_metric_value(item.sales_reps),
            "visits": self._serialize_metric_value(item.visits),
            "stock": self._serialize_metric_value(item.stock),
            "data_status": item.data_status,
        }

    def _serialize_inventory_opportunity(
        self,
        item: AnalyticsInventoryTransferOpportunity,
    ) -> dict[str, object]:
        return {
            "product_external_id": item.product_external_id,
            "product_name": item.product_name,
            "from_organization_id": str(item.from_organization_id),
            "from_organization_name": item.from_organization_name,
            "to_organization_id": str(item.to_organization_id),
            "to_organization_name": item.to_organization_name,
            "source_stock": self._serialize_metric_value(item.source_stock),
            "destination_stock": self._serialize_metric_value(item.destination_stock),
            "source_days": self._serialize_metric_value(item.source_days),
            "destination_days": self._serialize_metric_value(item.destination_days),
            "source_velocity": self._serialize_metric_value(item.source_velocity),
            "destination_velocity": self._serialize_metric_value(item.destination_velocity),
            "reason": item.reason,
        }

    def _serialize_sales_rep_item(self, item: AnalyticsSalesRepItem) -> dict[str, object]:
        return {
            "sales_rep_key": item.sales_rep_key,
            "sales_rep_name": item.sales_rep_name,
            "revenue": self._serialize_metric_value(item.revenue),
            "orders": self._serialize_metric_value(item.orders),
            "sold_units": self._serialize_metric_value(item.sold_units),
            "customers": self._serialize_metric_value(item.customers),
            "new_customers": self._serialize_metric_value(item.new_customers),
            "average_order": self._serialize_metric_value(item.average_order),
            "returns": self._serialize_metric_value(item.returns),
            "visits": self._serialize_metric_value(item.visits),
            "completed_visits": self._serialize_metric_value(item.completed_visits),
            "orders_after_visit": self._serialize_metric_value(item.orders_after_visit),
            "visit_conversion": self._serialize_metric_value(item.visit_conversion),
            "revenue_after_visits": self._serialize_metric_value(item.revenue_after_visits),
            "data_status": item.data_status,
        }

    def _serialize_ai_insight_card(self, insight: AIInsightCard) -> dict[str, object | None]:
        return {
            "id": insight.id,
            "type": insight.type,
            "severity": insight.severity,
            "priority": insight.priority,
            "title": insight.title,
            "summary": insight.summary,
            "recommendation": insight.recommendation,
            "widget_type": insight.widget_type,
            "entity_type": insight.entity_type,
            "entity_id": insight.entity_id,
            "organization_ids": [str(org_id) for org_id in insight.organization_ids],
            "period_label": None if insight.period is None else insight.period.label,
            "metrics": [
                {
                    "label": metric.label,
                    "current": metric.current,
                    "previous": metric.previous,
                    "delta": metric.delta,
                    "direction": metric.direction,
                }
                for metric in insight.metrics
            ],
            "evidence": insight.evidence,
        }

    def _decimal_to_string(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        return format(value, "f")

    def _validate_widgets(
        self,
        widgets: list[DashboardManifestWidget],
        context: DashboardManifestContext,
    ) -> list[str]:
        errors: list[str] = []
        for widget in widgets:
            registry = self.registry_by_type.get(widget.widget_type)
            if registry is None:
                errors.append(f"UNKNOWN_WIDGET_TYPE:{widget.widget_type}")
                continue
            if semantic_size_rank(widget.semantic_size) < semantic_size_rank(widget.min_size):
                errors.append(f"SIZE_BELOW_MIN:{widget.widget_id}")
            if semantic_size_rank(widget.semantic_size) > semantic_size_rank(widget.max_size):
                errors.append(f"SIZE_ABOVE_MAX:{widget.widget_id}")
            if widget.source_type == DashboardWidgetSourceType.AI_DYNAMIC and not widget.signal_ids:
                errors.append(f"MISSING_SIGNAL_BINDING:{widget.widget_id}")
            if context.organization_mode == DashboardOrganizationMode.SINGLE:
                allowed = set(context.organization_ids)
                if widget.organization_ids and not set(widget.organization_ids).issubset(allowed):
                    errors.append(f"ORGANIZATION_SCOPE_INVALID:{widget.widget_id}")
            if widget.drilldown is None:
                errors.append(f"MISSING_DRILLDOWN:{widget.widget_id}")
        return errors

    def _layout_policy(self, widgets: list[DashboardManifestWidget]):
        from app.core.analytics.dashboard_manifest import DashboardLayoutPolicy

        return DashboardLayoutPolicy(
            permanent_widget_ids=[
                widget.widget_id
                for widget in widgets
                if widget.source_type != DashboardWidgetSourceType.AI_DYNAMIC
            ],
            notes=[
                "Composer sets semantic size and priority only.",
                "Frontend layout engine resolves grid positions and collisions.",
            ],
        )

    def _data_quality(
        self,
        items: list[AnalyticsDataQualityEntry],
        notes: list[str],
    ) -> DashboardManifestDataQuality:
        material = self._material_quality_items(items)
        overall = (
            material[0].data_status
            if material
            else AnalyticsDataStatus.AVAILABLE
        )
        for item in material[1:]:
            overall = self._worst_status([overall, item.data_status])
        return DashboardManifestDataQuality(
            overall_status=overall,
            surfaced_items=material,
            notes=notes,
        )

    def _material_quality_items(
        self,
        items: list[AnalyticsDataQualityEntry],
    ) -> list[AnalyticsDataQualityEntry]:
        return [
            item
            for item in items
            if item.data_status
            in {
                AnalyticsDataStatus.NO_VERIFIED_DATA,
                AnalyticsDataStatus.PARTIAL,
                AnalyticsDataStatus.UNRESOLVED,
                AnalyticsDataStatus.PERMISSION_RESTRICTED,
            }
        ][:5]

    def _dynamic_widget_type(self, insight: AIInsightCard) -> DashboardWidgetType:
        if insight.type in {"DATA_QUALITY"}:
            return DashboardWidgetType.DATA_QUALITY
        if insight.type in {"ORGANIZATION"}:
            return DashboardWidgetType.ORGANIZATION_COMPARISON
        if insight.type in {"PRODUCT", "INVENTORY"}:
            return DashboardWidgetType.PRODUCT_RANKING
        if insight.type in {"CUSTOMER"}:
            return DashboardWidgetType.CUSTOMER_RANKING
        if insight.type in {"RISK", "ANOMALY"}:
            return DashboardWidgetType.ALERT
        return DashboardWidgetType.AI_INSIGHT

    def _inventory_widget_status(self, snapshot: AnalyticsBusinessSnapshot) -> AnalyticsDataStatus:
        candidates = [item.data_status for item in snapshot.low_stock_products]
        candidates += [item.data_status for item in snapshot.stockout_risk_products]
        if snapshot.inventory:
            candidates.append(AnalyticsDataStatus.PARTIAL)
        return self._worst_status(candidates or [AnalyticsDataStatus.NO_DATA])

    def _worst_status(self, statuses: list[AnalyticsDataStatus]) -> AnalyticsDataStatus:
        order = {
            AnalyticsDataStatus.UNRESOLVED: 7,
            AnalyticsDataStatus.PERMISSION_RESTRICTED: 6,
            AnalyticsDataStatus.NO_VERIFIED_DATA: 5,
            AnalyticsDataStatus.PARTIAL: 4,
            AnalyticsDataStatus.INSUFFICIENT_HISTORY: 3,
            AnalyticsDataStatus.NO_DATA: 2,
            AnalyticsDataStatus.NOT_AVAILABLE: 1,
            AnalyticsDataStatus.AVAILABLE: 0,
        }
        return max(statuses, key=lambda item: order.get(item, 0))

    def _period_label(self, snapshot: AnalyticsBusinessSnapshot) -> str:
        start = snapshot.period.current_start
        end = snapshot.period.current_end
        if start is None or end is None:
            return snapshot.period.label
        return f"{start:%d.%m.%Y} - {end:%d.%m.%Y}"

    def _analytics_context_hash(self, snapshot: AnalyticsBusinessSnapshot) -> str:
        payload = dumps(
            {
                "organization_ids": [str(item) for item in snapshot.query.organization_ids],
                "period": snapshot.period.model_dump(mode="json"),
                "business": snapshot.business.model_dump(mode="json"),
                "quality": snapshot.data_quality.model_dump(mode="json"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    def _ai_context_hash(self, ai_result: AIAnalyticsResult) -> str:
        payload = dumps(
            {
                "headline": ai_result.executive_brief.headline,
                "signals": [item.signal_id for item in ai_result.signals],
                "top": [item.id for item in ai_result.top_insights],
                "watch": [item.id for item in ai_result.watchlist],
                "provider": ai_result.provider_status.model_dump(mode="json")
                if ai_result.provider_status
                else None,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    def _preferences_hash(self, preferences: UserDashboardPreferences) -> str:
        payload = dumps(preferences.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        return sha256(payload.encode("utf-8")).hexdigest()

    def _cache_key(
        self,
        *,
        analytics_context_hash: str,
        ai_context_hash: str,
        preferences_hash: str,
        context: DashboardManifestContext,
    ) -> str:
        payload = dumps(
            {
                "manifest_version": MANIFEST_VERSION,
                "widget_registry_version": WIDGET_REGISTRY_VERSION,
                "analytics_context_hash": analytics_context_hash,
                "ai_context_hash": ai_context_hash,
                "preferences_hash": preferences_hash,
                "context": context.model_dump(mode="json"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return sha256(payload.encode("utf-8")).hexdigest()


def ai_result_metrics(snapshot: AnalyticsBusinessSnapshot) -> dict[str, str]:
    """Summaries for permanent KPIs."""

    return {
        "revenue": str(snapshot.business.revenue.value or 0),
        "orders": str(snapshot.business.orders.value or 0),
        "sold_units": str(snapshot.business.sold_units.value or 0),
        "average_order": str(snapshot.business.average_order.value or 0),
        "payments_received": str(snapshot.business.payments_received.value or 0),
    }
