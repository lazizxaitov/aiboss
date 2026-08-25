"""Canonical Data Layer V2 models and validation reports."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import BaseModel, Field


class CanonicalDataQualityStatus(StrEnum):
    """Quality states for canonical V2 rows."""

    VERIFIED = "verified"
    PARTIAL = "partial"
    UNRESOLVED = "unresolved"
    UNSAFE = "unsafe"


def canonical_row_uuid(*parts: object) -> UUID:
    """Build a stable canonical UUID from source-scoped values."""

    seed = "::".join("" if part is None else str(part) for part in parts)
    return uuid5(NAMESPACE_URL, f"ai-business-os:canonical-v2:{seed}")


class CanonicalOrganization(BaseModel):
    """Canonical SmartUp organization dimension."""

    organization_id: UUID
    name: str
    company_id: str
    filial_id: str
    filial_code: str | None = None
    project_code: str
    is_active: bool = True
    sort_order: int = 0
    source_system: str = "smartup"
    source_endpoint: str = "smartup_organizations"
    source_external_id: str
    source_raw_record_id: UUID | None = None
    request_filial_id: str | None = None
    response_filial_id: str | None = None
    request_company_id: str | None = None
    request_project_code: str | None = None
    source_raw_batch_id: UUID | None = None
    data_quality_status: CanonicalDataQualityStatus = CanonicalDataQualityStatus.VERIFIED
    imported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_synced_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanonicalEntityBase(BaseModel):
    """Common source-tracked fields for canonical business entities."""

    id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    source_system: str = "smartup"
    source_endpoint: str
    source_external_id: str
    source_raw_record_id: UUID | None = None
    request_filial_id: str | None = None
    response_filial_id: str | None = None
    request_company_id: str | None = None
    request_project_code: str | None = None
    source_raw_batch_id: UUID | None = None
    data_quality_status: CanonicalDataQualityStatus = CanonicalDataQualityStatus.PARTIAL
    imported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_synced_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanonicalCustomerGroup(CanonicalEntityBase):
    """Canonical group of customers/counterparties from SmartUp person_group."""

    group_id: str | None = None
    code: str | None = None
    name: str
    customer_kind: str | None = None
    state: str | None = None
    group_types: list[dict[str, Any]] = Field(default_factory=list)


class CanonicalCustomer(CanonicalEntityBase):
    """Canonical customer record from SmartUp legal/natural person exports."""

    person_id: str | None = None
    code: str | None = None
    name: str
    short_name: str | None = None
    main_phone: str | None = None
    email: str | None = None
    address: str | None = None
    groups: list[dict[str, Any]] = Field(default_factory=list)
    state: str | None = None
    customer_kind: str | None = None
    tin: str | None = None


class CanonicalProductCategory(CanonicalEntityBase):
    """Canonical product category from SmartUp product_group exports."""

    group_id: str | None = None
    code: str | None = None
    name: str
    product_kind: str | None = None
    state: str | None = None
    group_types: list[dict[str, Any]] = Field(default_factory=list)


class CanonicalProduct(CanonicalEntityBase):
    """Canonical product master record from SmartUp inventory/service/producer exports."""

    product_id: str | None = None
    code: str | None = None
    name: str
    short_name: str | None = None
    measure_code: str | None = None
    article_code: str | None = None
    producer_code: str | None = None
    barcodes: list[str] = Field(default_factory=list)
    inventory_kinds: list[dict[str, Any]] = Field(default_factory=list)
    groups: list[dict[str, Any]] = Field(default_factory=list)
    state: str | None = None
    source_kind: str | None = None
    gtin: str | None = None
    ikpu: str | None = None
    box_quant: str | None = None
    box_type_code: str | None = None
    litr: str | None = None
    marking_group_code: str | None = None
    sector_codes: list[dict[str, Any]] = Field(default_factory=list)
    tnved: str | None = None
    weight_brutto: str | None = None
    weight_netto: str | None = None


class CanonicalWarehouse(CanonicalEntityBase):
    """Canonical warehouse or storage location."""

    warehouse_id: str | None = None
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    state: str | None = None
    source_kind: str | None = None


class CanonicalPriceType(CanonicalEntityBase):
    """Canonical SmartUp price type reference."""

    price_type_id: str | None = None
    code: str
    name: str
    short_name: str | None = None
    currency_code: str | None = None
    price_type_kind: str | None = None
    with_card: str | None = None
    state: str | None = None


class CanonicalProductPrice(CanonicalEntityBase):
    """Canonical SmartUp price point row."""

    product_id: UUID | None = None
    product_code: str | None = None
    inventory_code: str | None = None
    inventory_barcode: str | None = None
    price_type_id: UUID | None = None
    price_type_code: str | None = None
    price_type_card_code: str | None = None
    price: Decimal = Decimal("0")
    currency_code: str | None = None
    state: str | None = None


class CanonicalSalesRep(CanonicalEntityBase):
    """Canonical sales representative discovered from Sales and Visit rows."""

    sales_manager_id: str | None = None
    sales_manager_code: str | None = None
    sales_manager_name: str | None = None
    role: str | None = None
    state: str | None = None
    source_kind: str | None = None


class CanonicalWorkingZone(CanonicalEntityBase):
    """Canonical working zone/distribution room discovered from Sales and Visit rows."""

    room_id: str | None = None
    room_code: str | None = None
    room_name: str | None = None
    state: str | None = None
    source_kind: str | None = None


class CanonicalVisit(CanonicalEntityBase):
    """Canonical SmartUp field visit header from visit export RAW."""

    visit_id: str | None = None
    customer_id: UUID | None = None
    customer_external_id: str | None = None
    customer_code: str | None = None
    customer_name: str | None = None
    sales_rep_id: UUID | None = None
    sales_rep_external_id: str | None = None
    sales_rep_code: str | None = None
    sales_rep_name: str | None = None
    working_zone_id: UUID | None = None
    working_zone_external_id: str | None = None
    working_zone_code: str | None = None
    working_zone_name: str | None = None
    visit_date: datetime | None = None
    visit_start_time: datetime | None = None
    visit_end_time: datetime | None = None
    visited_at: datetime | None = None
    duration_seconds: int | None = None
    derived_duration_seconds: int | None = None
    source_status_code: str | None = None
    normalized_status: str = "unmapped"
    display_status: str = "UNMAPPED"
    is_planned: bool | None = None
    source_is_planned: str | None = None
    supervisor_external_id: str | None = None
    start_latitude: Decimal | None = None
    start_longitude: Decimal | None = None
    end_latitude: Decimal | None = None
    end_longitude: Decimal | None = None
    note: str | None = None
    person_types: list[dict[str, Any]] = Field(default_factory=list)


class CanonicalVisitStock(CanonicalEntityBase):
    """Canonical stock facts observed during a field visit."""

    visit_id: UUID
    visit_external_id: str | None = None
    line_number: int = 0
    product_id: UUID | None = None
    product_external_id: str | None = None
    product_code: str | None = None
    product_name: str | None = None
    quantity: Decimal | None = None
    expiry_date: datetime | None = None
    card_code: str | None = None
    serial_number: str | None = None
    inventory_kind: str | None = None
    unavailable_reason: str | None = None


class CanonicalVisitQuizAnswer(CanonicalEntityBase):
    """Canonical quiz/question answer captured during a field visit."""

    visit_id: UUID
    visit_external_id: str | None = None
    quiz_external_id: str | None = None
    quiz_name: str | None = None
    question_external_id: str | None = None
    question_text: str | None = None
    answer_value: str | None = None
    answer_type: str | None = None
    photo_sha: str | None = None
    line_number: int = 0


class CanonicalVisitEquipment(CanonicalEntityBase):
    """Canonical equipment evidence attached to a field visit."""

    visit_id: UUID
    visit_external_id: str | None = None
    equipment_external_id: str | None = None
    equipment_code: str | None = None
    equipment_name: str | None = None
    serial_number: str | None = None
    status_code: str | None = None
    note: str | None = None
    line_number: int = 0


class CanonicalVisitComment(CanonicalEntityBase):
    """Canonical structured comment attached to a field visit."""

    visit_id: UUID
    visit_external_id: str | None = None
    comment_text: str | None = None
    comment_type: str | None = None
    created_by_external_id: str | None = None
    created_at_source: datetime | None = None
    line_number: int = 0


class CanonicalMediaAsset(CanonicalEntityBase):
    """Canonical media reference preserved from SmartUp source evidence."""

    media_id: str | None = None
    source_entity_type: str | None = None
    source_entity_id: str | None = None
    visit_id: UUID | None = None
    visit_external_id: str | None = None
    media_type: str | None = None
    source_sha: str | None = None
    source_reference: str | None = None
    download_status: str = "not_requested"
    local_path: str | None = None
    mime_type: str | None = None


class CanonicalOrder(CanonicalEntityBase):
    """Canonical SmartUp order document preserved before sale realization logic."""

    order_id: str | None = None
    deal_id: str | None = None
    external_document_id: str | None = None
    order_number: str | None = None
    delivery_number: str | None = None
    order_at: datetime | None = None
    delivery_date: datetime | None = None
    customer_id: UUID | None = None
    customer_external_id: str | None = None
    customer_code: str | None = None
    customer_name: str | None = None
    sales_rep_id: UUID | None = None
    sales_rep_external_id: str | None = None
    working_zone_id: UUID | None = None
    working_zone_external_id: str | None = None
    source_status_code: str | None = None
    source_status_name: str | None = None
    normalized_status: str = "unmapped"
    display_status: str = "UNMAPPED"
    total_amount: Decimal = Decimal("0")
    currency_code: str | None = None
    source_currency_code: str | None = None
    item_count: int = 0
    ordered_quantity: Decimal = Decimal("0")
    sold_quantity: Decimal = Decimal("0")
    has_realization_evidence: bool = False


class CanonicalSale(CanonicalEntityBase):
    """Canonical realized sale fact derived conservatively from SmartUp order rows."""

    sale_id: str | None = None
    order_id: UUID | None = None
    order_external_id: str | None = None
    deal_id: str | None = None
    sale_number: str | None = None
    sale_at: datetime | None = None
    closed_at: datetime | None = None
    customer_id: UUID | None = None
    customer_external_id: str | None = None
    customer_code: str | None = None
    customer_name: str | None = None
    sales_rep_id: UUID | None = None
    sales_rep_external_id: str | None = None
    working_zone_id: UUID | None = None
    working_zone_external_id: str | None = None
    source_status_code: str | None = None
    source_status_name: str | None = None
    normalized_status: str = "unmapped"
    display_status: str = "UNMAPPED"
    total_amount: Decimal = Decimal("0")
    currency_code: str | None = None
    source_currency_code: str | None = None
    item_count: int = 0
    ordered_quantity: Decimal = Decimal("0")
    sold_quantity: Decimal = Decimal("0")
    returned_quantity: Decimal = Decimal("0")
    realization_basis: str | None = None


class CanonicalSaleItem(CanonicalEntityBase):
    """Canonical order/sale line item preserving SmartUp transactional semantics."""

    sale_id: UUID | None = None
    order_id: UUID | None = None
    sale_external_id: str | None = None
    order_external_id: str | None = None
    line_number: int = 0
    product_id: UUID | None = None
    product_external_id: str | None = None
    product_code: str | None = None
    product_name: str | None = None
    warehouse_id: UUID | None = None
    warehouse_external_id: str | None = None
    warehouse_code: str | None = None
    price_type_id: UUID | None = None
    price_type_code: str | None = None
    source_status_code: str | None = None
    ordered_quantity: Decimal = Decimal("0")
    sold_quantity: Decimal = Decimal("0")
    returned_quantity: Decimal = Decimal("0")
    unit_price: Decimal | None = None
    amount: Decimal = Decimal("0")
    vat_percent: Decimal | None = None
    vat_amount: Decimal | None = None
    margin_amount: Decimal | None = None
    currency_code: str | None = None
    source_currency_code: str | None = None
    has_realization_evidence: bool = False


class CanonicalPayment(CanonicalEntityBase):
    """Canonical customer payment fact from SmartUp cashin export."""

    payment_id: str | None = None
    cashin_id: str | None = None
    cashin_number: str | None = None
    paid_at: datetime | None = None
    cashin_date: str | None = None
    cashin_time: str | None = None
    customer_id: UUID | None = None
    customer_external_id: str | None = None
    customer_code: str | None = None
    customer_name: str | None = None
    cashbox_code: str | None = None
    bank_account_code: str | None = None
    source_payment_type_code: str | None = None
    normalized_payment_type: str = "unknown"
    amount: Decimal = Decimal("0")
    currency_code: str | None = None
    source_currency_code: str | None = None
    posted: str | None = None
    purpose: str | None = None
    subfilial_code: str | None = None


class CanonicalPaymentAllocation(CanonicalEntityBase):
    """Canonical allocation between one customer payment and order/sale evidence."""

    payment_id: UUID
    sale_id: UUID | None = None
    sale_external_id: str | None = None
    order_id: UUID | None = None
    order_external_id: str | None = None
    allocated_amount: Decimal | None = None
    currency_code: str | None = None
    allocation_type: str = "unresolved"
    source_reference: dict[str, Any] = Field(default_factory=dict)


class CanonicalFinancialDirection(StrEnum):
    """Normalized direction of a verified financial movement."""

    INFLOW = "INFLOW"
    OUTFLOW = "OUTFLOW"
    TRANSFER = "TRANSFER"
    UNKNOWN = "UNKNOWN"


class CanonicalFinancialAccount(CanonicalEntityBase):
    """Canonical financial account discovered from SmartUp finance-related RAW."""

    account_code: str | None = None
    account_name: str | None = None
    account_type: str = "unknown"
    source_account_id: str | None = None
    currency_code: str | None = None
    source_currency_code: str | None = None
    bank_name: str | None = None
    bank_account_code: str | None = None
    cashbox_code: str | None = None
    coa_code: str | None = None
    subfilial_code: str | None = None


class CanonicalFinancialOperation(CanonicalEntityBase):
    """Canonical financial movement preserving source semantics and provenance."""

    operation_id: str | None = None
    operation_number: str | None = None
    operation_at: datetime | None = None
    operation_date: datetime | None = None
    source_operation_type: str | None = None
    normalized_operation_type: str = "unknown"
    direction: CanonicalFinancialDirection = CanonicalFinancialDirection.UNKNOWN
    amount: Decimal = Decimal("0")
    source_amount: Decimal | None = None
    currency_code: str | None = None
    source_currency_code: str | None = None
    account_id: UUID | None = None
    account_external_id: str | None = None
    account_code: str | None = None
    counterparty_type: str = "unknown"
    counterparty_customer_id: UUID | None = None
    counterparty_external_id: str | None = None
    counterparty_code: str | None = None
    counterparty_name: str | None = None
    purpose: str | None = None
    note: str | None = None
    posted: str | None = None
    source_document_type: str | None = None
    source_document_external_id: str | None = None
    reference_codes: list[dict[str, Any]] = Field(default_factory=list)
    is_internal_transfer: bool = False


class CanonicalCustomerReturn(CanonicalEntityBase):
    """Canonical customer return header from SmartUp customer return export."""

    return_id: str | None = None
    deal_id: str | None = None
    order_deal_id: str | None = None
    external_document_id: str | None = None
    return_number: str | None = None
    return_at: datetime | None = None
    booked_at: datetime | None = None
    delivery_date: datetime | None = None
    customer_id: UUID | None = None
    customer_external_id: str | None = None
    customer_code: str | None = None
    customer_name: str | None = None
    sales_rep_id: UUID | None = None
    sales_rep_external_id: str | None = None
    source_status_code: str | None = None
    source_status_name: str | None = None
    normalized_status: str = "unmapped"
    display_status: str = "UNMAPPED"
    total_amount: Decimal = Decimal("0")
    currency_code: str | None = None
    source_currency_code: str | None = None
    return_reason_id: str | None = None
    return_reason_code: str | None = None
    linked_order_id: UUID | None = None
    linked_order_external_id: str | None = None
    linked_sale_id: UUID | None = None
    linked_sale_external_id: str | None = None
    item_count: int = 0
    returned_quantity: Decimal = Decimal("0")


class CanonicalCustomerReturnItem(CanonicalEntityBase):
    """Canonical customer return line item preserving SmartUp return semantics."""

    customer_return_id: UUID
    return_external_id: str | None = None
    line_number: int = 0
    product_id: UUID | None = None
    product_external_id: str | None = None
    product_code: str | None = None
    product_name: str | None = None
    warehouse_id: UUID | None = None
    warehouse_external_id: str | None = None
    warehouse_code: str | None = None
    price_type_id: UUID | None = None
    price_type_code: str | None = None
    returned_quantity: Decimal = Decimal("0")
    unit_price: Decimal | None = None
    amount: Decimal = Decimal("0")
    vat_percent: Decimal | None = None
    vat_amount: Decimal | None = None
    margin_amount: Decimal | None = None
    currency_code: str | None = None
    source_currency_code: str | None = None
    linked_order_id: UUID | None = None
    linked_sale_id: UUID | None = None


class CanonicalInventoryBalance(CanonicalEntityBase):
    """Canonical warehouse stock snapshot row."""

    snapshot_date: datetime | None = None
    warehouse_id: UUID | None = None
    warehouse_external_id: str | None = None
    warehouse_code: str | None = None
    product_id: UUID | None = None
    product_external_id: str | None = None
    product_code: str | None = None
    product_name: str | None = None
    quantity: Decimal = Decimal("0")
    available_quantity: Decimal | None = None
    reserved_quantity: Decimal | None = None
    input_price: Decimal | None = None
    valuation_amount: Decimal | None = None
    currency_code: str | None = None
    source_currency_code: str | None = None
    batch_number: str | None = None
    card_code: str | None = None
    serial_number: str | None = None
    expiry_date: datetime | None = None
    inventory_kind: str | None = None
    measure_code: str | None = None
    grain_key: str | None = None


class CanonicalInventoryDocumentBase(CanonicalEntityBase):
    """Base canonical warehouse document header."""

    document_id: str | None = None
    document_number: str | None = None
    document_at: datetime | None = None
    source_status_code: str | None = None
    source_status_name: str | None = None
    warehouse_id: UUID | None = None
    warehouse_external_id: str | None = None
    warehouse_code: str | None = None
    total_amount: Decimal | None = None
    currency_code: str | None = None
    source_currency_code: str | None = None
    note: str | None = None
    item_count: int = 0
    total_quantity: Decimal = Decimal("0")


class CanonicalInventoryDocumentItemBase(CanonicalEntityBase):
    """Base canonical warehouse document line item."""

    document_id: UUID
    document_external_id: str | None = None
    line_number: int = 0
    product_id: UUID | None = None
    product_external_id: str | None = None
    product_code: str | None = None
    product_name: str | None = None
    warehouse_id: UUID | None = None
    warehouse_external_id: str | None = None
    warehouse_code: str | None = None
    quantity: Decimal = Decimal("0")
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    source_currency_code: str | None = None
    batch_number: str | None = None
    card_code: str | None = None
    serial_number: str | None = None
    expiry_date: datetime | None = None
    inventory_kind: str | None = None
    measure_code: str | None = None


class CanonicalPurchase(CanonicalInventoryDocumentBase):
    """Canonical supplier purchase header."""

    purchase_id: str | None = None
    purchase_number: str | None = None
    supplier_external_id: str | None = None
    supplier_code: str | None = None
    contract_code: str | None = None
    invoice_number: str | None = None
    invoice_external_id: str | None = None
    invoice_date: datetime | None = None
    input_date: datetime | None = None
    posted: str | None = None
    total_margin_kind: str | None = None
    total_margin_value: Decimal | None = None


class CanonicalPurchaseItem(CanonicalInventoryDocumentItemBase):
    """Canonical supplier purchase line item."""

    purchase_external_id: str | None = None
    purchase_item_id: str | None = None
    purchase_order_item_id: str | None = None
    product_article_code: str | None = None
    on_balance: str | None = None
    base_price: Decimal | None = None
    vat_percent: Decimal | None = None
    vat_amount: Decimal | None = None
    margin_kind: str | None = None
    margin_value: Decimal | None = None


class CanonicalWarehouseReceipt(CanonicalInventoryDocumentBase):
    """Canonical warehouse receipt header."""

    receipt_id: str | None = None
    receipt_number: str | None = None
    supplier_external_id: str | None = None
    supplier_code: str | None = None


class CanonicalWarehouseReceiptItem(CanonicalInventoryDocumentItemBase):
    """Canonical warehouse receipt line item."""

    receipt_external_id: str | None = None
    receipt_item_id: str | None = None
    purchase_external_id: str | None = None
    purchase_item_external_id: str | None = None
    product_article_code: str | None = None
    vat_percent: Decimal | None = None
    vat_amount: Decimal | None = None
    margin_kind: str | None = None
    margin_value: Decimal | None = None


class CanonicalWriteoff(CanonicalInventoryDocumentBase):
    """Canonical write-off header."""

    writeoff_id: str | None = None
    writeoff_number: str | None = None
    writeoff_date: datetime | None = None
    reason_code: str | None = None
    barcode: str | None = None
    c_amount: Decimal | None = None
    c_amount_base: Decimal | None = None


class CanonicalWriteoffItem(CanonicalInventoryDocumentItemBase):
    """Canonical write-off line item."""

    writeoff_external_id: str | None = None
    writeoff_item_id: str | None = None
    product_article_code: str | None = None


class CanonicalSupplierReturn(CanonicalInventoryDocumentBase):
    """Canonical supplier return header."""

    supplier_return_id: str | None = None
    supplier_return_number: str | None = None
    supplier_external_id: str | None = None
    supplier_code: str | None = None
    reason_code: str | None = None


class CanonicalSupplierReturnItem(CanonicalInventoryDocumentItemBase):
    """Canonical supplier return line item."""

    supplier_return_external_id: str | None = None
    supplier_return_item_id: str | None = None


class CanonicalStocktaking(CanonicalInventoryDocumentBase):
    """Canonical stocktaking header."""

    stocktaking_id: str | None = None
    stocktaking_number: str | None = None


class CanonicalStocktakingItem(CanonicalInventoryDocumentItemBase):
    """Canonical stocktaking line item."""

    stocktaking_external_id: str | None = None
    stocktaking_item_id: str | None = None
    book_quantity: Decimal | None = None
    actual_quantity: Decimal | None = None
    difference_quantity: Decimal | None = None
    surplus_quantity: Decimal | None = None
    shortage_quantity: Decimal | None = None
    valuation_amount: Decimal | None = None


class CanonicalInternalMovement(CanonicalInventoryDocumentBase):
    """Canonical internal warehouse transfer header."""

    movement_id: str | None = None
    movement_number: str | None = None
    source_warehouse_id: UUID | None = None
    source_warehouse_external_id: str | None = None
    source_warehouse_code: str | None = None
    destination_warehouse_id: UUID | None = None
    destination_warehouse_external_id: str | None = None
    destination_warehouse_code: str | None = None


class CanonicalInternalMovementItem(CanonicalInventoryDocumentItemBase):
    """Canonical internal warehouse transfer line item."""

    movement_external_id: str | None = None
    movement_item_id: str | None = None
    source_warehouse_id: UUID | None = None
    source_warehouse_external_id: str | None = None
    source_warehouse_code: str | None = None
    destination_warehouse_id: UUID | None = None
    destination_warehouse_external_id: str | None = None
    destination_warehouse_code: str | None = None


class CanonicalCrossOrgMovement(CanonicalInventoryDocumentBase):
    """Canonical cross-organization movement header."""

    movement_id: str | None = None
    delivery_number: str | None = None
    source_filial_code: str | None = None
    destination_filial_code: str | None = None
    source_warehouse_id: UUID | None = None
    source_warehouse_external_id: str | None = None
    source_warehouse_code: str | None = None
    destination_warehouse_id: UUID | None = None
    destination_warehouse_external_id: str | None = None
    destination_warehouse_code: str | None = None
    subfilial_code: str | None = None
    to_subfilial_code: str | None = None
    price_type_code: str | None = None
    payment_type_code: str | None = None
    to_payment_type_code: str | None = None
    reason_id: str | None = None
    request_id: str | None = None


class CanonicalCrossOrgMovementItem(CanonicalInventoryDocumentItemBase):
    """Canonical cross-organization movement line item."""

    movement_external_id: str | None = None
    movement_unit_id: str | None = None
    source_warehouse_id: UUID | None = None
    source_warehouse_external_id: str | None = None
    source_warehouse_code: str | None = None
    destination_warehouse_id: UUID | None = None
    destination_warehouse_external_id: str | None = None
    destination_warehouse_code: str | None = None
    base_amount: Decimal | None = None
    vat_percent: Decimal | None = None
    vat_amount: Decimal | None = None
    margin_kind: str | None = None
    margin_value: Decimal | None = None
    margin_amount: Decimal | None = None
    on_balance: str | None = None


@dataclass(slots=True)
class CanonicalV2ValidationTableReport:
    """Validation statistics for one canonical V2 table."""

    table: str
    raw_source_count: int = 0
    canonical_count: int = 0
    verified: int = 0
    partial: int = 0
    unresolved: int = 0
    unsafe: int = 0
    duplicates: int = 0
    samples: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CanonicalV2ValidationReport:
    """Phase 1 validation summary for the canonical V2 foundation."""

    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    source_system: str = "SmartUp"
    organization_scope: str = "all organizations"
    tables: list[CanonicalV2ValidationTableReport] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def table_map(self) -> dict[str, CanonicalV2ValidationTableReport]:
        """Return validation rows keyed by table name."""

        return {table.table: table for table in self.tables}


def unique_text_list(values: Iterable[Any]) -> list[str]:
    """Return unique, non-empty text values preserving order."""

    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
