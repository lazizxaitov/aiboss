"""Tests for the SQLite storage adapter and DDL generation."""

import sqlite3
from uuid import UUID

from app.core.data_layer.entities import BusinessProfile, SourceSystem
from app.storage.sqlite import SQLiteCoreStore, render_core_data_layer_ddl


def test_sqlite_ddl_contains_core_tables() -> None:
    statements = render_core_data_layer_ddl()

    assert any("CREATE TABLE IF NOT EXISTS businesses" in statement for statement in statements)
    assert any("CREATE TABLE IF NOT EXISTS source_systems" in statement for statement in statements)
    assert any("CREATE TABLE IF NOT EXISTS core_records" in statement for statement in statements)
    assert any(
        "CREATE INDEX IF NOT EXISTS idx_sales_business_id_occurred_at" in statement
        for statement in statements
    )


def test_sqlite_store_writes_and_reads_businesses_and_sources() -> None:
    connection = sqlite3.connect(":memory:")
    store = SQLiteCoreStore.from_connection(connection)
    store.ensure_schema()

    business = BusinessProfile(
        business_id=UUID("11111111-1111-1111-1111-111111111111"),
        name="Example Business",
        display_name="Example",
        external_ref="smartup",
        metadata={},
    )
    source_system = SourceSystem(
        business_id=business.business_id,
        name="SmartUp",
        source_type="erp",
        external_ref="smartup",
        metadata={"base_url": "https://smartup.online"},
    )

    store.register_business(business)
    store.register_source_system(source_system)

    fetched_business = store.get_business(business.business_id)
    fetched_source = store.get_source_system(source_system.source_system_id)
    listed_businesses = list(store.list_businesses())
    listed_sources = list(store.list_source_systems())

    assert fetched_business is not None
    assert fetched_business.name == "Example Business"
    assert fetched_source is not None
    assert fetched_source.name == "SmartUp"
    assert fetched_source.business_id == business.business_id
    assert len(listed_businesses) == 1
    assert listed_businesses[0].business_id == business.business_id
    assert len(listed_sources) == 1
    assert listed_sources[0].source_system_id == source_system.source_system_id
    assert (
        connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='businesses'",
        ).fetchone()
        is not None
    )
    assert (
        connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='source_systems'",
        ).fetchone()
        is not None
    )
