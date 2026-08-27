"""Telegram AI gateway backed by the shared AI conversation service."""

from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.routes.ai_chat import _hermes_request, _resolve_tool_result, _tool_definitions
from app.core.ai_conversation import (
    AIConversationChannel,
    AIConversationService,
    AIConversationTargetChannel,
)
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.hermes_tools import HermesBusinessTools
from app.core.ai_routing import AITaskRouter
from app.core.ai_shared_memory import SharedMemoryService
from app.core.hermes_model_registry import hermes_model_registry
from app.core.ai_insight_presentation import AIInsightPresentationService
from app.core.analytics.widget_builder import WidgetBuilderService

router = APIRouter(prefix="/telegram")


class TelegramLinkRequest(BaseModel):
    telegram_chat_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)


class TelegramChatRequest(BaseModel):
    telegram_chat_id: str = Field(min_length=1)
    user_id: str | None = None
    conversation_id: str | None = None
    organization_id: UUID | None = None
    period: str | None = None
    message: str = Field(min_length=1)
    target_channel: AIConversationTargetChannel | None = None


class TelegramChatResponse(BaseModel):
    conversation_id: str
    target_channel: AIConversationTargetChannel | None = None
    assistant_message: str
    telegram_message: str
    deliver_to_web: bool = False


class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    user_id: str | None = None
    organization_id: UUID | None = None
    period: str | None = None
    messages: list[dict[str, object]]
    target_channel: AIConversationTargetChannel | None = None


def _message_text(text: str) -> str:
    return text.strip()


def _telegram_confirmation(text: str) -> str:
    trimmed = text.strip()
    if not trimmed:
        return "Ответ подготовлен."
    return f"Ответ подготовлен: {trimmed[:120]}{'…' if len(trimmed) > 120 else ''}"


def _telegram_runtime_context(router: AITaskRouter, store: CoreDataStore) -> str:
    assignments = router.get_config().roles
    latest = AIInsightPresentationService(store).latest()
    latest_text = "нет готового анализа"
    if latest and latest.status == "completed":
        latest_text = f"analysis_id={latest.analysis_id}, generated_at={latest.generated_at.isoformat()}"
    lines = ["AI BOS RUNTIME CONTEXT:", f"last_successful_business_analysis: {latest_text}"]
    for task_type in ("business_analytics", "system_action", "communications", "ai_chat"):
        assignment = assignments.get(task_type)
        if assignment:
            lines.append(
                f"{task_type}: primary={assignment.primary_provider_id or '-'} / {assignment.primary_model_id or '-'}; "
                f"fallback={assignment.fallback_provider_id or '-'} / {assignment.fallback_model_id or '-'}"
            )
    return "\n".join(lines)


@router.post("/link", response_model=ConversationHistoryResponse)
def link_telegram_chat(
    request: TelegramLinkRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> ConversationHistoryResponse:
    service = AIConversationService(store)
    shared_memory = SharedMemoryService(store)
    service.link_telegram_chat(request.telegram_chat_id, request.user_id)
    conversation = service.resolve_or_create_conversation(
        source_channel=AIConversationChannel.TELEGRAM,
        user_id=request.user_id,
        telegram_chat_id=request.telegram_chat_id,
    )
    if conversation.telegram_chat_id != request.telegram_chat_id:
        conversation = service.update_context(
            conversation,
            source_channel=AIConversationChannel.TELEGRAM,
            telegram_chat_id=request.telegram_chat_id,
            user_id=request.user_id,
        )
    return ConversationHistoryResponse(
        conversation_id=conversation.conversation_id,
        user_id=conversation.user_id,
        organization_id=conversation.organization_id,
        period=conversation.period,
        messages=service.conversation_history(conversation),
        target_channel=conversation.target_channel,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationHistoryResponse)
def get_conversation_history(
    conversation_id: str,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> ConversationHistoryResponse:
    service = AIConversationService(store)
    conversation = service.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationHistoryResponse(
        conversation_id=conversation.conversation_id,
        user_id=conversation.user_id,
        organization_id=conversation.organization_id,
        period=conversation.period,
        messages=service.conversation_history(conversation),
        target_channel=conversation.target_channel,
    )


@router.post("/chat", response_model=TelegramChatResponse)
async def telegram_chat(
    request: TelegramChatRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> TelegramChatResponse:
    service = AIConversationService(store)
    tools_service = HermesBusinessTools(store)
    await hermes_model_registry.get_providers()
    router = AITaskRouter(store)
    task_type = "ai_chat"
    lowered_text = request.message.lower()
    if "свеж" in lowered_text and "анализ" in lowered_text:
        task_type = "business_analytics"
    elif any(word in lowered_text for word in ("добавь виджет", "удали виджет", "измени виджет", "создай виджет")):
        task_type = "system_action"
    routing_candidates = router.resolve_candidates(task_type)
    routed_model = str(routing_candidates[0]["model_id"]) if routing_candidates else None
    selected_candidate_index = 0

    conversation = service.resolve_or_create_conversation(
        source_channel=AIConversationChannel.TELEGRAM,
        user_id=request.user_id,
        telegram_chat_id=request.telegram_chat_id,
        organization_id=request.organization_id,
        period=request.period,
        conversation_id=request.conversation_id,
    )
    if request.organization_id is not None or request.period is not None:
        conversation = service.update_context(
            conversation,
            source_channel=AIConversationChannel.TELEGRAM,
            telegram_chat_id=request.telegram_chat_id,
            organization_id=request.organization_id,
            period=request.period,
            user_id=request.user_id,
        )

    user_text = _message_text(request.message)
    resolved_target_channel = request.target_channel or service.infer_target_channel(user_text)
    conversation = service.append_message(
        conversation,
        role="user",
        content=user_text,
        source_channel=AIConversationChannel.TELEGRAM,
        target_channel=resolved_target_channel,
    )
    shared_memory.remember(conversation.user_id or request.user_id, user_text, "telegram")

    messages = [
        {"role": "system", "content": service.build_system_prompt(conversation)},
        {"role": "system", "content": shared_memory.prompt_context(conversation.user_id or request.user_id)},
        {"role": "system", "content": _telegram_runtime_context(router, store)},
        *[{"role": message.role, "content": message.content} for message in conversation.messages],
    ]
    tools = _tool_definitions()

    for attempt in range(3):
        response = await _hermes_request(
            messages=messages,
            tools=tools,
            stream=False,
            tool_choice="auto",
            model=routed_model,
        )
        if response.status_code >= 400:
            if selected_candidate_index + 1 < len(routing_candidates):
                selected_candidate_index += 1
                routed_model = str(routing_candidates[selected_candidate_index]["model_id"])
                continue
            raise HTTPException(status_code=response.status_code, detail=response.text or "Hermes вернул ошибку.")
        payload = response.json()
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            break
        choice = choices[0]
        if not isinstance(choice, dict):
            break
        assistant_message = choice.get("message")
        if not isinstance(assistant_message, dict):
            break
        tool_calls = assistant_message.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            final_text = str(assistant_message.get("content") or "")
            conversation = service.append_message(
                conversation,
                role="assistant",
                content=final_text,
                source_channel=AIConversationChannel.TELEGRAM,
                target_channel=resolved_target_channel,
            )
            telegram_message = (
                _telegram_confirmation(final_text)
                if resolved_target_channel == AIConversationTargetChannel.REPLY_WEB
                else final_text
            )
            return TelegramChatResponse(
                conversation_id=conversation.conversation_id,
                target_channel=resolved_target_channel,
                assistant_message=final_text,
                telegram_message=telegram_message,
                deliver_to_web=resolved_target_channel in {None, AIConversationTargetChannel.REPLY_WEB, AIConversationTargetChannel.REPLY_BOTH},
            )

        messages.append(
            {
                "role": "assistant",
                "content": assistant_message.get("content") or "",
                "tool_calls": tool_calls,
            },
        )
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function")
            if not isinstance(function, dict):
                continue
            tool_name = str(function.get("name") or "")
            arguments = function.get("arguments")
            if isinstance(arguments, dict):
                parsed_arguments = arguments
            elif isinstance(arguments, str) and arguments.strip():
                try:
                    parsed_arguments = json.loads(arguments)
                except Exception:  # noqa: BLE001
                    parsed_arguments = {}
            else:
                parsed_arguments = {}
            tool_result = await _resolve_tool_result(tool_name, parsed_arguments, tools_service, WidgetBuilderService(store), router)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(tool_call.get("id")),
                    "content": json.dumps(tool_result, ensure_ascii=False, default=str),
                },
            )

    raise HTTPException(status_code=502, detail="AI did not return a final answer.")
