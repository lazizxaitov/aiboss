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
from app.core.ai_routing import AITaskRouter, TaskType
from app.core.hermes_model_registry import hermes_model_registry
from app.core.ai_conversation import (
    AIConversationChannel,
    AIConversationService,
    AIConversationTargetChannel,
)
from app.core.analytics.widget_builder import (
    WidgetBuilderDraft,
    WidgetBuilderService,
    WidgetBuilderUpdatePatch,
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
    task_type: TaskType = "ai_chat"
    provider_id: str | None = None
    model_id: str | None = None


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
        {
            "type": "function",
            "function": {
                "name": "delegate_ai_task",
                "description": "Delegate a task to the agent selected by the backend role router. Never choose a provider or model manually.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_type": {"type": "string", "enum": ["business_analytics", "system_action", "communications"]},
                        "instruction": {"type": "string"},
                        "context": {"type": "object"},
                    },
                    "required": ["task_type", "instruction"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_dashboard_widget",
                "description": "Create and persist a dashboard widget from a structured draft.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "draft": {"type": "object"},
                        "source_channel": {"type": "string", "default": "web"},
                        "organization_id": {"type": ["string", "null"]},
                        "period": {"type": ["string", "null"]},
                    },
                    "required": ["draft"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_dashboard_widget",
                "description": "Update an existing dashboard widget configuration.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "widget_id": {"type": ["string", "null"]},
                        "match_text": {"type": ["string", "null"]},
                        "patch": {
                            "type": "object",
                            "properties": {
                                "title": {"type": ["string", "null"]},
                                "widget_type": {"type": ["string", "null"]},
                                "metric": {"type": ["string", "null"]},
                                "period": {"type": ["string", "null"]},
                                "organization_ids": {
                                    "type": ["array", "null"],
                                    "items": {"type": "string"},
                                },
                                "organization_name": {"type": ["string", "null"]},
                                "filters": {"type": ["array", "null"]},
                                "grouping": {"type": ["string", "null"]},
                                "limit": {"type": ["integer", "null"]},
                                "size": {"type": ["string", "null"]},
                                "notes": {"type": ["array", "null"], "items": {"type": "string"}},
                            },
                            "additionalProperties": False,
                        },
                        "organization_id": {"type": ["string", "null"]},
                        "period": {"type": ["string", "null"]},
                    },
                    "required": ["patch"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_dashboard_widget",
                "description": "Delete an existing dashboard widget configuration.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "widget_id": {"type": ["string", "null"]},
                        "match_text": {"type": ["string", "null"]},
                    },
                    "additionalProperties": False,
                },
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
        "If the user wants to create, update, or delete a dashboard widget, use the widget builder tools.\n"
        "If the user does not specify organization or period, rely on the current AI Business OS context.\n"
        "If the user asks for a file or a document, return it as a fenced code block in the form "
        "```file name=\"report.txt\" type=\"text/plain\"\n<content>\n``` so the UI can offer a download.\n"
        "Answer in the user's language and keep the answer grounded in tool results.\n"
        f"Current organization context: {organization_text}.\n"
        f"Current period context: {period_text}."
    )


def _routing_context(router: AITaskRouter) -> str:
    assignments = router.get_config().roles
    lines = [
        "AI BOS ROLE ROUTING:",
        "You are the orchestrator. Infer task_type and use delegate_ai_task without selecting a provider or model.",
        "For system_action assigned to the current agent, use the existing AI BOS tools directly and do not delegate back to yourself.",
    ]
    for task_type in ("business_analytics", "system_action", "communications"):
        assignment = assignments.get(task_type)
        if assignment is None:
            continue
        lines.append(
            f"{task_type}: primary={assignment.primary_provider_id or 'not configured'} / "
            f"{assignment.primary_model_id or '-'}; fallback={assignment.fallback_provider_id or 'not configured'} / "
            f"{assignment.fallback_model_id or '-'}"
        )
    return "\n".join(lines)


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
    model: str | None = None,
) -> httpx.Response:
    url = f"{settings.hermes_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.hermes_api_key}"}
    body: dict[str, object] = {
        "model": model or settings.hermes_model,
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


async def _resolve_tool_result(
    tool_name: str,
    arguments: dict[str, object],
    tools: HermesBusinessTools,
    widget_builder: WidgetBuilderService,
    router: AITaskRouter,
) -> object:
    if tool_name == "delegate_ai_task":
        raw_task_type = str(arguments.get("task_type") or "")
        if raw_task_type not in {"business_analytics", "system_action", "communications"}:
            return {"status": "error", "message": "Unsupported task type."}
        runtime = router.resolve_runtime(raw_task_type)  # type: ignore[arg-type]
        if not runtime.get("provider_id"):
            return {"status": "error", "message": "No configured AI agent is available for this task."}
        if runtime.get("model_id"):
            response = await _hermes_request(
                messages=[
                    {"role": "system", "content": "Complete the delegated AI BOS task using only the supplied instruction and context."},
                    {"role": "user", "content": str(arguments.get("instruction") or "") + "\nContext: " + json.dumps(arguments.get("context") or {}, ensure_ascii=False)},
                ],
                tools=None,
                stream=False,
                model=str(runtime["model_id"]),
            )
            if response.status_code < 400:
                message = _extract_assistant_message(response.json()) or {}
                return {
                    "status": "completed",
                    "result": message.get("content") or "",
                    "provider_used": runtime["provider_name"],
                    "model_used": runtime["model_id"],
                    "fallback_used": runtime["fallback_used"],
                }
        return {"status": "error", "message": "Selected AI agent is unavailable.", "provider_used": runtime.get("provider_name"), "fallback_used": runtime.get("fallback_used")}
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
    if tool_name == "create_dashboard_widget":
        draft_payload = arguments.get("draft")
        if not isinstance(draft_payload, dict):
            return {"status": "not_found", "message": "Missing draft payload."}
        draft = WidgetBuilderDraft.model_validate(draft_payload)
        try:
            return widget_builder.create_dashboard_widget(
                draft,
                source_channel=str(arguments.get("source_channel") or "web"),
                organization_id=_normalize_uuid(arguments.get("organization_id")),
                period=_normalize_period_value(arguments.get("period")),
            ).model_dump(mode="json")
        except ValueError as error:
            return {"status": "error", "message": str(error)}
    if tool_name == "update_dashboard_widget":
        patch_payload = arguments.get("patch")
        if not isinstance(patch_payload, dict):
            return {"status": "not_found", "message": "Missing patch payload."}
        patch = WidgetBuilderUpdatePatch.model_validate(patch_payload)
        try:
            return widget_builder.update_dashboard_widget(
                widget_id=str(arguments.get("widget_id")) if arguments.get("widget_id") else None,
                match_text=str(arguments.get("match_text")) if arguments.get("match_text") else None,
                patch=patch,
                organization_id=_normalize_uuid(arguments.get("organization_id")),
                period=_normalize_period_value(arguments.get("period")),
            ).model_dump(mode="json")
        except ValueError as error:
            return {"status": "error", "message": str(error)}
    if tool_name == "delete_dashboard_widget":
        return widget_builder.delete_dashboard_widget(
            widget_id=str(arguments.get("widget_id")) if arguments.get("widget_id") else None,
            match_text=str(arguments.get("match_text")) if arguments.get("match_text") else None,
        ).model_dump(mode="json")
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
        widget_builder = WidgetBuilderService(store)
        await hermes_model_registry.get_providers()
        router = AITaskRouter(store)
        candidates = router.resolve_candidates(
            request.task_type,
            provider_id=request.provider_id,
            model_id=request.model_id,
        )
        if not candidates:
            yield _event({"message": "Для этой задачи нет доступного provider/model."}, "error")
            return
        routing_runtime = candidates[0]
        routed_model = str(routing_runtime["model_id"])
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
            {"role": "system", "content": _routing_context(router)},
            *[{"role": message.role, "content": message.content} for message in conversation.messages],
        ]
        tools = _tool_definitions()
        assistant_text = ""
        try:
            response = None
            for candidate in candidates:
                candidate_response = await _hermes_request(
                    messages=messages,
                    tools=tools,
                    stream=False,
                    tool_choice="auto",
                    model=str(candidate["model_id"]),
                )
                if candidate_response.status_code < 400:
                    routing_runtime = candidate
                    routed_model = str(candidate["model_id"])
                    response = candidate_response
                    break
            if response is None:
                yield _event({"message": "Не удалось выполнить задачу ни через основной, ни через резервный provider."}, "error")
                return
            for _ in range(3):
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
                    tool_result = await _resolve_tool_result(
                        tool_name,
                        _tool_arguments(tool_call),
                        tools_service,
                        widget_builder,
                        router,
                    )
                    messages.append(_tool_message(str(tool_call.get("id")), tool_result))
                response = await _hermes_request(
                    messages=messages,
                    tools=tools,
                    stream=False,
                    tool_choice="auto",
                    model=routed_model,
                )

            url = f"{settings.hermes_base_url.rstrip('/')}/chat/completions"
            headers = {"Authorization": f"Bearer {settings.hermes_api_key}"}
            body: dict[str, object] = {
                "model": routed_model or settings.hermes_model,
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
                    "provider_id": str(routing_runtime.get("provider_id") or ""),
                    "provider_name": str(routing_runtime.get("provider_name") or ""),
                        "model_id": str(routing_runtime.get("model_id") or ""),
                    "fallback_used": str(bool(routing_runtime.get("fallback_used"))).lower(),
                },
                "meta",
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
