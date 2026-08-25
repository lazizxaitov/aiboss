"""Tests for Phase 3B AI analytics foundation."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.core.ai_analytics.context import build_input_contract
from app.core.ai_analytics.models import (
    AIInsightCard,
    AIInsightMetric,
    AIProviderHealth,
    AIProviderResponse,
    AIProviderStatus,
    AISignalType,
)
from app.core.ai_analytics.service import AIAnalyticsService
from app.core.ai_analytics.signals import build_signals
from app.core.analytics.engine import BusinessAnalyticsEngine
from app.core.analytics.models import AnalyticsDataStatus, AnalyticsQuery
from tests.test_analytics_engine import _seed_analytics_store


class _ExplodingProvider:
    def rewrite_insights(self, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("provider unavailable")


class _HallucinatingProvider:
    def rewrite_insights(self, **kwargs):  # type: ignore[no-untyped-def]
        deterministic_insights = kwargs["deterministic_insights"]
        executive_brief = kwargs["executive_brief"]
        hallucinated = AIInsightCard(
            id="hallucinated-insight",
            type="RISK",
            severity="high",
            priority=1,
            title="Придуманная сущность",
            summary="Провайдер сослался на несуществующий объект.",
            metrics=[AIInsightMetric(label="revenue", current="999999999")],
            evidence=["fake"],
            recommendation="ignore",
            widget_type="ai_insight",
            entity_type="customer",
            entity_id="missing-customer",
            organization_ids=[uuid4()],
        )
        return [hallucinated, *deterministic_insights], executive_brief


class _StructuredBadProvider:
    provider_name = "mock"
    model = "mock-1"

    def generate_brief(self, **kwargs):  # type: ignore[no-untyped-def]
        return (
            AIProviderResponse(
                headline="LLM headline",
                executive_summary="Provider summary",
                provider="mock",
                model="mock-1",
                prompt_version="test-v1",
                insights=[
                    {
                        "signal_id": kwargs["deterministic_signals"][0].signal_id,
                        "title": "Плохая математика",
                        "summary": "Ручная интерпретация.",
                        "recommended_action": "Проверить.",
                        "confidence": 0.8,
                        "fact_statement": "Выручка 999999999.",
                        "interpretation": "Sales fell because demand collapsed.",
                        "limitations": [],
                        "entity_type": kwargs["deterministic_signals"][0].entity_type,
                        "entity_id": kwargs["deterministic_signals"][0].entity_id,
                        "organization_ids": [],
                        "metric_labels": ["revenue"],
                        "numeric_claims": ["999999999"],
                    }
                ],
            ),
            AIProviderStatus(
                provider="mock",
                model="mock-1",
                health=AIProviderHealth.AVAILABLE,
                used_fallback=False,
                prompt_version="test-v1",
            ),
        )


class _StructuredGoodProvider:
    provider_name = "mock"
    model = "mock-1"

    def generate_brief(self, **kwargs):  # type: ignore[no-untyped-def]
        signal = next(
            item
            for item in kwargs["deterministic_signals"]
            if item.signal_type == AISignalType.TOP_PRODUCT
        )
        return (
            AIProviderResponse(
                headline="Краткий executive brief",
                executive_summary="Главные изменения за период.",
                provider="mock",
                model="mock-1",
                prompt_version="test-v1",
                insights=[
                    {
                        "signal_id": signal.signal_id,
                        "title": "Топ товар периода",
                        "summary": "Товар лидирует по выручке.",
                        "recommended_action": "Проверьте наличие и повторяемость спроса.",
                        "confidence": 0.9,
                        "fact_statement": (
                            "Текущая выручка подтверждена "
                            "детерминированным сигналом."
                        ),
                        "interpretation": "Это один из самых сильных product signals в выборке.",
                        "limitations": ["Формулировка основана только на deterministic evidence."],
                        "entity_type": signal.entity_type,
                        "entity_id": signal.entity_id,
                        "organization_ids": (
                            [signal.organization_id] if signal.organization_id else []
                        ),
                        "metric_labels": ["product_revenue"],
                        "numeric_claims": [str(signal.current_value)],
                    }
                ],
            ),
            AIProviderStatus(
                provider="mock",
                model="mock-1",
                health=AIProviderHealth.AVAILABLE,
                used_fallback=False,
                prompt_version="test-v1",
            ),
        )


def _snapshot_all():
    store, org_one, org_two = _seed_analytics_store()
    snapshot = BusinessAnalyticsEngine(store).build_snapshot(
        AnalyticsQuery(organization_ids=[org_one.organization_id, org_two.organization_id])
    )
    return snapshot, org_one, org_two


def test_ai_input_contract_uses_canonical_query_context() -> None:
    snapshot, org_one, _org_two = _snapshot_all()
    snapshot.query.organization_id = org_one.organization_id

    contract = build_input_contract(snapshot)

    assert org_one.organization_id in contract.context.organization_ids
    assert contract.finance["verified_cash_out"]["data_status"] == "AVAILABLE"
    assert contract.payments["payments_received"]["value"] is not None


def test_ai_service_generates_deterministic_insights_without_llm() -> None:
    snapshot, _org_one, _org_two = _snapshot_all()

    result = AIAnalyticsService().analyze(snapshot)

    assert result.signals
    assert result.top_insights
    assert result.dashboard_feed
    assert any(signal.signal_type.value == "TOP_PRODUCT" for signal in result.signals)
    assert any(signal.signal_type.value == "TOP_CUSTOMER" for signal in result.signals)
    assert any(signal.signal_type.value == "ORGANIZATION_DECLINE" for signal in result.signals)
    assert any(signal.signal_type.value == "RETURN_SPIKE" for signal in result.signals)


def test_ai_service_falls_back_when_provider_unavailable() -> None:
    snapshot, _org_one, _org_two = _snapshot_all()

    result = AIAnalyticsService(provider=_ExplodingProvider()).analyze(snapshot)

    assert result.top_insights
    assert result.executive_brief.top_insights


def test_ai_service_rejects_hallucinated_entities_and_numbers() -> None:
    snapshot, _org_one, _org_two = _snapshot_all()

    result = AIAnalyticsService(provider=_HallucinatingProvider()).analyze(snapshot)

    assert all(insight.id != "hallucinated-insight" for insight in result.top_insights)
    assert all(item.insight_id != "hallucinated-insight" for item in result.dashboard_feed)


def test_ai_service_rejects_structured_bad_provider_claims() -> None:
    snapshot, _org_one, _org_two = _snapshot_all()

    result = AIAnalyticsService(provider=_StructuredBadProvider()).analyze(snapshot)

    assert result.provider_status is not None
    assert result.provider_status.health == AIProviderHealth.DEGRADED
    assert result.provider_status.used_fallback is True
    assert result.rejected_provider_insights


def test_ai_service_accepts_structured_provider_output() -> None:
    snapshot, _org_one, _org_two = _snapshot_all()

    result = AIAnalyticsService(provider=_StructuredGoodProvider()).analyze(
        snapshot,
        force_refresh=True,
    )

    assert result.provider_status is not None
    assert result.provider_status.health == AIProviderHealth.AVAILABLE
    assert result.provider_status.used_fallback is False
    assert result.cache_metadata is not None
    assert result.top_insights
    assert result.top_insights[0].title == "Топ товар периода"


def test_ai_service_preserves_revenue_vs_payments_semantics() -> None:
    snapshot, _org_one, _org_two = _snapshot_all()
    result = AIAnalyticsService().analyze(snapshot)

    assert snapshot.business.revenue.value == Decimal("606000")
    assert snapshot.business.payments_received.value == Decimal("606000")
    assert snapshot.business.verified_cash_in.value == Decimal("606000")
    assert snapshot.business.verified_cash_out.value == Decimal("100000")
    assert snapshot.business.cash_flow.value == Decimal("506000")
    finance_labels = {metric.label for metric in result.executive_brief.key_numbers}
    assert "Выручка" in finance_labels
    assert "Поступления" in finance_labels
    assert "Возвраты" in finance_labels


def test_ai_service_emits_data_quality_warning_for_no_verified_data() -> None:
    snapshot, _org_one, _org_two = _snapshot_all()
    snapshot.business.verified_cash_out.data_status = snapshot.business.verified_cash_out.status = (
        snapshot.business.verified_cash_out.data_status.NO_VERIFIED_DATA
    )
    snapshot.data_quality.items.append(
        type(snapshot.data_quality.items[0])(
            metric_key="verified_cash_out",
            data_status=snapshot.business.verified_cash_out.data_status,
            message="Нет проверенных расходов.",
        )
    )

    result = AIAnalyticsService().analyze(snapshot)

    assert any(signal.metric_key == "verified_cash_out" for signal in result.signals)
    assert any(item.type == "DATA_QUALITY" for item in result.data_warnings)


def test_customer_signal_keeps_single_organization_context() -> None:
    snapshot, org_one, _org_two = _snapshot_all()

    signals = build_signals(snapshot)
    top_customer = next(
        signal for signal in signals if signal.signal_type == AISignalType.TOP_CUSTOMER
    )

    assert top_customer.organization_id == org_one.organization_id


def test_customer_signal_is_suppressed_for_no_verified_data() -> None:
    snapshot, _org_one, _org_two = _snapshot_all()
    customer = snapshot.top_customers[0]
    customer.revenue.data_status = customer.revenue.status = AnalyticsDataStatus.NO_VERIFIED_DATA
    customer.revenue.value = None
    customer.revenue.previous_value = None
    customer.revenue.delta = None
    customer.revenue.percent_delta = None

    signals = build_signals(snapshot)

    assert not any(signal.signal_type == AISignalType.TOP_CUSTOMER for signal in signals)


def test_inventory_signals_are_suppressed_for_no_data() -> None:
    snapshot, _org_one, _org_two = _snapshot_all()
    product = snapshot.low_stock_products[0]
    product.current_stock.data_status = product.current_stock.status = AnalyticsDataStatus.NO_DATA
    product.current_stock.value = Decimal("0")
    product.days_of_stock.data_status = product.days_of_stock.status = AnalyticsDataStatus.NO_DATA
    product.days_of_stock.value = None

    signals = build_signals(snapshot)

    assert not any(
        signal.entity_id == product.product_external_id
        and signal.signal_type in {AISignalType.LOW_STOCK, AISignalType.OUT_OF_STOCK}
        for signal in signals
    )


def test_stockout_risk_is_suppressed_for_insufficient_history() -> None:
    snapshot, _org_one, _org_two = _snapshot_all()
    product = snapshot.stockout_risk_products[0]
    product.current_stock.data_status = product.current_stock.status = AnalyticsDataStatus.AVAILABLE
    product.current_stock.value = Decimal("12")
    product.days_of_stock.data_status = product.days_of_stock.status = (
        AnalyticsDataStatus.INSUFFICIENT_HISTORY
    )
    product.days_of_stock.value = None

    signals = build_signals(snapshot)

    assert not any(
        signal.entity_id == product.product_external_id
        and signal.signal_type == AISignalType.STOCKOUT_RISK
        for signal in signals
    )
