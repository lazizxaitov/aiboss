"""Tests for the canonical core data layer schema."""

from app.core.data_layer.schema import CORE_DATA_LAYER_SCHEMA_V2


def test_core_schema_has_expected_tables_and_relations() -> None:
    assert CORE_DATA_LAYER_SCHEMA_V2.version == "v2"
    assert CORE_DATA_LAYER_SCHEMA_V2.table_names() == [
        "app_settings",
        "businesses",
        "source_systems",
        "contacts",
        "sales",
        "marketing_activities",
        "finance_entries",
        "kpi_snapshots",
        "core_records",
        "ingestion_batches",
        "ingestion_errors",
        "smartup_organizations",
        "smartup_migration_runs",
        "sync_checkpoints",
        "migration_batches",
        "inventory_snapshots",
        "smartup_raw_records",
        "normalization_issues",
        "normalized_customers",
        "normalized_product_categories",
        "normalized_products",
        "normalized_warehouses",
        "normalized_price_types",
        "normalized_product_prices",
        "normalized_sales",
        "normalized_sale_items",
        "normalized_payments",
        "normalized_inventory_balances",
        "normalized_visits",
        "normalized_bank_operations",
        "normalized_business_documents",
        "normalized_business_document_items",
        "canonical_organizations",
        "canonical_customer_groups",
        "canonical_customers",
        "canonical_product_categories",
        "canonical_products",
        "canonical_warehouses",
        "canonical_price_types",
        "canonical_product_prices",
        "canonical_sales_reps",
        "canonical_working_zones",
        "canonical_visits",
        "canonical_visit_stocks",
        "canonical_visit_quiz_answers",
        "canonical_visit_equipments",
        "canonical_visit_comments",
        "canonical_media_assets",
        "canonical_orders",
        "canonical_sales",
        "canonical_sale_items",
        "canonical_payments",
        "canonical_payment_allocations",
        "canonical_financial_accounts",
        "canonical_financial_operations",
        "canonical_customer_returns",
        "canonical_customer_return_items",
        "canonical_inventory_balances",
        "canonical_purchases",
        "canonical_purchase_items",
        "canonical_warehouse_receipts",
        "canonical_warehouse_receipt_items",
        "canonical_writeoffs",
        "canonical_writeoff_items",
        "canonical_supplier_returns",
        "canonical_supplier_return_items",
        "canonical_stocktakings",
        "canonical_stocktaking_items",
        "canonical_internal_movements",
        "canonical_internal_movement_items",
        "canonical_cross_org_movements",
        "canonical_cross_org_movement_items",
    ]

    businesses = CORE_DATA_LAYER_SCHEMA_V2.get_table("businesses")
    assert businesses is not None
    assert businesses.primary_key == "business_id"
    assert any(column.name == "metadata" for column in businesses.columns)

    sales_relations = [
        relation
        for relation in CORE_DATA_LAYER_SCHEMA_V2.relations
        if relation.source_table == "sales"
    ]
    assert any(relation.source_column == "business_id" for relation in sales_relations)
    assert any(relation.source_column == "contact_id" for relation in sales_relations)

    smartup_relations = [
        relation
        for relation in CORE_DATA_LAYER_SCHEMA_V2.relations
        if relation.source_table == "smartup_migration_runs"
    ]
    assert any(relation.source_column == "organization_id" for relation in smartup_relations)

    sale_item_table = CORE_DATA_LAYER_SCHEMA_V2.get_table("normalized_sale_items")
    assert sale_item_table is not None
    assert any(column.name == "sale_id" for column in sale_item_table.columns)
    assert any(column.name == "sale_external_id" for column in sale_item_table.columns)
    assert any(
        relation.source_table == "normalized_sale_items" and relation.source_column == "sale_id"
        for relation in CORE_DATA_LAYER_SCHEMA_V2.relations
    )
