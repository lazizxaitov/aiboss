"""Presentation views over the latest persisted automatic business analysis."""

from __future__ import annotations

from dataclasses import dataclass
from logging import getLogger
from typing import Any

from app.core.auto_business_analytics import (
    AutoAnalyticsInsight,
    AutoAnalyticsRecommendation,
    AutoAnalyticsRun,
    AutoBusinessAnalyticsService,
)
from app.core.data_layer.contracts import CoreDataStore

logger = getLogger(__name__)
logger.setLevel("INFO")


@dataclass(slots=True)
class AIInsightPresentationService:
    store: CoreDataStore

    def latest(self) -> AutoAnalyticsRun | None:
        return AutoBusinessAnalyticsService(self.store).latest()

    def dashboard(self) -> dict[str, Any]:
        service = AutoBusinessAnalyticsService(self.store)
        run = service.latest_successful()
        latest_run = service.latest()
        analytics_status = service.status()
        if run is None or run.structured_result is None:
            status = "empty"
            message = "ИИ-анализ ещё не выполнен"
            if analytics_status.status == "analyzing" or latest_run and latest_run.status == "running":
                status = "running"
                message = "ИИ анализирует бизнес..."
            elif analytics_status.status in {"error", "retry_wait"} or latest_run and latest_run.status == "failed":
                status = "error"
                message = analytics_status.last_error or latest_run.error or "Не удалось завершить ИИ-анализ."
            payload = {
                "analysis_id": None,
                "generated_at": None,
                "summary": None,
                "status": status,
                "message": message,
                "findings": [],
                "opportunities": [],
                "recommendations": [],
                "provider_id": analytics_status.provider_id,
                "model_id": analytics_status.model_id,
                "organization_ids": [],
                "period": {},
                "latest_run_status": latest_run.status if latest_run else None,
                "items": [],
            }
            logger.info("BUSINESS_ANALYSIS_LATEST_READ analysis_id=None status=%s", status)
            logger.info("AI_INSIGHTS_DASHBOARD_RESPONSE status=%s findings_count=0", status)
            return payload
        result = run.structured_result
        findings = [item for item in result.findings if isinstance(item, dict)]
        findings.extend(self._insight(item) for item in result.insights)
        if result.dashboard_plan:
            findings.extend(self._insight(item) for item in result.dashboard_plan.insights)
        items = [self._finding(item) for item in findings]
        items.extend(self._recommendation(item) for item in result.recommendations)
        if result.dashboard_plan:
            items.extend(self._recommendation(item) for item in result.dashboard_plan.recommendations)
        recommendations = [self._recommendation(item) for item in result.recommendations]
        if result.dashboard_plan:
            recommendations.extend(
                self._recommendation(item) for item in result.dashboard_plan.recommendations
            )
        opportunities = (
            [self._insight(item) for item in result.dashboard_plan.opportunities]
            if result.dashboard_plan
            else []
        )
        opportunities.extend(
            {"type": "opportunity", "title": item}
            for item in result.top_opportunities
            if isinstance(item, str) and item.strip()
        )
        payload = {
            "analysis_id": run.analysis_id,
            "generated_at": result.generated_at or run.generated_at,
            "summary": result.dashboard_plan.executive_summary if result.dashboard_plan else result.summary,
            "status": "ready",
            "findings": findings,
            "opportunities": opportunities,
            "recommendations": recommendations,
            "provider_id": run.provider_id or result.provider_id,
            "model_id": run.model_id or result.model_id,
            "organization_ids": run.organization_scope or result.organization_ids,
            "period": result.analysis_period or {"preset": run.period},
            "items": self._dedupe(items),
        }
        logger.info(
            "BUSINESS_ANALYSIS_LATEST_READ analysis_id=%s status=ready",
            run.analysis_id,
        )
        logger.info(
            "AI_INSIGHTS_DASHBOARD_RESPONSE status=ready findings_count=%s",
            len(payload["findings"]),
        )
        return payload

    def page(self, page: str) -> dict[str, Any]:
        payload = self.dashboard()
        payload["page"] = page
        return payload

    def entity(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        payload = self.dashboard()
        payload["items"] = [
            item for item in payload["items"]
            if item.get("affected_entity") == entity_id or item.get("affected_entity") == entity_type
        ]
        payload["entity_type"] = entity_type
        payload["entity_id"] = entity_id
        return payload

    @staticmethod
    def _insight(item: AutoAnalyticsInsight) -> dict[str, Any]:
        return item.model_dump(mode="json")

    @staticmethod
    def _finding(item: dict[str, Any]) -> dict[str, Any]:
        """Expose raw structured findings without inventing narrative fields."""

        return {**item, "type": item.get("type", "finding")}

    @staticmethod
    def _recommendation(item: AutoAnalyticsRecommendation) -> dict[str, Any]:
        payload = item.model_dump(mode="json")
        payload["type"] = "recommendation"
        return payload

    @staticmethod
    def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        priority = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        unique: dict[tuple[Any, ...], dict[str, Any]] = {}
        for item in items:
            key = (item.get("affected_entity"), item.get("affected_metric"), item.get("title"), item.get("type"))
            unique[key] = item
        return sorted(unique.values(), key=lambda item: priority.get(str(item.get("priority", "medium")), 2))[:12]
