"""Tests for historical SmartUp migration."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import httpx

from app.core.data_layer.service import InMemoryCoreDataLayer
from app.integrations.smartup.connector import SmartUpConnector
from app.integrations.smartup.history import SmartUpHistoricalImportRunner
from app.integrations.smartup.mapping import SMARTUP_CORE_MAPPING_V1
from app.integrations.smartup.models import (
    SMARTUP_INTEGRATION_UUID,
    SmartUpMigrationMode,
    SmartUpOrganization,
    SmartUpRawRecord,
    SmartUpRawRecordStatus,
)
from app.integrations.smartup.normalizers.sale import SaleNormalizer
from app.integrations.smartup.operations import _ENTITY_IMPORT_PLAN


class FakeSmartUpClient:
    """Deterministic fake SmartUp client for tests."""

    def request_json(self, mapping, payload):  # noqa: ANN001
        if mapping.name == "Legal entities":
            return {
                "legal_person": [
                    {
                        "person_id": "lp-001",
                        "code": "C-001",
                        "name": "Example LLC",
                        "short_name": "Example",
                        "main_phone": "+998900000000",
                        "email": "info@example.uz",
                        "state": "A",
                    },
                ]
            }
        if mapping.name == "Inventory":
            return {
                "inventory": [
                    {
                        "product_id": "prd-001",
                        "code": "P-001",
                        "name": "Product One",
                        "short_name": "Prod 1",
                        "measure_code": "pcs",
                        "producer_code": "SUP-01",
                    },
                ]
            }
        if mapping.name == "Product groups":
            return {
                "product_group": [
                    {
                        "product_group_id": "grp-001",
                        "code": "G-001",
                        "name": "Group One",
                        "state": "A",
                    },
                ]
            }
        if mapping.name == "Service export":
            return {
                "service": [
                    {
                        "service_id": "srv-001",
                        "code": "S-001",
                        "name": "Service One",
                        "short_name": "Srv 1",
                    },
                ]
            }
        if mapping.name == "Workspaces":
            return {
                "room": [
                    {
                        "room_id": "room-001",
                        "room_code": "WH-001",
                        "room_name": "Main Warehouse",
                    },
                ]
            }
        if mapping.name == "Orders":
            return {
                "order": [
                    {
                        "deal_id": "deal-001",
                        "external_id": "ext-deal-001",
                        "person_code": "C-001",
                        "total_amount": "120.50",
                        "currency_code": "860",
                        "status": "B#V",
                        "deal_time": "2026-07-20 10:15:00",
                        "delivery_date": "20.07.2026",
                    },
                ]
            }
        if mapping.name == "Client payments":
            return {
                "cashin": [
                    {
                        "cashin_id": "pay-001",
                        "external_id": "pay-ext-001",
                        "deal_id": "deal-001",
                        "amount": "35.00",
                        "currency_code": "860",
                        "cashin_date": "2026-07-21 09:00:00",
                    },
                ]
            }
        if mapping.name == "Cash operations":
            return {
                "cash_operation": [
                    {
                        "operation_id": "op-001",
                        "external_id": "op-ext-001",
                        "amount": "15.00",
                        "currency_code": "860",
                        "operation_date": "2026-07-21 10:00:00",
                        "description": "Cash expense",
                    },
                ]
            }
        if mapping.name == "Bank statements":
            return {
                "bank_operation": [
                    {
                        "operation_id": "bank-001",
                        "external_id": "bank-ext-001",
                        "amount": "90.00",
                        "currency_code": "860",
                        "operation_date": "2026-07-21 11:00:00",
                        "description": "Bank receipt",
                    },
                ]
            }
        if mapping.name == "Visits":
            return {
                "visit": [
                    {
                        "visit_id": "visit-001",
                        "external_id": "visit-ext-001",
                        "person_code": "C-001",
                        "visit_date": "2026-07-22 12:00:00",
                        "visit_status": "done",
                    },
                ]
            }
        if mapping.name == "Inventory balance":
            return {
                "balance": [
                    {
                        "warehouse_code": "WH-001",
                        "product_code": "P-001",
                        "quantity": "12",
                        "date": "2026-07-23",
                    },
                ]
            }
        return {}


class CapturingOrdersClient(FakeSmartUpClient):
    """Fake client that captures SmartUp requests for Orders."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def request_json(self, mapping, payload):  # noqa: ANN001
        self.calls.append((mapping.name, payload))
        if mapping.name == "Orders":
            return {
                "order": [
                    {
                        "deal_id": "268805991",
                        "external_id": "ext-deal-001",
                        "person_code": "C-001",
                        "total_amount": "606000",
                        "currency_code": "860",
                        "status": "B#N",
                        "deal_time": "2026-08-03 10:15:00",
                        "delivery_date": "03.08.2026",
                        "order_products": [
                            {
                                "product_code": "935",
                                "product_name": "DAILY MOISTURE SPF PA++++ 50+/ 50ml [935]",
                                "order_quant": "4",
                                "sold_amount": "606000",
                                "product_price": "151500",
                                "margin_amount": "0",
                                "vat_amount": "0",
                                "details": [
                                    {
                                        "card_code": None,
                                        "sold_quant": "4",
                                        "expiry_date": None,
                                        "batch_number": "20260720000002561026",
                                    },
                                ],
                            },
                        ],
                    },
                ]
            }
        return super().request_json(mapping, payload)


class PermissionDeniedSmartUpClient(FakeSmartUpClient):
    """Fake client that returns a documented 403 upstream error."""

    def request_json(self, mapping, payload):  # noqa: ANN001
        if mapping.name == "Return reason export":
            request = httpx.Request(
                "POST",
                "https://smartup.online/b/anor/mxsx/mdeal/return_reason$export",
            )
            response = httpx.Response(
                403,
                request=request,
                text="Forbidden",
                headers={"content-type": "text/plain"},
            )
            raise httpx.HTTPStatusError("Forbidden", request=request, response=response)
        return super().request_json(mapping, payload)


def test_history_runner_imports_full_history_into_single_business() -> None:
    store = InMemoryCoreDataLayer()
    selected_names = {"Legal entities", "Orders"}
    connector = SmartUpConnector(
        mappings=tuple(
            mapping for mapping in SMARTUP_CORE_MAPPING_V1 if mapping.name in selected_names
        ),
    )
    runner = SmartUpHistoricalImportRunner(
        client=FakeSmartUpClient(),
        target=store,
        business_id=UUID("11111111-1111-1111-1111-111111111111"),
        business_name="Example Business",
        connector=connector,
    )

    counters = runner.run(
        history_start=datetime(2026, 7, 1, tzinfo=UTC),
        history_end=datetime(2026, 7, 8, tzinfo=UTC),
        chunk_days=7,
    )

    assert counters["batches"] == 2
    assert counters["errors"] == 0
    assert counters["records"] >= 2

    businesses = list(store.list_businesses())
    contacts = list(store.list_contacts())
    sales = list(store.list_sales())
    source_systems = list(store.list_source_systems())
    batches = list(store.list_ingestion_batches())
    records = list(store.list_records())
    raw_records = list(store.list_smartup_raw_records())

    assert len(businesses) == 1
    assert businesses[0].business_id == UUID("11111111-1111-1111-1111-111111111111")
    assert len(contacts) == 1
    assert len(sales) == 1
    assert len(source_systems) == 1
    assert source_systems[0].name == "SmartUp"
    assert len(batches) == 2
    assert len(raw_records) >= 2
    assert all(batch.status.name == "COMPLETED" for batch in batches)
    assert all(batch.source_system_id == source_systems[0].source_system_id for batch in batches)
    assert len(records) >= 2
    assert sales[0].amount == Decimal("120.50")
    assert sales[0].contact_id is not None


def test_history_runner_keeps_full_backfill_chunks_at_thirty_days_for_orders() -> None:
    store = InMemoryCoreDataLayer()
    connector = SmartUpConnector(
        mappings=tuple(mapping for mapping in SMARTUP_CORE_MAPPING_V1 if mapping.name == "Orders"),
    )
    client = CapturingOrdersClient()
    runner = SmartUpHistoricalImportRunner(
        client=client,
        target=store,
        business_id=UUID("44444444-4444-4444-4444-444444444444"),
        business_name="Example Business 4",
        connector=connector,
    )

    counters = runner.run(
        history_start=datetime(2026, 7, 1, tzinfo=UTC),
        history_end=datetime(2026, 8, 10, tzinfo=UTC),
        migration_mode=SmartUpMigrationMode.FULL_BACKFILL,
    )

    assert counters["errors"] == 0
    assert counters["batches"] == 2
    assert client.calls[0][0] == "Orders"
    assert client.calls[0][1] == {
        "begin_deal_date": "01.07.2026",
        "end_deal_date": "31.07.2026",
    }


def test_entity_import_plan_uses_existing_mapping_names() -> None:
    mapping_names = {mapping.name for mapping in SMARTUP_CORE_MAPPING_V1}

    for entity_name, names in _ENTITY_IMPORT_PLAN.items():
        assert set(names).issubset(mapping_names), entity_name


def test_sale_normalizer_and_history_runner_preserve_order_quantity_and_sale_item() -> None:
    raw_record = SmartUpRawRecord(
        organization_id=UUID("66666666-6666-6666-6666-666666666666"),
        filial_id="16114091",
        entity_type="sales",
        external_id="268805991",
        source_endpoint="/b/trade/txs/tdeal/order$export",
        response_payload={
            "deal_id": "268805991",
            "external_id": "ext-deal-001",
            "person_code": "C-001",
            "total_amount": "606000",
            "currency_code": "860",
            "status": "B#N",
            "deal_time": "2026-08-03 10:15:00",
            "delivery_date": "03.08.2026",
            "order_products": [
                {
                    "product_code": "935",
                    "product_name": "DAILY MOISTURE SPF PA++++ 50+/ 50ml [935]",
                    "order_quant": "4",
                    "sold_amount": "606000",
                    "product_price": "151500",
                    "margin_amount": "0",
                    "vat_amount": "0",
                    "details": [
                        {
                            "card_code": None,
                            "sold_quant": "4",
                            "expiry_date": None,
                            "batch_number": "20260720000002561026",
                        },
                    ],
                },
            ],
        },
    )

    normalized = SaleNormalizer().normalize(raw_record)
    assert normalized.related_entities
    sale_item_payload = next(
        entity.data for entity in normalized.related_entities if entity.entity_type == "sale_items"
    )
    assert sale_item_payload["quantity"] == Decimal("4")
    assert sale_item_payload["unit_price"] == Decimal("151500")
    assert sale_item_payload["amount"] == Decimal("606000")
    assert sale_item_payload["sale_id"] is None

    store = InMemoryCoreDataLayer()
    connector = SmartUpConnector(
        mappings=tuple(mapping for mapping in SMARTUP_CORE_MAPPING_V1 if mapping.name == "Orders"),
    )
    runner = SmartUpHistoricalImportRunner(
        client=CapturingOrdersClient(),
        target=store,
        business_id=UUID("66666666-6666-6666-6666-666666666666"),
        business_name="Example Business 6",
        connector=connector,
    )

    counters = runner.run(
        history_start=datetime(2026, 8, 3, tzinfo=UTC),
        history_end=datetime(2026, 8, 10, tzinfo=UTC),
        migration_mode=SmartUpMigrationMode.FULL_BACKFILL,
    )

    sales = list(store.list_sales_v2())
    sale_items = list(store.list_sale_items())
    raw_records = list(store.list_smartup_raw_records())

    assert counters["errors"] == 0
    assert counters["records"] >= 1
    assert len(raw_records) == 1
    assert len(raw_records[0].response_payload["order_products"]) == 1
    assert len(sales) == 1
    assert len(sale_items) == 1
    assert sale_items[0].sale_id == sales[0].id
    assert sale_items[0].quantity == Decimal("4")
    assert sale_items[0].unit_price == Decimal("151500")
    assert sale_items[0].amount == Decimal("606000")


def test_history_runner_uses_sale_external_id_for_sale_item_identity() -> None:
    class DuplicateProductOrdersClient(CapturingOrdersClient):
        def request_json(self, mapping, payload):  # noqa: ANN001
            if mapping.name == "Orders":
                return {
                    "order": [
                        {
                            "deal_id": "deal-001",
                            "external_id": "ext-deal-001",
                            "person_code": "C-001",
                            "total_amount": "606000",
                            "currency_code": "860",
                            "status": "B#N",
                            "deal_time": "2026-08-03 10:15:00",
                            "delivery_date": "03.08.2026",
                            "order_products": [
                                {
                                    "product_code": "935",
                                    "order_quant": "2",
                                    "sold_amount": "303000",
                                    "product_price": "151500",
                                    "details": [{"sold_quant": "2"}],
                                },
                            ],
                        },
                        {
                            "deal_id": "deal-002",
                            "external_id": "ext-deal-002",
                            "person_code": "C-001",
                            "total_amount": "151500",
                            "currency_code": "860",
                            "status": "B#N",
                            "deal_time": "2026-08-03 11:15:00",
                            "delivery_date": "03.08.2026",
                            "order_products": [
                                {
                                    "product_code": "935",
                                    "order_quant": "1",
                                    "sold_amount": "151500",
                                    "product_price": "151500",
                                    "details": [{"sold_quant": "1"}],
                                },
                            ],
                        },
                    ]
                }
            return super().request_json(mapping, payload)

    store = InMemoryCoreDataLayer()
    connector = SmartUpConnector(
        mappings=tuple(mapping for mapping in SMARTUP_CORE_MAPPING_V1 if mapping.name == "Orders"),
    )
    runner = SmartUpHistoricalImportRunner(
        client=DuplicateProductOrdersClient(),
        target=store,
        business_id=UUID("77777777-7777-7777-7777-777777777777"),
        business_name="Example Business 7",
        connector=connector,
    )

    counters = runner.run(
        history_start=datetime(2026, 8, 3, tzinfo=UTC),
        history_end=datetime(2026, 8, 10, tzinfo=UTC),
        migration_mode=SmartUpMigrationMode.FULL_BACKFILL,
    )

    sales = list(store.list_sales_v2())
    sale_items = list(store.list_sale_items())

    assert counters["errors"] == 0
    assert len(sales) == 2
    assert len(sale_items) == 2
    assert {item.sale_external_id for item in sale_items} == {"deal-001", "deal-002"}
    assert {item.source_external_id for item in sale_items} == {"deal-001:1", "deal-002:1"}


def test_sale_normalizer_maps_smartup_raw_status_to_semantic_status() -> None:
    raw_record = SmartUpRawRecord(
        organization_id=UUID("66666666-6666-6666-6666-666666666666"),
        filial_id="16114091",
        entity_type="sales",
        external_id="268805991",
        source_endpoint="/b/trade/txs/tdeal/order$export",
        response_payload={
            "deal_id": "268805991",
            "total_amount": "606000",
            "currency_code": "860",
            "status": "B#N",
            "order_products": [
                {
                    "product_code": "935",
                    "order_quant": "4",
                    "sold_amount": "606000",
                    "product_price": "151500",
                    "details": [{"sold_quant": "4"}],
                }
            ],
        },
    )

    normalized = SaleNormalizer().normalize(raw_record)

    assert normalized.normalized_data["status"] == "new"
    assert normalized.normalized_data["amount"] == Decimal("606000")
    assert normalized.related_entities


def test_connector_uses_documented_date_format_for_history_windows() -> None:
    connector = SmartUpConnector(
        mappings=tuple(
            mapping for mapping in SMARTUP_CORE_MAPPING_V1 if mapping.name == "Legal entities"
        ),
    )

    tasks = connector.build_history_plan(
        datetime(2026, 7, 1, tzinfo=UTC),
        datetime(2026, 7, 8, tzinfo=UTC),
        chunk_days=7,
    )

    assert len(tasks) == 1
    assert tasks[0].payload_template["begin_created_on"] == "01.07.2026"
    assert tasks[0].payload_template["end_created_on"] == "08.07.2026"


def test_history_runner_uses_filial_codes_array_for_contracts() -> None:
    runner = SmartUpHistoricalImportRunner(
        client=FakeSmartUpClient(),
        target=InMemoryCoreDataLayer(),
        business_id=UUID("33333333-3333-3333-3333-333333333333"),
        business_name="Example Business 3",
    )
    mapping = next(mapping for mapping in SMARTUP_CORE_MAPPING_V1 if mapping.name == "Contracts")

    payload = runner._prepare_request_payload(mapping, {})

    assert payload == {}


def test_history_runner_clean_text_trims_values_and_handles_empty_inputs() -> None:
    assert SmartUpHistoricalImportRunner._clean_text(None) is None
    assert SmartUpHistoricalImportRunner._clean_text("   ") is None
    assert SmartUpHistoricalImportRunner._clean_text("  hello  ") == "hello"
    assert SmartUpHistoricalImportRunner._clean_text(123) == "123"


def test_history_runner_backfills_inventory_balance_filial_code_from_raw_orders() -> None:
    store = InMemoryCoreDataLayer()
    organization_id = UUID("66666666-6666-6666-6666-666666666666")
    store.upsert_smartup_organization(
        SmartUpOrganization(
            id=organization_id,
            integration_id=SMARTUP_INTEGRATION_UUID,
            name="Administration",
            company_id="11300",
            filial_id="14475622",
            filial_code=None,
            project_code="trade",
            is_active=True,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization_id,
            filial_id="14475622",
            entity_type="sales",
            external_id="268805991",
            source_endpoint="/b/trade/txs/tdeal/order$export",
            request_payload={"begin_deal_date": "01.08.2026", "end_deal_date": "02.08.2026"},
            response_payload={
                "order": [
                    {
                        "deal_id": "268805991",
                        "filial_id": "14475622",
                        "filial_code": "16114091",
                    },
                ]
            },
            processing_status=SmartUpRawRecordStatus.NORMALIZED,
        ),
    )

    class CapturingInventoryClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def request_json(self, mapping, payload):  # noqa: ANN001
            self.calls.append({"mapping": mapping.name, "payload": payload})
            return {
                "balance": [
                    {
                        "warehouse_code": "WH-001",
                        "product_code": "P-001",
                        "quantity": "12",
                        "date": "2026-08-10",
                    },
                ]
            }

    client = CapturingInventoryClient()
    runner = SmartUpHistoricalImportRunner(
        client=client,
        target=store,
        business_id=organization_id,
        business_name="Administration",
        smartup_filial_id="14475622",
        connector=SmartUpConnector(
            mappings=tuple(
                mapping
                for mapping in SMARTUP_CORE_MAPPING_V1
                if mapping.name == "Inventory balance"
            ),
        ),
    )

    counters = runner.run(
        history_start=datetime(2026, 8, 3, tzinfo=UTC),
        history_end=datetime(2026, 8, 10, tzinfo=UTC),
        chunk_days=7,
    )

    organization = store.get_smartup_organization(organization_id)
    batches = list(store.list_migration_batches(organization_id=organization_id))

    assert counters["errors"] == 0
    assert client.calls == [
        {
            "mapping": "Inventory balance",
            "payload": {
                "filial_code": "16114091",
                "begin_date": "03.08.2026",
                "end_date": "10.08.2026",
            },
        },
    ]
    assert organization is not None
    assert organization.filial_code == "16114091"
    assert len(batches) == 1
    assert batches[0].status.value == "completed"
    assert batches[0].request_payload == {
        "filial_code": "16114091",
        "begin_date": "03.08.2026",
        "end_date": "10.08.2026",
    }


def test_history_runner_skips_unpaired_inventory_balance_filial_code() -> None:
    store = InMemoryCoreDataLayer()
    organization_id = UUID("66666666-6666-6666-6666-666666666667")
    store.upsert_smartup_organization(
        SmartUpOrganization(
            id=organization_id,
            integration_id=SMARTUP_INTEGRATION_UUID,
            name="Administration",
            company_id="11300",
            filial_id="14475622",
            filial_code=None,
            project_code="trade",
            is_active=True,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization_id,
            filial_id="14475622",
            entity_type="sales",
            external_id="268805991",
            source_endpoint="/b/trade/txs/tdeal/order$export",
            request_payload={"begin_deal_date": "01.08.2026", "end_deal_date": "02.08.2026"},
            response_payload={
                "order": [
                    {
                        "deal_id": "268805991",
                        "filial_code": "16114091",
                    },
                ]
            },
            processing_status=SmartUpRawRecordStatus.NORMALIZED,
        ),
    )

    class FailingInventoryClient:
        def request_json(self, mapping, payload):  # noqa: ANN001
            raise AssertionError("Inventory balance request must not be sent")

    runner = SmartUpHistoricalImportRunner(
        client=FailingInventoryClient(),
        target=store,
        business_id=organization_id,
        business_name="Administration",
        smartup_filial_id="14475622",
        connector=SmartUpConnector(
            mappings=tuple(
                mapping
                for mapping in SMARTUP_CORE_MAPPING_V1
                if mapping.name == "Inventory balance"
            ),
        ),
    )

    counters = runner.run(
        history_start=datetime(2026, 8, 3, tzinfo=UTC),
        history_end=datetime(2026, 8, 10, tzinfo=UTC),
        chunk_days=7,
    )

    batches = list(store.list_migration_batches(organization_id=organization_id))
    organization = store.get_smartup_organization(organization_id)

    assert counters["errors"] == 1
    assert len(batches) == 1
    assert batches[0].status.value == "failed"
    assert batches[0].error_message == "missing_filial_code"
    assert batches[0].request_payload == {
        "begin_date": "03.08.2026",
        "end_date": "10.08.2026",
    }
    assert organization is not None
    assert organization.filial_code is None


def test_history_runner_marks_inventory_balance_missing_filial_code_without_request() -> None:
    store = InMemoryCoreDataLayer()
    organization_id = UUID("77777777-7777-7777-7777-777777777777")
    store.upsert_smartup_organization(
        SmartUpOrganization(
            id=organization_id,
            integration_id=SMARTUP_INTEGRATION_UUID,
            name="Administration",
            company_id="11300",
            filial_id="14475622",
            filial_code=None,
            project_code="trade",
            is_active=True,
        ),
    )

    class FailingInventoryClient:
        def request_json(self, mapping, payload):  # noqa: ANN001
            raise AssertionError("Inventory balance request must not be sent")

    runner = SmartUpHistoricalImportRunner(
        client=FailingInventoryClient(),
        target=store,
        business_id=organization_id,
        business_name="Administration",
        smartup_filial_id="14475622",
        connector=SmartUpConnector(
            mappings=tuple(
                mapping
                for mapping in SMARTUP_CORE_MAPPING_V1
                if mapping.name == "Inventory balance"
            ),
        ),
    )

    counters = runner.run(
        history_start=datetime(2026, 8, 3, tzinfo=UTC),
        history_end=datetime(2026, 8, 10, tzinfo=UTC),
        chunk_days=7,
    )

    batches = list(store.list_migration_batches(organization_id=organization_id))

    assert counters["errors"] == 1
    assert len(batches) == 1
    assert batches[0].status.value == "failed"
    assert batches[0].error_message == "missing_filial_code"
    assert batches[0].request_payload == {
        "begin_date": "03.08.2026",
        "end_date": "10.08.2026",
    }


def test_history_runner_marks_equipment_balance_missing_filial_code_without_request() -> None:
    store = InMemoryCoreDataLayer()
    organization_id = UUID("88888888-8888-8888-8888-888888888888")
    store.upsert_smartup_organization(
        SmartUpOrganization(
            id=organization_id,
            integration_id=SMARTUP_INTEGRATION_UUID,
            name="Administration",
            company_id="11300",
            filial_id="14475622",
            filial_code=None,
            project_code="trade",
            is_active=True,
        ),
    )

    class FailingEquipmentClient:
        def request_json(self, mapping, payload):  # noqa: ANN001
            raise AssertionError("Equipment balance request must not be sent")

    runner = SmartUpHistoricalImportRunner(
        client=FailingEquipmentClient(),
        target=store,
        business_id=organization_id,
        business_name="Administration",
        smartup_filial_id="14475622",
        connector=SmartUpConnector(
            mappings=tuple(
                mapping
                for mapping in SMARTUP_CORE_MAPPING_V1
                if mapping.name == "Equipment balance"
            ),
        ),
    )

    counters = runner.run(
        history_start=datetime(2026, 8, 3, tzinfo=UTC),
        history_end=datetime(2026, 8, 10, tzinfo=UTC),
        chunk_days=7,
    )

    batches = list(store.list_migration_batches(organization_id=organization_id))

    assert counters["errors"] == 1
    assert len(batches) == 1
    assert batches[0].status.value == "failed"
    assert batches[0].error_message == "missing_filial_code"
    assert batches[0].request_payload == {}


def test_history_runner_uses_documented_movement_window_fields() -> None:
    runner = SmartUpHistoricalImportRunner(
        client=FakeSmartUpClient(),
        target=InMemoryCoreDataLayer(),
        business_id=UUID("55555555-5555-5555-5555-555555555555"),
        business_name="Example Business 5",
    )
    cross_mapping = next(
        mapping
        for mapping in SMARTUP_CORE_MAPPING_V1
        if mapping.name == "Cross-organizational movement export"
    )
    internal_mapping = next(
        mapping for mapping in SMARTUP_CORE_MAPPING_V1 if mapping.name == "Internal movement export"
    )

    cross_payload = runner._prepare_request_payload(
        cross_mapping,
        {},
        window_start=datetime(2026, 8, 3, tzinfo=UTC),
        window_end=datetime(2026, 8, 10, tzinfo=UTC),
    )
    internal_payload = runner._prepare_request_payload(
        internal_mapping,
        {},
        window_start=datetime(2026, 8, 3, tzinfo=UTC),
        window_end=datetime(2026, 8, 10, tzinfo=UTC),
    )

    assert cross_payload["begin_from_date"] == "03.08.2026"
    assert cross_payload["end_from_date"] == "10.08.2026"
    assert internal_payload["begin_from_movement_date"] == "03.08.2026"
    assert internal_payload["end_from_movement_date"] == "10.08.2026"


def test_history_runner_marks_return_reason_403_as_permission_denied() -> None:
    store = InMemoryCoreDataLayer()
    connector = SmartUpConnector(
        mappings=tuple(
            mapping
            for mapping in SMARTUP_CORE_MAPPING_V1
            if mapping.name in {"Legal entities", "Return reason export"}
        ),
    )
    runner = SmartUpHistoricalImportRunner(
        client=PermissionDeniedSmartUpClient(),
        target=store,
        business_id=UUID("55555555-5555-5555-5555-555555555555"),
        business_name="Example Business 5",
        connector=connector,
    )

    counters = runner.run(
        history_start=datetime(2026, 7, 1, tzinfo=UTC),
        history_end=datetime(2026, 7, 8, tzinfo=UTC),
        chunk_days=7,
    )

    batches = list(
        store.list_migration_batches(
            organization_id=UUID("55555555-5555-5555-5555-555555555555"),
        ),
    )
    errors = list(store.list_ingestion_errors())

    assert counters["batches"] == 2
    assert counters["errors"] == 1
    assert any(batch.status.value == "completed" for batch in batches)
    denied_batches = [batch for batch in batches if batch.status.value == "permission_denied"]
    assert len(denied_batches) == 1
    assert denied_batches[0].upstream_status == 403
    assert denied_batches[0].upstream_response == "Forbidden"
    assert any(error.error_code == "SMARTUP_PERMISSION_DENIED" for error in errors)


def test_history_runner_normalizes_catalog_stock_and_finance_sources() -> None:
    store = InMemoryCoreDataLayer()
    store.upsert_smartup_organization(
        SmartUpOrganization(
            id=UUID("22222222-2222-2222-2222-222222222222"),
            integration_id=SMARTUP_INTEGRATION_UUID,
            name="Example Business 2",
            company_id="11300",
            filial_id="14475622",
            filial_code=None,
            project_code="trade",
            is_active=True,
            metadata={
                "smartup_verified_filial_id": "14475622",
                "smartup_verified_filial_code": "16114091",
                "smartup_verified_filial_code_by_filial_id": {
                    "14475622": {
                        "filial_id": "14475622",
                        "filial_code": "16114091",
                        "source": "manual",
                        "raw_record_id": "verified-raw-record",
                    },
                },
            },
        ),
    )
    selected_names = {
        "Legal entities",
        "Inventory",
        "Product groups",
        "Service export",
        "Workspaces",
        "Client payments",
        "Cash operations",
        "Bank statements",
        "Visits",
        "Inventory balance",
    }
    connector = SmartUpConnector(
        mappings=tuple(
            mapping for mapping in SMARTUP_CORE_MAPPING_V1 if mapping.name in selected_names
        ),
    )
    runner = SmartUpHistoricalImportRunner(
        client=FakeSmartUpClient(),
        target=store,
        business_id=UUID("22222222-2222-2222-2222-222222222222"),
        business_name="Example Business 2",
        connector=connector,
    )

    counters = runner.run(
        history_start=datetime(2026, 7, 1, tzinfo=UTC),
        history_end=datetime(2026, 7, 28, tzinfo=UTC),
        chunk_days=30,
    )

    assert counters["errors"] == 0
    assert len(list(store.list_customers())) == 1
    assert len(list(store.list_products())) == 2
    assert len(list(store.list_product_categories())) == 1
    assert len(list(store.list_warehouses())) == 1
    assert len(list(store.list_payments())) == 1
    assert len(list(store.list_bank_operations())) == 2
    assert len(list(store.list_visits())) == 1
    assert len(list(store.list_inventory_balances())) == 1
