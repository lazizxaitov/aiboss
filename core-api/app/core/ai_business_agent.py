"""Reusable multi-step business AI orchestration for all supported channels."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from logging import getLogger
from time import monotonic
from uuid import uuid4

from app.core.ai_conversation import AIConversationService, AIConversationState
from app.core.ai_capabilities import BUSINESS_QUERY_CAPABILITY
from app.core.ai_system_context import AISystemContextService
from app.core.ai_routing import AITaskRouter, TaskType
from app.core.analytics.widget_builder import WidgetBuilderService
from app.core.ai_readonly_sql import AIReadOnlyQueryError, AIReadOnlySQLService
from app.core.data_layer.contracts import CoreDataStore
from app.core.hermes_tools import HermesBusinessTools

logger = getLogger(__name__)

MAX_ROUNDS = 12
MAX_TOOL_CALLS = 12
CHAT_MAX_ROUNDS = 4
CHAT_TOOL_CALLS = 3
LIGHTWEIGHT_ANALYSIS_MAX_ROUNDS = 6


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


def _structured_protocol_prompt(
    tools: list[dict[str, object]],
    *,
    database_schema: dict[str, object] | None = None,
    repair: bool = False,
) -> str:
    repair_text = "The previous output was invalid. Return one valid JSON object only.\n" if repair else ""
    return (
        "You are operating in AI Business OS agent mode.\n"
        "Select your next research step using only the supplied approved schema.\n"
        "For business data return exactly one internal capability envelope "
        "{\"capability\":\"business.query\",\"arguments\":{\"sql\":\"SELECT ... FROM ai_sales ...\"}}. "
        "Only SELECT from ai_* views is allowed.\n"
        "After verified evidence is supplied, return an ordinary answer (or the requested structured analysis JSON).\n"
        "Do not query for the sake of querying. Once sufficient evidence exists to answer the task, you MUST return final.\n"
        "Do not claim that business data or tools are unavailable before attempting a relevant tool.\n"
        "The backend validates and executes the SQL; never access RAW, files, credentials, secrets, or other tables.\n"
        "Use the current organization scope. Keep queries compact and include a useful LIMIT.\n"
        + repair_text
        + "Approved SQL schema/catalog:\n"
        + json.dumps(database_schema or AIReadOnlySQLService.catalog(), ensure_ascii=False, default=str)
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
    payload = _parse_json_object(text)
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
    sql = payload.get("sql")
    if isinstance(sql, str) and sql.strip():
        return {
            "action": "capability",
            "capability": BUSINESS_QUERY_CAPABILITY,
            "arguments": {"sql": sql},
            "approved": True,
        }, None
    return None, "Поле action должно быть query или final."


def _parse_capability_request(content: object) -> dict[str, object] | None:
    """Parse the provider-independent business.query envelope."""

    payload = _parse_json_object(content)
    if not isinstance(payload, dict):
        return None
    arguments = payload.get("arguments")
    if payload.get("capability") == BUSINESS_QUERY_CAPABILITY and isinstance(arguments, dict):
        sql = arguments.get("sql")
        if isinstance(sql, str) and sql.strip():
            return {
                "action": "capability",
                "capability": BUSINESS_QUERY_CAPABILITY,
                "arguments": {"sql": sql},
                "approved": True,
            }
    return None


def _parse_final_request(content: object) -> str | None:
    """Unwrap the provider-independent final branch of the agent protocol."""

    payload = _parse_json_object(content)
    if not isinstance(payload, dict) or payload.get("type") != "final":
        return None
    final_content = payload.get("content")
    return final_content.strip() if isinstance(final_content, str) and final_content.strip() else None


def _parse_json_object(content: object) -> dict[str, object] | None:
    """Parse a provider JSON object while tolerating a short text wrapper."""

    if not isinstance(content, str) or not content.strip():
        return None
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
        decoder = json.JSONDecoder()
        for index, character in enumerate(text):
            if character != "{":
                continue
            try:
                candidate, end = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and not text[index + end :].lstrip().startswith("{"):
                return candidate
        return None
    return payload if isinstance(payload, dict) else None


def _raw_select(content: object) -> str | None:
    """Accept a provider's plain SQL response without exposing it to users."""

    if not isinstance(content, str):
        return None
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if not text.lower().startswith("select"):
        match = re.search(r"\bselect\b", text, re.IGNORECASE)
        if match is None:
            return None
        text = text[match.start():]
    return text.rstrip("` \n")


def _is_analytics_result(payload: dict[str, object] | None) -> bool:
    """Recognize the analytics result contract without requiring chat actions."""

    if not isinstance(payload, dict) or not isinstance(payload.get("summary"), str):
        return False
    fields = ("findings", "warnings", "opportunities", "recommendations", "insights", "risks")
    return any(field in payload and isinstance(payload[field], list) for field in fields)


def _validate_tool_arguments(
    tool_name: str,
    arguments: dict[str, object],
    tools: list[dict[str, object]],
) -> str | None:
    """Apply the catalog's top-level required/property contract before execution."""

    if tool_name in {"query_business_data", BUSINESS_QUERY_CAPABILITY} and isinstance(arguments.get("sql"), str):
        return None

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
        # Business data must be selected by the model through the universal
        # validated query contract, not preloaded as a backend-picked baseline.
        build_baseline: bool = False,
        request_id: str | None = None,
        tool_call_budget: int = MAX_TOOL_CALLS,
        ui_context: dict[str, object] | None = None,
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
        sql_service = AIReadOnlySQLService(self.store)
        system_context = AISystemContextService(self.store).build(
            role=task_type,
            organization_id=conversation.organization_id,
            period=conversation.period,
            ui_context=ui_context,
        )
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
        if build_baseline:
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
                    "message": "Базовый контекст временно недоступен; выполните разрешённый SQL research-запрос.",
                }
        messages: list[dict[str, object]] = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": memory_prompt},
            {"role": "system", "content": _routing_context(router)},
            {
                "role": "system",
                "content": (
                    "AI BUSINESS OS SYSTEM CONTEXT. Use only the capabilities and exact database schema listed here.\n"
                    + json.dumps(system_context, ensure_ascii=False, default=str)
                ),
            },
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
                        "The approved AI Business OS database views listed in this request ARE connected and available. "
                        "Never tell the user that business data is unavailable merely because you have not queried it yet."
                    ),
                },
            )
        tools = _tool_definitions()
        available_capabilities = system_context.get("capabilities", [])
        messages.insert(
            3,
            {
                "role": "system",
                "content": (
                    "You are the primary reasoning intelligence inside AI Business OS.\n"
                    "Understand the user's intent from conversation and system context yourself. "
                    "Answer directly when no external fact is needed. When authoritative business facts are needed, "
                    "independently use business.query before making factual claims. Do not query merely because "
                    "business terminology appears. Never invent business facts.\n"
                    "Return exactly one JSON object per turn. For a final response use: "
                    '{"type":"final","content":"..."}. '
                    "For business.query return this internal envelope: "
                    '{"capability":"business.query","arguments":{"sql":"SELECT ..."}}. '
                    "The capability envelope is never a user-facing answer.\n"
                    "AVAILABLE BUSINESS OS CAPABILITIES (executable):\n"
                    + json.dumps(available_capabilities, ensure_ascii=False, default=str)
                    + "\nFor a listed capability, emit its documented internal request format; do not tell the user to run it.\n"
                    "Exact database schema:\n"
                    + json.dumps(sql_service.database_schema(), ensure_ascii=False, default=str)
                ),
            },
        )
        result_cache: dict[str, object] = {}
        duplicate_query_keys: set[str] = set()
        total_tool_calls = 0
        rounds = 0
        # Chat and analytics use the provider-independent capability protocol.
        # This is selected by the agent role, never by inspecting user text.
        capability_only = task_type in {"ai_chat", "business_analytics"}
        structured_mode = False
        tool_choice_for_round = "auto"
        max_rounds = MAX_ROUNDS
        if task_type == "ai_chat":
            max_rounds = CHAT_MAX_ROUNDS
            tool_call_budget = min(tool_call_budget, CHAT_TOOL_CALLS)
        elif task_type == "business_analytics" and tool_call_budget <= 4:
            max_rounds = LIGHTWEIGHT_ANALYSIS_MAX_ROUNDS
        tool_names = {
            str(item.get("function", {}).get("name"))
            for item in tools
            if isinstance(item, dict) and isinstance(item.get("function"), dict)
        }
        logger.info("AI_AGENT_MODE request_id=%s mode=capability", request_id)

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
                    tools=[] if capability_only else tools,
                    stream=False,
                    tool_choice="none" if capability_only else tool_choice,
                    model=model,
                    provider=provider,
                    # Chat and analytics share one machine-actionable protocol:
                    # the model returns either a capability request or final.
                    response_format={"type": "json_object"} if capability_only else None,
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

        async def final_synthesis(*, round_number: int) -> AIBusinessAgentResult:
            """Ask once for an evidence-only answer when the loop cannot continue."""

            messages.append({
                "role": "system",
                "content": (
                    "FINAL SYNTHESIS: Use ONLY the authoritative business evidence already collected in this conversation. "
                    "Do not request or call any more tools. Return the final answer now. "
                    "If the evidence is insufficient, state exactly what is missing."
                ),
            })
            synthesis_response = await model_request(
                messages=messages,
                tool_choice="auto",
                model=str(runtime["model_id"]),
                provider=str(runtime["provider_id"]),
                round_number=round_number,
            )
            if synthesis_response.status_code >= 400:
                raise ValueError("AI provider не смог сформировать финальный ответ по полученным данным.")
            assistant = _extract_assistant_message(synthesis_response.json())
            if assistant is None or _parse_tool_calls(assistant):
                raise ValueError("AI не смог сформировать финальный ответ по полученным данным.")
            if structured_mode:
                action, error = _parse_structured_action(assistant.get("content"), tool_names)
                if action is None or action.get("action") != "final":
                    raise ValueError(error or "AI не смог сформировать финальный ответ по полученным данным.")
                final_text = str(action["answer"])
            else:
                final_text = _parse_final_request(assistant.get("content")) or str(assistant.get("content") or "")
            if not final_text.strip():
                raise ValueError("AI не смог сформировать финальный ответ по полученным данным.")
            logger.info(
                "AI_AGENT_FINAL request_id=%s rounds=%s tool_calls=%s provider=%s model=%s elapsed_ms=%.2f preview=%s",
                request_id, round_number, total_tool_calls, runtime.get("provider_id"),
                runtime.get("model_id"), (monotonic() - started_at) * 1000, _preview(final_text),
            )
            return AIBusinessAgentResult(
                final_text=final_text, messages=messages, runtime=runtime,
                rounds=round_number, tool_calls=total_tool_calls,
            )

        for rounds in range(1, max_rounds + 1):
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
            if capability_only and tool_calls and isinstance(tools_service, HermesBusinessTools):
                raise ValueError("AI вернул native tool call вместо capability business.query.")
            if capability_only and not tool_calls:
                # Capability envelopes are internal control messages and are
                # recognized on every round, without an intent classifier.
                structured_action = _parse_capability_request(assistant_message.get("content"))
                if structured_action is None:
                    shorthand_action, _ = _parse_structured_action(
                        assistant_message.get("content"),
                        {"query_business_data"},
                    )
                    if shorthand_action and shorthand_action.get("action") == "capability":
                        structured_action = shorthand_action
                if structured_action is not None:
                    structured_tool_id = f"capability-{request_id}-{rounds}"
                    tool_calls = [{
                        "id": structured_tool_id,
                        "function": {
                            "name": str(structured_action["capability"]),
                            "arguments": json.dumps(
                                structured_action.get("arguments") or {},
                                ensure_ascii=False,
                            ),
                        },
                    }]
                else:
                    final_request = _parse_final_request(assistant_message.get("content"))
                    if final_request is not None:
                        assistant_message = {**assistant_message, "content": final_request}
            if structured_mode and not tool_calls:
                if task_type != "business_analytics" and total_tool_calls:
                    payload = _parse_json_object(assistant_message.get("content"))
                    is_query_request = (
                        isinstance(payload, dict)
                        and payload.get("action") == "query"
                    ) or _parse_capability_request(assistant_message.get("content")) is not None
                    if not is_query_request:
                        final_text = str(assistant_message.get("content") or "")
                        if isinstance(payload, dict) and payload.get("action") == "final":
                            final_text = str(payload.get("answer") or "")
                        if final_text.strip():
                            return AIBusinessAgentResult(
                                final_text=final_text, messages=messages, runtime=runtime,
                                rounds=rounds, tool_calls=total_tool_calls,
                            )
                if task_type == "business_analytics":
                    analytics_payload = _parse_json_object(assistant_message.get("content"))
                    if _is_analytics_result(analytics_payload):
                        final_text = json.dumps(analytics_payload, ensure_ascii=False, default=str)
                        logger.info(
                            "AI_AGENT_FINAL request_id=%s rounds=%s tool_calls=%s provider=%s model=%s elapsed_ms=%.2f preview=%s",
                            request_id, rounds, total_tool_calls, runtime.get("provider_id"),
                            runtime.get("model_id"), (monotonic() - started_at) * 1000, _preview(final_text),
                        )
                        return AIBusinessAgentResult(
                            final_text=final_text, messages=messages, runtime=runtime,
                            rounds=rounds, tool_calls=total_tool_calls,
                        )
                structured_action, parse_error = _parse_structured_action(assistant_message.get("content"), tool_names)
                if structured_action is None:
                    structured_action = _parse_capability_request(assistant_message.get("content"))
                if structured_action is None:
                    sql = _raw_select(assistant_message.get("content"))
                    if sql is not None:
                        structured_action = {
                            "action": "capability",
                            "capability": BUSINESS_QUERY_CAPABILITY,
                            "arguments": {"sql": sql},
                            "approved": True,
                        }
                        parse_error = None
                if structured_action is None:
                    if not structured_repair_used:
                        structured_repair_used = True
                        messages.append({"role": "assistant", "content": str(assistant_message.get("content") or "")})
                        messages.append({
                            "role": "system",
                            "content": _structured_protocol_prompt(
                                tools,
                                database_schema=sql_service.database_schema(),
                                repair=True,
                            )
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
                    raise ValueError("AI не вернул корректное structured business action.")
                logger.info(
                    "AI_AGENT_ACTION request_id=%s round=%s action=%s tool=%s",
                    request_id,
                    rounds,
                    structured_action.get("action"),
                    structured_action.get("tool"),
                )
                if structured_action.get("action") == "final":
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
                structured_tool_name = str(
                    structured_action.get("capability") or structured_action.get("tool") or ""
                )
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
                # Internal business requests have one model-facing protocol.
                # Never fall back to the legacy Hermes-native business tools,
                # otherwise the route can bypass capability execution.
                if isinstance(tools_service, HermesBusinessTools) and structured_repair_used:
                    raise ValueError("AI вернул неподдерживаемый business tool call вместо business.query.")
                if not isinstance(tools_service, HermesBusinessTools):
                    # Keep direct service callers that still provide a custom
                    # legacy executor compatible; the Web route always passes
                    # HermesBusinessTools and therefore takes the strict path.
                    structured_mode = False
                    logger.info("AI_AGENT_MODE request_id=%s mode=native", request_id)
                else:
                    structured_repair_used = True
                    messages.append({
                        "role": "assistant",
                        "content": assistant_message.get("content") or "",
                        "tool_calls": tool_calls,
                    })
                    messages.append({
                        "role": "system",
                        "content": _structured_protocol_prompt(
                            tools,
                            database_schema=sql_service.database_schema(),
                            repair=True,
                        )
                        + "\nDo not emit native tool_calls. Return the business.query capability envelope.",
                    })
                    response = await model_request(
                        messages=messages,
                        tool_choice="auto",
                        model=str(runtime["model_id"]),
                        provider=str(runtime["provider_id"]),
                        round_number=rounds + 1,
                    )
                    if response.status_code >= 400:
                        raise ValueError("AI provider вернул ошибку при исправлении business capability.")
                    continue
            if not tool_calls:
                if not structured_mode and total_tool_calls:
                    repeated_action = _parse_json_object(assistant_message.get("content"))
                    if isinstance(repeated_action, dict) and repeated_action.get("action") == "query":
                        # A provider can repeat the internal control message
                        # after the chat has already received the evidence.
                        # Never expose that protocol JSON to the user.
                        return await final_synthesis(round_number=rounds + 1)
                final_text = str(assistant_message.get("content") or "")
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
                query_executed = False
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
                cached_query = cache_key in result_cache
                repeated_query = cached_query and cache_key in duplicate_query_keys
                validation_error = _validate_tool_arguments(tool_name, arguments, tools)
                if validation_error:
                    tool_result = {
                        "status": "error",
                        "message": validation_error,
                    }
                    logger.info("AI_TOOL_RESULT request_id=%s name=%s rejected=true", request_id, tool_name)
                elif cache_key in result_cache:
                    tool_result = result_cache[cache_key]
                    duplicate_query_keys.add(cache_key)
                    logger.info("AI_TOOL_RESULT request_id=%s name=%s rows=%s cached=true", request_id, tool_name, _row_count(tool_result))
                elif total_tool_calls >= tool_call_budget:
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
                    if tool_name in {"query_business_data", BUSINESS_QUERY_CAPABILITY} and isinstance(arguments.get("sql"), str):
                        try:
                            tool_result = sql_service.execute(
                                str(arguments["sql"]),
                                organization_id=conversation.organization_id,
                            )
                        except AIReadOnlyQueryError as error:
                            tool_result = {
                                "available": False,
                                "status": "invalid_query",
                                "message": str(error),
                                "database_schema": sql_service.database_schema(),
                            }
                        except Exception as error:  # noqa: BLE001 - feed DB errors back to the researcher
                            logger.info(
                                "AI_BUSINESS_QUERY_ERROR request_id=%s error_type=%s",
                                request_id,
                                type(error).__name__,
                            )
                            tool_result = {
                                "available": False,
                                "status": "invalid_query",
                                "message": str(error),
                                "database_schema": sql_service.database_schema(),
                            }
                    else:
                        tool_result = await _resolve_tool_result(
                            tool_name,
                            arguments,
                            tools_service,
                            widget_builder,
                            router,
                        )
                    query_executed = tool_name in {"query_business_data", BUSINESS_QUERY_CAPABILITY}
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
                # Hermes deployments may discard role=tool messages when no
                # native tool call was sent. Keep the same full result in a
                # normal readable context message for provider-independent
                # capability roundtrips.
                messages.append({
                    "role": "system",
                    "content": (
                        "BUSINESS_OS_CAPABILITY_RESULT\n"
                        "The capability was executed by AI Business OS. The following returned values are "
                        "authoritative evidence. Use the actual rows directly and do not ask the user to provide them.\n"
                        + json.dumps(
                            {
                                "capability": tool_name,
                                "status": "success" if not (isinstance(tool_result, dict) and tool_result.get("available") is False) else "error",
                                "result": tool_result,
                            },
                            ensure_ascii=False,
                            default=str,
                        )
                    ),
                })
                if tool_name in {"query_business_data", BUSINESS_QUERY_CAPABILITY} and isinstance(arguments.get("sql"), str) and isinstance(tool_result, dict) and tool_result.get("available") is False:
                    messages.append({
                        "role": "system",
                        "content": (
                            "SQL research failed internally. Use the exact DATABASE SCHEMA above and correct the query. "
                            "Do not expose the database error or SQL to the user."
                        ),
                    })
                if cached_query:
                    messages.append({
                        "role": "system",
                        "content": (
                            "This exact query has already been executed. Use the cached authoritative evidence below. "
                            "Do not repeat this query. Return action=final now; no further query is needed."
                        ),
                    })
                else:
                    messages.append({
                        "role": "system",
                        "content": (
                            "The requested business data has now been retrieved. The result below is TRUSTED BUSINESS "
                            "EVIDENCE from AI Business OS. If it is sufficient to answer the original user question, "
                            "return action=final now. Only request another query when specific additional data is genuinely required."
                        ),
                    })
                if task_type == "business_analytics":
                    logger.info(
                        "BUSINESS_ANALYSIS_QUERY_RESULT analysis_id=%s tool=%s rows=%s",
                        request_id,
                        tool_name,
                        _row_count(tool_result),
                    )
                if repeated_query:
                    return await final_synthesis(round_number=rounds + 1)
            if rounds >= max_rounds:
                return await final_synthesis(round_number=rounds + 1)
            tool_choice_for_round = "auto"
            if structured_mode:
                messages.append({
                    "role": "system",
                    "content": _structured_protocol_prompt(tools, database_schema=sql_service.database_schema()),
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
        if total_tool_calls:
            return await final_synthesis(round_number=max_rounds + 1)
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
        "визит", "магазин", "организац", "филиал", "продав", "продал", "продажу",
        "сумм продаж", "лучший продавец", "менеджер", "бизнес",
        "проблем", "аналит", "kpi", "revenue", "sales", "inventory", "customer",
        "product", "order", "stock", "dashboard", "виджет",
        "в нашей базе", "нашей базе", "внутренн", "из базы", "по базе",
    }
    normalized = text.lower()
    return any(term in normalized for term in business_terms)


def _looks_analytical_request(text: str) -> bool:
    """Keep multi-step investigations structured; simple lookups can answer in prose."""

    analytical_terms = (
        "почему", "проанализ", "сравни", "сравнение", "динамик", "проблем",
        "аномал", "рекомендац", "главн", "обзор", "исследуй", "исследован",
        "упал", "сниз", "вырос", "изменил", "что происходит",
    )
    normalized = text.lower()
    return any(term in normalized for term in analytical_terms)
