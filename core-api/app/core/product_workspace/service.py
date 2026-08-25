"""Canonical Products / Product 360 business workspace service."""

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
    AnalyticsMetricValue,
    AnalyticsProductItem,
    AnalyticsQuery,
)
from app.core.data_layer.canonical_v2 import (
    CanonicalCustomer,
    CanonicalCustomerReturn,
    CanonicalCustomerReturnItem,
    CanonicalDataQualityStatus,
    CanonicalInventoryBalance,
    CanonicalOrder,
    CanonicalOrganization,
    CanonicalProduct,
    CanonicalProductCategory,
    CanonicalProductPrice,
    CanonicalSale,
    CanonicalSaleItem,
    CanonicalWarehouse,
)
from app.core.data_layer.contracts import CoreDataStore
from app.core.product_workspace.models import (
    ProductWorkspaceCustomerRow,
    ProductWorkspaceDetail,
    ProductWorkspaceFilterMetadata,
    ProductWorkspaceFilterOption,
    ProductWorkspaceInventoryRow,
    ProductWorkspaceOrganizationRow,
    ProductWorkspacePagination,
    ProductWorkspacePriceRow,
    ProductWorkspaceProvenance,
    ProductWorkspaceQuery,
    ProductWorkspaceResponse,
    ProductWorkspaceReturnRow,
    ProductWorkspaceRow,
    ProductWorkspaceSaleRow,
    ProductWorkspaceSortBy,
    ProductWorkspaceSortOrder,
    ProductWorkspaceStockStatus,
    ProductWorkspaceSummary,
    ProductWorkspaceTimelineEvent,
)

T = TypeVar("T")


@dataclass(slots=True)
class _ProductGroup:
    identity_key: str
    anchor_product: CanonicalProduct
    products: list[CanonicalProduct]


@dataclass(slots=True)
class _ProductRowBundle:
    row: ProductWorkspaceRow
    group: _ProductGroup
    sale_items: list[CanonicalSaleItem]
    sales: list[CanonicalSale]
    orders: list[CanonicalOrder]
    returns: list[CanonicalCustomerReturn]
    return_items: list[CanonicalCustomerReturnItem]
    balances: list[CanonicalInventoryBalance]
    customers: list[CanonicalCustomer]
    prices: list[CanonicalProductPrice]


@dataclass(slots=True)
class _ScopedProductData:
    organizations_by_id: dict[UUID, CanonicalOrganization]
    categories_by_id: dict[UUID, CanonicalProductCategory]
    warehouses_by_id: dict[UUID, CanonicalWarehouse]
    customers_by_id: dict[UUID, CanonicalCustomer]
    products: list[CanonicalProduct]
    product_prices: list[CanonicalProductPrice]
    orders: list[CanonicalOrder]
    sales: list[CanonicalSale]
    sale_items: list[CanonicalSaleItem]
    returns: list[CanonicalCustomerReturn]
    return_items: list[CanonicalCustomerReturnItem]
    balances: list[CanonicalInventoryBalance]
    latest_balances: list[CanonicalInventoryBalance]


class ProductWorkspaceService:
    """Build Products / Product 360 payloads from Canonical V2."""

    def __init__(self, store: CoreDataStore) -> None:
        self._store = store
        self._analytics = BusinessAnalyticsEngine(store)

    def list_workspace(
        self,
        analytics_query: AnalyticsQuery,
        workspace_query: ProductWorkspaceQuery,
    ) -> ProductWorkspaceResponse:
        summary_payload = self._analytics.build_summary(analytics_query)
        product_report = self._analytics.build_products(analytics_query)
        scoped = self._load_scoped_data(analytics_query)
        row_bundles = self._build_row_bundles(scoped, product_report.items)
        filter_metadata = self._build_filter_metadata(row_bundles)
        row_bundles = self._apply_workspace_filters(row_bundles, workspace_query)
        row_bundles = self._sort_rows(
            row_bundles,
            workspace_query.sort_by,
            workspace_query.sort_order,
        )
        pagination = self._paginate(row_bundles, workspace_query.page, workspace_query.page_size)
        page_rows = row_bundles[
            pagination.page_size * (pagination.page - 1) : pagination.page_size * pagination.page
        ]

        return ProductWorkspaceResponse(
            period=summary_payload.period,
            summary=self._build_summary(row_bundles, summary_payload.business),
            filters=filter_metadata,
            rows=[bundle.row for bundle in page_rows],
            pagination=pagination,
        )

    def get_detail(
        self,
        product_id: UUID,
        analytics_query: AnalyticsQuery,
    ) -> ProductWorkspaceDetail | None:
        product_report = self._analytics.build_products(analytics_query)
        scoped = self._load_scoped_data(analytics_query)
        row_bundles = self._build_row_bundles(scoped, product_report.items)
        bundle = next((item for item in row_bundles if item.row.product_id == product_id), None)
        if bundle is None:
            return None

        reference_sources = {
            product.source_endpoint for product in bundle.group.products
        }
        reference_sources.update(item.source_endpoint for item in bundle.sale_items)
        reference_sources.update(item.source_endpoint for item in bundle.return_items)
        reference_sources.update(item.source_endpoint for item in bundle.balances)
        reference_sources.update(item.source_endpoint for item in bundle.prices)

        limitations: list[str] = []
        if not bundle.sale_items:
            limitations.append("Продажи по товару в выбранном периоде не найдены.")
        if not bundle.balances:
            limitations.append("Текущий складской snapshot по товару не найден.")
        if not bundle.prices:
            limitations.append("Нет подтверждённой прайс-лист цены.")
        if any(
            product.data_quality_status is not CanonicalDataQualityStatus.VERIFIED
            for product in bundle.group.products
        ):
            limitations.append(
                "Данные о закупочной связке доступны частично. "
                "Продажи и stock используются отдельно от sparse master price."
            )

        return ProductWorkspaceDetail(
            product_id=bundle.row.product_id,
            row=bundle.row,
            overview=self._build_product_overview(bundle),
            sales=self._build_sales_rows(bundle, scoped),
            organizations=self._build_organization_rows(bundle, scoped),
            customers=self._build_customer_rows(bundle, scoped),
            inventory=self._build_inventory_rows(bundle, scoped),
            prices=self._build_price_rows(bundle, scoped),
            returns=self._build_return_rows(bundle, scoped),
            timeline=self._build_timeline(bundle, scoped),
            ai_summary=self._build_ai_summary(bundle),
            provenance=ProductWorkspaceProvenance(
                canonical_product_id=bundle.group.anchor_product.id,
                source_endpoint=bundle.group.anchor_product.source_endpoint,
                source_external_id=bundle.group.anchor_product.source_external_id,
                source_raw_record_id=bundle.group.anchor_product.source_raw_record_id,
                request_filial_id=bundle.group.anchor_product.request_filial_id,
                response_filial_id=bundle.group.anchor_product.response_filial_id,
                request_company_id=bundle.group.anchor_product.request_company_id,
                request_project_code=bundle.group.anchor_product.request_project_code,
                data_quality_status=bundle.group.anchor_product.data_quality_status,
                reference_sources=sorted(reference_sources),
            ),
            limitations=limitations,
        )

    def _build_summary(
        self,
        row_bundles: list[_ProductRowBundle],
        business: object,
    ) -> ProductWorkspaceSummary:
        items = [bundle.row for bundle in row_bundles]
        sold_products = [item for item in items if (item.sold_units or Decimal("0")) > 0]
        sold_units = sum((item.sold_units or Decimal("0") for item in items), Decimal("0"))
        revenue = business.revenue
        average_selling_price = None
        if sold_units > 0 and revenue.value is not None:
            average_selling_price = revenue.value / sold_units
        low_stock = [
            item
            for item in items
            if item.stock_status is ProductWorkspaceStockStatus.LOW_STOCK
            and (item.current_stock or Decimal("0")) > 0
        ]
        out_of_stock = [
            item
            for item in items
            if item.stock_status is ProductWorkspaceStockStatus.OUT_OF_STOCK
        ]
        overstock = [
            item for item in items if item.stock_status is ProductWorkspaceStockStatus.OVERSTOCK
        ]
        return_qty = sum((item.return_quantity or Decimal("0") for item in items), Decimal("0"))
        return_value = sum((item.return_value or Decimal("0") for item in items), Decimal("0"))
        return ProductWorkspaceSummary(
            products=business.unique_products,
            products_sold=AnalyticsMetricValue(
                value=Decimal(len(sold_products)),
                unit="count",
                status=AnalyticsDataStatus.AVAILABLE if items else AnalyticsDataStatus.NO_DATA,
                data_status=AnalyticsDataStatus.AVAILABLE if items else AnalyticsDataStatus.NO_DATA,
                record_count=len(sold_products),
                note="Товары с подтверждёнными продажами в выбранном периоде.",
            ),
            sold_units=business.sold_units,
            revenue=revenue,
            average_selling_price=AnalyticsMetricValue(
                value=average_selling_price,
                unit="money",
                status=(
                    AnalyticsDataStatus.AVAILABLE
                    if average_selling_price is not None
                    else AnalyticsDataStatus.NO_DATA
                ),
                data_status=(
                    AnalyticsDataStatus.AVAILABLE
                    if average_selling_price is not None
                    else AnalyticsDataStatus.NO_DATA
                ),
                currency="UZS",
                record_count=len(sold_products),
                note="Средняя наблюдаемая цена продажи по canonical sale items.",
            ),
            current_stock=business.current_stock,
            out_of_stock=AnalyticsMetricValue(
                value=Decimal(len(out_of_stock)),
                unit="count",
                status=AnalyticsDataStatus.AVAILABLE if items else AnalyticsDataStatus.NO_DATA,
                data_status=AnalyticsDataStatus.AVAILABLE if items else AnalyticsDataStatus.NO_DATA,
                record_count=len(out_of_stock),
                note="Товары без текущего остатка по latest inventory snapshot.",
            ),
            low_stock=AnalyticsMetricValue(
                value=Decimal(len(low_stock)),
                unit="count",
                status=AnalyticsDataStatus.AVAILABLE if items else AnalyticsDataStatus.NO_DATA,
                data_status=AnalyticsDataStatus.AVAILABLE if items else AnalyticsDataStatus.NO_DATA,
                record_count=len(low_stock),
                note="Товары с low stock / stockout pressure.",
            ),
            overstock=AnalyticsMetricValue(
                value=Decimal(len(overstock)),
                unit="count",
                status=AnalyticsDataStatus.AVAILABLE if items else AnalyticsDataStatus.NO_DATA,
                data_status=AnalyticsDataStatus.AVAILABLE if items else AnalyticsDataStatus.NO_DATA,
                record_count=len(overstock),
                note="Товары с признаками overstock по deterministic stock rules.",
            ),
            return_quantity=AnalyticsMetricValue(
                value=return_qty if return_qty > 0 else Decimal("0"),
                unit="units",
                status=AnalyticsDataStatus.AVAILABLE if items else AnalyticsDataStatus.NO_DATA,
                data_status=AnalyticsDataStatus.AVAILABLE if items else AnalyticsDataStatus.NO_DATA,
                record_count=len(items),
                note="Сумма возвращённых единиц по canonical return items.",
            ),
            return_value=AnalyticsMetricValue(
                value=return_value if return_value > 0 else Decimal("0"),
                unit="money",
                status=AnalyticsDataStatus.AVAILABLE if items else AnalyticsDataStatus.NO_DATA,
                data_status=AnalyticsDataStatus.AVAILABLE if items else AnalyticsDataStatus.NO_DATA,
                currency="UZS",
                record_count=len(items),
                note="Сумма возвратов по товарным строкам.",
            ),
        )

    def _load_scoped_data(self, analytics_query: AnalyticsQuery) -> _ScopedProductData:
        organization_ids = analytics_query.organization_ids
        if analytics_query.organization_id is not None:
            organization_ids = [analytics_query.organization_id]

        organizations = list(self._store.list_canonical_organizations())
        if organization_ids:
            allowed = set(organization_ids)
            organizations = [item for item in organizations if item.organization_id in allowed]

        products = self._list_scoped(self._store.list_canonical_products, organization_ids)
        categories = self._list_scoped(
            self._store.list_canonical_product_categories,
            organization_ids,
        )
        warehouses = self._list_scoped(self._store.list_canonical_warehouses, organization_ids)
        customers = self._list_scoped(self._store.list_canonical_customers, organization_ids)
        product_prices = self._list_scoped(self._store.list_canonical_product_prices, organization_ids)
        orders = self._list_scoped(self._store.list_canonical_orders, organization_ids)
        sales = self._list_scoped(self._store.list_canonical_sales, organization_ids)
        sale_items = self._list_scoped(self._store.list_canonical_sale_items, organization_ids)
        returns = self._list_scoped(self._store.list_canonical_customer_returns, organization_ids)
        return_items = self._list_scoped(
            self._store.list_canonical_customer_return_items, organization_ids
        )
        balances = self._list_scoped(self._store.list_canonical_inventory_balances, organization_ids)

        return _ScopedProductData(
            organizations_by_id={item.organization_id: item for item in organizations},
            categories_by_id={item.id: item for item in categories},
            warehouses_by_id={item.id: item for item in warehouses},
            customers_by_id={item.id: item for item in customers},
            products=products,
            product_prices=product_prices,
            orders=orders,
            sales=sales,
            sale_items=sale_items,
            returns=returns,
            return_items=return_items,
            balances=balances,
            latest_balances=_latest_inventory_rows(balances),
        )

    def _build_row_bundles(
        self,
        scoped: _ScopedProductData,
        analytics_items: list[AnalyticsProductItem],
    ) -> list[_ProductRowBundle]:
        analytics_by_key = {
            self._identity_key_from_analytics(item): item for item in analytics_items
        }
        products_by_identity: dict[str, list[CanonicalProduct]] = defaultdict(list)
        for product in scoped.products:
            products_by_identity[self._identity_key_from_product(product)].append(product)

        sales_by_id = {item.id: item for item in scoped.sales}
        orders_by_id = {item.id: item for item in scoped.orders}
        customers_by_id = scoped.customers_by_id

        sale_items_by_identity: dict[str, list[CanonicalSaleItem]] = defaultdict(list)
        for item in scoped.sale_items:
            sale_items_by_identity[self._identity_key_from_line(item)].append(item)

        return_items_by_identity: dict[str, list[CanonicalCustomerReturnItem]] = defaultdict(list)
        for item in scoped.return_items:
            return_items_by_identity[self._identity_key_from_return_line(item)].append(item)

        balances_by_identity: dict[str, list[CanonicalInventoryBalance]] = defaultdict(list)
        for item in scoped.latest_balances:
            balances_by_identity[self._identity_key_from_balance(item)].append(item)

        prices_by_identity: dict[str, list[CanonicalProductPrice]] = defaultdict(list)
        for item in scoped.product_prices:
            prices_by_identity[self._identity_key_from_price(item)].append(item)

        bundles: list[_ProductRowBundle] = []
        for identity_key, products in products_by_identity.items():
            anchor = sorted(products, key=lambda item: str(item.id))[0]
            analytics = analytics_by_key.get(identity_key)
            sale_items = sale_items_by_identity.get(identity_key, [])
            sales = [
                sales_by_id[item.sale_id]
                for item in sale_items
                if item.sale_id is not None and item.sale_id in sales_by_id
            ]
            orders = [
                orders_by_id[item.order_id]
                for item in sale_items
                if item.order_id is not None and item.order_id in orders_by_id
            ]
            sales = list({item.id: item for item in sales}.values())
            orders = list({item.id: item for item in orders}.values())

            return_items = return_items_by_identity.get(identity_key, [])
            returns_by_id = {
                item.id: item
                for item in scoped.returns
                if item.id in {row.customer_return_id for row in return_items}
            }
            returns = list(returns_by_id.values())

            customers = list(
                {
                    customer.id: customer
                    for customer in (
                        customers_by_id.get(sale.customer_id)
                        for sale in sales
                        if sale.customer_id is not None
                    )
                    if customer is not None
                }.values()
            )
            balances = balances_by_identity.get(identity_key, [])
            prices = prices_by_identity.get(identity_key, [])
            stock_status, stock_reason = self._resolve_stock_status(analytics, balances)
            category_id, category_name = self._resolve_category(anchor, scoped)
            organization_ids = sorted(
                {item.organization_id for item in products},
                key=str,
            )
            organization_names = [
                self._organization_name(item, scoped.organizations_by_id)
                for item in organization_ids
            ]
            row = ProductWorkspaceRow(
                product_id=anchor.id,
                product_external_id=anchor.source_external_id,
                product_code=anchor.code,
                product_name=anchor.name,
                category_id=category_id,
                category_name=category_name,
                organization_ids=organization_ids,
                organization_names=organization_names,
                measure_code=anchor.measure_code,
                producer_code=anchor.producer_code,
                article_code=anchor.article_code,
                barcodes=anchor.barcodes,
                sold_units=self._metric_decimal(analytics.sold_units) if analytics else sum(
                    (item.sold_quantity for item in sale_items), Decimal("0")
                ),
                revenue=self._metric_decimal(analytics.revenue) if analytics else sum(
                    (item.amount for item in sale_items), Decimal("0")
                ),
                orders_count=self._metric_decimal(analytics.orders_count) if analytics else Decimal(
                    len({item.order_id for item in sale_items if item.order_id is not None})
                ),
                customers_count=self._metric_decimal(analytics.customers_count) if analytics else Decimal(
                    len(customers)
                ),
                average_selling_price=self._metric_decimal(analytics.average_selling_price)
                if analytics
                else self._safe_divide(
                    sum((item.amount for item in sale_items), Decimal("0")),
                    sum((item.sold_quantity for item in sale_items), Decimal("0")),
                ),
                current_stock=sum((item.quantity for item in balances), Decimal("0")) if balances else None,
                last_sale=(
                    analytics.last_sale_date
                    if analytics
                    else self._max_datetime(
                        [item.sale_at or item.closed_at for item in sales]
                    )
                ),
                first_sale=(
                    analytics.first_sale_date
                    if analytics
                    else self._min_datetime(
                        [item.sale_at or item.closed_at for item in sales]
                    )
                ),
                return_quantity=self._preferred_decimal(
                    self._metric_decimal(analytics.returns_quantity) if analytics else None,
                    sum((item.returned_quantity for item in return_items), Decimal("0")),
                ),
                return_value=self._preferred_decimal(
                    self._metric_decimal(analytics.returns_amount) if analytics else None,
                    sum((item.amount for item in return_items), Decimal("0")),
                ),
                stock_status=stock_status,
                stock_status_reason=stock_reason,
                data_quality_status=self._worst_quality(
                    [item.data_quality_status for item in products]
                ),
                data_status=(
                    analytics.data_status
                    if analytics is not None
                    else self._analytics_status_from_quality(anchor.data_quality_status)
                ),
            )
            bundles.append(
                _ProductRowBundle(
                    row=row,
                    group=_ProductGroup(
                        identity_key=identity_key,
                        anchor_product=anchor,
                        products=products,
                    ),
                    sale_items=sale_items,
                    sales=sales,
                    orders=orders,
                    returns=returns,
                    return_items=return_items,
                    balances=balances,
                    customers=customers,
                    prices=prices,
                )
            )
        return bundles

    def _build_filter_metadata(
        self,
        row_bundles: list[_ProductRowBundle],
    ) -> ProductWorkspaceFilterMetadata:
        organizations = Counter()
        categories = Counter()
        stock_statuses = Counter()
        data_quality = Counter()
        for bundle in row_bundles:
            for name in bundle.row.organization_names:
                organizations[name] += 1
            if bundle.row.category_id and bundle.row.category_name:
                categories[str(bundle.row.category_id)] = categories[str(bundle.row.category_id)] + 1
            if bundle.row.stock_status is not None:
                stock_statuses[bundle.row.stock_status.value] += 1
            data_quality[bundle.row.data_quality_status.value] += 1
        category_options = []
        for bundle in row_bundles:
            if bundle.row.category_id and bundle.row.category_name:
                category_options.append((str(bundle.row.category_id), bundle.row.category_name))
        category_counter: dict[str, tuple[str, int]] = {}
        for value, label in category_options:
            current = category_counter.get(value)
            category_counter[value] = (label, (current[1] if current else 0) + 1)

        return ProductWorkspaceFilterMetadata(
            organizations=self._optionize_counter(organizations),
            categories=[
                ProductWorkspaceFilterOption(value=value, label=label, count=count)
                for value, (label, count) in sorted(
                    category_counter.items(), key=lambda item: item[1][0].lower()
                )
            ],
            stock_statuses=self._optionize_counter(stock_statuses),
            data_quality=self._optionize_counter(data_quality),
        )

    def _apply_workspace_filters(
        self,
        row_bundles: list[_ProductRowBundle],
        workspace_query: ProductWorkspaceQuery,
    ) -> list[_ProductRowBundle]:
        filtered = row_bundles
        if workspace_query.search:
            needle = workspace_query.search.strip().lower()
            filtered = [bundle for bundle in filtered if self._matches_search(bundle, needle)]
        if workspace_query.category_id:
            allowed = {str(item) for item in workspace_query.category_id}
            filtered = [
                bundle
                for bundle in filtered
                if bundle.row.category_id is not None and str(bundle.row.category_id) in allowed
            ]
        if workspace_query.stock_status:
            allowed = {item.value for item in workspace_query.stock_status}
            filtered = [
                bundle
                for bundle in filtered
                if bundle.row.stock_status is not None and bundle.row.stock_status.value in allowed
            ]
        if workspace_query.has_sales is not None:
            filtered = [
                bundle
                for bundle in filtered
                if bool(bundle.sale_items) is workspace_query.has_sales
            ]
        if workspace_query.has_returns is not None:
            filtered = [
                bundle
                for bundle in filtered
                if bool(bundle.return_items) is workspace_query.has_returns
            ]
        if workspace_query.data_quality:
            allowed = {item.value for item in workspace_query.data_quality}
            filtered = [
                bundle
                for bundle in filtered
                if bundle.row.data_quality_status.value in allowed
            ]
        if workspace_query.revenue_min is not None:
            filtered = [
                bundle
                for bundle in filtered
                if (bundle.row.revenue or Decimal("0")) >= workspace_query.revenue_min
            ]
        if workspace_query.revenue_max is not None:
            filtered = [
                bundle
                for bundle in filtered
                if (bundle.row.revenue or Decimal("0")) <= workspace_query.revenue_max
            ]
        if workspace_query.sold_units_min is not None:
            filtered = [
                bundle
                for bundle in filtered
                if (bundle.row.sold_units or Decimal("0")) >= workspace_query.sold_units_min
            ]
        if workspace_query.sold_units_max is not None:
            filtered = [
                bundle
                for bundle in filtered
                if (bundle.row.sold_units or Decimal("0")) <= workspace_query.sold_units_max
            ]
        return filtered

    def _sort_rows(
        self,
        row_bundles: list[_ProductRowBundle],
        sort_by: ProductWorkspaceSortBy,
        sort_order: ProductWorkspaceSortOrder,
    ) -> list[_ProductRowBundle]:
        reverse = sort_order is ProductWorkspaceSortOrder.DESC
        key_map = {
            ProductWorkspaceSortBy.PRODUCT_NAME: lambda bundle: bundle.row.product_name.lower(),
            ProductWorkspaceSortBy.REVENUE: lambda bundle: bundle.row.revenue or Decimal("0"),
            ProductWorkspaceSortBy.SOLD_UNITS: lambda bundle: bundle.row.sold_units or Decimal("0"),
            ProductWorkspaceSortBy.ORDERS: lambda bundle: bundle.row.orders_count or Decimal("0"),
            ProductWorkspaceSortBy.CUSTOMERS: lambda bundle: bundle.row.customers_count or Decimal("0"),
            ProductWorkspaceSortBy.CURRENT_STOCK: lambda bundle: bundle.row.current_stock or Decimal("0"),
            ProductWorkspaceSortBy.LAST_SALE: lambda bundle: bundle.row.last_sale or datetime.min.replace(tzinfo=UTC),
            ProductWorkspaceSortBy.RETURN_QUANTITY: lambda bundle: bundle.row.return_quantity or Decimal("0"),
        }
        return sorted(row_bundles, key=key_map[sort_by], reverse=reverse)

    def _paginate(
        self,
        bundles: list[_ProductRowBundle],
        page: int,
        page_size: int,
    ) -> ProductWorkspacePagination:
        total_items = len(bundles)
        total_pages = max(1, ceil(total_items / page_size)) if total_items else 1
        current_page = min(page, total_pages)
        return ProductWorkspacePagination(
            page=current_page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        )

    def _build_product_overview(self, bundle: _ProductRowBundle) -> ProductWorkspaceSummary:
        sold_units = sum((item.sold_quantity for item in bundle.sale_items), Decimal("0"))
        revenue = sum((item.amount for item in bundle.sale_items), Decimal("0"))
        avg_price = self._safe_divide(revenue, sold_units)
        return_qty = sum((item.returned_quantity for item in bundle.return_items), Decimal("0"))
        return_value = sum((item.amount for item in bundle.return_items), Decimal("0"))
        current_stock = sum((item.quantity for item in bundle.balances), Decimal("0"))
        stock_status = bundle.row.stock_status
        return ProductWorkspaceSummary(
            products=AnalyticsMetricValue(
                value=Decimal("1"),
                unit="count",
                status=AnalyticsDataStatus.AVAILABLE,
                data_status=AnalyticsDataStatus.AVAILABLE,
                record_count=1,
                note="Один выбранный товар.",
            ),
            products_sold=AnalyticsMetricValue(
                value=Decimal("1") if bundle.sale_items else Decimal("0"),
                unit="count",
                status=AnalyticsDataStatus.AVAILABLE,
                data_status=AnalyticsDataStatus.AVAILABLE,
                record_count=1,
                note="Наличие подтверждённых продаж по товару.",
            ),
            sold_units=self._metric_from_decimal(
                sold_units if bundle.sale_items else None,
                "units",
                None,
                len(bundle.sale_items),
                note="Проданные единицы из canonical sale items.",
            ),
            revenue=self._metric_from_decimal(
                revenue if bundle.sale_items else None,
                "money",
                "UZS",
                len(bundle.sale_items),
                note="Выручка товара из realized sale items.",
            ),
            average_selling_price=self._metric_from_decimal(
                avg_price,
                "money",
                "UZS",
                len(bundle.sale_items),
                note="Средняя наблюдаемая цена продажи.",
            ),
            current_stock=self._metric_from_decimal(
                current_stock if bundle.balances else None,
                "units",
                None,
                len(bundle.balances),
                note="Текущий остаток из latest inventory snapshot.",
            ),
            out_of_stock=AnalyticsMetricValue(
                value=Decimal("1") if stock_status is ProductWorkspaceStockStatus.OUT_OF_STOCK else Decimal("0"),
                unit="count",
                status=AnalyticsDataStatus.AVAILABLE,
                data_status=AnalyticsDataStatus.AVAILABLE,
                record_count=1,
                note="1, если товар полностью отсутствует в текущем stock snapshot.",
            ),
            low_stock=AnalyticsMetricValue(
                value=Decimal("1") if stock_status is ProductWorkspaceStockStatus.LOW_STOCK else Decimal("0"),
                unit="count",
                status=AnalyticsDataStatus.AVAILABLE,
                data_status=AnalyticsDataStatus.AVAILABLE,
                record_count=1,
                note="1, если deterministic signal пометил товар как low stock.",
            ),
            overstock=AnalyticsMetricValue(
                value=Decimal("1") if stock_status is ProductWorkspaceStockStatus.OVERSTOCK else Decimal("0"),
                unit="count",
                status=AnalyticsDataStatus.AVAILABLE,
                data_status=AnalyticsDataStatus.AVAILABLE,
                record_count=1,
                note="1, если товар имеет overstock signal.",
            ),
            return_quantity=self._metric_from_decimal(
                return_qty if bundle.return_items else Decimal("0"),
                "units",
                None,
                len(bundle.return_items),
                note="Возвращённое количество по товару.",
            ),
            return_value=self._metric_from_decimal(
                return_value if bundle.return_items else Decimal("0"),
                "money",
                "UZS",
                len(bundle.return_items),
                note="Сумма возвратов по товару.",
            ),
        )

    def _build_sales_rows(
        self,
        bundle: _ProductRowBundle,
        scoped: _ScopedProductData,
    ) -> list[ProductWorkspaceSaleRow]:
        sales_by_id = {item.id: item for item in bundle.sales}
        orders_by_id = {item.id: item for item in bundle.orders}
        rows = []
        for item in sorted(
            bundle.sale_items,
            key=lambda row: self._sale_item_date(row, sales_by_id, orders_by_id)
            or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        ):
            sale = sales_by_id.get(item.sale_id) if item.sale_id is not None else None
            order = orders_by_id.get(item.order_id) if item.order_id is not None else None
            rows.append(
                ProductWorkspaceSaleRow(
                    sale_item_id=item.id,
                    sale_id=item.sale_id,
                    order_id=item.order_id,
                    business_date=self._sale_item_date(item, sales_by_id, orders_by_id),
                    organization_id=item.organization_id,
                    organization_name=self._organization_name(item.organization_id, scoped.organizations_by_id),
                    order_number=order.order_number if order is not None else None,
                    sale_number=sale.sale_number if sale is not None else None,
                    deal_id=sale.deal_id if sale is not None else (order.deal_id if order is not None else None),
                    customer_id=sale.customer_id if sale is not None else (order.customer_id if order is not None else None),
                    customer_name=sale.customer_name if sale is not None else (order.customer_name if order is not None else None),
                    sold_quantity=item.sold_quantity,
                    unit_price=item.unit_price,
                    amount=item.amount,
                    currency_code=item.currency_code,
                    display_status=sale.display_status if sale is not None else (order.display_status if order is not None else None),
                    data_quality_status=item.data_quality_status,
                )
            )
        return rows

    def _build_organization_rows(
        self,
        bundle: _ProductRowBundle,
        scoped: _ScopedProductData,
    ) -> list[ProductWorkspaceOrganizationRow]:
        sale_items_by_org = _group_by(bundle.sale_items, lambda item: item.organization_id)
        balances_by_org = _group_by(bundle.balances, lambda item: item.organization_id)
        sales_by_id = {item.id: item for item in bundle.sales}
        rows = []
        for organization_id in sorted(
            {*(sale_items_by_org.keys()), *(balances_by_org.keys()), *(product.organization_id for product in bundle.group.products)},
            key=str,
        ):
            items = sale_items_by_org.get(organization_id, [])
            org_sales = [
                sales_by_id[item.sale_id]
                for item in items
                if item.sale_id is not None and item.sale_id in sales_by_id
            ]
            customers_count = Decimal(
                len({sale.customer_id for sale in org_sales if sale.customer_id is not None})
            )
            balances = balances_by_org.get(organization_id, [])
            stock_status, _ = self._resolve_stock_status(
                self._product_analytics_for_org(bundle, organization_id),
                balances,
            )
            rows.append(
                ProductWorkspaceOrganizationRow(
                    organization_id=organization_id,
                    organization_name=self._organization_name(organization_id, scoped.organizations_by_id),
                    revenue=sum((item.amount for item in items), Decimal("0")) if items else None,
                    sold_units=sum((item.sold_quantity for item in items), Decimal("0")) if items else None,
                    orders_count=Decimal(
                        len({item.order_id for item in items if item.order_id is not None})
                    ) if items else None,
                    customers_count=customers_count if org_sales else None,
                    current_stock=sum((item.quantity for item in balances), Decimal("0")) if balances else None,
                    last_sale=self._max_datetime([sale.sale_at or sale.closed_at for sale in org_sales]),
                    stock_status=stock_status,
                    data_quality_status=self._worst_quality(
                        [*(item.data_quality_status for item in items), *(item.data_quality_status for item in balances)]
                    ),
                )
            )
        rows.sort(key=lambda item: item.revenue or Decimal("0"), reverse=True)
        return rows

    def _build_customer_rows(
        self,
        bundle: _ProductRowBundle,
        scoped: _ScopedProductData,
    ) -> list[ProductWorkspaceCustomerRow]:
        sales_by_id = {item.id: item for item in bundle.sales}
        sale_items_by_customer: dict[UUID, list[CanonicalSaleItem]] = defaultdict(list)
        for item in bundle.sale_items:
            sale = sales_by_id.get(item.sale_id) if item.sale_id is not None else None
            if sale is None or sale.customer_id is None:
                continue
            sale_items_by_customer[sale.customer_id].append(item)

        rows = []
        for customer_id, items in sale_items_by_customer.items():
            customer = scoped.customers_by_id.get(customer_id)
            if customer is None:
                continue
            relevant_sales = [
                sales_by_id[item.sale_id]
                for item in items
                if item.sale_id is not None and item.sale_id in sales_by_id
            ]
            rows.append(
                ProductWorkspaceCustomerRow(
                    customer_id=customer.id,
                    customer_name=customer.name or "Клиент не определён",
                    organization_id=customer.organization_id,
                    organization_name=self._organization_name(customer.organization_id, scoped.organizations_by_id),
                    sold_units=sum((item.sold_quantity for item in items), Decimal("0")) if items else None,
                    revenue=sum((item.amount for item in items), Decimal("0")) if items else None,
                    orders_count=Decimal(
                        len({item.order_id for item in items if item.order_id is not None})
                    ),
                    last_purchase=self._max_datetime([sale.sale_at or sale.closed_at for sale in relevant_sales]),
                    data_quality_status=customer.data_quality_status,
                )
            )
        rows.sort(key=lambda item: item.revenue or Decimal("0"), reverse=True)
        return rows

    def _build_inventory_rows(
        self,
        bundle: _ProductRowBundle,
        scoped: _ScopedProductData,
    ) -> list[ProductWorkspaceInventoryRow]:
        rows = [
            ProductWorkspaceInventoryRow(
                inventory_balance_id=item.id,
                organization_id=item.organization_id,
                organization_name=self._organization_name(item.organization_id, scoped.organizations_by_id),
                warehouse_id=item.warehouse_id,
                warehouse_code=item.warehouse_code,
                warehouse_name=self._warehouse_name(item.warehouse_id, scoped.warehouses_by_id),
                snapshot_date=item.snapshot_date,
                quantity=item.quantity,
                available_quantity=item.available_quantity,
                reserved_quantity=item.reserved_quantity,
                input_price=item.input_price,
                valuation_amount=item.valuation_amount,
                currency_code=item.currency_code,
                batch_number=item.batch_number,
                card_code=item.card_code,
                serial_number=item.serial_number,
                data_quality_status=item.data_quality_status,
            )
            for item in sorted(
                bundle.balances,
                key=lambda row: (
                    row.snapshot_date or datetime.min.replace(tzinfo=UTC),
                    self._organization_name(row.organization_id, scoped.organizations_by_id),
                    self._warehouse_name(row.warehouse_id, scoped.warehouses_by_id) or "",
                ),
                reverse=True,
            )
        ]
        return rows

    def _build_price_rows(
        self,
        bundle: _ProductRowBundle,
        scoped: _ScopedProductData,
    ) -> list[ProductWorkspacePriceRow]:
        rows = [
            ProductWorkspacePriceRow(
                price_id=item.id,
                source_type="master_price",
                organization_id=item.organization_id,
                organization_name=self._organization_name(item.organization_id, scoped.organizations_by_id),
                price_type_code=item.price_type_code,
                price_type_name=item.metadata.get("price_type_name"),
                price=item.price,
                currency_code=item.currency_code,
                effective_date=item.updated_at,
                note="Подтверждённая прайс-лист цена.",
                data_quality_status=item.data_quality_status,
            )
            for item in sorted(
                bundle.prices,
                key=lambda row: row.updated_at or datetime.min.replace(tzinfo=UTC),
                reverse=True,
            )
        ]

        observed_sale_prices = sorted(
            {
                (
                    item.organization_id,
                    item.unit_price,
                    item.currency_code,
                    self._sale_item_date(item, {sale.id: sale for sale in bundle.sales}, {order.id: order for order in bundle.orders}),
                )
                for item in bundle.sale_items
                if item.unit_price is not None
            },
            key=lambda row: row[3] or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        for organization_id, unit_price, currency_code, effective_date in observed_sale_prices[:10]:
            rows.append(
                ProductWorkspacePriceRow(
                    price_id=None,
                    source_type="observed_sale_price",
                    organization_id=organization_id,
                    organization_name=self._organization_name(organization_id, scoped.organizations_by_id),
                    price_type_code=None,
                    price_type_name=None,
                    price=unit_price,
                    currency_code=currency_code,
                    effective_date=effective_date,
                    note="Наблюдаемая transaction sale price.",
                    data_quality_status=CanonicalDataQualityStatus.VERIFIED,
                )
            )
        return rows

    def _build_return_rows(
        self,
        bundle: _ProductRowBundle,
        scoped: _ScopedProductData,
    ) -> list[ProductWorkspaceReturnRow]:
        returns_by_id = {item.id: item for item in bundle.returns}
        rows = []
        for item in sorted(
            bundle.return_items,
            key=lambda row: (
                returns_by_id.get(row.customer_return_id).return_at
                if row.customer_return_id in returns_by_id
                else datetime.min.replace(tzinfo=UTC)
            ),
            reverse=True,
        ):
            customer_return = returns_by_id.get(item.customer_return_id)
            rows.append(
                ProductWorkspaceReturnRow(
                    return_item_id=item.id,
                    return_id=item.customer_return_id,
                    organization_id=item.organization_id,
                    organization_name=self._organization_name(item.organization_id, scoped.organizations_by_id),
                    return_number=customer_return.return_number if customer_return is not None else None,
                    return_at=customer_return.return_at if customer_return is not None else None,
                    customer_id=customer_return.customer_id if customer_return is not None else None,
                    customer_name=customer_return.customer_name if customer_return is not None else None,
                    returned_quantity=item.returned_quantity,
                    amount=item.amount,
                    currency_code=item.currency_code,
                    status=customer_return.display_status if customer_return is not None else None,
                    data_quality_status=item.data_quality_status,
                )
            )
        return rows

    def _build_timeline(
        self,
        bundle: _ProductRowBundle,
        scoped: _ScopedProductData,
    ) -> list[ProductWorkspaceTimelineEvent]:
        events: list[ProductWorkspaceTimelineEvent] = []
        for row in self._build_sales_rows(bundle, scoped):
            events.append(
                ProductWorkspaceTimelineEvent(
                    event_id=f"sale:{row.sale_item_id}",
                    event_type="sale",
                    title=row.order_number or row.sale_number or row.deal_id or "Продажа",
                    happened_at=row.business_date,
                    organization_name=row.organization_name,
                    amount=row.amount,
                    quantity=row.sold_quantity,
                    currency_code=row.currency_code,
                    reference_id=row.order_id or row.sale_id,
                    reference_type="sale",
                    drilldown_target="/sales",
                    description=row.display_status,
                )
            )
        for row in self._build_return_rows(bundle, scoped):
            events.append(
                ProductWorkspaceTimelineEvent(
                    event_id=f"return:{row.return_item_id}",
                    event_type="return",
                    title=row.return_number or "Возврат",
                    happened_at=row.return_at,
                    organization_name=row.organization_name,
                    amount=row.amount,
                    quantity=row.returned_quantity,
                    currency_code=row.currency_code,
                    reference_id=row.return_id,
                    reference_type="return",
                    drilldown_target="/inventory",
                    description=row.status,
                )
            )
        for row in self._build_inventory_rows(bundle, scoped):
            events.append(
                ProductWorkspaceTimelineEvent(
                    event_id=f"inventory:{row.inventory_balance_id}",
                    event_type="inventory_snapshot",
                    title=row.warehouse_name or row.warehouse_code or "Складской snapshot",
                    happened_at=row.snapshot_date,
                    organization_name=row.organization_name,
                    amount=row.valuation_amount,
                    quantity=row.quantity,
                    currency_code=row.currency_code,
                    reference_id=row.inventory_balance_id,
                    reference_type="inventory_snapshot",
                    drilldown_target="/inventory",
                    description="Текущий остаток по складу",
                )
            )
        for row in self._build_price_rows(bundle, scoped):
            events.append(
                ProductWorkspaceTimelineEvent(
                    event_id=f"price:{row.source_type}:{row.organization_id}:{row.effective_date}",
                    event_type="price",
                    title="Цена",
                    happened_at=row.effective_date,
                    organization_name=row.organization_name,
                    amount=row.price,
                    quantity=None,
                    currency_code=row.currency_code,
                    reference_id=row.price_id,
                    reference_type="price",
                    drilldown_target="/inventory",
                    description=row.note,
                )
            )
        events.sort(
            key=lambda item: item.happened_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return events[:200]

    def _build_ai_summary(self, bundle: _ProductRowBundle) -> str | None:
        revenue = bundle.row.revenue
        sold_units = bundle.row.sold_units
        if revenue is None and sold_units is None:
            return None
        parts: list[str] = []
        if revenue is not None:
            parts.append(f"Товар принёс {revenue:,.0f} UZS выручки".replace(",", " "))
        if sold_units is not None:
            parts.append(f"и продан в объёме {sold_units.normalize()} ед.")
        if bundle.row.stock_status is ProductWorkspaceStockStatus.LOW_STOCK:
            parts.append("По текущему snapshot у товара low stock")
        if bundle.row.stock_status is ProductWorkspaceStockStatus.OVERSTOCK:
            parts.append("По текущему snapshot у товара overstock")
        if not parts:
            return None
        return ". ".join(parts).strip() + "."

    def _matches_search(self, bundle: _ProductRowBundle, needle: str) -> bool:
        haystack = [
            bundle.row.product_name,
            bundle.row.product_code,
            bundle.row.product_external_id,
            bundle.row.article_code,
            *(bundle.row.barcodes),
            *(bundle.row.organization_names),
            bundle.row.category_name,
        ]
        return any(value and needle in value.lower() for value in haystack)

    def _resolve_category(
        self,
        product: CanonicalProduct,
        scoped: _ScopedProductData,
    ) -> tuple[UUID | None, str | None]:
        primary_group_id = product.metadata.get("primary_group_id")
        if isinstance(primary_group_id, UUID):
            category = scoped.categories_by_id.get(primary_group_id)
            return primary_group_id, category.name if category is not None else None
        if isinstance(primary_group_id, str):
            try:
                category_uuid = UUID(primary_group_id)
            except ValueError:
                return None, None
            category = scoped.categories_by_id.get(category_uuid)
            return category_uuid, category.name if category is not None else None
        return None, None

    def _resolve_stock_status(
        self,
        analytics: AnalyticsProductItem | None,
        balances: list[CanonicalInventoryBalance],
    ) -> tuple[ProductWorkspaceStockStatus | None, str | None]:
        current_stock = sum((item.quantity for item in balances), Decimal("0")) if balances else None
        if current_stock is not None and current_stock <= 0:
            return (
                ProductWorkspaceStockStatus.OUT_OF_STOCK,
                "Текущий остаток по latest snapshot равен нулю.",
            )
        if analytics is not None and "OVERSTOCK" in analytics.classification_tags:
            return (
                ProductWorkspaceStockStatus.OVERSTOCK,
                "Analytics engine определил overstock по velocity и days of stock.",
            )
        if analytics is not None and analytics.stockout_risk in {"critical", "high", "medium"}:
            return (
                ProductWorkspaceStockStatus.LOW_STOCK,
                "Analytics engine определил low stock / stockout pressure.",
            )
        if current_stock is not None:
            return (
                ProductWorkspaceStockStatus.IN_STOCK,
                "Товар доступен в latest inventory snapshot.",
            )
        return None, None

    def _product_analytics_for_org(
        self,
        bundle: _ProductRowBundle,
        organization_id: UUID,
    ) -> AnalyticsProductItem | None:
        if bundle.row.organization_ids == [organization_id]:
            return None
        return None

    def _sale_item_date(
        self,
        item: CanonicalSaleItem,
        sales_by_id: dict[UUID, CanonicalSale],
        orders_by_id: dict[UUID, CanonicalOrder],
    ) -> datetime | None:
        sale = sales_by_id.get(item.sale_id) if item.sale_id is not None else None
        if sale is not None:
            return sale.sale_at or sale.closed_at
        order = orders_by_id.get(item.order_id) if item.order_id is not None else None
        if order is not None:
            return order.order_at or order.delivery_date
        return None

    def _identity_key_from_product(self, product: CanonicalProduct) -> str:
        return str(product.id)

    def _identity_key_from_analytics(self, item: AnalyticsProductItem) -> str:
        return str(item.product_id)

    def _identity_key_from_line(self, item: CanonicalSaleItem) -> str:
        return str(
            item.product_id or item.product_external_id or item.product_code or item.source_external_id
        )

    def _identity_key_from_return_line(self, item: CanonicalCustomerReturnItem) -> str:
        return str(
            item.product_id or item.product_external_id or item.product_code or item.source_external_id
        )

    def _identity_key_from_balance(self, item: CanonicalInventoryBalance) -> str:
        return str(
            item.product_id or item.product_external_id or item.product_code or item.source_external_id
        )

    def _identity_key_from_price(self, item: CanonicalProductPrice) -> str:
        return str(item.product_id or item.product_code or item.source_external_id)

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

    def _metric_decimal(self, value: AnalyticsMetricValue) -> Decimal | None:
        if value.value is None:
            return None
        return Decimal(str(value.value))

    def _metric_from_decimal(
        self,
        value: Decimal | None,
        unit: str,
        currency: str | None,
        record_count: int,
        *,
        note: str,
    ) -> AnalyticsMetricValue:
        status = AnalyticsDataStatus.AVAILABLE if value is not None else AnalyticsDataStatus.NO_DATA
        return AnalyticsMetricValue(
            value=value,
            unit=unit,
            status=status,
            data_status=status,
            currency=currency,
            record_count=record_count,
            note=note,
        )

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

    def _optionize_counter(self, counter: Counter[str]) -> list[ProductWorkspaceFilterOption]:
        return [
            ProductWorkspaceFilterOption(value=value, label=value, count=count)
            for value, count in sorted(counter.items(), key=lambda item: item[0].lower())
        ]

    def _safe_divide(self, numerator: Decimal, denominator: Decimal) -> Decimal | None:
        if denominator == 0:
            return None
        return numerator / denominator

    def _preferred_decimal(
        self,
        primary: Decimal | None,
        fallback: Decimal | None,
    ) -> Decimal | None:
        if primary is not None and primary != Decimal("0"):
            return primary
        if fallback is not None and fallback != Decimal("0"):
            return fallback
        return primary if primary is not None else fallback

    def _max_datetime(self, values: list[datetime | None]) -> datetime | None:
        resolved = [item for item in values if item is not None]
        return max(resolved) if resolved else None

    def _min_datetime(self, values: list[datetime | None]) -> datetime | None:
        resolved = [item for item in values if item is not None]
        return min(resolved) if resolved else None

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


def _group_by[T, K](items: list[T], key_fn: Callable[[T], K]) -> dict[K, list[T]]:
    grouped: dict[K, list[T]] = defaultdict(list)
    for item in items:
        grouped[key_fn(item)].append(item)
    return grouped


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
