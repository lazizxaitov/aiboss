"""Provider-independent media boundary for AI Business OS."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import settings


@dataclass(frozen=True, slots=True)
class AITranscription:
    text: str
    provider_id: str
    model_id: str


class TranscriptionProvider(Protocol):
    async def transcribe(self, path: Path, *, filename: str, mime_type: str) -> AITranscription:
        ...


class TranscriptionService:
    """Use an explicitly configured speech provider, never the chat model."""

    async def transcribe(self, path: Path, *, filename: str, mime_type: str) -> AITranscription:
        provider = settings.ai_transcription_provider
        model = settings.ai_transcription_model
        if not provider or not model:
            raise RuntimeError("Транскрибация голосовых сообщений не настроена")
        if provider != "openai" or not settings.openai_api_key:
            raise RuntimeError("Выбранный provider транскрибации недоступен")
        async with httpx.AsyncClient(timeout=settings.ai_transcription_timeout_seconds) as client:
            with path.open("rb") as media:
                response = await client.post(
                    f"{settings.openai_base_url.rstrip('/')}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    data={"model": model},
                    files={"file": (filename, media, mime_type)},
                )
            response.raise_for_status()
            payload = response.json()
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Provider транскрибации не вернул текст")
        return AITranscription(text=text.strip(), provider_id=provider, model_id=model)
