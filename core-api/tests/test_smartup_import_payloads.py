"""Tests for documented SmartUp import payload builders."""

from datetime import date

from app.integrations.smartup import (
    SmartUpOrderActionImport,
    SmartUpOrderConsignmentImport,
    SmartUpOrderGiftImport,
    SmartUpOrderImportDocument,
    SmartUpOrderProductImport,
    SmartUpReturnActionImport,
    SmartUpReturnConsignmentImport,
    SmartUpReturnGiftImport,
    SmartUpReturnImportDocument,
    SmartUpReturnProductImport,
    build_bank_operation_export_payload,
    build_cash_operation_export_payload,
    build_cashin_export_payload,
    build_cross_organizational_movement_export_payload,
    build_equipment_balance_export_payload,
    build_input_export_payload,
    build_internal_movement_export_payload,
    build_inventory_balance_export_payload,
    build_order_export_payload,
    build_order_import_payload,
    build_purchase_export_payload,
    build_return_export_payload,
    build_return_import_payload,
    build_stocktaking_export_payload,
    build_supplier_return_export_payload,
    build_visit_export_payload,
    build_writeoff_export_payload,
    format_order_import_date,
)


def test_order_import_payload_matches_documented_shape() -> None:
    payload = build_order_import_payload(
        SmartUpOrderImportDocument(
            filial_code="",
            external_id="",
            deal_id="1",
            subfilial_code="",
            delivery_number="1",
            delivery_date="03.09.21",
            room_code="100",
            robot_code="100",
            deal_time="02.09.21",
            status="A",
            sales_manager_code="100",
            person_code="100",
            currency_code="860",
            owner_person_code="",
            van_code="",
            contract_code="",
            note="",
            self_shipment="",
            delivery_address_short="",
            delivery_address_full="",
            marking_attaching_method="",
            invoice_number="100",
            expeditor_code="",
            payment_type_code="",
            order_products=[
                SmartUpOrderProductImport(
                    external_id="",
                    product_unit_id="",
                    inventory_kind="G",
                    warehouse_code="100",
                    product_code="100",
                    serial_number="",
                    card_code="",
                    expiry_date="",
                    on_balance="",
                    order_quant="10",
                    price_type_code="777",
                    product_price="",
                    margin_kind="S",
                    margin_value="",
                    margin_amount="100",
                    vat_percent="",
                ),
            ],
            order_gifts=[
                SmartUpOrderGiftImport(),
            ],
            order_actions=[
                SmartUpOrderActionImport(),
            ],
            order_consignments=[
                SmartUpOrderConsignmentImport(),
            ],
        ),
    )

    assert payload == {
        "order": [
            {
                "filial_code": "",
                "external_id": "",
                "deal_id": "1",
                "subfilial_code": "",
                "delivery_number": "1",
                "delivery_date": "03.09.21",
                "room_code": "100",
                "robot_code": "100",
                "deal_time": "02.09.21",
                "status": "A",
                "sales_manager_code": "100",
                "person_code": "100",
                "currency_code": "860",
                "owner_person_code": "",
                "van_code": "",
                "contract_code": "",
                "note": "",
                "self_shipment": "",
                "delivery_address_short": "",
                "delivery_address_full": "",
                "marking_attaching_method": "",
                "invoice_number": "100",
                "expeditor_code": "",
                "payment_type_code": "",
                "order_products": [
                    {
                        "external_id": "",
                        "product_unit_id": "",
                        "inventory_kind": "G",
                        "warehouse_code": "100",
                        "product_code": "100",
                        "serial_number": "",
                        "card_code": "",
                        "expiry_date": "",
                        "on_balance": "",
                        "order_quant": "10",
                        "price_type_code": "777",
                        "product_price": "",
                        "margin_kind": "S",
                        "margin_value": "",
                        "margin_amount": "100",
                        "vat_percent": "",
                    }
                ],
                "order_gifts": [
                    {
                        "external_id": "",
                        "product_unit_id": "",
                        "inventory_kind": "",
                        "warehouse_code": "",
                        "product_code": "",
                        "serial_number": "",
                        "card_code": "",
                        "expiry_date": "",
                        "on_balance": "",
                        "order_quant": "",
                    }
                ],
                "order_actions": [
                    {
                        "external_id": "",
                        "product_unit_id": "",
                        "inventory_kind": "",
                        "warehouse_code": "",
                        "product_code": "",
                        "serial_number": "",
                        "card_code": "",
                        "expiry_date": "",
                        "on_balance": "",
                        "order_quant": "",
                        "bonus_id": "",
                    }
                ],
                "order_consignments": [
                    {
                        "external_id": "",
                        "consignment_unit_id": "",
                        "consignment_date": "",
                        "consignment_amount": "",
                    }
                ],
            }
        ]
    }


def test_order_import_date_formatter_uses_two_digit_year() -> None:
    assert format_order_import_date(date(2021, 9, 3)) == "03.09.21"


def test_order_export_payload_matches_documented_window_shape() -> None:
    payload = build_order_export_payload(
        begin_deal_date=date(2026, 8, 1),
        end_deal_date=date(2026, 8, 2),
    )

    assert payload == {
        "begin_deal_date": "01.08.2026",
        "end_deal_date": "02.08.2026",
    }


def test_return_export_payload_matches_documented_shape() -> None:
    assert build_return_export_payload(
        begin_return_date=date(2026, 8, 3),
        end_return_date=date(2026, 8, 10),
    ) == {
        "begin_return_date": "03.08.2026",
        "end_return_date": "10.08.2026",
    }


def test_visit_export_payload_matches_documented_shape() -> None:
    assert build_visit_export_payload(
        begin_visit_date=date(2026, 8, 3),
        end_visit_date=date(2026, 8, 10),
    ) == {
        "begin_visit_date": "03.08.2026",
        "end_visit_date": "10.08.2026",
    }


def test_cashin_export_payload_matches_documented_shape() -> None:
    assert build_cashin_export_payload(
        begin_cashin_date=date(2026, 8, 3),
        end_cashin_date=date(2026, 8, 10),
        filial_code="16114091",
    ) == {
        "begin_cashin_date": "03.08.2026",
        "end_cashin_date": "10.08.2026",
        "filial_code": "16114091",
    }


def test_cross_org_movement_export_payload_matches_documented_shape() -> None:
    assert build_cross_organizational_movement_export_payload(
        begin_from_date=date(2026, 8, 3),
        end_from_date=date(2026, 8, 10),
    ) == {
        "begin_from_date": "03.08.2026",
        "end_from_date": "10.08.2026",
    }


def test_internal_movement_export_payload_matches_documented_shape() -> None:
    assert build_internal_movement_export_payload(
        begin_from_movement_date=date(2026, 8, 3),
        end_from_movement_date=date(2026, 8, 10),
    ) == {
        "begin_from_movement_date": "03.08.2026",
        "end_from_movement_date": "10.08.2026",
    }


def test_stocktaking_export_payload_matches_documented_shape() -> None:
    assert build_stocktaking_export_payload(
        begin_stocktaking_date=date(2026, 8, 3),
        end_stocktaking_date=date(2026, 8, 10),
    ) == {
        "begin_stocktaking_date": "03.08.2026",
        "end_stocktaking_date": "10.08.2026",
    }


def test_other_documented_history_builders_keep_documented_fields() -> None:
    assert build_writeoff_export_payload(
        begin_writeoff_date=date(2026, 8, 3),
        end_writeoff_date=date(2026, 8, 10),
    ) == {
        "begin_writeoff_date": "03.08.2026",
        "end_writeoff_date": "10.08.2026",
    }
    assert build_supplier_return_export_payload(
        begin_return_date=date(2026, 8, 3),
        end_return_date=date(2026, 8, 10),
    ) == {
        "begin_return_date": "03.08.2026",
        "end_return_date": "10.08.2026",
    }
    assert build_input_export_payload(
        begin_input_date=date(2026, 8, 3),
        end_input_date=date(2026, 8, 10),
    ) == {
        "begin_input_date": "03.08.2026",
        "end_input_date": "10.08.2026",
    }
    assert build_purchase_export_payload(
        begin_purchase_date=date(2026, 8, 3),
        end_purchase_date=date(2026, 8, 10),
    ) == {
        "begin_purchase_date": "03.08.2026",
        "end_purchase_date": "10.08.2026",
    }
    assert build_cash_operation_export_payload(
        begin_operation_date=date(2026, 8, 3),
        end_operation_date=date(2026, 8, 10),
    ) == {
        "begin_operation_date": "03.08.2026",
        "end_operation_date": "10.08.2026",
    }
    assert build_bank_operation_export_payload(
        begin_operation_date=date(2026, 8, 3),
        end_operation_date=date(2026, 8, 10),
    ) == {
        "begin_operation_date": "03.08.2026",
        "end_operation_date": "10.08.2026",
    }
    assert build_equipment_balance_export_payload(filial_code="16114091") == {
        "offset": "0",
        "limit": "1000",
        "filial_code": "16114091",
    }
    assert build_inventory_balance_export_payload(
        filial_code="16114091",
        begin_date=date(2026, 8, 3),
        end_date=date(2026, 8, 10),
        warehouse_codes=[],
    ) == {
        "filial_code": "16114091",
        "begin_date": "03.08.2026",
        "end_date": "10.08.2026",
    }


def test_return_import_payload_matches_documented_shape() -> None:
    payload = build_return_import_payload(
        SmartUpReturnImportDocument(
            filial_code="",
            external_id="",
            deal_id="1",
            subfilial_code="",
            delivery_number="1",
            delivery_date="03.09.21",
            room_code="100",
            robot_code="100",
            deal_time="02.09.21",
            status="A",
            sales_manager_code="100",
            person_code="100",
            currency_code="860",
            owner_person_code="",
            van_code="",
            contract_code="",
            note="",
            self_shipment="",
            delivery_address_short="",
            delivery_address_full="",
            marking_attaching_method="",
            invoice_number="100",
            expeditor_code="",
            payment_type_code="",
            return_reason_code="1",
            return_products=[
                SmartUpReturnProductImport(
                    external_id="",
                    product_unit_id="",
                    inventory_kind="G",
                    warehouse_code="100",
                    product_code="100",
                    serial_number="",
                    card_code="",
                    expiry_date="",
                    on_balance="",
                    order_quant="10",
                    price_type_code="777",
                    product_price="",
                    margin_kind="S",
                    margin_value="",
                    margin_amount="100",
                    vat_percent="",
                ),
            ],
            return_gifts=[
                SmartUpReturnGiftImport(),
            ],
            return_actions=[
                SmartUpReturnActionImport(),
            ],
            return_consignments=[
                SmartUpReturnConsignmentImport(),
            ],
        ),
    )

    assert payload == {
        "return": [
            {
                "filial_code": "",
                "external_id": "",
                "deal_id": "1",
                "subfilial_code": "",
                "delivery_number": "1",
                "delivery_date": "03.09.21",
                "room_code": "100",
                "robot_code": "100",
                "deal_time": "02.09.21",
                "status": "A",
                "sales_manager_code": "100",
                "person_code": "100",
                "currency_code": "860",
                "owner_person_code": "",
                "van_code": "",
                "contract_code": "",
                "note": "",
                "self_shipment": "",
                "delivery_address_short": "",
                "delivery_address_full": "",
                "marking_attaching_method": "",
                "invoice_number": "100",
                "expeditor_code": "",
                "payment_type_code": "",
                "return_reason_code": "1",
                "return_products": [
                    {
                        "external_id": "",
                        "product_unit_id": "",
                        "inventory_kind": "G",
                        "warehouse_code": "100",
                        "product_code": "100",
                        "serial_number": "",
                        "card_code": "",
                        "expiry_date": "",
                        "on_balance": "",
                        "order_quant": "10",
                        "price_type_code": "777",
                        "product_price": "",
                        "margin_kind": "S",
                        "margin_value": "",
                        "margin_amount": "100",
                        "vat_percent": "",
                    }
                ],
                "return_gifts": [
                    {
                        "external_id": "",
                        "product_unit_id": "",
                        "inventory_kind": "",
                        "warehouse_code": "",
                        "product_code": "",
                        "serial_number": "",
                        "card_code": "",
                        "expiry_date": "",
                        "on_balance": "",
                        "order_quant": "",
                    }
                ],
                "return_actions": [
                    {
                        "external_id": "",
                        "product_unit_id": "",
                        "inventory_kind": "",
                        "warehouse_code": "",
                        "product_code": "",
                        "serial_number": "",
                        "card_code": "",
                        "expiry_date": "",
                        "on_balance": "",
                        "order_quant": "",
                        "bonus_id": "",
                    }
                ],
                "return_consignments": [
                    {
                        "external_id": "",
                        "consignment_unit_id": "",
                        "consignment_date": "",
                        "consignment_amount": "",
                    }
                ],
            }
        ]
    }
