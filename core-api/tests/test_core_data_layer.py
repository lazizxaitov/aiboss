"""Tests for the core data layer and SmartUp migration pipeline."""

from datetime import UTC, datetime
from decimal import Decimal

from app.core.data_layer.entities import AppSetting, FinanceEntryType, MarketingChannel, SaleStage
from app.core.data_layer.migrations.smartup import (
    SmartUpBusinessRow,
    SmartUpContactRow,
    SmartUpExportBundle,
    SmartUpFinanceRow,
    SmartUpMarketingRow,
    SmartUpMigrationService,
    SmartUpSaleRow,
)
from app.core.data_layer.service import InMemoryCoreDataLayer


def test_in_memory_core_data_layer_supports_canonical_entities() -> None:
    store = InMemoryCoreDataLayer()
    bundle = SmartUpExportBundle(
        businesses=[
            SmartUpBusinessRow(
                external_business_id="su-biz-001",
                name="Acme LLC",
                legal_name="Acme LLC",
            ),
        ],
        contacts=[
            SmartUpContactRow(
                external_customer_id="su-cust-001",
                external_business_id="su-biz-001",
                full_name="John Doe",
                email="john@example.com",
            ),
        ],
        sales=[
            SmartUpSaleRow(
                external_sale_id="su-sale-001",
                external_business_id="su-biz-001",
                external_customer_id="su-cust-001",
                amount=Decimal("125.50"),
                currency="USD",
                stage=SaleStage.WON,
                occurred_at=datetime(2026, 7, 28, tzinfo=UTC),
            ),
        ],
        marketing=[
            SmartUpMarketingRow(
                external_activity_id="su-mkt-001",
                external_business_id="su-biz-001",
                channel=MarketingChannel.META_ADS,
                campaign_name="Launch",
                impressions=1000,
                clicks=120,
                conversions=12,
                spend=Decimal("45.00"),
                occurred_at=datetime(2026, 7, 28, tzinfo=UTC),
            ),
        ],
        finance=[
            SmartUpFinanceRow(
                external_entry_id="su-fin-001",
                external_business_id="su-biz-001",
                entry_type=FinanceEntryType.REVENUE,
                category="sales",
                amount=Decimal("125.50"),
                currency="USD",
                occurred_at=datetime(2026, 7, 28, tzinfo=UTC),
            ),
        ],
    )

    report = SmartUpMigrationService(target=store).import_bundle(bundle)

    assert report.businesses_imported == 1
    assert report.source_systems_imported == 1
    assert report.contacts_imported == 1
    assert report.sales_imported == 1
    assert report.marketing_imported == 1
    assert report.finance_imported == 1
    assert report.warnings == []

    businesses = list(store.list_businesses())
    source_systems = list(store.list_source_systems())
    contacts = list(store.list_contacts())
    sales = list(store.list_sales())
    marketing = list(store.list_marketing_activities())
    finance_entries = list(store.list_finance_entries())
    records = list(store.list_records())

    assert len(businesses) == 1
    assert len(source_systems) == 1
    assert len(contacts) == 1
    assert len(sales) == 1
    assert len(marketing) == 1
    assert len(finance_entries) == 1
    assert len(records) == 4

    assert sales[0].amount == Decimal("125.50")
    assert marketing[0].channel == MarketingChannel.META_ADS
    assert finance_entries[0].entry_type == FinanceEntryType.REVENUE


def test_in_memory_app_setting_upsert_is_idempotent_by_setting_key() -> None:
    store = InMemoryCoreDataLayer()

    first = store.upsert_app_setting(
        AppSetting(
            setting_key="smartup:organization_credentials:org-1",
            setting_value={"username": "demo", "password": "secret-1"},
        ),
    )
    second = store.upsert_app_setting(
        AppSetting(
            setting_key="smartup:organization_credentials:org-1",
            setting_value={"username": "demo", "password": "secret-2"},
        ),
    )

    stored = store.get_app_setting("smartup:organization_credentials:org-1")

    assert first.setting_key == second.setting_key == "smartup:organization_credentials:org-1"
    assert stored is not None
    assert stored.setting_value["password"] == "secret-2"
    assert len(list(store.list_app_settings())) == 1
