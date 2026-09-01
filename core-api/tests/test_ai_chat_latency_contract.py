from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

from app.core.ai_business_agent import AIBusinessAgentService
from app.core.ai_conversation import AIConversationState


class Router:
    def resolve_candidates(self, task_type, *, provider_id=None, model_id=None):
        return [{
            "provider_id": provider_id or "custom",
            "provider_name": "Local",
            "model_id": model_id or "model",
            "fallback_used": False,
        }]

    def get_config(self):
        return SimpleNamespace(roles={})


class Tools:
    pass


def response(content):
    return SimpleNamespace(status_code=200, json=lambda: {"choices": [{"message": {"content": content}}]})


def run(responses, text="Привет", store=None, conversation=None):
    async def execute():
        with patch("app.api.routes.ai_chat._hermes_request", new_callable=AsyncMock) as request:
            request.side_effect = responses
            result = await AIBusinessAgentService(store or object()).run(
                conversation=conversation or AIConversationState(
                    organization_id=UUID("11111111-1111-1111-1111-111111111111"),
                    messages=[],
                ),
                user_text=text,
                source_channel="web",
                task_type="ai_chat",
                router=Router(),
                tools_service=Tools(),
                widget_builder=object(),
                memory_prompt="",
                system_prompt="agent",
            )
            return result, request

    return asyncio.run(execute())


def test_greeting_uses_one_model_call_without_database_query():
    result, request = run([response('{"type":"final","content":"Привет!"}')])

    assert result.final_text == "Привет!"
    assert request.await_count == 1
    assert result.runtime["timings"]["model_calls"] == 1
    assert result.runtime["timings"]["db_queries"] == 0


def test_non_business_turn_does_not_build_business_schema():
    class Store:
        def __init__(self):
            self.schema_calls = 0

        def describe_ai_views(self):
            self.schema_calls += 1
            return {"ai_sales": {"columns": [{"name": "revenue"}]}}

    store = Store()
    result, request = run([response('{"type":"final","content":"Хорошего дня!"}')], "Спасибо", store)

    assert result.final_text == "Хорошего дня!"
    assert request.await_count == 1
    assert store.schema_calls == 0
    assert "business.query" not in request.await_args.kwargs["messages"][3]["content"]


def test_business_conversation_keeps_context_for_ambiguous_follow_up():
    conversation = AIConversationState(
        organization_id=UUID("11111111-1111-1111-1111-111111111111"),
        conversation_mode="business",
        messages=[],
    )

    async def execute():
        with patch("app.api.routes.ai_chat._hermes_request", new_callable=AsyncMock) as request:
            request.return_value = response('{"type":"final","content":"Проверяю данные."}')
            result = await AIBusinessAgentService(object()).run(
                conversation=conversation,
                user_text="А почему?",
                source_channel="web",
                task_type="ai_chat",
                router=Router(),
                tools_service=Tools(),
                widget_builder=object(),
                memory_prompt="",
                system_prompt="agent",
            )
            return result, request

    result, request = asyncio.run(execute())

    assert result.final_text == "Проверяю данные."
    request_messages = request.await_args.kwargs["messages"]
    assert any("database" in str(message.get("content")) for message in request_messages)
    assert conversation.conversation_mode == "business"


def test_explicit_general_message_leaves_business_context():
    conversation = AIConversationState(conversation_mode="business", messages=[])
    result, request = run(
        [response('{"type":"final","content":"Хорошего дня!"}')],
        "Спасибо",
        conversation=conversation,
    )

    assert result.final_text == "Хорошего дня!"
    assert request.await_count == 1
    assert conversation.conversation_mode == "general"


def test_successful_business_query_stops_on_next_final():
    class Store:
        def __init__(self):
            self.calls = 0

        def execute_ai_readonly_sql(self, sql, params, *, statement_timeout_ms):
            self.calls += 1
            return [{"manager": "Иван", "revenue": 500000}]

    store = Store()
    result, request = run([
        response('{"capability":"business.query","arguments":{"sql":"SELECT revenue FROM ai_sales"}}'),
        response('{"action":"final","answer":"Иван — 500 000."}'),
    ], "Кто больше всех продал?", store)

    assert result.final_text == "Иван — 500 000."
    assert request.await_count == 2
    assert store.calls == 1
    assert result.runtime["timings"]["model_calls"] == 2
    assert result.runtime["timings"]["db_queries"] == 1


def test_final_on_first_round_does_not_start_second_round():
    result, request = run([response('{"action":"final","answer":"Готово."}')])

    assert result.final_text == "Готово."
    assert request.await_count == 1


def test_same_sql_with_whitespace_variation_uses_run_cache():
    class Store:
        def __init__(self):
            self.calls = 0

        def execute_ai_readonly_sql(self, sql, params, *, statement_timeout_ms):
            self.calls += 1
            return [{"revenue": 500000}]

    store = Store()
    result, request = run([
        response('{"capability":"business.query","arguments":{"sql":"SELECT revenue FROM ai_sales"}}'),
        response('{"capability":"business.query","arguments":{"sql":" SELECT   revenue   FROM   ai_sales "}}'),
        response('{"type":"final","content":"500 000."}'),
    ], "Проверь сумму продаж", store)

    assert result.final_text == "500 000."
    assert store.calls == 1
    assert result.runtime["timings"]["db_queries"] == 1
    assert request.await_count == 3
