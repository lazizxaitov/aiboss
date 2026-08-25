"""Canonical Inventory / Warehouse workspace service."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from math import ceil
from typing import TypeVar
from uuid import UUID

from app.core.analytics.engine import BusinessAnalyticsEngine
from app.core.analytics.models import (
    AnalyticsDataStatus,
    AnalyticsInventoryReport,
    AnalyticsMetricValue,
    AnalyticsProductItem,
    AnalyticsQuery,
)
from app.core.data_layer.canonical_v2 import (
    CanonicalCrossOrgMovement,
    CanonicalDataQualityStatus,
    CanonicalInternalMovement,
    CanonicalInventoryBalance,
    CanonicalOrganization,
    CanonicalProduct,
    CanonicalProductCategory,
    CanonicalPurchase,
    CanonicalStocktaking,
    CanonicalSupplierReturn,
    CanonicalWarehouse,
    CanonicalWarehouseReceipt,
    CanonicalWriteoff,
)
from app.core.data_layer.contracts import CoreDataStore
from app.core.inventory_workspace.models import (
    InventoryWorkspaceCapabilityStatus,
    InventoryWorkspaceCurrentStockDetail,
    InventoryWorkspaceCurrentStockRow,
    InventoryWorkspaceFilterOption,
    InventoryWorkspaceFiltersMetadata,
    InventoryWorkspaceMovementRow,
    InventoryWorkspacePagination,
    InventoryWorkspacePurchaseRow,
    InventoryWorkspaceQuery,
    InventoryWorkspaceReceiptRow,
    InventoryWorkspaceResponse,
    InventoryWorkspaceRows,
    InventoryWorkspaceSortBy,
    InventoryWorkspaceSortOrder,
    InventoryWorkspaceStockStatus,
    InventoryWorkspaceStocktakingRow,
    InventoryWorkspaceSummary,
    InventoryWorkspaceSupplierReturnRow,
    InventoryWorkspaceTabStatus,
    InventoryWorkspaceView,
    InventoryWorkspaceWarehouseDetail,
    InventoryWorkspaceWarehouseRow,
    InventoryWorkspaceWriteoffRow,
)

T = TypeVar("T")


@dataclass(slots=True)
class _ScopedInventoryData:
    organizations_by_id: dict[UUID, CanonicalOrganization]
    products_by_id: dict[UUID, CanonicalProduct]
    categories_by_id: dict[UUID, CanonicalProductCategory]
    warehouses_by_id: dict[UUID, CanonicalWarehouse]
    balances: list[CanonicalInventoryBalance]
    latest_balances: list[CanonicalInventoryBalance]
    purchases: list[CanonicalPurchase]
    receipts: list[CanonicalWarehouseReceipt]
    writeoffs: list[CanonicalWriteoff]
    supplier_returns: list[CanonicalSupplierReturn]
    stocktakings: list[CanonicalStocktaking]
    internal_movements: list[CanonicalInternalMovement]
    cross_org_movements: list[CanonicalCrossOrgMovement]


class InventoryWorkspaceService:
    """Build inventory / warehouse workspace payloads from Canonical V2."""

    def __init__(self, store: CoreDataStore) -> None:
        self._store = store
        self._analytics = BusinessAnalyticsEngine(store)

    def list_workspace(
        self,
        analytics_query: AnalyticsQuery,
        workspace_query: InventoryWorkspaceQuery,
    ) -> InventoryWorkspaceResponse:
        summary_payload = self._analytics.build_summary(analytics_query)
        inventory_report = self._analytics.build_inventory(analytics_query)
        scoped = self._load_scoped_data(analytics_query)

        current_stock_rows = self._build_current_stock_rows(scoped, inventory_report)
        warehouse_rows = self._build_warehouse_rows(scoped, current_stock_rows)
        purchase_rows = self._build_purchase_rows(scoped)
        receipt_rows = self._build_receipt_rows(scoped)
        writeoff_rows = self._build_writeoff_rows(scoped)
        movement_rows = self._build_movement_rows(scoped)
        stocktaking_rows = self._build_stocktaking_rows(scoped)
        supplier_return_rows = self._build_supplier_return_rows(scoped)

        filters = self._build_filters_metadata(scoped, current_stock_rows)
        tabs = self._build_tabs(
            current_stock_rows,
            warehouse_rows,
            purchase_rows,
            receipt_rows,
            writeoff_rows,
            movement_rows,
            stocktaking_rows,
            supplier_return_rows,
        )

        filtered_current_stock = self._filter_current_stock_rows(
            current_stock_rows,
            workspace_query,
        )
        filtered_warehouses = self._filter_warehouse_rows(
            warehouse_rows,
            workspace_query,
        )
        filtered_purchases = self._filter_document_rows(purchase_rows, workspace_query)
        filtered_receipts = self._filter_document_rows(receipt_rows, workspace_query)
        filtered_writeoffs = self._filter_document_rows(writeoff_rows, workspace_query)
        filtered_movements = self._filter_movement_rows(movement_rows, workspace_query)
        filtered_stocktaking = self._filter_document_rows(stocktaking_rows, workspace_query)
        filtered_supplier_returns = self._filter_document_rows(
            supplier_return_rows,
            workspace_query,
        )

        rows_map: dict[InventoryWorkspaceView, list[object]] = {
            InventoryWorkspaceView.CURRENT_STOCK: self._sort_current_stock_rows(
                filtered_current_stock,
                workspace_query.sort_by,
                workspace_query.sort_order,
            ),
            InventoryWorkspaceView.WAREHOUSES: self._sort_warehouse_rows(
                filtered_warehouses,
                workspace_query.sort_by,
                workspace_query.sort_order,
            ),
            InventoryWorkspaceView.PURCHASES: self._sort_document_rows(
                filtered_purchases,
                workspace_query.sort_by,
                workspace_query.sort_order,
            ),
            InventoryWorkspaceView.RECEIPTS: self._sort_document_rows(
                filtered_receipts,
                workspace_query.sort_by,
                workspace_query.sort_order,
            ),
            InventoryWorkspaceView.WRITEOFFS: self._sort_document_rows(
                filtered_writeoffs,
                workspace_query.sort_by,
                workspace_query.sort_order,
            ),
            InventoryWorkspaceView.MOVEMENTS: self._sort_movement_rows(
                filtered_movements,
                workspace_query.sort_by,
                workspace_query.sort_order,
            ),
            InventoryWorkspaceView.STOCKTAKING: self._sort_document_rows(
                filtered_stocktaking,
                workspace_query.sort_by,
                workspace_query.sort_order,
            ),
            InventoryWorkspaceView.SUPPLIER_RETURNS: self._sort_document_rows(
                filtered_supplier_returns,
                workspace_query.sort_by,
                workspace_query.sort_order,
            ),
        }
        active_rows = rows_map[workspace_query.view]
        pagination = self._paginate(active_rows, workspace_query.page, workspace_query.page_size)
        start = pagination.page_size * (pagination.page - 1)
        end = start + pagination.page_size
        paged_rows = active_rows[start:end]

        return InventoryWorkspaceResponse(
            period=summary_payload.period,
            active_view=workspace_query.view,
            summary=self._build_summary(scoped, current_stock_rows, inventory_report),
            tabs=tabs,
            filters=filters,
            pagination=pagination,
            rows=InventoryWorkspaceRows(
                current_stock=(
                    paged_rows if workspace_query.view is InventoryWorkspaceView.CURRENT_STOCK else []
                ),
                warehouses=(
                    paged_rows if workspace_query.view is InventoryWorkspaceView.WAREHOUSES else []
                ),
                purchases=(
                    paged_rows if workspace_query.view is InventoryWorkspaceView.PURCHASES else []
                ),
                receipts=(
                    paged_rows if workspace_query.view is InventoryWorkspaceView.RECEIPTS else []
                ),
                writeoffs=(
                    paged_rows if workspace_query.view is InventoryWorkspaceView.WRITEOFFS else []
                ),
                movements=(
                    paged_rows if workspace_query.view is InventoryWorkspaceView.MOVEMENTS else []
                ),
                stocktaking=(
                    paged_rows if workspace_query.view is InventoryWorkspaceView.STOCKTAKING else []
                ),
                supplier_returns=(
                    paged_rows
                    if workspace_query.view is InventoryWorkspaceView.SUPPLIER_RETURNS
                    else []
                ),
            ),
        )

    def get_current_stock_detail(
        self,
        inventory_balance_id: UUID,
        analytics_query: AnalyticsQuery,
    ) -> InventoryWorkspaceCurrentStockDetail | None:
        inventory_report = self._analytics.build_inventory(analytics_query)
        scoped = self._load_scoped_data(analytics_query)
        rows = self._build_current_stock_rows(scoped, inventory_report)
        row = next(
            (item for item in rows if item.inventory_balance_id == inventory_balance_id),
            None,
        )
        if row is None:
            return None

        related_rows = [
            item
            for item in rows
            if item.organization_id == row.organization_id
            and item.product_id == row.product_id
            and item.warehouse_id == row.warehouse_id
        ]
        related_rows = sorted(
            related_rows,
            key=lambda item: item.snapshot_date or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )

        recent_receipts = [
            item
            for item in self._build_receipt_rows(scoped)
            if item.organization_id == row.organization_id
            and (item.warehouse_id == row.warehouse_id if row.warehouse_id is not None else True)
        ][:5]
        recent_writeoffs = [
            item
            for item in self._build_writeoff_rows(scoped)
            if item.organization_id == row.organization_id
            and (item.warehouse_id == row.warehouse_id if row.warehouse_id is not None else True)
        ][:5]
        recent_movements = [
            item
            for item in self._build_movement_rows(scoped)
            if row.organization_name in {item.source_organization_name, item.destination_organization_name}
            and (
                row.warehouse_code in {item.source_warehouse_code, item.destination_warehouse_code}
                if row.warehouse_code is not None
                else True
            )
        ][:5]

        limitations: list[str] = []
        if row.data_quality_status is not CanonicalDataQualityStatus.VERIFIED:
            limitations.append("Остаток основан на частично подтверждённом источнике SmartUp.")
        if row.sales_velocity_30d is None:
            limitations.append("Скорость продаж недоступна для выбранного продукта в текущем контексте.")
        if row.days_of_stock is None:
            limitations.append("Дни запаса не рассчитаны из-за отсутствия надёжной velocity.")

        return InventoryWorkspaceCurrentStockDetail(
            row=row,
            recent_snapshots=related_rows[:10],
            recent_receipts=recent_receipts,
            recent_writeoffs=recent_writeoffs,
            recent_movements=recent_movements,
            limitations=limitations,
        )

    def get_warehouse_detail(
        self,
        warehouse_key: str,
        analytics_query: AnalyticsQuery,
    ) -> InventoryWorkspaceWarehouseDetail | None:
        inventory_report = self._analytics.build_inventory(analytics_query)
        scoped = self._load_scoped_data(analytics_query)
        current_stock_rows = self._build_current_stock_rows(scoped, inventory_report)
        warehouse_rows = self._build_warehouse_rows(scoped, current_stock_rows)
        row = next((item for item in warehouse_rows if item.warehouse_key == warehouse_key), None)
        if row is None:
            return None

        current_stock = [
            item for item in current_stock_rows if item.organization_id == row.organization_id and (
                item.warehouse_id == row.warehouse_id
                if row.warehouse_id is not None
                else item.warehouse_code == row.warehouse_code
            )
        ][:20]

        purchases = [
            item for item in self._build_purchase_rows(scoped) if item.organization_id == row.organization_id and (
                item.warehouse_id == row.warehouse_id
                if row.warehouse_id is not None
                else item.warehouse_code == row.warehouse_code
            )
        ][:10]
        receipts = [
            item for item in self._build_receipt_rows(scoped) if item.organization_id == row.organization_id and (
                item.warehouse_id == row.warehouse_id
                if row.warehouse_id is not None
                else item.warehouse_code == row.warehouse_code
            )
        ][:10]
        writeoffs = [
            item for item in self._build_writeoff_rows(scoped) if item.organization_id == row.organization_id and (
                item.warehouse_id == row.warehouse_id
                if row.warehouse_id is not None
                else item.warehouse_code == row.warehouse_code
            )
        ][:10]
        stocktaking = [
            item for item in self._build_stocktaking_rows(scoped) if item.organization_id == row.organization_id and (
                item.warehouse_id == row.warehouse_id
                if row.warehouse_id is not None
                else item.warehouse_code == row.warehouse_code
            )
        ][:10]
        supplier_returns = [
            item
            for item in self._build_supplier_return_rows(scoped)
            if item.organization_id == row.organization_id and (
                item.warehouse_id == row.warehouse_id
                if row.warehouse_id is not None
                else item.warehouse_code == row.warehouse_code
            )
        ][:10]
        movements = [
            item
            for item in self._build_movement_rows(scoped)
            if row.organization_name in {item.source_organization_name, item.destination_organization_name}
            and row.warehouse_code in {item.source_warehouse_code, item.destination_warehouse_code}
        ][:10]

        limitations: list[str] = []
        if row.data_quality_status is not CanonicalDataQualityStatus.VERIFIED:
            limitations.append("Идентичность склада подтверждена частично.")
        if not current_stock:
            limitations.append("Нет materialized current stock по выбранному складу.")

        return InventoryWorkspaceWarehouseDetail(
            row=row,
            current_stock=current_stock,
            purchases=purchases,
            receipts=receipts,
            writeoffs=writeoffs,
            movements=movements,
            stocktaking=stocktaking,
            supplier_returns=supplier_returns,
            limitations=limitations,
        )

    def _build_summary(
        self,
        scoped: _ScopedInventoryData,
        current_stock_rows: list[InventoryWorkspaceCurrentStockRow],
        inventory_report: AnalyticsInventoryReport,
    ) -> InventoryWorkspaceSummary:
        total_quantity = sum(
            (row.quantity or Decimal("0") for row in current_stock_rows),
            Decimal("0"),
        )
        inventory_values = [
            row.valuation_amount
            for row in current_stock_rows
            if row.valuation_amount is not None
            and row.data_quality_status is CanonicalDataQualityStatus.VERIFIED
        ]
        inventory_value = sum(inventory_values, Decimal("0")) if inventory_values else None
        inventory_value_status = (
            AnalyticsDataStatus.AVAILABLE if inventory_values else AnalyticsDataStatus.NO_VERIFIED_DATA
        )
        return InventoryWorkspaceSummary(
            current_stock_quantity=AnalyticsMetricValue(
                value=total_quantity,
                unit="units",
                status=AnalyticsDataStatus.AVAILABLE if current_stock_rows else AnalyticsDataStatus.NO_DATA,
                data_status=AnalyticsDataStatus.AVAILABLE if current_stock_rows else AnalyticsDataStatus.NO_DATA,
                record_count=len(current_stock_rows),
                note="Текущий складской остаток по latest verified snapshots.",
            ),
            products_in_stock=AnalyticsMetricValue(
                value=Decimal(sum(1 for row in current_stock_rows if (row.quantity or Decimal("0")) > 0)),
                unit="count",
                status=AnalyticsDataStatus.AVAILABLE if current_stock_rows else AnalyticsDataStatus.NO_DATA,
                data_status=AnalyticsDataStatus.AVAILABLE if current_stock_rows else AnalyticsDataStatus.NO_DATA,
                record_count=len(current_stock_rows),
                note="Количество товарных позиций с положительным остатком.",
            ),
            warehouses=AnalyticsMetricValue(
                value=Decimal(len({row.warehouse_key for row in self._build_warehouse_rows(scoped, current_stock_rows)})),
                unit="count",
                status=AnalyticsDataStatus.AVAILABLE,
                data_status=AnalyticsDataStatus.AVAILABLE,
                record_count=len(scoped.warehouses_by_id),
                note="Склады с materialized остатками или warehouse master.",
            ),
            zero_stock_products=AnalyticsMetricValue(
                value=Decimal(sum(1 for row in current_stock_rows if (row.quantity or Decimal("0")) == 0)),
                unit="count",
                status=AnalyticsDataStatus.AVAILABLE if current_stock_rows else AnalyticsDataStatus.NO_DATA,
                data_status=AnalyticsDataStatus.AVAILABLE if current_stock_rows else AnalyticsDataStatus.NO_DATA,
                record_count=len(current_stock_rows),
                note="Позиции с нулевым остатком.",
            ),
            negative_stock_products=AnalyticsMetricValue(
                value=Decimal(sum(1 for row in current_stock_rows if (row.quantity or Decimal("0")) < 0)),
                unit="count",
                status=AnalyticsDataStatus.AVAILABLE if current_stock_rows else AnalyticsDataStatus.NO_DATA,
                data_status=AnalyticsDataStatus.AVAILABLE if current_stock_rows else AnalyticsDataStatus.NO_DATA,
                record_count=len(current_stock_rows),
                note="Позиции с отрицательным остатком.",
            ),
            low_stock_signals=AnalyticsMetricValue(
                value=Decimal(len(inventory_report.low_stock)),
                unit="count",
                status=AnalyticsDataStatus.AVAILABLE if inventory_report.items else AnalyticsDataStatus.NO_DATA,
                data_status=AnalyticsDataStatus.AVAILABLE if inventory_report.items else AnalyticsDataStatus.NO_DATA,
                record_count=len(inventory_report.low_stock),
                note="Позиции с риском низкого остатка по analytics engine.",
            ),
            overstock_signals=AnalyticsMetricValue(
                value=Decimal(len(inventory_report.overstock)),
                unit="count",
                status=AnalyticsDataStatus.AVAILABLE if inventory_report.items else AnalyticsDataStatus.NO_DATA,
                data_status=AnalyticsDataStatus.AVAILABLE if inventory_report.items else AnalyticsDataStatus.NO_DATA,
                record_count=len(inventory_report.overstock),
                note="Позиции с избыточным остатком по analytics engine.",
            ),
            inventory_value=AnalyticsMetricValue(
                value=inventory_value,
                unit="money",
                status=inventory_value_status,
                data_status=inventory_value_status,
                currency="UZS" if inventory_value is not None else None,
                record_count=len(inventory_values),
                note=(
                    "Оценка склада только по verified valuation_amount из balance snapshots."
                    if inventory_value is not None
                    else "Нет достаточного verified valuation coverage для оценки склада."
                ),
            ),
        )

    def _build_tabs(
        self,
        current_stock_rows: list[InventoryWorkspaceCurrentStockRow],
        warehouse_rows: list[InventoryWorkspaceWarehouseRow],
        purchase_rows: list[InventoryWorkspacePurchaseRow],
        receipt_rows: list[InventoryWorkspaceReceiptRow],
        writeoff_rows: list[InventoryWorkspaceWriteoffRow],
        movement_rows: list[InventoryWorkspaceMovementRow],
        stocktaking_rows: list[InventoryWorkspaceStocktakingRow],
        supplier_return_rows: list[InventoryWorkspaceSupplierReturnRow],
    ) -> list[InventoryWorkspaceTabStatus]:
        return [
            self._tab(InventoryWorkspaceView.CURRENT_STOCK, "Текущий остаток", len(current_stock_rows)),
            self._tab(InventoryWorkspaceView.WAREHOUSES, "Склады", len(warehouse_rows)),
            self._tab(InventoryWorkspaceView.PURCHASES, "Закупки", len(purchase_rows)),
            self._tab(InventoryWorkspaceView.RECEIPTS, "Поступления", len(receipt_rows)),
            self._tab(InventoryWorkspaceView.WRITEOFFS, "Списания", len(writeoff_rows)),
            self._tab(InventoryWorkspaceView.MOVEMENTS, "Перемещения", len(movement_rows)),
            self._tab(InventoryWorkspaceView.STOCKTAKING, "Инвентаризация", len(stocktaking_rows)),
            self._tab(
                InventoryWorkspaceView.SUPPLIER_RETURNS,
                "Возвраты поставщику",
                len(supplier_return_rows),
                status=(
                    InventoryWorkspaceCapabilityStatus.NO_DATA
                    if not supplier_return_rows
                    else InventoryWorkspaceCapabilityStatus.AVAILABLE
                ),
                note=(
                    "Нет materialized supplier returns."
                    if not supplier_return_rows
                    else None
                ),
            ),
        ]

    def _tab(
        self,
        view: InventoryWorkspaceView,
        label: str,
        count: int,
        *,
        status: InventoryWorkspaceCapabilityStatus = InventoryWorkspaceCapabilityStatus.AVAILABLE,
        note: str | None = None,
    ) -> InventoryWorkspaceTabStatus:
        if count == 0 and status is InventoryWorkspaceCapabilityStatus.AVAILABLE:
            status = InventoryWorkspaceCapabilityStatus.NO_DATA
        return InventoryWorkspaceTabStatus(
            view=view,
            label=label,
            count=count,
            status=status,
            note=note,
        )

    def _load_scoped_data(self, query: AnalyticsQuery) -> _ScopedInventoryData:
        organization_ids = query.organization_ids
        all_organizations = list(self._store.list_canonical_organizations())
        if organization_ids:
            selected_ids = set(organization_ids)
            organizations = [
                item for item in all_organizations if item.organization_id in selected_ids
            ]
        else:
            organizations = all_organizations
        products = self._list_scoped(self._store.list_canonical_products, organization_ids)
        categories = self._list_scoped(self._store.list_canonical_product_categories, organization_ids)
        warehouses = self._list_scoped(self._store.list_canonical_warehouses, organization_ids)
        balances = self._list_scoped(self._store.list_canonical_inventory_balances, organization_ids)
        purchases = self._list_scoped(self._store.list_canonical_purchases, organization_ids)
        receipts = self._list_scoped(self._store.list_canonical_warehouse_receipts, organization_ids)
        writeoffs = self._list_scoped(self._store.list_canonical_writeoffs, organization_ids)
        supplier_returns = self._list_scoped(
            self._store.list_canonical_supplier_returns,
            organization_ids,
        )
        stocktakings = self._list_scoped(self._store.list_canonical_stocktakings, organization_ids)
        internal_movements = self._list_scoped(
            self._store.list_canonical_internal_movements,
            organization_ids,
        )
        cross_org_movements = self._list_scoped(
            self._store.list_canonical_cross_org_movements,
            organization_ids,
        )

        return _ScopedInventoryData(
            organizations_by_id={item.organization_id: item for item in organizations},
            products_by_id={item.id: item for item in products},
            categories_by_id={item.id: item for item in categories},
            warehouses_by_id={item.id: item for item in warehouses},
            balances=balances,
            latest_balances=_latest_inventory_rows(balances),
            purchases=purchases,
            receipts=receipts,
            writeoffs=writeoffs,
            supplier_returns=supplier_returns,
            stocktakings=stocktakings,
            internal_movements=internal_movements,
            cross_org_movements=cross_org_movements,
        )

    def _build_current_stock_rows(
        self,
        scoped: _ScopedInventoryData,
        inventory_report: AnalyticsInventoryReport,
    ) -> list[InventoryWorkspaceCurrentStockRow]:
        analytics_by_product: dict[UUID, AnalyticsProductItem] = {}
        for item in inventory_report.items:
            if item.product_id is not None:
                analytics_by_product[item.product_id] = item

        rows: list[InventoryWorkspaceCurrentStockRow] = []
        for balance in scoped.latest_balances:
            product = scoped.products_by_id.get(balance.product_id) if balance.product_id is not None else None
            category_id = None
            category_name = None
            if product is not None:
                category_id = self._product_category_id(product)
                category = scoped.categories_by_id.get(category_id) if category_id is not None else None
                if category is not None:
                    category_name = category.name

            analytics_item = analytics_by_product.get(balance.product_id) if balance.product_id is not None else None
            status = self._stock_status_from_balance(balance, analytics_item)
            rows.append(
                InventoryWorkspaceCurrentStockRow(
                    inventory_balance_id=balance.id,
                    organization_id=balance.organization_id,
                    organization_name=self._organization_name(
                        balance.organization_id,
                        scoped.organizations_by_id,
                    ),
                    warehouse_id=balance.warehouse_id,
                    warehouse_code=balance.warehouse_code,
                    warehouse_name=self._warehouse_name(balance.warehouse_id, scoped.warehouses_by_id),
                    product_id=balance.product_id,
                    product_code=balance.product_code,
                    product_name=balance.product_name or (product.name if product is not None else "Товар не определён"),
                    category_id=category_id,
                    category_name=category_name,
                    quantity=balance.quantity,
                    available_quantity=balance.available_quantity,
                    reserved_quantity=balance.reserved_quantity,
                    snapshot_date=balance.snapshot_date,
                    valuation_amount=balance.valuation_amount,
                    currency_code=self._resolve_currency(balance.currency_code, balance.source_currency_code),
                    sales_velocity_30d=self._metric_decimal(analytics_item.sales_velocity_30d) if analytics_item else None,
                    days_of_stock=self._metric_decimal(analytics_item.days_of_stock) if analytics_item else None,
                    stock_status=status,
                    stock_status_reason=self._stock_status_reason(status, analytics_item),
                    data_quality_status=balance.data_quality_status,
                    data_status=self._analytics_status_from_quality(balance.data_quality_status),
                    batch_number=balance.batch_number,
                    expiry_date=balance.expiry_date,
                    inventory_kind=balance.inventory_kind,
                )
            )
        return rows

    def _build_warehouse_rows(
        self,
        scoped: _ScopedInventoryData,
        current_stock_rows: list[InventoryWorkspaceCurrentStockRow],
    ) -> list[InventoryWorkspaceWarehouseRow]:
        grouped: dict[tuple[UUID, UUID | None, str | None], list[InventoryWorkspaceCurrentStockRow]] = defaultdict(list)
        for row in current_stock_rows:
            grouped[(row.organization_id, row.warehouse_id, row.warehouse_code)].append(row)

        rows: list[InventoryWorkspaceWarehouseRow] = []
        for _key, items in grouped.items():
            row = items[0]
            rows.append(
                InventoryWorkspaceWarehouseRow(
                    warehouse_key=self._warehouse_key(row.organization_id, row.warehouse_id, row.warehouse_code),
                    warehouse_id=row.warehouse_id,
                    warehouse_code=row.warehouse_code,
                    warehouse_name=row.warehouse_name,
                    organization_id=row.organization_id,
                    organization_name=row.organization_name,
                    products_count=len({item.product_id or item.product_code or item.product_name for item in items}),
                    current_quantity=sum((item.quantity or Decimal("0") for item in items), Decimal("0")),
                    last_snapshot=self._max_datetime([item.snapshot_date for item in items]),
                    low_stock_count=sum(1 for item in items if item.stock_status is InventoryWorkspaceStockStatus.LOW_STOCK),
                    out_of_stock_count=sum(1 for item in items if item.stock_status is InventoryWorkspaceStockStatus.OUT_OF_STOCK),
                    overstock_count=sum(1 for item in items if item.stock_status is InventoryWorkspaceStockStatus.OVERSTOCK),
                    negative_stock_count=sum(1 for item in items if item.stock_status is InventoryWorkspaceStockStatus.NEGATIVE_STOCK),
                    data_quality_status=self._worst_quality([item.data_quality_status for item in items]),
                )
            )

        known_keys = {item.warehouse_key for item in rows}
        for warehouse in scoped.warehouses_by_id.values():
            key = self._warehouse_key(
                warehouse.organization_id,
                warehouse.id,
                warehouse.warehouse_code,
            )
            if key in known_keys:
                continue
            rows.append(
                InventoryWorkspaceWarehouseRow(
                    warehouse_key=key,
                    warehouse_id=warehouse.id,
                    warehouse_code=warehouse.warehouse_code,
                    warehouse_name=warehouse.warehouse_name,
                    organization_id=warehouse.organization_id,
                    organization_name=self._organization_name(
                        warehouse.organization_id,
                        scoped.organizations_by_id,
                    ),
                    current_quantity=Decimal("0"),
                    last_snapshot=None,
                    data_quality_status=warehouse.data_quality_status,
                )
            )
        return rows

    def _build_purchase_rows(self, scoped: _ScopedInventoryData) -> list[InventoryWorkspacePurchaseRow]:
        return [
            InventoryWorkspacePurchaseRow(
                purchase_id=item.id,
                source_external_id=item.source_external_id,
                document_number=item.purchase_number or item.document_number,
                document_date=item.document_at,
                organization_id=item.organization_id,
                organization_name=self._organization_name(item.organization_id, scoped.organizations_by_id),
                warehouse_id=item.warehouse_id,
                warehouse_code=item.warehouse_code,
                warehouse_name=self._warehouse_name(item.warehouse_id, scoped.warehouses_by_id),
                supplier_code=item.supplier_code,
                supplier_external_id=item.supplier_external_id,
                amount=item.total_amount,
                currency_code=self._resolve_currency(item.currency_code, item.source_currency_code),
                status=item.source_status_name or item.source_status_code or item.posted,
                items_count=item.item_count,
                total_quantity=item.total_quantity,
                product_linkage_coverage=self._metadata_decimal(item.metadata, "product_linkage_coverage"),
                warehouse_linkage_coverage=self._metadata_decimal(item.metadata, "warehouse_linkage_coverage"),
                data_quality_status=item.data_quality_status,
                quality_note=self._metadata_text(item.metadata, "coverage_note"),
            )
            for item in scoped.purchases
        ]

    def _build_receipt_rows(self, scoped: _ScopedInventoryData) -> list[InventoryWorkspaceReceiptRow]:
        return [
            InventoryWorkspaceReceiptRow(
                receipt_id=item.id,
                source_external_id=item.source_external_id,
                document_number=item.receipt_number or item.document_number,
                document_date=item.document_at,
                organization_id=item.organization_id,
                organization_name=self._organization_name(item.organization_id, scoped.organizations_by_id),
                warehouse_id=item.warehouse_id,
                warehouse_code=item.warehouse_code,
                warehouse_name=self._warehouse_name(item.warehouse_id, scoped.warehouses_by_id),
                supplier_code=item.supplier_code,
                supplier_external_id=item.supplier_external_id,
                linked_purchase_external_id=self._metadata_text(item.metadata, "linked_purchase_external_id"),
                items_count=item.item_count,
                total_quantity=item.total_quantity,
                amount=item.total_amount,
                currency_code=self._resolve_currency(item.currency_code, item.source_currency_code),
                data_quality_status=item.data_quality_status,
                quality_note=self._metadata_text(item.metadata, "coverage_note"),
            )
            for item in scoped.receipts
        ]

    def _build_writeoff_rows(self, scoped: _ScopedInventoryData) -> list[InventoryWorkspaceWriteoffRow]:
        return [
            InventoryWorkspaceWriteoffRow(
                writeoff_id=item.id,
                source_external_id=item.source_external_id,
                document_number=item.writeoff_number or item.document_number,
                document_date=item.writeoff_date or item.document_at,
                organization_id=item.organization_id,
                organization_name=self._organization_name(item.organization_id, scoped.organizations_by_id),
                warehouse_id=item.warehouse_id,
                warehouse_code=item.warehouse_code,
                warehouse_name=self._warehouse_name(item.warehouse_id, scoped.warehouses_by_id),
                reason_code=item.reason_code,
                items_count=item.item_count,
                total_quantity=item.total_quantity,
                amount=item.total_amount or item.c_amount,
                currency_code=self._resolve_currency(item.currency_code, item.source_currency_code),
                status=item.source_status_name or item.source_status_code,
                data_quality_status=item.data_quality_status,
            )
            for item in scoped.writeoffs
        ]

    def _build_movement_rows(self, scoped: _ScopedInventoryData) -> list[InventoryWorkspaceMovementRow]:
        rows: list[InventoryWorkspaceMovementRow] = []
        for item in scoped.internal_movements:
            rows.append(
                InventoryWorkspaceMovementRow(
                    movement_id=item.id,
                    movement_type="internal",
                    source_external_id=item.source_external_id,
                    document_number=item.movement_number or item.document_number,
                    document_date=item.document_at,
                    organization_id=item.organization_id,
                    organization_name=self._organization_name(item.organization_id, scoped.organizations_by_id),
                    source_organization_name=self._organization_name(item.organization_id, scoped.organizations_by_id),
                    source_warehouse_code=item.source_warehouse_code,
                    source_warehouse_name=self._warehouse_name(item.source_warehouse_id, scoped.warehouses_by_id),
                    destination_organization_name=self._organization_name(item.organization_id, scoped.organizations_by_id),
                    destination_warehouse_code=item.destination_warehouse_code,
                    destination_warehouse_name=self._warehouse_name(item.destination_warehouse_id, scoped.warehouses_by_id),
                    total_quantity=item.total_quantity,
                    amount=item.total_amount,
                    currency_code=self._resolve_currency(item.currency_code, item.source_currency_code),
                    direction="warehouse_to_warehouse",
                    data_quality_status=item.data_quality_status,
                )
            )
        for item in scoped.cross_org_movements:
            rows.append(
                InventoryWorkspaceMovementRow(
                    movement_id=item.id,
                    movement_type="cross_org",
                    source_external_id=item.source_external_id,
                    document_number=item.delivery_number or item.document_number,
                    document_date=item.document_at,
                    organization_id=item.organization_id,
                    organization_name=self._organization_name(item.organization_id, scoped.organizations_by_id),
                    source_organization_name=self._organization_name(item.organization_id, scoped.organizations_by_id),
                    source_warehouse_code=item.source_warehouse_code,
                    source_warehouse_name=self._warehouse_name(item.source_warehouse_id, scoped.warehouses_by_id),
                    destination_organization_name=self._organization_name(
                        self._organization_by_filial_code(
                            item.destination_filial_code,
                            scoped.organizations_by_id,
                            item.organization_id,
                        ),
                        scoped.organizations_by_id,
                    ),
                    destination_warehouse_code=item.destination_warehouse_code,
                    destination_warehouse_name=self._warehouse_name(item.destination_warehouse_id, scoped.warehouses_by_id),
                    total_quantity=item.total_quantity,
                    amount=item.total_amount,
                    currency_code=self._resolve_currency(item.currency_code, item.source_currency_code),
                    direction="organization_to_organization",
                    data_quality_status=item.data_quality_status,
                )
            )
        return rows

    def _build_stocktaking_rows(self, scoped: _ScopedInventoryData) -> list[InventoryWorkspaceStocktakingRow]:
        return [
            InventoryWorkspaceStocktakingRow(
                stocktaking_id=item.id,
                source_external_id=item.source_external_id,
                document_number=item.stocktaking_number or item.document_number,
                document_date=item.document_at,
                organization_id=item.organization_id,
                organization_name=self._organization_name(item.organization_id, scoped.organizations_by_id),
                warehouse_id=item.warehouse_id,
                warehouse_code=item.warehouse_code,
                warehouse_name=self._warehouse_name(item.warehouse_id, scoped.warehouses_by_id),
                items_count=item.item_count,
                total_quantity=item.total_quantity,
                data_quality_status=item.data_quality_status,
            )
            for item in scoped.stocktakings
        ]

    def _build_supplier_return_rows(
        self,
        scoped: _ScopedInventoryData,
    ) -> list[InventoryWorkspaceSupplierReturnRow]:
        return [
            InventoryWorkspaceSupplierReturnRow(
                supplier_return_id=item.id,
                source_external_id=item.source_external_id,
                document_number=item.supplier_return_number or item.document_number,
                document_date=item.document_at,
                organization_id=item.organization_id,
                organization_name=self._organization_name(item.organization_id, scoped.organizations_by_id),
                warehouse_id=item.warehouse_id,
                warehouse_code=item.warehouse_code,
                warehouse_name=self._warehouse_name(item.warehouse_id, scoped.warehouses_by_id),
                supplier_code=item.supplier_code,
                supplier_external_id=item.supplier_external_id,
                reason_code=item.reason_code,
                items_count=item.item_count,
                total_quantity=item.total_quantity,
                amount=item.total_amount,
                currency_code=self._resolve_currency(item.currency_code, item.source_currency_code),
                data_quality_status=item.data_quality_status,
            )
            for item in scoped.supplier_returns
        ]

    def _build_filters_metadata(
        self,
        scoped: _ScopedInventoryData,
        current_stock_rows: list[InventoryWorkspaceCurrentStockRow],
    ) -> InventoryWorkspaceFiltersMetadata:
        warehouse_counter = Counter(
            row.warehouse_name or row.warehouse_code or "Склад не определён" for row in current_stock_rows
        )
        category_counter = Counter(
            row.category_name or "Без категории" for row in current_stock_rows
        )
        product_counter = Counter(row.product_name for row in current_stock_rows)
        status_counter = Counter(row.stock_status.value for row in current_stock_rows)
        quality_counter = Counter(row.data_quality_status.value for row in current_stock_rows)

        return InventoryWorkspaceFiltersMetadata(
            organizations=[
                InventoryWorkspaceFilterOption(
                    value=str(org.organization_id),
                    label=org.name,
                    count=sum(1 for row in current_stock_rows if row.organization_id == org.organization_id),
                )
                for org in sorted(scoped.organizations_by_id.values(), key=lambda item: item.sort_order)
            ],
            warehouses=self._optionize_counter(warehouse_counter),
            categories=self._optionize_counter(category_counter),
            products=self._optionize_counter(product_counter),
            stock_statuses=self._optionize_counter(status_counter),
            data_quality=self._optionize_counter(quality_counter),
        )

    def _filter_current_stock_rows(
        self,
        rows: list[InventoryWorkspaceCurrentStockRow],
        query: InventoryWorkspaceQuery,
    ) -> list[InventoryWorkspaceCurrentStockRow]:
        filtered = rows
        search = (query.search or "").strip().lower()
        if search:
            filtered = [
                row
                for row in filtered
                if search in row.product_name.lower()
                or search in (row.product_code or "").lower()
                or search in (row.warehouse_name or "").lower()
                or search in (row.warehouse_code or "").lower()
            ]
        if query.warehouse_id:
            selected = set(query.warehouse_id)
            filtered = [
                row
                for row in filtered
                if (str(row.warehouse_id) in selected)
                or ((row.warehouse_name or row.warehouse_code or "") in selected)
            ]
        if query.product_id:
            selected_products = {str(item) for item in query.product_id}
            filtered = [row for row in filtered if row.product_id is not None and str(row.product_id) in selected_products]
        if query.category_id:
            selected_categories = {str(item) for item in query.category_id}
            filtered = [row for row in filtered if row.category_id is not None and str(row.category_id) in selected_categories]
        if query.stock_status:
            selected_status = set(query.stock_status)
            filtered = [row for row in filtered if row.stock_status in selected_status]
        if query.has_stock is True:
            filtered = [row for row in filtered if (row.quantity or Decimal("0")) > 0]
        if query.zero_stock is True:
            filtered = [row for row in filtered if (row.quantity or Decimal("0")) == 0]
        if query.negative_stock is True:
            filtered = [row for row in filtered if (row.quantity or Decimal("0")) < 0]
        if query.data_quality:
            selected_quality = set(query.data_quality)
            filtered = [row for row in filtered if row.data_quality_status in selected_quality]
        return filtered

    def _filter_warehouse_rows(
        self,
        rows: list[InventoryWorkspaceWarehouseRow],
        query: InventoryWorkspaceQuery,
    ) -> list[InventoryWorkspaceWarehouseRow]:
        filtered = rows
        search = (query.search or "").strip().lower()
        if search:
            filtered = [
                row
                for row in filtered
                if search in (row.warehouse_name or "").lower()
                or search in (row.warehouse_code or "").lower()
                or search in row.organization_name.lower()
            ]
        if query.warehouse_id:
            selected = set(query.warehouse_id)
            filtered = [
                row
                for row in filtered
                if (str(row.warehouse_id) in selected)
                or ((row.warehouse_name or row.warehouse_code or "") in selected)
            ]
        if query.data_quality:
            selected_quality = set(query.data_quality)
            filtered = [row for row in filtered if row.data_quality_status in selected_quality]
        return filtered

    def _filter_document_rows[TDocument](
        self,
        rows: list[TDocument],
        query: InventoryWorkspaceQuery,
    ) -> list[TDocument]:
        filtered = rows
        search = (query.search or "").strip().lower()
        if search:
            filtered = [
                row
                for row in filtered
                if search in str(getattr(row, "document_number", "") or "").lower()
                or search in str(getattr(row, "organization_name", "") or "").lower()
                or search in str(getattr(row, "warehouse_name", "") or "").lower()
                or search in str(getattr(row, "warehouse_code", "") or "").lower()
            ]
        if query.warehouse_id:
            selected = set(query.warehouse_id)
            filtered = [
                row
                for row in filtered
                if (str(getattr(row, "warehouse_id", "") or "") in selected)
                or ((getattr(row, "warehouse_name", None) or getattr(row, "warehouse_code", None) or "") in selected)
            ]
        if query.data_quality:
            selected_quality = set(query.data_quality)
            filtered = [
                row
                for row in filtered
                if getattr(row, "data_quality_status", None) in selected_quality
            ]
        return filtered

    def _filter_movement_rows(
        self,
        rows: list[InventoryWorkspaceMovementRow],
        query: InventoryWorkspaceQuery,
    ) -> list[InventoryWorkspaceMovementRow]:
        filtered = rows
        search = (query.search or "").strip().lower()
        if search:
            filtered = [
                row
                for row in filtered
                if search in (row.source_organization_name or "").lower()
                or search in (row.destination_organization_name or "").lower()
                or search in (row.source_warehouse_name or "").lower()
                or search in (row.destination_warehouse_name or "").lower()
                or search in (row.document_number or "").lower()
            ]
        if query.data_quality:
            selected_quality = set(query.data_quality)
            filtered = [row for row in filtered if row.data_quality_status in selected_quality]
        return filtered

    def _sort_current_stock_rows(
        self,
        rows: list[InventoryWorkspaceCurrentStockRow],
        sort_by: InventoryWorkspaceSortBy,
        sort_order: InventoryWorkspaceSortOrder,
    ) -> list[InventoryWorkspaceCurrentStockRow]:
        reverse = sort_order is InventoryWorkspaceSortOrder.DESC
        key_map = {
            InventoryWorkspaceSortBy.PRODUCT_NAME: lambda row: row.product_name.lower(),
            InventoryWorkspaceSortBy.WAREHOUSE: lambda row: (row.warehouse_name or row.warehouse_code or "").lower(),
            InventoryWorkspaceSortBy.ORGANIZATION: lambda row: row.organization_name.lower(),
            InventoryWorkspaceSortBy.QUANTITY: lambda row: row.quantity or Decimal("0"),
            InventoryWorkspaceSortBy.SNAPSHOT_DATE: lambda row: row.snapshot_date or datetime.min.replace(tzinfo=UTC),
            InventoryWorkspaceSortBy.STOCK_STATUS: lambda row: row.stock_status.value,
            InventoryWorkspaceSortBy.AMOUNT: lambda row: row.valuation_amount or Decimal("0"),
            InventoryWorkspaceSortBy.DOCUMENT_DATE: lambda row: row.snapshot_date or datetime.min.replace(tzinfo=UTC),
        }
        return sorted(rows, key=key_map[sort_by], reverse=reverse)

    def _sort_warehouse_rows(
        self,
        rows: list[InventoryWorkspaceWarehouseRow],
        sort_by: InventoryWorkspaceSortBy,
        sort_order: InventoryWorkspaceSortOrder,
    ) -> list[InventoryWorkspaceWarehouseRow]:
        reverse = sort_order is InventoryWorkspaceSortOrder.DESC
        key_map = {
            InventoryWorkspaceSortBy.WAREHOUSE: lambda row: (row.warehouse_name or row.warehouse_code or "").lower(),
            InventoryWorkspaceSortBy.ORGANIZATION: lambda row: row.organization_name.lower(),
            InventoryWorkspaceSortBy.QUANTITY: lambda row: row.current_quantity or Decimal("0"),
            InventoryWorkspaceSortBy.SNAPSHOT_DATE: lambda row: row.last_snapshot or datetime.min.replace(tzinfo=UTC),
            InventoryWorkspaceSortBy.STOCK_STATUS: lambda row: row.negative_stock_count + row.out_of_stock_count + row.low_stock_count,
            InventoryWorkspaceSortBy.PRODUCT_NAME: lambda row: (row.warehouse_name or row.warehouse_code or "").lower(),
            InventoryWorkspaceSortBy.AMOUNT: lambda row: row.current_quantity or Decimal("0"),
            InventoryWorkspaceSortBy.DOCUMENT_DATE: lambda row: row.last_snapshot or datetime.min.replace(tzinfo=UTC),
        }
        return sorted(rows, key=key_map[sort_by], reverse=reverse)

    def _sort_document_rows[TDocument](
        self,
        rows: list[TDocument],
        sort_by: InventoryWorkspaceSortBy,
        sort_order: InventoryWorkspaceSortOrder,
    ) -> list[TDocument]:
        reverse = sort_order is InventoryWorkspaceSortOrder.DESC
        key_map = {
            InventoryWorkspaceSortBy.DOCUMENT_DATE: lambda row: getattr(row, "document_date", None) or datetime.min.replace(tzinfo=UTC),
            InventoryWorkspaceSortBy.AMOUNT: lambda row: getattr(row, "amount", None) or Decimal("0"),
            InventoryWorkspaceSortBy.WAREHOUSE: lambda row: (getattr(row, "warehouse_name", None) or getattr(row, "warehouse_code", None) or "").lower(),
            InventoryWorkspaceSortBy.ORGANIZATION: lambda row: getattr(row, "organization_name", "").lower(),
            InventoryWorkspaceSortBy.QUANTITY: lambda row: getattr(row, "total_quantity", None) or Decimal("0"),
            InventoryWorkspaceSortBy.PRODUCT_NAME: lambda row: (getattr(row, "document_number", None) or "").lower(),
            InventoryWorkspaceSortBy.SNAPSHOT_DATE: lambda row: getattr(row, "document_date", None) or datetime.min.replace(tzinfo=UTC),
            InventoryWorkspaceSortBy.STOCK_STATUS: lambda row: getattr(row, "items_count", 0),
        }
        return sorted(rows, key=key_map[sort_by], reverse=reverse)

    def _sort_movement_rows(
        self,
        rows: list[InventoryWorkspaceMovementRow],
        sort_by: InventoryWorkspaceSortBy,
        sort_order: InventoryWorkspaceSortOrder,
    ) -> list[InventoryWorkspaceMovementRow]:
        reverse = sort_order is InventoryWorkspaceSortOrder.DESC
        key_map = {
            InventoryWorkspaceSortBy.DOCUMENT_DATE: lambda row: row.document_date or datetime.min.replace(tzinfo=UTC),
            InventoryWorkspaceSortBy.AMOUNT: lambda row: row.amount or Decimal("0"),
            InventoryWorkspaceSortBy.WAREHOUSE: lambda row: (row.source_warehouse_name or row.source_warehouse_code or "").lower(),
            InventoryWorkspaceSortBy.ORGANIZATION: lambda row: row.organization_name.lower(),
            InventoryWorkspaceSortBy.QUANTITY: lambda row: row.total_quantity or Decimal("0"),
            InventoryWorkspaceSortBy.PRODUCT_NAME: lambda row: (row.document_number or "").lower(),
            InventoryWorkspaceSortBy.SNAPSHOT_DATE: lambda row: row.document_date or datetime.min.replace(tzinfo=UTC),
            InventoryWorkspaceSortBy.STOCK_STATUS: lambda row: row.movement_type,
        }
        return sorted(rows, key=key_map[sort_by], reverse=reverse)

    def _paginate(
        self,
        rows: list[object],
        page: int,
        page_size: int,
    ) -> InventoryWorkspacePagination:
        total_items = len(rows)
        total_pages = max(1, ceil(total_items / page_size)) if total_items else 1
        current_page = min(page, total_pages)
        return InventoryWorkspacePagination(
            page=current_page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        )

    def _organization_name(
        self,
        organization_id: UUID,
        organizations_by_id: dict[UUID, CanonicalOrganization],
    ) -> str:
        organization = organizations_by_id.get(organization_id)
        return organization.name if organization is not None else "Организация не определена"

    def _warehouse_name(
        self,
        warehouse_id: UUID | None,
        warehouses_by_id: dict[UUID, CanonicalWarehouse],
    ) -> str | None:
        if warehouse_id is None:
            return None
        warehouse = warehouses_by_id.get(warehouse_id)
        if warehouse is None:
            return None
        return warehouse.warehouse_name or warehouse.warehouse_code or warehouse.source_external_id

    def _stock_status_from_balance(
        self,
        balance: CanonicalInventoryBalance,
        analytics_item: AnalyticsProductItem | None,
    ) -> InventoryWorkspaceStockStatus:
        quantity = balance.quantity or Decimal("0")
        if quantity < 0:
            return InventoryWorkspaceStockStatus.NEGATIVE_STOCK
        if quantity == 0:
            return InventoryWorkspaceStockStatus.OUT_OF_STOCK
        if analytics_item is not None:
            tags = set(analytics_item.classification_tags)
            if analytics_item.stockout_risk in {"critical", "high"}:
                return InventoryWorkspaceStockStatus.STOCKOUT_RISK
            if "OVERSTOCK" in tags:
                return InventoryWorkspaceStockStatus.OVERSTOCK
            if analytics_item.stockout_risk in {"medium", "low"}:
                return InventoryWorkspaceStockStatus.LOW_STOCK
        return InventoryWorkspaceStockStatus.IN_STOCK

    def _stock_status_reason(
        self,
        status: InventoryWorkspaceStockStatus,
        analytics_item: AnalyticsProductItem | None,
    ) -> str | None:
        if analytics_item is not None and analytics_item.stockout_risk:
            return f"stockout_risk={analytics_item.stockout_risk}"
        return status.value

    def _product_category_id(self, product: CanonicalProduct) -> UUID | None:
        metadata_id = product.metadata.get("primary_group_id")
        if isinstance(metadata_id, UUID):
            return metadata_id
        if isinstance(metadata_id, str):
            try:
                return UUID(metadata_id)
            except ValueError:
                return None
        return None

    def _resolve_currency(self, currency_code: str | None, source_currency_code: str | None) -> str | None:
        if currency_code:
            return currency_code
        if source_currency_code == "860":
            return "UZS"
        return source_currency_code

    def _metric_decimal(self, value: AnalyticsMetricValue | None) -> Decimal | None:
        if value is None or value.value is None:
            return None
        return Decimal(str(value.value))

    def _analytics_status_from_quality(
        self,
        quality: CanonicalDataQualityStatus,
    ) -> AnalyticsDataStatus:
        if quality is CanonicalDataQualityStatus.VERIFIED:
            return AnalyticsDataStatus.AVAILABLE
        if quality is CanonicalDataQualityStatus.PARTIAL:
            return AnalyticsDataStatus.PARTIAL
        if quality is CanonicalDataQualityStatus.UNRESOLVED:
            return AnalyticsDataStatus.UNRESOLVED
        return AnalyticsDataStatus.NO_VERIFIED_DATA

    def _metadata_decimal(self, metadata: dict[str, object], key: str) -> Decimal | None:
        value = metadata.get(key)
        if value is None or value == "":
            return None
        return Decimal(str(value))

    def _metadata_text(self, metadata: dict[str, object], key: str) -> str | None:
        value = metadata.get(key)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _list_scoped(
        self,
        reader: Callable[..., list[T] | tuple[T, ...] | object],
        organization_ids: list[UUID],
    ) -> list[T]:
        if not organization_ids:
            return list(reader())  # type: ignore[arg-type]
        aggregated: list[T] = []
        for organization_id in organization_ids:
            aggregated.extend(list(reader(organization_id=organization_id)))  # type: ignore[arg-type]
        return aggregated

    def _optionize_counter(self, counter: Counter[str]) -> list[InventoryWorkspaceFilterOption]:
        return [
            InventoryWorkspaceFilterOption(value=value, label=value, count=count)
            for value, count in sorted(counter.items(), key=lambda item: item[0].lower())
        ]

    def _warehouse_key(
        self,
        organization_id: UUID,
        warehouse_id: UUID | None,
        warehouse_code: str | None,
    ) -> str:
        return f"{organization_id}:{warehouse_id or warehouse_code or 'warehouse-unknown'}"

    def _organization_by_filial_code(
        self,
        filial_code: str | None,
        organizations_by_id: dict[UUID, CanonicalOrganization],
        fallback: UUID,
    ) -> UUID:
        if filial_code:
            for organization in organizations_by_id.values():
                if organization.filial_code == filial_code:
                    return organization.organization_id
        return fallback

    def _worst_quality(
        self,
        qualities: list[CanonicalDataQualityStatus],
    ) -> CanonicalDataQualityStatus:
        if not qualities:
            return CanonicalDataQualityStatus.UNSAFE
        priority = {
            CanonicalDataQualityStatus.VERIFIED: 0,
            CanonicalDataQualityStatus.PARTIAL: 1,
            CanonicalDataQualityStatus.UNRESOLVED: 2,
            CanonicalDataQualityStatus.UNSAFE: 3,
        }
        return max(qualities, key=lambda item: priority[item])

    def _max_datetime(self, values: list[datetime | None]) -> datetime | None:
        resolved = [item for item in values if item is not None]
        return max(resolved) if resolved else None


def _latest_inventory_rows(
    rows: list[CanonicalInventoryBalance],
) -> list[CanonicalInventoryBalance]:
    latest_by_grain: dict[str, CanonicalInventoryBalance] = {}
    for row in rows:
        key = row.grain_key or "::".join(
            [
                str(row.organization_id),
                str(row.product_id or row.product_external_id or row.product_code),
                str(row.warehouse_id or row.warehouse_external_id or row.warehouse_code),
                str(row.batch_number or ""),
                str(row.card_code or ""),
                str(row.serial_number or ""),
            ]
        )
        current = latest_by_grain.get(key)
        current_date = current.snapshot_date if current is not None else None
        row_date = row.snapshot_date
        if current is None or (row_date or datetime.min.replace(tzinfo=UTC)) >= (
            current_date or datetime.min.replace(tzinfo=UTC)
        ):
            latest_by_grain[key] = row
    return list(latest_by_grain.values())
