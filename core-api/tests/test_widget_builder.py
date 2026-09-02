"""Focused contracts for AI-generated widget presentation metadata."""

from __future__ import annotations

from app.core.analytics.widget_builder import WidgetBuilderDraft, WidgetBuilderService, WidgetBuilderType
from tests.test_ai_analytics_seed import seed_ai_analytics_store


def test_ai_title_and_description_are_preserved_in_resolved_widget() -> None:
    store, organization, _other = seed_ai_analytics_store()
    draft = WidgetBuilderDraft(
        title="Продажи Бекзода",
        description="Сумма продаж Бекзода за последние 7 дней.",
        widget_type=WidgetBuilderType.KPI,
        metric="revenue",
        organization_ids=[organization.organization_id],
        period="7d",
    )

    resolved, preview, _needs_selection, _options = WidgetBuilderService(store).resolve_draft(
        draft,
        organization_id=organization.organization_id,
        period="7d",
    )

    assert resolved.title == "Продажи Бекзода"
    assert resolved.description == "Сумма продаж Бекзода за последние 7 дней."
    assert preview.title == resolved.title
    assert preview.subtitle == resolved.description
