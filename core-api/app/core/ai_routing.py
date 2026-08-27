"""Persistent AI provider registry and task assignments."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.entities import AppSetting
from app.core.hermes_model_registry import HermesProvider, hermes_model_registry

AI_ROUTING_SETTING_KEY = "ai_routing:settings:v1"
TaskType = Literal["business_analytics", "system_action", "communications", "ai_chat"]


class AIProvider(BaseModel):
    id: str
    provider: str
    model: str
    name: str
    status: Literal["available", "unavailable", "not_configured"]
    available: bool = True
    capabilities: list[str] = Field(default_factory=list)


class AIRoleAssignment(BaseModel):
    primary_provider_id: str | None = None
    primary_model_id: str | None = None
    fallback_provider_id: str | None = None
    fallback_model_id: str | None = None


class AIRoutingConfig(BaseModel):
    roles: dict[TaskType, AIRoleAssignment] = Field(default_factory=dict)
    business_analytics_auto_enabled: bool = False
    business_analytics_triggers: list[str] = Field(default_factory=list)


class AIRoutingResponse(BaseModel):
    providers: list[AIProvider]
    config: AIRoutingConfig


def _providers() -> list[AIProvider]:
    return _targets(hermes_model_registry.cached_providers())


def _targets(providers: list[HermesProvider]) -> list[AIProvider]:
    targets: list[AIProvider] = []
    seen: set[tuple[str, str]] = set()
    for provider in providers:
        for model in provider.models:
            key = (provider.id, model.id)
            if key in seen:
                continue
            seen.add(key)
            available = provider.status == "available" and model.available
            targets.append(AIProvider(
                id=f"{provider.id}:{model.id}",
                provider=provider.id,
                model=model.id,
                name=model.name,
                status="available" if available else "unavailable",
                available=available,
                capabilities=provider.capabilities,
            ))
    return targets


class AITaskRouter:
    def __init__(self, store: CoreDataStore) -> None:
        self.store = store

    def get_config(self) -> AIRoutingConfig:
        setting = self.store.get_app_setting(AI_ROUTING_SETTING_KEY)
        if setting is None:
            return self.default_config()
        config = AIRoutingConfig.model_validate(setting.setting_value)
        migrated = self._migrate_legacy_config(config)
        if migrated != config:
            self._persist_config(migrated)
        return migrated

    def save_config(self, config: AIRoutingConfig) -> AIRoutingConfig:
        targets = {(target.provider, target.model): target for target in _providers()}
        for role, assignment in config.roles.items():
            for provider_id, model_id in (
                (assignment.primary_provider_id, assignment.primary_model_id),
                (assignment.fallback_provider_id, assignment.fallback_model_id),
            ):
                if provider_id is None and model_id is None:
                    continue
                target = targets.get((provider_id or "", model_id or ""))
                if target is None or not target.available:
                    raise ValueError(f"Недоступный provider/model для роли {role}.")
        self._persist_config(config)
        return config

    def _persist_config(self, config: AIRoutingConfig) -> None:
        now = datetime.now(UTC)
        self.store.upsert_app_setting(AppSetting(
            setting_key=AI_ROUTING_SETTING_KEY,
            setting_value=config.model_dump(mode="json"),
            metadata={"scope": "global", "kind": "ai_routing"},
            created_at=now,
            updated_at=now,
        ))

    def _migrate_legacy_config(self, config: AIRoutingConfig) -> AIRoutingConfig:
        targets = [target for target in _providers() if target.available]
        custom = next((target for target in targets if target.provider == "custom"), None)
        replacement = custom or (targets[0] if targets else None)
        if replacement is None:
            return config
        roles: dict[TaskType, AIRoleAssignment] = {}
        changed = False
        for role, assignment in config.roles.items():
            updates: dict[str, str | None] = {}
            if assignment.primary_provider_id == "hermes" and assignment.primary_model_id == "default":
                updates.update(primary_provider_id=replacement.provider, primary_model_id=replacement.model)
            if assignment.fallback_provider_id == "hermes" and assignment.fallback_model_id == "default":
                updates.update(fallback_provider_id=replacement.provider, fallback_model_id=replacement.model)
            roles[role] = assignment.model_copy(update=updates) if updates else assignment
            changed = changed or bool(updates)
        return config.model_copy(update={"roles": roles}) if changed else config

    @staticmethod
    def default_config() -> AIRoutingConfig:
        targets = [target for target in _providers() if target.available]
        if not targets:
            return AIRoutingConfig()
        return AIRoutingConfig(roles={
            role: AIRoleAssignment(primary_provider_id=targets[0].provider, primary_model_id=targets[0].model)
            for role in ("business_analytics", "system_action", "communications", "ai_chat")
        })

    def resolve(self, task_type: TaskType) -> AIRoleAssignment:
        return self.get_config().roles.get(task_type, self.default_config().roles[task_type])

    def resolve_candidates(
        self,
        task_type: TaskType,
        *,
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> list[dict[str, object]]:
        targets = {(target.provider, target.model): target for target in _providers()}
        if provider_id or model_id:
            assignment = [(provider_id, model_id, False)]
        else:
            role = self.resolve(task_type)
            assignment = [
                (role.primary_provider_id, role.primary_model_id, False),
                (role.fallback_provider_id, role.fallback_model_id, True),
            ]
        candidates: list[dict[str, object]] = []
        for selected_provider_id, selected_model_id, fallback_used in assignment:
            target = targets.get((selected_provider_id or "", selected_model_id or ""))
            if target is None or not target.available:
                continue
            candidates.append({
                "task_type": task_type,
                "provider_id": target.provider,
                "provider_name": target.name,
                "model_id": selected_model_id,
                "fallback_used": fallback_used,
            })
        return candidates

    def resolve_runtime(
        self,
        task_type: TaskType,
        *,
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> dict[str, object]:
        return (self.resolve_candidates(task_type, provider_id=provider_id, model_id=model_id) or [
            {"task_type": task_type, "provider_id": None, "model_id": None, "fallback_used": False},
        ])[0]


def get_routing_response(store: CoreDataStore) -> AIRoutingResponse:
    return AIRoutingResponse(providers=_providers(), config=AITaskRouter(store).get_config())


def providers_from_registry(providers: list[HermesProvider]) -> list[AIProvider]:
    return _targets(providers)
