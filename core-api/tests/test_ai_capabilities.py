from types import SimpleNamespace

from app.core.ai_capabilities import ai_capability_registry
from app.core.ai_system_context import AISystemContextService


def test_business_roles_receive_read_only_business_query_capability():
    capabilities = ai_capability_registry.describe("business_analytics")

    assert {item["name"] for item in capabilities} == {
        "business.query", "system.inspect", "ui.inspect",
    }
    assert all(item["access"] == "read" for item in capabilities)


def test_system_context_contains_exact_published_schema_and_permissions():
    context = AISystemContextService(SimpleNamespace()).build(
        role="ai_chat",
        organization_id="org-1",
        period="this_week",
        ui_context={"current_page": "/"},
    )

    assert context["permissions"]["database"] == "read_only"
    assert context["permissions"]["raw_data"] is False
    assert context["database"]["schema"]["ai_sales"]["columns"]
    assert "seller_name" not in {
        column["name"] for column in context["database"]["schema"]["ai_sales"]["columns"]
    }
    assert context["current_ui"] == {"current_page": "/"}
