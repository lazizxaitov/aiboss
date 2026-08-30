from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

from app.api.routes.ai_chat import ChatMessage, ChatRequest, chat
from app.core.data_layer.service import InMemoryCoreDataLayer


class RouteSQLStore(InMemoryCoreDataLayer):
    def __init__(self):
        super().__init__()
        self.sql_calls = []

    def execute_ai_readonly_sql(self, sql, params, *, statement_timeout_ms):
        self.sql_calls.append((sql, params, statement_timeout_ms))
        return [{"sales_rep_external_id": "123", "total_sales_amount": 64742600}]


def test_web_chat_sse_only_contains_final_answer_after_business_query():
    async def execute():
        store = RouteSQLStore()
        capability_json = (
            '{"capability":"business.query","arguments":{"sql":"'
            "SELECT sales_rep_external_id, SUM(total_amount) AS total_sales "
            "FROM ai_sales GROUP BY sales_rep_external_id LIMIT 1"
            '"}}'
        )
        model_request = AsyncMock(side_effect=[
            SimpleNamespace(
                status_code=200,
                json=lambda: {"choices": [{"message": {"content": capability_json}}]},
            ),
            SimpleNamespace(
                status_code=200,
                json=lambda: {"choices": [{"message": {"content": '{"type":"final","content":"Лидер продаж — Иван, 64 742 600 сум."}'}}]},
            ),
        ])
        request = ChatRequest(
            messages=[ChatMessage(role="user", content="Кто продал больше всех по сумме за эту неделю?")],
            organization_id=UUID("11111111-1111-1111-1111-111111111111"),
        )
        candidates = [{
            "provider_id": "custom",
            "provider_name": "Local / Custom",
            "model_id": "local-model",
            "fallback_used": False,
        }]
        with (
            patch("app.api.routes.ai_chat._hermes_request", model_request),
            patch("app.api.routes.ai_chat._resolve_tool_result", new=AsyncMock()) as legacy_tool_flow,
            patch("app.core.hermes_model_registry.HermesModelRegistry.get_providers", new=AsyncMock(return_value=[])),
            patch("app.api.routes.ai_chat.AITaskRouter.resolve_candidates", return_value=candidates),
        ):
            response = await chat(request, store, None)
            chunks = [chunk async for chunk in response.body_iterator]
        return store, model_request, legacy_tool_flow, "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks)

    store, model_request, legacy_tool_flow, body = asyncio.run(execute())
    assert len(store.sql_calls) == 1
    assert model_request.await_count == 2
    assert legacy_tool_flow.await_count == 0
    first_turn = model_request.await_args_list[0].kwargs["messages"]
    first_context = "\n".join(str(message.get("content")) for message in first_turn)
    assert "business.query" in first_context
    assert '"required": ["sql"]' in first_context
    assert model_request.await_args_list[0].kwargs["response_format"] == {"type": "json_object"}
    assert model_request.await_args_list[1].kwargs["response_format"] == {"type": "json_object"}
    second_turn = model_request.await_args_list[1].kwargs["messages"]
    second_context = "\n".join(str(message.get("content")) for message in second_turn)
    assert "BUSINESS_OS_CAPABILITY_RESULT" in second_context
    assert "64742600" in second_context
    assert "Лидер продаж — Иван, 64 742 600 сум." in body
    assert "business.query" not in body
    assert "SELECT" not in body


def test_web_chat_meta_question_can_finish_without_business_query():
    async def execute():
        store = RouteSQLStore()
        model_request = AsyncMock(return_value=SimpleNamespace(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "Да, через безопасную capability Business OS."}}]},
        ))
        request = ChatRequest(
            messages=[ChatMessage(role="user", content="У тебя есть доступ к нашей базе?")],
        )
        candidates = [{
            "provider_id": "custom",
            "provider_name": "Local / Custom",
            "model_id": "local-model",
            "fallback_used": False,
        }]
        with (
            patch("app.api.routes.ai_chat._hermes_request", model_request),
            patch("app.api.routes.ai_chat._resolve_tool_result", new=AsyncMock()) as legacy_tool_flow,
            patch("app.core.hermes_model_registry.HermesModelRegistry.get_providers", new=AsyncMock(return_value=[])),
            patch("app.api.routes.ai_chat.AITaskRouter.resolve_candidates", return_value=candidates),
        ):
            response = await chat(request, store, None)
            chunks = [chunk async for chunk in response.body_iterator]
            body = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks)
        return store, legacy_tool_flow, body

    store, legacy_tool_flow, body = asyncio.run(execute())
    assert store.sql_calls == []
    assert legacy_tool_flow.await_count == 0
    assert "Да, через безопасную capability Business OS." in body
