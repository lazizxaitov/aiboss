"""AI widget builder models and persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.core.analytics.engine import BusinessAnalyticsEngine
from app.core.analytics.models import (
    AnalyticsDataStatus,
    AnalyticsDimensionRow,
    AnalyticsPeriodPreset,
    AnalyticsQuery,
    DashboardWidgetType,
)
from app.core.analytics.dashboard_manifest import (
    DashboardAspectHint,
    DashboardContentDensity,
    DashboardDrilldown,
    DashboardFlowHint,
    DashboardLayoutPolicy,
    DashboardManifestWidget,
    DashboardScrollBehavior,
    DashboardSemanticSize,
    DashboardWidgetSourceType,
)
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.entities import AppSetting
from app.core.organization_context import AnalyticsContextState, OrganizationContextService

WIDGET_BUILDER_CONFIGS_KEY = "dashboard:widget_builder:configs:v1"


class WidgetBuilderType(StrEnum):
    """Supported AI widget builder types."""

    KPI = "kpi"
    DETAILED_LIST = "detailed_list"
    LINE_CHART = "line_chart"
    BAR_CHART = "bar_chart"
    DONUT = "donut"
    RANKING = "ranking"
    COMPARISON = "comparison"

    def to_dashboard_type(self) -> DashboardWidgetType:
        mapping = {
            WidgetBuilderType.KPI: DashboardWidgetType.KPI,
            WidgetBuilderType.DETAILED_LIST: DashboardWidgetType.TABLE,
            WidgetBuilderType.LINE_CHART: DashboardWidgetType.LINE_CHART,
            WidgetBuilderType.BAR_CHART: DashboardWidgetType.BAR_CHART,
            WidgetBuilderType.DONUT: DashboardWidgetType.DONUT,
            WidgetBuilderType.RANKING: DashboardWidgetType.RANKING,
            WidgetBuilderType.COMPARISON: DashboardWidgetType.ORGANIZATION_COMPARISON,
        }
        return mapping[self]


class WidgetBuilderFilterOperator(StrEnum):
    """Supported filter operators for widget drafts."""

    EQ = "eq"
    IN = "in"
    CONTAINS = "contains"
    GTE = "gte"
    LTE = "lte"
    BETWEEN = "between"


class WidgetBuilderFilter(BaseModel):
    """One widget filter resolved from user intent."""

    field: str
    operator: WidgetBuilderFilterOperator = WidgetBuilderFilterOperator.EQ
    value: Any
    resolved_field: str | None = None
    resolved_id: str | None = None
    resolved_label: str | None = None


class WidgetBuilderSpec(BaseModel):
    """Available widget-builder template information."""

    widget_type: WidgetBuilderType
    label: str
    description: str
    default_size: DashboardSemanticSize
    fixed_size: DashboardSemanticSize


class WidgetBuilderDraft(BaseModel):
    """Draft state controlled by Hermes and the constructor."""

    widget_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = ""
    widget_type: WidgetBuilderType = WidgetBuilderType.KPI
    metric: str | None = None
    period: str | None = None
    organization_ids: list[UUID] = Field(default_factory=list)
    organization_name: str | None = None
    filters: list[WidgetBuilderFilter] = Field(default_factory=list)
    grouping: str | None = None
    limit: int | None = None
    size: DashboardSemanticSize = DashboardSemanticSize.S
    notes: list[str] = Field(default_factory=list)
    resolved_entities: dict[str, Any] = Field(default_factory=dict)


class WidgetBuilderPreview(BaseModel):
    """Real-data preview returned to the constructor."""

    state: Literal["ready", "partial", "no_data", "needs_selection"] = "ready"
    widget_type: WidgetBuilderType
    title: str
    subtitle: str | None = None
    data_status: AnalyticsDataStatus = AnalyticsDataStatus.NO_DATA
    payload: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class WidgetBuilderConfig(WidgetBuilderDraft):
    """Persisted widget configuration."""

    config_id: str = Field(default_factory=lambda: str(uuid4()))
    source_channel: str = "web"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    preview: WidgetBuilderPreview | None = None


class WidgetBuilderUpdatePatch(BaseModel):
    """Partial widget-config update payload."""

    title: str | None = None
    widget_type: WidgetBuilderType | None = None
    metric: str | None = None
    period: str | None = None
    organization_ids: list[UUID] | None = None
    organization_name: str | None = None
    filters: list[WidgetBuilderFilter] | None = None
    grouping: str | None = None
    limit: int | None = None
    size: DashboardSemanticSize | None = None
    notes: list[str] | None = None


class WidgetBuilderCreateRequest(BaseModel):
    """Create widget request."""

    draft: WidgetBuilderDraft
    source_channel: str = "web"
    organization_id: UUID | None = None
    period: str | None = None


class WidgetBuilderUpdateRequest(BaseModel):
    """Update widget request."""

    widget_id: str | None = None
    match_text: str | None = None
    patch: WidgetBuilderUpdatePatch
    organization_id: UUID | None = None
    period: str | None = None


class WidgetBuilderDeleteRequest(BaseModel):
    """Delete widget request."""

    widget_id: str | None = None
    match_text: str | None = None


class WidgetBuilderMutationResponse(BaseModel):
    """Widget lifecycle mutation result."""

    status: Literal["created", "updated", "deleted", "needs_selection", "not_found"]
    config: WidgetBuilderConfig | None = None
    preview: WidgetBuilderPreview | None = None
    dashboard_widget: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class WidgetBuilderContextResponse(BaseModel):
    """Modal context payload."""

    current_context: dict[str, Any]
    organizations: list[dict[str, Any]] = Field(default_factory=list)
    widget_specs: list[WidgetBuilderSpec] = Field(default_factory=list)
    saved_configs: list[WidgetBuilderConfig] = Field(default_factory=list)


class WidgetBuilderChatRequest(BaseModel):
    """Input for widget-builder AI chat."""

    conversation_id: str | None = None
    user_id: str | None = None
    organization_id: UUID | None = None
    period: str | None = None
    message: str = Field(min_length=1)
    draft: WidgetBuilderDraft | None = None


class WidgetBuilderChatResponse(BaseModel):
    """Structured assistant response for widget builder."""

    conversation_id: str
    assistant_message: str
    widget_draft: WidgetBuilderDraft | None = None
    clarification_required: bool = False
    clarification_options: list[str] = Field(default_factory=list)
    preview: WidgetBuilderPreview | None = None


class WidgetBuilderConfirmRequest(BaseModel):
    """Persisted widget builder confirmation request."""

    draft: WidgetBuilderDraft
    conversation_id: str | None = None
    user_id: str | None = None
    source_channel: str = "web"


class WidgetBuilderConfirmResponse(BaseModel):
    """Confirmation response after saving a widget."""

    config: WidgetBuilderConfig
    preview: WidgetBuilderPreview | None = None
    dashboard_widget: dict[str, Any] | None = None


@dataclass(slots=True)
class WidgetBuilderService:
    """Persist widget builder drafts and translate them into dashboard widgets."""

    store: CoreDataStore

    def supported_specs(self) -> list[WidgetBuilderSpec]:
        return [
            WidgetBuilderSpec(
                widget_type=WidgetBuilderType.KPI,
                label="KPI / Простая цифра",
                description="Single numeric card with one primary metric.",
                default_size=DashboardSemanticSize.S,
                fixed_size=DashboardSemanticSize.S,
            ),
            WidgetBuilderSpec(
                widget_type=WidgetBuilderType.DETAILED_LIST,
                label="Detailed list / Подробный список",
                description="Large scrollable list with real rows and details.",
                default_size=DashboardSemanticSize.XL,
                fixed_size=DashboardSemanticSize.XL,
            ),
            WidgetBuilderSpec(
                widget_type=WidgetBuilderType.LINE_CHART,
                label="Line chart",
                description="Trend chart for time series.",
                default_size=DashboardSemanticSize.XL,
                fixed_size=DashboardSemanticSize.XL,
            ),
            WidgetBuilderSpec(
                widget_type=WidgetBuilderType.BAR_CHART,
                label="Bar chart",
                description="Grouped comparison chart.",
                default_size=DashboardSemanticSize.L,
                fixed_size=DashboardSemanticSize.L,
            ),
            WidgetBuilderSpec(
                widget_type=WidgetBuilderType.DONUT,
                label="Donut",
                description="Circular composition chart.",
                default_size=DashboardSemanticSize.M,
                fixed_size=DashboardSemanticSize.M,
            ),
            WidgetBuilderSpec(
                widget_type=WidgetBuilderType.RANKING,
                label="Ranking",
                description="Sorted list of top entities.",
                default_size=DashboardSemanticSize.L,
                fixed_size=DashboardSemanticSize.L,
            ),
            WidgetBuilderSpec(
                widget_type=WidgetBuilderType.COMPARISON,
                label="Comparison",
                description="Comparison widget across entities or periods.",
                default_size=DashboardSemanticSize.XL,
                fixed_size=DashboardSemanticSize.XL,
            ),
        ]

    def get_context_payload(
        self,
        *,
        organization_id: UUID | None = None,
        period: str | None = None,
    ) -> WidgetBuilderContextResponse:
        context_service = OrganizationContextService(self.store)
        context = context_service.get_context()
        query = self._build_query(context, organization_id=organization_id, period=period)
        return WidgetBuilderContextResponse(
            current_context={
                "organization_ids": [str(item) for item in query.organization_ids],
                "organization_id": str(query.organization_id) if query.organization_id else None,
                "period": {
                    "preset": query.period.value,
                    "date_from": query.date_from.isoformat() if query.date_from else None,
                    "date_to": query.date_to.isoformat() if query.date_to else None,
                },
            },
            organizations=self._organizations_payload(),
            widget_specs=self.supported_specs(),
            saved_configs=self.list_configs(
                organization_ids=query.organization_ids,
            ),
        )

    def list_configs(
        self,
        *,
        organization_ids: list[UUID] | None = None,
    ) -> list[WidgetBuilderConfig]:
        setting = self.store.get_app_setting(WIDGET_BUILDER_CONFIGS_KEY)
        if setting is None:
            return []
        value = setting.setting_value or {}
        raw_configs = value.get("configs", []) if isinstance(value, dict) else []
        configs: list[WidgetBuilderConfig] = []
        for raw in raw_configs if isinstance(raw_configs, list) else []:
            try:
                config = WidgetBuilderConfig.model_validate(raw)
            except Exception:  # noqa: BLE001 - fall back to safe defaults
                continue
            if organization_ids:
                if config.organization_ids and not set(config.organization_ids).intersection(organization_ids):
                    continue
            configs.append(config)
        configs.sort(key=lambda item: (item.created_at, item.config_id))
        return configs

    def save_config(self, config: WidgetBuilderConfig) -> WidgetBuilderConfig:
        configs = self.list_configs()
        normalized = config.model_copy(update={"updated_at": datetime.now(UTC)})
        replaced = False
        for index, item in enumerate(configs):
            if item.config_id == normalized.config_id:
                configs[index] = normalized
                replaced = True
                break
        if not replaced:
            configs.append(normalized)
        self.store.upsert_app_setting(
            AppSetting(
                setting_key=WIDGET_BUILDER_CONFIGS_KEY,
                setting_value={"configs": [item.model_dump(mode="json") for item in configs]},
                metadata={"scope": "global", "kind": "widget_builder_configs"},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        )
        return normalized

    def get_config(self, widget_id: str) -> WidgetBuilderConfig | None:
        for config in self.list_configs():
            if config.widget_id == widget_id:
                return config
        return None

    def resolve_config_matches(self, match_text: str | None) -> list[WidgetBuilderConfig]:
        if match_text is None or not match_text.strip():
            return []
        normalized = match_text.strip().lower()
        matches: list[WidgetBuilderConfig] = []
        for config in self.list_configs():
            fields = [
                config.widget_id,
                config.config_id,
                config.title,
                config.metric or "",
                config.grouping or "",
                config.organization_name or "",
            ]
            haystack = " ".join(field.lower() for field in fields if field)
            if normalized in haystack:
                matches.append(config)
        return matches

    def validate_config(self, config: WidgetBuilderConfig) -> list[str]:
        errors: list[str] = []
        registry = self._registry_entry(config.widget_type.to_dashboard_type())
        if config.size != self._default_size(config.widget_type):
            errors.append("FIXED_SIZE_MISMATCH")
        if registry.widget_type != config.widget_type.to_dashboard_type():
            errors.append("UNKNOWN_WIDGET_TYPE")
        if config.limit is not None and config.limit < 1:
            errors.append("LIMIT_TOO_SMALL")
        if config.filters:
            for filter_item in config.filters:
                if filter_item.field not in {
                    "organization",
                    "organization_id",
                    "seller",
                    "sales_rep",
                    "employee",
                    "sales_rep_id",
                    "customer",
                    "customer_id",
                    "product",
                    "product_id",
                    "category",
                    "product_category",
                    "category_id",
                    "date",
                    "period",
                }:
                    errors.append(f"UNSUPPORTED_FILTER_FIELD:{filter_item.field}")
        return errors

    def create_dashboard_widget(
        self,
        draft: WidgetBuilderDraft,
        *,
        source_channel: str = "web",
        organization_id: UUID | None = None,
        period: str | None = None,
    ) -> WidgetBuilderMutationResponse:
        config, preview = self.save_confirmed_widget(
            draft,
            source_channel=source_channel,
            organization_id=organization_id,
            period=period,
        )
        errors = self.validate_config(config)
        if errors:
            raise ValueError(f"Invalid widget config: {', '.join(errors)}")
        return WidgetBuilderMutationResponse(
            status="created",
            config=config,
            preview=preview,
            dashboard_widget=self.build_dashboard_widget(config).model_dump(mode="json"),
        )

    def update_dashboard_widget(
        self,
        *,
        widget_id: str | None = None,
        match_text: str | None = None,
        patch: WidgetBuilderUpdatePatch,
        organization_id: UUID | None = None,
        period: str | None = None,
    ) -> WidgetBuilderMutationResponse:
        target = self.get_config(widget_id) if widget_id else None
        matches = [target] if target is not None else self.resolve_config_matches(match_text)
        matches = [item for item in matches if item is not None]
        if not matches:
            return WidgetBuilderMutationResponse(status="not_found")
        if len(matches) > 1:
            return WidgetBuilderMutationResponse(
                status="needs_selection",
                candidates=[item.model_dump(mode="json") for item in matches[:5]],
            )
        current = matches[0]
        updated = current.model_copy(deep=True)
        for field_name, field_value in patch.model_dump(exclude_none=True).items():
            if field_name == "widget_type":
                updated.widget_type = field_value
                updated.size = self._default_size(field_value)
                continue
            if field_name == "size":
                continue
            setattr(updated, field_name, field_value)
        if updated.organization_ids:
            updated.organization_ids = self._resolve_organization_ids(updated.organization_ids)
        if not updated.title:
            updated.title = self._default_title(updated)
        if not updated.metric:
            updated.metric = self._default_metric(updated)
        updated.preview = self.build_preview(
            updated,
            organization_id=organization_id,
            period=period,
        )
        errors = self.validate_config(updated)
        if errors:
            raise ValueError(f"Invalid widget config: {', '.join(errors)}")
        saved = self.save_config(updated)
        return WidgetBuilderMutationResponse(
            status="updated",
            config=saved,
            preview=saved.preview,
            dashboard_widget=self.build_dashboard_widget(saved).model_dump(mode="json"),
        )

    def delete_dashboard_widget(
        self,
        *,
        widget_id: str | None = None,
        match_text: str | None = None,
    ) -> WidgetBuilderMutationResponse:
        target = self.get_config(widget_id) if widget_id else None
        matches = [target] if target is not None else self.resolve_config_matches(match_text)
        matches = [item for item in matches if item is not None]
        if not matches:
            return WidgetBuilderMutationResponse(status="not_found")
        if len(matches) > 1:
            return WidgetBuilderMutationResponse(
                status="needs_selection",
                candidates=[item.model_dump(mode="json") for item in matches[:5]],
            )
        current = matches[0]
        configs = [item for item in self.list_configs() if item.widget_id != current.widget_id]
        self.store.upsert_app_setting(
            AppSetting(
                setting_key=WIDGET_BUILDER_CONFIGS_KEY,
                setting_value={"configs": [item.model_dump(mode="json") for item in configs]},
                metadata={"scope": "global", "kind": "widget_builder_configs"},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        )
        return WidgetBuilderMutationResponse(status="deleted", config=current)

    def build_preview(
        self,
        draft: WidgetBuilderDraft,
        *,
        organization_id: UUID | None = None,
        period: str | None = None,
    ) -> WidgetBuilderPreview:
        query = self._build_query(
            OrganizationContextService(self.store).get_context(),
            organization_id=organization_id or (draft.organization_ids[0] if draft.organization_ids else None),
            organization_ids=draft.organization_ids or None,
            period=period or draft.period,
        )
        engine = BusinessAnalyticsEngine(self.store)
        widget_type = draft.widget_type
        metric = (draft.metric or "").strip().lower()
        limit = max(1, min(draft.limit or 10, 100))

        if widget_type == WidgetBuilderType.KPI:
            return self._build_kpi_preview(engine, query, draft)
        if widget_type == WidgetBuilderType.DETAILED_LIST:
            return self._build_list_preview(engine, query, draft, limit)
        if widget_type == WidgetBuilderType.LINE_CHART:
            return self._build_line_chart_preview(engine, query, draft)
        if widget_type == WidgetBuilderType.BAR_CHART:
            return self._build_bar_chart_preview(engine, query, draft)
        if widget_type == WidgetBuilderType.DONUT:
            return self._build_donut_preview(engine, query, draft)
        if widget_type == WidgetBuilderType.RANKING:
            return self._build_ranking_preview(engine, query, draft, limit)
        if widget_type == WidgetBuilderType.COMPARISON:
            return self._build_comparison_preview(engine, query, draft)
        return WidgetBuilderPreview(
            state="no_data",
            widget_type=draft.widget_type,
            title=draft.title or "Widget",
            data_status=AnalyticsDataStatus.NO_DATA,
            notes=["Unsupported widget type."],
        )

    def resolve_draft(
        self,
        draft: WidgetBuilderDraft,
        *,
        organization_id: UUID | None = None,
        period: str | None = None,
    ) -> tuple[WidgetBuilderDraft, WidgetBuilderPreview, bool, list[str]]:
        resolved = draft.model_copy(deep=True)
        context = OrganizationContextService(self.store).get_context()
        query = self._build_query(
            context,
            organization_id=organization_id,
            organization_ids=resolved.organization_ids or None,
            period=period or resolved.period,
        )
        resolved.organization_ids = list(query.organization_ids)
        resolved.organization_name = self._organization_label(resolved.organization_ids)
        if not resolved.period:
            resolved.period = query.period.value
        resolved.size = self._default_size(resolved.widget_type)
        ambiguity_options: list[str] = []
        clarification_required = False
        for filter_item in resolved.filters:
            matches = self._resolve_filter_entities(filter_item)
            if len(matches) > 1:
                clarification_required = True
                ambiguity_options.extend(
                    [f"{item['label']} ({item['id']})" for item in matches[:5]],
                )
                continue
            if len(matches) == 1:
                match = matches[0]
                filter_item.resolved_field = match["resolved_field"]
                filter_item.resolved_id = match["id"]
                filter_item.resolved_label = match["label"]
                filter_item.value = match["id"]
                filter_item.field = match["resolved_field"]
                resolved.resolved_entities[match["resolved_field"]] = match
        if not resolved.title:
            resolved.title = self._default_title(resolved)
        if not resolved.metric:
            resolved.metric = self._default_metric(resolved)
        preview = self.build_preview(resolved, organization_id=organization_id, period=period)
        if preview.state == "needs_selection":
            clarification_required = True
        return resolved, preview, clarification_required, list(dict.fromkeys(ambiguity_options))

    def build_manifest_widget(
        self,
        config: WidgetBuilderConfig,
    ) -> DashboardManifestWidget:
        widget_type = config.widget_type.to_dashboard_type()
        registry_entry = self._registry_entry(widget_type)
        preview = config.preview
        payload = {
            "widget_builder": {
                "config": config.model_dump(mode="json"),
                "preview": None if preview is None else preview.model_dump(mode="json"),
            }
        }
        return DashboardManifestWidget(
            widget_id=config.widget_id,
            widget_type=widget_type,
            source_type=DashboardWidgetSourceType.USER_PINNED,
            title=config.title,
            subtitle=None if preview is None else preview.subtitle,
            metric_keys=[config.metric] if config.metric else [],
            signal_ids=[],
            entity_type=self._entity_type(config),
            entity_id=self._entity_id(config),
            organization_ids=list(config.organization_ids),
            semantic_size=config.size,
            priority=0,
            priority_reason="User-created widget from AI Widget Builder",
            min_size=config.size,
            preferred_size=config.size,
            max_size=config.size,
            supports_horizontal_expand=registry_entry.capabilities.supports_horizontal_expand,
            supports_vertical_expand=registry_entry.capabilities.supports_vertical_expand,
            supports_internal_scroll=registry_entry.capabilities.supports_internal_scroll,
            flow=registry_entry.capabilities.flow,
            preferred_aspect=registry_entry.capabilities.preferred_aspect,
            content_density=registry_entry.capabilities.content_density,
            scroll_behavior=registry_entry.capabilities.scroll_behavior,
            removable_by_ai=False,
            movable_by_ai=True,
            resizable_by_ai=False,
            locked_position=False,
            locked_size=True,
            pinned=True,
            hidden=False,
            drilldown=DashboardDrilldown(
                target="dashboard",
                entity_type=self._entity_type(config),
                entity_id=self._entity_id(config),
                organization_ids=list(config.organization_ids),
                filters={
                    "builder_type": config.widget_type.value,
                    "metric": config.metric or "",
                },
            ),
            summary=None if preview is None else preview.subtitle,
            data_status=AnalyticsDataStatus.AVAILABLE
            if preview is None
            else preview.data_status,
            payload=payload,
        )

    def build_dashboard_widget(self, config: WidgetBuilderConfig) -> DashboardManifestWidget:
        return self.build_manifest_widget(config)

    def save_confirmed_widget(
        self,
        draft: WidgetBuilderDraft,
        *,
        source_channel: str = "web",
        organization_id: UUID | None = None,
        period: str | None = None,
    ) -> tuple[WidgetBuilderConfig, WidgetBuilderPreview]:
        resolved, preview, _, _ = self.resolve_draft(
            draft,
            organization_id=organization_id,
            period=period,
        )
        config = WidgetBuilderConfig(
            **resolved.model_dump(),
            source_channel=source_channel,
            preview=preview,
        )
        errors = self.validate_config(config)
        if errors:
            raise ValueError(f"Invalid widget config: {', '.join(errors)}")
        saved = self.save_config(config)
        return saved, preview

    def append_custom_widgets(
        self,
        widgets: list[DashboardManifestWidget],
        *,
        organization_ids: list[UUID] | None = None,
    ) -> list[DashboardManifestWidget]:
        configs = self.list_configs(organization_ids=organization_ids)
        if not configs:
            return widgets
        # A user-created AI widget is a normal dashboard widget after it is
        # saved. Rebuild its preview from the persisted query definition so a
        # later Core/Canonical update changes the displayed value as well.
        custom_widgets: list[DashboardManifestWidget] = []
        for config in configs:
            preview = self.build_preview(
                config,
                organization_id=config.organization_ids[0] if config.organization_ids else None,
                period=config.period,
            )
            custom_widgets.append(
                self.build_manifest_widget(config.model_copy(update={"preview": preview})),
            )
        widget_ids = {widget.widget_id for widget in custom_widgets}
        base_widgets = [widget for widget in widgets if widget.widget_id not in widget_ids]
        return [*base_widgets, *custom_widgets]

    def _build_kpi_preview(
        self,
        engine: BusinessAnalyticsEngine,
        query: AnalyticsQuery,
        draft: WidgetBuilderDraft,
    ) -> WidgetBuilderPreview:
        summary = engine.build_summary(query)
        metric_name = (draft.metric or "revenue").strip().lower()
        metric = self._extract_metric(summary.business, metric_name)
        if metric is None:
            return WidgetBuilderPreview(
                state="no_data",
                widget_type=WidgetBuilderType.KPI,
                title=draft.title or "KPI",
                data_status=AnalyticsDataStatus.NO_DATA,
                notes=["No matching metric found for KPI preview."],
            )
        return WidgetBuilderPreview(
            state="ready" if metric.data_status == AnalyticsDataStatus.AVAILABLE else "partial",
            widget_type=WidgetBuilderType.KPI,
            title=draft.title or self._default_title(draft),
            subtitle=metric.note,
            data_status=metric.data_status,
            payload={
                "metric": metric.model_dump(mode="json"),
                "organization_ids": [str(item) for item in query.organization_ids],
                "period": self._period_payload(query),
            },
        )

    def _build_list_preview(
        self,
        engine: BusinessAnalyticsEngine,
        query: AnalyticsQuery,
        draft: WidgetBuilderDraft,
        limit: int,
    ) -> WidgetBuilderPreview:
        report_name = self._report_for_list(draft.metric, draft.grouping)
        payload = self._report_payload(engine, query, report_name, limit=limit, widget_type=draft.widget_type)
        rows = payload.get("rows", [])
        state = "no_data" if not rows else "ready"
        data_status = self._payload_status(payload)
        return WidgetBuilderPreview(
            state=state,
            widget_type=WidgetBuilderType.DETAILED_LIST,
            title=draft.title or self._default_title(draft),
            subtitle=payload.get("subtitle"),
            data_status=data_status,
            payload=payload,
            notes=[] if rows else ["No rows available for the selected scope."],
        )

    def _build_line_chart_preview(
        self,
        engine: BusinessAnalyticsEngine,
        query: AnalyticsQuery,
        draft: WidgetBuilderDraft,
    ) -> WidgetBuilderPreview:
        report = engine.build_sales(query)
        series = [
            {
                "date": row.key,
                "label": row.label,
                "value": self._dimension_metric_value(row, draft.metric),
                "status": row.data_status,
            }
            for row in report.by_date
        ]
        state = "no_data" if not series else "ready"
        return WidgetBuilderPreview(
            state=state,
            widget_type=WidgetBuilderType.LINE_CHART,
            title=draft.title or self._default_title(draft),
            subtitle=report.period.label,
            data_status=report.data_quality.overall_status,
            payload={"series": series, "period": self._period_payload(query)},
            notes=[] if series else ["No time-series data available."],
        )

    def _build_bar_chart_preview(
        self,
        engine: BusinessAnalyticsEngine,
        query: AnalyticsQuery,
        draft: WidgetBuilderDraft,
    ) -> WidgetBuilderPreview:
        report_name = self._report_for_list(draft.metric, draft.grouping, prefer_comparison=True)
        payload = self._report_payload(engine, query, report_name, limit=draft.limit or 10)
        rows = payload.get("rows", [])
        state = "no_data" if not rows else "ready"
        return WidgetBuilderPreview(
            state=state,
            widget_type=WidgetBuilderType.BAR_CHART,
            title=draft.title or self._default_title(draft),
            subtitle=payload.get("subtitle"),
            data_status=self._payload_status(payload),
            payload=payload,
            notes=[] if rows else ["No bar-chart data available."],
        )

    def _build_donut_preview(
        self,
        engine: BusinessAnalyticsEngine,
        query: AnalyticsQuery,
        draft: WidgetBuilderDraft,
    ) -> WidgetBuilderPreview:
        payload = self._report_payload(engine, query, "organizations", limit=draft.limit or 5)
        rows = payload.get("rows", [])
        total = sum(self._row_numeric_value(row) for row in rows)
        slices = [
            {
                "label": row.get("label"),
                "value": self._row_numeric_value(row),
                "share": None if not total else round(self._row_numeric_value(row) / total, 4),
            }
            for row in rows
        ]
        state = "no_data" if not slices else "ready"
        return WidgetBuilderPreview(
            state=state,
            widget_type=WidgetBuilderType.DONUT,
            title=draft.title or self._default_title(draft),
            subtitle=payload.get("subtitle"),
            data_status=self._payload_status(payload),
            payload={"slices": slices, "period": self._period_payload(query)},
            notes=[] if slices else ["No composition data available."],
        )

    def _build_ranking_preview(
        self,
        engine: BusinessAnalyticsEngine,
        query: AnalyticsQuery,
        draft: WidgetBuilderDraft,
        limit: int,
    ) -> WidgetBuilderPreview:
        report_name = self._report_for_list(draft.metric, draft.grouping, ranking=True)
        payload = self._report_payload(engine, query, report_name, limit=limit)
        rows = payload.get("rows", [])
        state = "no_data" if not rows else "ready"
        return WidgetBuilderPreview(
            state=state,
            widget_type=WidgetBuilderType.RANKING,
            title=draft.title or self._default_title(draft),
            subtitle=payload.get("subtitle"),
            data_status=self._payload_status(payload),
            payload=payload,
            notes=[] if rows else ["No ranking data available."],
        )

    def _build_comparison_preview(
        self,
        engine: BusinessAnalyticsEngine,
        query: AnalyticsQuery,
        draft: WidgetBuilderDraft,
    ) -> WidgetBuilderPreview:
        summary = engine.build_summary(query)
        rows = [
            {
                "label": "Current revenue",
                "value": self._metric_payload(summary.business.revenue),
            },
            {
                "label": "Orders",
                "value": self._metric_payload(summary.business.orders),
            },
            {
                "label": "Average order",
                "value": self._metric_payload(summary.business.average_order),
            },
            {
                "label": "Sold units",
                "value": self._metric_payload(summary.business.sold_units),
            },
            {
                "label": "Returns",
                "value": self._metric_payload(summary.business.returns),
            },
        ]
        return WidgetBuilderPreview(
            state="ready" if rows else "no_data",
            widget_type=WidgetBuilderType.COMPARISON,
            title=draft.title or self._default_title(draft),
            subtitle=summary.period.label,
            data_status=summary.data_quality.overall_status,
            payload={"rows": rows, "period": self._period_payload(query)},
            notes=[] if rows else ["No comparison data available."],
        )

    def _report_payload(
        self,
        engine: BusinessAnalyticsEngine,
        query: AnalyticsQuery,
        report_name: str,
        *,
        limit: int,
        widget_type: WidgetBuilderType | None = None,
    ) -> dict[str, Any]:
        if report_name == "sales":
            report = engine.build_sales(query)
            source_rows = report.by_date if widget_type == WidgetBuilderType.DETAILED_LIST else report.by_sales_rep
            rows = [self._serialize_dimension_row(row) for row in source_rows[:limit]]
            return {"rows": rows, "subtitle": report.period.label, "data_status": report.data_quality.overall_status}
        if report_name == "products":
            report = engine.build_products(query)
            rows = [self._serialize_product_item(item) for item in report.top[:limit]]
            return {"rows": rows, "subtitle": report.period.label, "data_status": report.data_quality.overall_status}
        if report_name == "customers":
            report = engine.build_customers(query)
            rows = [self._serialize_customer_item(item) for item in report.top[:limit]]
            return {"rows": rows, "subtitle": report.period.label, "data_status": report.data_quality.overall_status}
        if report_name == "organizations":
            report = engine.build_organizations(query)
            rows = [self._serialize_organization_item(item) for item in report.items[:limit]]
            return {"rows": rows, "subtitle": report.period.label, "data_status": report.data_quality.overall_status}
        if report_name == "sales_reps":
            report = engine.build_sales_reps(query)
            rows = [self._serialize_sales_rep_item(item) for item in report.items[:limit]]
            return {"rows": rows, "subtitle": report.period.label, "data_status": report.data_quality.overall_status}
        if report_name == "visits":
            report = engine.build_visits(query)
            rows = [self._serialize_dimension_row(row) for row in report.by_sales_rep[:limit]]
            return {"rows": rows, "subtitle": report.period.label, "data_status": report.data_quality.overall_status}
        if report_name == "finance":
            report = engine.build_finance(query)
            rows = [
                {"label": item.label, "value": self._metric_payload(item.value), "metric_key": item.metric_key}
                for item in report.by_type[:limit]
            ]
            return {"rows": rows, "subtitle": report.period.label, "data_status": report.data_quality.overall_status}
        summary = engine.build_summary(query)
        rows = [
            {"label": item.label, "value": self._metric_payload(item.current_value)}
            for item in summary.metric_registry[:limit]
        ]
        return {"rows": rows, "subtitle": summary.period.label, "data_status": summary.data_quality.overall_status}

    def _resolve_filter_entities(self, filter_item: WidgetBuilderFilter) -> list[dict[str, str]]:
        raw_value = filter_item.value
        query = "" if raw_value is None else str(raw_value).strip().lower()
        if not query:
            return []
        if filter_item.field in {"seller", "sales_rep", "employee", "sales_rep_id"}:
            return self._match_entities(
                self.store.list_canonical_sales_reps(),
                query=query,
                resolved_field="sales_rep_id",
                label_getter=lambda item: getattr(item, "sales_rep_name", None)
                or item.sales_manager_name
                or item.sales_manager_code
                or str(item.id),
            )
        if filter_item.field in {"customer", "customer_id"}:
            return self._match_entities(
                self.store.list_canonical_customers(),
                query=query,
                resolved_field="customer_id",
                label_getter=lambda item: item.name or item.code or str(item.id),
            )
        if filter_item.field in {"product", "product_id"}:
            return self._match_entities(
                self.store.list_canonical_products(),
                query=query,
                resolved_field="product_id",
                label_getter=lambda item: item.name or item.code or str(item.id),
            )
        if filter_item.field in {"category", "product_category", "category_id"}:
            return self._match_entities(
                self.store.list_canonical_product_categories(),
                query=query,
                resolved_field="category_id",
                label_getter=lambda item: item.name or item.code or str(item.id),
            )
        if filter_item.field in {"organization", "organization_id"}:
            return self._match_entities(
                self.store.list_canonical_organizations(),
                query=query,
                resolved_field="organization_id",
                label_getter=lambda item: item.name or item.project_code or str(item.organization_id),
            )
        return []

    def _match_entities(
        self,
        items,
        *,
        query: str,
        resolved_field: str,
        label_getter,
    ) -> list[dict[str, str]]:
        matched: list[dict[str, str]] = []
        for item in items:
            item_label = label_getter(item)
            searchable = item_label.lower()
            if query == searchable or query in searchable:
                matched.append(
                    {
                        "resolved_field": resolved_field,
                        "id": str(getattr(item, "id", getattr(item, "organization_id", ""))),
                        "label": item_label,
                    },
                )
        return matched

    def _resolve_organization_ids(self, organization_ids: list[UUID]) -> list[UUID]:
        normalized = []
        for organization_id in organization_ids:
            if organization_id not in normalized:
                normalized.append(organization_id)
        return normalized

    def _extract_metric(self, summary, metric_name: str):
        mapping = {
            "revenue": summary.revenue,
            "orders": summary.orders,
            "average_order": summary.average_order,
            "sold_units": summary.sold_units,
            "returns": summary.returns,
            "customers": summary.customers,
            "products": summary.unique_products,
            "visits": summary.visits,
            "payments_received": summary.payments_received,
            "current_stock": summary.current_stock,
            "realised_sales": summary.realised_sales,
            "unique_customers": summary.unique_customers,
            "unique_products": summary.unique_products,
        }
        return mapping.get(metric_name)

    def _default_title(self, draft: WidgetBuilderDraft) -> str:
        metric = draft.metric or "metric"
        return f"{metric.replace('_', ' ').title()}"

    def _default_metric(self, draft: WidgetBuilderDraft) -> str:
        if draft.widget_type == WidgetBuilderType.KPI:
            return "revenue"
        if draft.widget_type == WidgetBuilderType.DETAILED_LIST:
            return "orders"
        if draft.widget_type == WidgetBuilderType.LINE_CHART:
            return "revenue"
        if draft.widget_type == WidgetBuilderType.BAR_CHART:
            return "orders"
        if draft.widget_type == WidgetBuilderType.DONUT:
            return "revenue"
        if draft.widget_type == WidgetBuilderType.RANKING:
            return "revenue"
        return "revenue"

    def _default_size(self, widget_type: WidgetBuilderType) -> DashboardSemanticSize:
        return {
            WidgetBuilderType.KPI: DashboardSemanticSize.S,
            WidgetBuilderType.DETAILED_LIST: DashboardSemanticSize.XL,
            WidgetBuilderType.LINE_CHART: DashboardSemanticSize.XL,
            WidgetBuilderType.BAR_CHART: DashboardSemanticSize.L,
            WidgetBuilderType.DONUT: DashboardSemanticSize.M,
            WidgetBuilderType.RANKING: DashboardSemanticSize.L,
            WidgetBuilderType.COMPARISON: DashboardSemanticSize.XL,
        }[widget_type]

    def _period_payload(self, query: AnalyticsQuery) -> dict[str, Any]:
        return {
            "preset": query.period.value,
            "date_from": query.date_from.isoformat() if query.date_from else None,
            "date_to": query.date_to.isoformat() if query.date_to else None,
        }

    def _build_query(
        self,
        context: AnalyticsContextState,
        *,
        organization_id: UUID | None = None,
        organization_ids: list[UUID] | None = None,
        period: str | None = None,
    ) -> AnalyticsQuery:
        requested_organization_ids = list(dict.fromkeys(
            [organization_id] if organization_id is not None else (organization_ids or []),
        ))
        if requested_organization_ids:
            accessible_organization_ids = set(
                OrganizationContextService(self.store).resolve_accessible_organization_ids(),
            )
            if not set(requested_organization_ids).issubset(accessible_organization_ids):
                raise ValueError("Выбранная организация недоступна для текущего владельца.")
        resolved_organization_ids = (
            [item for item in organization_ids if item is not None]
            if organization_ids
            else OrganizationContextService(self.store).resolve_organization_ids(organization_id=organization_id) or []
        )
        resolved_organization_id = organization_id
        if resolved_organization_id is None and len(resolved_organization_ids) == 1:
            resolved_organization_id = resolved_organization_ids[0]
        preset, date_from, date_to = self._resolve_period(period, context)
        return AnalyticsQuery(
            organization_id=resolved_organization_id,
            organization_ids=resolved_organization_ids,
            date_from=date_from,
            date_to=date_to,
            period=preset,
        )

    def _resolve_period(
        self,
        period: str | None,
        context: AnalyticsContextState,
    ) -> tuple[AnalyticsPeriodPreset, Any | None, Any | None]:
        if period is None or not str(period).strip():
            return (
                context.period_context.preset,
                context.period_context.date_from,
                context.period_context.date_to,
            )
        normalized = str(period).strip().lower()
        aliases = {
            "last_7_days": AnalyticsPeriodPreset.LAST_7_DAYS,
            "last_30_days": AnalyticsPeriodPreset.LAST_30_DAYS,
            "last_12_months": AnalyticsPeriodPreset.ALL,
            "all": AnalyticsPeriodPreset.ALL,
            "today": AnalyticsPeriodPreset.TODAY,
            "yesterday": AnalyticsPeriodPreset.YESTERDAY,
            "current_month": AnalyticsPeriodPreset.CURRENT_MONTH,
            "previous_month": AnalyticsPeriodPreset.PREVIOUS_MONTH,
            "custom": AnalyticsPeriodPreset.CUSTOM,
            "7d": AnalyticsPeriodPreset.LAST_7_DAYS,
            "30d": AnalyticsPeriodPreset.LAST_30_DAYS,
            "12m": AnalyticsPeriodPreset.ALL,
        }
        preset = aliases.get(normalized)
        if preset is None:
            try:
                preset = AnalyticsPeriodPreset(normalized)
            except ValueError:
                preset = context.period_context.preset
        if preset != AnalyticsPeriodPreset.CUSTOM:
            return preset, None, None
        return preset, context.period_context.date_from, context.period_context.date_to

    def _organization_label(self, organization_ids: list[UUID]) -> str | None:
        if not organization_ids:
            return None
        rows = self.store.list_canonical_organizations()
        names = [row.name for row in rows if row.organization_id in organization_ids]
        return ", ".join(names) if names else None

    def _organizations_payload(self) -> list[dict[str, Any]]:
        return [
            {
                "organization_id": str(row.organization_id),
                "name": row.name,
                "project_code": row.project_code,
                "filial_code": row.filial_code,
                "is_active": row.is_active,
            }
            for row in self.store.list_canonical_organizations()
        ]

    def _registry_entry(self, widget_type: DashboardWidgetType):
        from app.core.analytics.dashboard_manifest import default_widget_registry

        registry = {entry.widget_type: entry for entry in default_widget_registry()}
        return registry[widget_type]

    def _entity_type(self, config: WidgetBuilderConfig) -> str | None:
        if not config.filters:
            return None
        return config.filters[0].resolved_field or config.filters[0].field

    def _entity_id(self, config: WidgetBuilderConfig) -> str | None:
        if not config.filters:
            return None
        return config.filters[0].resolved_id

    def _serialize_dimension_row(self, row: AnalyticsDimensionRow) -> dict[str, Any]:
        return {
            "dimension": row.dimension,
            "key": row.key,
            "label": row.label,
            "metrics": {name: metric.model_dump(mode="json") for name, metric in row.metrics.items()},
            "data_status": row.data_status,
            "context": row.context,
        }

    def _serialize_product_item(self, item) -> dict[str, Any]:
        return item.model_dump(mode="json")

    def _serialize_customer_item(self, item) -> dict[str, Any]:
        return item.model_dump(mode="json")

    def _serialize_organization_item(self, item) -> dict[str, Any]:
        return item.model_dump(mode="json")

    def _serialize_sales_rep_item(self, item) -> dict[str, Any]:
        return item.model_dump(mode="json")

    def _metric_payload(self, metric) -> dict[str, Any]:
        return metric.model_dump(mode="json")

    def _dimension_metric_value(self, row: AnalyticsDimensionRow, metric_name: str | None) -> dict[str, Any] | None:
        if metric_name and metric_name in row.metrics:
            return row.metrics[metric_name].model_dump(mode="json")
        if row.metrics:
            metric = next(iter(row.metrics.values()))
            return metric.model_dump(mode="json")
        return None

    def _row_numeric_value(self, row: dict[str, Any]) -> float:
        value = row.get("value")
        if isinstance(value, dict):
            raw = value.get("value")
        else:
            raw = value
        try:
            return float(raw or 0)
        except (TypeError, ValueError):
            return 0.0

    def _payload_status(self, payload: dict[str, Any]) -> AnalyticsDataStatus:
        status = payload.get("data_status")
        if isinstance(status, AnalyticsDataStatus):
            return status
        try:
            return AnalyticsDataStatus(status)
        except Exception:  # noqa: BLE001
            return AnalyticsDataStatus.NO_DATA

    def _report_for_list(
        self,
        metric: str | None,
        grouping: str | None,
        *,
        prefer_comparison: bool = False,
        ranking: bool = False,
    ) -> str:
        metric_text = (metric or "").lower()
        grouping_text = (grouping or "").lower()
        if grouping_text in {"customer", "customers"}:
            return "customers"
        if grouping_text in {"product", "products"}:
            return "products"
        if grouping_text in {"organization", "organizations"}:
            return "organizations"
        if grouping_text in {"sales_rep", "sales_rep_name", "seller", "employee"}:
            return "sales_reps"
        if metric_text in {"customer", "customers"}:
            return "customers"
        if metric_text in {"product", "products"}:
            return "products"
        if metric_text in {"organization", "organizations"}:
            return "organizations"
        if metric_text in {"visits", "visit"}:
            return "visits"
        if metric_text in {"finance", "cash", "cash_flow", "payments_received"}:
            return "finance"
        if prefer_comparison:
            return "organizations"
        if ranking:
            return "sales_reps"
        return "sales"
