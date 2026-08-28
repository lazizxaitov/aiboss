from datetime import UTC, datetime

from app.api.routes.ai_insights import get_dashboard_insights
from app.core.ai_insight_presentation import AIInsightPresentationService
from app.core.auto_business_analytics import (
    AutoAnalyticsResult,
    AutoAnalyticsRun,
    AutoAnalyticsStatus,
    AutoBusinessAnalyticsService,
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
            findings=[{"title": "Рост продаж", "priority": "high", "evidence": [{"metric": "revenue"}]}],
            recommendations=[{"title": "Удержать темп", "description": "Продолжить работу с лидерами."}],
            organization_ids=["org-1"],
            analysis_period={"preset": "last_7_days"},
        ),
    )


def test_completed_analysis_is_persisted_and_dashboard_reads_structured_result():
    store = InMemoryCoreDataLayer()
    run = AutoBusinessAnalyticsService(store)._save(_completed_run())

    payload = get_dashboard_insights(store)

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
        setting_value=AutoAnalyticsStatus(status="analyzing", last_started_at=now).model_dump(mode="json"),
        metadata={},
        created_at=now,
        updated_at=now,
    ))

    payload = AIInsightPresentationService(store).dashboard()

    assert payload["status"] == "running"
    assert payload["message"] == "ИИ анализирует бизнес..."
