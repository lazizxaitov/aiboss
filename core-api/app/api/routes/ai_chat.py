"""Streaming chat proxy for the local Hermes OpenAI-compatible server."""

from __future__ import annotations

import json
from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.ai_conversation import (
    AIConversationChannel,
    AIConversationService,
    AIConversationTargetChannel,
)
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.hermes_tools import HermesBusinessTools
from app.core.organization_context import OrganizationContextService

router = APIRouter(prefix="/ai")


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str | list[dict[str, object]]


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    conversation_id: str | None = None
    user_id: str | None = None
    telegram_chat_id: str | None = None
    organization_id: UUID | None = None
    period: str | None = None
    source_channel: AIConversationChannel = AIConversationChannel.WEB
    target_channel: AIConversationTargetChannel | None = None


def _event(payload: dict[str, str], event: str | None = None) -> str:
    prefix = f"event: {event}\n" if event else ""
    return f'{prefix}data: {json.dumps(payload, ensure_ascii=False)}\n\n'


def _tool_definitions() -> list[dict[str, object]]:
    common_org_period_parameters = {
        "type": "object",
        "properties": {
            "organization_id": {
                "type": ["string", "null"],
                "description": "Optional organization UUID. If omitted, the current AI Business OS organization context is used.",
            },
            "period": {
                "type": ["string", "null"],
                "description": (
                    "Optional period preset. If omitted, the current AI Business OS period context is used."
                ),
            },
        },
        "additionalProperties": False,
    }
    return [
        {
            "type": "function",
            "function": {
                "name": "get_business_summary",
                "description": "Return real business KPIs from Canonical V2 analytics.",
                "parameters": common_org_period_parameters,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_sales_summary",
                "description": "Return the real analytics sales summary from the existing analytics layer.",
                "parameters": common_org_period_parameters,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_top_products",
                "description": "Return top products from existing canonical/analytics data.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "organization_id": {
                            "type": ["string", "null"],
                            "description": "Optional organization UUID. If omitted, the current AI Business OS organization context is used.",
                        },
                        "period": {
                            "type": ["string", "null"],
                            "description": "Optional period preset. If omitted, the current AI Business OS period context is used.",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 50,
                            "description": "Maximum number of top products to return.",
                        },
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_organizations",
                "description": "Return available AI Business OS organizations without credentials or secrets.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_business_alerts",
                "description": "Return existing real business signals and important alerts used by the system.",
                "parameters": common_org_period_parameters,
            },
        },
    ]


def _normalize_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _normalize_period_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _system_prompt(context_service: OrganizationContextService) -> str:
    context = context_service.get_context()
    organization_ids = [str(item) for item in context.organization_context.organization_ids]
    organization_text = ", ".join(organization_ids) if organization_ids else "all"
    period_text = context.period_context.preset.value
    if context.period_context.date_from and context.period_context.date_to:
        period_text = (
            f"{period_text} ({context.period_context.date_from.isoformat()}.."
            f"{context.period_context.date_to.isoformat()})"
        )
    return (
        "You are Hermes for AI Business OS.\n"
        "Use ONLY the provided business data tools when the user asks about revenue, orders, sales, top products, "
        "business comparisons, organizations, or current attention.\n"
        "Do not request or reveal SQL, PostgreSQL, raw SmartUp payloads, terminal/file/system access, or secrets.\n"
        "If the user does not specify organization or period, rely on the current AI Business OS context.\n"
        "If the user asks for a file or a document, return it as a fenced code block in the form "
        "```file name=\"report.txt\" type=\"text/plain\"\n<content>\n``` so the UI can offer a download.\n"
        "Answer in the user's language and keep the answer grounded in tool results.\n"
        f"Current organization context: {organization_text}.\n"
        f"Current period context: {period_text}."
    )


def _message_dump(message: ChatMessage) -> dict[str, str]:
    return message.model_dump()


def _tool_message(tool_call_id: str, result: object) -> dict[str, str]:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(result, ensure_ascii=False, default=str),
    }


async def _hermes_request(
    *,
    messages: list[dict[str, object]],
    tools: list[dict[str, object]] | None,
    stream: bool,
    tool_choice: str | dict[str, object] | None = None,
) -> httpx.Response:
    url = f"{settings.hermes_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.hermes_api_key}"}
    body: dict[str, object] = {
        "model": settings.hermes_model,
        "messages": messages,
        "stream": stream,
    }
    if tools is not None:
        body["tools"] = tools
    if tool_choice is not None:
        body["tool_choice"] = tool_choice

    client = httpx.AsyncClient(timeout=None)
    response = await client.post(url, headers=headers, json=body)
    if not stream:
        await client.aclose()
    return response


def _extract_assistant_message(payload: dict[str, object]) -> dict[str, object] | None:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    choice = choices[0]
    if not isinstance(choice, dict):
        return None
    message = choice.get("message")
    if not isinstance(message, dict):
        return None
    return message


def _extract_stream_content(data: dict[str, object]) -> str | None:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    choice = choices[0]
    if not isinstance(choice, dict):
        return None
    delta = choice.get("delta")
    if not isinstance(delta, dict):
        return None
    content = delta.get("content")
    return content if isinstance(content, str) and content else None


def _parse_tool_calls(message: dict[str, object]) -> list[dict[str, object]]:
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list):
        return []
    parsed: list[dict[str, object]] = []
    for tool_call in tool_calls:
        if isinstance(tool_call, dict) and tool_call.get("id"):
            parsed.append(tool_call)
    return parsed


def _tool_arguments(tool_call: dict[str, object]) -> dict[str, object]:
    function = tool_call.get("function")
    if not isinstance(function, dict):
        return {}
    arguments = function.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    if not isinstance(arguments, str) or not arguments.strip():
        return {}
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _resolve_tool_result(
    tool_name: str,
    arguments: dict[str, object],
    tools: HermesBusinessTools,
) -> object:
    organization_id = _normalize_uuid(arguments.get("organization_id"))
    period = _normalize_period_value(arguments.get("period"))
    if tool_name == "get_business_summary":
        return tools.get_business_summary(organization_id=organization_id, period=period)
    if tool_name == "get_sales_summary":
        return tools.get_sales_summary(organization_id=organization_id, period=period)
    if tool_name == "get_top_products":
        limit = arguments.get("limit", 10)
        try:
            limit_value = int(limit)
        except (TypeError, ValueError):
            limit_value = 10
        return tools.get_top_products(
            organization_id=organization_id,
            period=period,
            limit=limit_value,
        )
    if tool_name == "get_organizations":
        return tools.get_organizations()
    if tool_name == "get_business_alerts":
        return tools.get_business_alerts(organization_id=organization_id, period=period)
    return {"error": f"Unknown tool: {tool_name}"}


def _message_text(content: str | list[dict[str, object]]) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text)
    return "\n".join(parts)


@router.post("/chat")
async def chat(
    request: ChatRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> StreamingResponse:
    """Proxy Hermes' OpenAI-compatible stream without exposing its credentials."""

    async def stream():
        conversation_service = AIConversationService(store)
        tools_service = HermesBusinessTools(store)
        conversation = conversation_service.resolve_or_create_conversation(
            source_channel=request.source_channel,
            user_id=request.user_id,
            telegram_chat_id=request.telegram_chat_id,
            organization_id=request.organization_id,
            period=request.period,
            conversation_id=request.conversation_id,
        )
        if request.organization_id is not None or request.period is not None:
            conversation = conversation_service.update_context(
                conversation,
                source_channel=request.source_channel,
                telegram_chat_id=request.telegram_chat_id,
                organization_id=request.organization_id,
                period=request.period,
                user_id=request.user_id,
            )
        incoming_messages = [_message_dump(message) for message in request.messages]
        last_user_message = next((message for message in reversed(request.messages) if message.role == "user"), None)
        resolved_target_channel = request.target_channel or conversation_service.infer_target_channel(
            _message_text(last_user_message.content) if last_user_message is not None else None,
        )
        conversation = conversation_service.sync_incoming_messages(
            conversation,
            incoming_messages,
            source_channel=request.source_channel,
            target_channel=resolved_target_channel,
        )
        messages: list[dict[str, object]] = [
            {"role": "system", "content": conversation_service.build_system_prompt(conversation)},
            *[{"role": message.role, "content": message.content} for message in conversation.messages],
        ]
        tools = _tool_definitions()
        assistant_text = ""
        try:
            for _ in range(3):
                response = await _hermes_request(
                    messages=messages,
                    tools=tools,
                    stream=False,
                    tool_choice="auto",
                )
                if response.status_code >= 400:
                    detail = response.text
                    yield _event({"message": detail or "Hermes вернул ошибку."}, "error")
                    return
                payload = response.json()
                assistant_message = _extract_assistant_message(payload)
                if assistant_message is None:
                    break
                tool_calls = _parse_tool_calls(assistant_message)
                if not tool_calls:
                    break
                messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_message.get("content") or "",
                        "tool_calls": tool_calls,
                    }
                )
                for tool_call in tool_calls:
                    function = tool_call.get("function")
                    if not isinstance(function, dict):
                        continue
                    tool_name = str(function.get("name") or "")
                    tool_result = _resolve_tool_result(
                        tool_name,
                        _tool_arguments(tool_call),
                        tools_service,
                    )
                    messages.append(_tool_message(str(tool_call.get("id")), tool_result))

            url = f"{settings.hermes_base_url.rstrip('/')}/chat/completions"
            headers = {"Authorization": f"Bearer {settings.hermes_api_key}"}
            body: dict[str, object] = {
                "model": settings.hermes_model,
                "messages": messages,
                "stream": True,
                "tool_choice": "none",
            }
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
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        content = _extract_stream_content(chunk)
                        if content:
                            assistant_text += content
                            yield _event({"content": content})
            if assistant_text:
                conversation_service.append_message(
                    conversation,
                    role="assistant",
                    content=assistant_text,
                    source_channel=request.source_channel,
                    target_channel=resolved_target_channel,
                )
            yield _event(
                {
                    "conversation_id": conversation.conversation_id,
                    "target_channel": resolved_target_channel.value if resolved_target_channel else "",
                },
                "done",
            )
        except httpx.HTTPError:
            yield _event({"message": "Не удалось подключиться к AI."}, "error")

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
