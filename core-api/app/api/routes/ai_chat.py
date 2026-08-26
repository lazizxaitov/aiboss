"""Streaming chat proxy for the local Hermes OpenAI-compatible server."""

from __future__ import annotations

import json
from typing import Literal

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings

router = APIRouter(prefix="/ai")


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)


def _event(payload: dict[str, str], event: str | None = None) -> str:
    prefix = f"event: {event}\n" if event else ""
    return f'{prefix}data: {json.dumps(payload, ensure_ascii=False)}\n\n'


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """Proxy Hermes' OpenAI-compatible stream without exposing its credentials."""

    async def stream():
        url = f"{settings.hermes_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {settings.hermes_api_key}"}
        body = {
            "model": settings.hermes_model,
            "messages": [message.model_dump() for message in request.messages],
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", url, headers=headers, json=body) as response:
                    if response.status_code >= 400:
                        detail = (await response.aread()).decode("utf-8", errors="replace")
                        yield _event({"message": detail or "Hermes вернул ошибку."}, "error")
                        return
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            yield _event({}, "done")
                            return
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                        if content:
                            yield _event({"content": content})
                    yield _event({}, "done")
        except httpx.HTTPError:
            yield _event({"message": "Не удалось подключиться к AI."}, "error")

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
