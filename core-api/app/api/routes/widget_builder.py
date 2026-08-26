"""Widget builder endpoints backed by Hermes and the shared conversation service."""

from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.routes.ai_chat import _extract_assistant_message, _hermes_request
from app.core.ai_conversation import AIConversationChannel, AIConversationService
from app.core.analytics.widget_builder import (
    WidgetBuilderCreateRequest,
    WidgetBuilderChatRequest,
    WidgetBuilderChatResponse,
    WidgetBuilderDeleteRequest,
    WidgetBuilderConfirmRequest,
    WidgetBuilderConfirmResponse,
    WidgetBuilderContextResponse,
    WidgetBuilderDraft,
    WidgetBuilderPreview,
    WidgetBuilderService,
    WidgetBuilderMutationResponse,
    WidgetBuilderUpdateRequest,
)
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store

router = APIRouter(prefix="/dashboard/widget-builder")


def _extract_json_object(text: str) -> dict[str, object] | None:
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if "\n" in stripped:
            stripped = stripped.split("\n", 1)[1]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _fallback_message(draft: WidgetBuilderDraft | None) -> str:
    if draft is None:
        return "Опиши, какой виджет ты хочешь видеть, и я соберу draft."
    return f"Я обновил draft для виджета «{draft.title or 'Widget'}»."


def _handle_value_error(error: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(error))


@router.get("/context", response_model=WidgetBuilderContextResponse)
def get_widget_builder_context(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[UUID | None, Query()] = None,
    period: Annotated[str | None, Query()] = None,
) -> WidgetBuilderContextResponse:
    return WidgetBuilderService(store).get_context_payload(organization_id=organization_id, period=period)


@router.post("/chat", response_model=WidgetBuilderChatResponse)
async def widget_builder_chat(
    request: WidgetBuilderChatRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> WidgetBuilderChatResponse:
    service = WidgetBuilderService(store)
    conversation_service = AIConversationService(store)
    conversation = conversation_service.resolve_or_create_conversation(
        source_channel=AIConversationChannel.WEB,
        user_id=request.user_id,
        organization_id=request.organization_id,
        period=request.period,
        conversation_id=request.conversation_id,
    )
    conversation = conversation_service.append_message(
        conversation,
        role="user",
        content=request.message,
        source_channel=AIConversationChannel.WEB,
    )

    context_payload = service.get_context_payload(
        organization_id=request.organization_id,
        period=request.period,
    ).model_dump(mode="json")
    system_prompt = (
        "You are Hermes AI Widget Builder for AI Business OS.\n"
        "Return STRICT JSON only, without markdown fences or extra commentary.\n"
        "Schema:\n"
        "{"
        '"assistant_message": string, '
        '"widget_draft": object|null, '
        '"clarification_required": boolean, '
        '"clarification_options": array<string>'
        "}\n"
        "Rules:\n"
        "- Use only real AI Business OS data concepts.\n"
        "- Do not invent SQL, raw SmartUp payloads, shell access, or fake fields.\n"
        "- Update the draft when the user provides new requirements.\n"
        "- If the intent is ambiguous, set clarification_required=true and provide concise options.\n"
        "- Keep widget sizes fixed.\n"
        "- Prefer current organization and period context when the user does not specify them.\n"
        f"Current context: {json.dumps(context_payload, ensure_ascii=False, default=str)}\n"
        f"Current draft: {json.dumps(None if request.draft is None else request.draft.model_dump(mode='json'), ensure_ascii=False, default=str)}\n"
    )

    hermes_messages = [
        {"role": "system", "content": system_prompt},
        *[
            {"role": message.role, "content": message.content}
            for message in conversation.messages
        ],
    ]
    response = await _hermes_request(messages=hermes_messages, tools=None, stream=False)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text or "Hermes вернул ошибку.")

    payload = response.json()
    assistant_message = ""
    assistant_message_payload = _extract_assistant_message(payload)
    if isinstance(assistant_message_payload, dict):
        assistant_message = str(assistant_message_payload.get("content") or "")
    parsed = _extract_json_object(assistant_message)

    draft: WidgetBuilderDraft | None = request.draft
    clarification_required = False
    clarification_options: list[str] = []
    preview: WidgetBuilderPreview | None = None

    if parsed is not None:
        raw_draft = parsed.get("widget_draft")
        if isinstance(raw_draft, dict):
            try:
                draft = WidgetBuilderDraft.model_validate(raw_draft)
            except Exception:  # noqa: BLE001
                draft = request.draft
        clarification_required = bool(parsed.get("clarification_required", False))
        options = parsed.get("clarification_options", [])
        if isinstance(options, list):
            clarification_options = [str(item) for item in options if str(item).strip()]
        if isinstance(parsed.get("assistant_message"), str) and parsed["assistant_message"].strip():
            assistant_message = str(parsed["assistant_message"]).strip()

    if draft is not None:
        resolved_draft, preview, resolved_clarification_required, resolved_options = service.resolve_draft(
            draft,
            organization_id=request.organization_id,
            period=request.period,
        )
        draft = resolved_draft
        clarification_required = clarification_required or resolved_clarification_required
        clarification_options = list(dict.fromkeys([*clarification_options, *resolved_options]))
    else:
        assistant_message = assistant_message or _fallback_message(None)

    if not assistant_message.strip():
        assistant_message = _fallback_message(draft)

    conversation_service.append_message(
        conversation,
        role="assistant",
        content=assistant_message,
        source_channel=AIConversationChannel.WEB,
        metadata={
            "mode": "widget_builder",
            "widget_draft": None if draft is None else draft.model_dump(mode="json"),
            "clarification_required": clarification_required,
            "clarification_options": clarification_options,
        },
    )

    return WidgetBuilderChatResponse(
        conversation_id=conversation.conversation_id,
        assistant_message=assistant_message,
        widget_draft=draft,
        clarification_required=clarification_required,
        clarification_options=clarification_options,
        preview=preview,
    )


@router.post("/confirm", response_model=WidgetBuilderConfirmResponse)
def confirm_widget_builder(
    request: WidgetBuilderConfirmRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> WidgetBuilderConfirmResponse:
    service = WidgetBuilderService(store)
    config, preview = service.save_confirmed_widget(
        request.draft,
        source_channel=request.source_channel,
        organization_id=request.draft.organization_ids[0] if request.draft.organization_ids else None,
        period=request.draft.period,
    )
    return WidgetBuilderConfirmResponse(
        config=config,
        preview=preview,
        dashboard_widget=service.build_manifest_widget(config).model_dump(mode="json"),
    )


@router.post("/create", response_model=WidgetBuilderMutationResponse)
def create_widget(
    request: WidgetBuilderCreateRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> WidgetBuilderMutationResponse:
    service = WidgetBuilderService(store)
    try:
        return service.create_dashboard_widget(
            request.draft,
            source_channel=request.source_channel,
            organization_id=request.organization_id,
            period=request.period,
        )
    except ValueError as error:
        raise _handle_value_error(error) from error


@router.patch("/update", response_model=WidgetBuilderMutationResponse)
def update_widget(
    request: WidgetBuilderUpdateRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> WidgetBuilderMutationResponse:
    service = WidgetBuilderService(store)
    try:
        return service.update_dashboard_widget(
            widget_id=request.widget_id,
            match_text=request.match_text,
            patch=request.patch,
            organization_id=request.organization_id,
            period=request.period,
        )
    except ValueError as error:
        raise _handle_value_error(error) from error


@router.delete("/delete", response_model=WidgetBuilderMutationResponse)
def delete_widget(
    request: WidgetBuilderDeleteRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> WidgetBuilderMutationResponse:
    service = WidgetBuilderService(store)
    return service.delete_dashboard_widget(
        widget_id=request.widget_id,
        match_text=request.match_text,
    )
