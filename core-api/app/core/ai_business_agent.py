"""Reusable multi-step business AI orchestration for all supported channels."""

from __future__ import annotations

import json
from dataclasses import dataclass
from logging import getLogger
from uuid import uuid4

from app.core.ai_conversation import AIConversationService, AIConversationState
from app.core.ai_routing import AITaskRouter, TaskType
from app.core.analytics.widget_builder import WidgetBuilderService
from app.core.data_layer.contracts import CoreDataStore
from app.core.hermes_tools import HermesBusinessTools

logger = getLogger(__name__)
logger.setLevel("INFO")

MAX_ROUNDS = 12
MAX_TOOL_CALLS = 12


@dataclass(slots=True)
class AIBusinessAgentResult:
    """Final result and metadata produced by the shared agent loop."""

    final_text: str
    messages: list[dict[str, object]]
    runtime: dict[str, object]
    rounds: int
    tool_calls: int


class AIBusinessAgentService:
    """Run provider-independent, read-only AI Business OS tool orchestration."""

    def __init__(self, store: CoreDataStore) -> None:
        self.store = store

    async def run(
        self,
        *,
        conversation: AIConversationState,
        user_text: str,
        source_channel: str,
        task_type: TaskType,
        router: AITaskRouter,
        tools_service: HermesBusinessTools,
        widget_builder: WidgetBuilderService,
        memory_prompt: str,
        system_prompt: str,
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> AIBusinessAgentResult:
        """Resolve a target, execute tools, and stop at the first final answer."""

        # Imports are local to keep the route-level tool contract in one place and
        # avoid making the HTTP route a second implementation of the tool layer.
        from app.api.routes.ai_chat import (
            _extract_assistant_message,
            _hermes_request,
            _parse_tool_calls,
            _resolve_tool_result,
            _resolved_entities_from_search,
            _routing_context,
            _tool_arguments,
            _tool_definitions,
        )

        request_id = str(uuid4())
        candidates = router.resolve_candidates(
            task_type,
            provider_id=provider_id,
            model_id=model_id,
        )
        if not candidates:
            raise ValueError("Для этой задачи нет доступного provider/model.")
        runtime = candidates[0]
        baseline = None
        if _looks_business_related(user_text):
            try:
                baseline = tools_service.build_business_context(
                    user_text,
                    organization_id=conversation.organization_id,
                    period=conversation.period,
                )
            except Exception:  # noqa: BLE001 - tools remain the authoritative fallback
                baseline = {
                    "source": "AI Business OS canonical/analytics services",
                    "authoritative": True,
                    "unavailable": True,
                    "message": "Базовый контекст временно недоступен; проверьте нужные business tools.",
                }
        messages: list[dict[str, object]] = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": memory_prompt},
            {"role": "system", "content": _routing_context(router)},
            *[{"role": message.role, "content": message.content} for message in conversation.messages],
        ]
        if baseline is not None:
            messages.insert(
                3,
                {
                    "role": "system",
                    "content": "AUTHORITATIVE AI BUSINESS OS BASELINE CONTEXT:\n"
                    + json.dumps(baseline, ensure_ascii=False, default=str),
                },
            )
            messages.insert(
                3,
                {
                    "role": "system",
                    "content": (
                        "Business tools listed in this request ARE connected and available. "
                        "Never tell the user that a tool is not connected merely because you have not called it yet."
                    ),
                },
            )
        tools = _tool_definitions()
        result_cache: dict[str, object] = {}
        total_tool_calls = 0
        rounds = 0
        evidence_retry_used = False
        business_request = _looks_business_related(user_text)
        tool_choice_for_round = "auto"
        logger.info(
            "AI_AGENT_START request_id=%s provider=%s model=%s organization=%s period=%s source=%s",
            request_id,
            runtime.get("provider_id"),
            runtime.get("model_id"),
            conversation.organization_id,
            conversation.period,
            source_channel,
        )

        response = None
        for candidate in candidates:
            candidate_response = await _hermes_request(
                messages=messages,
                tools=tools,
                stream=False,
                tool_choice="auto",
                model=str(candidate["model_id"]),
                provider=str(candidate["provider_id"]),
            )
            if candidate_response.status_code < 400:
                runtime = candidate
                response = candidate_response
                break
        if response is None:
            raise ValueError("Не удалось выполнить запрос через доступные provider/model.")

        for rounds in range(1, MAX_ROUNDS + 1):
            logger.info(
                "AI_AGENT_ROUND request_id=%s round=%s tool_calls=%s tool_choice=%s",
                request_id,
                rounds,
                total_tool_calls,
                tool_choice_for_round,
            )
            assistant_message = _extract_assistant_message(response.json())
            if assistant_message is None:
                raise ValueError("AI не вернул корректный ответ.")
            tool_calls = _parse_tool_calls(assistant_message)
            if not tool_calls:
                final_text = str(assistant_message.get("content") or "")
                if business_request and rounds == 1 and not evidence_retry_used:
                    evidence_retry_used = True
                    messages.append({"role": "assistant", "content": final_text})
                    messages.append({
                        "role": "system",
                        "content": (
                            "The previous response attempted to answer without inspecting AI Business OS tools. "
                            "This is a factual business-data request. Re-evaluate the user's request, determine "
                            "which available tool or tools can provide the required evidence, and call them now. "
                            "Do not answer that data is unavailable until the relevant tools have been checked."
                        ),
                    })
                    logger.info(
                        "AI_AGENT_NO_TOOL_RETRY request_id=%s round=%s provider=%s model=%s",
                        request_id,
                        rounds,
                        runtime.get("provider_id"),
                        runtime.get("model_id"),
                    )
                    tool_choice_for_round = "required"
                    response = await _hermes_request(
                        messages=messages,
                        tools=tools,
                        stream=False,
                        tool_choice=tool_choice_for_round,
                        model=str(runtime["model_id"]),
                        provider=str(runtime["provider_id"]),
                    )
                    if response.status_code >= 400:
                        raise ValueError("AI provider вернул ошибку при повторной проверке business tools.")
                    continue
                if business_request and evidence_retry_used and total_tool_calls == 0:
                    raise ValueError("AI не выполнил обязательную проверку бизнес-данных.")
                logger.info(
                    "AI_AGENT_FINAL request_id=%s rounds=%s tool_calls=%s provider=%s model=%s preview=%s",
                    request_id,
                    rounds,
                    total_tool_calls,
                    runtime.get("provider_id"),
                    runtime.get("model_id"),
                    _preview(final_text),
                )
                return AIBusinessAgentResult(
                    final_text=final_text,
                    messages=messages,
                    runtime=runtime,
                    rounds=rounds,
                    tool_calls=total_tool_calls,
                )

            messages.append({
                "role": "assistant",
                "content": assistant_message.get("content") or "",
                "tool_calls": tool_calls,
            })
            for tool_call in tool_calls:
                arguments = _tool_arguments(tool_call)
                tool_name = str(tool_call.get("function", {}).get("name") or "")
                cache_key = json.dumps(
                    {"name": tool_name, "arguments": arguments},
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
                if cache_key in result_cache:
                    tool_result = result_cache[cache_key]
                    logger.info("AI_TOOL_RESULT request_id=%s name=%s rows=%s cached=true", request_id, tool_name, _row_count(tool_result))
                elif total_tool_calls >= MAX_TOOL_CALLS:
                    tool_result = {
                        "status": "tool_budget_exhausted",
                        "message": "Достигнут лимит business tool calls. Сформируйте вывод по уже полученным данным.",
                    }
                    logger.info("AI_TOOL_RESULT request_id=%s name=%s budget_exhausted=true", request_id, tool_name)
                else:
                    total_tool_calls += 1
                    logger.info(
                        "AI_TOOL_CALL request_id=%s name=%s args=%s",
                        request_id,
                        tool_name,
                        _sanitized_args(arguments),
                    )
                    tool_result = await _resolve_tool_result(
                        tool_name,
                        arguments,
                        tools_service,
                        widget_builder,
                        router,
                    )
                    result_cache[cache_key] = tool_result
                    logger.info("AI_TOOL_RESULT request_id=%s name=%s rows=%s", request_id, tool_name, _row_count(tool_result))
                    if tool_name == "search_entities":
                        conversation_service = AIConversationService(self.store)
                        conversation_service.remember_entities(
                            conversation,
                            _resolved_entities_from_search(tool_result, arguments),
                        )
                messages.append({
                    "role": "tool",
                    "tool_call_id": str(tool_call.get("id")),
                    "content": "AUTHORITATIVE AI BUSINESS OS TOOL RESULT. Use these returned values as factual business evidence.\n"
                    + json.dumps(tool_result, ensure_ascii=False, default=str),
                })
            tool_choice_for_round = "auto"
            response = await _hermes_request(
                messages=messages,
                tools=tools,
                stream=False,
                tool_choice=tool_choice_for_round,
                model=str(runtime["model_id"]),
                provider=str(runtime["provider_id"]),
            )
            if response.status_code >= 400:
                raise ValueError("AI provider вернул ошибку после выполнения business tool.")
        raise ValueError("AI достиг безопасного лимита шагов без финального ответа.")


def _sanitized_args(arguments: dict[str, object]) -> dict[str, object]:
    blocked = {"password", "token", "secret", "api_key", "authorization", "raw"}
    return {
        key: "[redacted]" if any(part in key.lower() for part in blocked) else value
        for key, value in arguments.items()
    }


def _preview(text: str) -> str:
    return " ".join(text.split())[:200]


def _row_count(result: object) -> int:
    """Count rows across compact tool result containers without changing them."""

    if isinstance(result, list):
        return len(result)
    if not isinstance(result, dict):
        return 0
    for key in ("rows", "data", "items", "results", "signals", "action_center"):
        value = result.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            nested_count = _row_count(value)
            if nested_count:
                return nested_count
    return 0


def _looks_business_related(text: str) -> bool:
    """Use baseline context only for likely business requests; tools stay generic."""

    business_terms = {
        "продаж", "выруч", "заказ", "товар", "склад", "остат", "клиент", "покуп",
        "визит", "магазин", "организац", "филиал", "продав", "менеджер", "бизнес",
        "проблем", "аналит", "kpi", "revenue", "sales", "inventory", "customer",
        "product", "order", "stock", "dashboard", "виджет",
    }
    normalized = text.lower()
    return any(term in normalized for term in business_terms)
