"""Meta configuration. Credentials are resolved only in the backend."""

from dataclasses import dataclass
import os


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

    @property
    def configured(self) -> bool:
        return bool(self.access_token or (self.app_id and self.app_secret and self.redirect_uri))
