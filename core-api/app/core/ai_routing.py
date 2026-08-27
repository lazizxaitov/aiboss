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


class AIModelOption(BaseModel):
    id: str
    name: str


class AIProvider(BaseModel):
    id: str
    name: str
    status: Literal["available", "unavailable", "not_configured"]
    available_models: list[AIModelOption] = Field(default_factory=list)
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
    return [
        AIProvider(
            id=provider.id,
            name=provider.name,
            status=provider.status,
            available_models=[AIModelOption(id=model.id, name=model.name) for model in provider.models],
            capabilities=provider.capabilities,
        )
        for provider in hermes_model_registry.cached_providers()
    ]


class AITaskRouter:
    def __init__(self, store: CoreDataStore) -> None:
        self.store = store

    def get_config(self) -> AIRoutingConfig:
        setting = self.store.get_app_setting(AI_ROUTING_SETTING_KEY)
        if setting is None:
            return self.default_config()
        return AIRoutingConfig.model_validate(setting.setting_value)

    def save_config(self, config: AIRoutingConfig) -> AIRoutingConfig:
        providers = {provider.id: provider for provider in _providers()}
        for role, assignment in config.roles.items():
            for provider_id, model_id in (
                (assignment.primary_provider_id, assignment.primary_model_id),
                (assignment.fallback_provider_id, assignment.fallback_model_id),
            ):
                if provider_id is None and model_id is None:
                    continue
                provider = providers.get(provider_id or "")
                if provider is None or provider.status != "available" or not model_id or model_id not in {model.id for model in provider.available_models}:
                    raise ValueError(f"Недоступный provider/model для роли {role}.")
        now = datetime.now(UTC)
        self.store.upsert_app_setting(AppSetting(
            setting_key=AI_ROUTING_SETTING_KEY,
            setting_value=config.model_dump(mode="json"),
            metadata={"scope": "global", "kind": "ai_routing"},
            created_at=now,
            updated_at=now,
        ))
        return config

    @staticmethod
    def default_config() -> AIRoutingConfig:
        providers = hermes_model_registry.cached_providers()
        if not providers or not providers[0].models:
            return AIRoutingConfig()
        default = AIRoleAssignment(
            primary_provider_id=providers[0].id,
            primary_model_id=providers[0].models[0].id,
        )
        return AIRoutingConfig(roles={
            "business_analytics": default,
            "system_action": default,
            "communications": default,
            "ai_chat": default,
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
        providers = {provider.id: provider for provider in _providers()}
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
            provider = providers.get(selected_provider_id or "")
            if provider is None and selected_provider_id == "custom" and selected_model_id:
                provider = next(
                    (
                        item
                        for item in providers.values()
                        if item.id == f"custom:{selected_model_id}"
                    ),
                    None,
                )
            if not provider or provider.status != "available" or not selected_model_id:
                continue
            if selected_model_id not in {model.id for model in provider.available_models}:
                continue
            candidates.append({
                "task_type": task_type,
                "provider_id": provider.id,
                "provider_name": provider.name,
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
    return [
        AIProvider(
            id=provider.id,
            name=provider.name,
            status=provider.status,
            available_models=[AIModelOption(id=model.id, name=model.name) for model in provider.models],
            capabilities=provider.capabilities,
        )
        for provider in providers
    ]
