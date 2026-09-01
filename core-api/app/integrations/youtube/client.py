"""Official YouTube Data and Analytics API client."""

from __future__ import annotations

from typing import Any
import httpx

from app.integrations.youtube.config import YouTubeConfig


class YouTubeAPIError(RuntimeError):
    def __init__(self, message: str, *, kind: str = "api") -> None:
        super().__init__(message)
        self.kind = kind


class YouTubeClient:
    def __init__(self, config: YouTubeConfig, client: httpx.Client | None = None) -> None:
        self.config = config
        self.client = client or httpx.Client(timeout=30.0)
        self._access_token = config.access_token

    def _refresh(self) -> None:
        if self._access_token or not self.config.refresh_token:
            return
        response = self.client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "refresh_token": self.config.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if response.status_code >= 400:
            raise YouTubeAPIError("YouTube OAuth refresh failed", kind="refresh")
        payload = response.json()
        self._access_token = payload.get("access_token")
        if not self._access_token:
            raise YouTubeAPIError("YouTube OAuth refresh returned no access token", kind="refresh")

    def _request(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        self._refresh()
        if not self._access_token:
            raise YouTubeAPIError("YouTube connection is not configured", kind="not_configured")
        response = self.client.get(url, params={**params, "access_token": self._access_token})
        if response.status_code in (401, 403):
            raise YouTubeAPIError("YouTube authorization or scope is unavailable", kind="oauth")
        if response.status_code == 429:
            raise YouTubeAPIError("YouTube quota or rate limit reached", kind="quota")
        if response.status_code >= 400:
            raise YouTubeAPIError("YouTube API request failed", kind="api")
        try:
            payload = response.json()
        except ValueError as exc:
            raise YouTubeAPIError("YouTube returned malformed data", kind="malformed") from exc
        if not isinstance(payload, dict):
            raise YouTubeAPIError("YouTube returned malformed data", kind="malformed")
        return payload

    def data(self, resource: str, **params: Any) -> dict[str, Any]:
        return self._request(
            f"{self.config.api_base_url.rstrip('/')}/{resource.lstrip('/')}", params
        )

    def analytics(self, **params: Any) -> dict[str, Any]:
        return self._request(f"{self.config.analytics_base_url.rstrip('/')}/reports", params)

    def channels(self) -> list[dict[str, Any]]:
        return self.data(
            "channels", part="snippet,statistics,contentDetails,status", mine="true"
        ).get("items", [])

    def videos(self, channel_id: str) -> list[dict[str, Any]]:
        search = self.data(
            "search", part="snippet", channelId=channel_id, type="video", maxResults=50
        )
        ids = [
            item.get("id", {}).get("videoId")
            for item in search.get("items", [])
            if isinstance(item, dict)
        ]
        ids = [item for item in ids if isinstance(item, str)]
        if not ids:
            return []
        return self.data("videos", part="snippet,contentDetails,status", id=",".join(ids)).get(
            "items", []
        )
