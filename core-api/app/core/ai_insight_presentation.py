"""Presentation views over the latest persisted automatic business analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.auto_business_analytics import AutoAnalyticsInsight, AutoAnalyticsRecommendation, AutoAnalyticsRun, AutoBusinessAnalyticsService
from app.core.data_layer.contracts import CoreDataStore


@dataclass(slots=True)
class AIInsightPresentationService:
    store: CoreDataStore

    def latest(self) -> AutoAnalyticsRun | None:
        return AutoBusinessAnalyticsService(self.store).latest()

    def dashboard(self) -> dict[str, Any]:
        service = AutoBusinessAnalyticsService(self.store)
        run = service.latest_successful()
        latest_run = service.latest()
        if run is None or run.structured_result is None:
            return {
                "analysis_id": None,
                "generated_at": None,
                "summary": None,
                "status": "AI_UNAVAILABLE",
                "message": "ИИ-аналитика временно недоступна",
                "latest_run_status": latest_run.status if latest_run else None,
                "items": [],
            }
        result = run.structured_result
        items = [self._insight(item) for item in result.insights]
        if result.dashboard_plan:
            items.extend(self._insight(item) for item in result.dashboard_plan.insights)
            items.extend(self._recommendation(item) for item in result.dashboard_plan.recommendations)
        return {
            "analysis_id": run.analysis_id,
            "generated_at": run.generated_at,
            "summary": result.dashboard_plan.executive_summary if result.dashboard_plan else result.summary,
            "status": result.dashboard_plan.priority if result.dashboard_plan else result.status,
            "items": self._dedupe(items),
        }

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
