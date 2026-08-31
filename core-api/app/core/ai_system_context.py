"""Compact, request-scoped system context for AI Business OS models."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core.ai_capabilities import AICapabilityRegistry, ai_capability_registry
from app.core.ai_readonly_sql import AIReadOnlySQLService
from app.core.data_layer.contracts import CoreDataStore


class AISystemContextService:
    """Build only the system map relevant to the current request."""

    def __init__(self, store: CoreDataStore, registry: AICapabilityRegistry = ai_capability_registry) -> None:
        self.store = store
        self.registry = registry

    def build(
        self,
        *,
        role: str,
        provider: str | None = None,
        model: str | None = None,
        organization_id: object | None = None,
        period: str | None = None,
        ui_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC).astimezone(ZoneInfo("Asia/Tashkent"))
        monday = now.date() - timedelta(days=now.weekday())
        next_monday = monday + timedelta(days=7)
        business_context = {
            "organization_id": str(organization_id) if organization_id else None,
            "period": period,
            "timezone": "Asia/Tashkent",
            "local_date": now.date().isoformat(),
            "local_now": now.isoformat(),
            "calendar_week": {
                "definition": "Monday 00:00 through next Monday 00:00, business timezone",
                "start": datetime.combine(monday, time.min, tzinfo=now.tzinfo).isoformat(),
                "end_exclusive": datetime.combine(next_monday, time.min, tzinfo=now.tzinfo).isoformat(),
            },
        }
        context: dict[str, Any] = {
            "ai": {
                "role": role,
                "provider": provider,
                "model": model,
            },
            "role": role,
            "capabilities": self.registry.describe(role),
            "permissions": {
                "database": "read_only",
                "raw_data": False,
                "credentials": False,
                "shell": False,
                "network_tools": False,
            },
            "business_context": business_context,
        }
        if any(capability.name == "business.query" for capability in self.registry.for_role(role)):
            sql_service = AIReadOnlySQLService(self.store)
            schema = sql_service.database_schema()
            context["database"] = {
                "kind": "published_read_only_views",
                "schema": schema,
                "semantic_environment": sql_service.semantic_environment(schema),
            }
        if ui_context:
            context["current_ui"] = ui_context
        return context
