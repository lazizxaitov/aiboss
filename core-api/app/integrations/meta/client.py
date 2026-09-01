"""Small official Graph API client with pagination and safe error classes."""

from __future__ import annotations

from typing import Any
import httpx

from app.integrations.meta.config import MetaConfig


class MetaAPIError(RuntimeError):
    def __init__(self, message: str, *, kind: str = "graph_error") -> None:
        super().__init__(message)
        self.kind = kind


class MetaGraphClient:
    def __init__(self, config: MetaConfig, client: httpx.Client | None = None) -> None:
        self.config = config
        self.client = client or httpx.Client(timeout=30.0)

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        if not self.config.access_token:
            raise MetaAPIError("Meta connection is not configured", kind="not_configured")
        url = f"{self.config.base_url.rstrip('/')}/{self.config.api_version.strip('/')}/{path.strip('/')}"
        try:
            response = self.client.get(
                url, params={**params, "access_token": self.config.access_token}
            )
        except httpx.HTTPError as exc:
            raise MetaAPIError("Meta is temporarily unavailable", kind="network") from exc
        if response.status_code in (401, 403):
            raise MetaAPIError("Meta authorization or permission is unavailable", kind="permission")
        if response.status_code == 429:
            raise MetaAPIError("Meta rate limit reached", kind="rate_limit")
        if response.status_code >= 400:
            raise MetaAPIError("Meta Graph API request failed", kind="graph_error")
        try:
            payload = response.json()
        except ValueError as exc:
            raise MetaAPIError("Meta returned malformed data", kind="malformed") from exc
        if not isinstance(payload, dict):
            raise MetaAPIError("Meta returned malformed data", kind="malformed")
        return payload

    def pages(self) -> list[dict[str, Any]]:
        payload = self.get("me/accounts", fields="id,name,category,instagram_business_account")
        return self._paginate(payload)

    def ad_accounts(self) -> list[dict[str, Any]]:
        payload = self.get("me/adaccounts", fields="id,name,currency,timezone_name,account_status")
        return self._paginate(payload)

    def collection(self, object_id: str, edge: str, *, fields: str = "") -> list[dict[str, Any]]:
        payload = self.get(f"{object_id}/{edge}", **({"fields": fields} if fields else {}))
        return self._paginate(payload)

    def insights(
        self,
        object_id: str,
        *,
        since: str,
        until: str,
        level: str = "ad",
        breakdowns: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        params = {
            "fields": "date_start,date_stop,spend,impressions,reach,frequency,clicks,unique_clicks,ctr,cpc,cpm,actions,action_values,cost_per_action_type",
            "time_range": '{"since":"%s","until":"%s"}' % (since, until),
            "level": level,
        }
        if breakdowns:
            params["breakdowns"] = ",".join(breakdowns)
        return self._paginate(self.get(f"{object_id}/insights", **params))

    def _paginate(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows = list(payload.get("data") or []) if isinstance(payload.get("data"), list) else []
        next_url = (
            (payload.get("paging") or {}).get("next")
            if isinstance(payload.get("paging"), dict)
            else None
        )
        while isinstance(next_url, str) and next_url:
            try:
                response = self.client.get(next_url)
                response.raise_for_status()
                page = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise MetaAPIError("Meta pagination failed", kind="network") from exc
            if not isinstance(page, dict):
                break
            rows.extend(item for item in page.get("data", []) if isinstance(item, dict))
            next_url = (
                (page.get("paging") or {}).get("next")
                if isinstance(page.get("paging"), dict)
                else None
            )
        return rows
