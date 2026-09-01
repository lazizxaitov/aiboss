"""Compatibility AI analytics agent backed by Canonical V2 AI foundation."""

from __future__ import annotations

from app.core.ai_analytics.service import AIAnalyticsService
from app.core.analytics.engine import BusinessAnalyticsEngine
from app.core.analytics.models import AIInsightCard, AnalyticsQuery, BusinessAnalyticsSnapshot


class AIAnalyticsAgent:
    """Compatibility layer preserving the executive dashboard API contract."""

    def __init__(self) -> None:
        self.service = AIAnalyticsService()

    def generate_insights(self, snapshot: BusinessAnalyticsSnapshot) -> list[AIInsightCard]:
        """Legacy dashboard path using the old snapshot contract."""

        return self._legacy_insights(snapshot)

    def generate_canonical_insights(self, store, query: AnalyticsQuery) -> list[AIInsightCard]:
        """Canonical V2 path for new AI analytics consumers."""

        canonical_snapshot = BusinessAnalyticsEngine(store).build_snapshot(query)
        return self.service.legacy_insights(canonical_snapshot)

    def analyze_canonical(
        self,
        store,
        query: AnalyticsQuery,
        *,
        language: str | None = None,
        force_refresh: bool = False,
        include_provider: bool = True,
        engine: BusinessAnalyticsEngine | None = None,
    ):
        """Return the full structured AI analytics result from Canonical V2."""

        canonical_snapshot = (engine or BusinessAnalyticsEngine(store)).build_snapshot(query)
        return self.service.analyze(
            canonical_snapshot,
            language=language,
            force_refresh=force_refresh,
            include_provider=include_provider,
        )

    def _legacy_insights(self, snapshot: BusinessAnalyticsSnapshot) -> list[AIInsightCard]:
        """Preserve old dashboard behavior until dashboard migration switches."""

        return _legacy_rule_based_insights(snapshot)


def _legacy_rule_based_insights(snapshot: BusinessAnalyticsSnapshot) -> list[AIInsightCard]:
    """Existing dashboard-compatible rule-based insights kept intact for current UI."""

    insights: list[AIInsightCard] = []
    kpi_by_key = {kpi.key: kpi for kpi in snapshot.kpis}

    revenue = kpi_by_key.get("revenue")
    orders = kpi_by_key.get("orders")
    sold_units = kpi_by_key.get("sold_units")
    average_order = kpi_by_key.get("average_order")
    payments = kpi_by_key.get("payments_received")
    expenses = kpi_by_key.get("expenses")
    cash_flow = kpi_by_key.get("cash_flow")
    returns = kpi_by_key.get("returns")
    receivables = kpi_by_key.get("receivables")
    visits = kpi_by_key.get("visits")
    conversion = kpi_by_key.get("visit_conversion")

    if revenue is not None:
        insights.append(
            AIInsightCard(
                type="revenue",
                severity=_legacy_severity_from_kpi(revenue),
                priority=1,
                title="Динамика выручки",
                summary=_legacy_summary_text(revenue, "Выручка"),
                recommendation="Проверьте каналы продаж, ассортимент и отклонения по организациям.",
                metrics=[_legacy_metric_from_kpi(revenue)],
                evidence=snapshot.sales.top_entities[:3],
                widget_type="line_chart",
                entity_type="sales",
                organization_ids=snapshot.organization_ids,
                period=snapshot.period,
            )
        )

    if cash_flow is not None:
        insights.append(
            AIInsightCard(
                type="cash_flow",
                severity=_legacy_severity_from_kpi(cash_flow),
                priority=2,
                title="Денежный поток",
                summary=_legacy_summary_text(cash_flow, "Денежный поток"),
                recommendation="Сопоставьте поступления, расходы и дебиторку по периодам.",
                metrics=[
                    _legacy_metric_from_kpi(cash_flow),
                    _legacy_metric_from_kpi(payments),
                ],
                evidence=snapshot.finance.top_entities[:3] + snapshot.returns.top_entities[:2],
                widget_type="ai_recommendation",
                entity_type="finance",
                organization_ids=snapshot.organization_ids,
                period=snapshot.period,
            )
        )

    if returns is not None and (
        returns.current_value > 0
        or (returns.previous_value is not None and returns.previous_value > 0)
    ):
        insights.append(
            AIInsightCard(
                type="returns",
                severity="warning",
                priority=3,
                title="Возвраты требуют внимания",
                summary=_legacy_summary_text(returns, "Возвраты"),
                recommendation="Разберите причины возвратов по товарам, клиентам и менеджерам.",
                metrics=[_legacy_metric_from_kpi(returns)],
                evidence=snapshot.returns.top_entities[:5],
                widget_type="product_alert",
                entity_type="returns",
                organization_ids=snapshot.organization_ids,
                period=snapshot.period,
            )
        )

    if sold_units is not None:
        insights.append(
            AIInsightCard(
                type="sold_units",
                severity=_legacy_severity_from_kpi(sold_units),
                priority=4,
                title="Проданные единицы",
                summary=_legacy_summary_text(sold_units, "Продано единиц"),
                recommendation="Сравните продажи по категориям и SKU с остатками на складе.",
                metrics=[_legacy_metric_from_kpi(sold_units)],
                evidence=snapshot.products.top_entities[:5],
                widget_type="ranking",
                entity_type="products",
                organization_ids=snapshot.organization_ids,
                period=snapshot.period,
            )
        )

    if orders is not None and orders.current_value > 0:
        insights.append(
            AIInsightCard(
                type="orders",
                severity="info",
                priority=5,
                title="Заказы и средний чек",
                summary=_legacy_summary_text(orders, "Заказы"),
                recommendation="Отслеживайте средний заказ и долю повторных покупок.",
                metrics=[
                    _legacy_metric_from_kpi(orders),
                    _legacy_metric_from_kpi(average_order),
                ],
                evidence=snapshot.customers.top_entities[:3],
                widget_type="table",
                entity_type="customers",
                organization_ids=snapshot.organization_ids,
                period=snapshot.period,
            )
        )

    if expenses is not None:
        insights.append(
            AIInsightCard(
                type="expenses",
                severity=_legacy_severity_from_kpi(expenses, reverse=True),
                priority=6,
                title="Расходы и эффективность",
                summary=_legacy_summary_text(expenses, "Расходы"),
                recommendation="Сверьте расходы с денежным потоком и маркетинговыми конверсиями.",
                metrics=[_legacy_metric_from_kpi(expenses)],
                evidence=snapshot.merchandising.top_entities[:3],
                widget_type="bar_chart",
                entity_type="finance",
                organization_ids=snapshot.organization_ids,
                period=snapshot.period,
            )
        )

    if receivables is not None:
        insights.append(
            AIInsightCard(
                type="receivables",
                severity=_legacy_severity_from_kpi(receivables),
                priority=7,
                title="Дебиторская задолженность",
                summary=_legacy_summary_text(receivables, "Дебиторка"),
                recommendation="Отдельно проверьте отложенные оплаты и просроченные счета.",
                metrics=[_legacy_metric_from_kpi(receivables)],
                evidence=snapshot.finance.top_entities[:3],
                widget_type="customer_alert",
                entity_type="finance",
                organization_ids=snapshot.organization_ids,
                period=snapshot.period,
            )
        )

    if visits is not None and visits.current_value > 0:
        insights.append(
            AIInsightCard(
                type="visits",
                severity="info",
                priority=8,
                title="Визиты и конверсия",
                summary=_legacy_summary_text(visits, "Визиты"),
                recommendation="Сопоставьте число визитов с закрытыми сделками и конверсией.",
                metrics=[
                    _legacy_metric_from_kpi(visits),
                    _legacy_metric_from_kpi(conversion),
                ],
                evidence=snapshot.visits.top_entities[:3],
                widget_type="sales_rep_performance",
                entity_type="visits",
                organization_ids=snapshot.organization_ids,
                period=snapshot.period,
            )
        )

    if snapshot.sales_reps.current_count > 0:
        insights.append(
            AIInsightCard(
                type="sales_rep",
                severity="info",
                priority=9,
                title="Эффективность торговых представителей",
                summary=(
                    f"В snapshot найдено {snapshot.sales_reps.current_count} "
                    "активных торговых представителей."
                ),
                recommendation="Сравните вклад менеджеров в выручку, заказы и единицы.",
                metrics=[],
                evidence=snapshot.top_sales_reps[:5],
                widget_type="sales_rep_performance",
                entity_type="sales_reps",
                organization_ids=snapshot.organization_ids,
                period=snapshot.period,
            )
        )

    if snapshot.merchandising.current_count > 0:
        insights.append(
            AIInsightCard(
                type="merchandising",
                severity="info",
                priority=10,
                title="Мерчандайзинг и маркетинг",
                summary=(
                    f"Маркетинговых активностей: {snapshot.merchandising.current_count}, "
                    f"затраты: {snapshot.merchandising.current_amount}."
                ),
                recommendation="Проверьте, какие активности реально влияют на продажи и визиты.",
                metrics=[],
                evidence=snapshot.merchandising.top_entities[:3],
                widget_type="photo_alert",
                entity_type="marketing",
                organization_ids=snapshot.organization_ids,
                period=snapshot.period,
            )
        )

    if not insights:
        insights.append(
            AIInsightCard(
                type="coverage",
                severity="info",
                priority=99,
                title="Данные ядра готовы к анализу",
                summary=(
                    "Snapshot собран, но пока нет достаточного объёма событий "
                    "для приоритетных инсайтов."
                ),
                recommendation=(
                    "Продолжайте загрузку истории и проверьте покрытие "
                    "SmartUp экспорта."
                ),
                metrics=[],
                evidence=snapshot.notes[:3],
                widget_type="ai_insight",
                entity_type="core",
                organization_ids=snapshot.organization_ids,
                period=snapshot.period,
            )
        )

    return sorted(insights, key=lambda item: (item.priority, item.generated_at))


def _legacy_metric_from_kpi(kpi):
    from app.core.analytics.models import AIInsightMetric

    if kpi is None:
        return AIInsightMetric(label="Нет данных")
    return AIInsightMetric(
        label=kpi.label,
        current=str(kpi.current_value),
        previous=str(kpi.previous_value) if kpi.previous_value is not None else None,
        delta=str(kpi.absolute_delta) if kpi.absolute_delta is not None else None,
        direction=kpi.direction,
    )


def _legacy_severity_from_kpi(kpi, *, reverse: bool = False) -> str:
    from decimal import Decimal

    delta = kpi.percent_delta
    if delta is None:
        return "info"
    if reverse:
        delta = -delta
    if delta <= Decimal("-15"):
        return "critical"
    if delta < Decimal("0"):
        return "warning"
    if delta >= Decimal("15"):
        return "success"
    return "info"


def _legacy_summary_text(kpi, label: str) -> str:
    if kpi.previous_value is None:
        return f"{label}: {kpi.current_value} сейчас."
    if kpi.absolute_delta is None:
        return f"{label}: {kpi.current_value}."
    sign = "+" if kpi.absolute_delta > 0 else ""
    return (
        f"{label}: {kpi.current_value} против {kpi.previous_value}; "
        f"изменение {sign}{kpi.absolute_delta}."
    )
