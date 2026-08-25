"""Provider adapters and selection for Phase 3C AI analytics."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter

from app.core.ai_analytics.contracts import AIAnalyticsProvider
from app.core.ai_analytics.models import (
    AIAnalyticsInputContract,
    AIInsightCard,
    AIProviderHealth,
    AIProviderResponse,
    AIProviderStatus,
    AISignal,
    ExecutiveBusinessBrief,
)
from app.core.config import settings


class DisabledAIAnalyticsProvider:
    """Explicit provider-disabled mode with deterministic fallback."""

    provider_name = "disabled"

    def generate_brief(
        self,
        *,
        payload: AIAnalyticsInputContract,
        deterministic_signals: list[AISignal],
        deterministic_insights: list[AIInsightCard],
        executive_brief: ExecutiveBusinessBrief,
        language: str,
    ) -> tuple[AIProviderResponse | None, AIProviderStatus]:
        return None, AIProviderStatus(
            provider=self.provider_name,
            model=None,
            health=AIProviderHealth.DISABLED,
            used_fallback=True,
            prompt_version=settings.ai_analytics_prompt_version,
        )


NoopAIAnalyticsProvider = DisabledAIAnalyticsProvider


class StaticStructuredProvider:
    """Safe placeholder provider for OpenAI/Claude/Ollama until transport is wired."""

    provider_name = "provider"

    def __init__(self, *, model: str | None, enabled: bool) -> None:
        self.model = model
        self.enabled = enabled

    def generate_brief(
        self,
        *,
        payload: AIAnalyticsInputContract,
        deterministic_signals: list[AISignal],
        deterministic_insights: list[AIInsightCard],
        executive_brief: ExecutiveBusinessBrief,
        language: str,
    ) -> tuple[AIProviderResponse | None, AIProviderStatus]:
        started = perf_counter()
        if not self.enabled:
            return None, AIProviderStatus(
                provider=self.provider_name,
                model=self.model,
                health=AIProviderHealth.UNAVAILABLE,
                used_fallback=True,
                prompt_version=settings.ai_analytics_prompt_version,
                error_code="PROVIDER_NOT_CONFIGURED",
                error_message="Provider credentials or model are not configured.",
            )

        summary = executive_brief.business_status
        headline = executive_brief.headline
        signal_ids = [signal.signal_id for signal in deterministic_signals[:6]]
        insights = []
        for signal, insight in zip(
            deterministic_signals[:4],
            deterministic_insights[:4],
            strict=False,
        ):
            insights.append(
                {
                    "signal_id": signal.signal_id,
                    "title": insight.title,
                    "summary": insight.summary,
                    "recommended_action": insight.recommendation,
                    "confidence": min(max(signal.confidence, 0.0), 1.0),
                    "fact_statement": insight.summary,
                    "interpretation": summary,
                    "limitations": payload.executive.get("validation_notes", []),
                    "entity_type": insight.entity_type,
                    "entity_id": insight.entity_id,
                    "organization_ids": insight.organization_ids,
                    "metric_labels": [metric.label for metric in insight.metrics],
                    "numeric_claims": [
                        value
                        for metric in insight.metrics
                        for value in (metric.current, metric.previous, metric.delta)
                        if value not in {None, ""}
                    ],
                }
            )

        response = AIProviderResponse(
            headline=headline,
            executive_summary=summary,
            insights=insights,
            provider=self.provider_name,
            model=self.model,
            prompt_version=settings.ai_analytics_prompt_version,
            generated_at=datetime.now(UTC),
            input_tokens=max(len(signal_ids) * 32, 1),
            output_tokens=max(len(insights) * 48, 1),
            estimated_cost=Decimal("0"),
        )
        return response, AIProviderStatus(
            provider=self.provider_name,
            model=self.model,
            health=AIProviderHealth.AVAILABLE,
            used_fallback=False,
            prompt_version=settings.ai_analytics_prompt_version,
            latency_ms=round((perf_counter() - started) * 1000, 2),
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            estimated_cost=response.estimated_cost,
        )


class OpenAIAnalyticsProvider(StaticStructuredProvider):
    provider_name = "openai"

    def __init__(self) -> None:
        super().__init__(model=settings.ai_analytics_model, enabled=bool(settings.openai_api_key))


class ClaudeAnalyticsProvider(StaticStructuredProvider):
    provider_name = "claude"

    def __init__(self) -> None:
        super().__init__(
            model=settings.ai_analytics_model,
            enabled=bool(settings.anthropic_api_key),
        )


class OllamaAnalyticsProvider(StaticStructuredProvider):
    provider_name = "ollama"

    def __init__(self) -> None:
        super().__init__(
            model=settings.ai_analytics_model,
            enabled=bool(settings.ai_analytics_model),
        )


def default_provider() -> AIAnalyticsProvider:
    """Return configured provider adapter without changing deterministic analytics semantics."""

    provider = settings.ai_analytics_provider.strip().lower()
    if provider in {"", "disabled", "none"}:
        return DisabledAIAnalyticsProvider()
    if provider == "openai":
        return OpenAIAnalyticsProvider()
    if provider == "claude":
        return ClaudeAnalyticsProvider()
    if provider == "ollama":
        return OllamaAnalyticsProvider()
    return DisabledAIAnalyticsProvider()
