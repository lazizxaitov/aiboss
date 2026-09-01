import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from app.api.routes import ai_insights
from app.api.routes.ai_insights import get_dashboard_insights, run_dashboard_analysis
from app.core.ai_insight_presentation import AIInsightPresentationService
from app.core.auto_business_analytics import (
    AutoAnalyticsResult,
    AutoAnalyticsRun,
    AutoAnalyticsStatus,
    AutoBusinessAnalyticsService,
    DashboardPlan,
    DashboardWidgetPlan,
    _analytical_content_count,
    _normalize_ai_result_payload,
    _unwrap_analytics_result,
    _validated_dashboard_widgets,
)
from app.core.data_layer.entities import AppSetting
from app.core.data_layer.service import InMemoryCoreDataLayer


def _completed_run() -> AutoAnalyticsRun:
    return AutoAnalyticsRun(
        analysis_id="analysis-1",
        organization_scope=["org-1"],
        period="last_7_days",
        provider_id="openai-codex",
        model_id="gpt-5.6-luna",
        generated_at=datetime(2026, 8, 29, tzinfo=UTC),
        status="completed",
        summary="Продажи растут.",
        structured_result=AutoAnalyticsResult(
            summary="Продажи растут.",
            findings=[{
                "title": "Рост продаж",
                "priority": "high",
                "evidence": [{"metric": "revenue"}],
            }],
            recommendations=[{
                "title": "Удержать темп",
                "description": "Продолжить работу с лидерами.",
            }],
            organization_ids=["org-1"],
            analysis_period={"preset": "last_7_days"},
        ),
    )


def test_completed_analysis_is_persisted_and_dashboard_reads_structured_result():
    store = InMemoryCoreDataLayer()
    run = AutoBusinessAnalyticsService(store)._save(_completed_run())

    payload = asyncio.run(get_dashboard_insights(store))

    assert AutoBusinessAnalyticsService(store).latest_successful().analysis_id == run.analysis_id
    assert payload["status"] == "ready"
    assert payload["analysis_id"] == "analysis-1"
    assert payload["summary"] == "Продажи растут."
    assert payload["findings"][0]["title"] == "Рост продаж"
    assert payload["recommendations"][0]["title"] == "Удержать темп"
    assert payload["provider_id"] == "openai-codex"
    assert payload["model_id"] == "gpt-5.6-luna"


def test_empty_dashboard_state_is_explicit():
    payload = AIInsightPresentationService(InMemoryCoreDataLayer()).dashboard()

    assert payload["status"] == "empty"
    assert payload["message"] == "ИИ-анализ ещё не выполнен"
    assert payload["findings"] == []


def test_running_dashboard_state_is_explicit():
    store = InMemoryCoreDataLayer()
    now = datetime.now(UTC)
    store.upsert_app_setting(AppSetting(
        setting_key="ai_business_analytics:status:v1",
        setting_value=AutoAnalyticsStatus(
            status="analyzing",
            last_started_at=now,
        ).model_dump(mode="json"),
        metadata={},
        created_at=now,
        updated_at=now,
    ))

    payload = AIInsightPresentationService(store).dashboard()

    assert payload["status"] == "running"
    assert payload["message"] == "ИИ анализирует бизнес..."


def test_manual_analysis_starts_in_background_and_deduplicates_requests():
    store = InMemoryCoreDataLayer()
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_run(_service, mode="deep"):
        started.set()
        await release.wait()
        return AutoAnalyticsRun(status="completed", analysis_level=mode)

    async def scenario():
        with patch.object(AutoBusinessAnalyticsService, "run", new=fake_run):
            first = await run_dashboard_analysis(store)
            await started.wait()
            second = await run_dashboard_analysis(store)
            release.set()
            await asyncio.sleep(0)
        return first, second

    try:
        first, second = asyncio.run(scenario())
    finally:
        ai_insights._MANUAL_ANALYSIS_TASKS.clear()

    assert first.status == "running"
    assert second.status == "running"


def test_startup_analysis_skips_when_canonical_data_is_not_ready():
    store = InMemoryCoreDataLayer()
    service = AutoBusinessAnalyticsService(store)

    with patch.object(store, "list_canonical_organizations", return_value=[]), patch.object(
        service, "run_widget_if_needed", new=AsyncMock()
    ) as run_widget:
        result = asyncio.run(service.run_startup_if_needed())

    assert result is None
    run_widget.assert_not_awaited()


def test_startup_analysis_reuses_existing_widget_flow_when_data_is_ready():
    store = InMemoryCoreDataLayer()
    service = AutoBusinessAnalyticsService(store)
    expected = _completed_run()

    with patch.object(store, "list_canonical_organizations", return_value=[object()]), patch.object(
        service, "run_widget_if_needed", new=AsyncMock(return_value=expected)
    ) as run_widget:
        result = asyncio.run(service.run_startup_if_needed())

    assert result is expected
    run_widget.assert_awaited_once()


def test_auto_analysis_normalizes_provider_result_variants_without_fake_metrics():
    payload = _normalize_ai_result_payload({
        "summary": "Есть риск снижения продаж.",
        "status": "unexpected-provider-status",
        "insights": [{
            "title": "Снижение продаж",
            "description": "Продажи ниже предыдущего периода.",
            "type": "finding",
            "priority": "urgent",
            "evidence": "sales comparison",
        }],
        "recommendations": ["Проверить причины снижения."],
        "anomalies": [{"title": "Резкое изменение"}],
        "top_opportunities": [{"description": "Вернуть клиентов"}],
        "dashboard_plan": {"widgets": [{"invalid": True}]},
    })

    result = AutoAnalyticsResult.model_validate(payload)

    assert result.status == "normal"
    assert result.insights[0].type == "info"
    assert result.insights[0].priority == "medium"
    assert result.insights[0].evidence == [{"detail": "sales comparison"}]
    assert result.recommendations[0].title == "Проверить причины снижения."
    assert result.anomalies == ["Резкое изменение"]
    assert result.top_opportunities == ["Вернуть клиентов"]
    assert result.dashboard_plan is None
    assert _analytical_content_count(result) == 2


def test_dashboard_plan_requires_safe_type_scope_and_evidence():
    run = _completed_run()
    organization_id = "00000000-0000-0000-0000-000000000001"
    run.organization_scope = [organization_id]
    run.structured_result.dashboard_plan = DashboardPlan(widgets=[
        DashboardWidgetPlan(
            widget_type="bar_chart",
            title="Продажи по продавцам",
            reason="Подтверждённое сравнение",
            insight="Показать ranking по результатам запроса.",
            organization_ids=[organization_id],
            evidence=[{"dataset": "ai_sales", "row_count": 2, "sql": "SELECT secret"}],
        ),
        DashboardWidgetPlan(
            widget_type="execute_js",
            title="Нельзя",
            reason="Нельзя",
            insight="Нельзя",
            evidence=[{"dataset": "ai_sales"}],
        ),
        DashboardWidgetPlan(
            widget_type="line_chart",
            title="Без доказательств",
            reason="Причина",
            insight="Нет evidence",
        ),
    ])

    widgets = _validated_dashboard_widgets(run)

    assert len(widgets) == 1
    assert widgets[0].widget_type == "bar_chart"


def test_auto_analysis_unwraps_fenced_and_final_envelopes():
    body = '{"summary":"Готово","findings":[{"title":"Факт"}]}'
    envelope = json.dumps({"type": "final", "content": body}, ensure_ascii=False)
    assert _unwrap_analytics_result(f"```json\n{envelope}\n```") == {
        "summary": "Готово",
        "findings": [{"title": "Факт"}],
    }


def test_auto_analysis_rejects_result_without_analytical_content():
    result = AutoAnalyticsResult.model_validate({"summary": "Обзор завершён"})

    assert _analytical_content_count(result) == 0
