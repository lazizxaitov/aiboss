"""AI analytics foundation built on top of deterministic Canonical V2 analytics."""

from app.core.ai_analytics.contracts import AIAnalyticsProvider
from app.core.ai_analytics.models import (
    AIAnalyticsInputContract,
    AIAnalyticsResult,
    AIDashboardFeedItem,
    AIDashboardSemanticSize,
    AIEntityRef,
    AIEvidence,
    AIInsightSeverity,
    AIInsightType,
    AISignal,
    AISignalType,
    ExecutiveBusinessBrief,
)
from app.core.ai_analytics.provider import NoopAIAnalyticsProvider, default_provider
from app.core.ai_analytics.service import AIAnalyticsService

__all__ = [
    "AIAnalyticsInputContract",
    "AIAnalyticsProvider",
    "AIAnalyticsResult",
    "AIAnalyticsService",
    "AIDashboardFeedItem",
    "AIDashboardSemanticSize",
    "AIEvidence",
    "AIEntityRef",
    "AIInsightSeverity",
    "AIInsightType",
    "AISignal",
    "AISignalType",
    "ExecutiveBusinessBrief",
    "NoopAIAnalyticsProvider",
    "default_provider",
]
