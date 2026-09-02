"""Application settings."""

from functools import lru_cache

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    """Runtime configuration for the application."""

    app_name: str = "AI Business OS Core"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    storage_backend: str = "postgres"
    sqlite_path: str = ":memory:"
    postgres_dsn: str = "postgresql://postgres:postgres@localhost:5432/ai_business_os"
    ai_analytics_provider: str = "disabled"
    ai_analytics_model: str | None = None
    ai_analytics_language: str = "ru"
    ai_analytics_timeout_seconds: float = 8.0
    ai_analytics_agent_timeout_seconds: float = 300.0
    ai_analytics_widget_timeout_seconds: float = 60.0
    ai_analytics_prompt_version: str = "phase-3c-v1"
    ai_analytics_cache_ttl_seconds: int = 300
    ai_chat_timeout_seconds: float = 45.0
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    ollama_base_url: str = "http://127.0.0.1:11434"
    hermes_base_url: str = "http://127.0.0.1:8642/v1"
    hermes_api_key: str = "aiboss-hermes-local"
    hermes_model: str = "gemma4:26b"
    telegram_bot_token: str | None = None
    telegram_transport_enabled: bool = True
    telegram_poll_timeout_seconds: int = 25
    telegram_request_timeout_seconds: float = 35.0
    telegram_ai_timeout_seconds: float = 120.0
    telegram_bot_username: str | None = None
    telegram_max_media_bytes: int = 20 * 1024 * 1024
    telegram_media_dir: str = "/tmp/aiboss-telegram-media"
    ai_transcription_provider: str | None = None
    ai_transcription_model: str | None = None
    ai_transcription_timeout_seconds: float = 60.0
    owner_login: str | None = None
    owner_password: str | None = None
    auth_secret: str = "change-this-ai-business-os-secret"
    smartup_live_sync_enabled: bool = True
    smartup_live_sync_interval_seconds: int = 300
    smartup_reconciliation_interval_seconds: int = 86400
    smartup_auto_sync_schedule: str = "08:00,14:00,21:00"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type["Settings"],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Prioritize .env values over ambient environment variables."""

        return init_settings, dotenv_settings, env_settings, file_secret_settings


@lru_cache
def get_settings() -> Settings:
    """Return cached settings."""

    return Settings()


settings = get_settings()
