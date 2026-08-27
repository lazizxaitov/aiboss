from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.ai_business_agent import AIBusinessAgentService
from app.core.ai_conversation import AIConversationState, AIConversationMessage, AIConversationChannel


class FakeRouter:
    def get_config(self):
        return SimpleNamespace(roles={})

    def resolve_candidates(self, task_type, *, provider_id=None, model_id=None):
        return [{
            "task_type": task_type,
            "provider_id": provider_id or "custom",
            "provider_name": "Local / Custom",
            "model_id": model_id or "local-model",
            "fallback_used": False,
        }]


class FakeTools:
    def build_business_context(self, *args, **kwargs):
        return {"source": "canonical", "summary": {"revenue": 100}}


def _response(message):
    return SimpleNamespace(status_code=200, json=lambda: {"choices": [{"message": message}]})


def _conversation(text: str) -> AIConversationState:
    return AIConversationState(messages=[AIConversationMessage(
        role="user", content=text, source_channel=AIConversationChannel.WEB,
    )])


def _run(text, responses, tool_result=None):
    async def execute():
        with patch("app.api.routes.ai_chat._hermes_request", new_callable=AsyncMock) as request:
            request.side_effect = responses
            with patch("app.api.routes.ai_chat._resolve_tool_result", new_callable=AsyncMock) as resolve:
                resolve.return_value = tool_result or {"domain": "sales", "data": [{"name": "Bekzod", "revenue": 100}]}
                result = await AIBusinessAgentService(object()).run(
                    conversation=_conversation(text),
                    user_text=text,
                    source_channel="web",
                    task_type="ai_chat",
                    router=FakeRouter(),
                    tools_service=FakeTools(),
                    widget_builder=object(),
                    memory_prompt="memory",
                    system_prompt="agent",
                )
                return result, resolve

    return asyncio.run(execute())


def test_seller_question_uses_manager_aggregation():
    tool_call = {"id": "1", "function": {"name": "aggregate_sales", "arguments": '{"group_by":"manager"}'}}
    result, resolve = _run(
        "Кто из продавцов сделал больше продаж на этой неделе?",
        [_response({"content": None, "tool_calls": [tool_call]}), _response({"content": "Bekzod"})],
    )
    assert result.final_text == "Bekzod"
    assert resolve.await_args.args[0] == "aggregate_sales"
    assert resolve.await_args.args[1]["group_by"] == "manager"


def test_product_question_uses_product_aggregation():
    tool_call = {"id": "1", "function": {"name": "aggregate_sales", "arguments": '{"group_by":"product"}'}}
    result, resolve = _run(
        "Какой товар продавался лучше всего?",
        [_response({"content": None, "tool_calls": [tool_call]}), _response({"content": "Product A"})],
    )
    assert result.final_text == "Product A"
    assert resolve.await_args.args[1]["group_by"] == "product"


def test_multi_step_analysis_and_duplicate_tool_call_are_bounded():
    tool_call = {"id": "1", "function": {"name": "compare_periods", "arguments": '{"period":"this_week"}'}}
    result, resolve = _run(
        "Почему продажи упали?",
        [
            _response({"content": None, "tool_calls": [tool_call]}),
            _response({"content": None, "tool_calls": [tool_call]}),
            _response({"content": "Падение подтверждено"}),
        ],
    )
    assert result.final_text == "Падение подтверждено"
    assert resolve.await_count == 1
    assert result.tool_calls == 1


def test_broad_analysis_can_execute_multiple_distinct_tools():
    first = {"id": "1", "function": {"name": "compare_periods", "arguments": "{}"}}
    second = {"id": "2", "function": {"name": "detect_anomalies", "arguments": "{}"}}
    result, resolve = _run(
        "Проанализируй бизнес и скажи, на что обратить внимание",
        [
            _response({"content": None, "tool_calls": [first]}),
            _response({"content": None, "tool_calls": [second]}),
            _response({"content": "Есть два подтвержденных сигнала"}),
        ],
    )
    assert result.final_text == "Есть два подтвержденных сигнала"
    assert resolve.await_count == 2


def test_missing_data_after_tool_check_is_available_to_final_answer():
    tool_call = {"id": "1", "function": {"name": "query_inventory", "arguments": "{}"}}
    result, resolve = _run(
        "Проверь склад",
        [_response({"content": None, "tool_calls": [tool_call]}), _response({"content": "Остатки отсутствуют в данных"})],
        tool_result={"available": False, "reason": "inventory отсутствует"},
    )
    assert result.final_text == "Остатки отсутствуют в данных"
    assert resolve.await_count == 1


def test_missing_data_is_passed_to_model_without_invention():
    result, _ = _run(
        "Проанализируй бизнес и скажи проблемы",
        [_response({"content": "Данных для вывода недостаточно"})],
        tool_result={"available": False, "reason": "inventory отсутствует"},
    )
    assert result.final_text == "Данных для вывода недостаточно"


def test_non_business_question_does_not_build_business_baseline():
    class Tools(FakeTools):
        def build_business_context(self, *args, **kwargs):
            raise AssertionError("baseline should not be requested")

    async def execute():
        with patch("app.api.routes.ai_chat._hermes_request", new_callable=AsyncMock) as request:
            request.return_value = _response({"content": "Привет"})
            return await AIBusinessAgentService(object()).run(
                conversation=_conversation("Привет"), user_text="Привет", source_channel="web",
                task_type="ai_chat", router=FakeRouter(), tools_service=Tools(), widget_builder=object(),
                memory_prompt="memory", system_prompt="agent",
            )

    assert asyncio.run(execute()).final_text == "Привет"


def test_web_and_telegram_routes_use_the_same_agent_service():
    from app.api.routes.ai_chat import AIBusinessAgentService as WebAgent
    from app.api.routes.telegram_ai import AIBusinessAgentService as TelegramAgent

    assert WebAgent is TelegramAgent is AIBusinessAgentService
