"""Semantic dashboard manifest models for the layout engine boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.ai_analytics.models import AIProviderStatus
from app.core.analytics.models import (
    AnalyticsDataQualityEntry,
    AnalyticsDataStatus,
    AnalyticsPeriodWindow,
    DashboardWidgetType,
)

MANIFEST_VERSION = "phase-3d-v1"
WIDGET_REGISTRY_VERSION = "phase-3d-v1"


class DashboardOrganizationMode(StrEnum):
    """Organization selection mode for a manifest."""

    ALL = "ALL"
    SINGLE = "SINGLE"
    MULTIPLE = "MULTIPLE"


class DashboardWidgetSourceType(StrEnum):
    """Origin of a dashboard widget."""

    PERMANENT = "PERMANENT"
    AI_DYNAMIC = "AI_DYNAMIC"
    USER_PINNED = "USER_PINNED"


class DashboardSemanticSize(StrEnum):
    """Device-independent semantic sizes."""

    XS = "XS"
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"


class DashboardFlowHint(StrEnum):
    """Preferred content flow for frontend layout engine."""

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    WIDE = "wide"


class DashboardAspectHint(StrEnum):
    """Preferred aspect of a semantic widget."""

    COMPACT = "compact"
    SQUARE = "square"
    WIDE = "wide"
    TALL = "tall"


class DashboardContentDensity(StrEnum):
    """Expected content density inside a widget."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DashboardScrollBehavior(StrEnum):
    """Scroll strategy for widget contents."""

    NONE = "none"
    INTERNAL = "internal"


class DashboardWidgetCapabilities(BaseModel):
    """Registry capability contract for one widget type."""

    min_size: DashboardSemanticSize
    preferred_size: DashboardSemanticSize
    max_size: DashboardSemanticSize
    supports_horizontal_expand: bool = False
    supports_vertical_expand: bool = False
    supports_internal_scroll: bool = False
    flow: DashboardFlowHint = DashboardFlowHint.VERTICAL
    preferred_aspect: DashboardAspectHint = DashboardAspectHint.COMPACT
    content_density: DashboardContentDensity = DashboardContentDensity.MEDIUM
    scroll_behavior: DashboardScrollBehavior = DashboardScrollBehavior.NONE


class DashboardWidgetRegistryEntry(BaseModel):
    """Strict registry entry for a supported widget type."""

    widget_type: DashboardWidgetType
    description: str
    capabilities: DashboardWidgetCapabilities
    default_metric_keys: list[str] = Field(default_factory=list)
    allowed_source_types: list[DashboardWidgetSourceType] = Field(default_factory=list)


class DashboardDrilldown(BaseModel):
    """Structured drilldown target for frontend routing/filtering."""

    target: str
    entity_type: str | None = None
    entity_id: str | None = None
    organization_ids: list[UUID] = Field(default_factory=list)
    filters: dict[str, str] = Field(default_factory=dict)


class UserDashboardPreferences(BaseModel):
    """Manifest-affecting preferences without UI persistence concerns."""

    pinned_widget_ids: list[str] = Field(default_factory=list)
    hidden_widget_ids: list[str] = Field(default_factory=list)
    locked_position_widget_ids: list[str] = Field(default_factory=list)
    locked_size_widget_ids: list[str] = Field(default_factory=list)
    preferred_sizes: dict[str, DashboardSemanticSize] = Field(default_factory=dict)
    widget_order_preferences: dict[str, int] = Field(default_factory=dict)


class DashboardManifestContext(BaseModel):
    """Context used to generate the semantic dashboard manifest."""

    organization_mode: DashboardOrganizationMode
    organization_ids: list[UUID] = Field(default_factory=list)
    organization_names: list[str] = Field(default_factory=list)
    period: AnalyticsPeriodWindow
    language: str = "ru"


class DashboardManifestWidget(BaseModel):
    """One validated dashboard manifest widget."""

    widget_id: str
    widget_type: DashboardWidgetType
    source_type: DashboardWidgetSourceType
    title: str
    subtitle: str | None = None
    metric_keys: list[str] = Field(default_factory=list)
    signal_ids: list[str] = Field(default_factory=list)
    entity_type: str | None = None
    entity_id: str | None = None
    organization_ids: list[UUID] = Field(default_factory=list)
    semantic_size: DashboardSemanticSize
    priority: int
    priority_reason: str
    min_size: DashboardSemanticSize
    preferred_size: DashboardSemanticSize
    max_size: DashboardSemanticSize
    supports_horizontal_expand: bool = False
    supports_vertical_expand: bool = False
    supports_internal_scroll: bool = False
    flow: DashboardFlowHint = DashboardFlowHint.VERTICAL
    preferred_aspect: DashboardAspectHint = DashboardAspectHint.COMPACT
    content_density: DashboardContentDensity = DashboardContentDensity.MEDIUM
    scroll_behavior: DashboardScrollBehavior = DashboardScrollBehavior.NONE
    removable_by_ai: bool = True
    movable_by_ai: bool = True
    resizable_by_ai: bool = True
    locked_position: bool = False
    locked_size: bool = False
    pinned: bool = False
    hidden: bool = False
    drilldown: DashboardDrilldown | None = None
    summary: str | None = None
    data_status: AnalyticsDataStatus = AnalyticsDataStatus.AVAILABLE
    payload: dict[str, Any] = Field(default_factory=dict)


class DashboardLayoutPolicy(BaseModel):
    """Rules and boundaries for the downstream layout engine."""

    manifest_has_no_coordinates: bool = True
    device_independent: bool = True
    preserve_locked_widgets: bool = True
    supports_internal_scroll: bool = True
    permanent_widget_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DashboardManifestDataQuality(BaseModel):
    """Material data-quality state exposed at manifest level."""

    overall_status: AnalyticsDataStatus = AnalyticsDataStatus.NO_DATA
    surfaced_items: list[AnalyticsDataQualityEntry] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DashboardManifestCacheMetadata(BaseModel):
    """Traceability and cache metadata for one manifest."""

    cache_key: str
    analytics_context_hash: str
    ai_context_hash: str
    preferences_hash: str
    manifest_version: str = MANIFEST_VERSION
    widget_registry_version: str = WIDGET_REGISTRY_VERSION
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None


class DashboardManifest(BaseModel):
    """Stable machine-readable dashboard manifest."""

    context: DashboardManifestContext
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    manifest_version: str = MANIFEST_VERSION
    widget_registry_version: str = WIDGET_REGISTRY_VERSION
    analytics_context_hash: str
    ai_context_hash: str
    widgets: list[DashboardManifestWidget] = Field(default_factory=list)
    widget_registry: list[DashboardWidgetRegistryEntry] = Field(default_factory=list)
    layout_policy: DashboardLayoutPolicy
    data_quality: DashboardManifestDataQuality
    provider_status: AIProviderStatus | None = None
    cache_metadata: DashboardManifestCacheMetadata | None = None
    validation_errors: list[str] = Field(default_factory=list)


def semantic_size_rank(size: DashboardSemanticSize) -> int:
    """Map semantic sizes to monotonic order for validation."""

    return {
        DashboardSemanticSize.XS: 0,
        DashboardSemanticSize.S: 1,
        DashboardSemanticSize.M: 2,
        DashboardSemanticSize.L: 3,
        DashboardSemanticSize.XL: 4,
    }[size]


def default_widget_registry() -> list[DashboardWidgetRegistryEntry]:
    """Return the strict supported widget registry for Phase 3D."""

    return [
        DashboardWidgetRegistryEntry(
            widget_type=DashboardWidgetType.KPI,
            description="Single primary KPI card.",
            capabilities=DashboardWidgetCapabilities(
                min_size=DashboardSemanticSize.XS,
                preferred_size=DashboardSemanticSize.S,
                max_size=DashboardSemanticSize.S,
                flow=DashboardFlowHint.HORIZONTAL,
                preferred_aspect=DashboardAspectHint.COMPACT,
                content_density=DashboardContentDensity.LOW,
            ),
            allowed_source_types=[
                DashboardWidgetSourceType.PERMANENT,
                DashboardWidgetSourceType.USER_PINNED,
            ],
        ),
        DashboardWidgetRegistryEntry(
            widget_type=DashboardWidgetType.TREND,
            description="Compact trend widget.",
            capabilities=DashboardWidgetCapabilities(
                min_size=DashboardSemanticSize.S,
                preferred_size=DashboardSemanticSize.M,
                max_size=DashboardSemanticSize.L,
                supports_horizontal_expand=True,
                flow=DashboardFlowHint.WIDE,
                preferred_aspect=DashboardAspectHint.WIDE,
            ),
        ),
        DashboardWidgetRegistryEntry(
            widget_type=DashboardWidgetType.LINE_CHART,
            description="Wide chart for trend metrics.",
            capabilities=DashboardWidgetCapabilities(
                min_size=DashboardSemanticSize.L,
                preferred_size=DashboardSemanticSize.XL,
                max_size=DashboardSemanticSize.XL,
                supports_horizontal_expand=True,
                flow=DashboardFlowHint.WIDE,
                preferred_aspect=DashboardAspectHint.WIDE,
                content_density=DashboardContentDensity.MEDIUM,
            ),
        ),
        DashboardWidgetRegistryEntry(
            widget_type=DashboardWidgetType.BAR_CHART,
            description="Wide comparison chart.",
            capabilities=DashboardWidgetCapabilities(
                min_size=DashboardSemanticSize.L,
                preferred_size=DashboardSemanticSize.L,
                max_size=DashboardSemanticSize.XL,
                supports_horizontal_expand=True,
                flow=DashboardFlowHint.WIDE,
                preferred_aspect=DashboardAspectHint.WIDE,
                content_density=DashboardContentDensity.MEDIUM,
            ),
        ),
        DashboardWidgetRegistryEntry(
            widget_type=DashboardWidgetType.RANKING,
            description="Generic vertical ranking list.",
            capabilities=DashboardWidgetCapabilities(
                min_size=DashboardSemanticSize.M,
                preferred_size=DashboardSemanticSize.L,
                max_size=DashboardSemanticSize.XL,
                supports_vertical_expand=True,
                supports_internal_scroll=True,
                flow=DashboardFlowHint.VERTICAL,
                preferred_aspect=DashboardAspectHint.TALL,
                content_density=DashboardContentDensity.HIGH,
                scroll_behavior=DashboardScrollBehavior.INTERNAL,
            ),
        ),
        DashboardWidgetRegistryEntry(
            widget_type=DashboardWidgetType.TABLE,
            description="Large tabular business data.",
            capabilities=DashboardWidgetCapabilities(
                min_size=DashboardSemanticSize.L,
                preferred_size=DashboardSemanticSize.XL,
                max_size=DashboardSemanticSize.XL,
                supports_horizontal_expand=True,
                supports_vertical_expand=True,
                supports_internal_scroll=True,
                flow=DashboardFlowHint.WIDE,
                preferred_aspect=DashboardAspectHint.WIDE,
                content_density=DashboardContentDensity.HIGH,
                scroll_behavior=DashboardScrollBehavior.INTERNAL,
            ),
        ),
        DashboardWidgetRegistryEntry(
            widget_type=DashboardWidgetType.ALERT,
            description="Compact high-priority operational alert.",
            capabilities=DashboardWidgetCapabilities(
                min_size=DashboardSemanticSize.S,
                preferred_size=DashboardSemanticSize.M,
                max_size=DashboardSemanticSize.L,
                supports_vertical_expand=True,
                flow=DashboardFlowHint.VERTICAL,
                preferred_aspect=DashboardAspectHint.COMPACT,
            ),
        ),
        DashboardWidgetRegistryEntry(
            widget_type=DashboardWidgetType.AI_INSIGHT,
            description="AI executive brief or explanation card.",
            capabilities=DashboardWidgetCapabilities(
                min_size=DashboardSemanticSize.M,
                preferred_size=DashboardSemanticSize.M,
                max_size=DashboardSemanticSize.L,
                supports_horizontal_expand=True,
                supports_vertical_expand=True,
                flow=DashboardFlowHint.WIDE,
                preferred_aspect=DashboardAspectHint.WIDE,
            ),
        ),
        DashboardWidgetRegistryEntry(
            widget_type=DashboardWidgetType.WATCHLIST,
            description="Watchlist of risks or opportunities.",
            capabilities=DashboardWidgetCapabilities(
                min_size=DashboardSemanticSize.M,
                preferred_size=DashboardSemanticSize.L,
                max_size=DashboardSemanticSize.XL,
                supports_vertical_expand=True,
                supports_internal_scroll=True,
                flow=DashboardFlowHint.VERTICAL,
                preferred_aspect=DashboardAspectHint.TALL,
                content_density=DashboardContentDensity.HIGH,
                scroll_behavior=DashboardScrollBehavior.INTERNAL,
            ),
        ),
        DashboardWidgetRegistryEntry(
            widget_type=DashboardWidgetType.ORGANIZATION_COMPARISON,
            description="Cross-organization comparison widget.",
            capabilities=DashboardWidgetCapabilities(
                min_size=DashboardSemanticSize.L,
                preferred_size=DashboardSemanticSize.XL,
                max_size=DashboardSemanticSize.XL,
                supports_horizontal_expand=True,
                supports_vertical_expand=True,
                supports_internal_scroll=True,
                flow=DashboardFlowHint.WIDE,
                preferred_aspect=DashboardAspectHint.WIDE,
                content_density=DashboardContentDensity.HIGH,
                scroll_behavior=DashboardScrollBehavior.INTERNAL,
            ),
        ),
        DashboardWidgetRegistryEntry(
            widget_type=DashboardWidgetType.PRODUCT_RANKING,
            description="Top or risky products list.",
            capabilities=DashboardWidgetCapabilities(
                min_size=DashboardSemanticSize.M,
                preferred_size=DashboardSemanticSize.L,
                max_size=DashboardSemanticSize.XL,
                supports_vertical_expand=True,
                supports_internal_scroll=True,
                flow=DashboardFlowHint.VERTICAL,
                preferred_aspect=DashboardAspectHint.TALL,
                content_density=DashboardContentDensity.HIGH,
                scroll_behavior=DashboardScrollBehavior.INTERNAL,
            ),
        ),
        DashboardWidgetRegistryEntry(
            widget_type=DashboardWidgetType.CUSTOMER_RANKING,
            description="Top or at-risk customers list.",
            capabilities=DashboardWidgetCapabilities(
                min_size=DashboardSemanticSize.M,
                preferred_size=DashboardSemanticSize.L,
                max_size=DashboardSemanticSize.XL,
                supports_vertical_expand=True,
                supports_internal_scroll=True,
                flow=DashboardFlowHint.VERTICAL,
                preferred_aspect=DashboardAspectHint.TALL,
                content_density=DashboardContentDensity.HIGH,
                scroll_behavior=DashboardScrollBehavior.INTERNAL,
            ),
        ),
        DashboardWidgetRegistryEntry(
            widget_type=DashboardWidgetType.INVENTORY_RISK,
            description="Inventory risk list or transfer opportunity set.",
            capabilities=DashboardWidgetCapabilities(
                min_size=DashboardSemanticSize.M,
                preferred_size=DashboardSemanticSize.L,
                max_size=DashboardSemanticSize.XL,
                supports_vertical_expand=True,
                supports_internal_scroll=True,
                flow=DashboardFlowHint.VERTICAL,
                preferred_aspect=DashboardAspectHint.TALL,
                content_density=DashboardContentDensity.HIGH,
                scroll_behavior=DashboardScrollBehavior.INTERNAL,
            ),
        ),
        DashboardWidgetRegistryEntry(
            widget_type=DashboardWidgetType.VISIT_SUMMARY,
            description="Field visits or sales rep visit summary.",
            capabilities=DashboardWidgetCapabilities(
                min_size=DashboardSemanticSize.M,
                preferred_size=DashboardSemanticSize.M,
                max_size=DashboardSemanticSize.L,
                supports_vertical_expand=True,
                flow=DashboardFlowHint.VERTICAL,
                preferred_aspect=DashboardAspectHint.COMPACT,
                content_density=DashboardContentDensity.MEDIUM,
            ),
        ),
        DashboardWidgetRegistryEntry(
            widget_type=DashboardWidgetType.DATA_QUALITY,
            description="Material data-quality limitations only.",
            capabilities=DashboardWidgetCapabilities(
                min_size=DashboardSemanticSize.S,
                preferred_size=DashboardSemanticSize.M,
                max_size=DashboardSemanticSize.L,
                supports_vertical_expand=True,
                flow=DashboardFlowHint.VERTICAL,
                preferred_aspect=DashboardAspectHint.COMPACT,
                content_density=DashboardContentDensity.MEDIUM,
            ),
        ),
    ]
