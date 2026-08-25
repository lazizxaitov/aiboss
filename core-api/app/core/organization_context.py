"""Global organization and period context for the executive dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.core.analytics.models import AnalyticsPeriodPreset
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.entities import AppSetting

CONTEXT_SETTING_KEY = "global_analytics_context"


class OrganizationContextMode(StrEnum):
    """Supported organization selection modes."""

    ALL = "all"
    SINGLE = "single"
    MULTIPLE = "multiple"


class OrganizationContext(BaseModel):
    """Organization selection context shared across dashboard pages."""

    mode: OrganizationContextMode = OrganizationContextMode.ALL
    organization_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize(self) -> OrganizationContext:
        unique_ids = list(dict.fromkeys(self.organization_ids))
        if self.mode == OrganizationContextMode.ALL:
            self.organization_ids = []
        elif self.mode == OrganizationContextMode.SINGLE:
            self.organization_ids = unique_ids[:1]
        else:
            self.organization_ids = unique_ids
        return self


class PeriodContext(BaseModel):
    """Reusable period selection context."""

    preset: AnalyticsPeriodPreset = AnalyticsPeriodPreset.LAST_30_DAYS
    date_from: date | None = None
    date_to: date | None = None


class AnalyticsContextState(BaseModel):
    """Combined global context persisted by the core store."""

    organization_context: OrganizationContext = Field(default_factory=OrganizationContext)
    period_context: PeriodContext = Field(default_factory=PeriodContext)
    saved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AnalyticsContextUpdate(BaseModel):
    """Partial update payload for the global context."""

    organization_context: OrganizationContext | None = None
    period_context: PeriodContext | None = None


@dataclass(slots=True)
class OrganizationContextService:
    """Persist and resolve the selected organization context."""

    store: CoreDataStore

    def get_context(self) -> AnalyticsContextState:
        """Return the persisted context or a default global context."""

        setting = self.store.get_app_setting(CONTEXT_SETTING_KEY)
        if setting is None:
            return AnalyticsContextState()
        return self._deserialize(setting)

    def save_context(self, context: AnalyticsContextState) -> AnalyticsContextState:
        """Persist the current context in the core store."""

        normalized = context.model_copy(update={"saved_at": datetime.now(UTC)})
        self.store.upsert_app_setting(
            AppSetting(
                setting_key=CONTEXT_SETTING_KEY,
                setting_value=normalized.model_dump(mode="json"),
                metadata={"scope": "global"},
                created_at=normalized.saved_at,
                updated_at=normalized.saved_at,
            ),
        )
        return normalized

    def update_context(self, update: AnalyticsContextUpdate) -> AnalyticsContextState:
        """Merge a partial update into the existing context."""

        current = self.get_context()
        payload = current.model_dump(mode="python")
        if update.organization_context is not None:
            payload["organization_context"] = update.organization_context.model_dump(
                mode="python",
            )
        if update.period_context is not None:
            payload["period_context"] = update.period_context.model_dump(mode="python")
        return self.save_context(AnalyticsContextState.model_validate(payload))

    def reset_context(self) -> AnalyticsContextState:
        """Reset the context to its default global state."""

        return self.save_context(AnalyticsContextState())

    def resolve_organization_ids(
        self,
        *,
        organization_id: UUID | None = None,
        organization_ids: list[UUID] | None = None,
    ) -> list[UUID] | None:
        """Resolve the effective organization filter for a request."""

        if organization_id is not None:
            return [organization_id]

        ids = list(dict.fromkeys(organization_ids or []))
        if ids:
            return ids

        context = self.get_context().organization_context
        if context.mode == OrganizationContextMode.ALL or not context.organization_ids:
            return None
        return list(context.organization_ids)

    def _deserialize(self, setting: AppSetting) -> AnalyticsContextState:
        value = setting.setting_value or {}
        if not isinstance(value, dict):
            return AnalyticsContextState()

        try:
            return AnalyticsContextState.model_validate(value)
        except Exception:  # noqa: BLE001 - fall back to safe defaults for corrupt settings
            return AnalyticsContextState()
