"""Normalization helpers for SmartUp business documents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.core.data_layer.normalized import BusinessDocument, BusinessDocumentItem
from app.integrations.smartup.models import SmartUpRawRecord

from .base import BaseSmartUpNormalizer, NormalizationResult, NormalizedEntityData


@dataclass(frozen=True, slots=True)
class DocumentFamilyConfig:
    """Field selection rules for one SmartUp document family."""

    document_type: str
    source_id_keys: tuple[str, ...]
    number_keys: tuple[str, ...] = ()
    status_keys: tuple[str, ...] = ()
    date_keys: tuple[str, ...] = ()
    amount_keys: tuple[str, ...] = ()
    currency_keys: tuple[str, ...] = ()
    counterparty_keys: tuple[str, ...] = ()
    warehouse_keys: tuple[str, ...] = ()
    product_keys: tuple[str, ...] = ()
    quantity_keys: tuple[str, ...] = ()
    item_list_keys: tuple[str, ...] = ()
    item_source_id_keys: tuple[str, ...] = ()
    item_product_keys: tuple[str, ...] = ()
    item_warehouse_keys: tuple[str, ...] = ()
    item_counterparty_keys: tuple[str, ...] = ()
    item_quantity_keys: tuple[str, ...] = ()
    item_unit_price_keys: tuple[str, ...] = ()
    item_amount_keys: tuple[str, ...] = ()


@dataclass(slots=True)
class BusinessDocumentNormalizationResult:
    """Normalized SmartUp business document plus optional line items."""

    document: BusinessDocument
    items: list[BusinessDocumentItem]
    source_external_id: str


DOCUMENT_FAMILY_CONFIGS: dict[str, DocumentFamilyConfig] = {
    "returns": DocumentFamilyConfig(
        document_type="return",
        source_id_keys=("return_id", "deal_id", "external_id", "id"),
        number_keys=("return_number", "number", "code", "deal_id"),
        status_keys=("status", "status_code"),
        date_keys=("return_time", "deal_time", "delivery_date", "created_on", "occurred_at"),
        amount_keys=("total_amount", "amount", "total_sum"),
        currency_keys=("currency_code", "currency"),
        counterparty_keys=("person_code", "customer_code", "supplier_code"),
        warehouse_keys=("warehouse_code", "room_code"),
        product_keys=("product_code", "inventory_code"),
        quantity_keys=("quantity", "total_quantity"),
        item_list_keys=("return_products", "return_items", "items"),
        item_source_id_keys=("return_product_id", "line_id", "external_id", "product_code"),
        item_product_keys=("product_code", "inventory_code", "code"),
        item_warehouse_keys=("warehouse_code", "room_code"),
        item_counterparty_keys=("person_code", "supplier_code", "customer_code"),
        item_quantity_keys=("quantity",),
        item_unit_price_keys=("price", "unit_price"),
        item_amount_keys=("amount", "total_amount"),
    ),
    "purchases": DocumentFamilyConfig(
        document_type="purchase",
        source_id_keys=("purchase_id", "external_id", "id"),
        number_keys=("purchase_number", "invoice_number", "number", "code"),
        status_keys=("status", "status_code"),
        date_keys=("purchase_time", "input_date", "created_on", "occurred_at"),
        amount_keys=("total_amount", "total_sum", "amount"),
        currency_keys=("currency_code", "currency"),
        counterparty_keys=("supplier_code", "person_code"),
        warehouse_keys=("warehouse_code",),
        product_keys=("product_code", "inventory_code"),
        quantity_keys=("quantity", "total_quantity"),
        item_list_keys=("purchase_items", "items"),
        item_source_id_keys=("purchase_item_id", "line_id", "external_id", "product_code"),
        item_product_keys=("product_code", "inventory_code", "code"),
        item_warehouse_keys=("warehouse_code", "room_code"),
        item_counterparty_keys=("supplier_code", "person_code"),
        item_quantity_keys=("quantity",),
        item_unit_price_keys=("price", "unit_price"),
        item_amount_keys=("amount", "total_amount"),
    ),
    "warehouse_receipts": DocumentFamilyConfig(
        document_type="warehouse_receipt",
        source_id_keys=("receipt_id", "input_id", "external_id", "id"),
        number_keys=("receipt_number", "number", "code", "input_number"),
        status_keys=("status", "status_code"),
        date_keys=("input_date", "receipt_date", "created_on", "occurred_at"),
        amount_keys=("total_amount", "amount"),
        currency_keys=("currency_code", "currency"),
        counterparty_keys=("supplier_code", "person_code"),
        warehouse_keys=("warehouse_code", "room_code"),
        product_keys=("product_code", "inventory_code"),
        quantity_keys=("quantity",),
        item_list_keys=("items", "receipt_items", "input_items"),
        item_source_id_keys=("receipt_item_id", "line_id", "external_id", "product_code"),
        item_product_keys=("product_code", "inventory_code", "code"),
        item_warehouse_keys=("warehouse_code", "room_code"),
        item_counterparty_keys=("supplier_code", "person_code"),
        item_quantity_keys=("quantity",),
        item_unit_price_keys=("price", "unit_price"),
        item_amount_keys=("amount", "total_amount"),
    ),
    "return_to_suppliers": DocumentFamilyConfig(
        document_type="return_to_supplier",
        source_id_keys=("return_id", "external_id", "id"),
        number_keys=("return_number", "number", "code"),
        status_keys=("status", "status_code"),
        date_keys=("return_date", "delivery_date", "created_on", "occurred_at"),
        amount_keys=("total_amount", "amount"),
        currency_keys=("currency_code", "currency"),
        counterparty_keys=("supplier_code", "person_code"),
        warehouse_keys=("warehouse_code", "room_code"),
        product_keys=("product_code", "inventory_code"),
        quantity_keys=("quantity",),
        item_list_keys=("return_products", "items"),
        item_source_id_keys=("return_product_id", "line_id", "external_id", "product_code"),
        item_product_keys=("product_code", "inventory_code", "code"),
        item_warehouse_keys=("warehouse_code", "room_code"),
        item_counterparty_keys=("supplier_code", "person_code"),
        item_quantity_keys=("quantity",),
        item_unit_price_keys=("price", "unit_price"),
        item_amount_keys=("amount", "total_amount"),
    ),
    "stocktakings": DocumentFamilyConfig(
        document_type="stocktaking",
        source_id_keys=("stocktaking_id", "external_id", "id"),
        number_keys=("stocktaking_number", "number", "code"),
        status_keys=("status", "status_code"),
        date_keys=("stocktaking_date", "created_on", "occurred_at"),
        amount_keys=("total_amount", "amount"),
        currency_keys=("currency_code", "currency"),
        warehouse_keys=("warehouse_code", "room_code"),
        product_keys=("product_code", "inventory_code"),
        quantity_keys=("quantity",),
        item_list_keys=("items", "stocktaking_items"),
        item_source_id_keys=("stocktaking_item_id", "line_id", "external_id", "product_code"),
        item_product_keys=("product_code", "inventory_code", "code"),
        item_warehouse_keys=("warehouse_code", "room_code"),
        item_quantity_keys=("quantity",),
        item_unit_price_keys=("price", "unit_price"),
        item_amount_keys=("amount", "total_amount"),
    ),
    "write_offs": DocumentFamilyConfig(
        document_type="write_off",
        source_id_keys=("writeoff_id", "external_id", "id"),
        number_keys=("writeoff_number", "number", "code"),
        status_keys=("status", "status_code"),
        date_keys=("writeoff_date", "created_on", "occurred_at"),
        amount_keys=("total_amount", "amount"),
        currency_keys=("currency_code", "currency"),
        warehouse_keys=("warehouse_code", "room_code"),
        product_keys=("product_code", "inventory_code"),
        quantity_keys=("quantity",),
        item_list_keys=("items", "writeoff_items"),
        item_source_id_keys=("writeoff_item_id", "line_id", "external_id", "product_code"),
        item_product_keys=("product_code", "inventory_code", "code"),
        item_warehouse_keys=("warehouse_code", "room_code"),
        item_quantity_keys=("quantity",),
        item_unit_price_keys=("price", "unit_price"),
        item_amount_keys=("amount", "total_amount"),
    ),
    "cross_organizational_movements": DocumentFamilyConfig(
        document_type="cross_organizational_movement",
        source_id_keys=("movement_id", "external_id", "id"),
        number_keys=("movement_number", "number", "code"),
        status_keys=("status", "status_code"),
        date_keys=("movement_date", "created_on", "occurred_at"),
        amount_keys=("total_amount", "amount"),
        currency_keys=("currency_code", "currency"),
        counterparty_keys=("from_filial_code", "to_filial_code", "counterparty_code"),
        warehouse_keys=("from_warehouse_code", "to_warehouse_code", "warehouse_code"),
        product_keys=("product_code", "inventory_code"),
        quantity_keys=("quantity",),
        item_list_keys=("items", "movement_items"),
        item_source_id_keys=("movement_item_id", "line_id", "external_id", "product_code"),
        item_product_keys=("product_code", "inventory_code", "code"),
        item_warehouse_keys=("from_warehouse_code", "to_warehouse_code", "warehouse_code"),
        item_counterparty_keys=("from_filial_code", "to_filial_code", "counterparty_code"),
        item_quantity_keys=("quantity",),
        item_unit_price_keys=("price", "unit_price"),
        item_amount_keys=("amount", "total_amount"),
    ),
    "internal_movements": DocumentFamilyConfig(
        document_type="internal_movement",
        source_id_keys=("movement_id", "external_id", "id"),
        number_keys=("movement_number", "number", "code"),
        status_keys=("status", "status_code"),
        date_keys=("movement_date", "created_on", "occurred_at"),
        amount_keys=("total_amount", "amount"),
        currency_keys=("currency_code", "currency"),
        counterparty_keys=("from_person_code", "to_person_code"),
        warehouse_keys=("from_room_code", "to_room_code", "room_code"),
        product_keys=("product_code", "inventory_code"),
        quantity_keys=("quantity",),
        item_list_keys=("items", "movement_items"),
        item_source_id_keys=("movement_item_id", "line_id", "external_id", "product_code"),
        item_product_keys=("product_code", "inventory_code", "code"),
        item_warehouse_keys=("from_room_code", "to_room_code", "room_code"),
        item_counterparty_keys=("from_person_code", "to_person_code"),
        item_quantity_keys=("quantity",),
        item_unit_price_keys=("price", "unit_price"),
        item_amount_keys=("amount", "total_amount"),
    ),
    "logistics": DocumentFamilyConfig(
        document_type="logistics",
        source_id_keys=("logistics_id", "external_id", "id"),
        number_keys=("logistics_number", "number", "code"),
        status_keys=("status", "status_code"),
        date_keys=("delivery_date", "created_on", "modified_on", "occurred_at"),
        amount_keys=("total_amount", "amount"),
        currency_keys=("currency_code", "currency"),
        counterparty_keys=("expeditor_code", "van_code"),
        warehouse_keys=("warehouse_code", "room_code"),
        product_keys=("product_code", "inventory_code"),
        quantity_keys=("quantity",),
        item_list_keys=("items", "logistics_items"),
    ),
    "equipment_movements": DocumentFamilyConfig(
        document_type="equipment_movement",
        source_id_keys=("movement_id", "external_id", "id"),
        number_keys=("movement_number", "number", "code"),
        status_keys=("status", "status_code"),
        date_keys=("movement_date", "movement_time", "created_on", "occurred_at"),
        amount_keys=("total_amount", "amount"),
        currency_keys=("currency_code", "currency"),
        counterparty_keys=("from_person_code", "to_person_code"),
        warehouse_keys=("from_room_code", "to_room_code", "room_code"),
        product_keys=("product_code", "inventory_code"),
        quantity_keys=("quantity",),
        item_list_keys=("items", "movement_items"),
        item_source_id_keys=("movement_item_id", "line_id", "external_id", "product_code"),
        item_product_keys=("product_code", "inventory_code", "code"),
        item_warehouse_keys=("from_room_code", "to_room_code", "room_code"),
        item_counterparty_keys=("from_person_code", "to_person_code"),
        item_quantity_keys=("quantity",),
        item_unit_price_keys=("price", "unit_price"),
        item_amount_keys=("amount", "total_amount"),
    ),
    "equipment_requests": DocumentFamilyConfig(
        document_type="equipment_request",
        source_id_keys=("request_id", "external_id", "id"),
        number_keys=("request_number", "number", "code"),
        status_keys=("status", "status_code"),
        date_keys=("request_date", "created_on", "occurred_at"),
        amount_keys=("total_amount", "amount"),
        currency_keys=("currency_code", "currency"),
        counterparty_keys=("person_code", "robot_code"),
        warehouse_keys=("warehouse_code", "room_code"),
        product_keys=("product_code", "inventory_code"),
        quantity_keys=("quantity",),
        item_list_keys=("items", "request_items"),
        item_source_id_keys=("request_item_id", "line_id", "external_id", "product_code"),
        item_product_keys=("product_code", "inventory_code", "code"),
        item_warehouse_keys=("warehouse_code", "room_code"),
        item_counterparty_keys=("person_code", "robot_code"),
        item_quantity_keys=("quantity",),
        item_unit_price_keys=("price", "unit_price"),
        item_amount_keys=("amount", "total_amount"),
    ),
}


@dataclass(slots=True)
class BusinessDocumentNormalizationContext:
    """Normalized document models generated from a SmartUp row."""

    document: BusinessDocument
    items: list[BusinessDocumentItem]
    source_external_id: str


def build_business_document_models(
    *,
    organization_id: UUID,
    filial_id: str,
    source_system: str,
    source_endpoint: str,
    entity_type: str,
    row: dict[str, Any],
    imported_at: datetime,
    source_created_at: datetime | None = None,
    source_updated_at: datetime | None = None,
) -> BusinessDocumentNormalizationContext | None:
    """Build normalized document models for supported SmartUp document exports."""

    family = DOCUMENT_FAMILY_CONFIGS.get(entity_type)
    if family is None:
        return None
    source_external_id = _first_text_value(row, family.source_id_keys)
    if source_external_id is None:
        source_external_id = _first_text_value(row, ("external_id", "id", "code"))
    if source_external_id is None:
        source_external_id = f"{entity_type}:{imported_at.isoformat()}"
    document_at = (
        _first_datetime_value(row, family.date_keys)
        or source_created_at
        or source_updated_at
        or imported_at
    )
    document_id = uuid5(
        NAMESPACE_URL,
        f"smartup:business-document:{organization_id}:{source_system}:{entity_type}:{source_external_id}",
    )
    document = BusinessDocument(
        id=document_id,
        organization_id=organization_id,
        source_system=source_system,
        source_external_id=source_external_id,
        source_filial_id=filial_id,
        source_payload_id=_first_text_value(row, family.source_id_keys),
        source_created_at=source_created_at,
        source_updated_at=source_updated_at,
        document_type=family.document_type,
        document_number=_first_text_value(row, family.number_keys),
        status=_first_text_value(row, family.status_keys),
        document_at=document_at,
        counterparty_external_id=_first_text_value(row, family.counterparty_keys),
        warehouse_external_id=_first_text_value(row, family.warehouse_keys),
        product_external_id=_first_text_value(row, family.product_keys),
        quantity=_first_decimal_value(row, family.quantity_keys),
        amount=_first_decimal_value(row, family.amount_keys),
        currency=_first_text_value(row, family.currency_keys) or "USD",
        metadata={
            "source_entity": entity_type,
            "source_endpoint": source_endpoint,
            "document_family": family.document_type,
            "raw_payload": row,
        },
    )

    items = _build_items(
        organization_id=organization_id,
        filial_id=filial_id,
        source_system="smartup",
        source_endpoint=source_endpoint,
        entity_type=entity_type,
        document=document,
        row=row,
        imported_at=imported_at,
        family=family,
    )
    return BusinessDocumentNormalizationContext(
        document=document,
        items=items,
        source_external_id=source_external_id,
    )


class BusinessDocumentNormalizer(BaseSmartUpNormalizer):
    """Normalize SmartUp document exports into canonical business documents."""

    def __init__(self, entity_type: str) -> None:
        self.entity_type = entity_type

    def normalize(self, raw_record: SmartUpRawRecord) -> NormalizationResult:
        payload = self._payload_as_dict(raw_record)
        context = build_business_document_models(
            organization_id=raw_record.organization_id,
            filial_id=raw_record.filial_id,
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            entity_type=raw_record.entity_type,
            row=payload,
            imported_at=raw_record.imported_at,
            source_created_at=raw_record.source_created_at,
            source_updated_at=raw_record.source_updated_at,
        )
        if context is None:
            return self._unsupported(raw_record, "unsupported_document_family")
        return NormalizationResult(
            entity_type="business_documents",
            source_external_id=context.source_external_id,
            normalized_data=context.document.model_dump(mode="python"),
            related_entities=[
                NormalizedEntityData(
                    entity_type="business_document_items",
                    data=item.model_dump(mode="python"),
                )
                for item in context.items
            ],
        )


def _build_items(
    *,
    organization_id: UUID,
    filial_id: str,
    source_system: str,
    source_endpoint: str,
    entity_type: str,
    document: BusinessDocument,
    row: dict[str, Any],
    imported_at: datetime,
    family: DocumentFamilyConfig,
) -> list[BusinessDocumentItem]:
    items: list[BusinessDocumentItem] = []
    line_items = _first_list_value(row, family.item_list_keys)
    if not isinstance(line_items, list):
        return items
    for index, raw_item in enumerate(line_items, start=1):
        if not isinstance(raw_item, dict):
            continue
        item_source_external_id = _first_text_value(raw_item, family.item_source_id_keys)
        if item_source_external_id is None:
            item_source_external_id = f"{document.source_external_id}:{index}"
        item_id = uuid5(
            NAMESPACE_URL,
            (
                "smartup:business-document-item:"
                f"{organization_id}:{source_system}:{entity_type}:{document.id}:{item_source_external_id}:{index}"
            ),
        )
        item = BusinessDocumentItem(
            id=item_id,
            organization_id=organization_id,
            source_system=source_system,
            source_external_id=item_source_external_id,
            source_filial_id=filial_id,
            source_payload_id=item_source_external_id,
            source_created_at=None,
            source_updated_at=None,
            document_id=document.id,
            line_number=index,
            item_type=family.document_type,
            product_external_id=_first_text_value(raw_item, family.item_product_keys),
            warehouse_external_id=_first_text_value(raw_item, family.item_warehouse_keys),
            counterparty_external_id=_first_text_value(raw_item, family.item_counterparty_keys),
            quantity=_first_decimal_value(raw_item, family.item_quantity_keys),
            unit_price=_first_decimal_value(raw_item, family.item_unit_price_keys, allow_none=True),
            amount=_first_decimal_value(raw_item, family.item_amount_keys),
            currency=_first_text_value(raw_item, family.currency_keys) or document.currency,
            metadata={
                "source_entity": entity_type,
                "source_endpoint": source_endpoint,
                "document_type": family.document_type,
                "raw_item": raw_item,
                "imported_at": imported_at.isoformat(),
            },
        )
        items.append(item)
    return items


def _first_text_value(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _first_list_value(row: dict[str, Any], keys: tuple[str, ...]) -> list[Any] | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, list):
            return value
    return None


def _first_datetime_value(row: dict[str, Any], keys: tuple[str, ...]) -> datetime | None:
    for key in keys:
        value = row.get(key)
        parsed = _parse_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _first_decimal_value(
    row: dict[str, Any],
    keys: tuple[str, ...],
    *,
    allow_none: bool = False,
) -> Decimal:
    for key in keys:
        value = row.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            continue
    return Decimal("0") if not allow_none else Decimal("0")


def _parse_datetime(value: object | None) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y",
        "%Y-%m-%d",
    ):
        try:
            parsed = datetime.strptime(candidate, fmt)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None
