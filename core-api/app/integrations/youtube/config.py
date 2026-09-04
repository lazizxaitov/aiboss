"""Backend-only Google OAuth configuration for YouTube.

Two sources are layered together: environment variables (YOUTUBE_CLIENT_ID
and friends — set once by whoever deploys the server) and a small settings
row in the core data store (set by the owner from Settings → Интеграции →
YouTube, see app/integrations/youtube/service.py's save_credentials()). The
Settings-entered value wins when present; the env var is the fallback for a
setup that still configures YouTube the old way, via .env."""

from dataclasses import dataclass
from typing import Any
import os

YOUTUBE_CREDENTIALS_SETTING_KEY = "integrations:youtube:credentials:v1"


@dataclass(frozen=True, slots=True)
class YouTubeConfig:
    client_id: str | None
    client_secret: str | None
    redirect_uri: str | None
    access_token: str | None
    refresh_token: str | None
    api_base_url: str
    analytics_base_url: str

    @classmethod
    def from_env(cls) -> "YouTubeConfig":
        return cls(
            client_id=os.getenv("YOUTUBE_CLIENT_ID"),
            client_secret=os.getenv("YOUTUBE_CLIENT_SECRET"),
            redirect_uri=os.getenv("YOUTUBE_REDIRECT_URI"),
            access_token=os.getenv("YOUTUBE_ACCESS_TOKEN"),
            refresh_token=os.getenv("YOUTUBE_REFRESH_TOKEN"),
            api_base_url=os.getenv(
                "YOUTUBE_DATA_API_BASE_URL", "https://www.googleapis.com/youtube/v3"
            ),
            analytics_base_url=os.getenv(
                "YOUTUBE_ANALYTICS_API_BASE_URL", "https://youtubeanalytics.googleapis.com/v2"
            ),
        )

    @classmethod
    def resolve(cls, store: Any) -> "YouTubeConfig":
        env = cls.from_env()
        try:
            setting = store.get_app_setting(YOUTUBE_CREDENTIALS_SETTING_KEY)
        except Exception:  # noqa: BLE001 - a broken settings read must never block YouTube entirely
            setting = None
        stored = setting.setting_value if setting else {}

        def pick(key: str, fallback: str | None) -> str | None:
            value = stored.get(key)
            return value if isinstance(value, str) and value.strip() else fallback

        return cls(
            client_id=pick("client_id", env.client_id),
            client_secret=pick("client_secret", env.client_secret),
            redirect_uri=pick("redirect_uri", env.redirect_uri),
            access_token=pick("access_token", env.access_token),
            refresh_token=pick("refresh_token", env.refresh_token),
            api_base_url=env.api_base_url,
            analytics_base_url=env.analytics_base_url,
        )

    @property
    def configured(self) -> bool:
        return bool(
            self.client_id
            and self.client_secret
            and self.redirect_uri
            and (self.access_token or self.refresh_token)
        )
