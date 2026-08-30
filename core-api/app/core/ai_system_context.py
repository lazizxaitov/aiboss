"""Compact, request-scoped system context for AI Business OS models."""

from __future__ import annotations

from typing import Any

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
        organization_id: object | None = None,
        period: str | None = None,
        ui_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "role": role,
            "capabilities": self.registry.describe(role),
            "permissions": {
                "database": "read_only",
                "raw_data": False,
                "credentials": False,
                "shell": False,
                "network_tools": False,
            },
            "business_context": {
                "organization_id": str(organization_id) if organization_id else None,
                "period": period,
            },
        }
        if role in {"business_analytics", "ai_chat", "system_action", "communications"}:
            context["database"] = {
                "kind": "published_read_only_views",
                "schema": AIReadOnlySQLService(self.store).database_schema(),
            }
        if ui_context:
            context["current_ui"] = ui_context
        return context
