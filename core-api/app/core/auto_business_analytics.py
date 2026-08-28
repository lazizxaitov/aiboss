"""Persistent, role-routed automatic business analytics runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from logging import getLogger
from threading import Lock
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.ai_business_agent import AIBusinessAgentService
from app.core.ai_conversation import AIConversationChannel, AIConversationMessage, AIConversationState
from app.core.ai_routing import AITaskRouter
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.entities import AppSetting
from app.core.hermes_tools import HermesBusinessTools
from app.core.hermes_model_registry import hermes_model_registry
from app.core.analytics.widget_builder import WidgetBuilderService
from app.core.organization_context import OrganizationContextService

AUTO_ANALYTICS_INDEX_KEY = "ai_business_analytics:index:v1"
AUTO_ANALYTICS_KEY_PREFIX = "ai_business_analytics:run:v1:"
AUTO_ANALYTICS_STATUS_KEY = "ai_business_analytics:status:v1"
_AUTO_ANALYTICS_RUN_LOCK = Lock()
logger = getLogger(__name__)


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
    findings: list[dict[str, Any]] = Field(default_factory=list)
    checked_datasets: list[str] = Field(default_factory=list)
    queries_executed: list[dict[str, Any]] = Field(default_factory=list)
    organization_ids: list[str] = Field(default_factory=list)
    analysis_period: dict[str, Any] = Field(default_factory=dict)
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


class AutoAnalyticsStatus(BaseModel):
    status: Literal["idle", "analyzing", "completed", "retry_wait", "error", "disabled"] = "idle"
    last_started_at: datetime | None = None
    last_completed_at: datetime | None = None
    last_error: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    next_retry_at: datetime | None = None


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

    def status(self) -> AutoAnalyticsStatus:
        setting = self.store.get_app_setting(AUTO_ANALYTICS_STATUS_KEY)
        if setting is not None:
            try:
                return AutoAnalyticsStatus.model_validate(setting.setting_value)
            except Exception:  # noqa: BLE001
                pass
        config = AITaskRouter(self.store).get_config()
        if not config.business_analytics_auto_enabled:
            return AutoAnalyticsStatus(status="disabled")
        latest = self.latest_successful()
        if latest is not None:
            return AutoAnalyticsStatus(
                status="completed",
                last_completed_at=latest.generated_at,
                provider_id=latest.provider_id,
                model_id=latest.model_id,
            )
        return AutoAnalyticsStatus(status="idle")

    def _save_status(self, status: AutoAnalyticsStatus) -> AutoAnalyticsStatus:
        now = datetime.now(UTC)
        self.store.upsert_app_setting(AppSetting(
            setting_key=AUTO_ANALYTICS_STATUS_KEY,
            setting_value=status.model_dump(mode="json"),
            metadata={"scope": "global", "kind": "auto_business_analytics_status"},
            created_at=now,
            updated_at=now,
        ))
        return status

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
        structured = run.structured_result
        findings_count = (
            len(structured.findings) + len(structured.insights) + len(structured.recommendations)
            if structured is not None
            else 0
        )
        logger.info(
            "BUSINESS_ANALYSIS_SAVE analysis_id=%s findings_count=%s status=%s",
            run.analysis_id,
            findings_count,
            run.status,
        )
        return run

    async def run(self) -> AutoAnalyticsRun:
        if not _AUTO_ANALYTICS_RUN_LOCK.acquire(blocking=False):
            return self.latest() or AutoAnalyticsRun(status="failed", error="Автоанализ уже выполняется.")
        try:
            return await self._run_locked()
        except Exception as error:  # noqa: BLE001 - sync must remain healthy when AI preparation fails
            self._save_status(AutoAnalyticsStatus(
                status="error",
                last_error=f"Не удалось подготовить автоанализ: {error}",
                next_retry_at=datetime.now(UTC) + timedelta(minutes=5),
            ))
            raise
        finally:
            _AUTO_ANALYTICS_RUN_LOCK.release()

    async def _run_locked(self) -> AutoAnalyticsRun:
        await hermes_model_registry.get_providers(refresh=True)
        router = AITaskRouter(self.store)
        candidates = router.resolve_candidates("business_analytics")
        runtime = candidates[0] if candidates else {}
        started_at = datetime.now(UTC)
        self._save_status(AutoAnalyticsStatus(
            status="analyzing",
            last_started_at=started_at,
            provider_id=str(runtime.get("provider_id")) if runtime.get("provider_id") else None,
            model_id=str(runtime.get("model_id")) if runtime.get("model_id") else None,
        ))
        tools = HermesBusinessTools(self.store)
        context = OrganizationContextService(self.store).get_context()
        run = AutoAnalyticsRun(
            organization_scope=[str(item) for item in context.organization_context.organization_ids],
            period=context.period_context.preset.value,
            provider_id=runtime.get("provider_id") if runtime else None,
            model_id=runtime.get("model_id") if runtime else None,
            status="running",
        )
        self._save(run)
        logger.info(
            "BUSINESS_ANALYSIS_START analysis_id=%s provider=%s model=%s organization=%s period=%s trigger=scheduled_or_sync",
            run.analysis_id,
            run.provider_id,
            run.model_id,
            run.organization_scope,
            run.period,
        )
        if not runtime.get("model_id"):
            run.status = "failed"
            run.error = "Нет доступного агента для роли business_analytics."
            self._save_status(AutoAnalyticsStatus(status="retry_wait", last_started_at=started_at, last_error=run.error, next_retry_at=datetime.now(UTC) + timedelta(minutes=5)))
            return self._save(run)
        instruction = (
            "Проведи самостоятельный автоматический анализ AI Business OS через доступные read-only business tools. "
            "Начни с compact query по sales и сравнения периодов, затем сам выбери дополнительные queries, "
            "если они нужны для проверки причин, продавцов, товаров, клиентов, организаций, возвратов, визитов, "
            "склада или финансов. Не используй один заранее заданный сценарий и не повторяй ненужные запросы. "
            "Используй текущую организацию и период контекста, а при необходимости указывай их в query. "
            "Никаких RAW/SQL и выдуманных чисел. После получения достаточного evidence верни финальный ответ строго JSON "
            "по схеме summary,status,kpis,insights,recommendations,anomalies,top_opportunities,risks,dashboard_plan. "
            "Каждый важный вывод обязан содержать evidence, priority, reason, affected_entity и affected_metric. "
            "Не выдавай корреляцию за доказанную причину. dashboard_plan.widgets использует только существующие Widget Registry types."
        )
        last_error: Exception | None = None
        try:
            previous = self.latest_successful()
            previous_metadata = (
                f" Previous analysis metadata: generated_at={previous.generated_at.isoformat()}, "
                f"provider={previous.provider_id}, model={previous.model_id}."
                if previous is not None else ""
            )
            conversation = AIConversationState(
                user_id="auto-business-analytics",
                organization_id=(context.organization_context.organization_ids[0]
                                 if len(context.organization_context.organization_ids) == 1 else None),
                period=context.period_context.preset.value,
                messages=[AIConversationMessage(
                    role="user", content=instruction, source_channel=AIConversationChannel.WEB,
                )],
            )
            agent_result = await AIBusinessAgentService(self.store).run(
                conversation=conversation,
                user_text=instruction,
                source_channel="system",
                task_type="business_analytics",
                router=router,
                tools_service=tools,
                widget_builder=WidgetBuilderService(self.store),
                memory_prompt="",
                system_prompt=(
                    "You are the business analytics agent for AI Business OS. "
                    "Investigate facts through approved read-only tools; do not rely on precomputed narrative."
                    + previous_metadata
                ),
                provider_id=None,
                model_id=None,
                build_baseline=False,
            )
            raw = agent_result.final_text.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.splitlines()[1:-1]).strip()
            result = AutoAnalyticsResult.model_validate(json.loads(raw))
            result.provider_id = str(agent_result.runtime.get("provider_id"))
            result.model_id = str(agent_result.runtime.get("model_id"))
            result.fallback_used = bool(agent_result.runtime.get("fallback_used"))
            result.organization_ids = run.organization_scope
            result.analysis_period = {"preset": run.period}
            result.queries_executed = _queries_from_agent_messages(agent_result.messages)
            result.checked_datasets = list(dict.fromkeys(
                str(query.get("arguments", {}).get("dataset"))
                for query in result.queries_executed
                if query.get("tool") == "query_business_data"
                and query.get("arguments", {}).get("dataset")
            ))
            run.provider_id = result.provider_id
            run.model_id = result.model_id
            run.status = "completed"
            run.summary = result.summary
            run.structured_result = result
            logger.info(
                "BUSINESS_ANALYSIS_FINAL analysis_id=%s findings=%s provider=%s model=%s rounds=%s",
                run.analysis_id,
                len(result.insights) + len(result.recommendations),
                run.provider_id,
                run.model_id,
                agent_result.rounds,
            )
        except Exception as error:  # noqa: BLE001 - failed runs must remain observable and persisted
            last_error = error
            logger.info("BUSINESS_ANALYSIS_ERROR analysis_id=%s error=%s", run.analysis_id, str(error)[:300])
        if run.status != "completed":
            run.status = "failed"
            run.error = f"Не удалось завершить автоанализ: {last_error or 'нет доступного provider/model'}"
            self._save_status(AutoAnalyticsStatus(
                status="retry_wait" if candidates else "error",
                last_started_at=started_at,
                last_error=run.error,
                provider_id=run.provider_id,
                model_id=run.model_id,
                next_retry_at=datetime.now(UTC) + timedelta(minutes=5),
            ))
        else:
            self._save_status(AutoAnalyticsStatus(
                status="completed",
                last_started_at=started_at,
                last_completed_at=run.generated_at,
                provider_id=run.provider_id,
                model_id=run.model_id,
            ))
        return self._save(run)


def _queries_from_agent_messages(messages: list[dict[str, object]]) -> list[dict[str, Any]]:
    """Persist only compact query metadata, never complete tool payloads."""

    queries: list[dict[str, Any]] = []
    for message in messages:
        calls = message.get("tool_calls") if isinstance(message, dict) else None
        if not isinstance(calls, list):
            continue
        for call in calls:
            if not isinstance(call, dict):
                continue
            function = call.get("function")
            if not isinstance(function, dict):
                continue
            name = function.get("name")
            if not isinstance(name, str):
                continue
            arguments = function.get("arguments")
            try:
                parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
            except json.JSONDecodeError:
                parsed = {}
            queries.append({"tool": name, "arguments": parsed if isinstance(parsed, dict) else {}})
    return queries

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
        if latest.status == "failed":
            status = self.status()
            if status.status == "retry_wait" and status.next_retry_at and now >= status.next_retry_at:
                return await self.run()
        return None


def apply_dashboard_plan(manifest: Any, run: AutoAnalyticsRun | None) -> Any:
    """Overlay only the latest persisted AI analysis on the dashboard manifest."""

    from app.core.analytics.dashboard_manifest import DashboardWidgetSourceType
    from app.core.analytics.models import AnalyticsDataStatus, DashboardWidgetType

    # The manifest composer also has a deterministic insight workspace for legacy
    # dashboard pages. Remove those AI-shaped cards here so ordinary KPI facts are
    # never presented as findings generated by Business Analytics AI.
    manifest.widgets = [
        widget
        for widget in manifest.widgets
        if widget.source_type != DashboardWidgetSourceType.AI_DYNAMIC
    ]
    executive = next(
        (widget for widget in manifest.widgets if widget.widget_id == "executive-brief"),
        None,
    )
    if run is None or run.status != "completed" or run.structured_result is None:
        if executive is not None:
            executive.payload = {
                "headline": "ИИ-анализ ещё не выполнен",
                "business_status": "После успешного анализа здесь появятся выводы и рекомендации.",
                "key_numbers": [],
                "top_insights": [],
                "risks": [],
                "opportunities": [],
                "data_warnings": [],
            }
            executive.summary = "ИИ-анализ ещё не выполнен"
            executive.subtitle = "Ожидание результата анализа"
            executive.data_status = AnalyticsDataStatus.ANALYSIS_PENDING
        return manifest

    result = run.structured_result
    dashboard_plan = result.dashboard_plan
    summary = dashboard_plan.executive_summary if dashboard_plan else result.summary
    insight_cards = [
        _saved_analysis_card(item, "finding")
        for item in result.insights
    ]
    insight_cards.extend(
        _saved_analysis_card(item, "finding")
        for item in result.findings
        if isinstance(item, dict)
    )
    recommendation_cards = [
        _saved_analysis_card(item, "recommendation")
        for item in result.recommendations
    ]
    if dashboard_plan:
        insight_cards.extend(_saved_analysis_card(item, "finding") for item in dashboard_plan.insights)
        insight_cards.extend(_saved_analysis_card(item, "risk") for item in dashboard_plan.risks)
        insight_cards.extend(_saved_analysis_card(item, "opportunity") for item in dashboard_plan.opportunities)
        recommendation_cards.extend(_saved_analysis_card(item, "recommendation") for item in dashboard_plan.recommendations)
    if executive is not None:
        executive.payload = {
            "headline": summary or "ИИ-анализ завершён",
            "business_status": summary or "Выводы сформированы на основе проверенных данных.",
            "key_numbers": [],
            "top_insights": insight_cards[:6],
            "risks": [item for item in insight_cards if item.get("type") == "risk"][:4],
            "opportunities": [item for item in insight_cards if item.get("type") == "opportunity"][:4],
            "data_warnings": [],
            "recommendations": recommendation_cards[:6],
            "analysis_id": run.analysis_id,
            "generated_at": result.generated_at.isoformat(),
        }
        executive.summary = summary or "ИИ-анализ завершён"
        executive.subtitle = f"Проверено ИИ · {result.generated_at.strftime('%d.%m.%Y %H:%M')}"
        executive.data_status = AnalyticsDataStatus.AVAILABLE

    if dashboard_plan is None:
        return manifest

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


def _saved_analysis_card(item: Any, card_type: str) -> dict[str, Any]:
    """Adapt persisted AI analysis records to the existing dashboard renderer."""

    if isinstance(item, BaseModel):
        payload = item.model_dump(mode="json")
    elif isinstance(item, dict):
        payload = dict(item)
    else:
        payload = {"title": str(item)}
    payload["type"] = card_type
    payload.setdefault("title", payload.get("name") or "Вывод ИИ")
    payload.setdefault("summary", payload.get("description") or payload.get("reason") or "")
    payload.setdefault("severity", payload.get("priority", "medium"))
    payload.setdefault("recommendation", payload.get("description") if card_type == "recommendation" else None)
    return payload
