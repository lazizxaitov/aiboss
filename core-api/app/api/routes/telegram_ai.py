"""Telegram AI gateway backed by the shared AI conversation service."""

from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from app.api.routes.ai_chat import _hermes_request, _resolve_tool_result, _resolved_entities_from_search, _tool_definitions
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
    provider_id: str | None = Field(default=None, validation_alias=AliasChoices("provider_id", "provider"))
    model_id: str | None = Field(default=None, validation_alias=AliasChoices("model_id", "model"))


class TelegramOption(BaseModel):
    label: str
    command: str


class TelegramChatResponse(BaseModel):
    conversation_id: str
    target_channel: AIConversationTargetChannel | None = None
    assistant_message: str
    telegram_message: str
    deliver_to_web: bool = False
    provider_id: str | None = None
    model_id: str | None = None
    fallback_used: bool = False
    options: list[TelegramOption] = Field(default_factory=list)


class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    user_id: str | None = None
    organization_id: UUID | None = None
    period: str | None = None
    messages: list[dict[str, object]]
    target_channel: AIConversationTargetChannel | None = None


def _message_text(text: str) -> str:
    return text.strip()


def _provider_label(provider) -> str:
    provider_id = str(provider.id).lower()
    if provider_id == "custom":
        return "Local / Custom"
    if provider_id == "openai-codex":
        return "OpenAI Codex"
    if provider_id in {"anthropic", "claude"}:
        return "Anthropic / Claude"
    return provider.name


def _command_parts(text: str) -> tuple[str, str]:
    parts = text.strip().split(maxsplit=1)
    return parts[0].lower(), parts[1].strip() if len(parts) > 1 else ""


def _provider_options(providers) -> list[TelegramOption]:
    options: list[TelegramOption] = []
    seen: set[str] = set()
    for provider in providers:
        provider_id = str(provider.id)
        if provider_id.lower() == "hermes" or provider_id in seen:
            continue
        if provider.status != "available" or not any(model.available for model in provider.models):
            continue
        seen.add(provider_id)
        options.append(TelegramOption(label=_provider_label(provider), command=f"/ai {provider_id}"))
    return options


def _model_options(provider) -> list[TelegramOption]:
    return [
        TelegramOption(label=model.name, command=f"/model {model.id}")
        for model in provider.models
        if model.available
    ]


def _find_provider(providers, value: str):
    normalized = value.strip().lower()
    for provider in providers:
        if str(provider.id).lower() == normalized or str(provider.name).lower() == normalized:
            return provider
    return None


def _find_model(provider, value: str):
    normalized = value.strip().lower()
    for model in provider.models:
        if model.available and (model.id.lower() == normalized or model.name.lower() == normalized):
            return model
    return None


def _command_result(
    *,
    conversation,
    service: AIConversationService,
    text: str,
    options: list[TelegramOption] | None = None,
    provider_id: str | None = None,
    model_id: str | None = None,
    fallback_used: bool = False,
) -> TelegramChatResponse:
    return TelegramChatResponse(
        conversation_id=conversation.conversation_id,
        target_channel=None,
        assistant_message=text,
        telegram_message=text,
        deliver_to_web=False,
        provider_id=provider_id,
        model_id=model_id,
        fallback_used=fallback_used,
        options=options or [],
    )


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
    router = AITaskRouter(store)
    providers = await hermes_model_registry.get_providers(refresh=True)
    user_id = request.user_id or service.resolve_identity(telegram_chat_id=request.telegram_chat_id)
    conversation = service.resolve_or_create_conversation(
        source_channel=AIConversationChannel.TELEGRAM,
        user_id=user_id,
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
            user_id=user_id,
        )

    user_text = _message_text(request.message)
    command, argument = _command_parts(user_text)
    if command in {"/ai", "/model", "/current", "/organization", "/period"}:
        if command == "/ai":
            if not argument:
                return _command_result(
                    conversation=conversation,
                    service=service,
                    text="Выберите тип ИИ:",
                    options=_provider_options(providers),
                )
            provider = _find_provider(providers, argument)
            if provider is None or provider.id.lower() == "hermes" or provider.status != "available":
                return _command_result(conversation=conversation, service=service, text="Такой провайдер недоступен.", options=_provider_options(providers))
            model = next((item for item in provider.models if item.available), None)
            if model is None:
                return _command_result(conversation=conversation, service=service, text="У этого провайдера нет доступных моделей.")
            service.set_telegram_target(request.telegram_chat_id, provider_id=provider.id, model_id=model.id)
            return _command_result(
                conversation=conversation,
                service=service,
                text=f"Выбран провайдер: {_provider_label(provider)}. Модель: {model.name}",
                options=_model_options(provider),
                provider_id=provider.id,
                model_id=model.id,
            )
        if command == "/model":
            selected = service.get_telegram_target(request.telegram_chat_id)
            provider = _find_provider(providers, selected.get("provider_id", "")) if selected else None
            if provider is None:
                candidates = router.resolve_candidates("ai_chat")
                provider_id = str(candidates[0]["provider_id"]) if candidates else ""
                provider = _find_provider(providers, provider_id)
            if provider is None:
                return _command_result(conversation=conversation, service=service, text="Нет доступного провайдера для выбора модели.")
            if not argument:
                return _command_result(conversation=conversation, service=service, text=f"Модели {_provider_label(provider)}:", options=_model_options(provider), provider_id=provider.id)
            model = _find_model(provider, argument)
            if model is None:
                return _command_result(conversation=conversation, service=service, text="Такая модель недоступна.", options=_model_options(provider), provider_id=provider.id)
            service.set_telegram_target(request.telegram_chat_id, provider_id=provider.id, model_id=model.id)
            return _command_result(conversation=conversation, service=service, text=f"Выбрана модель: {model.name}", provider_id=provider.id, model_id=model.id)
        if command == "/current":
            selected = service.get_telegram_target(request.telegram_chat_id)
            candidates = router.resolve_candidates("ai_chat")
            selected_target = (
                router.resolve_candidates(
                    "ai_chat",
                    provider_id=selected.get("provider_id") if selected else None,
                    model_id=selected.get("model_id") if selected else None,
                )
                if selected
                else []
            )
            runtime = (selected_target[0] if selected_target else (candidates[0] if candidates else {}))
            provider = _find_provider(providers, str(runtime.get("provider_id") or ""))
            provider_name = _provider_label(provider) if provider else "не выбран"
            model_name = str(runtime.get("model_id") or "не выбрана")
            return _command_result(
                conversation=conversation,
                service=service,
                text=(f"Провайдер: {provider_name}\nМодель: {model_name}\n"
                      f"Организация: {conversation.organization_id or 'все'}\nПериод: {conversation.period or 'текущий контекст'}"),
                provider_id=str(runtime.get("provider_id") or "") or None,
                model_id=str(runtime.get("model_id") or "") or None,
                fallback_used=bool(runtime.get("fallback_used", False)),
            )
        if command == "/organization":
            organization_result = tools_service.get_organizations()
            organizations = organization_result.get("items", [])
            if not argument:
                options = [TelegramOption(label=str(item.get("name") or item.get("organization_id")), command=f"/organization {item.get('organization_id')}") for item in organizations]
                return _command_result(conversation=conversation, service=service, text="Выберите организацию:", options=options)
            selected = next((item for item in organizations if str(item.get("organization_id")) == argument or str(item.get("name", "")).lower() == argument.lower()), None)
            if selected is None:
                return _command_result(conversation=conversation, service=service, text="Организация не найдена.")
            conversation = service.update_context(conversation, organization_id=UUID(str(selected["organization_id"])), source_channel=AIConversationChannel.TELEGRAM, telegram_chat_id=request.telegram_chat_id, user_id=user_id)
            return _command_result(conversation=conversation, service=service, text=f"Организация выбрана: {selected.get('name')}")
        period_values = {"сегодня": "today", "today": "today", "вчера": "yesterday", "yesterday": "yesterday", "эта неделя": "this_week", "this_week": "this_week", "прошлая неделя": "last_week", "last_week": "last_week", "этот месяц": "this_month", "this_month": "this_month", "прошлый месяц": "last_month", "last_month": "last_month"}
        if not argument:
            return _command_result(conversation=conversation, service=service, text="Выберите период:", options=[TelegramOption(label=label, command=f"/period {value}") for label, value in (("Сегодня", "today"), ("Вчера", "yesterday"), ("Эта неделя", "this_week"), ("Прошлая неделя", "last_week"), ("Этот месяц", "this_month"), ("Прошлый месяц", "last_month"))])
        period = period_values.get(argument.lower())
        if period is None:
            return _command_result(conversation=conversation, service=service, text="Неизвестный период. Используйте /period для списка.")
        conversation = service.update_context(conversation, period=period, source_channel=AIConversationChannel.TELEGRAM, telegram_chat_id=request.telegram_chat_id, user_id=user_id)
        return _command_result(conversation=conversation, service=service, text=f"Период выбран: {period}")

    target = service.get_telegram_target(request.telegram_chat_id)
    explicit_provider = request.provider_id or (target or {}).get("provider_id")
    explicit_model = request.model_id or (target or {}).get("model_id")
    lowered_text = user_text.lower()
    task_type = "ai_chat"
    if "свеж" in lowered_text and "анализ" in lowered_text:
        task_type = "business_analytics"
    elif any(word in lowered_text for word in ("добавь виджет", "удали виджет", "измени виджет", "создай виджет")):
        task_type = "system_action"
    candidates = router.resolve_candidates(
        task_type,
        provider_id=explicit_provider if task_type == "ai_chat" else None,
        model_id=explicit_model if task_type == "ai_chat" else None,
    )
    if not candidates:
        raise HTTPException(status_code=409, detail="Выбранный provider/model сейчас недоступен.")
    resolved_target_channel = request.target_channel or service.infer_target_channel(user_text)
    conversation = service.append_message(conversation, role="user", content=user_text, source_channel=AIConversationChannel.TELEGRAM, target_channel=resolved_target_channel)
    shared_memory = SharedMemoryService(store)
    shared_memory.remember(user_id, user_text, "telegram")
    try:
        business_context = tools_service.build_business_context(user_text, organization_id=conversation.organization_id, period=conversation.period)
    except Exception:  # noqa: BLE001 - tool calls remain authoritative and can report unavailable data
        business_context = {"source": "AI Business OS canonical/analytics services", "authoritative": True, "unavailable": True, "message": "Не удалось получить запрошенный набор бизнес-данных."}
    messages: list[dict[str, object]] = [
        {"role": "system", "content": service.build_system_prompt(conversation)},
        {"role": "system", "content": shared_memory.prompt_context(user_id)},
        {"role": "system", "content": _telegram_runtime_context(router, store)},
        {"role": "system", "content": "AUTHORITATIVE AI BUSINESS OS CONTEXT:\n" + json.dumps(business_context, ensure_ascii=False, default=str)},
        *[{"role": message.role, "content": message.content} for message in conversation.messages],
    ]
    tools = _tool_definitions()
    widget_builder = WidgetBuilderService(store)
    runtime = candidates[0]
    response = None
    for candidate in candidates:
        candidate_response = await _hermes_request(messages=messages, tools=tools, stream=False, tool_choice="auto", model=str(candidate["model_id"]), provider=str(candidate["provider_id"]))
        if candidate_response.status_code < 400:
            runtime, response = candidate, candidate_response
            break
    if response is None:
        raise HTTPException(status_code=502, detail="Не удалось выполнить запрос через доступные provider/model.")
    for _ in range(6):
        payload = response.json()
        choices = payload.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
        assistant_message = choice.get("message") if choice else None
        if not isinstance(assistant_message, dict):
            break
        tool_calls = assistant_message.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            final_text = str(assistant_message.get("content") or "")
            conversation = service.append_message(conversation, role="assistant", content=final_text, source_channel=AIConversationChannel.TELEGRAM, target_channel=resolved_target_channel, metadata={"provider_id": runtime.get("provider_id"), "model_id": runtime.get("model_id"), "fallback_used": runtime.get("fallback_used", False)})
            telegram_message = _telegram_confirmation(final_text) if resolved_target_channel == AIConversationTargetChannel.REPLY_WEB else final_text
            return TelegramChatResponse(conversation_id=conversation.conversation_id, target_channel=resolved_target_channel, assistant_message=final_text, telegram_message=telegram_message, deliver_to_web=resolved_target_channel in {None, AIConversationTargetChannel.REPLY_WEB, AIConversationTargetChannel.REPLY_BOTH}, provider_id=str(runtime.get("provider_id")), model_id=str(runtime.get("model_id")), fallback_used=bool(runtime.get("fallback_used", False)))
        messages.append({"role": "assistant", "content": assistant_message.get("content") or "", "tool_calls": tool_calls})
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict) or not isinstance(tool_call.get("function"), dict):
                continue
            function = tool_call["function"]
            arguments = function.get("arguments")
            try:
                parsed_arguments = arguments if isinstance(arguments, dict) else json.loads(arguments or "{}")
            except (TypeError, ValueError):
                parsed_arguments = {}
            tool_result = await _resolve_tool_result(str(function.get("name") or ""), parsed_arguments, tools_service, widget_builder, router)
            if str(function.get("name")) == "search_entities":
                service.remember_entities(conversation, _resolved_entities_from_search(tool_result, parsed_arguments))
            messages.append({"role": "tool", "tool_call_id": str(tool_call.get("id")), "content": json.dumps(tool_result, ensure_ascii=False, default=str)})
        response = await _hermes_request(messages=messages, tools=tools, stream=False, tool_choice="auto", model=str(runtime["model_id"]), provider=str(runtime["provider_id"]))
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text or "Hermes вернул ошибку.")
    raise HTTPException(status_code=502, detail="AI не вернул финальный ответ.")
