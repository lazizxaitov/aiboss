"""Streaming chat proxy for the local Hermes OpenAI-compatible server."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from logging import getLogger
from time import monotonic
from typing import Annotated, Literal
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import AliasChoices, BaseModel, Field

from app.api.routes.auth import _session, _token_from_request
from app.core.ai_business_agent import AIBusinessAgentService
from app.core.ai_conversation import (
    AIConversationChannel,
    AIConversationService,
    AIConversationTargetChannel,
)
from app.core.ai_routing import AITaskRouter, TaskType
from app.core.ai_shared_memory import SharedMemoryService
from app.core.analytics.widget_builder import (
    WidgetBuilderDraft,
    WidgetBuilderService,
    WidgetBuilderUpdatePatch,
)
from app.core.business_data_query import BusinessDataQueryService
from app.core.config import settings
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.hermes_model_registry import hermes_model_registry
from app.core.hermes_tools import HermesBusinessTools
from app.core.organization_context import OrganizationContextService

router = APIRouter(prefix="/ai")
logger = getLogger(__name__)


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
    provider: str | None = Field(default=None, validation_alias=AliasChoices("provider", "provider_id"))
    model: str | None = Field(default=None, validation_alias=AliasChoices("model", "model_id"))
    ui_context: dict[str, object] | None = None


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
                "name": "aggregate_sales",
                "description": (
                    "Aggregate real canonical sales by one supported business dimension. "
                    "Use this for questions such as which seller, product, branch, organization, "
                    "or customer sold the most. Never select a provider or use raw data."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "organization_id": {"type": ["string", "null"]},
                        "period": {"type": ["string", "null"]},
                        "filters": {"type": ["object", "null"], "description": "Canonical entity filters such as manager_id, customer_id or product_id."},
                        "group_by": {
                            "type": "string",
                            "enum": ["manager", "seller", "employee", "organization", "filial", "product", "category", "client", "customer", "date", "day", "week", "month"],
                        },
                        "metrics": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["revenue", "sales", "sales_amount", "orders", "order_count", "quantity", "sold_units", "average_check", "average_order", "returns"]},
                        },
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 100},
                    },
                    "required": ["group_by"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_business_data",
                "description": "Generic read-only query over approved Canonical V2 business datasets. Choose the dataset, dimensions, metrics and filters needed for the question.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dataset": {"type": "string", "enum": ["sales", "inventory", "products", "customers", "returns", "visits", "finance"]},
                        "organization_id": {"type": ["string", "null"]},
                        "period": {"type": ["string", "null"]},
                        "date_from": {"type": ["string", "null"], "description": "ISO date, optional."},
                        "date_to": {"type": ["string", "null"], "description": "ISO date, optional."},
                        "dimensions": {"type": "array", "items": {"type": "string"}, "maxItems": 1},
                        "metrics": {"type": "array", "items": {"type": "string"}},
                        "filters": {"type": ["object", "null"]},
                        "sort": {"type": "array", "items": {"type": "object"}},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
                    },
                    "required": ["dataset"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_inventory",
                "description": "Read-only inventory query using canonical analytics. Returns stock, low-stock, zero-stock, overstock and stockout signals when available.",
                "parameters": {
                    "type": "object", "properties": {
                        "organization_id": {"type": ["string", "null"]}, "period": {"type": ["string", "null"]},
                        "filters": {"type": ["object", "null"]}, "limit": {"type": "integer", "default": 50}, "sort": {"type": "string"},
                    }, "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_products",
                "description": "Read-only product analytics query for sales, velocity, stock, returns and fast/slow movers.",
                "parameters": {
                    "type": "object", "properties": {
                        "organization_id": {"type": ["string", "null"]}, "period": {"type": ["string", "null"]},
                        "filters": {"type": ["object", "null"]}, "group_by": {"type": ["string", "null"]},
                        "limit": {"type": "integer", "default": 50}, "sort": {"type": "string"},
                    }, "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_customers",
                "description": "Read-only customer analytics query for revenue, orders, last purchase, frequency, inactive and at-risk customers.",
                "parameters": {
                    "type": "object", "properties": {
                        "organization_id": {"type": ["string", "null"]}, "period": {"type": ["string", "null"]},
                        "filters": {"type": ["object", "null"]}, "limit": {"type": "integer", "default": 50}, "sort": {"type": "string"},
                    }, "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_returns",
                "description": "Read-only returns aggregation by product, customer, manager, filial or organization.",
                "parameters": {"type": "object", "properties": {
                    "organization_id": {"type": ["string", "null"]}, "period": {"type": ["string", "null"]},
                    "group_by": {"type": "string", "default": "product"}, "limit": {"type": "integer", "default": 50},
                }, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_visits",
                "description": "Read-only visit analytics by manager, customer, organization or available status metrics.",
                "parameters": {"type": "object", "properties": {
                    "organization_id": {"type": ["string", "null"]}, "period": {"type": ["string", "null"]},
                    "group_by": {"type": ["string", "null"]}, "limit": {"type": "integer", "default": 50},
                }, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_finance",
                "description": "Read-only finance analytics. Returns only canonical payment, cash, bank and cash-flow metrics that exist.",
                "parameters": {"type": "object", "properties": {
                    "organization_id": {"type": ["string", "null"]}, "period": {"type": ["string", "null"]},
                    "group_by": {"type": ["string", "null"]}, "limit": {"type": "integer", "default": 50},
                }, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_entities",
                "description": "Read-only search across canonical products, customers, managers, warehouses, organizations and filials.",
                "parameters": {"type": "object", "properties": {
                    "entity_type": {"type": "string", "enum": ["product", "category", "customer", "manager", "seller", "employee", "warehouse", "filial", "organization"]},
                    "search": {"type": "string"}, "organization_id": {"type": ["string", "null"]}, "limit": {"type": "integer", "default": 20},
                }, "required": ["entity_type", "search"], "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compare_periods",
                "description": "Compare compact canonical sales aggregations for two periods.",
                "parameters": {"type": "object", "properties": {
                    "organization_id": {"type": ["string", "null"]}, "period": {"type": ["string", "null"]},
                    "comparison_period": {"type": ["string", "null"]}, "group_by": {"type": ["string", "null"]}, "limit": {"type": "integer", "default": 20},
                }, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "detect_anomalies",
                "description": "Compute deterministic anomaly and risk signals from existing canonical analytics; the model only explains the returned evidence.",
                "parameters": {"type": "object", "properties": {
                    "organization_id": {"type": ["string", "null"]}, "period": {"type": ["string", "null"]}, "limit": {"type": "integer", "default": 30},
                }, "additionalProperties": False},
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
        "Use ONLY the provided authoritative AI Business OS context and business data tools when the user asks about revenue, orders, sales, top products, "
        "business comparisons, organizations, or current attention.\n"
        "Do not request or reveal SQL, PostgreSQL, raw SmartUp payloads, terminal/file/system access, or secrets.\n"
        "If the user wants to create, update, or delete a dashboard widget, use the widget builder tools.\n"
        "If the user does not specify organization or period, rely on the current AI Business OS context.\n"
        "If the user asks for a file or a document, return it as a fenced code block in the form "
        "```file name=\"report.txt\" type=\"text/plain\"\n<content>\n``` so the UI can offer a download.\n"
        "Answer in the user's language and keep the answer grounded in tool results.\n"
        "Never invent a value, stock level, customer, product, or cause that is absent from the provided context. "
        "If a required dataset is missing, name the missing dataset explicitly.\n"
        f"Current organization context: {organization_text}.\n"
        f"Current period context: {period_text}."
    )


def _routing_context(router: AITaskRouter) -> str:
    assignments = router.get_config().roles
    lines = [
        "AI BOS ROLE ROUTING:",
        "You are the orchestrator. For this interactive chat, use approved business data tools directly when factual business evidence is needed. Use delegate_ai_task only for a distinct delegated task; never select a provider or model.",
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


def _resolved_entities_from_search(result: object, arguments: dict[str, object]) -> list[dict[str, str]]:
    if not isinstance(result, dict) or result.get("domain") != "entity_search":
        return []
    rows = result.get("data")
    if not isinstance(rows, list):
        return []
    entity_type = str(arguments.get("entity_type") or "")
    entities: list[dict[str, str]] = []
    for row in rows[:20]:
        if not isinstance(row, dict):
            continue
        entity_id = row.get("id")
        display_name = row.get("name")
        if entity_type in {"manager", "seller", "employee"}:
            entity_id = row.get("sales_manager_id") or row.get("sales_manager_code") or entity_id
            display_name = row.get("sales_manager_name") or display_name
        elif entity_type == "warehouse":
            entity_id = row.get("warehouse_id") or row.get("warehouse_code") or entity_id
            display_name = row.get("warehouse_name") or display_name
        if entity_id and display_name:
            entities.append({"type": entity_type, "id": str(entity_id), "display_name": str(display_name)})
    return entities


async def _hermes_request(
    *,
    messages: list[dict[str, object]],
    tools: list[dict[str, object]] | None,
    stream: bool,
    tool_choice: str | dict[str, object] | None = None,
    model: str | None = None,
    provider: str | None = None,
    response_format: dict[str, object] | None = None,
) -> httpx.Response:
    body = _hermes_payload(
        messages=messages,
        tools=tools,
        stream=stream,
        tool_choice=tool_choice,
        model=model,
        provider=provider,
        response_format=response_format,
    )
    url = f"{settings.hermes_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.hermes_api_key}"}
    client = httpx.AsyncClient(timeout=None)
    response = await client.post(url, headers=headers, json=body)
    if not stream:
        await client.aclose()
    return response


def _hermes_payload(
    *,
    messages: list[dict[str, object]],
    tools: list[dict[str, object]] | None,
    stream: bool,
    tool_choice: str | dict[str, object] | None = None,
    model: str | None = None,
    provider: str | None = None,
    response_format: dict[str, object] | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "model": model or settings.hermes_model,
        "messages": messages,
        "stream": stream,
    }
    if provider:
        body["provider"] = "custom" if provider.startswith("custom:") else provider
    if tools is not None:
        body["tools"] = tools
    if tool_choice is not None:
        body["tool_choice"] = tool_choice
    if response_format is not None:
        body["response_format"] = response_format
    return body


@asynccontextmanager
async def _hermes_stream(
    *,
    messages: list[dict[str, object]],
    tools: list[dict[str, object]] | None,
    model: str | None = None,
    provider: str | None = None,
    tool_choice: str | dict[str, object] | None = None,
    response_format: dict[str, object] | None = None,
) -> AsyncIterator[httpx.Response]:
    """Open the real provider stream; callers must consume it inside this context."""

    url = f"{settings.hermes_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.hermes_api_key}"}
    body = _hermes_payload(
        messages=messages,
        tools=tools,
        stream=True,
        tool_choice=tool_choice,
        model=model,
        provider=provider,
        response_format=response_format,
    )
    async with httpx.AsyncClient(timeout=None) as client:
        stream_context = client.stream("POST", url, headers=headers, json=body)
        try:
            response = await stream_context.__aenter__()
        except Exception:
            # A provider may expose completions but not streaming. The agent
            # detects this sentinel and retries the same turn non-streaming.
            # Cancellation is not swallowed because it inherits BaseException.
            class _UnavailableStream:
                status_code = 599

                async def aread(self) -> bytes:
                    return b""

            yield _UnavailableStream()
            return
        try:
            yield response
        finally:
            await stream_context.__aexit__(None, None, None)


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
                provider=str(runtime["provider_id"]),
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
    if tool_name == "query_business_data":
        def parse_date(value: object) -> date | None:
            if not value:
                return None
            try:
                return date.fromisoformat(str(value))
            except ValueError:
                return None

        return BusinessDataQueryService(tools).query(
            dataset=str(arguments.get("dataset") or ""),
            organization_id=organization_id,
            period=period,
            date_from=parse_date(arguments.get("date_from")),
            date_to=parse_date(arguments.get("date_to")),
            dimensions=arguments.get("dimensions") if isinstance(arguments.get("dimensions"), list) else None,
            metrics=arguments.get("metrics") if isinstance(arguments.get("metrics"), list) else None,
            filters=arguments.get("filters") if isinstance(arguments.get("filters"), dict) else None,
            sort=arguments.get("sort") if isinstance(arguments.get("sort"), list) else None,
            limit=int(arguments.get("limit", 50)),
        )
    if tool_name == "aggregate_sales":
        raw_metrics = arguments.get("metrics")
        metrics = raw_metrics if isinstance(raw_metrics, list) and all(isinstance(item, str) for item in raw_metrics) else None
        try:
            limit = int(arguments.get("limit", 100))
        except (TypeError, ValueError):
            limit = 100
        return tools.aggregate_sales(
            organization_id=organization_id,
            period=period,
            group_by=str(arguments.get("group_by") or ""),
            metrics=metrics,
            filters=arguments.get("filters") if isinstance(arguments.get("filters"), dict) else None,
            limit=limit,
        )
    if tool_name == "query_inventory":
        return tools.query_inventory(
            organization_id=organization_id, period=period,
            filters=arguments.get("filters") if isinstance(arguments.get("filters"), dict) else None,
            limit=int(arguments.get("limit", 50)), sort=str(arguments.get("sort") or "current_stock"),
        )
    if tool_name == "query_products":
        return tools.query_products(
            organization_id=organization_id, period=period,
            filters=arguments.get("filters") if isinstance(arguments.get("filters"), dict) else None,
            group_by=str(arguments.get("group_by")) if arguments.get("group_by") else None,
            limit=int(arguments.get("limit", 50)), sort=str(arguments.get("sort") or "revenue"),
        )
    if tool_name == "query_customers":
        return tools.query_customers(
            organization_id=organization_id, period=period,
            filters=arguments.get("filters") if isinstance(arguments.get("filters"), dict) else None,
            limit=int(arguments.get("limit", 50)), sort=str(arguments.get("sort") or "revenue"),
        )
    if tool_name == "query_returns":
        return tools.query_returns(
            organization_id=organization_id, period=period,
            group_by=str(arguments.get("group_by") or "product"), limit=int(arguments.get("limit", 50)),
        )
    if tool_name == "query_visits":
        return tools.query_visits(
            organization_id=organization_id, period=period,
            group_by=str(arguments.get("group_by")) if arguments.get("group_by") else None,
            limit=int(arguments.get("limit", 50)),
        )
    if tool_name == "query_finance":
        return tools.query_finance(
            organization_id=organization_id, period=period,
            group_by=str(arguments.get("group_by")) if arguments.get("group_by") else None,
            limit=int(arguments.get("limit", 50)),
        )
    if tool_name == "search_entities":
        return tools.search_entities(
            entity_type=str(arguments.get("entity_type") or ""), search=str(arguments.get("search") or ""),
            organization_id=organization_id, limit=int(arguments.get("limit", 20)),
        )
    if tool_name == "compare_periods":
        return tools.compare_periods(
            organization_id=organization_id, period=period,
            comparison_period=_normalize_period_value(arguments.get("comparison_period")),
            group_by=str(arguments.get("group_by")) if arguments.get("group_by") else None,
            limit=int(arguments.get("limit", 20)),
        )
    if tool_name == "detect_anomalies":
        return tools.detect_anomalies(organization_id=organization_id, period=period, limit=int(arguments.get("limit", 30)))
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
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    """Proxy Hermes' OpenAI-compatible stream without exposing its credentials."""

    request_id = str(uuid4())
    request_started = monotonic()

    async def stream():
        conversation_service = AIConversationService(store)
        logger.info(
            "AI_CHAT_REQUEST_START request_id=%s selected_provider=%s selected_model=%s",
            request_id,
            request.provider or "settings",
            request.model or "settings",
        )
        session = _session(_token_from_request(None, authorization), store)
        effective_user_id = request.user_id or (session.login if session is not None else None)
        shared_memory = SharedMemoryService(store)
        tools_service = HermesBusinessTools(store)
        widget_builder = WidgetBuilderService(store)
        await hermes_model_registry.get_providers()
        router = AITaskRouter(store)
        candidates = router.resolve_candidates(
            request.task_type,
            provider_id=request.provider if request.task_type == "ai_chat" else None,
            model_id=request.model if request.task_type == "ai_chat" else None,
        )
        if not candidates:
            yield _event({"message": "Для этой задачи нет доступного provider/model."}, "error")
            logger.info(
                "AI_CHAT_RESPONSE request_id=%s status=error elapsed_ms=%.2f response_type=configuration",
                request_id,
                (monotonic() - request_started) * 1000,
            )
            return
        conversation = conversation_service.resolve_or_create_conversation(
            source_channel=request.source_channel,
            user_id=effective_user_id,
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
                user_id=effective_user_id,
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
        last_user_text = _message_text(last_user_message.content) if last_user_message is not None else ""
        shared_memory.remember(
            conversation.user_id or effective_user_id or "owner",
            last_user_text,
            "dashboard",
        )
        try:
            delta_queue: asyncio.Queue[str | None] = asyncio.Queue()
            streamed_parts: list[str] = []

            async def on_final_delta(content: str) -> None:
                await delta_queue.put(content)

            async def execute_agent():
                try:
                    return await AIBusinessAgentService(store).run(
                        conversation=conversation,
                        user_text=last_user_text,
                        source_channel=request.source_channel.value,
                        task_type=request.task_type,
                        router=router,
                        tools_service=tools_service,
                        widget_builder=widget_builder,
                        memory_prompt=shared_memory.prompt_context(conversation.user_id or effective_user_id or "owner"),
                        system_prompt=conversation_service.build_system_prompt(conversation),
                        # Chat selection is a per-message override only for the
                        # conversational role. Business analytics and system actions
                        # must always use their assignments from AI Routing settings.
                        provider_id=request.provider if request.task_type == "ai_chat" else None,
                        model_id=request.model if request.task_type == "ai_chat" else None,
                        # Interactive chat must let the model plan the relevant query
                        # from the approved catalog; deep automatic analytics owns its
                        # separate baseline flow.
                        build_baseline=False,
                        request_id=request_id,
                        ui_context=request.ui_context,
                        on_final_delta=on_final_delta,
                    )
                finally:
                    await delta_queue.put(None)

            agent_task = asyncio.create_task(execute_agent())
            while True:
                delta = await delta_queue.get()
                if delta is None:
                    break
                if delta:
                    streamed_parts.append(delta)
                    yield _event({"content": delta}, "delta")
            result = await agent_task
            assistant_text = result.final_text
            if not assistant_text.strip():
                raise ValueError("AI не вернул завершённый ответ.")
            timings = result.runtime.get("timings")
            if isinstance(timings, dict):
                normalization_started = monotonic()
                timings["total_ms"] = (monotonic() - request_started) * 1000
                timings["final_normalization_ms"] = (monotonic() - normalization_started) * 1000
                timings.setdefault("first_token_ms", None)
                logger.info(
                    "AI_CHAT_LATENCY request_id=%s total_request_ms=%.2f model_calls=%s db_queries=%s "
                    "round1_prompt_chars=%s round2_prompt_chars=%s postgres_query_ms=%s capability_result_ms=%s sections=%s",
                    request_id,
                    timings["total_ms"],
                    timings.get("model_calls", 0),
                    timings.get("db_queries", 0),
                    timings.get("round_1_prompt_chars", 0),
                    timings.get("round_2_prompt_chars", 0),
                    timings.get("postgres_query_ms", 0),
                    timings.get("capability_result_ms", 0),
                    json.dumps(
                        {
                            "round1": timings.get("round_1_sections", {}),
                            "round2": timings.get("round_2_sections", {}),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
                logger.info(
                    "AI_CHAT_LATENCY_STREAM request_id=%s final_stream_started_ms=%s first_final_token_ms=%s "
                    "final_stream_duration_ms=%s final_completion_ms=%s",
                    request_id,
                    timings.get("final_stream_started_ms"),
                    timings.get("first_final_token_ms"),
                    timings.get("final_stream_duration_ms"),
                    timings.get("final_completion_ms"),
                )
            conversation_service.append_message(
                conversation,
                role="assistant",
                content=assistant_text,
                source_channel=request.source_channel,
                target_channel=resolved_target_channel,
                metadata={
                    "provider_id": result.runtime.get("provider_id"),
                    "model_id": result.runtime.get("model_id"),
                    "fallback_used": result.runtime.get("fallback_used", False),
                    "agent_rounds": result.rounds,
                    "tool_calls": result.tool_calls,
                    "business_entities": result.runtime.get("business_entities", []),
                },
            )
            if assistant_text and not streamed_parts:
                # Non-stream providers retain the old complete-content event.
                yield _event({"content": assistant_text})
            yield _event(
                {
                    "conversation_id": conversation.conversation_id,
                    "target_channel": resolved_target_channel.value if resolved_target_channel else "",
                    "provider_id": str(result.runtime.get("provider_id") or ""),
                    "provider_name": str(result.runtime.get("provider_name") or ""),
                    "model_id": str(result.runtime.get("model_id") or ""),
                    "fallback_used": str(bool(result.runtime.get("fallback_used"))).lower(),
                    "agent_rounds": str(result.rounds),
                    "tool_calls": str(result.tool_calls),
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
            logger.info(
                "AI_CHAT_RESPONSE request_id=%s status=success elapsed_ms=%.2f response_type=assistant",
                request_id,
                (monotonic() - request_started) * 1000,
            )
        except asyncio.CancelledError:
            if "agent_task" in locals() and not agent_task.done():
                agent_task.cancel()
            raise
        except Exception as error:  # noqa: BLE001 - SSE clients need a terminal error event
            logger.exception(
                "AI_CHAT_RESPONSE request_id=%s status=error elapsed_ms=%.2f response_type=error",
                request_id,
                (monotonic() - request_started) * 1000,
            )
            yield _event({"message": str(error) or "Не удалось подключиться к AI."}, "error")

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
