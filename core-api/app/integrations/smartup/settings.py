"""SmartUp integration settings."""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SmartUpOrganizationConfig(BaseModel):
    """SmartUp organization entry loaded from environment variables."""

    name: str
    company_id: str = "11300"
    filial_id: str
    filial_code: str | None = None
    project_code: str = "trade"


class SmartUpSettings(BaseSettings):
    """Configuration for the SmartUp API client."""

    base_url: str = "https://smartup.online"
    username: str = ""
    password: str = ""
    company_id: str = "11300"
    project_code: str = "trade"
    filial_id: str = ""
    lang_code: str = "ru"
    timeout_seconds: float = 30.0
    history_start_date: str | None = None
    history_chunk_days: int = 7
    normalization_pipeline_enabled: bool = False
    organizations: list[SmartUpOrganizationConfig] = Field(default_factory=list)

    model_config = SettingsConfigDict(
        env_prefix="SMARTUP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
