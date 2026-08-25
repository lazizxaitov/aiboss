"""Transform deterministic signals into structured executive insights."""

from __future__ import annotations

from decimal import Decimal

from app.core.ai_analytics.models import (
    AIInsightCard,
    AIInsightMetric,
    AIInsightSeverity,
    AIInsightType,
    AISignal,
)
from app.core.analytics.models import AnalyticsDataStatus


def build_insights(signals: list[AISignal]) -> list[AIInsightCard]:
    """Convert deterministic signals into stable executive insight cards."""

    insights: list[AIInsightCard] = []
    for priority, signal in enumerate(signals, start=1):
        insight_type = _insight_type(signal)
        title, summary, recommendation, widget_type = _narrative(signal)
        insights.append(
            AIInsightCard(
                type=insight_type.value,
                severity=signal.severity.value.lower(),
                priority=priority,
                title=title,
                summary=summary,
                metrics=_build_metrics(signal),
                evidence=[item.note or item.metric for item in signal.evidence],
                recommendation=recommendation,
                widget_type=widget_type,
                entity_type=signal.entity_type,
                entity_id=signal.entity_id,
                organization_ids=[signal.organization_id]
                if signal.organization_id is not None
                else [],
                period=signal.period,
            )
        )
    return insights


def _build_metrics(signal: AISignal) -> list[AIInsightMetric]:
    metrics = [
        AIInsightMetric(
            label=signal.metric_key,
            current=None if signal.current_value is None else str(signal.current_value),
            previous=None if signal.previous_value is None else str(signal.previous_value),
            delta=None if signal.absolute_change is None else str(signal.absolute_change),
            direction="up"
            if signal.absolute_change and signal.absolute_change > 0
            else "down"
            if signal.absolute_change and signal.absolute_change < 0
            else "flat",
        )
    ]
    if signal.percentage_change is not None:
        metrics.append(
            AIInsightMetric(
                label="change_percent",
                current=str(signal.percentage_change),
                direction="up"
                if signal.percentage_change > 0
                else "down"
                if signal.percentage_change < 0
                else "flat",
            )
        )
    return metrics


def _insight_type(signal: AISignal) -> AIInsightType:
    if signal.signal_type.name.startswith("DATA_QUALITY"):
        return AIInsightType.DATA_QUALITY
    if signal.signal_type.name.startswith("TOP_CUSTOMER") or "CUSTOMER" in signal.signal_type.name:
        return AIInsightType.CUSTOMER
    if signal.signal_type.name.startswith("TOP_PRODUCT") or "PRODUCT" in signal.signal_type.name:
        return AIInsightType.PRODUCT
    if "STOCK" in signal.signal_type.name or "INVENTORY" in signal.signal_type.name:
        return AIInsightType.INVENTORY
    if "ORGANIZATION" in signal.signal_type.name:
        return AIInsightType.ORGANIZATION
    if signal.metric_key in {"payments_received", "customer_return_value", "cash_in", "cash_out"}:
        return AIInsightType.FINANCE
    if signal.severity in {AIInsightSeverity.CRITICAL, AIInsightSeverity.HIGH}:
        return AIInsightType.RISK
    return AIInsightType.PERFORMANCE


def _narrative(signal: AISignal) -> tuple[str, str, str, str]:
    if signal.signal_type.name == "DATA_QUALITY_WARNING":
        status_text = signal.data_status.value
        title = "Ограничение качества данных"
        summary = (
            f"Метрика {signal.metric_key} имеет статус {status_text}. "
            "AI учитывает это ограничение и не трактует отсутствующие данные как ноль."
        )
        return (
            title,
            summary,
            "Проверьте покрытие источников и статус canonical quality.",
            "ai_recommendation",
        )

    if signal.metric_key == "revenue":
        direction = "выросла" if (signal.percentage_change or Decimal("0")) > 0 else "снизилась"
        percent = _format_percent(signal.percentage_change)
        summary = (
            f"Выручка {direction} на {percent} относительно предыдущего периода."
            if percent is not None
            else "Изменение выручки обнаружено, но процент недоступен."
        )
        return (
            "Динамика выручки",
            summary,
            "Проверьте организации, товары и клиентов с наибольшим вкладом в изменение.",
            "line_chart",
        )

    if signal.signal_type.name == "PAYMENT_CHANGE":
        summary = _comparison_summary("Поступления клиентов", signal)
        return (
            "Изменение поступлений",
            summary,
            "Сравните выручку и поступления: это разные показатели.",
            "ai_recommendation",
        )

    if signal.signal_type.name == "RETURN_SPIKE":
        summary = (
            "В выбранном периоде зафиксированы документы возврата. "
            "Это сумма документов возврата, а не подтверждённые денежные возвраты."
        )
        return (
            "Возвраты клиентов",
            summary,
            "Проверьте причины возвратов по товарам и клиентам.",
            "product_alert",
        )

    if signal.signal_type.name in {"SALES_GROWTH", "SALES_DECLINE"}:
        summary = _comparison_summary("Продажи", signal)
        return (
            "Продажи периода",
            summary,
            "Сравните вклад организаций, товаров и клиентов.",
            "line_chart",
        )

    if signal.entity_type == "product":
        summary = _comparison_summary("Товар", signal)
        if signal.signal_type.name in {"LOW_STOCK", "OUT_OF_STOCK", "STOCKOUT_RISK"}:
            summary = "По товару выявлен риск нехватки запаса по текущему snapshot склада."
        elif signal.signal_type.name == "OVERSTOCK":
            summary = "По товару выявлен избыточный запас относительно текущего спроса."
        return (
            "Товарный сигнал",
            summary,
            "Проверьте продажи, остатки и возвраты этого SKU.",
            "ranking",
        )

    if signal.entity_type == "customer":
        summary = _comparison_summary("Клиент", signal)
        return (
            "Клиентский сигнал",
            summary,
            "Проверьте заказы, визиты и активность клиента.",
            "customer_alert",
        )

    if signal.entity_type == "organization":
        summary = _comparison_summary("Организация", signal)
        return (
            "Организация требует внимания",
            summary,
            "Сравните филиал с общей динамикой бизнеса.",
            "organization_comparison",
        )

    if signal.signal_type.name == "STOCK_TRANSFER_OPPORTUNITY":
        summary = "В разных организациях найден дисбаланс остатков по одному и тому же товару."
        return (
            "Возможность перераспределения запаса",
            summary,
            "Проверьте межфилиальное перераспределение вручную.",
            "inventory_alert",
        )

    if signal.metric_key == "visits":
        summary = _comparison_summary("Визиты", signal)
        return (
            "Изменение полевых визитов",
            summary,
            "Не трактуйте это как конверсию без отдельной методологии Visit → Order.",
            "sales_rep_performance",
        )

    summary = _comparison_summary(signal.metric_key, signal)
    return "AI аналитика", summary, "Проверьте drilldown и подтверждающие метрики.", "ai_insight"


def _comparison_summary(label: str, signal: AISignal) -> str:
    current = _format_decimal(signal.current_value)
    previous = _format_decimal(signal.previous_value)
    percent = _format_percent(signal.percentage_change)
    if signal.data_status == AnalyticsDataStatus.INSUFFICIENT_HISTORY:
        return f"{label}: недостаточно истории для тренда."
    if signal.data_status == AnalyticsDataStatus.NO_VERIFIED_DATA:
        return f"{label}: нет проверенных данных для корректного вывода."
    if current is None:
        return f"{label}: значение недоступно."
    if previous is None:
        return f"{label}: текущее значение {current}."
    if percent is None:
        return f"{label}: {current} против {previous}."
    return f"{label}: {current} против {previous}, изменение {percent}."


def _format_percent(value: Decimal | None) -> str | None:
    if value is None:
        return None
    sign = "+" if value > 0 else ""
    return f"{sign}{value.quantize(Decimal('0.01'))}%"


def _format_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return (
        str(value.quantize(Decimal("0.01")))
        if value != value.to_integral()
        else str(value.quantize(Decimal("1")))
    )
