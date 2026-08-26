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


class HermesProvider(BaseModel):
    id: str
    name: str
    status: str
    models: list[HermesModel] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


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
                return self._providers_cache
            return []

        self._providers_cache = providers
        self._expires_at = now + self.ttl_seconds
        return providers

    def cached_providers(self) -> list[HermesProvider]:
        return self._providers_cache or []

    @staticmethod
    def _normalize(payload: Any) -> list[HermesProvider]:
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            return []
        grouped: dict[str, HermesProvider] = {}
        for row in rows:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            model_id = str(row["id"])
            provider_id = str(row.get("provider_id") or row.get("provider") or "hermes")
            provider_name = str(row.get("provider_name") or provider_id)
            provider = grouped.setdefault(
                provider_id,
                HermesProvider(id=provider_id, name=provider_name, status="available"),
            )
            provider.models.append(HermesModel(id=model_id, name=str(row.get("name") or model_id)))
        return list(grouped.values())


hermes_model_registry = HermesModelRegistry()
