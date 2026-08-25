"""Data Explorer helpers for the business core."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from math import ceil
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.data_layer.contracts import CoreDataReader
from app.core.data_layer.normalized import BusinessDocument, BusinessDocumentItem
from app.storage.postgres.adapter import PostgresCoreStore


class DataExplorerState(StrEnum):
    """Availability state for a Data Explorer section."""

    AVAILABLE = "available"
    EMPTY = "empty"
    UNAVAILABLE = "unavailable"


class DataExplorerCollection(StrEnum):
    """Supported Data Explorer pages."""

    OVERVIEW = "overview"
    SALES = "sales"
    SALE_ITEMS = "sale-items"
    PRODUCTS = "products"
    CUSTOMERS = "customers"
    INVENTORY = "inventory"
    PAYMENTS = "payments"
    RETURNS = "returns"
    CASH_OPERATIONS = "cash-operations"
    BANK_OPERATIONS = "bank-operations"
    PURCHASES = "purchases"
    STOCK_MOVEMENTS = "stock-movements"
    VISITS = "visits"
    ORGANIZATIONS = "organizations"
    SMARTUP_RAW = "smartup-raw"
    PROCESSING = "processing"


class DataExplorerSectionStats(BaseModel):
    """Summary card for one Data Explorer page."""

    key: str
    label: str
    href: str
    source_system: str = "SmartUp"
    count: int = 0
    raw_count: int = 0
    normalized_count: int = 0
    state: DataExplorerState = DataExplorerState.EMPTY
    note: str = ""


class DataExplorerStatsResponse(BaseModel):
    """Top-level Data Explorer statistics payload."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_system: str = "SmartUp"
    organizations: int = 0
    businesses: int = 0
    core_records: int = 0
    raw_records: int = 0
    normalized_records: int = 0
    processing_records: int = 0
    sections: list[DataExplorerSectionStats] = Field(default_factory=list)


class DataExplorerPageResponse(BaseModel):
    """Paginated collection payload for Data Explorer pages."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_system: str = "SmartUp"
    dataset: str
    label: str
    page: int
    page_size: int
    total: int
    total_pages: int
    items: list[dict[str, Any]] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _CollectionSpec:
    key: DataExplorerCollection
    label: str
    href: str
    note: str
    raw_endpoint_suffixes: tuple[str, ...] = ()
    normalized_tables: tuple[str, ...] = ()
    row_builder: Callable[[DataExplorerService, UUID | None], list[dict[str, Any]]] | None = None
    count_builder: Callable[[DataExplorerService, UUID | None], tuple[int, int]] | None = None


class DataExplorerService:
    """Build Data Explorer summaries and paginated pages."""

    _OVERVIEW_NOTE = "Сводка по SmartUp-данным, raw-слою и нормализованным сущностям."

    def __init__(self, store: CoreDataReader) -> None:
        self.store = store
        self._organization_names = {
            organization.id: organization.name
            for organization in store.list_smartup_organizations()
        }

    def build_stats(self, organization_id: UUID | None = None) -> DataExplorerStatsResponse:
        """Return the explorer summary cards and totals."""

        sections = [
            self._build_organization_section(organization_id),
            self._build_sales_section(organization_id),
            self._build_sale_items_section(organization_id),
            self._build_products_section(organization_id),
            self._build_customers_section(organization_id),
            self._build_inventory_section(organization_id),
            self._build_payments_section(organization_id),
            self._build_returns_section(organization_id),
            self._build_cash_operations_section(organization_id),
            self._build_bank_operations_section(organization_id),
            self._build_purchases_section(organization_id),
            self._build_stock_movements_section(organization_id),
            self._build_visits_section(organization_id),
            self._build_raw_section(organization_id),
            self._build_processing_section(organization_id),
        ]
        raw_records = self._count_raw_records_by_suffixes(organization_id=organization_id)
        normalized_records = self._count_normalized_records_total(organization_id=organization_id)
        processing_records = self._count_processing_items(organization_id)
        businesses = len(list(self.store.list_businesses()))

        return DataExplorerStatsResponse(
            organizations=self._count_smartup_organizations(organization_id)[0],
            businesses=businesses,
            core_records=self._count_core_records(organization_id),
            raw_records=raw_records,
            normalized_records=normalized_records,
            processing_records=processing_records,
            sections=sections,
        )

    def build_page(
        self,
        collection: DataExplorerCollection,
        *,
        organization_id: UUID | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> DataExplorerPageResponse:
        """Return a paginated page for one Data Explorer collection."""

        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        items = self._build_collection_rows(collection, organization_id)
        total = len(items)
        total_pages = max(1, ceil(total / page_size)) if total else 1
        start = (page - 1) * page_size
        end = start + page_size
        page_items = items[start:end]
        label = self._collection_specs()[collection].label
        return DataExplorerPageResponse(
            dataset=collection.value,
            label=label,
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            items=page_items,
        )

    def _collection_specs(self) -> dict[DataExplorerCollection, _CollectionSpec]:
        return {
            DataExplorerCollection.OVERVIEW: _CollectionSpec(
                key=DataExplorerCollection.OVERVIEW,
                label="Overview",
                href="/api/v1/data/overview",
                note=self._OVERVIEW_NOTE,
            ),
            DataExplorerCollection.SALES: _CollectionSpec(
                key=DataExplorerCollection.SALES,
                label="Sales",
                href="/api/v1/data/sales",
                note="Нормализованные продажи и их строки.",
                raw_endpoint_suffixes=("order$export",),
                normalized_tables=("normalized_sales",),
                row_builder=DataExplorerService._build_sales_rows,
                count_builder=DataExplorerService._count_sales,
            ),
            DataExplorerCollection.SALE_ITEMS: _CollectionSpec(
                key=DataExplorerCollection.SALE_ITEMS,
                label="Sale Items",
                href="/api/v1/data/sale-items",
                note="Строки заказов и проданных товаров.",
                raw_endpoint_suffixes=("order$export",),
                normalized_tables=("normalized_sale_items",),
                row_builder=DataExplorerService._build_sale_item_rows,
                count_builder=DataExplorerService._count_sale_items,
            ),
            DataExplorerCollection.PRODUCTS: _CollectionSpec(
                key=DataExplorerCollection.PRODUCTS,
                label="Products",
                href="/api/v1/data/products",
                note="Каталог товаров, групп, производителей и цен.",
                raw_endpoint_suffixes=(
                    "inventory$export",
                    "product_group$export",
                    "producer$export",
                    "price_type$export",
                    "product_price$export",
                    "service$export",
                    "person_group$export",
                    "return_reason$export",
                ),
                normalized_tables=(
                    "normalized_products",
                    "normalized_product_categories",
                    "normalized_warehouses",
                ),
                row_builder=DataExplorerService._build_product_rows,
                count_builder=DataExplorerService._count_products,
            ),
            DataExplorerCollection.CUSTOMERS: _CollectionSpec(
                key=DataExplorerCollection.CUSTOMERS,
                label="Customers",
                href="/api/v1/data/customers",
                note="Контрагенты, юридические и физические лица.",
                raw_endpoint_suffixes=("legal_person$export", "natural_person$export"),
                normalized_tables=("normalized_customers",),
                row_builder=DataExplorerService._build_customer_rows,
                count_builder=DataExplorerService._count_customers,
            ),
            DataExplorerCollection.INVENTORY: _CollectionSpec(
                key=DataExplorerCollection.INVENTORY,
                label="Inventory",
                href="/api/v1/data/inventory",
                note="Остатки и складские балансы.",
                raw_endpoint_suffixes=("balance$export",),
                normalized_tables=("normalized_inventory_balances", "inventory_snapshots"),
                row_builder=DataExplorerService._build_inventory_rows,
                count_builder=DataExplorerService._count_inventory,
            ),
            DataExplorerCollection.PAYMENTS: _CollectionSpec(
                key=DataExplorerCollection.PAYMENTS,
                label="Payments",
                href="/api/v1/data/payments",
                note="Платежи и поступления, привязанные к продажам.",
                raw_endpoint_suffixes=("cashin$export",),
                normalized_tables=("normalized_payments",),
                row_builder=DataExplorerService._build_payment_rows,
                count_builder=DataExplorerService._count_payments,
            ),
            DataExplorerCollection.RETURNS: _CollectionSpec(
                key=DataExplorerCollection.RETURNS,
                label="Returns",
                href="/api/v1/data/returns",
                note="Возвраты клиентов и возвраты поставщику.",
                raw_endpoint_suffixes=("return$export", "return_reason$export"),
                normalized_tables=("normalized_business_documents",),
                row_builder=DataExplorerService._build_return_rows,
                count_builder=DataExplorerService._count_returns,
            ),
            DataExplorerCollection.CASH_OPERATIONS: _CollectionSpec(
                key=DataExplorerCollection.CASH_OPERATIONS,
                label="Cash Operations",
                href="/api/v1/data/cash-operations",
                note="Кассовые операции и движения денег.",
                raw_endpoint_suffixes=("cash_operation$export",),
                normalized_tables=("normalized_bank_operations",),
                row_builder=DataExplorerService._build_cash_operation_rows,
                count_builder=DataExplorerService._count_cash_operations,
            ),
            DataExplorerCollection.BANK_OPERATIONS: _CollectionSpec(
                key=DataExplorerCollection.BANK_OPERATIONS,
                label="Bank Operations",
                href="/api/v1/data/bank-operations",
                note="Безналичные банковские операции.",
                raw_endpoint_suffixes=("bank_operation$export",),
                normalized_tables=("normalized_bank_operations",),
                row_builder=DataExplorerService._build_bank_operation_rows,
                count_builder=DataExplorerService._count_bank_operations,
            ),
            DataExplorerCollection.PURCHASES: _CollectionSpec(
                key=DataExplorerCollection.PURCHASES,
                label="Purchases",
                href="/api/v1/data/purchases",
                note="Закупки, приходы и документы поставок.",
                raw_endpoint_suffixes=("purchase$export", "input$export", "return$export"),
                normalized_tables=("normalized_business_documents",),
                row_builder=DataExplorerService._build_purchase_rows,
                count_builder=DataExplorerService._count_purchases,
            ),
            DataExplorerCollection.STOCK_MOVEMENTS: _CollectionSpec(
                key=DataExplorerCollection.STOCK_MOVEMENTS,
                label="Stock Movements",
                href="/api/v1/data/stock-movements",
                note="Перемещения, списания, инвентаризации и складские документы.",
                raw_endpoint_suffixes=("movement$export", "stocktaking$export", "writeoff$export"),
                normalized_tables=("normalized_business_documents",),
                row_builder=DataExplorerService._build_stock_movement_rows,
                count_builder=DataExplorerService._count_stock_movements,
            ),
            DataExplorerCollection.VISITS: _CollectionSpec(
                key=DataExplorerCollection.VISITS,
                label="Visits",
                href="/api/v1/data/visits",
                note="Выезды и визиты торговых представителей.",
                raw_endpoint_suffixes=("visit$export",),
                normalized_tables=("normalized_visits",),
                row_builder=DataExplorerService._build_visit_rows,
                count_builder=DataExplorerService._count_visits,
            ),
            DataExplorerCollection.ORGANIZATIONS: _CollectionSpec(
                key=DataExplorerCollection.ORGANIZATIONS,
                label="Organizations",
                href="/api/v1/data/organizations",
                note="Организации SmartUp, подключенные через filial_id.",
                normalized_tables=("smartup_organizations",),
                row_builder=DataExplorerService._build_organization_rows,
                count_builder=DataExplorerService._count_smartup_organizations,
            ),
            DataExplorerCollection.SMARTUP_RAW: _CollectionSpec(
                key=DataExplorerCollection.SMARTUP_RAW,
                label="SmartUp Raw",
                href="/api/v1/data/smartup-raw",
                note="Сырые ответы SmartUp до нормализации.",
                normalized_tables=("smartup_raw_records",),
                row_builder=DataExplorerService._build_raw_rows,
                count_builder=DataExplorerService._count_raw_records,
            ),
            DataExplorerCollection.PROCESSING: _CollectionSpec(
                key=DataExplorerCollection.PROCESSING,
                label="Processing",
                href="/api/v1/data/processing",
                note="Запуски, батчи, чекпоинты и проблемы импорта.",
                normalized_tables=(
                    "smartup_migration_runs",
                    "migration_batches",
                    "sync_checkpoints",
                    "normalization_issues",
                ),
                row_builder=DataExplorerService._build_processing_rows,
                count_builder=DataExplorerService._count_processing_section,
            ),
        }

    def _build_section(
        self,
        *,
        key: DataExplorerCollection,
        organization_id: UUID | None = None,
    ) -> DataExplorerSectionStats:
        spec = self._collection_specs()[key]
        raw_count, normalized_count = spec.count_builder(self, organization_id)
        total = normalized_count or raw_count
        if total > 0:
            state = DataExplorerState.AVAILABLE
        elif raw_count > 0:
            state = DataExplorerState.UNAVAILABLE
        else:
            state = DataExplorerState.EMPTY
        return DataExplorerSectionStats(
            key=key.value,
            label=spec.label,
            href=spec.href,
            count=total,
            raw_count=raw_count,
            normalized_count=normalized_count,
            state=state,
            note=spec.note,
        )

    def _build_organization_section(self, organization_id: UUID | None) -> DataExplorerSectionStats:
        return self._build_section(
            key=DataExplorerCollection.ORGANIZATIONS, organization_id=organization_id
        )

    def _build_sales_section(self, organization_id: UUID | None) -> DataExplorerSectionStats:
        return self._build_section(
            key=DataExplorerCollection.SALES, organization_id=organization_id
        )

    def _build_sale_items_section(self, organization_id: UUID | None) -> DataExplorerSectionStats:
        return self._build_section(
            key=DataExplorerCollection.SALE_ITEMS,
            organization_id=organization_id,
        )

    def _build_products_section(self, organization_id: UUID | None) -> DataExplorerSectionStats:
        return self._build_section(
            key=DataExplorerCollection.PRODUCTS, organization_id=organization_id
        )

    def _build_customers_section(self, organization_id: UUID | None) -> DataExplorerSectionStats:
        return self._build_section(
            key=DataExplorerCollection.CUSTOMERS, organization_id=organization_id
        )

    def _build_inventory_section(self, organization_id: UUID | None) -> DataExplorerSectionStats:
        return self._build_section(
            key=DataExplorerCollection.INVENTORY, organization_id=organization_id
        )

    def _build_payments_section(self, organization_id: UUID | None) -> DataExplorerSectionStats:
        return self._build_section(
            key=DataExplorerCollection.PAYMENTS, organization_id=organization_id
        )

    def _build_returns_section(self, organization_id: UUID | None) -> DataExplorerSectionStats:
        return self._build_section(
            key=DataExplorerCollection.RETURNS, organization_id=organization_id
        )

    def _build_cash_operations_section(
        self,
        organization_id: UUID | None,
    ) -> DataExplorerSectionStats:
        return self._build_section(
            key=DataExplorerCollection.CASH_OPERATIONS,
            organization_id=organization_id,
        )

    def _build_bank_operations_section(
        self,
        organization_id: UUID | None,
    ) -> DataExplorerSectionStats:
        return self._build_section(
            key=DataExplorerCollection.BANK_OPERATIONS,
            organization_id=organization_id,
        )

    def _build_purchases_section(self, organization_id: UUID | None) -> DataExplorerSectionStats:
        return self._build_section(
            key=DataExplorerCollection.PURCHASES, organization_id=organization_id
        )

    def _build_stock_movements_section(
        self,
        organization_id: UUID | None,
    ) -> DataExplorerSectionStats:
        return self._build_section(
            key=DataExplorerCollection.STOCK_MOVEMENTS,
            organization_id=organization_id,
        )

    def _build_visits_section(self, organization_id: UUID | None) -> DataExplorerSectionStats:
        return self._build_section(
            key=DataExplorerCollection.VISITS, organization_id=organization_id
        )

    def _build_raw_section(self, organization_id: UUID | None) -> DataExplorerSectionStats:
        return self._build_section(
            key=DataExplorerCollection.SMARTUP_RAW, organization_id=organization_id
        )

    def _build_processing_section(self, organization_id: UUID | None) -> DataExplorerSectionStats:
        return self._build_section(
            key=DataExplorerCollection.PROCESSING, organization_id=organization_id
        )

    def _build_collection_rows(
        self,
        collection: DataExplorerCollection,
        organization_id: UUID | None,
    ) -> list[dict[str, Any]]:
        spec = self._collection_specs()[collection]
        if spec.row_builder is None:
            return []
        return spec.row_builder(self, organization_id)

    def _build_sales_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        sale_items = list(self.store.list_sale_items(organization_id=organization_id))
        sales = list(self.store.list_sales_v2(organization_id=organization_id))
        sale_items_by_sale: dict[UUID, list] = {}
        for item in sale_items:
            if item.sale_id is None:
                continue
            sale_items_by_sale.setdefault(item.sale_id, []).append(item)
        rows: list[dict[str, Any]] = []
        for sale in sorted(sales, key=lambda item: item.sale_at, reverse=True):
            items = sale_items_by_sale.get(sale.id, [])
            rows.append(
                {
                    "id": str(sale.id),
                    "organization_id": str(sale.organization_id),
                    "organization_name": self._organization_names.get(
                        sale.organization_id,
                        str(sale.organization_id),
                    ),
                    "source_external_id": sale.source_external_id,
                    "sale_number": sale.sale_number,
                    "amount": str(sale.amount),
                    "currency": sale.currency,
                    "status": sale.status,
                    "sale_at": sale.sale_at,
                    "items_count": len(items),
                    "products_count": len(
                        {item.product_external_id for item in items if item.product_external_id},
                    ),
                    "details_href": f"/api/v1/data/sales?organization_id={sale.organization_id}",
                },
            )
        return rows

    def _build_sale_item_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        items = list(self.store.list_sale_items(organization_id=organization_id))
        rows = []
        for item in sorted(items, key=lambda value: value.imported_at, reverse=True):
            rows.append(
                {
                    "id": str(item.id),
                    "organization_id": str(item.organization_id),
                    "organization_name": self._organization_names.get(
                        item.organization_id,
                        str(item.organization_id),
                    ),
                    "sale_id": str(item.sale_id) if item.sale_id else None,
                    "sale_external_id": item.sale_external_id,
                    "product_external_id": item.product_external_id,
                    "quantity": str(item.quantity),
                    "unit_price": str(item.unit_price) if item.unit_price is not None else None,
                    "amount": str(item.amount),
                    "currency": item.currency,
                    "source_external_id": item.source_external_id,
                    "details_href": self._organization_details_href(
                        "/api/v1/data/sale-items",
                        item.organization_id,
                    ),
                },
            )
        return rows

    def _build_product_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        products = list(self.store.list_products(organization_id=organization_id))
        inventory_balances = list(
            self.store.list_inventory_balances(organization_id=organization_id)
        )
        sale_items = list(self.store.list_sale_items(organization_id=organization_id))
        sold_by_product: dict[str, Decimal] = {}
        sold_amount_by_product: dict[str, Decimal] = {}
        for item in sale_items:
            if item.product_external_id is None:
                continue
            sold_by_product[item.product_external_id] = (
                sold_by_product.get(
                    item.product_external_id,
                    Decimal("0"),
                )
                + item.quantity
            )
            sold_amount_by_product[item.product_external_id] = (
                sold_amount_by_product.get(
                    item.product_external_id,
                    Decimal("0"),
                )
                + item.amount
            )
        stock_by_product: dict[str, Decimal] = {}
        for balance in inventory_balances:
            stock_by_product[balance.product_external_id] = (
                stock_by_product.get(
                    balance.product_external_id,
                    Decimal("0"),
                )
                + balance.quantity
            )
        rows = []
        for product in sorted(products, key=lambda value: value.name.lower()):
            rows.append(
                {
                    "id": str(product.id),
                    "organization_id": str(product.organization_id),
                    "organization_name": self._organization_names.get(
                        product.organization_id,
                        str(product.organization_id),
                    ),
                    "name": product.name,
                    "sku": product.sku,
                    "unit": product.unit,
                    "category_external_id": product.category_external_id,
                    "source_external_id": product.source_external_id,
                    "sold_quantity": str(
                        sold_by_product.get(product.source_external_id, Decimal("0"))
                    ),
                    "sold_amount": str(
                        sold_amount_by_product.get(product.source_external_id, Decimal("0"))
                    ),
                    "stock_quantity": str(
                        stock_by_product.get(product.source_external_id, Decimal("0"))
                    ),
                    "details_href": self._organization_details_href(
                        "/api/v1/data/products",
                        product.organization_id,
                    ),
                },
            )
        return rows

    def _build_customer_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        customers = list(self.store.list_customers(organization_id=organization_id))
        rows = []
        for customer in sorted(customers, key=lambda value: value.name.lower()):
            rows.append(
                {
                    "id": str(customer.id),
                    "organization_id": str(customer.organization_id),
                    "organization_name": self._organization_names.get(
                        customer.organization_id,
                        str(customer.organization_id),
                    ),
                    "name": customer.name,
                    "display_name": customer.display_name,
                    "phone": customer.phone,
                    "email": customer.email,
                    "source_external_id": customer.source_external_id,
                    "details_href": self._organization_details_href(
                        "/api/v1/data/customers",
                        customer.organization_id,
                    ),
                },
            )
        return rows

    def _build_inventory_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        balances = list(self.store.list_inventory_balances(organization_id=organization_id))
        rows = []
        for balance in sorted(balances, key=lambda value: value.balance_at, reverse=True):
            rows.append(
                {
                    "id": str(balance.id),
                    "organization_id": str(balance.organization_id),
                    "organization_name": self._organization_names.get(
                        balance.organization_id,
                        str(balance.organization_id),
                    ),
                    "warehouse_external_id": balance.warehouse_external_id,
                    "product_external_id": balance.product_external_id,
                    "quantity": str(balance.quantity),
                    "balance_at": balance.balance_at,
                    "source_external_id": balance.source_external_id,
                    "details_href": self._organization_details_href(
                        "/api/v1/data/inventory",
                        balance.organization_id,
                    ),
                },
            )
        return rows

    def _build_payment_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        payments = list(self.store.list_payments(organization_id=organization_id))
        rows = []
        for payment in sorted(payments, key=lambda value: value.paid_at, reverse=True):
            rows.append(
                {
                    "id": str(payment.id),
                    "organization_id": str(payment.organization_id),
                    "organization_name": self._organization_names.get(
                        payment.organization_id,
                        str(payment.organization_id),
                    ),
                    "sale_external_id": payment.sale_external_id,
                    "amount": str(payment.amount),
                    "currency": payment.currency,
                    "paid_at": payment.paid_at,
                    "method": payment.method,
                    "source_external_id": payment.source_external_id,
                    "details_href": self._organization_details_href(
                        "/api/v1/data/payments",
                        payment.organization_id,
                    ),
                },
            )
        return rows

    def _build_operation_rows(
        self,
        organization_id: UUID | None,
        *,
        source_endpoint_suffixes: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        operations = list(self.store.list_bank_operations(organization_id=organization_id))
        if source_endpoint_suffixes is not None:
            operations = [
                operation
                for operation in operations
                if any(
                    str(operation.metadata.get("source_endpoint", "")).endswith(suffix)
                    for suffix in source_endpoint_suffixes
                )
            ]
        rows: list[dict[str, Any]] = []
        for operation in sorted(operations, key=lambda value: value.occurred_at, reverse=True):
            rows.append(
                {
                    "id": str(operation.id),
                    "organization_id": str(operation.organization_id),
                    "organization_name": self._organization_names.get(
                        operation.organization_id,
                        str(operation.organization_id),
                    ),
                    "amount": str(operation.amount),
                    "currency": operation.currency,
                    "occurred_at": operation.occurred_at,
                    "operation_type": operation.operation_type,
                    "description": operation.description,
                    "source_external_id": operation.source_external_id,
                    "source_endpoint": operation.metadata.get("source_endpoint"),
                    "details_href": self._organization_details_href(
                        "/api/v1/data/processing",
                        operation.organization_id,
                    ),
                },
            )
        return rows

    def _build_cash_operation_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        return self._build_operation_rows(
            organization_id,
            source_endpoint_suffixes=("cash_operation$export",),
        )

    def _build_bank_operation_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        return self._build_operation_rows(
            organization_id,
            source_endpoint_suffixes=("bank_operation$export",),
        )

    def _build_document_rows(
        self,
        *,
        organization_id: UUID | None,
        document_types: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        documents = [
            document
            for document in self.store.list_business_documents(organization_id=organization_id)
            if document.document_type in document_types
        ]
        document_items = list(
            self.store.list_business_document_items(organization_id=organization_id)
        )
        items_by_document: dict[UUID, list[BusinessDocumentItem]] = {}
        for item in document_items:
            items_by_document.setdefault(item.document_id, []).append(item)
        rows: list[dict[str, Any]] = []
        for document in sorted(documents, key=lambda value: value.document_at, reverse=True):
            rows.append(
                {
                    "id": str(document.id),
                    "organization_id": str(document.organization_id),
                    "organization_name": self._organization_names.get(
                        document.organization_id,
                        str(document.organization_id),
                    ),
                    "document_type": document.document_type,
                    "document_number": document.document_number,
                    "status": document.status,
                    "document_at": document.document_at,
                    "counterparty_external_id": document.counterparty_external_id,
                    "warehouse_external_id": document.warehouse_external_id,
                    "product_external_id": document.product_external_id,
                    "quantity": str(document.quantity),
                    "amount": str(document.amount),
                    "currency": document.currency,
                    "items_count": len(items_by_document.get(document.id, [])),
                    "source_external_id": document.source_external_id,
                    "details_href": self._organization_details_href(
                        "/api/v1/data/processing",
                        document.organization_id,
                    ),
                },
            )
        return rows

    def _build_return_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        return self._build_document_rows(
            organization_id=organization_id,
            document_types=("return", "return_to_supplier"),
        )

    def _build_purchase_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        return self._build_document_rows(
            organization_id=organization_id,
            document_types=("purchase", "warehouse_receipt"),
        )

    def _build_stock_movement_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        return self._build_document_rows(
            organization_id=organization_id,
            document_types=(
                "cross_organizational_movement",
                "internal_movement",
                "write_off",
                "stocktaking",
                "logistics",
                "equipment_movement",
                "equipment_request",
                "warehouse_receipt",
            ),
        )

    def _build_visit_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        visits = list(self.store.list_visits(organization_id=organization_id))
        rows = []
        for visit in sorted(visits, key=lambda value: value.visited_at, reverse=True):
            rows.append(
                {
                    "id": str(visit.id),
                    "organization_id": str(visit.organization_id),
                    "organization_name": self._organization_names.get(
                        visit.organization_id,
                        str(visit.organization_id),
                    ),
                    "customer_external_id": visit.customer_external_id,
                    "visited_at": visit.visited_at,
                    "status": visit.status,
                    "source_external_id": visit.source_external_id,
                    "details_href": self._organization_details_href(
                        "/api/v1/data/visits",
                        visit.organization_id,
                    ),
                },
            )
        return rows

    def _build_organization_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        organizations = list(self.store.list_smartup_organizations())
        if organization_id is not None:
            organizations = [
                organization for organization in organizations if organization.id == organization_id
            ]
        rows = []
        for organization in sorted(
            organizations, key=lambda value: (value.sort_order, value.name.lower())
        ):
            rows.append(
                {
                    "id": str(organization.id),
                    "name": organization.name,
                    "company_id": organization.company_id,
                    "filial_id": organization.filial_id,
                    "project_code": organization.project_code,
                    "is_active": organization.is_active,
                    "sort_order": organization.sort_order,
                    "last_sync_at": organization.last_sync_at,
                    "details_href": self._organization_details_href(
                        "/api/v1/data/organizations",
                        organization.id,
                    ),
                },
            )
        return rows

    def _build_raw_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        raw_records = list(self.store.list_smartup_raw_records(organization_id=organization_id))
        rows = []
        for record in sorted(raw_records, key=lambda value: value.imported_at, reverse=True):
            rows.append(
                {
                    "id": str(record.id),
                    "organization_id": str(record.organization_id),
                    "organization_name": self._organization_names.get(
                        record.organization_id,
                        str(record.organization_id),
                    ),
                    "filial_id": record.filial_id,
                    "entity_type": record.entity_type,
                    "external_id": record.external_id,
                    "source_endpoint": record.source_endpoint,
                    "processing_status": str(record.processing_status),
                    "processing_error": record.processing_error,
                    "imported_at": record.imported_at,
                    "batch_id": str(record.batch_id) if record.batch_id else None,
                    "checksum": record.checksum,
                    "details_href": self._organization_details_href(
                        "/api/v1/data/smartup-raw",
                        record.organization_id,
                    ),
                },
            )
        return rows

    def _build_processing_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for run in self.store.list_smartup_migration_runs(organization_id=organization_id):
            rows.append(
                {
                    "kind": "migration_run",
                    "id": str(run.run_id),
                    "organization_id": str(run.organization_id),
                    "organization_name": self._organization_names.get(
                        run.organization_id,
                        str(run.organization_id),
                    ),
                    "entity_type": run.entity_type,
                    "status": str(run.status),
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                    "imported_count": run.imported_count,
                    "updated_count": run.updated_count,
                    "skipped_count": run.skipped_count,
                    "failed_count": run.failed_count,
                },
            )
        for batch in self.store.list_migration_batches(organization_id=organization_id):
            rows.append(
                {
                    "kind": "migration_batch",
                    "id": str(batch.id),
                    "organization_id": str(batch.organization_id),
                    "organization_name": self._organization_names.get(
                        batch.organization_id,
                        str(batch.organization_id),
                    ),
                    "filial_id": batch.filial_id,
                    "entity_type": batch.entity_type,
                    "endpoint": batch.endpoint,
                    "status": str(batch.status),
                    "date_from": batch.date_from,
                    "date_to": batch.date_to,
                    "received_count": batch.received_count,
                    "inserted_count": batch.inserted_count,
                    "updated_count": batch.updated_count,
                    "skipped_count": batch.skipped_count,
                    "failed_count": batch.failed_count,
                    "upstream_status": batch.upstream_status,
                    "upstream_response": batch.upstream_response,
                    "started_at": batch.started_at,
                    "finished_at": batch.finished_at,
                },
            )
        for checkpoint in self.store.list_sync_checkpoints(organization_id=organization_id):
            rows.append(
                {
                    "kind": "sync_checkpoint",
                    "id": str(checkpoint.id),
                    "organization_id": str(checkpoint.organization_id),
                    "organization_name": self._organization_names.get(
                        checkpoint.organization_id,
                        str(checkpoint.organization_id),
                    ),
                    "entity_type": checkpoint.entity_type,
                    "migration_mode": str(checkpoint.migration_mode),
                    "period_start": checkpoint.period_start,
                    "period_end": checkpoint.period_end,
                    "last_successful_date": checkpoint.last_successful_date,
                    "last_successful_external_id": checkpoint.last_successful_external_id,
                    "status": str(checkpoint.status),
                    "attempts": checkpoint.attempts,
                    "last_error": checkpoint.last_error,
                    "updated_at": checkpoint.updated_at,
                },
            )
        for issue in self.store.list_normalization_issues(organization_id=organization_id):
            rows.append(
                {
                    "kind": "normalization_issue",
                    "id": str(issue.id),
                    "organization_id": str(issue.organization_id),
                    "organization_name": self._organization_names.get(
                        issue.organization_id,
                        str(issue.organization_id),
                    ),
                    "entity_type": issue.entity_type,
                    "issue_type": issue.issue_type,
                    "field_name": issue.field_name,
                    "message": issue.message,
                    "severity": str(issue.severity),
                    "created_at": issue.created_at,
                },
            )
        rows.sort(key=self._processing_sort_key, reverse=True)
        return rows

    def _processing_sort_key(self, item: dict[str, Any]) -> datetime:
        for key in (
            "started_at",
            "created_at",
            "updated_at",
            "period_start",
            "date_from",
            "imported_at",
        ):
            value = item.get(key)
            if isinstance(value, datetime):
                return value
        return datetime.min.replace(tzinfo=UTC)

    def _count_smartup_organizations(self, organization_id: UUID | None = None) -> tuple[int, int]:
        if organization_id is None:
            return len(list(self.store.list_smartup_organizations())), 0
        organizations = [
            organization
            for organization in self.store.list_smartup_organizations()
            if organization.id == organization_id
        ]
        return len(organizations), 0

    def _count_core_records(self, organization_id: UUID | None = None) -> int:
        if organization_id is None:
            return len(list(self.store.list_records()))
        return len(list(self.store.list_records(business_id=organization_id)))

    def _count_normalized_records_total(self, organization_id: UUID | None = None) -> int:
        return (
            self._count_table_rows("normalized_customers", organization_id=organization_id)
            + self._count_table_rows(
                "normalized_product_categories", organization_id=organization_id
            )
            + self._count_table_rows("normalized_products", organization_id=organization_id)
            + self._count_table_rows("normalized_warehouses", organization_id=organization_id)
            + self._count_table_rows("normalized_sales", organization_id=organization_id)
            + self._count_table_rows("normalized_sale_items", organization_id=organization_id)
            + self._count_table_rows("normalized_payments", organization_id=organization_id)
            + self._count_table_rows(
                "normalized_inventory_balances", organization_id=organization_id
            )
            + self._count_table_rows("normalized_visits", organization_id=organization_id)
            + self._count_table_rows("normalized_bank_operations", organization_id=organization_id)
            + self._count_table_rows(
                "normalized_business_documents", organization_id=organization_id
            )
            + self._count_table_rows(
                "normalized_business_document_items", organization_id=organization_id
            )
            + self._count_table_rows("inventory_snapshots", organization_id=organization_id)
        )

    def _count_raw_records(self, organization_id: UUID | None = None) -> tuple[int, int]:
        return self._count_raw_records_by_suffixes(organization_id=organization_id), 0

    def _count_sales(self, organization_id: UUID | None = None) -> tuple[int, int]:
        return (
            self._count_raw_records_by_suffixes(
                organization_id=organization_id,
                endpoint_suffixes=("order$export",),
            ),
            self._count_table_rows("normalized_sales", organization_id=organization_id),
        )

    def _count_sale_items(self, organization_id: UUID | None = None) -> tuple[int, int]:
        raw = self._count_raw_records_by_suffixes(
            organization_id=organization_id,
            endpoint_suffixes=("order$export",),
        )
        return raw, self._count_table_rows("normalized_sale_items", organization_id=organization_id)

    def _count_products(self, organization_id: UUID | None = None) -> tuple[int, int]:
        raw = self._count_raw_records_by_suffixes(
            organization_id=organization_id,
            endpoint_suffixes=(
                "inventory$export",
                "product_group$export",
                "producer$export",
                "price_type$export",
                "product_price$export",
                "service$export",
                "person_group$export",
                "return_reason$export",
            ),
        )
        normalized = (
            self._count_table_rows("normalized_products", organization_id=organization_id)
            + self._count_table_rows(
                "normalized_product_categories", organization_id=organization_id
            )
            + self._count_table_rows("normalized_warehouses", organization_id=organization_id)
        )
        return raw, normalized

    def _count_customers(self, organization_id: UUID | None = None) -> tuple[int, int]:
        raw = self._count_raw_records_by_suffixes(
            organization_id=organization_id,
            endpoint_suffixes=("legal_person$export", "natural_person$export"),
        )
        return raw, self._count_table_rows("normalized_customers", organization_id=organization_id)

    def _count_inventory(self, organization_id: UUID | None = None) -> tuple[int, int]:
        raw = self._count_raw_records_by_suffixes(
            organization_id=organization_id, endpoint_suffixes=("balance$export",)
        )
        normalized = self._count_table_rows(
            "normalized_inventory_balances", organization_id=organization_id
        ) + self._count_table_rows("inventory_snapshots", organization_id=organization_id)
        return raw, normalized

    def _count_payments(self, organization_id: UUID | None = None) -> tuple[int, int]:
        raw = self._count_raw_records_by_suffixes(
            organization_id=organization_id,
            endpoint_suffixes=("cashin$export",),
        )
        return raw, self._count_table_rows("normalized_payments", organization_id=organization_id)

    def _count_returns(self, organization_id: UUID | None = None) -> tuple[int, int]:
        raw = self._count_raw_records_by_suffixes(
            organization_id=organization_id,
            endpoint_suffixes=("return$export", "return_reason$export"),
        )
        normalized = self._count_business_documents(
            organization_id=organization_id,
            document_types=("return", "return_to_supplier"),
        )
        return raw, normalized

    def _count_cash_operations(self, organization_id: UUID | None = None) -> tuple[int, int]:
        raw = self._count_raw_records_by_suffixes(
            organization_id=organization_id,
            endpoint_suffixes=("cash_operation$export",),
        )
        return raw, self._count_normalized_bank_operations(
            organization_id=organization_id,
            source_endpoint_suffixes=("cash_operation$export",),
        )

    def _count_bank_operations(self, organization_id: UUID | None = None) -> tuple[int, int]:
        raw = self._count_raw_records_by_suffixes(
            organization_id=organization_id,
            endpoint_suffixes=("bank_operation$export",),
        )
        return raw, self._count_normalized_bank_operations(
            organization_id=organization_id,
            source_endpoint_suffixes=("bank_operation$export",),
        )

    def _count_purchases(self, organization_id: UUID | None = None) -> tuple[int, int]:
        raw = self._count_raw_records_by_suffixes(
            organization_id=organization_id,
            endpoint_suffixes=("purchase$export", "input$export", "return$export"),
        )
        normalized = self._count_business_documents(
            organization_id=organization_id,
            document_types=("purchase", "warehouse_receipt"),
        )
        return raw, normalized

    def _count_stock_movements(self, organization_id: UUID | None = None) -> tuple[int, int]:
        raw = self._count_raw_records_by_suffixes(
            organization_id=organization_id,
            endpoint_suffixes=("movement$export", "stocktaking$export", "writeoff$export"),
        )
        normalized = self._count_business_documents(
            organization_id=organization_id,
            document_types=(
                "cross_organizational_movement",
                "internal_movement",
                "write_off",
                "stocktaking",
                "logistics",
                "equipment_movement",
                "equipment_request",
                "warehouse_receipt",
            ),
        )
        return raw, normalized

    def _count_visits(self, organization_id: UUID | None = None) -> tuple[int, int]:
        raw = self._count_raw_records_by_suffixes(
            organization_id=organization_id, endpoint_suffixes=("visit$export",)
        )
        return raw, self._count_table_rows("normalized_visits", organization_id=organization_id)

    def _count_processing_items(self, organization_id: UUID | None = None) -> int:
        return (
            len(list(self.store.list_smartup_migration_runs(organization_id=organization_id)))
            + len(list(self.store.list_migration_batches(organization_id=organization_id)))
            + len(list(self.store.list_sync_checkpoints(organization_id=organization_id)))
            + len(list(self.store.list_normalization_issues(organization_id=organization_id)))
        )

    def _count_processing_section(self, organization_id: UUID | None = None) -> tuple[int, int]:
        return self._count_processing_items(organization_id), 0

    def _count_business_documents(
        self,
        *,
        organization_id: UUID | None = None,
        document_types: tuple[str, ...] | None = None,
    ) -> int:
        documents = self.store.list_business_documents(organization_id=organization_id)
        if document_types is None:
            return len(list(documents))
        return len([document for document in documents if document.document_type in document_types])

    def _count_normalized_bank_operations(
        self,
        *,
        organization_id: UUID | None = None,
        source_endpoint_suffixes: tuple[str, ...] | None = None,
    ) -> int:
        operations = list(self.store.list_bank_operations(organization_id=organization_id))
        if source_endpoint_suffixes is None:
            return len(operations)
        filtered = [
            operation
            for operation in operations
            if any(
                str(operation.metadata.get("source_endpoint", "")).endswith(suffix)
                for suffix in source_endpoint_suffixes
            )
        ]
        return len(filtered)

    def _count_table_rows(
        self,
        table: str,
        *,
        organization_id: UUID | None = None,
    ) -> int:
        if isinstance(self.store, PostgresCoreStore):
            clauses = []
            params: list[Any] = []
            if organization_id is not None:
                clauses.append("organization_id = %s")
                params.append(organization_id)
            sql = f"SELECT COUNT(*) AS count FROM {table}"
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            with self.store.connection_factory().cursor() as cursor:
                cursor.execute(sql, tuple(params) if params else None)
                row = cursor.fetchone() or {}
            return int(row.get("count", 0))

        if table == "normalized_sales":
            return len(list(self.store.list_sales_v2(organization_id=organization_id)))
        if table == "normalized_sale_items":
            return len(list(self.store.list_sale_items(organization_id=organization_id)))
        if table == "normalized_products":
            return len(list(self.store.list_products(organization_id=organization_id)))
        if table == "normalized_product_categories":
            return len(list(self.store.list_product_categories(organization_id=organization_id)))
        if table == "normalized_warehouses":
            return len(list(self.store.list_warehouses(organization_id=organization_id)))
        if table == "normalized_customers":
            return len(list(self.store.list_customers(organization_id=organization_id)))
        if table == "normalized_inventory_balances":
            return len(list(self.store.list_inventory_balances(organization_id=organization_id)))
        if table == "normalized_payments":
            return len(list(self.store.list_payments(organization_id=organization_id)))
        if table == "normalized_visits":
            return len(list(self.store.list_visits(organization_id=organization_id)))
        if table == "normalized_bank_operations":
            return len(list(self.store.list_bank_operations(organization_id=organization_id)))
        if table == "normalized_business_documents":
            return len(self._filter_business_documents(organization_id=organization_id))
        if table == "normalized_business_document_items":
            return len(
                list(self.store.list_business_document_items(organization_id=organization_id))
            )
        if table == "inventory_snapshots":
            return len(list(self.store.list_inventory_snapshots(organization_id=organization_id)))
        if table == "smartup_organizations":
            organizations = list(self.store.list_smartup_organizations())
            if organization_id is not None:
                organizations = [
                    organization
                    for organization in organizations
                    if organization.id == organization_id
                ]
            return len(organizations)
        if table == "smartup_migration_runs":
            return len(
                list(self.store.list_smartup_migration_runs(organization_id=organization_id))
            )
        if table == "migration_batches":
            return len(list(self.store.list_migration_batches(organization_id=organization_id)))
        if table == "sync_checkpoints":
            return len(list(self.store.list_sync_checkpoints(organization_id=organization_id)))
        if table == "normalization_issues":
            return len(list(self.store.list_normalization_issues(organization_id=organization_id)))
        return 0

    def _count_raw_records_by_suffixes(
        self,
        *,
        organization_id: UUID | None = None,
        endpoint_suffixes: tuple[str, ...] | None = None,
    ) -> int:
        if isinstance(self.store, PostgresCoreStore):
            clauses = []
            params: list[Any] = []
            if organization_id is not None:
                clauses.append("organization_id = %s")
                params.append(organization_id)
            if endpoint_suffixes:
                clauses.append("source_endpoint LIKE ANY(%s)")
                params.append([f"%{suffix}" for suffix in endpoint_suffixes])
            sql = "SELECT COUNT(*) AS count FROM smartup_raw_records"
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            with self.store.connection_factory().cursor() as cursor:
                cursor.execute(sql, tuple(params) if params else None)
                row = cursor.fetchone() or {}
            return int(row.get("count", 0))

        records = list(self.store.list_smartup_raw_records(organization_id=organization_id))
        if endpoint_suffixes:
            records = [
                record
                for record in records
                if any(str(record.source_endpoint).endswith(suffix) for suffix in endpoint_suffixes)
            ]
        return len(records)

    def _filter_business_documents(
        self,
        *,
        organization_id: UUID | None = None,
        document_types: tuple[str, ...] | None = None,
    ) -> list[BusinessDocument]:
        documents = list(self.store.list_business_documents(organization_id=organization_id))
        if document_types is not None:
            documents = [
                document for document in documents if document.document_type in document_types
            ]
        return documents

    def _organization_details_href(self, path: str, organization_id: UUID) -> str:
        return f"{path}?organization_id={organization_id}"


def paginate_items(items: list[dict[str, Any]], page: int, page_size: int) -> list[dict[str, Any]]:
    """Slice a list of items using one-based pagination."""

    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end]
