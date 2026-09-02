"""Telegram AI gateway backed by the shared AI conversation service."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from app.api.routes.auth import _session, _token_from_request
from app.core.ai_business_agent import AIBusinessAgentService
from app.core.ai_conversation import (
    AIConversationChannel,
    AIConversationService,
    AIConversationTargetChannel,
)
from app.core.ai_routing import AITaskRouter
from app.core.ai_shared_memory import SharedMemoryService
from app.core.analytics.widget_builder import WidgetBuilderService
from app.core.config import settings
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.hermes_model_registry import hermes_model_registry
from app.core.hermes_tools import HermesBusinessTools
from app.core.telegram_link import TelegramLinkService

router = APIRouter(prefix="/telegram")


class TelegramLinkRequest(BaseModel):
    telegram_chat_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)


class TelegramLinkResponse(BaseModel):
    connected: bool
    chats: list[str] = Field(default_factory=list)
    token: str | None = None
    deep_link: str | None = None
    instructions: str | None = None
    expires_at: str | None = None


class TelegramChatRequest(BaseModel):
    telegram_chat_id: str = Field(min_length=1)
    user_id: str | None = None
    conversation_id: str | None = None
    organization_id: UUID | None = None
    period: str | None = None
    message: str = Field(min_length=1)
    attachments: list[dict[str, object]] = Field(default_factory=list)
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
    artifacts: list[dict[str, object]] = Field(default_factory=list)


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


@router.post("/link", response_model=ConversationHistoryResponse)
def link_telegram_chat(
    request: TelegramLinkRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: str | None = Header(default=None),
) -> ConversationHistoryResponse:
    session = _require_owner(authorization, store)
    service = AIConversationService(store)
    # Keep the legacy endpoint for trusted internal callers, but never accept
    # an identity supplied by the client.
    service.link_telegram_chat(request.telegram_chat_id, session.login)
    conversation = service.resolve_or_create_conversation(
        source_channel=AIConversationChannel.TELEGRAM,
        user_id=session.login,
        telegram_chat_id=request.telegram_chat_id,
    )
    return ConversationHistoryResponse(
        conversation_id=conversation.conversation_id,
        user_id=conversation.user_id,
        organization_id=conversation.organization_id,
        period=conversation.period,
        messages=service.conversation_history(conversation),
        target_channel=conversation.target_channel,
    )


def _require_owner(authorization: str | None, store: CoreDataStore):
    session = _session(_token_from_request(None, authorization), store)
    if session is None:
        raise HTTPException(status_code=401, detail="Сессия недействительна")
    return session


@router.get("/link/status", response_model=TelegramLinkResponse)
def telegram_link_status(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: str | None = Header(default=None),
) -> TelegramLinkResponse:
    session = _require_owner(authorization, store)
    return TelegramLinkResponse(**TelegramLinkService(store).status(session.login))


@router.post("/link/create", response_model=TelegramLinkResponse)
def create_telegram_link(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: str | None = Header(default=None),
) -> TelegramLinkResponse:
    session = _require_owner(authorization, store)
    result = TelegramLinkService(store).create(session.login, bot_username=settings.telegram_bot_username)
    import logging
    logging.getLogger(__name__).info("TELEGRAM_LINK_CREATED identity=%s", session.login)
    return TelegramLinkResponse(
        connected=False,
        token=result["token"],
        deep_link=result.get("deep_link"),
        expires_at=result["expires_at"],
        instructions=f"Откройте Telegram и отправьте боту команду /start {result['token']}",
    )


@router.post("/link/disconnect", response_model=TelegramLinkResponse)
def disconnect_telegram(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: str | None = Header(default=None),
) -> TelegramLinkResponse:
    session = _require_owner(authorization, store)
    chats = AIConversationService(store).unlink_telegram_identity(session.login)
    import logging
    logging.getLogger(__name__).info("TELEGRAM_LINK_REVOKED identity=%s chats=%s", session.login, len(chats))
    return TelegramLinkResponse(connected=False, chats=[])


def complete_telegram_link(store: CoreDataStore, token: str, telegram_chat_id: str) -> bool:
    identity = TelegramLinkService(store).consume(token, telegram_chat_id)
    if identity is None:
        import logging
        logging.getLogger(__name__).info("TELEGRAM_LINK_FAILED reason=invalid_or_expired")
        return False
    service = AIConversationService(store)
    service.link_telegram_chat(telegram_chat_id, identity)
    service.resolve_or_create_conversation(
        source_channel=AIConversationChannel.TELEGRAM,
        user_id=identity,
        telegram_chat_id=telegram_chat_id,
    )
    import logging
    logging.getLogger(__name__).info("TELEGRAM_LINK_COMPLETED identity=%s", identity)
    return True




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


async def handle_telegram_chat(
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
    if command == "/new":
        linked_identity = service.get_telegram_identity(request.telegram_chat_id)
        if not linked_identity:
            return _command_result(
                conversation=conversation,
                service=service,
                text="Этот Telegram-чат ещё не подключён к AI Business OS.",
            )
        conversation = service.start_new_telegram_conversation(
            telegram_chat_id=request.telegram_chat_id,
            user_id=linked_identity,
            organization_id=request.organization_id,
            period=request.period,
        )
        return _command_result(
            conversation=conversation,
            service=service,
            text="Новый диалог начат. Подключение и выбранная модель сохранены.",
        )
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
    # Telegram conversations use the configured conversational role. The shared
    # Agent Core decides whether a capability is needed from the model context.
    task_type = "ai_chat"
    candidates = router.resolve_candidates(
        task_type,
        provider_id=explicit_provider if task_type == "ai_chat" else None,
        model_id=explicit_model if task_type == "ai_chat" else None,
    )
    if not candidates:
        raise HTTPException(status_code=409, detail="Выбранный provider/model сейчас недоступен.")
    resolved_target_channel = request.target_channel or service.infer_target_channel(user_text)
    message_content: str | list[dict[str, object]] = user_text
    if request.attachments:
        message_content = [{"type": "text", "text": user_text}]
        for attachment in request.attachments:
            if not isinstance(attachment, dict):
                continue
            multimodal_content = attachment.get("content")
            if isinstance(multimodal_content, dict) and multimodal_content.get("type") == "image_url":
                message_content.append(multimodal_content)
    conversation = service.append_message(
        conversation,
        role="user",
        content=message_content,
        source_channel=AIConversationChannel.TELEGRAM,
        target_channel=resolved_target_channel,
        metadata={"attachments": request.attachments} if request.attachments else None,
    )
    shared_memory = SharedMemoryService(store)
    shared_memory.remember(user_id, user_text, "telegram")
    try:
        result = await AIBusinessAgentService(store).run(
            conversation=conversation,
            user_text=user_text,
            source_channel=AIConversationChannel.TELEGRAM.value,
            task_type=task_type,
            router=router,
            tools_service=tools_service,
            widget_builder=WidgetBuilderService(store),
            memory_prompt=shared_memory.prompt_context(user_id),
            system_prompt=service.build_system_prompt(conversation),
            provider_id=explicit_provider if task_type == "ai_chat" else None,
            model_id=explicit_model if task_type == "ai_chat" else None,
            attachments=request.attachments,
        )
    except ValueError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    final_text = result.final_text
    conversation = service.append_message(
        conversation,
        role="assistant",
        content=final_text,
        source_channel=AIConversationChannel.TELEGRAM,
        target_channel=resolved_target_channel,
        metadata={
            "provider_id": result.runtime.get("provider_id"),
            "model_id": result.runtime.get("model_id"),
            "fallback_used": result.runtime.get("fallback_used", False),
            "agent_rounds": result.rounds,
            "tool_calls": result.tool_calls,
        },
    )
    telegram_message = _telegram_confirmation(final_text) if resolved_target_channel == AIConversationTargetChannel.REPLY_WEB else final_text
    return TelegramChatResponse(
        conversation_id=conversation.conversation_id,
        target_channel=resolved_target_channel,
        assistant_message=final_text,
        telegram_message=telegram_message,
        deliver_to_web=resolved_target_channel in {None, AIConversationTargetChannel.REPLY_WEB, AIConversationTargetChannel.REPLY_BOTH},
        provider_id=str(result.runtime.get("provider_id")),
        model_id=str(result.runtime.get("model_id")),
        fallback_used=bool(result.runtime.get("fallback_used", False)),
        artifacts=[],
    )


@router.post("/chat", response_model=TelegramChatResponse)
async def telegram_chat(
    request: TelegramChatRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> TelegramChatResponse:
    """HTTP adapter for the shared Telegram application service."""

    return await handle_telegram_chat(request, store)
