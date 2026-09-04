"""Meta configuration. Credentials are resolved only in the backend.

Two sources are layered together: environment variables (META_APP_ID and
friends — set once by whoever deploys the server) and a small settings row
in the core data store (set by the owner from Settings → Интеграции →
Meta, see app/integrations/meta/service.py's save_credentials()). The
Settings-entered value wins when present; the env var is the fallback for a
setup that still configures Meta the old way, via .env."""

from dataclasses import dataclass
from typing import Any
import os

META_CREDENTIALS_SETTING_KEY = "integrations:meta:credentials:v1"


@dataclass(frozen=True, slots=True)
class MetaConfig:
    api_version: str
    base_url: str
    app_id: str | None
    app_secret: str | None
    redirect_uri: str | None
    access_token: str | None

    @classmethod
    def from_env(cls) -> "MetaConfig":
        return cls(
            api_version=os.getenv("META_GRAPH_API_VERSION", "v21.0"),
            base_url=os.getenv("META_GRAPH_API_BASE_URL", "https://graph.facebook.com"),
            app_id=os.getenv("META_APP_ID"),
            app_secret=os.getenv("META_APP_SECRET"),
            redirect_uri=os.getenv("META_REDIRECT_URI"),
            access_token=os.getenv("META_ACCESS_TOKEN"),
        )

    @classmethod
    def resolve(cls, store: Any) -> "MetaConfig":
        env = cls.from_env()
        try:
            setting = store.get_app_setting(META_CREDENTIALS_SETTING_KEY)
        except Exception:  # noqa: BLE001 - a broken settings read must never block Meta entirely
            setting = None
        stored = setting.setting_value if setting else {}

        def pick(key: str, fallback: str | None) -> str | None:
            value = stored.get(key)
            return value if isinstance(value, str) and value.strip() else fallback

        return cls(
            api_version=env.api_version,
            base_url=env.base_url,
            app_id=pick("app_id", env.app_id),
            app_secret=pick("app_secret", env.app_secret),
            redirect_uri=pick("redirect_uri", env.redirect_uri),
            access_token=pick("access_token", env.access_token),
        )

    @property
    def configured(self) -> bool:
        return bool(self.access_token or (self.app_id and self.app_secret and self.redirect_uri))
