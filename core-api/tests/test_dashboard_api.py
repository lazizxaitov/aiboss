"""Tests for the dashboard overview API."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.routes.dashboard import get_core_store
from app.core.data_layer.entities import (
    BusinessProfile,
    ContactProfile,
    FinanceEntry,
    FinanceEntryType,
    IngestionBatch,
    IngestionBatchStatus,
    MarketingActivity,
    MarketingChannel,
    SaleRecord,
    SaleStage,
    SourceSystem,
)
from app.core.data_layer.normalized import Sale as NormalizedSale
from app.core.data_layer.normalized import SaleItem as NormalizedSaleItem
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.main import app


def test_dashboard_overview_returns_business_metrics_from_store() -> None:
    store = InMemoryCoreDataLayer()
    business = store.register_business(
        BusinessProfile(
            name="Acme LLC",
            legal_name="Acme LLC",
            external_ref="su-biz-001",
        ),
    )
    store.register_source_system(
        SourceSystem(
            business_id=business.business_id,
            name="SmartUp",
            source_type="erp",
            external_ref="su-biz-001",
        ),
    )
    store.upsert_contact(
        ContactProfile(
            business_id=business.business_id,
            full_name="John Doe",
            email="john@example.com",
            external_ref="su-cust-001",
        ),
    )
    store.upsert_sale(
        SaleRecord(
            business_id=business.business_id,
            contact_id=None,
            external_ref="su-sale-001",
            amount=Decimal("125.50"),
            currency="USD",
            stage=SaleStage.WON,
            occurred_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    store.upsert_sale_v2(
        NormalizedSale(
            organization_id=business.business_id,
            source_external_id="su-sale-001",
            sale_number="su-sale-001",
            amount=Decimal("125.50"),
            currency="USD",
            status="won",
            sale_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    store.upsert_sale_item(
        NormalizedSaleItem(
            organization_id=business.business_id,
            source_external_id="su-sale-item-001",
            sale_external_id="su-sale-001",
            product_external_id="su-product-001",
            quantity=Decimal("4"),
            unit_price=Decimal("31.375"),
            amount=Decimal("125.50"),
            currency="USD",
        ),
    )
    store.upsert_sale(
        SaleRecord(
            business_id=business.business_id,
            contact_id=None,
            external_ref="su-sale-002",
            amount=Decimal("80.00"),
            currency="USD",
            stage=SaleStage.LEAD,
            occurred_at=datetime.now(UTC) - timedelta(days=2),
        ),
    )
    store.upsert_sale_v2(
        NormalizedSale(
            organization_id=business.business_id,
            source_external_id="su-sale-002",
            sale_number="su-sale-002",
            amount=Decimal("80.00"),
            currency="USD",
            status="lead",
            sale_at=datetime.now(UTC) - timedelta(days=2),
        ),
    )
    store.upsert_marketing_activity(
        MarketingActivity(
            business_id=business.business_id,
            external_ref="su-mkt-001",
            channel=MarketingChannel.META_ADS,
            campaign_name="Launch",
            impressions=1000,
            clicks=120,
            conversions=12,
            spend=Decimal("45.00"),
            currency="USD",
            occurred_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    store.upsert_finance_entry(
        FinanceEntry(
            business_id=business.business_id,
            external_ref="su-fin-001",
            entry_type=FinanceEntryType.REVENUE,
            category="sales",
            amount=Decimal("125.50"),
            currency="USD",
            occurred_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    store.upsert_finance_entry(
        FinanceEntry(
            business_id=business.business_id,
            external_ref="su-fin-002",
            entry_type=FinanceEntryType.EXPENSE,
            category="ads",
            amount=Decimal("30.25"),
            currency="USD",
            occurred_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    store.upsert_ingestion_batch(
        IngestionBatch(
            business_id=business.business_id,
            source_system_id=None,
            batch_name="SmartUp full history",
            status=IngestionBatchStatus.COMPLETED,
            started_at=datetime.now(UTC) - timedelta(days=1, hours=1),
            finished_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )

    app.dependency_overrides[get_core_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get("/api/v1/dashboard/overview")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    payload = response.json()
    assert payload["analysis_engine"] == "Бизнес-аналитика"
    assert payload["analysis_note"]
    assert payload["freshness"]
    assert len(payload["data_summary"]) == 9
    assert payload["data_summary"][0]["label"] == "Выручка"
    assert payload["data_summary"][0]["value"] == "125,50 USD"
    assert len(payload["executive_summary"]) == 4
    assert payload["executive_summary"][0]["label"] == "Рост выручки"
    assert payload["executive_summary"][1]["label"] == "Денежный поток"
    assert len(payload["business_metrics"]) == 6
    metrics = {item["label"]: item["value"] for item in payload["business_metrics"]}
    assert metrics["Выручка"] == "125,50 USD"
    assert metrics["Получено денег"] == "125,50 USD"
    assert metrics["Расходы"] == "30,25 USD"
    assert metrics["Чистый денежный поток"] == "95,25 USD"
    assert metrics["Продано единиц"] == "4"
    assert metrics["Средний чек"] == "125,50 USD"
    assert payload["trend"]["title"] == "Динамика бизнеса"
    assert len(payload["trend"]["labels"]) == 12
    assert len(payload["trend"]["values"]) == 12
    assert len(payload["signals"]) == 4
    assert len(payload["structure"]) == 4
    assert len(payload["businesses"]) == 1
    assert payload["businesses"][0]["name"] == "Acme LLC"
    assert payload["businesses"][0]["contacts"] == 1
    assert len(payload["ai_insights"]) == 4


def test_dashboard_overview_normalizes_numeric_currency_codes() -> None:
    store = InMemoryCoreDataLayer()
    business = store.register_business(
        BusinessProfile(
            name="Uz Trade",
            legal_name="Uz Trade",
            external_ref="su-biz-uzs",
        ),
    )
    store.register_source_system(
        SourceSystem(
            business_id=business.business_id,
            name="SmartUp",
            source_type="erp",
            external_ref="su-biz-uzs",
        ),
    )
    store.upsert_sale(
        SaleRecord(
            business_id=business.business_id,
            contact_id=None,
            external_ref="su-sale-uzs",
            amount=Decimal("860"),
            currency="860",
            stage=SaleStage.WON,
            occurred_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    store.upsert_sale_v2(
        NormalizedSale(
            organization_id=business.business_id,
            source_external_id="su-sale-uzs",
            sale_number="su-sale-uzs",
            amount=Decimal("860"),
            currency="860",
            status="won",
            sale_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )

    app.dependency_overrides[get_core_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get("/api/v1/dashboard/overview")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    payload = response.json()
    metrics = {item["label"]: item["value"] for item in payload["business_metrics"]}
    assert metrics["Выручка"] == "860 UZS"


def test_dashboard_overview_uses_sales_revenue_without_payments() -> None:
    store = InMemoryCoreDataLayer()
    business = store.register_business(
        BusinessProfile(
            name="No Payments LLC",
            legal_name="No Payments LLC",
            external_ref="su-biz-no-pay",
        ),
    )
    store.register_source_system(
        SourceSystem(
            business_id=business.business_id,
            name="SmartUp",
            source_type="erp",
            external_ref="su-biz-no-pay",
        ),
    )
    store.upsert_sale_v2(
        NormalizedSale(
            organization_id=business.business_id,
            source_external_id="su-sale-no-pay",
            sale_number="su-sale-no-pay",
            amount=Decimal("250.00"),
            currency="USD",
            status="won",
            sale_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    store.upsert_sale_item(
        NormalizedSaleItem(
            organization_id=business.business_id,
            source_external_id="su-sale-no-pay-item",
            sale_external_id="su-sale-no-pay",
            product_external_id="su-product-no-pay",
            quantity=Decimal("2"),
            unit_price=Decimal("125"),
            amount=Decimal("250.00"),
            currency="USD",
        ),
    )

    app.dependency_overrides[get_core_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get("/api/v1/dashboard/overview")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    payload = response.json()
    metrics = {item["label"]: item["value"] for item in payload["business_metrics"]}
    assert metrics["Выручка"] == "250 USD"
    assert metrics["Получено денег"] == "0 USD"
    assert metrics["Продано единиц"] == "2"


def test_dashboard_overview_excludes_cancelled_sales_from_revenue() -> None:
    store = InMemoryCoreDataLayer()
    business = store.register_business(
        BusinessProfile(
            name="Cancelled Sales LLC",
            legal_name="Cancelled Sales LLC",
            external_ref="su-biz-cancelled",
        ),
    )
    store.register_source_system(
        SourceSystem(
            business_id=business.business_id,
            name="SmartUp",
            source_type="erp",
            external_ref="su-biz-cancelled",
        ),
    )
    store.upsert_sale_v2(
        NormalizedSale(
            organization_id=business.business_id,
            source_external_id="su-sale-won",
            sale_number="su-sale-won",
            amount=Decimal("100.00"),
            currency="USD",
            status="won",
            sale_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    store.upsert_sale_v2(
        NormalizedSale(
            organization_id=business.business_id,
            source_external_id="su-sale-refunded",
            sale_number="su-sale-refunded",
            amount=Decimal("50.00"),
            currency="USD",
            status="refunded",
            sale_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )

    app.dependency_overrides[get_core_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get("/api/v1/dashboard/overview")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    payload = response.json()
    metrics = {item["label"]: item["value"] for item in payload["business_metrics"]}
    assert metrics["Выручка"] == "50 USD"


def test_dashboard_overview_counts_new_sales_as_revenue() -> None:
    store = InMemoryCoreDataLayer()
    business = store.register_business(
        BusinessProfile(
            name="New Sales LLC",
            legal_name="New Sales LLC",
            external_ref="su-biz-new",
        ),
    )
    store.register_source_system(
        SourceSystem(
            business_id=business.business_id,
            name="SmartUp",
            source_type="erp",
            external_ref="su-biz-new",
        ),
    )
    store.upsert_sale_v2(
        NormalizedSale(
            organization_id=business.business_id,
            source_external_id="su-sale-new",
            sale_number="su-sale-new",
            amount=Decimal("606000"),
            currency="UZS",
            status="new",
            sale_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    store.upsert_sale_item(
        NormalizedSaleItem(
            organization_id=business.business_id,
            source_external_id="su-sale-item-new",
            sale_external_id="su-sale-new",
            product_external_id="su-product-new",
            quantity=Decimal("4"),
            unit_price=Decimal("151500"),
            amount=Decimal("606000"),
            currency="UZS",
        ),
    )

    app.dependency_overrides[get_core_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get("/api/v1/dashboard/overview")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    payload = response.json()
    metrics = {item["label"]: item["value"] for item in payload["business_metrics"]}
    assert metrics["Выручка"] == "606 000 UZS"
    assert metrics["Продано единиц"] == "4"
    assert metrics["Средний чек"] == "606 000 UZS"


def test_dashboard_overview_keeps_expenses_from_finance_entries() -> None:
    store = InMemoryCoreDataLayer()
    business = store.register_business(
        BusinessProfile(
            name="Expense LLC",
            legal_name="Expense LLC",
            external_ref="su-biz-expense",
        ),
    )
    store.register_source_system(
        SourceSystem(
            business_id=business.business_id,
            name="SmartUp",
            source_type="erp",
            external_ref="su-biz-expense",
        ),
    )
    store.upsert_sale_v2(
        NormalizedSale(
            organization_id=business.business_id,
            source_external_id="su-sale-expense",
            sale_number="su-sale-expense",
            amount=Decimal("120.00"),
            currency="USD",
            status="won",
            sale_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    store.upsert_finance_entry(
        FinanceEntry(
            business_id=business.business_id,
            external_ref="su-fin-expense",
            entry_type=FinanceEntryType.EXPENSE,
            category="ads",
            amount=Decimal("30.25"),
            currency="USD",
            occurred_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )

    app.dependency_overrides[get_core_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get("/api/v1/dashboard/overview")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    payload = response.json()
    metrics = {item["label"]: item["value"] for item in payload["business_metrics"]}
    assert metrics["Расходы"] == "30,25 USD"
    assert metrics["Получено денег"] == "0 USD"
    assert metrics["Чистый денежный поток"] == "-30,25 USD"


def test_dashboard_overview_sorts_business_breakdown_by_name() -> None:
    store = InMemoryCoreDataLayer()
    beta = store.register_business(
        BusinessProfile(
            name="Beta Group",
            legal_name="Beta Group",
            external_ref="su-biz-002",
        ),
    )
    acme = store.register_business(
        BusinessProfile(
            name="Acme LLC",
            legal_name="Acme LLC",
            external_ref="su-biz-001",
        ),
    )
    store.register_source_system(
        SourceSystem(
            business_id=beta.business_id,
            name="SmartUp",
            source_type="erp",
            external_ref="su-biz-002",
        ),
    )
    store.register_source_system(
        SourceSystem(
            business_id=acme.business_id,
            name="SmartUp",
            source_type="erp",
            external_ref="su-biz-001",
        ),
    )
    store.upsert_contact(
        ContactProfile(
            business_id=beta.business_id,
            full_name="Beta Contact",
        ),
    )
    store.upsert_contact(
        ContactProfile(
            business_id=acme.business_id,
            full_name="Acme Contact",
        ),
    )

    app.dependency_overrides[get_core_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get("/api/v1/dashboard/overview")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    payload = response.json()
    assert len(payload["businesses"]) == 2
    assert payload["businesses"][0]["name"] == "Acme LLC"
    assert payload["businesses"][1]["name"] == "Beta Group"
    assert payload["businesses"][0]["contacts"] == 1
    assert payload["businesses"][1]["contacts"] == 1
