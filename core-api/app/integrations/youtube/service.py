"""YouTube discovery, explicit mapping and bounded idempotent sync."""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.core.data_layer.entities import AppSetting
from app.integrations.youtube.client import YouTubeAPIError, YouTubeClient
from app.integrations.youtube.config import YOUTUBE_CREDENTIALS_SETTING_KEY, YouTubeConfig
from app.integrations.youtube.repository import YouTubeRepository

CREDENTIAL_FIELDS = ("client_id", "client_secret", "redirect_uri", "access_token", "refresh_token")


def _stat(value: Any) -> str | None:
    return str(value) if value is not None else None


class YouTubeMarketingService:
    def __init__(
        self,
        store: Any,
        *,
        config: YouTubeConfig | None = None,
        client: YouTubeClient | None = None,
    ) -> None:
        self.store = store
        self.config = config or YouTubeConfig.resolve(store)
        self.client = client or YouTubeClient(self.config)
        self.repository = YouTubeRepository(store)

    def credentials_state(self) -> dict[str, bool]:
        """Which credential fields are currently set — never the values themselves."""

        return {field: bool(getattr(self.config, field)) for field in CREDENTIAL_FIELDS}

    def save_credentials(self, **fields: str | None) -> dict[str, bool]:
        """Persist owner-entered YouTube credentials (Settings → Интеграции → YouTube).

        Only fields explicitly passed (not None) are touched; passing an empty
        string clears that field instead of leaving it as-is.
        """

        existing = self.store.get_app_setting(YOUTUBE_CREDENTIALS_SETTING_KEY)
        stored: dict[str, Any] = dict(existing.setting_value) if existing else {}
        now = datetime.now(timezone.utc)
        for field in CREDENTIAL_FIELDS:
            if field not in fields or fields[field] is None:
                continue
            value = fields[field].strip()
            if value:
                stored[field] = value
            else:
                stored.pop(field, None)
        self.store.upsert_app_setting(AppSetting(
            setting_key=YOUTUBE_CREDENTIALS_SETTING_KEY,
            setting_value=stored,
            metadata={"scope": "global", "kind": "integration_credentials", "provider": "youtube"},
            created_at=existing.created_at if existing else now,
            updated_at=now,
        ))
        self.config = YouTubeConfig.resolve(self.store)
        self.client = YouTubeClient(self.config)
        return self.credentials_state()

    def status(self) -> dict[str, Any]:
        connections = self.repository.list("youtube_connections")
        channels = self.repository.list("youtube_channels")
        return {
            "status": connections[0].get("status", "connected")
            if connections
            else "not_configured",
            "configured": self.config.configured,
            "credentials": self.credentials_state(),
            "last_success_at": connections[0].get("last_success_at") if connections else None,
            "last_error": connections[0].get("last_error") if connections else None,
            "channels": channels,
            "mappings": self.repository.list("youtube_resource_mappings"),
        }

    def connect(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        existing = self.repository.list("youtube_connections")
        connection_id = str(existing[0]["id"]) if existing else str(uuid4())
        try:
            channels = self.client.channels()
            self.repository.upsert(
                "youtube_connections",
                {
                    "id": connection_id,
                    "status": "connected",
                    "scopes": "youtube.readonly,youtube.analytics.readonly",
                    "created_at": existing[0].get("created_at", now) if existing else now,
                    "updated_at": now,
                    "last_success_at": now,
                },
                ("id",),
            )
            for item in channels:
                snippet = item.get("snippet") or {}
                statistics = item.get("statistics") or {}
                self.repository.upsert(
                    "youtube_channels",
                    {
                        "id": str(uuid4()),
                        "connection_id": connection_id,
                        "external_id": str(item.get("id")),
                        "title": snippet.get("title"),
                        "description": snippet.get("description"),
                        "custom_url": snippet.get("customUrl"),
                        "published_at": snippet.get("publishedAt"),
                        "country": snippet.get("country"),
                        "subscriber_count": _stat(statistics.get("subscriberCount")),
                        "video_count": _stat(statistics.get("videoCount")),
                        "view_count": _stat(statistics.get("viewCount")),
                        "created_at": now,
                        "updated_at": now,
                    },
                    ("connection_id", "external_id"),
                )
            return self.status()
        except YouTubeAPIError as exc:
            return {
                "status": "error",
                "configured": self.config.configured,
                "error": str(exc),
                "error_kind": exc.kind,
                "channels": [],
                "mappings": [],
            }

    def map_channel(
        self, organization_id: str, channel_id: str, display_name: str | None = None
    ) -> dict[str, Any]:
        row = {
            "id": str(uuid4()),
            "organization_id": organization_id,
            "channel_id": channel_id,
            "display_name": display_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.repository.upsert("youtube_resource_mappings", row, ("organization_id", "channel_id"))
        return row

    def sync(self, mode: str = "incremental", backfill_days: int = 7) -> dict[str, Any]:
        if mode not in {"incremental", "backfill"}:
            raise ValueError("Unsupported YouTube sync mode")
        status = self.connect()
        if status.get("status") != "connected":
            return {**status, "sync_status": "failed"}
        try:
            self._sync_mapped(min(max(backfill_days, 1), 365))
            return {
                **self.status(),
                "sync_mode": mode,
                "backfill_days": backfill_days,
                "sync_status": "completed",
            }
        except YouTubeAPIError as exc:
            return {
                **self.status(),
                "sync_mode": mode,
                "sync_status": "partial",
                "error": str(exc),
                "error_kind": exc.kind,
            }

    def _sync_mapped(self, days: int) -> None:
        today = datetime.now(timezone.utc).date()
        since = (today - timedelta(days=days - 1)).isoformat()
        until = today.isoformat()
        now = datetime.now(timezone.utc).isoformat()
        for mapping in self.repository.list("youtube_resource_mappings"):
            org = str(mapping["organization_id"])
            channel = next(
                (
                    row
                    for row in self.repository.list("youtube_channels")
                    if row.get("external_id") == mapping["channel_id"]
                ),
                None,
            )
            if not channel:
                continue
            channel_id = str(channel["id"])
            self.repository.upsert(
                "youtube_channels",
                {**channel, "organization_id": org, "updated_at": now},
                ("connection_id", "external_id"),
            )
            for video in self.client.videos(str(mapping["channel_id"])):
                snippet = video.get("snippet") or {}
                details = video.get("contentDetails") or {}
                state = video.get("status") or {}
                self.repository.upsert(
                    "youtube_videos",
                    {
                        "id": str(uuid4()),
                        "organization_id": org,
                        "channel_id": channel_id,
                        "external_id": str(video.get("id")),
                        "title": snippet.get("title"),
                        "description": snippet.get("description"),
                        "published_at": snippet.get("publishedAt"),
                        "duration": details.get("duration"),
                        "category_id": snippet.get("categoryId"),
                        "live_broadcast_content": snippet.get("liveBroadcastContent"),
                        "privacy_status": state.get("privacyStatus"),
                        "content_type": "unknown",
                        "created_at": now,
                        "updated_at": now,
                    },
                    ("organization_id", "external_id"),
                )
            self._sync_report(org, channel_id, str(mapping["channel_id"]), since, until, now)

    def _sync_report(
        self, org: str, channel_id: str, external_id: str, since: str, until: str, now: str
    ) -> None:
        report = self.client.analytics(
            ids=f"channel=={external_id}",
            startDate=since,
            endDate=until,
            metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares,subscribersGained,subscribersLost",
            dimensions="day",
        )
        for values in report.get("rows", []) or []:
            if not isinstance(values, list) or not values:
                continue
            date = values[0]
            metrics = values[1:]
            data = {
                "id": str(uuid4()),
                "organization_id": org,
                "channel_id": channel_id,
                "date": date,
                **dict(
                    zip(
                        (
                            "views",
                            "estimated_minutes_watched",
                            "average_view_duration",
                            "average_view_percentage",
                            "likes",
                            "comments",
                            "shares",
                            "subscribers_gained",
                            "subscribers_lost",
                        ),
                        metrics,
                        strict=False,
                    )
                ),
                "created_at": now,
                "updated_at": now,
            }
            self.repository.upsert(
                "youtube_channel_analytics_daily", data, ("organization_id", "channel_id", "date")
            )
        videos = {
            row.get("external_id"): row for row in self.repository.list("youtube_videos", org)
        }
        video_report = self.client.analytics(
            ids=f"channel=={external_id}",
            startDate=since,
            endDate=until,
            metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares,subscribersGained,subscribersLost",
            dimensions="day,video",
        )
        for values in video_report.get("rows", []) or []:
            if not isinstance(values, list) or len(values) < 2 or values[1] not in videos:
                continue
            data = {
                "id": str(uuid4()),
                "organization_id": org,
                "channel_id": channel_id,
                "video_id": str(videos[values[1]]["id"]),
                "date": values[0],
                **dict(
                    zip(
                        (
                            "views",
                            "estimated_minutes_watched",
                            "average_view_duration",
                            "average_view_percentage",
                            "likes",
                            "comments",
                            "shares",
                            "subscribers_gained",
                            "subscribers_lost",
                        ),
                        values[2:],
                        strict=False,
                    )
                ),
                "created_at": now,
                "updated_at": now,
            }
            self.repository.upsert(
                "youtube_video_analytics_daily",
                data,
                ("organization_id", "channel_id", "video_id", "date"),
            )
