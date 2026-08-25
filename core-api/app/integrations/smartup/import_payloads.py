"""Typed SmartUp import payloads mirroring the official API examples."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SmartUpOrderProductImport(BaseModel):
    """One order line item from the SmartUp import example."""

    external_id: str = ""
    product_unit_id: str = ""
    inventory_kind: str = ""
    warehouse_code: str = ""
    product_code: str = ""
    serial_number: str = ""
    card_code: str = ""
    expiry_date: str = ""
    on_balance: str = ""
    order_quant: str = ""
    price_type_code: str = ""
    product_price: str = ""
    margin_kind: str = ""
    margin_value: str = ""
    margin_amount: str = ""
    vat_percent: str = ""

    model_config = ConfigDict(extra="forbid")


class SmartUpOrderGiftImport(BaseModel):
    """One order gift row from the SmartUp import example."""

    external_id: str = ""
    product_unit_id: str = ""
    inventory_kind: str = ""
    warehouse_code: str = ""
    product_code: str = ""
    serial_number: str = ""
    card_code: str = ""
    expiry_date: str = ""
    on_balance: str = ""
    order_quant: str = ""

    model_config = ConfigDict(extra="forbid")


class SmartUpOrderActionImport(BaseModel):
    """One order action row from the SmartUp import example."""

    external_id: str = ""
    product_unit_id: str = ""
    inventory_kind: str = ""
    warehouse_code: str = ""
    product_code: str = ""
    serial_number: str = ""
    card_code: str = ""
    expiry_date: str = ""
    on_balance: str = ""
    order_quant: str = ""
    bonus_id: str = ""

    model_config = ConfigDict(extra="forbid")


class SmartUpOrderConsignmentImport(BaseModel):
    """One order consignment row from the SmartUp import example."""

    external_id: str = ""
    consignment_unit_id: str = ""
    consignment_date: str = ""
    consignment_amount: str = ""

    model_config = ConfigDict(extra="forbid")


class SmartUpOrderImportDocument(BaseModel):
    """One document item inside the order import request."""

    filial_code: str = ""
    external_id: str = ""
    deal_id: str = ""
    subfilial_code: str = ""
    delivery_number: str = ""
    delivery_date: str = ""
    room_code: str = ""
    robot_code: str = ""
    deal_time: str = ""
    status: str = ""
    sales_manager_code: str = ""
    person_code: str = ""
    currency_code: str = ""
    owner_person_code: str = ""
    van_code: str = ""
    contract_code: str = ""
    note: str = ""
    self_shipment: str = ""
    delivery_address_short: str = ""
    delivery_address_full: str = ""
    marking_attaching_method: str = ""
    invoice_number: str = ""
    expeditor_code: str = ""
    payment_type_code: str = ""
    order_products: list[SmartUpOrderProductImport] = Field(default_factory=list)
    order_gifts: list[SmartUpOrderGiftImport] = Field(default_factory=list)
    order_actions: list[SmartUpOrderActionImport] = Field(default_factory=list)
    order_consignments: list[SmartUpOrderConsignmentImport] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SmartUpOrderImportRequest(BaseModel):
    """Request body for the documented SmartUp Order / Import endpoint."""

    order: list[SmartUpOrderImportDocument] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SmartUpReturnProductImport(BaseModel):
    """One return line item from the SmartUp import example."""

    external_id: str = ""
    product_unit_id: str = ""
    inventory_kind: str = ""
    warehouse_code: str = ""
    product_code: str = ""
    serial_number: str = ""
    card_code: str = ""
    expiry_date: str = ""
    on_balance: str = ""
    order_quant: str = ""
    price_type_code: str = ""
    product_price: str = ""
    margin_kind: str = ""
    margin_value: str = ""
    margin_amount: str = ""
    vat_percent: str = ""

    model_config = ConfigDict(extra="forbid")


class SmartUpReturnGiftImport(BaseModel):
    """One return gift row from the SmartUp import example."""

    external_id: str = ""
    product_unit_id: str = ""
    inventory_kind: str = ""
    warehouse_code: str = ""
    product_code: str = ""
    serial_number: str = ""
    card_code: str = ""
    expiry_date: str = ""
    on_balance: str = ""
    order_quant: str = ""

    model_config = ConfigDict(extra="forbid")


class SmartUpReturnActionImport(BaseModel):
    """One return action row from the SmartUp import example."""

    external_id: str = ""
    product_unit_id: str = ""
    inventory_kind: str = ""
    warehouse_code: str = ""
    product_code: str = ""
    serial_number: str = ""
    card_code: str = ""
    expiry_date: str = ""
    on_balance: str = ""
    order_quant: str = ""
    bonus_id: str = ""

    model_config = ConfigDict(extra="forbid")


class SmartUpReturnConsignmentImport(BaseModel):
    """One return consignment row from the SmartUp import example."""

    external_id: str = ""
    consignment_unit_id: str = ""
    consignment_date: str = ""
    consignment_amount: str = ""

    model_config = ConfigDict(extra="forbid")


class SmartUpReturnImportDocument(BaseModel):
    """One document item inside the return import request."""

    filial_code: str = ""
    external_id: str = ""
    deal_id: str = ""
    subfilial_code: str = ""
    delivery_number: str = ""
    delivery_date: str = ""
    room_code: str = ""
    robot_code: str = ""
    deal_time: str = ""
    status: str = ""
    sales_manager_code: str = ""
    person_code: str = ""
    currency_code: str = ""
    owner_person_code: str = ""
    van_code: str = ""
    contract_code: str = ""
    note: str = ""
    self_shipment: str = ""
    delivery_address_short: str = ""
    delivery_address_full: str = ""
    marking_attaching_method: str = ""
    invoice_number: str = ""
    expeditor_code: str = ""
    payment_type_code: str = ""
    return_reason_code: str = ""
    return_products: list[SmartUpReturnProductImport] = Field(default_factory=list)
    return_gifts: list[SmartUpReturnGiftImport] = Field(default_factory=list)
    return_actions: list[SmartUpReturnActionImport] = Field(default_factory=list)
    return_consignments: list[SmartUpReturnConsignmentImport] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SmartUpReturnImportRequest(BaseModel):
    """Request body for the documented SmartUp Return / Import endpoint."""

    return_: list[SmartUpReturnImportDocument] = Field(default_factory=list, alias="return")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def build_order_import_payload(
    order: SmartUpOrderImportDocument | dict[str, Any],
    *additional_orders: SmartUpOrderImportDocument | dict[str, Any],
) -> dict[str, Any]:
    """Build the exact documented SmartUp order import body."""

    items = [order, *additional_orders]
    normalized_orders = [
        item
        if isinstance(item, SmartUpOrderImportDocument)
        else SmartUpOrderImportDocument.model_validate(item)
        for item in items
    ]
    return SmartUpOrderImportRequest(order=normalized_orders).model_dump(mode="python")


def build_return_import_payload(
    return_document: SmartUpReturnImportDocument | dict[str, Any],
    *additional_returns: SmartUpReturnImportDocument | dict[str, Any],
) -> dict[str, Any]:
    """Build the exact documented SmartUp return import body."""

    items = [return_document, *additional_returns]
    normalized_returns = [
        item
        if isinstance(item, SmartUpReturnImportDocument)
        else SmartUpReturnImportDocument.model_validate(item)
        for item in items
    ]
    return SmartUpReturnImportRequest(return_=normalized_returns).model_dump(
        mode="python",
        by_alias=True,
    )


def format_order_import_date(value: date | datetime) -> str:
    """Format SmartUp import dates as dd.mm.yy, matching the example payload."""

    if isinstance(value, datetime):
        value = value.date()
    return value.strftime("%d.%m.%y")


def build_order_export_payload(
    *,
    deal_id: str | int | None = None,
    begin_deal_date: date | datetime | str | None = None,
    end_deal_date: date | datetime | str | None = None,
    delivery_date: date | datetime | str | None = None,
    begin_created_on: date | datetime | str | None = None,
    end_created_on: date | datetime | str | None = None,
    begin_modified_on: date | datetime | str | None = None,
    end_modified_on: date | datetime | str | None = None,
    producer_codes: Iterable[str] | None = None,
    filial_code: str | None = None,
    filial_codes: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Build the documented SmartUp Order / Export payload."""

    payload: dict[str, Any] = {}

    if deal_id is not None:
        deal_text = str(deal_id).strip()
        if deal_text:
            payload["deal_id"] = deal_text

    for field_name, value in {
        "begin_deal_date": begin_deal_date,
        "end_deal_date": end_deal_date,
        "delivery_date": delivery_date,
        "begin_created_on": begin_created_on,
        "end_created_on": end_created_on,
        "begin_modified_on": begin_modified_on,
        "end_modified_on": end_modified_on,
    }.items():
        formatted = _format_smartup_export_date(value)
        if formatted is not None:
            payload[field_name] = formatted

    cleaned_producer_codes = _clean_string_list(producer_codes)
    if cleaned_producer_codes:
        payload["producer_codes"] = cleaned_producer_codes

    if filial_code is not None:
        filial_text = str(filial_code).strip()
        if filial_text:
            payload["filial_code"] = filial_text

    cleaned_filial_codes = _clean_string_list(filial_codes)
    if cleaned_filial_codes:
        payload["filial_codes"] = [{"filial_code": code} for code in cleaned_filial_codes]

    return clean_smartup_export_payload(payload)


def build_cashin_export_payload(
    *,
    external_id: str | None = None,
    cashin_id: str | int | None = None,
    begin_cashin_date: date | datetime | str | None = None,
    end_cashin_date: date | datetime | str | None = None,
    begin_created_on: date | datetime | str | None = None,
    end_created_on: date | datetime | str | None = None,
    begin_modified_on: date | datetime | str | None = None,
    end_modified_on: date | datetime | str | None = None,
    filial_code: str | None = None,
    filial_codes: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Build the documented SmartUp client payment export payload."""

    payload: dict[str, Any] = {}
    if external_id is not None:
        text = str(external_id).strip()
        if text:
            payload["external_id"] = text
    if cashin_id is not None:
        text = str(cashin_id).strip()
        if text:
            payload["cashin_id"] = text
    for field_name, value in {
        "begin_cashin_date": begin_cashin_date,
        "end_cashin_date": end_cashin_date,
        "begin_created_on": begin_created_on,
        "end_created_on": end_created_on,
        "begin_modified_on": begin_modified_on,
        "end_modified_on": end_modified_on,
    }.items():
        formatted = _format_smartup_export_date(value)
        if formatted is not None:
            payload[field_name] = formatted
    if filial_code is not None:
        text = str(filial_code).strip()
        if text:
            payload["filial_code"] = text
    cleaned_filial_codes = _clean_string_list(filial_codes)
    if cleaned_filial_codes:
        payload["filial_codes"] = [{"filial_code": code} for code in cleaned_filial_codes]
    return clean_smartup_export_payload(payload)


def build_return_export_payload(
    *,
    begin_return_date: date | datetime | str | None = None,
    end_return_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Build the documented SmartUp Return / Export payload."""

    return clean_smartup_export_payload(
        _build_simple_window_payload(
        {
            "begin_return_date": begin_return_date,
            "end_return_date": end_return_date,
        },
        ),
    )


def build_visit_export_payload(
    *,
    begin_visit_date: date | datetime | str | None = None,
    end_visit_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Build the documented SmartUp Visit / Export payload."""

    return clean_smartup_export_payload(
        _build_simple_window_payload(
        {
            "begin_visit_date": begin_visit_date,
            "end_visit_date": end_visit_date,
        },
        ),
    )


def build_cross_organizational_movement_export_payload(
    *,
    begin_from_date: date | datetime | str | None = None,
    end_from_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Build the documented cross-organizational movement export payload."""

    return clean_smartup_export_payload(
        _build_simple_window_payload(
        {
            "begin_from_date": begin_from_date,
            "end_from_date": end_from_date,
        },
        ),
    )


def build_internal_movement_export_payload(
    *,
    begin_from_movement_date: date | datetime | str | None = None,
    end_from_movement_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Build the documented internal movement export payload."""

    return clean_smartup_export_payload(
        _build_simple_window_payload(
        {
            "begin_from_movement_date": begin_from_movement_date,
            "end_from_movement_date": end_from_movement_date,
        },
        ),
    )


def build_stocktaking_export_payload(
    *,
    begin_stocktaking_date: date | datetime | str | None = None,
    end_stocktaking_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Build the documented stocktaking export payload."""

    return clean_smartup_export_payload(
        _build_simple_window_payload(
        {
            "begin_stocktaking_date": begin_stocktaking_date,
            "end_stocktaking_date": end_stocktaking_date,
        },
        ),
    )


def build_writeoff_export_payload(
    *,
    begin_writeoff_date: date | datetime | str | None = None,
    end_writeoff_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Build the documented write-off export payload."""

    return clean_smartup_export_payload(
        _build_simple_window_payload(
        {
            "begin_writeoff_date": begin_writeoff_date,
            "end_writeoff_date": end_writeoff_date,
        },
        ),
    )


def build_supplier_return_export_payload(
    *,
    begin_return_date: date | datetime | str | None = None,
    end_return_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Build the documented return-to-suppliers export payload."""

    return clean_smartup_export_payload(
        _build_simple_window_payload(
        {
            "begin_return_date": begin_return_date,
            "end_return_date": end_return_date,
        },
        ),
    )


def build_input_export_payload(
    *,
    begin_input_date: date | datetime | str | None = None,
    end_input_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Build the documented receipts-to-warehouse export payload."""

    return clean_smartup_export_payload(
        _build_simple_window_payload(
        {
            "begin_input_date": begin_input_date,
            "end_input_date": end_input_date,
        },
        ),
    )


def build_purchase_export_payload(
    *,
    begin_purchase_date: date | datetime | str | None = None,
    end_purchase_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Build the documented purchase export payload."""

    return clean_smartup_export_payload(
        _build_simple_window_payload(
        {
            "begin_purchase_date": begin_purchase_date,
            "end_purchase_date": end_purchase_date,
        },
        ),
    )


def build_cash_operation_export_payload(
    *,
    external_id: str | None = None,
    operation_id: str | int | None = None,
    begin_operation_date: date | datetime | str | None = None,
    end_operation_date: date | datetime | str | None = None,
    begin_created_on: date | datetime | str | None = None,
    end_created_on: date | datetime | str | None = None,
    begin_modified_on: date | datetime | str | None = None,
    end_modified_on: date | datetime | str | None = None,
    filial_code: str | None = None,
    filial_codes: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Build the documented cash operations export payload."""

    return clean_smartup_export_payload(
        _build_operations_export_payload(
        external_id=external_id,
        operation_id=operation_id,
        begin_operation_date=begin_operation_date,
        end_operation_date=end_operation_date,
        begin_created_on=begin_created_on,
        end_created_on=end_created_on,
        begin_modified_on=begin_modified_on,
        end_modified_on=end_modified_on,
        filial_code=filial_code,
        filial_codes=filial_codes,
        ),
    )


def build_bank_operation_export_payload(
    *,
    external_id: str | None = None,
    operation_id: str | int | None = None,
    begin_operation_date: date | datetime | str | None = None,
    end_operation_date: date | datetime | str | None = None,
    begin_created_on: date | datetime | str | None = None,
    end_created_on: date | datetime | str | None = None,
    begin_modified_on: date | datetime | str | None = None,
    end_modified_on: date | datetime | str | None = None,
    filial_code: str | None = None,
    filial_codes: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Build the documented bank statements export payload."""

    return clean_smartup_export_payload(
        _build_operations_export_payload(
        external_id=external_id,
        operation_id=operation_id,
        begin_operation_date=begin_operation_date,
        end_operation_date=end_operation_date,
        begin_created_on=begin_created_on,
        end_created_on=end_created_on,
        begin_modified_on=begin_modified_on,
        end_modified_on=end_modified_on,
        filial_code=filial_code,
        filial_codes=filial_codes,
        ),
    )


def build_equipment_balance_export_payload(
    *,
    offset: int | str | None = 0,
    limit: int | str | None = 1000,
    filial_code: str | None = None,
    room_codes: Iterable[str] | None = None,
    product_type_codes: Iterable[str] | None = None,
    product_group_codes: Iterable[str] | None = None,
    product_codes: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Build the documented equipment balance export payload."""

    payload: dict[str, Any] = {
        "offset": str(offset if offset is not None else 0),
        "limit": str(limit if limit is not None else 1000),
        "room_codes": [{"room_code": code} for code in _clean_string_list(room_codes)],
        "product_type_codes": [
            {"product_type_code": code} for code in _clean_string_list(product_type_codes)
        ],
        "product_group_codes": [
            {"product_group_code": code} for code in _clean_string_list(product_group_codes)
        ],
        "product_codes": [{"product_code": code} for code in _clean_string_list(product_codes)],
    }
    if filial_code is not None:
        filial_text = str(filial_code).strip()
        if filial_text:
            payload["filial_code"] = filial_text
    return clean_smartup_export_payload(payload)


def build_inventory_balance_export_payload(
    *,
    begin_date: date | datetime | str | None = None,
    end_date: date | datetime | str | None = None,
    filial_code: str | None = None,
    warehouse_codes: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Build the documented inventory balance export payload."""

    payload: dict[str, Any] = {}
    for field_name, value in {
        "begin_date": begin_date,
        "end_date": end_date,
    }.items():
        formatted = _format_smartup_export_date(value)
        if formatted is not None:
            payload[field_name] = formatted

    if filial_code is not None:
        filial_text = str(filial_code).strip()
        if filial_text:
            payload["filial_code"] = filial_text

    cleaned_warehouse_codes = _clean_string_list(warehouse_codes)
    if cleaned_warehouse_codes:
        payload["warehouse_codes"] = cleaned_warehouse_codes

    return clean_smartup_export_payload(payload)


def _build_simple_window_payload(
    window_fields: dict[str, date | datetime | str | None],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field_name, value in window_fields.items():
        formatted = _format_smartup_export_date(value)
        if formatted is not None:
            payload[field_name] = formatted
    return payload


def _build_operations_export_payload(
    *,
    external_id: str | None,
    operation_id: str | int | None,
    begin_operation_date: date | datetime | str | None,
    end_operation_date: date | datetime | str | None,
    begin_created_on: date | datetime | str | None,
    end_created_on: date | datetime | str | None,
    begin_modified_on: date | datetime | str | None,
    end_modified_on: date | datetime | str | None,
    filial_code: str | None,
    filial_codes: Iterable[str] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if external_id is not None:
        text = str(external_id).strip()
        if text:
            payload["external_id"] = text
    if operation_id is not None:
        text = str(operation_id).strip()
        if text:
            payload["operation_id"] = text
    for field_name, value in {
        "begin_operation_date": begin_operation_date,
        "end_operation_date": end_operation_date,
        "begin_created_on": begin_created_on,
        "end_created_on": end_created_on,
        "begin_modified_on": begin_modified_on,
        "end_modified_on": end_modified_on,
    }.items():
        formatted = _format_smartup_export_date(value)
        if formatted is not None:
            payload[field_name] = formatted
    if filial_code is not None:
        filial_text = str(filial_code).strip()
        if filial_text:
            payload["filial_code"] = filial_text
    cleaned_filial_codes = _clean_string_list(filial_codes)
    if cleaned_filial_codes:
        payload["filial_codes"] = [{"filial_code": code} for code in cleaned_filial_codes]
    return payload


def _format_smartup_export_date(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().strftime("%d.%m.%Y")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    text = str(value).strip()
    return text or None


def _clean_string_list(values: Iterable[str] | None) -> list[str]:
    if values is None:
        return []
    cleaned: list[str] = []
    for value in values:
        text = str(value).strip()
        if text:
            cleaned.append(text)
    return cleaned


def clean_smartup_export_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove empty optional SmartUp filters from an export payload."""

    cleaned = _clean_smartup_payload(payload)
    return cleaned if isinstance(cleaned, dict) else {}


def _clean_smartup_payload(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            normalized = _clean_smartup_payload(item)
            if normalized is None:
                continue
            if normalized == [] or normalized == {}:
                continue
            cleaned[key] = normalized
        return cleaned or None
    if isinstance(value, list):
        cleaned_list = []
        for item in value:
            normalized = _clean_smartup_payload(item)
            if normalized is None:
                continue
            if normalized == [] or normalized == {}:
                continue
            cleaned_list.append(normalized)
        return cleaned_list or None
    return value
