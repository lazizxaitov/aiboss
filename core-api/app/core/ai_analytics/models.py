"""Structured AI analytics models built on top of deterministic Canonical V2 facts."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.core.analytics.models import (
    AIInsightCard,
    AIInsightMetric,
    AnalyticsBusinessSnapshot,
    AnalyticsDataStatus,
    AnalyticsMetricValue,
    AnalyticsPeriodWindow,
    DashboardWidgetType,
)


class AIInsightSeverity(StrEnum):
    """Deterministic severity scale for AI signals and insights."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AIInsightType(StrEnum):
    """High-level insight categories exposed to executive consumers."""

    PERFORMANCE = "PERFORMANCE"
    OPPORTUNITY = "OPPORTUNITY"
    RISK = "RISK"
    ANOMALY = "ANOMALY"
    CUSTOMER = "CUSTOMER"
    PRODUCT = "PRODUCT"
    INVENTORY = "INVENTORY"
    ORGANIZATION = "ORGANIZATION"
    FINANCE = "FINANCE"
    DATA_QUALITY = "DATA_QUALITY"


class AISignalType(StrEnum):
    """Deterministic business signal identifiers."""

    SALES_GROWTH = "SALES_GROWTH"
    SALES_DECLINE = "SALES_DECLINE"
    TOP_PRODUCT = "TOP_PRODUCT"
    FAST_GROWING_PRODUCT = "FAST_GROWING_PRODUCT"
    DECLINING_PRODUCT = "DECLINING_PRODUCT"
    SLOW_MOVING_PRODUCT = "SLOW_MOVING_PRODUCT"
    DEAD_STOCK = "DEAD_STOCK"
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    OVERSTOCK = "OVERSTOCK"
    HIGH_RETURN_PRODUCT = "HIGH_RETURN_PRODUCT"
    TOP_CUSTOMER = "TOP_CUSTOMER"
    GROWING_CUSTOMER = "GROWING_CUSTOMER"
    DECLINING_CUSTOMER = "DECLINING_CUSTOMER"
    AT_RISK_CUSTOMER = "AT_RISK_CUSTOMER"
    INACTIVE_CUSTOMER = "INACTIVE_CUSTOMER"
    ORGANIZATION_GROWTH = "ORGANIZATION_GROWTH"
    ORGANIZATION_DECLINE = "ORGANIZATION_DECLINE"
    ORGANIZATION_OUTLIER = "ORGANIZATION_OUTLIER"
    STOCKOUT_RISK = "STOCKOUT_RISK"
    STOCK_TRANSFER_OPPORTUNITY = "STOCK_TRANSFER_OPPORTUNITY"
    PAYMENT_CHANGE = "PAYMENT_CHANGE"
    RETURN_SPIKE = "RETURN_SPIKE"
    VISIT_CHANGE = "VISIT_CHANGE"
    DATA_QUALITY_WARNING = "DATA_QUALITY_WARNING"


class AIDashboardSemanticSize(StrEnum):
    """Semantic widget size hint. Layout engine decides actual placement."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    TALL = "tall"


class AIEvidence(BaseModel):
    """Evidence payload used to support a signal or insight."""

    metric: str
    current: Decimal | str | int | None = None
    previous: Decimal | str | int | None = None
    change_percent: Decimal | None = None
    note: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class AISignal(BaseModel):
    """Deterministic signal derived from canonical analytics facts."""

    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    signal_type: AISignalType
    organization_id: UUID | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    severity: AIInsightSeverity
    current_value: Decimal | None = None
    previous_value: Decimal | None = None
    absolute_change: Decimal | None = None
    percentage_change: Decimal | None = None
    metric_key: str
    period: AnalyticsPeriodWindow
    confidence: float = 1.0
    data_status: AnalyticsDataStatus = AnalyticsDataStatus.AVAILABLE
    coverage: float | None = None
    evidence: list[AIEvidence] = Field(default_factory=list)
    drilldown: dict[str, Any] = Field(default_factory=dict)


class AIEntityRef(BaseModel):
    """Entity pointer attached to an AI insight."""

    entity_type: str | None = None
    entity_id: str | None = None
    label: str | None = None


class AIDashboardFeedItem(BaseModel):
    """Machine-readable dashboard manifest row."""

    insight_id: str
    priority: int
    suggested_widget_type: DashboardWidgetType
    suggested_size: AIDashboardSemanticSize
    expires_at: datetime | None = None


class AIProviderHealth(StrEnum):
    """Runtime health state of the configured AI provider."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"


class AIProviderStatus(BaseModel):
    """Provider execution status returned alongside analytics output."""

    provider: str
    model: str | None = None
    health: AIProviderHealth
    used_fallback: bool = False
    prompt_version: str | None = None
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: Decimal | None = None
    error_code: str | None = None
    error_message: str | None = None


class AIInsightRewrite(BaseModel):
    """Validated LLM rewrite tied to one deterministic signal."""

    signal_id: str
    title: str
    summary: str
    recommended_action: str
    confidence: float
    fact_statement: str
    interpretation: str
    limitations: list[str] = Field(default_factory=list)
    entity_type: str | None = None
    entity_id: str | None = None
    organization_ids: list[UUID] = Field(default_factory=list)
    metric_labels: list[str] = Field(default_factory=list)
    numeric_claims: list[str] = Field(default_factory=list)


class AIProviderResponse(BaseModel):
    """Structured provider response before validation and mapping."""

    headline: str
    executive_summary: str
    insights: list[AIInsightRewrite] = Field(default_factory=list)
    provider: str
    model: str | None = None
    prompt_version: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: Decimal | None = None


class AIAnalyticsCacheMetadata(BaseModel):
    """Traceability and cache metadata for one AI analytics result."""

    cache_key: str
    analytics_context_hash: str
    prompt_version: str
    provider: str
    model: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None


class ExecutiveBusinessBrief(BaseModel):
    """Top-level executive brief generated from deterministic signals."""

    headline: str
    business_status: str
    key_numbers: list[AIInsightMetric] = Field(default_factory=list)
    top_insights: list[AIInsightCard] = Field(default_factory=list)
    risks: list[AIInsightCard] = Field(default_factory=list)
    opportunities: list[AIInsightCard] = Field(default_factory=list)
    organization_watch: list[AIInsightCard] = Field(default_factory=list)
    data_warnings: list[AIInsightCard] = Field(default_factory=list)


class AIAnalyticsInputContext(BaseModel):
    """Strict AI input context based on canonical snapshot filters."""

    organization_ids: list[UUID] = Field(default_factory=list)
    period: AnalyticsPeriodWindow
    comparison_period: dict[str, datetime | None] = Field(default_factory=dict)


class AIAnalyticsInputContract(BaseModel):
    """Strict structured input exposed to AI analytics layers or providers."""

    context: AIAnalyticsInputContext
    executive: dict[str, Any] = Field(default_factory=dict)
    sales: dict[str, Any] = Field(default_factory=dict)
    products: dict[str, Any] = Field(default_factory=dict)
    customers: dict[str, Any] = Field(default_factory=dict)
    inventory: dict[str, Any] = Field(default_factory=dict)
    organizations: dict[str, Any] = Field(default_factory=dict)
    payments: dict[str, Any] = Field(default_factory=dict)
    returns: dict[str, Any] = Field(default_factory=dict)
    visits: dict[str, Any] = Field(default_factory=dict)
    finance: dict[str, Any] = Field(default_factory=dict)
    data_quality: dict[str, Any] = Field(default_factory=dict)


class AIAnalyticsResult(BaseModel):
    """Full structured output of the AI analytics foundation service."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    snapshot: AnalyticsBusinessSnapshot
    input_contract: AIAnalyticsInputContract
    signals: list[AISignal] = Field(default_factory=list)
    top_insights: list[AIInsightCard] = Field(default_factory=list)
    watchlist: list[AIInsightCard] = Field(default_factory=list)
    opportunities: list[AIInsightCard] = Field(default_factory=list)
    data_warnings: list[AIInsightCard] = Field(default_factory=list)
    executive_brief: ExecutiveBusinessBrief
    dashboard_feed: list[AIDashboardFeedItem] = Field(default_factory=list)
    provider_status: AIProviderStatus | None = None
    cache_metadata: AIAnalyticsCacheMetadata | None = None
    rejected_provider_insights: list[str] = Field(default_factory=list)


class AIAnalyticsBriefResponse(BaseModel):
    """Compact API contract for provider-assisted executive brief."""

    generated_at: datetime
    executive_brief: ExecutiveBusinessBrief
    provider_status: AIProviderStatus | None = None
    cache_metadata: AIAnalyticsCacheMetadata | None = None
    rejected_provider_insights: list[str] = Field(default_factory=list)


class AIAnalyticsInsightsResponse(BaseModel):
    """Compact API contract for AI insights consumers."""

    generated_at: datetime
    top_insights: list[AIInsightCard] = Field(default_factory=list)
    watchlist: list[AIInsightCard] = Field(default_factory=list)
    opportunities: list[AIInsightCard] = Field(default_factory=list)
    data_warnings: list[AIInsightCard] = Field(default_factory=list)
    dashboard_feed: list[AIDashboardFeedItem] = Field(default_factory=list)
    provider_status: AIProviderStatus | None = None
    cache_metadata: AIAnalyticsCacheMetadata | None = None
    rejected_provider_insights: list[str] = Field(default_factory=list)


def metric_to_insight_metric(metric: AnalyticsMetricValue, label: str) -> AIInsightMetric:
    """Convert deterministic analytics metric to UI-compatible insight metric."""

    return AIInsightMetric(
        label=label,
        current=None if metric.value is None else str(metric.value),
        previous=None if metric.previous_value is None else str(metric.previous_value),
        delta=None if metric.delta is None else str(metric.delta),
        direction=None
        if metric.delta is None
        else ("up" if metric.delta > 0 else "down" if metric.delta < 0 else "flat"),
    )
