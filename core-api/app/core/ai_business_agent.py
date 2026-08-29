"""Reusable multi-step business AI orchestration for all supported channels."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from logging import getLogger
from time import monotonic
from uuid import uuid4

from app.core.ai_conversation import AIConversationService, AIConversationState
from app.core.ai_routing import AITaskRouter, TaskType
from app.core.analytics.widget_builder import WidgetBuilderService
from app.core.data_layer.contracts import CoreDataStore
from app.core.hermes_tools import HermesBusinessTools

logger = getLogger(__name__)

MAX_ROUNDS = 12
MAX_TOOL_CALLS = 12


def _tool_catalog(tools: list[dict[str, object]]) -> list[dict[str, object]]:
    """Expose descriptions and schemas, never Python tool implementations."""

    catalog: list[dict[str, object]] = []
    for item in tools:
        function = item.get("function") if isinstance(item, dict) else None
        if not isinstance(function, dict):
            continue
        catalog.append({
            "name": function.get("name"),
            "description": function.get("description"),
            "arguments": function.get("parameters") or {"type": "object"},
        })
    return catalog


def _structured_protocol_prompt(tools: list[dict[str, object]], *, repair: bool = False) -> str:
    repair_text = "The previous output was invalid. Return one valid JSON object only.\n" if repair else ""
    return (
        "You are operating in AI Business OS agent mode.\n"
        "Select your next action using only the supplied approved tool catalog.\n"
        "Return exactly one JSON object with one of two actions: query or final.\n"
        "For business data, return: {\"action\":\"query\",\"query\":{\"dataset\":\"sales\",\"period\":\"this_week\",\"dimensions\":[\"manager\"],\"metrics\":[\"revenue\"],\"filters\":{},\"sort\":[{\"field\":\"revenue\",\"direction\":\"desc\"}],\"limit\":5}}.\n"
        "After verified evidence is supplied, return: {\"action\":\"final\",\"answer\":\"...\",\"evidence\":[]}.\n"
        "Do not claim that business data or tools are unavailable before attempting a relevant tool.\n"
        "The backend validates the selected tool and arguments; never select a provider or access SQL, RAW, files, or secrets.\n"
        + repair_text
        + "Approved tool catalog:\n"
        + json.dumps(_tool_catalog(tools), ensure_ascii=False, default=str)
    )


def _parse_structured_action(
    content: object,
    tool_names: set[str],
) -> tuple[dict[str, object] | None, str | None]:
    """Parse and validate the model-selected structured action."""

    if not isinstance(content, str) or not content.strip():
        return None, "Модель не вернула JSON-действие."
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Providers occasionally add a short preamble or trailing explanation
        # despite JSON mode. Accept an unambiguous JSON object and validate it
        # exactly like a clean response.
        decoder = json.JSONDecoder()
        payload = None
        for index, character in enumerate(text):
            if character != "{":
                continue
            try:
                candidate, end = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and not text[index + end :].lstrip().startswith("{"):
                payload = candidate
                break
        if payload is None:
            return None, "Ответ structured agent не является корректным JSON."
    if not isinstance(payload, dict):
        return None, "Structured action должен быть JSON-объектом."
    action = payload.get("action")
    if action == "final":
        answer = payload.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            return None, "Final action должен содержать непустое поле answer."
        return {"action": "final", "answer": answer}, None
    if action == "query":
        query = payload.get("query")
        if not isinstance(query, dict):
            return None, "Query action должен содержать объект query."
        return {
            "action": "tool",
            "tool": "query_business_data",
            "arguments": query,
            "approved": True,
        }, None
    return None, "Поле action должно быть query или final."


def _validate_tool_arguments(
    tool_name: str,
    arguments: dict[str, object],
    tools: list[dict[str, object]],
) -> str | None:
    """Apply the catalog's top-level required/property contract before execution."""

    definition = next(
        (
            item.get("function")
            for item in tools
            if isinstance(item, dict)
            and isinstance(item.get("function"), dict)
            and item["function"].get("name") == tool_name
        ),
        None,
    )
    if not isinstance(definition, dict):
        return "Запрошен неизвестный или неразрешённый AI Business OS tool."
    parameters = definition.get("parameters")
    if not isinstance(parameters, dict):
        return None
    properties = parameters.get("properties")
    if isinstance(properties, dict):
        unknown = sorted(set(arguments) - set(properties))
        if unknown:
            return "Инструмент получил неизвестные аргументы: " + ", ".join(unknown)
        for name, value in arguments.items():
            schema = properties.get(name)
            if not isinstance(schema, dict):
                continue
            allowed = schema.get("enum")
            if isinstance(allowed, list) and value not in allowed:
                return f"Недопустимое значение аргумента {name}."
    required = parameters.get("required")
    if isinstance(required, list):
        missing = [name for name in required if isinstance(name, str) and name not in arguments]
        if missing:
            return "Инструменту не хватает обязательных аргументов: " + ", ".join(missing)
    return None


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
        build_baseline: bool = True,
        request_id: str | None = None,
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

        request_id = request_id or str(uuid4())
        started_at = monotonic()
        candidates = router.resolve_candidates(
            task_type,
            provider_id=provider_id,
            model_id=model_id,
        )
        if not candidates:
            raise ValueError("Для этой задачи нет доступного provider/model.")
        runtime = candidates[0]
        logger.info(
            "AI_AGENT_START request_id=%s provider=%s model=%s organization=%s period=%s source=%s",
            request_id,
            runtime.get("provider_id"),
            runtime.get("model_id"),
            conversation.organization_id,
            conversation.period,
            source_channel,
        )
        baseline = None
        if build_baseline and _looks_business_related(user_text):
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
        business_request = _looks_business_related(user_text)
        internal_business = business_request or task_type in {
            "business_analytics",
            "system_action",
            "communications",
        }
        tools = _tool_definitions()
        if business_request:
            # Native tool schemas are not equally visible to every Hermes provider.
            # Keep the same backend-approved catalog in the prompt as an explicit
            # capability contract; the model still chooses the tool and arguments.
            messages.insert(
                3,
                {
                    "role": "system",
                    "content": (
                        "INTERNAL AI BUSINESS OS DATA ACCESS IS CONNECTED.\n"
                        "For factual questions about the owner's business, use the approved read-only "
                        "business tools below. Do not use internet or external search, and do not claim "
                        "that the database or tools are unavailable before attempting a relevant tool. "
                        "Choose the dataset, dimensions, metrics, period, filters, sort and limit yourself "
                        "from the catalog. The backend validates and executes the selected query.\n"
                        "Approved BusinessDataQueryService catalog:\n"
                        + json.dumps(_tool_catalog(tools), ensure_ascii=False, default=str)
                    ),
                },
            )
        result_cache: dict[str, object] = {}
        total_tool_calls = 0
        rounds = 0
        evidence_retry_used = False
        # Business requests start in the internal structured protocol. This
        # prevents a provider's own web/API discovery tools from becoming the
        # execution path; the model still selects the approved tool/query.
        structured_mode = business_request
        structured_repair_used = False
        tool_choice_for_round = "auto"
        tool_names = {
            str(item.get("function", {}).get("name"))
            for item in tools
            if isinstance(item, dict) and isinstance(item.get("function"), dict)
        }
        logger.info("AI_AGENT_MODE request_id=%s mode=native", request_id)
        if structured_mode:
            messages.append({
                "role": "system",
                "content": _structured_protocol_prompt(tools),
            })
            logger.info("AI_AGENT_MODE request_id=%s mode=structured", request_id)

        async def model_request(
            *,
            round_number: int,
            messages: list[dict[str, object]],
            tool_choice: str | dict[str, object] | None,
            model: str,
            provider: str,
        ):
            request_started = monotonic()
            logger.info(
                "AI_AGENT_MODEL_REQUEST request_id=%s round=%s timestamp=%s tool_choice=%s provider=%s model=%s",
                request_id,
                round_number,
                datetime.now(UTC).isoformat(),
                tool_choice,
                provider,
                model,
            )
            if task_type == "business_analytics":
                logger.info(
                    "BUSINESS_ANALYSIS_MODEL_REQUEST analysis_id=%s round=%s provider=%s model=%s",
                    request_id,
                    round_number,
                    provider,
                    model,
                )
            try:
                response = await _hermes_request(
                    messages=messages,
                    # Internal requests use Hermes as an inference gateway only.
                    # The model selects JSON actions from the prompt catalog;
                    # backend code validates and executes every business tool.
                    tools=[] if internal_business else tools,
                    stream=False,
                    tool_choice="none" if internal_business else tool_choice,
                    model=model,
                    provider=provider,
                    response_format=(
                        {"type": "json_object"}
                        if internal_business
                        else None
                    ),
                )
            except Exception:
                logger.info(
                    "AI_AGENT_MODEL_RESPONSE request_id=%s round=%s elapsed_ms=%.2f action=invalid",
                    request_id,
                    round_number,
                    (monotonic() - request_started) * 1000,
                )
                raise
            action = "invalid"
            usage_tokens = None
            try:
                payload = response.json()
                usage = payload.get("usage") if isinstance(payload, dict) else None
                if isinstance(usage, dict):
                    usage_tokens = usage.get("total_tokens")
                assistant = _extract_assistant_message(payload) if isinstance(payload, dict) else None
                if assistant is not None:
                    if _parse_tool_calls(assistant):
                        action = "query"
                    else:
                        content = assistant.get("content")
                        if isinstance(content, str):
                            try:
                                structured_action = json.loads(content)
                            except json.JSONDecodeError:
                                structured_action = None
                            if isinstance(structured_action, dict) and structured_action.get("action") == "query":
                                action = "query"
                            else:
                                action = "final"
                        else:
                            action = "final"
            except (ValueError, TypeError, json.JSONDecodeError):
                pass
            logger.info(
                "AI_AGENT_MODEL_RESPONSE request_id=%s round=%s elapsed_ms=%.2f usage_tokens=%s action=%s status=%s",
                request_id,
                round_number,
                (monotonic() - request_started) * 1000,
                usage_tokens,
                action,
                response.status_code,
            )
            return response

        response = None
        for candidate in candidates:
            candidate_response = await model_request(
                messages=messages,
                tool_choice="auto",
                model=str(candidate["model_id"]),
                provider=str(candidate["provider_id"]),
                round_number=1,
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
            if task_type == "business_analytics":
                logger.info(
                    "BUSINESS_ANALYSIS_ROUND analysis_id=%s round=%s",
                    request_id,
                    rounds,
                )
            assistant_message = _extract_assistant_message(response.json())
            if assistant_message is None:
                raise ValueError("AI не вернул корректный ответ.")
            tool_calls = _parse_tool_calls(assistant_message)
            structured_action: dict[str, object] | None = None
            if structured_mode and not tool_calls:
                structured_action, parse_error = _parse_structured_action(
                    assistant_message.get("content"),
                    tool_names,
                )
                if structured_action is None:
                    if not structured_repair_used:
                        structured_repair_used = True
                        messages.append({"role": "assistant", "content": str(assistant_message.get("content") or "")})
                        messages.append({
                            "role": "system",
                            "content": _structured_protocol_prompt(tools, repair=True)
                            + "\nValidation error: " + str(parse_error),
                        })
                        response = await model_request(
                            messages=messages,
                            tool_choice="auto",
                            model=str(runtime["model_id"]),
                            provider=str(runtime["provider_id"]),
                            round_number=rounds + 1,
                        )
                        if response.status_code >= 400:
                            raise ValueError("AI provider вернул ошибку при исправлении structured action.")
                        continue
                    if business_request and total_tool_calls == 0:
                        raise ValueError("AI не выполнил обязательную проверку бизнес-данных.")
                    raise ValueError("AI не вернул корректное structured business action.")
                logger.info(
                    "AI_AGENT_ACTION request_id=%s round=%s action=%s tool=%s",
                    request_id,
                    rounds,
                    structured_action.get("action"),
                    structured_action.get("tool"),
                )
                if structured_action.get("action") == "final":
                    if business_request and total_tool_calls == 0:
                        raise ValueError("AI не выполнил обязательную проверку бизнес-данных.")
                    final_text = str(structured_action["answer"])
                    logger.info(
                        "AI_AGENT_FINAL request_id=%s rounds=%s tool_calls=%s provider=%s model=%s elapsed_ms=%.2f preview=%s",
                        request_id, rounds, total_tool_calls, runtime.get("provider_id"),
                        runtime.get("model_id"), (monotonic() - started_at) * 1000, _preview(final_text),
                    )
                    return AIBusinessAgentResult(
                        final_text=final_text, messages=messages, runtime=runtime,
                        rounds=rounds, tool_calls=total_tool_calls,
                    )
                structured_tool_name = str(structured_action.get("tool") or "")
                structured_tool_id = f"structured-{request_id}-{rounds}"
                tool_calls = [{
                    "id": structured_tool_id,
                    "function": {
                        "name": structured_tool_name,
                        "arguments": json.dumps(
                            structured_action.get("arguments") or {},
                            ensure_ascii=False,
                        ),
                    },
                }]
            elif structured_mode and tool_calls:
                # A provider may recover native calling on the structured retry.
                # From this point use its native protocol for the remaining loop.
                structured_mode = False
                logger.info("AI_AGENT_MODE request_id=%s mode=native", request_id)
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
                    structured_mode = True
                    structured_repair_used = False
                    logger.info("AI_AGENT_MODE request_id=%s mode=structured", request_id)
                    messages.append({
                        "role": "system",
                        "content": _structured_protocol_prompt(tools),
                    })
                    response = await model_request(
                        messages=messages,
                        # Hermes Codex accepts this request but ignores required.
                        # Structured JSON is the provider-independent enforcement layer.
                        tool_choice="auto",
                        model=str(runtime["model_id"]),
                        provider=str(runtime["provider_id"]),
                        round_number=rounds + 1,
                    )
                    if response.status_code >= 400:
                        raise ValueError("AI provider вернул ошибку при повторной проверке business tools.")
                    continue
                if business_request and evidence_retry_used and total_tool_calls == 0:
                    raise ValueError("AI не выполнил обязательную проверку бизнес-данных.")
                logger.info(
                    "AI_AGENT_FINAL request_id=%s rounds=%s tool_calls=%s provider=%s model=%s elapsed_ms=%.2f preview=%s",
                    request_id,
                    rounds,
                    total_tool_calls,
                    runtime.get("provider_id"),
                    runtime.get("model_id"),
                    (monotonic() - started_at) * 1000,
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
            logger.info(
                "AI_AGENT_ACTION request_id=%s round=%s action=tool tool=%s native=%s",
                request_id,
                rounds,
                ",".join(str(call.get("function", {}).get("name") or "") for call in tool_calls),
                not structured_mode,
            )
            for tool_call in tool_calls:
                arguments = _tool_arguments(tool_call)
                tool_name = str(tool_call.get("function", {}).get("name") or "")
                if task_type == "business_analytics":
                    logger.info(
                        "BUSINESS_ANALYSIS_QUERY analysis_id=%s query_number=%s tool=%s args=%s",
                        request_id,
                        total_tool_calls + 1,
                        tool_name,
                        _sanitized_args(arguments),
                    )
                cache_key = json.dumps(
                    {"name": tool_name, "arguments": arguments},
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
                validation_error = _validate_tool_arguments(tool_name, arguments, tools)
                if validation_error:
                    tool_result = {
                        "status": "error",
                        "message": validation_error,
                    }
                    logger.info("AI_TOOL_RESULT request_id=%s name=%s rejected=true", request_id, tool_name)
                elif cache_key in result_cache:
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
                    if tool_name in {"query_business_data", "aggregate_sales", "query_inventory", "query_products", "query_customers", "query_returns", "query_visits", "query_finance"}:
                        logger.info(
                            "AI_BUSINESS_QUERY_START request_id=%s dataset=%s dimensions=%s metrics=%s",
                            request_id,
                            arguments.get("dataset") or tool_name.removeprefix("query_"),
                            arguments.get("dimensions") or arguments.get("group_by"),
                            arguments.get("metrics"),
                        )
                        query_started = monotonic()
                    tool_result = await _resolve_tool_result(
                        tool_name,
                        arguments,
                        tools_service,
                        widget_builder,
                        router,
                    )
                    result_cache[cache_key] = tool_result
                    logger.info("AI_TOOL_RESULT request_id=%s name=%s rows=%s", request_id, tool_name, _row_count(tool_result))
                    if tool_name in {"query_business_data", "aggregate_sales", "query_inventory", "query_products", "query_customers", "query_returns", "query_visits", "query_finance"}:
                        logger.info(
                            "AI_BUSINESS_QUERY_RESULT request_id=%s elapsed_ms=%.2f row_count=%s",
                            request_id,
                            (monotonic() - query_started) * 1000,
                            _row_count(tool_result),
                        )
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
                if task_type == "business_analytics":
                    logger.info(
                        "BUSINESS_ANALYSIS_QUERY_RESULT analysis_id=%s tool=%s rows=%s",
                        request_id,
                        tool_name,
                        _row_count(tool_result),
                    )
            tool_choice_for_round = "auto"
            if structured_mode:
                messages.append({
                    "role": "system",
                    "content": _structured_protocol_prompt(tools),
                })
            response = await model_request(
                messages=messages,
                tool_choice=tool_choice_for_round,
                model=str(runtime["model_id"]),
                provider=str(runtime["provider_id"]),
                round_number=rounds + 1,
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
        "в нашей базе", "нашей базе", "внутренн", "из базы", "по базе",
    }
    normalized = text.lower()
    return any(term in normalized for term in business_terms)
