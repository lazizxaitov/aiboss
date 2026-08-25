"""Tests for the SmartUp mapping registry and connector blueprint."""

from datetime import UTC, datetime

from app.integrations.smartup.connector import SmartUpConnector, SmartUpSyncWindow
from app.integrations.smartup.mapping import get_smartup_mapping, get_smartup_mappings_by_group


def test_smartup_mapping_registry_contains_core_sources() -> None:
    orders = get_smartup_mapping("Orders")
    assert orders is not None
    assert orders.smartup_endpoint == "/b/trade/txs/tdeal/order$export"
    assert orders.target_table == "sales"

    master_data = get_smartup_mappings_by_group("master_data")
    assert any(mapping.name == "Legal entities" for mapping in master_data)
    assert any(mapping.name == "Inventory" for mapping in master_data)


def test_smartup_connector_builds_sync_plan() -> None:
    connector = SmartUpConnector(base_url="https://smartup.online")
    window = SmartUpSyncWindow(
        begin=datetime(2026, 7, 1, tzinfo=UTC),
        end=datetime(2026, 7, 28, tzinfo=UTC),
    )

    tasks = connector.build_sync_plan(window=window)

    assert tasks
    assert any(task.mapping_name == "Orders" for task in tasks)
    orders_task = next(task for task in tasks if task.mapping_name == "Orders")
    assert orders_task.endpoint == "https://smartup.online/b/trade/txs/tdeal/order$export"
    assert orders_task.payload_template["sync_mode"] == "incremental"
    assert orders_task.payload_template["begin_deal_date"] == "01.07.2026"
    assert orders_task.payload_template["end_deal_date"] == "28.07.2026"
