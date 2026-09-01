"""AI analytics orchestration service on top of Canonical V2 analytics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from json import dumps
from time import perf_counter

from app.core.ai_analytics.context import build_input_contract
from app.core.ai_analytics.insights import build_insights
from app.core.ai_analytics.models import (
    AIAnalyticsCacheMetadata,
    AIAnalyticsResult,
    AIInsightCard,
    AIInsightMetric,
    AIInsightType,
    AIProviderHealth,
    AIProviderStatus,
    ExecutiveBusinessBrief,
)
from app.core.ai_analytics.provider import default_provider
from app.core.ai_analytics.ranking import build_dashboard_feed, deduplicate_signals, rank_signals
from app.core.ai_analytics.signals import build_signals
from app.core.ai_analytics.validation import (
    build_provider_brief,
    validate_provider_response,
)
from app.core.analytics.models import AnalyticsBusinessSnapshot
from app.core.config import settings


class AIAnalyticsService:
    """Build deterministic and provider-assisted AI analytics from canonical analytics."""

    _cache: dict[str, AIAnalyticsResult] = {}

    def __init__(self, provider=None) -> None:
        self.provider = provider or default_provider()

    def analyze(
        self,
        snapshot: AnalyticsBusinessSnapshot,
        *,
        language: str | None = None,
        force_refresh: bool = False,
        include_provider: bool = True,
    ) -> AIAnalyticsResult:
        started = perf_counter()
        payload = build_input_contract(snapshot)
        signals = deduplicate_signals(rank_signals(build_signals(snapshot)))
        deterministic_insights = build_insights(signals)
        deterministic_brief = self._build_executive_brief(snapshot, deterministic_insights)

        provider_language = (language or settings.ai_analytics_language).strip().lower() or "ru"
        context_hash = self._analytics_context_hash(payload, signals)
        cache_key = self._cache_key(payload, context_hash, provider_language, include_provider)
        if not force_refresh:
            cached = self._cache.get(cache_key)
            if cached and cached.cache_metadata and (
                cached.cache_metadata.expires_at is None
                or cached.cache_metadata.expires_at >= datetime.now(UTC)
            ):
                return cached

        validated_insights = deterministic_insights
        rejected_provider_insights: list[str] = []
        brief = deterministic_brief
        provider_status = AIProviderStatus(
            provider="disabled",
            model=None,
            health=AIProviderHealth.DISABLED,
            used_fallback=True,
            prompt_version=settings.ai_analytics_prompt_version,
        )

        provider_response = None
        if include_provider:
            try:
                provider_response, provider_status = self._invoke_provider(
                    payload=payload,
                    deterministic_signals=signals,
                    deterministic_insights=deterministic_insights,
                    deterministic_brief=deterministic_brief,
                    language=provider_language,
                )
            except Exception as exc:
                provider_status = AIProviderStatus(
                    provider=getattr(self.provider, "provider_name", "unknown"),
                    model=getattr(self.provider, "model", None),
                    health=AIProviderHealth.UNAVAILABLE,
                    used_fallback=True,
                    prompt_version=settings.ai_analytics_prompt_version,
                    error_code="PROVIDER_EXCEPTION",
                    error_message=str(exc),
                )

        if provider_response is not None:
            validated_insights, rejected_provider_insights = validate_provider_response(
                deterministic_signals=signals,
                deterministic_insights=deterministic_insights,
                provider_response=provider_response,
            )
            if validated_insights:
                brief = build_provider_brief(
                    provider_response=provider_response,
                    deterministic_brief=deterministic_brief,
                    validated_insights=validated_insights,
                )
            else:
                provider_status.used_fallback = True
                provider_status.health = AIProviderHealth.DEGRADED

        ranked = validated_insights[:12]
        cache_metadata = AIAnalyticsCacheMetadata(
            cache_key=cache_key,
            analytics_context_hash=context_hash,
            prompt_version=settings.ai_analytics_prompt_version,
            provider=provider_status.provider,
            model=provider_status.model,
            generated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC)
            + timedelta(seconds=settings.ai_analytics_cache_ttl_seconds),
        )
        if provider_status.latency_ms is None:
            provider_status.latency_ms = round((perf_counter() - started) * 1000, 2)

        result = AIAnalyticsResult(
            snapshot=snapshot,
            input_contract=payload,
            signals=signals,
            top_insights=ranked[:6],
            watchlist=ranked[6:10],
            opportunities=[item for item in ranked if item.type == AIInsightType.OPPORTUNITY.value][
                :5
            ],
            data_warnings=[
                item for item in ranked if item.type == AIInsightType.DATA_QUALITY.value
            ][:5],
            executive_brief=brief,
            dashboard_feed=build_dashboard_feed(ranked),
            provider_status=provider_status,
            cache_metadata=cache_metadata,
            rejected_provider_insights=rejected_provider_insights,
        )
        self._cache[cache_key] = result
        return result

    def _invoke_provider(
        self,
        *,
        payload,
        deterministic_signals,
        deterministic_insights,
        deterministic_brief,
        language: str,
    ):
        if hasattr(self.provider, "generate_brief"):
            return self.provider.generate_brief(
                payload=payload,
                deterministic_signals=deterministic_signals,
                deterministic_insights=deterministic_insights,
                executive_brief=deterministic_brief,
                language=language,
            )

        rewritten_insights, rewritten_brief = self.provider.rewrite_insights(
            payload=payload,
            deterministic_signals=deterministic_signals,
            deterministic_insights=deterministic_insights,
            executive_brief=deterministic_brief,
        )
        if (
            rewritten_insights is deterministic_insights
            and rewritten_brief is deterministic_brief
        ):
            return None, AIProviderStatus(
                provider=getattr(self.provider, "provider_name", "legacy"),
                model=getattr(self.provider, "model", None),
                health=AIProviderHealth.DEGRADED,
                used_fallback=False,
                prompt_version=settings.ai_analytics_prompt_version,
            )

        return self._legacy_rewrite_to_response(
            deterministic_signals=deterministic_signals,
            rewritten_insights=rewritten_insights,
            rewritten_brief=rewritten_brief,
        ), AIProviderStatus(
            provider=getattr(self.provider, "provider_name", "legacy"),
            model=getattr(self.provider, "model", None),
            health=AIProviderHealth.AVAILABLE,
            used_fallback=False,
            prompt_version=settings.ai_analytics_prompt_version,
        )

    def _legacy_rewrite_to_response(
        self,
        *,
        deterministic_signals,
        rewritten_insights,
        rewritten_brief,
    ):
        signal_by_entity = {
            (signal.entity_type, signal.entity_id): signal for signal in deterministic_signals
        }
        rewrites = []
        for insight in rewritten_insights:
            signal = signal_by_entity.get((insight.entity_type, insight.entity_id))
            if signal is None:
                continue
            rewrites.append(
                {
                    "signal_id": signal.signal_id,
                    "title": insight.title,
                    "summary": insight.summary,
                    "recommended_action": insight.recommendation,
                    "confidence": signal.confidence,
                    "fact_statement": insight.summary,
                    "interpretation": rewritten_brief.business_status,
                    "limitations": [],
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
        from app.core.ai_analytics.models import AIProviderResponse

        return AIProviderResponse(
            headline=rewritten_brief.headline,
            executive_summary=rewritten_brief.business_status,
            insights=rewrites,
            provider=getattr(self.provider, "provider_name", "legacy"),
            model=getattr(self.provider, "model", None),
            prompt_version=settings.ai_analytics_prompt_version,
        )

    def legacy_insights(self, snapshot: AnalyticsBusinessSnapshot) -> list[AIInsightCard]:
        """Compatibility adapter for the existing dashboard workspace layer."""

        result = self.analyze(snapshot)
        return result.top_insights + result.watchlist

    def _build_executive_brief(
        self,
        snapshot: AnalyticsBusinessSnapshot,
        insights: list[AIInsightCard],
    ) -> ExecutiveBusinessBrief:
        top = insights[:4]
        risks = [
            item
            for item in insights
            if item.type in {AIInsightType.RISK.value, AIInsightType.DATA_QUALITY.value}
        ][:4]
        opportunities = [
            item
            for item in insights
            if item.type
            in {
                AIInsightType.OPPORTUNITY.value,
                AIInsightType.PRODUCT.value,
                AIInsightType.INVENTORY.value,
            }
        ][:4]
        organization_watch = [
            item for item in insights if item.type == AIInsightType.ORGANIZATION.value
        ][:4]
        data_warnings = [
            item for item in insights if item.type == AIInsightType.DATA_QUALITY.value
        ][:4]

        headline = "Бизнес под контролем"
        if top:
            headline = top[0].title

        status = "Стабильно"
        if risks:
            status = "Есть риски, требующие внимания"
        elif opportunities:
            status = "Есть возможности для роста"

        key_numbers = [
            AIInsightMetric(
                label="Выручка",
                current=str(snapshot.business.revenue.value)
                if snapshot.business.revenue.value is not None
                else None,
            ),
            AIInsightMetric(
                label="Продано единиц",
                current=str(snapshot.business.sold_units.value)
                if snapshot.business.sold_units.value is not None
                else None,
            ),
            AIInsightMetric(
                label="Поступления",
                current=str(snapshot.business.payments_received.value)
                if snapshot.business.payments_received.value is not None
                else None,
            ),
            AIInsightMetric(
                label="Возвраты",
                current=str(snapshot.business.customer_return_value.value)
                if snapshot.business.customer_return_value.value is not None
                else None,
            ),
        ]

        return ExecutiveBusinessBrief(
            headline=headline,
            business_status=status,
            key_numbers=key_numbers,
            top_insights=top,
            risks=risks,
            opportunities=opportunities,
            organization_watch=organization_watch,
            data_warnings=data_warnings,
        )

    def _analytics_context_hash(self, payload, signals) -> str:  # type: ignore[no-untyped-def]
        serialized = dumps(
            {
                "context": payload.context.model_dump(mode="json"),
                "business": payload.executive.get("business", {}),
                "signal_ids": [signal.signal_id for signal in signals],
                "signal_types": [signal.signal_type.value for signal in signals],
                "orgs": [str(org_id) for org_id in payload.context.organization_ids],
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return sha256(serialized.encode("utf-8")).hexdigest()

    def _cache_key(
        self,
        payload,
        context_hash: str,
        language: str,
        include_provider: bool,
    ) -> str:  # type: ignore[no-untyped-def]
        serialized = dumps(
            {
                "provider": settings.ai_analytics_provider,
                "model": settings.ai_analytics_model,
                "include_provider": include_provider,
                "language": language,
                "prompt_version": settings.ai_analytics_prompt_version,
                "context_hash": context_hash,
                "period": payload.context.period.model_dump(mode="json"),
                "organization_ids": [str(org_id) for org_id in payload.context.organization_ids],
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return sha256(serialized.encode("utf-8")).hexdigest()
