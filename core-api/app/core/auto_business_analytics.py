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


def _normalize_ai_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize provider JSON to the persisted analytics contract only."""

    status = payload.get("status")
    if status not in {"normal", "attention", "critical"}:
        payload["status"] = "critical" if any(
            isinstance(item, dict) and item.get("type") == "critical"
            for item in (payload.get("risks") or [])
        ) else "attention" if payload.get("risks") or payload.get("warnings") else "normal"

    def normalize_items(key: str, *, default_type: str | None = None) -> None:
        items = payload.get(key)
        if not isinstance(items, list):
            payload[key] = []
            return
        normalized: list[dict[str, Any]] = []
        for item in items:
            item = {"title": item, "description": item} if isinstance(item, str) else dict(item) if isinstance(item, dict) else {}
            item.setdefault("title", "Вывод AI")
            item.setdefault("description", item["title"])
            if default_type is not None and item.get("type") not in {"positive", "warning", "critical", "info"}:
                item["type"] = default_type
            evidence = item.get("evidence")
            item["evidence"] = evidence if isinstance(evidence, list) else ([{"detail": evidence}] if evidence else [])
            normalized.append(item)
        payload[key] = normalized

    normalize_items("insights", default_type="info")
    normalize_items("risks", default_type="warning")
    normalize_items("opportunities", default_type="positive")
    normalize_items("findings", default_type=None)

    recommendations = payload.get("recommendations")
    if not isinstance(recommendations, list):
        payload["recommendations"] = []
    else:
        normalized_recommendations: list[dict[str, Any]] = []
        for item in recommendations:
            item = {"title": item, "description": item} if isinstance(item, str) else dict(item) if isinstance(item, dict) else {}
            item.setdefault("title", "Рекомендация AI")
            item.setdefault("description", item["title"])
            evidence = item.get("evidence")
            item["evidence"] = evidence if isinstance(evidence, list) else ([{"detail": evidence}] if evidence else [])
            normalized_recommendations.append(item)
        payload["recommendations"] = normalized_recommendations
    return payload


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
    warnings: list[Any] = Field(default_factory=list)
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
    analysis_level: Literal["widget", "daily", "deep"] = "deep"
    data_version: str | None = None


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

    def latest(self, level: Literal["widget", "daily", "deep"] | None = None) -> AutoAnalyticsRun | None:
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
                if level is None or run.analysis_level == level:
                    return run
            except Exception:  # noqa: BLE001
                continue
        return None

    def latest_successful(self, level: Literal["widget", "daily", "deep"] | None = None) -> AutoAnalyticsRun | None:
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
            if run.status == "completed" and run.structured_result is not None and (level is None or run.analysis_level == level):
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

    async def run(self, mode: Literal["widget", "daily", "deep"] = "deep") -> AutoAnalyticsRun:
        if not _AUTO_ANALYTICS_RUN_LOCK.acquire(blocking=False):
            return self.latest() or AutoAnalyticsRun(status="failed", error="Автоанализ уже выполняется.")
        try:
            return await self._run_locked(mode)
        except Exception as error:  # noqa: BLE001 - sync must remain healthy when AI preparation fails
            self._save_status(AutoAnalyticsStatus(
                status="error",
                last_error=f"Не удалось подготовить автоанализ: {error}",
                next_retry_at=datetime.now(UTC) + timedelta(minutes=5),
            ))
            raise
        finally:
            _AUTO_ANALYTICS_RUN_LOCK.release()

    async def _run_locked(self, mode: Literal["widget", "daily", "deep"]) -> AutoAnalyticsRun:
        await hermes_model_registry.get_providers(refresh=True)
        router = AITaskRouter(self.store)
        candidates = router.resolve_candidates("business_analytics")
        runtime = candidates[0] if candidates else {}
        logger.info(
            "BUSINESS_ANALYSIS_ROLE_RESOLVED role=business_analytics candidates=%s provider=%s model=%s fallback_used=%s",
            len(candidates),
            runtime.get("provider_id"),
            runtime.get("model_id"),
            runtime.get("fallback_used", False),
        )
        started_at = datetime.now(UTC)
        self._save_status(AutoAnalyticsStatus(
            status="analyzing",
            last_started_at=started_at,
            provider_id=str(runtime.get("provider_id")) if runtime.get("provider_id") else None,
            model_id=str(runtime.get("model_id")) if runtime.get("model_id") else None,
        ))
        tools = HermesBusinessTools(self.store)
        context = OrganizationContextService(self.store).get_context()
        data_version = self._data_version()
        run = AutoAnalyticsRun(
            organization_scope=[str(item) for item in context.organization_context.organization_ids],
            period=context.period_context.preset.value,
            provider_id=runtime.get("provider_id") if runtime else None,
            model_id=runtime.get("model_id") if runtime else None,
            status="running",
            analysis_level=mode,
            data_version=data_version,
        )
        self._save(run)
        logger.info(
            "AI_ANALYTICS_RUN_START run_id=%s role=business_analytics provider=%s model=%s organization_scope=%s period=%s",
            run.analysis_id,
            run.provider_id,
            run.model_id,
            run.organization_scope,
            run.period,
        )
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
            f"Проведи {'лёгкий widget-анализ' if mode == 'widget' else 'короткий ежедневный обзор' if mode == 'daily' else 'глубокий автоматический анализ'} AI Business OS через разрешённые read-only SQL research views. "
            + ("Ограничься несколькими ключевыми агрегатами и не углубляйся без необходимости. " if mode != "deep" else "")
            + ""
            "Сам выбери первый query из универсального AI-safe schema/catalog, затем сам выбери дополнительные queries, "
            "если они нужны для проверки причин, продавцов, товаров, клиентов, организаций, возвратов, визитов, "
            "склада или финансов. Не используй заранее заданную последовательность и не повторяй ненужные запросы. "
            "Используй текущую организацию и период контекста в SQL WHERE. SQL research выполняет backend, не показывай SQL пользователю. "
            "После получения достаточного evidence верни финальный ответ строго JSON "
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
            logger.info(
                "AI_ANALYTICS_MODEL_REQUEST run_id=%s role=business_analytics provider=%s model=%s",
                run.analysis_id,
                run.provider_id,
                run.model_id,
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
                    "Investigate facts through approved read-only SQL research views; do not rely on precomputed narrative. "
                    "Use status only normal, attention, or critical. Findings, risks, opportunities and recommendations "
                    "must be arrays of objects with title, description, type where required, and evidence as an array."
                    + previous_metadata
                ),
                provider_id=None,
                model_id=None,
                build_baseline=False,
                tool_call_budget={"widget": 4, "daily": 6, "deep": 12}[mode],
            )
            successful_queries = int(agent_result.runtime.get("successful_business_queries") or 0)
            logger.info(
                "AI_ANALYTICS_CAPABILITY_EXECUTED run_id=%s capability_calls=%s successful_business_queries=%s",
                run.analysis_id,
                agent_result.tool_calls,
                successful_queries,
            )
            if successful_queries < 1:
                raise ValueError("Business Analytics не получила подтверждённые данные из business.query.")
            logger.info(
                "AI_ANALYTICS_EVIDENCE_READY run_id=%s successful_business_queries=%s",
                run.analysis_id,
                successful_queries,
            )
            raw = agent_result.final_text.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.splitlines()[1:-1]).strip()
            payload = json.loads(raw)
            if isinstance(payload, dict):
                payload = _normalize_ai_result_payload(payload)
            result = AutoAnalyticsResult.model_validate(payload)
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
            logger.info(
                "AI_ANALYTICS_RUN_FAILED run_id=%s role=business_analytics provider=%s model=%s "
                "organization_scope=%s period=%s capability_calls=%s successful_business_queries=%s error=%s",
                run.analysis_id,
                run.provider_id,
                run.model_id,
                run.organization_scope,
                run.period,
                len(run.structured_result.queries_executed) if run.structured_result else 0,
                0,
                str(run.error)[:300],
            )
        else:
            self._save_status(AutoAnalyticsStatus(
                status="completed",
                last_started_at=started_at,
                last_completed_at=run.generated_at,
                provider_id=run.provider_id,
                model_id=run.model_id,
            ))
        saved = self._save(run)
        successful_queries = (
            len(saved.structured_result.queries_executed)
            if saved.structured_result is not None
            else 0
        )
        logger.info(
            "AI_ANALYTICS_PERSISTED run_id=%s status=%s insight_count=%s successful_business_queries=%s",
            saved.analysis_id,
            saved.status,
            len(saved.structured_result.findings) if saved.structured_result else 0,
            successful_queries,
        )
        logger.info(
            "AI_ANALYTICS_RUN_DONE run_id=%s status=%s provider=%s model=%s capability_calls=%s successful_business_queries=%s insight_count=%s error=%s",
            saved.analysis_id,
            saved.status,
            saved.provider_id,
            saved.model_id,
            successful_queries,
            successful_queries,
            len(saved.structured_result.findings) if saved.structured_result else 0,
            saved.error,
        )
        return saved

    def _data_version(self) -> str | None:
        """Return a stable version of configured SmartUp data for AI invalidation."""

        organizations = getattr(self.store, "list_smartup_organizations", lambda **_: [])(
            integration_id=None,
            is_active=True,
        )
        values = [
            f"{item.id}:{item.last_sync_at.isoformat() if item.last_sync_at else ''}"
            for item in organizations
        ]
        return "|".join(sorted(values)) or None

    async def run_widget_if_needed(self) -> AutoAnalyticsRun | None:
        existing = self.latest_successful("widget")
        version = self._data_version()
        if existing is not None and existing.data_version == version:
            return existing
        if not list(self.store.list_canonical_organizations()):
            return None
        return await self.run("widget")

    async def run_startup_if_needed(self) -> AutoAnalyticsRun | None:
        """Run one non-blocking startup refresh when Core data is already usable.

        SmartUp remains responsible for importing data and triggering refreshes
        after sync. This one-shot check covers restarts where data already exists
        or where the sync service was disabled, without adding another scheduler.
        """

        config = AITaskRouter(self.store).get_config()
        if not config.business_analytics_auto_enabled:
            logger.info("AI_ANALYTICS_RUN_SKIPPED reason=disabled")
            return None
        if not list(self.store.list_canonical_organizations()):
            logger.info("AI_ANALYTICS_RUN_SKIPPED reason=no_canonical_data")
            return None
        return await self.run_widget_if_needed()


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
        logger.info(
            "BUSINESS_ANALYSIS_TRIGGERED after_sync=%s auto_enabled=%s triggers=%s latest_analysis_id=%s",
            after_sync,
            config.business_analytics_auto_enabled,
            sorted(triggers),
            latest.analysis_id if latest else None,
        )
        if after_sync and config.business_analytics_auto_enabled and "after_sync" in triggers:
            return await self.run_widget_if_needed()
        if not config.business_analytics_auto_enabled:
            logger.info(
                "BUSINESS_ANALYSIS_TRIGGER_SKIPPED reason=%s",
                "disabled",
            )
            return None
        now = datetime.now(UTC)
        daily = self.latest_successful("daily")
        if "daily" in triggers and (daily is None or now - daily.generated_at >= timedelta(days=1)):
            return await self.run("daily")
        deep = self.latest_successful("deep")
        if "weekly" in triggers and (deep is None or now - deep.generated_at >= timedelta(days=7)):
            return await self.run("deep")
        if latest is None:
            logger.info("BUSINESS_ANALYSIS_TRIGGER_SKIPPED reason=no_schedule_or_previous_analysis")
        if latest is not None and latest.status == "failed":
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
