"""Persistent, role-routed automatic business analytics runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field

from app.api.routes.ai_chat import _extract_assistant_message
from app.core.ai_routing import AITaskRouter
from app.core.config import settings
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.entities import AppSetting
from app.core.hermes_tools import HermesBusinessTools
from app.core.hermes_model_registry import hermes_model_registry
from app.core.analytics.engine import BusinessAnalyticsEngine

AUTO_ANALYTICS_INDEX_KEY = "ai_business_analytics:index:v1"
AUTO_ANALYTICS_KEY_PREFIX = "ai_business_analytics:run:v1:"


class AutoAnalyticsInsight(BaseModel):
    type: Literal["positive", "warning", "critical", "info"]
    title: str
    description: str
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    reason: str = ""
    affected_entity: str | None = None
    affected_metric: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    metric: str | None = None
    value: str | int | float | None = None
    change: str | int | float | None = None


class AutoAnalyticsRecommendation(BaseModel):
    title: str
    description: str
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    reason: str = ""
    affected_entity: str | None = None
    affected_metric: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class DashboardWidgetPlan(BaseModel):
    widget_type: str
    title: str
    metric: str | None = None
    period: str | None = None
    value: str | int | float | None = None
    comparison: str | int | float | None = None
    entity: str | None = None
    filters: list[dict[str, Any]] = Field(default_factory=list)
    reason: str
    insight: str
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    size: str | None = None


class DashboardPlan(BaseModel):
    executive_summary: str = ""
    priority: Literal["normal", "attention", "critical"] = "normal"
    widgets: list[DashboardWidgetPlan] = Field(default_factory=list)
    insights: list[AutoAnalyticsInsight] = Field(default_factory=list)
    risks: list[AutoAnalyticsInsight] = Field(default_factory=list)
    opportunities: list[AutoAnalyticsInsight] = Field(default_factory=list)
    recommendations: list[AutoAnalyticsRecommendation] = Field(default_factory=list)
    actions: list[AutoAnalyticsRecommendation] = Field(default_factory=list)


class AutoAnalyticsResult(BaseModel):
    summary: str = ""
    status: Literal["normal", "attention", "critical"] = "normal"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    provider_id: str | None = None
    model_id: str | None = None
    fallback_used: bool = False
    kpis: list[dict[str, Any]] = Field(default_factory=list)
    insights: list[AutoAnalyticsInsight] = Field(default_factory=list)
    recommendations: list[AutoAnalyticsRecommendation] = Field(default_factory=list)
    anomalies: list[str] = Field(default_factory=list)
    top_opportunities: list[str] = Field(default_factory=list)
    risks: list[AutoAnalyticsInsight] = Field(default_factory=list)
    dashboard_plan: DashboardPlan | None = None


class AutoAnalyticsRun(BaseModel):
    analysis_id: str = Field(default_factory=lambda: str(uuid4()))
    organization_scope: list[str] = Field(default_factory=list)
    period: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["running", "completed", "failed"]
    summary: str = ""
    structured_result: AutoAnalyticsResult | None = None
    error: str | None = None


class AutoBusinessAnalyticsService:
    def __init__(self, store: CoreDataStore) -> None:
        self.store = store

    def latest(self) -> AutoAnalyticsRun | None:
        index_setting = self.store.get_app_setting(AUTO_ANALYTICS_INDEX_KEY)
        if index_setting is None:
            return None
        ids = index_setting.setting_value.get("analysis_ids", [])
        for analysis_id in reversed(ids if isinstance(ids, list) else []):
            setting = self.store.get_app_setting(f"{AUTO_ANALYTICS_KEY_PREFIX}{analysis_id}")
            if setting is None:
                continue
            try:
                return AutoAnalyticsRun.model_validate(setting.setting_value)
            except Exception:  # noqa: BLE001
                continue
        return None

    def latest_successful(self) -> AutoAnalyticsRun | None:
        index_setting = self.store.get_app_setting(AUTO_ANALYTICS_INDEX_KEY)
        if index_setting is None:
            return None
        ids = index_setting.setting_value.get("analysis_ids", [])
        for analysis_id in reversed(ids if isinstance(ids, list) else []):
            setting = self.store.get_app_setting(f"{AUTO_ANALYTICS_KEY_PREFIX}{analysis_id}")
            if setting is None:
                continue
            try:
                run = AutoAnalyticsRun.model_validate(setting.setting_value)
            except Exception:  # noqa: BLE001
                continue
            if run.status == "completed" and run.structured_result is not None:
                return run
        return None

    def _save(self, run: AutoAnalyticsRun) -> AutoAnalyticsRun:
        now = datetime.now(UTC)
        self.store.upsert_app_setting(AppSetting(
            setting_key=f"{AUTO_ANALYTICS_KEY_PREFIX}{run.analysis_id}",
            setting_value=run.model_dump(mode="json"),
            metadata={"scope": "global", "kind": "auto_business_analytics", "analysis_id": run.analysis_id},
            created_at=run.generated_at,
            updated_at=now,
        ))
        index_setting = self.store.get_app_setting(AUTO_ANALYTICS_INDEX_KEY)
        ids = index_setting.setting_value.get("analysis_ids", []) if index_setting else []
        ids = [str(item) for item in ids if str(item) != run.analysis_id][-49:] + [run.analysis_id]
        self.store.upsert_app_setting(AppSetting(
            setting_key=AUTO_ANALYTICS_INDEX_KEY,
            setting_value={"analysis_ids": ids},
            metadata={"scope": "global", "kind": "auto_business_analytics_index"},
            created_at=now,
            updated_at=now,
        ))
        return run

    async def run(self) -> AutoAnalyticsRun:
        await hermes_model_registry.get_providers()
        router = AITaskRouter(self.store)
        candidates = router.resolve_candidates("business_analytics")
        runtime = candidates[0] if candidates else {}
        tools = HermesBusinessTools(self.store)
        query = tools._build_query(organization_id=None, period=None)
        analytics = BusinessAnalyticsEngine(self.store)
        summary = tools.get_business_summary()
        sales = tools.get_sales_summary()
        products = tools.get_top_products()
        alerts = tools.get_business_alerts()
        organizations = analytics.build_organizations(query).model_dump(mode="json")
        sales_reps = analytics.build_sales_reps(query).model_dump(mode="json")
        customers = analytics.build_customers(query).model_dump(mode="json")
        visits = analytics.build_visits(query).model_dump(mode="json")
        run = AutoAnalyticsRun(
            organization_scope=[str(item) for item in summary.get("organization_ids", [])],
            period=str(summary.get("period", {}).get("preset") or ""),
            provider_id=runtime.get("provider_id") if runtime else None,
            model_id=runtime.get("model_id") if runtime else None,
            status="running",
        )
        self._save(run)
        if not runtime.get("model_id"):
            run.status = "failed"
            run.error = "Нет доступного агента для роли business_analytics."
            return self._save(run)

        instruction = (
            "Проведи автоматический анализ текущих бизнес-данных AI Business OS. "
            "Сравни текущий и предыдущий период. Найди не только изменения KPI, но и вклад организаций, "
            "продавцов, товаров, категорий и клиентов в абсолютных значениях и процентах, когда это возможно. "
            "Отдельно проанализируй sellers/employees, products, customers, organizations, categories, visits, "
            "returns и аномалии. Не называй корреляцию доказанной причиной: используй формулировку 'вклад' "
            "или 'наиболее заметное изменение', если причинность не подтверждена. "
            "Каждый insight и recommendation должен содержать priority, reason, affected_entity, affected_metric "
            "и evidence с current, previous и change_pct, если они доступны. Не повторяй один факт в разных блоках. "
            "Рекомендации должны быть конкретными и ссылаться на evidence. "
            "Используй только реальные данные. Верни STRICT JSON по схеме summary,status,kpis,insights,"
            "recommendations,anomalies,top_opportunities,risks,dashboard_plan. "
            "dashboard_plan.widgets may use only existing Widget Registry types and must explain reason and insight.\nDATA:\n"
            + json.dumps(
                {
                    "summary": summary,
                    "sales": sales,
                    "products": products,
                    "organizations": organizations,
                    "sales_reps": sales_reps,
                    "customers": customers,
                    "visits": visits,
                    "alerts": alerts,
                },
                ensure_ascii=False,
                default=str,
            )
        )
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    response = await client.post(
                        f"{settings.hermes_base_url.rstrip('/')}/chat/completions",
                        headers={"Authorization": f"Bearer {settings.hermes_api_key}"},
                        json={
                            "provider": candidate["provider_id"],
                            "model": candidate["model_id"],
                            "messages": [{"role": "user", "content": instruction}],
                            "stream": False,
                        },
                    )
                    response.raise_for_status()
                    message = _extract_assistant_message(response.json()) or {}
                    raw = message.get("content") or "{}"
                    text = str(raw).strip().strip("`")
                    result = AutoAnalyticsResult.model_validate(json.loads(text))
                    result.provider_id = str(candidate["provider_id"])
                    result.model_id = str(candidate["model_id"])
                    result.fallback_used = bool(candidate.get("fallback_used"))
                    run.provider_id = str(candidate["provider_id"])
                    run.model_id = str(candidate["model_id"])
                    run.status = "completed"
                    run.summary = result.summary
                    run.structured_result = result
                    break
            except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError) as error:
                last_error = error
        if run.status != "completed":
            run.status = "failed"
            run.error = f"Не удалось завершить автоанализ: {last_error or 'нет доступного provider/model'}"
        return self._save(run)

    async def run_if_due(self, *, after_sync: bool = False) -> AutoAnalyticsRun | None:
        config = AITaskRouter(self.store).get_config()
        triggers = set(config.business_analytics_triggers)
        latest = self.latest()
        if config.business_analytics_auto_enabled and after_sync and "after_sync" in triggers:
            return await self.run()
        if not config.business_analytics_auto_enabled or not latest:
            return None
        now = datetime.now(UTC)
        if "daily" in triggers and now - latest.generated_at >= timedelta(days=1):
            return await self.run()
        if "weekly" in triggers and now - latest.generated_at >= timedelta(days=7):
            return await self.run()
        return None


def apply_dashboard_plan(manifest: Any, run: AutoAnalyticsRun | None) -> Any:
    """Overlay the latest AI plan using only widgets already present in the registry."""

    if run is None or run.status != "completed" or run.structured_result is None or run.structured_result.dashboard_plan is None:
        return manifest
    from app.core.analytics.dashboard_manifest import DashboardWidgetSourceType
    from app.core.analytics.models import DashboardWidgetType

    type_aliases = {
        "area": DashboardWidgetType.TREND,
        "progress": DashboardWidgetType.KPI,
        "gauge": DashboardWidgetType.KPI,
        "comparison": DashboardWidgetType.ORGANIZATION_COMPARISON,
        "ranking": DashboardWidgetType.PRODUCT_RANKING,
        "detailed_list": DashboardWidgetType.TABLE,
    }
    generated = []
    for index, planned in enumerate(run.structured_result.dashboard_plan.widgets):
        try:
            widget_type = type_aliases.get(planned.widget_type)
            if widget_type is None:
                widget_type = DashboardWidgetType(planned.widget_type)
        except ValueError:
            continue
        source = next((widget for widget in manifest.widgets if widget.widget_type == widget_type), None)
        if source is None:
            continue
        generated.append(source.model_copy(update={
            "widget_id": f"ai-auto-{run.analysis_id[:12]}-{index}",
            "source_type": DashboardWidgetSourceType.AI_DYNAMIC,
            "title": planned.title,
            "priority": index,
            "priority_reason": planned.reason,
            "summary": planned.insight,
            "entity_type": planned.entity,
            "metric_keys": [planned.metric] if planned.metric else source.metric_keys,
            "payload": {**source.payload, "ai_context": {"reason": planned.reason, "insight": planned.insight, "comparison": planned.comparison, "priority": planned.priority, "filters": planned.filters}},
        }))
    if generated:
        manifest.widgets = [*generated, *[widget for widget in manifest.widgets if widget.source_type != DashboardWidgetSourceType.AI_DYNAMIC]]
    return manifest
