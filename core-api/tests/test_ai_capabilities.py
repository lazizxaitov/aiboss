from datetime import UTC, datetime
from types import SimpleNamespace

from app.core.ai_capabilities import ai_capability_registry
from app.core.ai_system_context import AISystemContextService
from app.core.organization_context import business_week_bounds


def test_business_roles_receive_read_only_business_query_capability():
    capabilities = ai_capability_registry.describe("business_analytics")

    assert {item["name"] for item in capabilities} == {
        "business.query", "system.inspect", "ui.inspect",
    }
    assert all(item["access"] == "read" for item in capabilities)
    business_query = next(item for item in capabilities if item["name"] == "business.query")
    assert business_query["arguments"]["required"] == ["sql"]
    assert business_query["arguments"]["properties"]["sql"]["type"] == "string"


def test_system_context_contains_exact_published_schema_and_permissions():
    context = AISystemContextService(SimpleNamespace()).build(
        role="ai_chat",
        provider="provider-b",
        model="model-b",
        organization_id="org-1",
        period="this_week",
        ui_context={"current_page": "/"},
    )

    assert context["permissions"]["database"] == "read_only"
    assert context["permissions"]["raw_data"] is False
    assert context["ai"] == {"role": "ai_chat", "provider": "provider-b", "model": "model-b"}
    assert context["database"]["schema"]["ai_sales"]["columns"]
    assert "sales_rep_name" in {
        column["name"] for column in context["database"]["schema"]["ai_sales"]["columns"]
    }
    assert context["database"]["semantic_environment"]["datasets"]
    assert context["database"]["semantic_environment"]["datasets"][0]["grain"]
    assert context["current_ui"] == {"current_page": "/"}


def test_role_without_business_query_does_not_receive_business_environment():
    context = AISystemContextService(SimpleNamespace()).build(role="system_developer")

    assert "business.query" not in {item["name"] for item in context["capabilities"]}
    assert "database" not in context


def test_business_context_publishes_explicit_local_week_boundaries():
    context = AISystemContextService(SimpleNamespace()).build(
        role="business_analytics",
        period="current_week",
    )

    business = context["business_context"]
    assert business["timezone"] == "Asia/Tashkent"
    assert business["calendar_week"]["definition"].startswith("Monday")
    assert business["calendar_week"]["start"].endswith("+05:00")
    assert business["calendar_week"]["end_exclusive"].endswith("+05:00")
    assert business["selected_period"] == "current_week"
    assert business["selected_period_window"]["start"].endswith("+05:00")


def test_business_week_resolver_is_timezone_stable_at_monday_boundary():
    start, end = business_week_bounds(datetime(2026, 8, 31, 18, 0, tzinfo=UTC))

    assert start.isoformat() == "2026-08-31T00:00:00+05:00"
    assert end.isoformat() == "2026-09-07T00:00:00+05:00"
