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
    # Providers/models change rarely; refreshing every 60s meant a request
    # arriving right after expiry paid a synchronous Hermes round trip (which
    # can itself queue behind Hermes's own inference work) before the actual
    # chat/analysis call even started. See AI_LATENCY_PROBLEMS.txt problem #5.
    ttl_seconds: int = 300

    _providers_cache: list[HermesProvider] | None = None
    _expires_at: float = 0

    async def get_providers(self, *, refresh: bool = False) -> list[HermesProvider]:
        now = time.monotonic()
        if not refresh and self._providers_cache is not None and now < self._expires_at:
            return self._providers_cache

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                headers = {"Authorization": f"Bearer {settings.hermes_api_key}"}
                response = await client.get(
                    f"{settings.hermes_base_url.rstrip('/').removesuffix('/v1')}/api/model/options?refresh=1",
                    headers=headers,
                )
                if response.status_code == 404:
                    response = await client.get(
                        f"{settings.hermes_base_url.rstrip('/')}/models",
                        headers=headers,
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
        provider_rows = payload.get("providers")
        if isinstance(provider_rows, list):
            return HermesModelRegistry._normalize_provider_options(provider_rows)

        rows = payload.get("data") or []
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
                if not isinstance(model_row, dict):
                    continue
                model_id_value = model_row.get("id") or model_row.get("model_id") or model_row.get("model")
                if not model_id_value or not isinstance(model_id_value, (str, int, float)):
                    continue
                model_id = str(model_id_value)
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
    def _normalize_provider_options(rows: list[Any]) -> list[HermesProvider]:
        grouped: dict[str, HermesProvider] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            provider_id = str(row.get("slug") or row.get("provider_id") or row.get("provider") or "").strip()
            if not provider_id:
                continue
            authenticated = row.get("authenticated") is True
            is_current = row.get("is_current") is True
            if not authenticated and not is_current:
                continue
            raw_models = row.get("models") or row.get("available_models") or []
            if not isinstance(raw_models, list):
                continue
            models: list[HermesModel] = []
            for raw_model in raw_models:
                if isinstance(raw_model, str):
                    model_id = raw_model.strip()
                    model_name = HermesModelRegistry._display_model_name(model_id)
                elif isinstance(raw_model, dict):
                    model_id = str(raw_model.get("id") or raw_model.get("model_id") or raw_model.get("model") or "").strip()
                    model_name = str(raw_model.get("display_name") or raw_model.get("name") or model_id)
                else:
                    continue
                if not model_id or any(model.id == model_id for model in models):
                    continue
                models.append(HermesModel(
                    id=model_id,
                    name=model_name,
                    available=True,
                    provider_id=provider_id,
                ))
            if not models:
                continue
            existing = grouped.get(provider_id)
            if existing is None:
                grouped[provider_id] = HermesProvider(
                    id=provider_id,
                    name=str(row.get("name") or provider_id),
                    status="available",
                    models=models,
                    auth_type="oauth" if authenticated else ("custom_endpoint" if provider_id == "custom" else None),
                )
            else:
                existing.models.extend(model for model in models if model.id not in {item.id for item in existing.models})
        return list(grouped.values())

    @staticmethod
    def _display_model_name(model_id: str) -> str:
        if model_id.lower().startswith("gpt-"):
            return "GPT-" + model_id[4:].replace("-", " ").title()
        return model_id

    @staticmethod
    def _status(provider: dict[str, Any], model: dict[str, Any]) -> str:
        if provider.get("available") is False or provider.get("authenticated") is False:
            return "unavailable"
        if model.get("available") is False or model.get("authenticated") is False:
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
