"""Widget builder endpoints backed by Hermes and the shared conversation service."""

from __future__ import annotations

import json
from logging import getLogger
from time import monotonic
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.ai_business_agent import AIBusinessAgentService
from app.core.ai_conversation import AIConversationChannel, AIConversationService
from app.core.ai_routing import AITaskRouter
from app.core.analytics.widget_builder import (
    WidgetBuilderCreateRequest,
    WidgetBuilderChatRequest,
    WidgetBuilderChatResponse,
    WidgetBuilderDeleteRequest,
    WidgetBuilderConfirmRequest,
    WidgetBuilderConfirmResponse,
    WidgetBuilderConfig,
    WidgetBuilderContextResponse,
    WidgetBuilderDraft,
    WidgetBuilderPreview,
    WidgetBuilderService,
    WidgetBuilderMutationResponse,
    WidgetBuilderUpdateRequest,
)
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.hermes_tools import HermesBusinessTools

router = APIRouter(prefix="/dashboard/widget-builder")
logger = getLogger(__name__)


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
    run_id = str(uuid4())
    started_at = monotonic()
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
    widget_type = request.draft.widget_type.value if request.draft is not None else WidgetBuilderDraft().widget_type.value
    widget_goal = {
        "user_request": request.message,
        "requested_widget_type": widget_type,
        "selected_organization_id": str(request.organization_id) if request.organization_id else None,
        "selected_period": request.period,
        "current_draft": None if request.draft is None else request.draft.model_dump(mode="json"),
    }
    runtime = AITaskRouter(store).resolve_runtime("system_action")
    logger.info(
        "AI_WIDGET_RUN_START request_id=%s role=system_action provider=%s model=%s requested_widget_type=%s",
        run_id,
        runtime.get("provider_id"),
        runtime.get("model_id"),
        widget_type,
    )
    logger.info(
        "AI_WIDGET_INTENT_READY request_id=%s widget_type=%s organization_resolved=%s period_resolved=%s metric_resolved=%s",
        run_id,
        widget_type,
        bool(request.organization_id),
        bool(request.period),
        False,
    )
    system_prompt = (
        "You are constructing ONE AI Business OS dashboard widget requested by the user.\n"
        "The immutable task goal is USER_WIDGET_REQUEST below. Preserve it in every reasoning step.\n"
        "Use the shared read-only business.query capability only for the minimum evidence needed for this widget.\n"
        "Do not investigate unrelated domains, do not switch the selected widget type, and do not return a normal business analysis answer.\n"
        "Resolve explicit organization names using accessible AI Business OS context; backend scope remains authoritative.\n"
        "After sufficient evidence, return a final JSON object only, with this shape:\n"
        '{"assistant_message":"...","widget_draft":{...}|null,"clarification_required":false,"clarification_options":[]}\n'
        "The widget_draft must use the existing WidgetBuilderDraft schema and must match the requested metric, organization, period and widget type.\n"
        "If evidence is insufficient or the request is ambiguous, return widget_draft=null and clarification_required=true.\n"
        "Never invent data, columns, SQL results, organizations, or widget fields.\n"
        f"USER_WIDGET_REQUEST: {json.dumps(widget_goal, ensure_ascii=False, default=str)}\n"
        f"CURRENT BUSINESS OS CONTEXT: {json.dumps(context_payload, ensure_ascii=False, default=str)}\n"
    )
    agent_result = await AIBusinessAgentService(store).run(
        conversation=conversation,
        user_text=request.message,
        source_channel="web",
        task_type="system_action",
        router=AITaskRouter(store),
        tools_service=HermesBusinessTools(store),
        widget_builder=service,
        memory_prompt="",
        system_prompt=system_prompt,
        build_baseline=False,
        request_id=run_id,
        tool_call_budget=4,
        max_duration_seconds=45.0,
        ui_context={"widget_goal": widget_goal, "widget_context": context_payload},
    )
    assistant_message = agent_result.final_text
    logger.info(
        "AI_WIDGET_EVIDENCE_READY request_id=%s capability_attempts=%s executions=%s",
        run_id,
        agent_result.runtime.get("capability_attempts", 0),
        agent_result.runtime.get("capability_executions", 0),
    )
    logger.info(
        "AI_WIDGET_SYNTHESIS_START request_id=%s rounds=%s",
        run_id,
        agent_result.rounds,
    )
    parsed = _extract_json_object(assistant_message)
    if parsed is None:
        logger.info("AI_WIDGET_VALIDATION_FAILED request_id=%s field=widget_draft reason=missing_structured_result", run_id)
        raise HTTPException(status_code=422, detail="AI не вернул структурированную конфигурацию виджета.")

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
        if request.draft is not None and resolved_draft.widget_type != request.draft.widget_type:
            logger.info("AI_WIDGET_VALIDATION_FAILED request_id=%s field=widget_type reason=changed_by_model", run_id)
            raise HTTPException(status_code=422, detail="AI изменил выбранный тип виджета.")
        validation_config = WidgetBuilderConfig(
            **resolved_draft.model_dump(),
            preview=preview,
            source_channel="web",
        )
        validation_errors = service.validate_config(validation_config)
        if validation_errors:
            logger.info(
                "AI_WIDGET_VALIDATION_FAILED request_id=%s field=config reason=%s",
                run_id,
                ",".join(validation_errors),
            )
            raise HTTPException(
                status_code=422,
                detail=f"Некорректная конфигурация виджета: {', '.join(validation_errors)}",
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

    result = WidgetBuilderChatResponse(
        conversation_id=conversation.conversation_id,
        assistant_message=assistant_message,
        widget_draft=draft,
        clarification_required=clarification_required,
        clarification_options=clarification_options,
        preview=preview,
    )
    logger.info(
        "AI_WIDGET_RUN_DONE request_id=%s rounds=%s capability_attempts=%s executions=%s elapsed_ms=%.2f status=%s",
        run_id,
        agent_result.rounds,
        agent_result.runtime.get("capability_attempts", 0),
        agent_result.runtime.get("capability_executions", 0),
        (monotonic() - started_at) * 1000,
        "clarification" if clarification_required else "ready",
    )
    return result


@router.post("/confirm", response_model=WidgetBuilderConfirmResponse)
def confirm_widget_builder(
    request: WidgetBuilderConfirmRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> WidgetBuilderConfirmResponse:
    service = WidgetBuilderService(store)
    try:
        config, preview = service.save_confirmed_widget(
            request.draft,
            source_channel=request.source_channel,
            organization_id=request.draft.organization_ids[0] if request.draft.organization_ids else None,
            period=request.draft.period,
        )
    except ValueError as error:
        raise _handle_value_error(error) from error
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
