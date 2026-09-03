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
    # 60s / 4 tool calls was too tight for the "Что важно сейчас" widget scan
    # (it still has to touch several read-only views to say anything useful)
    # and was hitting ResearchTimeoutError on most runs — see
    # AI_ANALYTICS_TIMEOUT logs and the raw error surfaced to the widget.
    ai_analytics_widget_timeout_seconds: float = 90.0
    ai_analytics_prompt_version: str = "phase-3c-v1"
    ai_analytics_cache_ttl_seconds: int = 300
    # This used to be tuned tighter and tighter (45s -> 90s -> 240s) and kept
    # failing on genuinely heavy chat questions ("посмотри где упали продажи
    # и дай подробный анализ") because each individual round's HTTP call was
    # given a SHRINKING slice of whatever was left of this number — so no
    # matter how high it was raised, a request needing many rounds eventually
    # starved late in its own research. That per-round starvation is now
    # fixed directly (ROUND_REQUEST_TIMEOUT_SECONDS / SQL_STATEMENT_TIMEOUT_SECONDS
    # in ai_business_agent.py give every round a fixed, generous timeout
    # instead). This number is now only an outer safety net for a wedged
    # request, not the everyday limit — CHAT_MAX_ROUNDS/CHAT_TOOL_CALLS decide
    # how deep an analysis can go, and those don't need bumping for a bigger
    # question. Set generously so it is never the reason a real analysis
    # fails.
    ai_chat_timeout_seconds: float = 1800.0
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
    # Kept at least as high as ai_chat_timeout_seconds so a broad "analyze
    # everything" request asked over Telegram gets at least as much research
    # time as the same request in the web chat. Same outer-safety-net role —
    # see the comment on ai_chat_timeout_seconds.
    telegram_ai_timeout_seconds: float = 1800.0
    telegram_bot_username: str | None = None
    telegram_max_media_bytes: int = 20 * 1024 * 1024
    telegram_media_dir: str = "/tmp/aiboss-telegram-media"
    ai_transcription_provider: str | None = None
    ai_transcription_model: str | None = None
    ai_transcription_timeout_seconds: float = 60.0
    # For ai_transcription_provider = "local": any OpenAI-compatible
    # speech-to-text server (e.g. faster-whisper-server / "speaches"), run
    # on your own infrastructure so voice messages never leave it. Same
    # request shape as OpenAI's /audio/transcriptions endpoint.
    ai_transcription_local_base_url: str = "http://127.0.0.1:8090/v1"
    ai_transcription_local_api_key: str = "aiboss-whisper-local"
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
