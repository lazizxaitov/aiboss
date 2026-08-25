"""Contracts and provider boundaries for AI analytics."""

from __future__ import annotations

from typing import Protocol

from app.core.ai_analytics.models import (
    AIAnalyticsInputContract,
    AIInsightCard,
    AIProviderResponse,
    AIProviderStatus,
    AISignal,
    ExecutiveBusinessBrief,
)


class AIAnalyticsProvider(Protocol):
    """Provider adapter for safe LLM-backed AI analytics augmentation."""

    def generate_brief(
        self,
        *,
        payload: AIAnalyticsInputContract,
        deterministic_signals: list[AISignal],
        deterministic_insights: list[AIInsightCard],
        executive_brief: ExecutiveBusinessBrief,
        language: str,
    ) -> tuple[AIProviderResponse | None, AIProviderStatus]:
        """Return structured provider output or provider status for fallback."""
