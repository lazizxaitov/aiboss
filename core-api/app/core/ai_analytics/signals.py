"""Deterministic business signal generation for AI analytics."""

from __future__ import annotations

from decimal import Decimal

from app.core.ai_analytics.models import (
    AIEvidence,
    AIInsightSeverity,
    AISignal,
    AISignalType,
)
from app.core.analytics.models import (
    AnalyticsBusinessSnapshot,
    AnalyticsCustomerItem,
    AnalyticsDataQualityEntry,
    AnalyticsDataStatus,
    AnalyticsMetricValue,
    AnalyticsProductItem,
)


def build_signals(snapshot: AnalyticsBusinessSnapshot) -> list[AISignal]:
    """Build deterministic signal candidates from canonical analytics snapshot."""

    signals: list[AISignal] = []
    signals.extend(_sales_signals(snapshot))
    signals.extend(_product_signals(snapshot))
    signals.extend(_customer_signals(snapshot))
    signals.extend(_organization_signals(snapshot))
    signals.extend(_inventory_signals(snapshot))
    signals.extend(_finance_signals(snapshot))
    signals.extend(_data_quality_signals(snapshot))
    return signals


def _sales_signals(snapshot: AnalyticsBusinessSnapshot) -> list[AISignal]:
    revenue = snapshot.business.revenue
    if revenue.data_status == AnalyticsDataStatus.INSUFFICIENT_HISTORY:
        return []
    if revenue.percent_delta is None:
        return []
    signal_type = (
        AISignalType.SALES_GROWTH if revenue.percent_delta > 0 else AISignalType.SALES_DECLINE
    )
    if revenue.percent_delta == 0:
        return []
    return [
        AISignal(
            signal_type=signal_type,
            severity=_severity_from_percent(revenue.percent_delta),
            current_value=revenue.value,
            previous_value=revenue.previous_value,
            absolute_change=revenue.delta,
            percentage_change=revenue.percent_delta,
            metric_key="revenue",
            period=snapshot.period,
            confidence=_confidence_from_metric(revenue),
            data_status=revenue.data_status,
            coverage=revenue.coverage,
            evidence=[_metric_evidence("revenue", revenue)],
            drilldown={"target": "sales", "metric": "revenue"},
        )
    ]


def _product_signals(snapshot: AnalyticsBusinessSnapshot) -> list[AISignal]:
    signals: list[AISignal] = []
    for product in snapshot.top_products[:3]:
        if _is_available(product.revenue):
            signals.append(
                AISignal(
                    signal_type=AISignalType.TOP_PRODUCT,
                    organization_id=product.organization_id,
                    entity_type="product",
                    entity_id=product.product_external_id,
                    severity=AIInsightSeverity.INFO,
                    current_value=product.revenue.value,
                    previous_value=product.revenue.previous_value,
                    absolute_change=product.revenue.delta,
                    percentage_change=product.revenue.percent_delta,
                    metric_key="product_revenue",
                    period=snapshot.period,
                    confidence=_confidence_from_metric(product.revenue),
                    data_status=product.revenue.data_status,
                    coverage=product.revenue.coverage,
                    evidence=[
                        _metric_evidence(
                            "product_revenue", product.revenue, note=product.product_name
                        )
                    ],
                    drilldown={
                        "target": "products",
                        "product_external_id": product.product_external_id,
                    },
                )
            )
    for product in snapshot.growing_products[:3]:
        if _can_emit_metric_signal(product.revenue_change_pct, product.revenue):
            signals.append(_product_change_signal(product, AISignalType.FAST_GROWING_PRODUCT))
    for product in snapshot.declining_products[:3]:
        if _can_emit_metric_signal(product.revenue_change_pct, product.revenue):
            signals.append(_product_change_signal(product, AISignalType.DECLINING_PRODUCT))
    for product in snapshot.slow_products[:3]:
        if _can_emit_inventory_signal(product, AISignalType.SLOW_MOVING_PRODUCT):
            signals.append(_inventory_product_signal(product, AISignalType.SLOW_MOVING_PRODUCT))
    for product in snapshot.low_stock_products[:3]:
        if not _can_emit_inventory_signal(product, AISignalType.LOW_STOCK):
            continue
        signal_type = (
            AISignalType.OUT_OF_STOCK
            if (product.current_stock.value or Decimal("0")) <= 0
            else AISignalType.LOW_STOCK
        )
        signals.append(_inventory_product_signal(product, signal_type))
    for product in snapshot.overstock_products[:3]:
        if _can_emit_inventory_signal(product, AISignalType.OVERSTOCK):
            signals.append(_inventory_product_signal(product, AISignalType.OVERSTOCK))
    for product in snapshot.stockout_risk_products[:3]:
        if _can_emit_inventory_signal(product, AISignalType.STOCKOUT_RISK):
            signals.append(_inventory_product_signal(product, AISignalType.STOCKOUT_RISK))
    return [signal for signal in signals if signal is not None]


def _customer_signals(snapshot: AnalyticsBusinessSnapshot) -> list[AISignal]:
    signals: list[AISignal] = []
    for customer in snapshot.top_customers[:3]:
        signal = _customer_metric_signal(customer, AISignalType.TOP_CUSTOMER, customer.revenue)
        if signal is not None:
            signals.append(signal)
    for customer in snapshot.at_risk_customers[:3]:
        signal_type = (
            AISignalType.AT_RISK_CUSTOMER
            if customer.segment == "AT_RISK"
            else AISignalType.DECLINING_CUSTOMER
        )
        signal = _customer_metric_signal(customer, signal_type, customer.revenue)
        if signal is not None:
            signals.append(signal)
    for customer in snapshot.lost_customers[:3]:
        signal = _customer_metric_signal(
            customer, AISignalType.INACTIVE_CUSTOMER, customer.days_since_last_order
        )
        if signal is not None:
            signals.append(signal)
    return signals


def _organization_signals(snapshot: AnalyticsBusinessSnapshot) -> list[AISignal]:
    signals: list[AISignal] = []
    for item in snapshot.organization_comparison[:5]:
        revenue = item.metrics.revenue
        if revenue.percent_delta is None:
            continue
        signal_type = (
            AISignalType.ORGANIZATION_GROWTH
            if revenue.percent_delta > 0
            else AISignalType.ORGANIZATION_DECLINE
        )
        if revenue.percent_delta == 0:
            continue
        signals.append(
            AISignal(
                signal_type=signal_type,
                organization_id=item.organization_id,
                entity_type="organization",
                entity_id=str(item.organization_id),
                severity=_severity_from_percent(revenue.percent_delta),
                current_value=revenue.value,
                previous_value=revenue.previous_value,
                absolute_change=revenue.delta,
                percentage_change=revenue.percent_delta,
                metric_key="organization_revenue",
                period=snapshot.period,
                confidence=_confidence_from_metric(revenue),
                data_status=revenue.data_status,
                coverage=revenue.coverage,
                evidence=[
                    _metric_evidence("organization_revenue", revenue, note=item.organization_name)
                ],
                drilldown={"target": "organizations", "organization_id": str(item.organization_id)},
            )
        )
    return signals


def _inventory_signals(snapshot: AnalyticsBusinessSnapshot) -> list[AISignal]:
    signals: list[AISignal] = []
    for opportunity in snapshot.inventory[:3]:
        signals.append(
            AISignal(
                signal_type=AISignalType.STOCK_TRANSFER_OPPORTUNITY,
                organization_id=opportunity.from_organization_id,
                entity_type="product",
                entity_id=opportunity.product_external_id,
                severity=AIInsightSeverity.MEDIUM,
                current_value=opportunity.source_stock.value,
                previous_value=opportunity.destination_stock.value,
                absolute_change=None,
                percentage_change=None,
                metric_key="inventory_transfer_opportunity",
                period=snapshot.period,
                confidence=0.75,
                data_status=AnalyticsDataStatus.PARTIAL,
                coverage=None,
                evidence=[
                    AIEvidence(
                        metric="source_stock",
                        current=opportunity.source_stock.value,
                        note=opportunity.from_organization_name,
                    ),
                    AIEvidence(
                        metric="destination_stock",
                        current=opportunity.destination_stock.value,
                        note=opportunity.to_organization_name,
                    ),
                ],
                drilldown={
                    "target": "inventory",
                    "product_external_id": opportunity.product_external_id,
                    "from_organization_id": str(opportunity.from_organization_id),
                    "to_organization_id": str(opportunity.to_organization_id),
                },
            )
        )
    return signals


def _finance_signals(snapshot: AnalyticsBusinessSnapshot) -> list[AISignal]:
    signals: list[AISignal] = []
    payments = snapshot.business.payments_received
    if payments.percent_delta not in {None, Decimal("0")}:
        signals.append(
            AISignal(
                signal_type=AISignalType.PAYMENT_CHANGE,
                severity=_severity_from_percent(payments.percent_delta),
                current_value=payments.value,
                previous_value=payments.previous_value,
                absolute_change=payments.delta,
                percentage_change=payments.percent_delta,
                metric_key="payments_received",
                period=snapshot.period,
                confidence=_confidence_from_metric(payments),
                data_status=payments.data_status,
                coverage=payments.coverage,
                evidence=[_metric_evidence("payments_received", payments)],
                drilldown={"target": "finance", "metric": "payments_received"},
            )
        )
    returns = snapshot.business.customer_return_value
    if returns.value not in {None, Decimal("0")}:
        signals.append(
            AISignal(
                signal_type=AISignalType.RETURN_SPIKE,
                severity=AIInsightSeverity.MEDIUM,
                current_value=returns.value,
                previous_value=returns.previous_value,
                absolute_change=returns.delta,
                percentage_change=returns.percent_delta,
                metric_key="customer_return_value",
                period=snapshot.period,
                confidence=_confidence_from_metric(returns),
                data_status=returns.data_status,
                coverage=returns.coverage,
                evidence=[_metric_evidence("customer_return_value", returns)],
                drilldown={"target": "finance", "metric": "returns"},
            )
        )
    visits = snapshot.business.visits
    if visits.percent_delta not in {None, Decimal("0")}:
        signals.append(
            AISignal(
                signal_type=AISignalType.VISIT_CHANGE,
                severity=_severity_from_percent(visits.percent_delta),
                current_value=visits.value,
                previous_value=visits.previous_value,
                absolute_change=visits.delta,
                percentage_change=visits.percent_delta,
                metric_key="visits",
                period=snapshot.period,
                confidence=_confidence_from_metric(visits),
                data_status=visits.data_status,
                coverage=visits.coverage,
                evidence=[_metric_evidence("visits", visits)],
                drilldown={"target": "visits", "metric": "visits"},
            )
        )
    return signals


def _data_quality_signals(snapshot: AnalyticsBusinessSnapshot) -> list[AISignal]:
    signals: list[AISignal] = []
    for item in snapshot.data_quality.items:
        if item.data_status in {
            AnalyticsDataStatus.NO_VERIFIED_DATA,
            AnalyticsDataStatus.PARTIAL,
            AnalyticsDataStatus.UNRESOLVED,
            AnalyticsDataStatus.INSUFFICIENT_HISTORY,
        }:
            signals.append(_data_quality_signal(snapshot, item))
    return signals[:8]


def _product_change_signal(product: AnalyticsProductItem, signal_type: AISignalType) -> AISignal:
    metric = product.revenue_change_pct
    return AISignal(
        signal_type=signal_type,
        organization_id=product.organization_id,
        entity_type="product",
        entity_id=product.product_external_id,
        severity=_severity_from_percent(metric.value),
        current_value=product.revenue.value,
        previous_value=product.revenue.previous_value,
        absolute_change=product.revenue.delta,
        percentage_change=metric.value,
        metric_key="product_revenue_change_pct",
        period=metric.period,
        confidence=_confidence_from_metric(metric),
        data_status=_worst_data_status(product.revenue.data_status, metric.data_status),
        coverage=metric.coverage,
        evidence=[
            _metric_evidence("product_revenue", product.revenue, note=product.product_name),
            _metric_evidence("product_revenue_change_pct", metric),
        ],
        drilldown={"target": "products", "product_external_id": product.product_external_id},
    )


def _inventory_product_signal(product: AnalyticsProductItem, signal_type: AISignalType) -> AISignal:
    severity = AIInsightSeverity.MEDIUM
    if signal_type in {AISignalType.OUT_OF_STOCK, AISignalType.STOCKOUT_RISK}:
        severity = AIInsightSeverity.HIGH
    elif signal_type == AISignalType.OVERSTOCK:
        severity = AIInsightSeverity.LOW
    signal_status = _inventory_signal_status(product, signal_type)
    return AISignal(
        signal_type=signal_type,
        organization_id=product.organization_id,
        entity_type="product",
        entity_id=product.product_external_id,
        severity=severity,
        current_value=product.current_stock.value,
        previous_value=product.days_of_stock.value,
        absolute_change=None,
        percentage_change=None,
        metric_key="current_stock",
        period=product.current_stock.period or product.days_of_stock.period,
        confidence=_confidence_from_metric(product.current_stock),
        data_status=signal_status,
        coverage=product.current_stock.coverage,
        evidence=[
            _metric_evidence("current_stock", product.current_stock, note=product.product_name),
            _metric_evidence("days_of_stock", product.days_of_stock),
        ],
        drilldown={"target": "inventory", "product_external_id": product.product_external_id},
    )


def _customer_metric_signal(
    customer: AnalyticsCustomerItem,
    signal_type: AISignalType,
    metric: AnalyticsMetricValue,
) -> AISignal | None:
    if not _can_emit_customer_signal(signal_type, metric):
        return None
    organization_id = customer.organization_ids[0] if len(customer.organization_ids) == 1 else None
    return AISignal(
        signal_type=signal_type,
        organization_id=organization_id,
        entity_type="customer",
        entity_id=customer.customer_external_id,
        severity=_severity_from_percent(metric.percent_delta)
        if metric.percent_delta is not None
        else AIInsightSeverity.INFO,
        current_value=metric.value,
        previous_value=metric.previous_value,
        absolute_change=metric.delta,
        percentage_change=metric.percent_delta,
        metric_key="customer_metric",
        period=metric.period or customer.revenue.period,
        confidence=_confidence_from_metric(metric),
        data_status=metric.data_status,
        coverage=metric.coverage,
        evidence=[_metric_evidence("customer_metric", metric, note=customer.customer_name)],
        drilldown={"target": "customers", "customer_external_id": customer.customer_external_id},
    )


def _can_emit_customer_signal(
    signal_type: AISignalType,
    metric: AnalyticsMetricValue,
) -> bool:
    if not _can_emit_metric_signal(metric):
        return False
    if signal_type == AISignalType.TOP_CUSTOMER:
        return (metric.value or Decimal("0")) > 0
    return True


def _can_emit_inventory_signal(
    product: AnalyticsProductItem,
    signal_type: AISignalType,
) -> bool:
    if not _can_emit_metric_signal(product.current_stock):
        return False
    if signal_type == AISignalType.SLOW_MOVING_PRODUCT:
        return _can_emit_metric_signal(product.sales_velocity_30d, product.current_stock)
    if signal_type == AISignalType.STOCKOUT_RISK:
        return _can_emit_metric_signal(
            product.days_of_stock,
            product.current_stock,
            excluded_statuses={AnalyticsDataStatus.INSUFFICIENT_HISTORY},
        )
    if signal_type in {AISignalType.OUT_OF_STOCK, AISignalType.LOW_STOCK, AISignalType.OVERSTOCK}:
        return True
    return False


def _inventory_signal_status(
    product: AnalyticsProductItem,
    signal_type: AISignalType,
) -> AnalyticsDataStatus:
    if signal_type in {AISignalType.OUT_OF_STOCK, AISignalType.LOW_STOCK, AISignalType.OVERSTOCK}:
        return product.current_stock.data_status
    if signal_type == AISignalType.SLOW_MOVING_PRODUCT:
        return _worst_data_status(
            product.current_stock.data_status,
            product.sales_velocity_30d.data_status,
        )
    return _worst_data_status(product.current_stock.data_status, product.days_of_stock.data_status)


def _can_emit_metric_signal(
    primary: AnalyticsMetricValue,
    supporting: AnalyticsMetricValue | None = None,
    *,
    excluded_statuses: set[AnalyticsDataStatus] | None = None,
) -> bool:
    disallowed = {
        AnalyticsDataStatus.NO_DATA,
        AnalyticsDataStatus.NO_VERIFIED_DATA,
        AnalyticsDataStatus.NOT_AVAILABLE,
        AnalyticsDataStatus.UNRESOLVED,
        AnalyticsDataStatus.NOT_SUPPORTED,
        AnalyticsDataStatus.ANALYSIS_PENDING,
    }
    if excluded_statuses:
        disallowed.update(excluded_statuses)
    if primary.data_status in disallowed:
        return False
    if primary.value is None and primary.percent_delta is None and primary.delta is None:
        return False
    if supporting is not None and supporting.data_status in disallowed:
        return False
    return True


def _data_quality_signal(
    snapshot: AnalyticsBusinessSnapshot,
    item: AnalyticsDataQualityEntry,
) -> AISignal:
    return AISignal(
        signal_type=AISignalType.DATA_QUALITY_WARNING,
        severity=AIInsightSeverity.MEDIUM,
        current_value=None,
        previous_value=None,
        absolute_change=None,
        percentage_change=None,
        metric_key=item.metric_key,
        period=snapshot.period,
        confidence=item.confidence or 1.0,
        data_status=item.data_status,
        coverage=item.coverage,
        evidence=[
            AIEvidence(
                metric=item.metric_key,
                note=item.message or ", ".join(item.missing_fields) or item.data_status.value,
            )
        ],
        drilldown={"target": "data_quality", "metric_key": item.metric_key},
    )


def _metric_evidence(
    metric_key: str, metric: AnalyticsMetricValue, *, note: str | None = None
) -> AIEvidence:
    return AIEvidence(
        metric=metric_key,
        current=metric.value,
        previous=metric.previous_value,
        change_percent=metric.percent_delta,
        note=note or metric.note,
    )


def _severity_from_percent(value: Decimal | None) -> AIInsightSeverity:
    if value is None:
        return AIInsightSeverity.INFO
    absolute = abs(value)
    if absolute >= Decimal("50"):
        return AIInsightSeverity.CRITICAL
    if absolute >= Decimal("30"):
        return AIInsightSeverity.HIGH
    if absolute >= Decimal("15"):
        return AIInsightSeverity.MEDIUM
    if absolute > 0:
        return AIInsightSeverity.LOW
    return AIInsightSeverity.INFO


def _confidence_from_metric(metric: AnalyticsMetricValue) -> float:
    if metric.confidence is not None:
        return metric.confidence
    if metric.coverage is not None:
        return max(0.0, min(1.0, metric.coverage))
    return 1.0 if metric.data_status == AnalyticsDataStatus.AVAILABLE else 0.6


def _is_available(metric: AnalyticsMetricValue) -> bool:
    return metric.value is not None and metric.data_status not in {
        AnalyticsDataStatus.NO_DATA,
        AnalyticsDataStatus.NO_VERIFIED_DATA,
        AnalyticsDataStatus.NOT_AVAILABLE,
    }


def _worst_data_status(*statuses: AnalyticsDataStatus) -> AnalyticsDataStatus:
    priority = {
        AnalyticsDataStatus.AVAILABLE: 0,
        AnalyticsDataStatus.PARTIAL: 1,
        AnalyticsDataStatus.UNRESOLVED: 2,
        AnalyticsDataStatus.INSUFFICIENT_HISTORY: 3,
        AnalyticsDataStatus.NO_DATA: 4,
        AnalyticsDataStatus.NO_VERIFIED_DATA: 5,
        AnalyticsDataStatus.NOT_AVAILABLE: 6,
        AnalyticsDataStatus.PERMISSION_RESTRICTED: 7,
        AnalyticsDataStatus.NOT_SUPPORTED: 8,
        AnalyticsDataStatus.ANALYSIS_PENDING: 9,
    }
    return max(statuses, key=lambda item: priority.get(item, 100))
