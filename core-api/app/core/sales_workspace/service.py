"""Canonical Sales / Orders business workspace service."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from math import ceil
from typing import Any, TypeVar
from uuid import UUID

from app.core.analytics.engine import BusinessAnalyticsEngine
from app.core.analytics.models import AnalyticsDataStatus, AnalyticsQuery
from app.core.data_layer.canonical_v2 import (
    CanonicalCustomer,
    CanonicalCustomerReturn,
    CanonicalCustomerReturnItem,
    CanonicalDataQualityStatus,
    CanonicalOrder,
    CanonicalOrganization,
    CanonicalPayment,
    CanonicalPaymentAllocation,
    CanonicalProduct,
    CanonicalSale,
    CanonicalSaleItem,
    CanonicalSalesRep,
    CanonicalWorkingZone,
)
from app.core.data_layer.contracts import CoreDataStore
from app.core.sales_workspace.models import (
    SalesWorkspaceDetail,
    SalesWorkspaceFilterMetadata,
    SalesWorkspaceFilterOption,
    SalesWorkspaceLineItem,
    SalesWorkspacePagination,
    SalesWorkspacePaymentItem,
    SalesWorkspaceProvenance,
    SalesWorkspaceQuery,
    SalesWorkspaceResponse,
    SalesWorkspaceReturnItem,
    SalesWorkspaceRowKind,
    SalesWorkspaceSortBy,
    SalesWorkspaceSortOrder,
    SalesWorkspaceSummary,
    SalesWorkspaceTableRow,
)

T = TypeVar("T")


@dataclass(slots=True)
class _WorkspaceRowBundle:
    row: SalesWorkspaceTableRow
    order: CanonicalOrder | None
    sale: CanonicalSale | None
    item_keys: set[UUID]


class SalesWorkspaceService:
    """Build Sales / Orders business workspace payloads from Canonical V2."""

    def __init__(self, store: CoreDataStore) -> None:
        self._store = store
        self._analytics = BusinessAnalyticsEngine(store)

    def list_workspace(
        self,
        analytics_query: AnalyticsQuery,
        workspace_query: SalesWorkspaceQuery,
    ) -> SalesWorkspaceResponse:
        summary_payload = self._analytics.build_summary(analytics_query)
        scoped = self._load_scoped_data(analytics_query)
        period = summary_payload.period
        row_bundles = self._build_row_bundles(scoped)
        row_bundles = self._filter_by_period(row_bundles, period.current_start, period.current_end)

        filter_metadata = self._build_filter_metadata(row_bundles)
        row_bundles = self._apply_workspace_filters(row_bundles, workspace_query, scoped)
        row_bundles = self._sort_rows(
            row_bundles, workspace_query.sort_by, workspace_query.sort_order
        )
        pagination = self._paginate(row_bundles, workspace_query.page, workspace_query.page_size)
        page_rows = row_bundles[
            pagination.page_size * (pagination.page - 1) : pagination.page_size * pagination.page
        ]

        return SalesWorkspaceResponse(
            period=period,
            summary=SalesWorkspaceSummary(
                revenue=summary_payload.business.revenue,
                orders=summary_payload.business.orders,
                realised_sales=summary_payload.business.realised_sales,
                sold_units=summary_payload.business.sold_units,
                average_order=summary_payload.business.average_order,
                unique_customers=summary_payload.business.unique_customers,
                payments_received=summary_payload.business.payments_received,
                return_value=summary_payload.business.customer_return_value,
            ),
            filters=filter_metadata,
            rows=[bundle.row for bundle in page_rows],
            pagination=pagination,
        )

    def get_detail(
        self,
        record_id: UUID,
        analytics_query: AnalyticsQuery,
    ) -> SalesWorkspaceDetail | None:
        scoped = self._load_scoped_data(analytics_query)
        row_bundles = self._build_row_bundles(scoped)
        bundle = next((item for item in row_bundles if item.row.record_id == record_id), None)
        if bundle is None:
            return None

        order = bundle.order
        sale = bundle.sale

        line_items = [
            SalesWorkspaceLineItem(
                line_number=item.line_number,
                product_id=item.product_id,
                product_external_id=item.product_external_id,
                product_code=item.product_code,
                product_name=item.product_name,
                warehouse_id=item.warehouse_id,
                warehouse_code=item.warehouse_code,
                warehouse_name=scoped.warehouse_names.get(item.warehouse_id),
                price_type_code=item.price_type_code,
                ordered_quantity=self._null_if_zero(item.ordered_quantity),
                sold_quantity=self._null_if_zero(item.sold_quantity),
                returned_quantity=self._null_if_zero(item.returned_quantity),
                unit_price=item.unit_price,
                amount=item.amount,
                vat_percent=item.vat_percent,
                vat_amount=item.vat_amount,
                margin_amount=item.margin_amount,
                currency_code=item.currency_code,
                data_quality_status=item.data_quality_status,
            )
            for item in self._resolve_detail_items(bundle, scoped)
        ]

        linked_returns = self._resolve_detail_returns(bundle, scoped)
        linked_payments = self._resolve_detail_payments(bundle, scoped)

        provenance_source = order or sale
        if provenance_source is None:
            return None

        limitations: list[str] = []
        if not line_items:
            limitations.append(
                "Не удалось восстановить строки заказа из подтверждённых canonical line items."
            )
        if not linked_payments:
            limitations.append("Детерминированная аллокация платежей к заказу не подтверждена.")
        if provenance_source.data_quality_status is not CanonicalDataQualityStatus.VERIFIED:
            limitations.append(
                "Запись доступна с неполным качеством данных. Используйте с учётом provenance."
            )

        return SalesWorkspaceDetail(
            record_id=bundle.row.record_id,
            row=bundle.row,
            items=line_items,
            returns=linked_returns,
            payments=linked_payments,
            provenance=SalesWorkspaceProvenance(
                source_endpoint=provenance_source.source_endpoint,
                source_external_id=provenance_source.source_external_id,
                source_raw_record_id=provenance_source.source_raw_record_id,
                request_filial_id=provenance_source.request_filial_id,
                response_filial_id=provenance_source.response_filial_id,
                request_company_id=provenance_source.request_company_id,
                request_project_code=provenance_source.request_project_code,
                data_quality_status=provenance_source.data_quality_status,
            ),
            limitations=limitations,
        )

    def _load_scoped_data(self, analytics_query: AnalyticsQuery) -> _ScopedData:
        organization_ids = analytics_query.organization_ids
        if analytics_query.organization_id is not None:
            organization_ids = [analytics_query.organization_id]

        organizations = list(self._store.list_canonical_organizations())
        if organization_ids:
            allowed = set(organization_ids)
            organizations = [
                organization
                for organization in organizations
                if organization.organization_id in allowed
            ]
        customers = self._list_scoped(self._store.list_canonical_customers, organization_ids)
        products = self._list_scoped(self._store.list_canonical_products, organization_ids)
        sales_reps = self._list_scoped(self._store.list_canonical_sales_reps, organization_ids)
        working_zones = self._list_scoped(
            self._store.list_canonical_working_zones, organization_ids
        )
        orders = self._list_scoped(self._store.list_canonical_orders, organization_ids)
        sales = self._list_scoped(self._store.list_canonical_sales, organization_ids)
        sale_items = self._list_scoped(self._store.list_canonical_sale_items, organization_ids)
        payments = self._list_scoped(self._store.list_canonical_payments, organization_ids)
        payment_allocations = self._list_scoped(
            self._store.list_canonical_payment_allocations, organization_ids
        )
        customer_returns = self._list_scoped(
            self._store.list_canonical_customer_returns, organization_ids
        )
        customer_return_items = self._list_scoped(
            self._store.list_canonical_customer_return_items, organization_ids
        )

        organizations_by_id = {org.organization_id: org for org in organizations}
        customers_by_id = {customer.id: customer for customer in customers}
        products_by_id = {product.id: product for product in products}
        sales_reps_by_id = {rep.id: rep for rep in sales_reps}
        working_zones_by_id = {zone.id: zone for zone in working_zones}

        warehouse_names: dict[UUID, str] = {}
        if hasattr(self._store, "list_canonical_warehouses"):
            try:
                warehouses = self._list_scoped(
                    self._store.list_canonical_warehouses, organization_ids
                )  # type: ignore[attr-defined]
                warehouse_names = {
                    warehouse.id: warehouse.name  # type: ignore[attr-defined]
                    for warehouse in warehouses
                    if getattr(warehouse, "name", None)
                }
            except Exception:
                warehouse_names = {}

        return _ScopedData(
            organizations=organizations,
            organizations_by_id=organizations_by_id,
            customers=customers,
            customers_by_id=customers_by_id,
            products=products,
            products_by_id=products_by_id,
            sales_reps=sales_reps,
            sales_reps_by_id=sales_reps_by_id,
            working_zones=working_zones,
            working_zones_by_id=working_zones_by_id,
            orders=orders,
            sales=sales,
            sale_items=sale_items,
            payments=payments,
            payment_allocations=payment_allocations,
            customer_returns=customer_returns,
            customer_return_items=customer_return_items,
            warehouse_names=warehouse_names,
        )

    def _build_row_bundles(self, scoped: _ScopedData) -> list[_WorkspaceRowBundle]:
        sales_by_order_id: dict[UUID, list[CanonicalSale]] = defaultdict(list)
        for sale in scoped.sales:
            if sale.order_id is not None:
                sales_by_order_id[sale.order_id].append(sale)

        sale_items_by_sale_id: dict[UUID, list[CanonicalSaleItem]] = defaultdict(list)
        sale_items_by_order_id: dict[UUID, list[CanonicalSaleItem]] = defaultdict(list)
        for item in scoped.sale_items:
            if item.sale_id is not None:
                sale_items_by_sale_id[item.sale_id].append(item)
            if item.order_id is not None:
                sale_items_by_order_id[item.order_id].append(item)

        returns_by_order_id: dict[UUID, list[CanonicalCustomerReturn]] = defaultdict(list)
        returns_by_sale_id: dict[UUID, list[CanonicalCustomerReturn]] = defaultdict(list)
        for customer_return in scoped.customer_returns:
            if customer_return.linked_order_id is not None:
                returns_by_order_id[customer_return.linked_order_id].append(customer_return)
            if customer_return.linked_sale_id is not None:
                returns_by_sale_id[customer_return.linked_sale_id].append(customer_return)

        allocations_by_order_id: dict[UUID, list[CanonicalPaymentAllocation]] = defaultdict(list)
        allocations_by_sale_id: dict[UUID, list[CanonicalPaymentAllocation]] = defaultdict(list)
        payments_by_id = {payment.id: payment for payment in scoped.payments}
        for allocation in scoped.payment_allocations:
            if allocation.order_id is not None:
                allocations_by_order_id[allocation.order_id].append(allocation)
            if allocation.sale_id is not None:
                allocations_by_sale_id[allocation.sale_id].append(allocation)

        bundles: list[_WorkspaceRowBundle] = []
        covered_sale_ids: set[UUID] = set()

        for order in scoped.orders:
            sale = self._pick_primary_sale(sales_by_order_id.get(order.id, []))
            if sale is not None:
                covered_sale_ids.add(sale.id)

            row_returns = self._merge_unique_rows(
                returns_by_order_id.get(order.id, []),
                returns_by_sale_id.get(sale.id, []) if sale is not None else [],
            )
            linked_payment_amount = self._sum_linked_payment_amount(
                allocations_by_order_id.get(order.id, []),
                allocations_by_sale_id.get(sale.id, []) if sale is not None else [],
                payments_by_id,
            )

            item_keys = {item.id for item in sale_items_by_order_id.get(order.id, [])}
            if sale is not None:
                item_keys.update(item.id for item in sale_items_by_sale_id.get(sale.id, []))

            bundles.append(
                _WorkspaceRowBundle(
                    row=SalesWorkspaceTableRow(
                        record_id=order.id,
                        row_kind=SalesWorkspaceRowKind.ORDER,
                        order_id=order.id,
                        sale_id=sale.id if sale is not None else None,
                        order_external_id=order.source_external_id,
                        sale_external_id=sale.source_external_id if sale is not None else None,
                        deal_id=order.deal_id,
                        order_number=order.order_number or order.deal_id,
                        sale_number=sale.sale_number if sale is not None else None,
                        business_date=order.order_at or order.delivery_date,
                        delivery_date=order.delivery_date,
                        last_modified_at=order.updated_at,
                        organization_id=order.organization_id,
                        organization_name=self._organization_name(
                            order.organization_id, scoped.organizations_by_id
                        ),
                        customer_id=order.customer_id,
                        customer_external_id=order.customer_external_id,
                        customer_code=order.customer_code,
                        customer_name=self._customer_name(
                            order.customer_id, order.customer_name, scoped.customers_by_id
                        ),
                        sales_rep_id=order.sales_rep_id,
                        sales_rep_name=self._sales_rep_name(
                            order.sales_rep_id, scoped.sales_reps_by_id, order.sales_rep_external_id
                        ),
                        working_zone_id=order.working_zone_id,
                        working_zone_name=self._working_zone_name(
                            order.working_zone_id,
                            scoped.working_zones_by_id,
                            order.working_zone_external_id,
                        ),
                        source_status_code=order.source_status_code,
                        source_status_name=order.source_status_name,
                        normalized_status=order.normalized_status,
                        display_status=order.display_status,
                        order_amount=order.total_amount,
                        realised_amount=sale.total_amount if sale is not None else None,
                        return_value=self._sum_amount(row_returns, "total_amount"),
                        linked_payment_amount=linked_payment_amount,
                        ordered_units=self._null_if_zero(order.ordered_quantity),
                        sold_units=self._null_if_zero(
                            sale.sold_quantity if sale is not None else order.sold_quantity
                        ),
                        returned_units=self._null_if_zero(
                            self._sum_amount(row_returns, "returned_quantity")
                        ),
                        item_count=max(
                            order.item_count,
                            sale.item_count if sale is not None else 0,
                            len(item_keys),
                        ),
                        currency_code=(
                            sale.currency_code if sale is not None else None
                        )
                        or order.currency_code,
                        realised=sale is not None,
                        data_quality_status=self._row_quality(
                            order.data_quality_status,
                            sale.data_quality_status if sale is not None else None,
                        ),
                        data_status=self._analytics_status_from_quality(
                            self._row_quality(
                                order.data_quality_status,
                                sale.data_quality_status if sale is not None else None,
                            )
                        ),
                    ),
                    order=order,
                    sale=sale,
                    item_keys=item_keys,
                )
            )

        for sale in scoped.sales:
            if sale.id in covered_sale_ids:
                continue
            row_returns = returns_by_sale_id.get(sale.id, [])
            item_keys = {item.id for item in sale_items_by_sale_id.get(sale.id, [])}
            bundles.append(
                _WorkspaceRowBundle(
                    row=SalesWorkspaceTableRow(
                        record_id=sale.id,
                        row_kind=SalesWorkspaceRowKind.SALE,
                        order_id=sale.order_id,
                        sale_id=sale.id,
                        order_external_id=sale.order_external_id,
                        sale_external_id=sale.source_external_id,
                        deal_id=sale.deal_id,
                        order_number=sale.deal_id,
                        sale_number=sale.sale_number or sale.deal_id,
                        business_date=sale.sale_at or sale.closed_at,
                        delivery_date=None,
                        last_modified_at=sale.updated_at,
                        organization_id=sale.organization_id,
                        organization_name=self._organization_name(
                            sale.organization_id, scoped.organizations_by_id
                        ),
                        customer_id=sale.customer_id,
                        customer_external_id=sale.customer_external_id,
                        customer_code=sale.customer_code,
                        customer_name=self._customer_name(
                            sale.customer_id, sale.customer_name, scoped.customers_by_id
                        ),
                        sales_rep_id=sale.sales_rep_id,
                        sales_rep_name=self._sales_rep_name(
                            sale.sales_rep_id, scoped.sales_reps_by_id, sale.sales_rep_external_id
                        ),
                        working_zone_id=sale.working_zone_id,
                        working_zone_name=self._working_zone_name(
                            sale.working_zone_id,
                            scoped.working_zones_by_id,
                            sale.working_zone_external_id,
                        ),
                        source_status_code=sale.source_status_code,
                        source_status_name=sale.source_status_name,
                        normalized_status=sale.normalized_status,
                        display_status=sale.display_status,
                        order_amount=None,
                        realised_amount=sale.total_amount,
                        return_value=self._sum_amount(row_returns, "total_amount"),
                        linked_payment_amount=self._sum_linked_payment_amount(
                            [],
                            allocations_by_sale_id.get(sale.id, []),
                            payments_by_id,
                        ),
                        ordered_units=self._null_if_zero(sale.ordered_quantity),
                        sold_units=self._null_if_zero(sale.sold_quantity),
                        returned_units=self._null_if_zero(
                            self._sum_amount(row_returns, "returned_quantity")
                        ),
                        item_count=max(sale.item_count, len(item_keys)),
                        currency_code=sale.currency_code,
                        realised=True,
                        data_quality_status=sale.data_quality_status,
                        data_status=self._analytics_status_from_quality(sale.data_quality_status),
                    ),
                    order=scoped.orders_by_id.get(sale.order_id)
                    if sale.order_id is not None
                    else None,
                    sale=sale,
                    item_keys=item_keys,
                )
            )

        return bundles

    def _build_filter_metadata(
        self, bundles: list[_WorkspaceRowBundle]
    ) -> SalesWorkspaceFilterMetadata:
        org_counter = Counter(bundle.row.organization_name for bundle in bundles)
        status_counter = Counter(bundle.row.normalized_status for bundle in bundles)
        customer_counter = Counter(
            self._customer_counter_key(bundle.row)
            for bundle in bundles
            if bundle.row.customer_name
        )
        sales_rep_counter = Counter(
            bundle.row.sales_rep_name for bundle in bundles if bundle.row.sales_rep_name
        )
        zone_counter = Counter(
            bundle.row.working_zone_name for bundle in bundles if bundle.row.working_zone_name
        )
        quality_counter = Counter(bundle.row.data_quality_status.value for bundle in bundles)

        def _options(counter: Counter[str]) -> list[SalesWorkspaceFilterOption]:
            return [
                SalesWorkspaceFilterOption(value=value, label=value, count=count)
                for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
            ]

        customer_options: list[SalesWorkspaceFilterOption] = []
        seen_customers: set[str] = set()
        for bundle in bundles:
            key = str(bundle.row.customer_external_id or bundle.row.customer_id or "")
            if not key or key in seen_customers:
                continue
            seen_customers.add(key)
            customer_options.append(
                SalesWorkspaceFilterOption(
                    value=key,
                    label=bundle.row.customer_name or "Не удалось определить клиента",
                    count=customer_counter.get(self._customer_counter_key(bundle.row), 0),
                )
            )

        return SalesWorkspaceFilterMetadata(
            organizations=_options(org_counter),
            statuses=_options(status_counter),
            customers=sorted(customer_options, key=lambda item: item.label),
            sales_reps=_options(sales_rep_counter),
            working_zones=_options(zone_counter),
            data_quality=_options(quality_counter),
        )

    def _apply_workspace_filters(
        self,
        bundles: list[_WorkspaceRowBundle],
        query: SalesWorkspaceQuery,
        scoped: _ScopedData,
    ) -> list[_WorkspaceRowBundle]:
        status_filter = {value.lower() for value in query.status}
        customer_filter = set(query.customer)
        sales_rep_filter = {value.lower() for value in query.sales_rep}
        working_zone_filter = {value.lower() for value in query.working_zone}
        quality_filter = {value.value for value in query.data_quality}
        search = (query.search or "").strip().lower()
        product_search = (query.product or "").strip().lower()

        result: list[_WorkspaceRowBundle] = []
        for bundle in bundles:
            row = bundle.row

            if (
                status_filter
                and row.normalized_status.lower() not in status_filter
                and row.display_status.lower() not in status_filter
            ):
                continue
            if (
                customer_filter
                and str(row.customer_external_id or row.customer_id or "") not in customer_filter
            ):
                continue
            if sales_rep_filter and (row.sales_rep_name or "").lower() not in sales_rep_filter:
                continue
            if (
                working_zone_filter
                and (row.working_zone_name or "").lower() not in working_zone_filter
            ):
                continue
            if quality_filter and row.data_quality_status.value not in quality_filter:
                continue
            if query.realised is not None and row.realised is not query.realised:
                continue
            if (
                query.has_returns is not None
                and ((row.returned_units or Decimal("0")) > 0) is not query.has_returns
            ):
                continue

            effective_amount = (
                row.realised_amount if row.realised_amount is not None else row.order_amount
            )
            if query.amount_min is not None and (
                effective_amount is None or effective_amount < query.amount_min
            ):
                continue
            if query.amount_max is not None and (
                effective_amount is None or effective_amount > query.amount_max
            ):
                continue

            if search and not self._matches_text_search(bundle, search, scoped):
                continue
            if product_search and not self._matches_product_search(bundle, product_search, scoped):
                continue

            result.append(bundle)

        return result

    def _sort_rows(
        self,
        bundles: list[_WorkspaceRowBundle],
        sort_by: SalesWorkspaceSortBy,
        sort_order: SalesWorkspaceSortOrder,
    ) -> list[_WorkspaceRowBundle]:
        reverse = sort_order is SalesWorkspaceSortOrder.DESC

        def _value(bundle: _WorkspaceRowBundle) -> Any:
            row = bundle.row
            if sort_by is SalesWorkspaceSortBy.ORDER_AMOUNT:
                return row.order_amount or Decimal("-1")
            if sort_by is SalesWorkspaceSortBy.REALISED_AMOUNT:
                return row.realised_amount or Decimal("-1")
            if sort_by is SalesWorkspaceSortBy.SOLD_UNITS:
                return row.sold_units or Decimal("-1")
            if sort_by is SalesWorkspaceSortBy.CUSTOMER:
                return row.customer_name or ""
            if sort_by is SalesWorkspaceSortBy.ORGANIZATION:
                return row.organization_name
            if sort_by is SalesWorkspaceSortBy.STATUS:
                return row.display_status
            return row.business_date or datetime.min.replace(tzinfo=UTC)

        return sorted(bundles, key=_value, reverse=reverse)

    def _paginate(
        self, bundles: list[_WorkspaceRowBundle], page: int, page_size: int
    ) -> SalesWorkspacePagination:
        safe_page_size = max(1, min(page_size, 100))
        safe_page = max(1, page)
        total_items = len(bundles)
        total_pages = max(1, ceil(total_items / safe_page_size)) if total_items else 1
        if safe_page > total_pages:
            safe_page = total_pages
        return SalesWorkspacePagination(
            page=safe_page,
            page_size=safe_page_size,
            total_items=total_items,
            total_pages=total_pages,
        )

    def _filter_by_period(
        self,
        bundles: list[_WorkspaceRowBundle],
        start: datetime | None,
        end: datetime | None,
    ) -> list[_WorkspaceRowBundle]:
        if start is None and end is None:
            return bundles

        filtered: list[_WorkspaceRowBundle] = []
        for bundle in bundles:
            moment = bundle.row.business_date
            if moment is None:
                continue
            if start is not None and moment < start:
                continue
            if end is not None and moment > end:
                continue
            filtered.append(bundle)
        return filtered

    def _resolve_detail_items(
        self,
        bundle: _WorkspaceRowBundle,
        scoped: _ScopedData,
    ) -> list[CanonicalSaleItem]:
        items = [item for item in scoped.sale_items if item.id in bundle.item_keys]
        return sorted(items, key=lambda item: item.line_number)

    def _resolve_detail_returns(
        self,
        bundle: _WorkspaceRowBundle,
        scoped: _ScopedData,
    ) -> list[SalesWorkspaceReturnItem]:
        returns: list[CanonicalCustomerReturn] = []
        for customer_return in scoped.customer_returns:
            if bundle.order is not None and customer_return.linked_order_id == bundle.order.id:
                returns.append(customer_return)
            if bundle.sale is not None and customer_return.linked_sale_id == bundle.sale.id:
                returns.append(customer_return)
        returns = self._merge_unique_rows(returns)

        return_items_by_return_id: dict[UUID, list[CanonicalCustomerReturnItem]] = defaultdict(list)
        for item in scoped.customer_return_items:
            return_items_by_return_id[item.customer_return_id].append(item)

        detail_rows: list[SalesWorkspaceReturnItem] = []
        for customer_return in returns:
            items = sorted(
                return_items_by_return_id.get(customer_return.id, []),
                key=lambda item: item.line_number,
            )
            if not items:
                detail_rows.append(
                    SalesWorkspaceReturnItem(
                        return_id=customer_return.id,
                        return_number=customer_return.return_number or customer_return.deal_id,
                        return_at=customer_return.return_at,
                        returned_quantity=self._null_if_zero(customer_return.returned_quantity),
                        amount=customer_return.total_amount,
                        currency_code=customer_return.currency_code,
                        reason_code=customer_return.return_reason_code,
                        status=customer_return.display_status,
                        data_quality_status=customer_return.data_quality_status,
                    )
                )
                continue

            for item in items:
                detail_rows.append(
                    SalesWorkspaceReturnItem(
                        return_id=customer_return.id,
                        return_number=customer_return.return_number or customer_return.deal_id,
                        return_at=customer_return.return_at,
                        product_code=item.product_code,
                        product_name=item.product_name,
                        returned_quantity=self._null_if_zero(item.returned_quantity),
                        amount=item.amount,
                        currency_code=item.currency_code or customer_return.currency_code,
                        reason_code=customer_return.return_reason_code,
                        status=customer_return.display_status,
                        data_quality_status=item.data_quality_status,
                    )
                )

        return detail_rows

    def _resolve_detail_payments(
        self,
        bundle: _WorkspaceRowBundle,
        scoped: _ScopedData,
    ) -> list[SalesWorkspacePaymentItem]:
        payments_by_id = {payment.id: payment for payment in scoped.payments}
        allocations: list[CanonicalPaymentAllocation] = []
        for allocation in scoped.payment_allocations:
            if bundle.order is not None and allocation.order_id == bundle.order.id:
                allocations.append(allocation)
            if bundle.sale is not None and allocation.sale_id == bundle.sale.id:
                allocations.append(allocation)
        allocations = self._merge_unique_rows(allocations)

        detail_rows: list[SalesWorkspacePaymentItem] = []
        for allocation in allocations:
            payment = payments_by_id.get(allocation.payment_id)
            if payment is None:
                continue
            detail_rows.append(
                SalesWorkspacePaymentItem(
                    payment_id=payment.id,
                    payment_number=payment.cashin_number or payment.payment_id,
                    paid_at=payment.paid_at,
                    amount=allocation.allocated_amount or payment.amount,
                    currency_code=allocation.currency_code or payment.currency_code,
                    normalized_payment_type=payment.normalized_payment_type,
                    allocation_type=allocation.allocation_type,
                    data_quality_status=payment.data_quality_status,
                )
            )

        return detail_rows

    @staticmethod
    def _list_scoped(
        loader: Callable[[UUID | None], Any],
        organization_ids: list[UUID],
    ) -> list[Any]:
        if not organization_ids:
            return list(loader(None))
        rows: list[Any] = []
        for organization_id in organization_ids:
            rows.extend(list(loader(organization_id)))
        return rows

    @staticmethod
    def _pick_primary_sale(sales: list[CanonicalSale]) -> CanonicalSale | None:
        if not sales:
            return None
        ranked = sorted(
            sales,
            key=lambda sale: (
                sale.data_quality_status != CanonicalDataQualityStatus.VERIFIED,
                sale.sale_at or sale.closed_at or sale.updated_at,
            ),
            reverse=False,
        )
        return ranked[0]

    @staticmethod
    def _merge_unique_rows(*groups: list[T]) -> list[T]:
        merged: list[T] = []
        seen: set[UUID] = set()
        for group in groups:
            for row in group:
                row_id = getattr(row, "id", None)
                if isinstance(row_id, UUID):
                    if row_id in seen:
                        continue
                    seen.add(row_id)
                merged.append(row)
        return merged

    @staticmethod
    def _sum_amount(rows: list[Any], attribute: str) -> Decimal | None:
        total = Decimal("0")
        found = False
        for row in rows:
            value = getattr(row, attribute, None)
            if value is None:
                continue
            total += Decimal(str(value))
            found = True
        return total if found and total != Decimal("0") else None

    @staticmethod
    def _sum_linked_payment_amount(
        order_allocations: list[CanonicalPaymentAllocation],
        sale_allocations: list[CanonicalPaymentAllocation],
        payments_by_id: dict[UUID, CanonicalPayment],
    ) -> Decimal | None:
        allocations = SalesWorkspaceService._merge_unique_rows(
            order_allocations,
            sale_allocations,
        )
        total = Decimal("0")
        found = False
        for allocation in allocations:
            if allocation.allocated_amount is not None:
                total += allocation.allocated_amount
                found = True
                continue
            payment = payments_by_id.get(allocation.payment_id)
            if payment is not None:
                total += payment.amount
                found = True
        return total if found and total != Decimal("0") else None

    def _matches_text_search(
        self,
        bundle: _WorkspaceRowBundle,
        search: str,
        scoped: _ScopedData,
    ) -> bool:
        row = bundle.row
        haystacks = [
            row.order_number,
            row.sale_number,
            row.deal_id,
            row.customer_name,
            row.customer_code,
            row.organization_name,
            row.sales_rep_name,
            row.working_zone_name,
        ]
        if any(search in (value or "").lower() for value in haystacks):
            return True
        return self._matches_product_search(bundle, search, scoped)

    def _matches_product_search(
        self,
        bundle: _WorkspaceRowBundle,
        search: str,
        scoped: _ScopedData,
    ) -> bool:
        detail_items = self._resolve_detail_items(bundle, scoped)
        return any(
            search in (item.product_name or "").lower()
            or search in (item.product_code or "").lower()
            for item in detail_items
        )

    @staticmethod
    def _row_quality(
        order_quality: CanonicalDataQualityStatus,
        sale_quality: CanonicalDataQualityStatus | None,
    ) -> CanonicalDataQualityStatus:
        if sale_quality is None:
            return order_quality
        qualities = [order_quality, sale_quality]
        if CanonicalDataQualityStatus.UNSAFE in qualities:
            return CanonicalDataQualityStatus.UNSAFE
        if CanonicalDataQualityStatus.UNRESOLVED in qualities:
            return CanonicalDataQualityStatus.UNRESOLVED
        if CanonicalDataQualityStatus.PARTIAL in qualities:
            return CanonicalDataQualityStatus.PARTIAL
        return CanonicalDataQualityStatus.VERIFIED

    @staticmethod
    def _analytics_status_from_quality(quality: CanonicalDataQualityStatus) -> AnalyticsDataStatus:
        if quality is CanonicalDataQualityStatus.VERIFIED:
            return AnalyticsDataStatus.AVAILABLE
        if quality is CanonicalDataQualityStatus.PARTIAL:
            return AnalyticsDataStatus.PARTIAL
        if quality is CanonicalDataQualityStatus.UNRESOLVED:
            return AnalyticsDataStatus.UNRESOLVED
        return AnalyticsDataStatus.NOT_AVAILABLE

    @staticmethod
    def _null_if_zero(value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        return None if value == Decimal("0") else value

    @staticmethod
    def _customer_counter_key(row: SalesWorkspaceTableRow) -> str:
        return str(row.customer_external_id or row.customer_id or row.customer_name or "")

    @staticmethod
    def _organization_name(
        organization_id: UUID,
        organizations_by_id: dict[UUID, CanonicalOrganization],
    ) -> str:
        organization = organizations_by_id.get(organization_id)
        return organization.name if organization is not None else str(organization_id)

    @staticmethod
    def _customer_name(
        customer_id: UUID | None,
        fallback_name: str | None,
        customers_by_id: dict[UUID, CanonicalCustomer],
    ) -> str | None:
        if customer_id is not None and customer_id in customers_by_id:
            return customers_by_id[customer_id].name
        return fallback_name or "Не удалось определить клиента"

    @staticmethod
    def _sales_rep_name(
        sales_rep_id: UUID | None,
        sales_reps_by_id: dict[UUID, CanonicalSalesRep],
        fallback_external_id: str | None,
    ) -> str | None:
        if sales_rep_id is not None and sales_rep_id in sales_reps_by_id:
            return (
                sales_reps_by_id[sales_rep_id].sales_manager_name
                or sales_reps_by_id[sales_rep_id].sales_manager_code
            )
        return fallback_external_id

    @staticmethod
    def _working_zone_name(
        working_zone_id: UUID | None,
        working_zones_by_id: dict[UUID, CanonicalWorkingZone],
        fallback_external_id: str | None,
    ) -> str | None:
        if working_zone_id is not None and working_zone_id in working_zones_by_id:
            zone = working_zones_by_id[working_zone_id]
            return zone.room_name or zone.room_code or zone.source_external_id
        return fallback_external_id


@dataclass(slots=True)
class _ScopedData:
    organizations: list[CanonicalOrganization]
    organizations_by_id: dict[UUID, CanonicalOrganization]
    customers: list[CanonicalCustomer]
    customers_by_id: dict[UUID, CanonicalCustomer]
    products: list[CanonicalProduct]
    products_by_id: dict[UUID, CanonicalProduct]
    sales_reps: list[CanonicalSalesRep]
    sales_reps_by_id: dict[UUID, CanonicalSalesRep]
    working_zones: list[CanonicalWorkingZone]
    working_zones_by_id: dict[UUID, CanonicalWorkingZone]
    orders: list[CanonicalOrder]
    sales: list[CanonicalSale]
    sale_items: list[CanonicalSaleItem]
    payments: list[CanonicalPayment]
    payment_allocations: list[CanonicalPaymentAllocation]
    customer_returns: list[CanonicalCustomerReturn]
    customer_return_items: list[CanonicalCustomerReturnItem]
    warehouse_names: dict[UUID, str]

    @property
    def orders_by_id(self) -> dict[UUID, CanonicalOrder]:
        return {order.id: order for order in self.orders}
