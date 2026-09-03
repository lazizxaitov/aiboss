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
    resolve_business_period,
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
        compact_business_data: bool = False,
        include_business_environment: bool = True,
    ) -> dict[str, Any]:
        now = datetime.now(UTC).astimezone(ZoneInfo(BUSINESS_TIMEZONE))
        week = resolve_business_period("this_week", now)
        week_start, week_end = week.start, week.end
        context_service = OrganizationContextService(self.store)
        # `resolve_accessible_organization_ids()` and the `accessible_organizations`
        # list below both ultimately read `list_canonical_organizations()`. This
        # used to be fetched twice (once inside resolve_accessible_organization_ids,
        # once directly here) on every single AI request. Fetch it once and derive
        # both from the same result.
        list_organizations = getattr(self.store, "list_canonical_organizations", None)
        organizations = list_organizations() if callable(list_organizations) else []
        if not isinstance(organizations, (list, tuple)):
            organizations = []
        accessible_organization_ids = list(dict.fromkeys(
            organization.organization_id
            for organization in organizations
            if getattr(organization, "organization_id", None) is not None
        ))
        if callable(getattr(self.store, "get_app_setting", None)):
            selected_context = context_service.get_context()
            selected_scope = (
                [organization_id]
                if organization_id is not None
                else accessible_organization_ids
            )
        else:
            selected_context = AnalyticsContextState()
            selected_scope = accessible_organization_ids
        accessible_organizations = [
            {"id": str(item.organization_id), "name": item.name}
            for item in organizations
            if getattr(item, "organization_id", None) is not None
        ]
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
            "organization_scope": {
                "default_mode": "explicit" if organization_id is not None else "all_accessible",
                "accessible_organizations": accessible_organizations,
                "selected_organization_ids": (
                    [str(item) for item in selected_scope]
                    if organization_id is not None
                    else None
                ),
            },
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
        if include_business_environment and any(
            capability.name == "business.query" for capability in self.registry.for_role(role)
        ):
            sql_service = AIReadOnlySQLService(self.store)
            schema = sql_service.database_schema()
            context["database"] = {
                "kind": "published_read_only_views",
                **(
                    {"domain_index": sql_service.semantic_domain_index(schema)}
                    if compact_business_data
                    else {
                        "schema": schema,
                        "semantic_environment": sql_service.semantic_environment(schema),
                    }
                ),
            }
        if ui_context:
            context["current_ui"] = ui_context
        return context
