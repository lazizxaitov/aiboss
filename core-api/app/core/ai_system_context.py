"""Compact, request-scoped system context for AI Business OS models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.ai_capabilities import AICapabilityRegistry, ai_capability_registry
from app.core.ai_readonly_sql import AIReadOnlySQLService
from app.core.data_layer.contracts import CoreDataStore
from app.core.organization_context import (
    BUSINESS_TIMEZONE,
    AnalyticsContextState,
    OrganizationContextService,
    business_week_bounds,
)


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
        now = datetime.now(UTC).astimezone(ZoneInfo(BUSINESS_TIMEZONE))
        week_start, week_end = business_week_bounds(now)
        context_service = OrganizationContextService(self.store)
        if callable(getattr(self.store, "get_app_setting", None)):
            selected_context = context_service.get_context()
            selected_scope = context_service.resolve_organization_ids(
                organization_id=organization_id if organization_id else None,
            )
        else:
            selected_context = AnalyticsContextState()
            selected_scope = None
        selected_period = period or selected_context.period_context.preset.value
        selected_window: dict[str, str] = {}
        if selected_period in {"current_week", "this_week"}:
            selected_window = {
                "start": week_start.isoformat(),
                "end": week_end.isoformat(),
            }
        elif selected_context.period_context.date_from and selected_context.period_context.date_to:
            selected_window = {
                "start_date": selected_context.period_context.date_from.isoformat(),
                "end_date_inclusive": selected_context.period_context.date_to.isoformat(),
            }
        business_context = {
            "organization_id": str(organization_id) if organization_id else None,
            "period": period,
            "selected_period": selected_period,
            "selected_period_window": selected_window,
            "organization_ids": [str(item) for item in selected_scope] if selected_scope else None,
            "timezone": BUSINESS_TIMEZONE,
            "local_date": now.date().isoformat(),
            "local_now": now.isoformat(),
            "calendar_week": {
                "definition": "Rolling seven calendar dates including today; start at local midnight six days ago, end at current local time",
                "start": week_start.isoformat(),
                "end": week_end.isoformat(),
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
