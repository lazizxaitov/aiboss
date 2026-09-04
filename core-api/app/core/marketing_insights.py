"""Best-effort LLM commentary for the Marketing Analytics page.

Deliberately a single non-streaming call to the same Hermes chat-completions
gateway the AI chat feature uses (`_hermes_request` in
`app/api/routes/ai_chat.py`) — not a tool-calling conversation via
`AIBusinessAgentService`, which needs a full `AIConversationState`/routing
setup this page doesn't have. This just asks for a short written take on
numbers the caller already computed, so it never touches the database
itself and never raises: any failure (no Hermes configured, network error,
malformed response) falls back to a short deterministic summary instead of
breaking the page.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import settings

_SYSTEM_PROMPT = (
    "Ты — маркетинговый аналитик внутри бизнес-приложения. Тебе присылают "
    "агрегированные данные по Instagram-постам, YouTube-видео и рекламе в "
    "Meta. Дай короткий, конкретный разбор на русском языке: 3-5 пунктов "
    "с выводами и практическими рекомендациями по контенту и продвижению. "
    "Пиши по делу, без вступлений и воды, опирайся только на переданные "
    "цифры и ничего не выдумывай. Если данных мало или они пустые — прямо "
    "скажи, каких данных не хватает и что нужно подключить/синхронизировать."
)


async def generate_marketing_commentary(payload: dict[str, Any]) -> str:
    if not settings.hermes_api_key or not settings.hermes_base_url:
        return _fallback_commentary(payload)
    try:
        url = f"{settings.hermes_base_url.rstrip('/')}/chat/completions"
        body = {
            "model": settings.hermes_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
            ],
        }
        headers = {"Authorization": f"Bearer {settings.hermes_api_key}"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, headers=headers, json=body)
        if response.status_code >= 400:
            return _fallback_commentary(payload)
        data = response.json()
        if not isinstance(data, dict):
            return _fallback_commentary(payload)
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return _fallback_commentary(payload)
        message = choices[0].get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and content.strip():
            return content.strip()
        return _fallback_commentary(payload)
    except (httpx.HTTPError, ValueError):
        return _fallback_commentary(payload)


def _fallback_commentary(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload, dict) else None
    summary = summary if isinstance(summary, dict) else {}
    lines: list[str] = []
    if summary.get("instagram_posts"):
        lines.append(
            f"Instagram: {summary['instagram_posts']} постов, суммарный охват "
            f"{summary.get('instagram_total_reach', 0)}, вовлечённость {summary.get('instagram_total_engagement', 0)}."
        )
    if summary.get("youtube_videos"):
        lines.append(
            f"YouTube: {summary['youtube_videos']} видео, суммарные просмотры {summary.get('youtube_total_views', 0)}."
        )
    if summary.get("meta_ad_spend"):
        lines.append(
            f"Реклама в Meta: потрачено {summary.get('meta_ad_spend', 0)}, показов {summary.get('meta_ad_impressions', 0)}."
        )
    if not lines:
        return (
            "AI-аналитика временно недоступна, а данных для сводки пока нет. "
            "Подключите Meta и YouTube в настройках, запустите синхронизацию — "
            "и здесь появится разбор постов, видео и рекламы."
        )
    lines.insert(0, "AI-комментарий временно недоступен, сводка по цифрам:")
    return "\n".join(f"— {line}" if index else line for index, line in enumerate(lines))
