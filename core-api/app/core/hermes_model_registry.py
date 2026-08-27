"""Runtime discovery of providers and models exposed by the local Hermes API."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.config import settings


class HermesModel(BaseModel):
    id: str
    name: str
    available: bool = True
    provider_id: str | None = None


class HermesProvider(BaseModel):
    id: str
    name: str
    status: str
    models: list[HermesModel] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    auth_type: str | None = None


@dataclass(slots=True)
class HermesModelRegistry:
    ttl_seconds: int = 60

    _providers_cache: list[HermesProvider] | None = None
    _expires_at: float = 0

    async def get_providers(self, *, refresh: bool = False) -> list[HermesProvider]:
        now = time.monotonic()
        if not refresh and self._providers_cache is not None and now < self._expires_at:
            return self._providers_cache

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{settings.hermes_base_url.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {settings.hermes_api_key}"},
                )
                response.raise_for_status()
                providers = self._normalize(response.json())
        except (httpx.HTTPError, ValueError, TypeError):
            if self._providers_cache is not None:
                self._providers_cache = [
                    provider.model_copy(update={"status": "unavailable"})
                    for provider in self._providers_cache
                ]
                self._expires_at = now + min(self.ttl_seconds, 10)
                return self._providers_cache
            return []

        self._providers_cache = providers
        self._expires_at = now + self.ttl_seconds
        return providers

    def cached_providers(self) -> list[HermesProvider]:
        return self._providers_cache or []

    @staticmethod
    def _normalize(payload: Any) -> list[HermesProvider]:
        if not isinstance(payload, dict):
            return []
        rows = payload.get("providers") or payload.get("data") or []
        if not isinstance(rows, list):
            return []
        grouped: dict[str, HermesProvider] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            nested_models = row.get("models") or row.get("available_models")
            model_rows = nested_models if isinstance(nested_models, list) else [row]
            provider_hint = row.get("provider_id") or row.get("provider") or row.get("owned_by")
            for model_row in model_rows:
                if isinstance(model_row, str):
                    model_row = {"id": model_row}
                if not isinstance(model_row, dict) or not model_row.get("id"):
                    continue
                model_id = str(model_row["id"])
                provider_id, provider_name, auth_type = HermesModelRegistry._provider_details(
                    model_row,
                    provider_hint,
                )
                provider = grouped.setdefault(
                    provider_id,
                    HermesProvider(
                        id=provider_id,
                        name=provider_name,
                        status=HermesModelRegistry._status(row, model_row),
                        auth_type=auth_type,
                    ),
                )
                if provider.status == "available" and HermesModelRegistry._status(row, model_row) != "available":
                    provider.status = HermesModelRegistry._status(row, model_row)
                provider.auth_type = provider.auth_type or auth_type
                if not any(model.id == model_id for model in provider.models):
                    provider.models.append(HermesModel(
                        id=model_id,
                        name=str(model_row.get("display_name") or model_row.get("name") or model_id),
                        available=bool(model_row.get("available", row.get("available", True))),
                        provider_id=provider_id,
                    ))
        return list(grouped.values())

    @staticmethod
    def _status(provider: dict[str, Any], model: dict[str, Any]) -> str:
        if provider.get("available") is False or model.get("available") is False:
            return "unavailable"
        status = str(model.get("status") or provider.get("status") or "available").lower()
        if status in {"available", "ready", "connected", "ok", "configured", "logged_in", "authenticated"}:
            return "available"
        if status in {"not_configured", "not-configured", "unconfigured"}:
            return "not_configured"
        return "unavailable"

    @staticmethod
    def _provider_details(model: dict[str, Any], provider_hint: Any) -> tuple[str, str, str | None]:
        raw_id = str(provider_hint or "").lower()
        model_id = str(model.get("id") or "")
        if not raw_id:
            if "codex" in model_id.lower():
                raw_id = "openai-codex"
            elif model_id.startswith("custom:") or model_id == settings.hermes_model:
                raw_id = "custom"
            else:
                raw_id = "hermes"
        if raw_id in {"codex", "openai_codex", "openai-codex"}:
            return "openai-codex", "OpenAI Codex", "oauth"
        if raw_id in {"custom", "custom_endpoint", "custom-endpoint"}:
            return "custom", "Custom endpoint", "custom_endpoint"
        name = str(model.get("provider_name") or model.get("display_name") or provider_hint or raw_id)
        return raw_id, name, str(model.get("auth_type")) if model.get("auth_type") else None


hermes_model_registry = HermesModelRegistry()
