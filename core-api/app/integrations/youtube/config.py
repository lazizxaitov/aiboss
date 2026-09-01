"""Backend-only Google OAuth configuration for YouTube."""

from dataclasses import dataclass
import os


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

    @property
    def configured(self) -> bool:
        return bool(
            self.client_id
            and self.client_secret
            and self.redirect_uri
            and (self.access_token or self.refresh_token)
        )
