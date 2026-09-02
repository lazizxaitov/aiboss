from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

from app.core.ai_business_agent import (
    AIBusinessAgentService,
    _parse_capability_request,
    _parse_structured_action,
)
from app.core.ai_conversation import (
    AIConversationChannel,
    AIConversationMessage,
    AIConversationState,
)


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


def test_structured_parser_accepts_clean_fenced_and_surrounded_json():
    tool_names = {"query_business_data"}
    query = '{"action":"query","query":{"dataset":"sales","metrics":["revenue"]}}'
    for content in (query, f"```json\n{query}\n```", f"Проверяю данные. {query} Готово."):
        action, error = _parse_structured_action(content, tool_names)
        assert error is None
        assert action == {
            "action": "tool",
            "tool": "query_business_data",
            "arguments": {"dataset": "sales", "metrics": ["revenue"]},
            "approved": True,
        }


def test_structured_parser_requires_query_or_final_action():
    action, error = _parse_structured_action(
        '{"action":"tool","tool":"query_business_data","arguments":{}}',
        {"query_business_data"},
    )
    assert action is None
    assert error == "Поле action должно быть query или final."


def test_structured_parser_accepts_sql_research_request():
    action, error = _parse_structured_action(
        '{"sql":"SELECT sales_rep_external_id, SUM(total_amount) FROM ai_sales GROUP BY sales_rep_external_id"}',
        {"query_business_data"},
    )
    assert error is None
    assert action == {
        "action": "capability",
        "capability": "business.query",
        "arguments": {"sql": "SELECT sales_rep_external_id, SUM(total_amount) FROM ai_sales GROUP BY sales_rep_external_id"},
        "approved": True,
    }


def test_capability_parser_accepts_type_capability_envelope():
    action = _parse_capability_request(
        '{"type":"capability","capability":"business.query","arguments":{"sql":"SELECT 1 FROM ai_sales"}}'
    )

    assert action["capability"] == "business.query"
    assert action["arguments"]["sql"] == "SELECT 1 FROM ai_sales"


def test_capability_envelope_is_executed_and_never_returned_as_final_text():
    class SQLStore:
        def execute_ai_readonly_sql(self, sql, params, *, statement_timeout_ms):
            return [{"sales_rep_external_id": "123", "total_amount": 64742600}]

    async def execute():
        with patch("app.api.routes.ai_chat._hermes_request", new_callable=AsyncMock) as request:
            request.side_effect = [
                _response({"content": '{"type":"capability","capability":"business.query","arguments":{"sql":"SELECT total_amount FROM ai_sales"}}'}),
                _response({"content": '{"type":"final","content":"Лидер продаж — 64 742 600 сум."}'}),
            ]
            result = await AIBusinessAgentService(SQLStore()).run(
                conversation=AIConversationState(
                    organization_id=UUID("11111111-1111-1111-1111-111111111111"),
                    messages=[AIConversationMessage(
                        role="user", content="Кто продал больше всех?", source_channel=AIConversationChannel.WEB,
                    )],
                ),
                user_text="Кто продал больше всех?", source_channel="web", task_type="ai_chat",
                router=FakeRouter(), tools_service=FakeTools(), widget_builder=object(),
                memory_prompt="", system_prompt="agent",
            )
            return result, request

    result, request = asyncio.run(execute())
    assert result.final_text == "Лидер продаж — 64 742 600 сум."
    assert result.tool_calls == 1
    assert "capability" not in result.final_text
    assert "SELECT" not in result.final_text
    assert "64742600" in "\n".join(str(item.get("content")) for item in request.await_args_list[1].kwargs["messages"])
    assert result.runtime["timings"]["model_calls"] == 2
    assert result.runtime["timings"]["db_queries"] == 1


def test_business_query_capability_is_intercepted_and_rows_are_sent_to_model():
    class SQLStore:
        def __init__(self):
            self.calls = []

        def execute_ai_readonly_sql(self, sql, params, *, statement_timeout_ms):
            self.calls.append((sql, params, statement_timeout_ms))
            return [{"sales_rep_external_id": "123", "total_sales_amount": 500000}]

    async def execute():
        store = SQLStore()
        responses = [
            _response({"content": '{"sql":"SELECT sales_rep_external_id, SUM(total_amount) AS total_sales_amount FROM ai_sales GROUP BY sales_rep_external_id ORDER BY total_sales_amount DESC LIMIT 1"}'}),
            _response({"content": "Иван — 500 000 сум."}),
        ]
        with patch("app.api.routes.ai_chat._hermes_request", new_callable=AsyncMock) as request:
            request.side_effect = responses
            result = await AIBusinessAgentService(store).run(
                conversation=AIConversationState(
                    organization_id=UUID("11111111-1111-1111-1111-111111111111"),
                    messages=[],
                ),
                user_text="Кто продал больше всех по сумме за эту неделю?",
                source_channel="web",
                task_type="ai_chat",
                router=FakeRouter(),
                tools_service=FakeTools(),
                widget_builder=object(),
                memory_prompt="memory",
                system_prompt="agent",
            )
            return store, request, result

    store, request, result = asyncio.run(execute())
    assert result.final_text == "Иван — 500 000 сум."
    assert len(store.calls) == 1
    second_request = request.await_args_list[1].kwargs["messages"]
    assert "500000" in "\n".join(str(message.get("content")) for message in second_request)
    assert '{"sql"' not in result.final_text


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
                return result, resolve, request

    return asyncio.run(execute())


def test_seller_question_uses_manager_aggregation():
    tool_call = {"id": "1", "function": {"name": "query_business_data", "arguments": '{"dataset":"sales","dimensions":["manager"],"metrics":["revenue"]}'}}
    result, resolve, _ = _run(
        "Кто из продавцов сделал больше продаж на этой неделе?",
        [_response({"content": None, "tool_calls": [tool_call]}), _response({"content": "Bekzod"})],
    )
    assert result.final_text == "Bekzod"
    assert resolve.await_args.args[0] == "query_business_data"
    assert resolve.await_args.args[1]["dimensions"] == ["manager"]


def test_internal_database_question_receives_business_data_capability():
    result, _, request = _run(
        "Найди в нашей базе не в интернете данные о том кто продал больше всех по суммам за неделю.",
        [_response({"content": None, "tool_calls": [{
            "id": "1",
            "function": {"name": "query_business_data", "arguments": '{"dataset":"sales"}'},
        }]}), _response({"content": "Ответ подтвержден внутренними данными."})],
    )

    assert result.final_text == "Ответ подтвержден внутренними данными."
    first_messages = request.await_args_list[0].kwargs["messages"]
    capability = "\n".join(str(message.get("content")) for message in first_messages)
    assert "business.query" in capability
    assert "ai_sales" in capability


def test_business_text_without_tools_gets_generic_evidence_retry():
    result, resolve, request = _run(
        "Какой менеджер продал на самую большую сумму за эту неделю? Покажи топ-5 менеджеров.",
        [
            _response({"content": "В baseline нет разбивки по менеджерам."}),
            _response({"content": '{"action":"query","query":{"dataset":"sales","dimensions":["manager"],"metrics":["revenue"],"limit":5}}'}),
            _response({"content": "Ответ подтвержден строками менеджеров"}),
        ],
    )
    assert result.final_text == "Ответ подтвержден строками менеджеров"
    assert resolve.await_count == 1
    assert request.await_args_list[0].kwargs["tool_choice"] == "none"
    assert all(call.kwargs["tool_choice"] == "none" for call in request.await_args_list)


def test_business_chat_refusal_is_retried_through_business_query():
    class SQLStore:
        def execute_ai_readonly_sql(self, sql, params, *, statement_timeout_ms):
            return [{"manager": "Bekzod", "revenue": 500000}]

    async def execute():
        from app.core.hermes_tools import HermesBusinessTools

        with patch("app.api.routes.ai_chat._hermes_request", new_callable=AsyncMock) as request:
            request.side_effect = [
                _response({"content": "Я не имею доступа к базе данных продаж."}),
                _response({"content": '{"capability":"business.query","arguments":{"sql":"SELECT 1 FROM ai_sales LIMIT 1"}}'}),
                _response({"content": "Лидер — Bekzod, 500 000 сум."}),
            ]
            result = await AIBusinessAgentService(SQLStore()).run(
                conversation=AIConversationState(
                    organization_id=UUID("11111111-1111-1111-1111-111111111111"),
                    messages=[AIConversationMessage(
                        role="user", content="Кто больше всех продал за эту неделю?",
                        source_channel=AIConversationChannel.TELEGRAM,
                    )],
                ),
                user_text="Кто больше всех продал за эту неделю?",
                source_channel="telegram",
                task_type="ai_chat",
                router=FakeRouter(),
                tools_service=HermesBusinessTools(SQLStore()),
                widget_builder=object(),
                memory_prompt="memory",
                system_prompt="agent",
            )
            return result, request

    result, request = asyncio.run(execute())

    assert result.final_text == "Лидер — Bekzod, 500 000 сум."
    assert request.await_count == 3


def test_seller_lookup_with_past_tense_enters_structured_business_flow():
    result, resolve, request = _run(
        "Кто продал больше по сумме за эту неделю?",
        [
            _response({"content": '{"action":"query","query":{"dataset":"sales","dimensions":["manager"],"metrics":["revenue"],"limit":5}}'}),
                _response({"content": "Бекзод — лидер по сумме продаж."}),
        ],
    )
    assert result.final_text == "Бекзод — лидер по сумме продаж."
    assert resolve.await_args.args[0] == "query_business_data"
    assert request.await_args_list[0].kwargs["response_format"] == {"type": "json_object"}


def test_structured_multi_step_agent_lets_model_choose_each_tool():
    result, resolve, request = _run(
        "Почему продажи упали?",
        [
            _response({"content": "Сначала проверю данные."}),
            _response({"content": '{"action":"query","query":{"dataset":"sales","dimensions":["date"],"metrics":["revenue"]}}'}),
            _response({"content": '{"action":"query","query":{"dataset":"sales","dimensions":["manager"],"metrics":["revenue"]}}'}),
            _response({"content": "Падение подтверждено."}),
        ],
    )
    assert result.final_text == "Падение подтверждено."
    assert resolve.await_count == 2
    assert all(call.args[0] == "query_business_data" for call in resolve.await_args_list)
    assert all(call.kwargs["tool_choice"] == "none" for call in request.await_args_list)


def test_structured_invalid_dataset_is_rejected_without_execution():
    result, resolve, _ = _run(
        "Проверь продажи",
        [
            _response({"content": "Проверю данные."}),
            _response({"content": '{"action":"query","query":{"dataset":"not_approved","metrics":["revenue"]}}'}),
            _response({"content": '{"action":"query","query":{"dataset":"sales","metrics":["revenue"]}}'}),
            _response({"content": "Проверка завершена."}),
        ],
    )
    assert result.final_text == "Проверка завершена."
    assert resolve.await_args.args[0] == "query_business_data"


def test_structured_malformed_json_gets_one_repair_retry():
    result, _, request = _run(
        "Проверь склад",
        [
            _response({"content": "не json"}),
            _response({"content": '{"action":"query","query":{"dataset":"inventory","metrics":["current_stock"]}}'}),
            _response({"content": "Склад проверен."}),
        ],
    )
    assert result.final_text == "Склад проверен."
    assert len(request.await_args_list) == 3


def test_required_evidence_round_without_tool_returns_controlled_error():
    async def execute():
        with patch("app.api.routes.ai_chat._hermes_request", new_callable=AsyncMock) as request:
            request.side_effect = [
                _response({"content": "В baseline недостаточно данных."}),
                _response({"content": "Инструменты не подключены."}),
                _response({"content": "Инструменты не подключены."}),
            ]
            try:
                await AIBusinessAgentService(object()).run(
                    conversation=_conversation("Сколько продаж было на этой неделе?"),
                    user_text="Сколько продаж было на этой неделе?",
                    source_channel="web", task_type="ai_chat", router=FakeRouter(),
                    tools_service=FakeTools(), widget_builder=object(), memory_prompt="memory",
                    system_prompt="agent",
                )
            except ValueError as error:
                return str(error), request
        raise AssertionError("expected controlled error")

    message, request = asyncio.run(execute())
    assert message == "AI не выполнил обязательную проверку бизнес-данных."
    assert request.await_args_list[1].kwargs["tool_choice"] == "none"


def test_product_question_uses_product_aggregation():
    tool_call = {"id": "1", "function": {"name": "query_business_data", "arguments": '{"dataset":"sales","dimensions":["product"],"metrics":["revenue"]}'}}
    result, resolve, _ = _run(
        "Какой товар продавался лучше всего?",
        [_response({"content": None, "tool_calls": [tool_call]}), _response({"content": "Product A"})],
    )
    assert result.final_text == "Product A"
    assert resolve.await_args.args[1]["dimensions"] == ["product"]


def test_multi_step_analysis_and_duplicate_tool_call_are_bounded():
    tool_call = {"id": "1", "function": {"name": "query_business_data", "arguments": '{"dataset":"sales","period":"this_week","metrics":["revenue"]}'}}
    result, resolve, request = _run(
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
    assert request.await_args_list[0].kwargs["tool_choice"] == "none"
    assert request.await_args_list[1].kwargs["tool_choice"] == "none"


def test_chat_passes_actual_query_rows_to_next_model_request():
    query = '{"action":"query","query":{"dataset":"sales","dimensions":["manager"],"metrics":["revenue"]}}'
    result, resolve, request = _run(
        "Кто продал больше всех за неделю?",
        [
            _response({"content": query}),
            _response({"content": query}),
            _response({"content": "Seller A — 500000."}),
        ],
        tool_result=[
            {"manager": "Seller A", "revenue": 500000},
            {"manager": "Seller B", "revenue": 300000},
        ],
    )
    assert result.final_text == "Seller A — 500000."
    assert resolve.await_count == 1
    follow_up_messages = request.await_args_list[1].kwargs["messages"]
    serialized = "\n".join(str(message.get("content")) for message in follow_up_messages)
    assert "Seller A" in serialized
    assert "500000" in serialized
    assert "Seller B" in serialized
    assert "300000" in serialized
    assert query not in result.final_text


def test_exact_sales_lookup_executes_internal_query_and_returns_normal_text():
    query = (
        '{"action":"query","query":{"dataset":"sales","period":"this_week",'
        '"dimensions":["manager"],"metrics":["revenue"],"filters":{},'
        '"sort":[{"field":"revenue","direction":"desc"}],"limit":1}}'
    )
    result, resolve, request = _run(
        "Кто продал больше всех по сумме за эту неделю? Покажи имя и сумму.",
        [
            _response({"content": query}),
            _response({"content": "Больше всех продал Seller A — 500 000."}),
        ],
        tool_result=[{"manager": "Seller A", "revenue": 500000}],
    )
    assert resolve.await_args.args[0] == "query_business_data"
    assert resolve.await_args.args[1] == {
        "dataset": "sales",
        "period": "this_week",
        "dimensions": ["manager"],
        "metrics": ["revenue"],
        "filters": {},
        "sort": [{"field": "revenue", "direction": "desc"}],
        "limit": 1,
    }
    second_messages = request.await_args_list[1].kwargs["messages"]
    serialized = "\n".join(str(message.get("content")) for message in second_messages)
    assert "Seller A" in serialized
    assert "500000" in serialized
    assert result.final_text == "Больше всех продал Seller A — 500 000."
    assert query not in result.final_text


def test_business_analytics_accepts_structured_result_without_chat_answer_action():
    async def execute():
        with patch("app.api.routes.ai_chat._hermes_request", new_callable=AsyncMock) as request:
            request.side_effect = [
                _response({"content": '{"action":"query","query":{"dataset":"sales","metrics":["revenue"]}}'}),
                _response({
                    "content": (
                        '{"summary":"Продажи выросли","findings":["Seller A лидер"],'
                        '"warnings":[],"opportunities":[],"recommendations":[]}'
                    ),
                }),
            ]
            with patch("app.api.routes.ai_chat._resolve_tool_result", new_callable=AsyncMock) as resolve:
                resolve.return_value = [{"manager": "Seller A", "revenue": 500000}]
                result = await AIBusinessAgentService(object()).run(
                    conversation=_conversation("Сделай краткий анализ продаж"),
                    user_text="Сделай краткий анализ продаж",
                    source_channel="system", task_type="business_analytics", router=FakeRouter(),
                    tools_service=FakeTools(), widget_builder=object(), memory_prompt="memory",
                    system_prompt="agent", build_baseline=False, tool_call_budget=4,
                )
                return result, resolve

    result, resolve = asyncio.run(execute())
    assert '"summary": "Продажи выросли"' in result.final_text
    assert resolve.await_count == 1


def test_step_limit_uses_evidence_only_final_synthesis():
    tool_call = {"id": "1", "function": {"name": "query_business_data", "arguments": '{"dataset":"sales","dimensions":["manager"],"metrics":["revenue"]}'}}
    result, resolve, request = _run(
        "Почему продажи упали?",
        [
            _response({"content": None, "tool_calls": [tool_call]}),
            _response({"content": None, "tool_calls": [tool_call]}),
            _response({"content": "Падение подтверждено по собранным данным."}),
        ],
    )
    assert result.final_text == "Падение подтверждено по собранным данным."
    assert resolve.await_count == 1
    assert len(request.await_args_list) == 3


def test_broad_analysis_can_execute_multiple_distinct_tools():
    first = {"id": "1", "function": {"name": "query_business_data", "arguments": '{"dataset":"sales","metrics":["revenue"]}'}}
    second = {"id": "2", "function": {"name": "query_business_data", "arguments": '{"dataset":"inventory","metrics":["current_stock"]}'}}
    result, resolve, _ = _run(
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
    tool_call = {"id": "1", "function": {"name": "query_business_data", "arguments": '{"dataset":"inventory","metrics":["current_stock"]}'}}
    result, resolve, _ = _run(
        "Проверь склад",
        [_response({"content": None, "tool_calls": [tool_call]}), _response({"content": "Остатки отсутствуют в данных"})],
        tool_result={"available": False, "reason": "inventory отсутствует"},
    )
    assert result.final_text == "Остатки отсутствуют в данных"
    assert resolve.await_count == 1


def test_missing_data_is_passed_to_model_without_invention():
    tool_call = {"id": "1", "function": {"name": "detect_anomalies", "arguments": "{}"}}
    result, _, _ = _run(
        "Проанализируй бизнес и скажи проблемы",
        [
            _response({"content": "В baseline недостаточно данных"}),
            _response({"content": None, "tool_calls": [tool_call]}),
            _response({"content": "Данных для вывода недостаточно"}),
        ],
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


def test_agent_emits_request_model_query_and_final_diagnostics(caplog):
    tool_call = {"id": "1", "function": {"name": "query_business_data", "arguments": '{"dataset":"sales","dimensions":["manager"],"metrics":["revenue"]}'}}
    with caplog.at_level(logging.INFO, logger="app.core.ai_business_agent"):
        result, _, _ = _run(
            "Проверь продажи",
            [_response({"content": None, "tool_calls": [tool_call]}), _response({"content": "Готово"})],
        )

    assert result.final_text == "Готово"
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "AI_AGENT_START" in messages
    assert "AI_AGENT_MODEL_REQUEST" in messages
    assert "AI_AGENT_MODEL_RESPONSE" in messages
    assert "AI_BUSINESS_QUERY_START" in messages
    assert "AI_BUSINESS_QUERY_RESULT" in messages
    assert "AI_AGENT_FINAL" in messages
