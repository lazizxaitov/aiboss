"""Normalized SmartUp-ready core entities."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class NormalizedEntityBase(BaseModel):
    """Common source-tracked fields for normalized business entities."""

    id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    source_system: str = "smartup"
    source_external_id: str
    source_filial_id: str | None = None
    source_payload_id: str | None = None
    source_created_at: datetime | None = None
    source_updated_at: datetime | None = None
    imported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_synced_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class Customer(NormalizedEntityBase):
    """Normalized customer/contact entity."""

    name: str
    display_name: str | None = None
    phone: str | None = None
    email: str | None = None


class ProductCategory(NormalizedEntityBase):
    """Normalized product category entity."""

    name: str
    parent_external_id: str | None = None


class Product(NormalizedEntityBase):
    """Normalized product entity."""

    name: str
    category_external_id: str | None = None
    sku: str | None = None
    unit: str | None = None


class Warehouse(NormalizedEntityBase):
    """Normalized warehouse entity."""

    name: str | None = None
    code: str | None = None


class PriceType(NormalizedEntityBase):
    """Normalized SmartUp price type reference."""

    code: str
    name: str
    currency_code: str | None = None
    status: str | None = None


class ProductPrice(NormalizedEntityBase):
    """Normalized SmartUp product price reference."""

    product_id: UUID | None = None
    product_external_id: str
    price_type_id: UUID | None = None
    price_type_code: str | None = None
    price: Decimal
    currency_code: str | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None


class Sale(NormalizedEntityBase):
    """Normalized sale entity."""

    customer_id: UUID | None = None
    customer_external_id: str | None = None
    sale_number: str | None = None
    amount: Decimal
    currency: str = "USD"
    status: str = "unknown"
    sale_at: datetime
    closed_at: datetime | None = None


class SaleItem(NormalizedEntityBase):
    """Normalized sale line item entity."""

    sale_id: UUID | None = None
    sale_external_id: str
    product_id: UUID | None = None
    product_external_id: str | None = None
    quantity: Decimal = Decimal("0")
    unit_price: Decimal | None = None
    amount: Decimal = Decimal("0")
    currency: str = "USD"


class Payment(NormalizedEntityBase):
    """Normalized payment entity."""

    sale_id: UUID | None = None
    sale_external_id: str | None = None
    amount: Decimal
    currency: str = "USD"
    paid_at: datetime
    method: str | None = None


class InventoryBalance(NormalizedEntityBase):
    """Normalized inventory balance entity."""

    warehouse_id: UUID | None = None
    product_id: UUID | None = None
    warehouse_external_id: str
    product_external_id: str
    quantity: Decimal
    balance_at: datetime


class Visit(NormalizedEntityBase):
    """Normalized visit entity."""

    customer_id: UUID | None = None
    customer_external_id: str | None = None
    visited_at: datetime
    status: str | None = None


class BankOperation(NormalizedEntityBase):
    """Normalized bank or cash operation entity."""

    amount: Decimal
    currency: str = "USD"
    occurred_at: datetime
    operation_type: str = "unknown"
    description: str | None = None


class BusinessDocument(NormalizedEntityBase):
    """Normalized SmartUp business document entity."""

    document_type: str
    document_number: str | None = None
    status: str | None = None
    document_at: datetime
    counterparty_external_id: str | None = None
    warehouse_external_id: str | None = None
    product_external_id: str | None = None
    quantity: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")
    currency: str = "USD"


class BusinessDocumentItem(NormalizedEntityBase):
    """Normalized SmartUp business document line item."""

    document_id: UUID
    line_number: int = 0
    item_type: str = "document_item"
    product_external_id: str | None = None
    warehouse_external_id: str | None = None
    counterparty_external_id: str | None = None
    quantity: Decimal = Decimal("0")
    unit_price: Decimal | None = None
    amount: Decimal = Decimal("0")
    currency: str = "USD"
