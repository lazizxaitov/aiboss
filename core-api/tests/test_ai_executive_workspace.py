"""Tests for the AI-driven executive dashboard workspace."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.routes.dashboard import get_core_store
from app.core.data_layer.entities import (
    BusinessProfile,
    ContactProfile,
    FinanceEntry,
    FinanceEntryType,
    MarketingActivity,
    MarketingChannel,
    SourceSystem,
)
from app.core.data_layer.normalized import (
    InventoryBalance,
    Payment,
    Product,
    ProductPrice,
    Visit,
)
from app.core.data_layer.normalized import (
    Sale as NormalizedSale,
)
from app.core.data_layer.normalized import (
    SaleItem as NormalizedSaleItem,
)
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.integrations.smartup.models import SmartUpOrganization
from app.main import app


def _seed_ai_workspace_store() -> tuple[InMemoryCoreDataLayer, BusinessProfile]:
    store = InMemoryCoreDataLayer()
    business = store.register_business(
        BusinessProfile(
            name="AI Workspace LLC",
            legal_name="AI Workspace LLC",
            external_ref="biz-ai-001",
        ),
    )
    store.register_source_system(
        SourceSystem(
            business_id=business.business_id,
            name="SmartUp",
            source_type="erp",
            external_ref="biz-ai-001",
        ),
    )
    store.upsert_smartup_organization(
        SmartUpOrganization(
            name="AI Workspace Org",
            company_id="11300",
            filial_id="16114091",
            project_code="trade",
            is_active=True,
        ),
    )
    store.upsert_contact(
        ContactProfile(
            business_id=business.business_id,
            full_name="Sarah Buyer",
            email="sarah@example.com",
            external_ref="contact-001",
        ),
    )
    store.upsert_product(
        Product(
            organization_id=business.business_id,
            source_external_id="prod-001",
            name="Balance Purifying Gel",
            sku="BAL-001",
        ),
    )
    store.upsert_product_price(
        ProductPrice(
            organization_id=business.business_id,
            source_external_id="price-001",
            product_external_id="prod-001",
            price=Decimal("151500"),
            currency_code="860",
            effective_from=datetime.now(UTC) - timedelta(days=2),
        ),
    )
    store.upsert_sale_v2(
        NormalizedSale(
            organization_id=business.business_id,
            source_external_id="268805991",
            sale_number="268805991",
            amount=Decimal("606000"),
            currency="860",
            status="won",
            sale_at=datetime.now(UTC) - timedelta(days=1),
            metadata={"sales_manager_code": "M-01"},
        ),
    )
    store.upsert_sale_item(
        NormalizedSaleItem(
            organization_id=business.business_id,
            source_external_id="item-001",
            sale_external_id="268805991",
            product_external_id="prod-001",
            quantity=Decimal("4"),
            unit_price=Decimal("151500"),
            amount=Decimal("606000"),
            currency="860",
        ),
    )
    store.upsert_sale_v2(
        NormalizedSale(
            organization_id=business.business_id,
            source_external_id="268802974",
            sale_number="268802974",
            amount=Decimal("100000"),
            currency="860",
            status="won",
            sale_at=datetime.now(UTC) - timedelta(days=400),
            metadata={"sales_manager_code": "M-02"},
        ),
    )
    store.upsert_payment(
        Payment(
            organization_id=business.business_id,
            source_external_id="payment-001",
            sale_external_id="268805991",
            amount=Decimal("606000"),
            currency="860",
            paid_at=datetime.now(UTC) - timedelta(days=1),
            method="cash",
        ),
    )
    store.upsert_finance_entry(
        FinanceEntry(
            business_id=business.business_id,
            external_ref="expense-001",
            entry_type=FinanceEntryType.EXPENSE,
            category="ads",
            amount=Decimal("100000"),
            currency="860",
            occurred_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    store.upsert_marketing_activity(
        MarketingActivity(
            business_id=business.business_id,
            external_ref="mkt-001",
            channel=MarketingChannel.META_ADS,
            campaign_name="Launch",
            impressions=2000,
            clicks=120,
            conversions=15,
            spend=Decimal("35000"),
            currency="860",
            occurred_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    store.upsert_inventory_balance(
        InventoryBalance(
            organization_id=business.business_id,
            source_external_id="inv-001",
            warehouse_external_id="wh-001",
            product_external_id="prod-001",
            quantity=Decimal("20"),
            balance_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    store.upsert_visit(
        Visit(
            organization_id=business.business_id,
            source_external_id="visit-001",
            customer_external_id="contact-001",
            visited_at=datetime.now(UTC) - timedelta(days=1),
            status="completed",
        ),
    )
    return store, business


def _client_for_store(store: InMemoryCoreDataLayer) -> TestClient:
    app.dependency_overrides[get_core_store] = lambda: store
    return TestClient(app)


def test_dashboard_overview_exposes_ai_workspace_payload() -> None:
    store, business = _seed_ai_workspace_store()
    client = _client_for_store(store)

    try:
        response = client.get(
            "/api/v1/dashboard/overview",
            params={"business_id": str(business.business_id)},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert payload["analytics_snapshot"]["business_count"] == 1
    assert payload["analytics_snapshot"]["smartup_organization_count"] == 1
    revenue_kpi = next(
        item for item in payload["analytics_snapshot"]["kpis"] if item["key"] == "revenue"
    )
    orders_kpi = next(
        item for item in payload["analytics_snapshot"]["kpis"] if item["key"] == "orders"
    )
    sold_units_kpi = next(
        item for item in payload["analytics_snapshot"]["kpis"] if item["key"] == "sold_units"
    )

    assert Decimal(str(revenue_kpi["current_value"])) == Decimal("606000")
    assert Decimal(str(orders_kpi["current_value"])) == Decimal("1")
    assert Decimal(str(sold_units_kpi["current_value"])) == Decimal("4")

    assert payload["ai_workspace"]["widget_locks_supported"] is True
    widget_types = {widget["widget_type"] for widget in payload["ai_workspace"]["widgets"]}
    assert "kpi" in widget_types
    assert "line_chart" in widget_types
    assert "ranking" in widget_types
    assert "table" in widget_types
    assert "ai_recommendation" in widget_types
    assert payload["ai_insights"]
    assert payload["ai_workspace"]["insights"]
    assert payload["ai_workspace"]["insights"][0]["summary"]


def test_dashboard_executive_workspace_route_returns_structured_workspace() -> None:
    store, business = _seed_ai_workspace_store()
    client = _client_for_store(store)

    try:
        response = client.get(
            "/api/v1/dashboard/executive-workspace",
            params={"business_id": str(business.business_id)},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert payload["snapshot"]["business_count"] == 1
    assert payload["snapshot"]["kpis"]
    assert len(payload["insights"]) >= 4
    assert len(payload["widgets"]) >= 6
    assert "kpi" in {widget["widget_type"] for widget in payload["widgets"]}
    assert "line_chart" in {widget["widget_type"] for widget in payload["widgets"]}
