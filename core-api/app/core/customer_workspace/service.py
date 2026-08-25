"""Canonical Customers / Customer 360 business workspace service."""

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
    AnalyticsQuery,
)
from app.core.customer_workspace.models import (
    CustomerWorkspaceDetail,
    CustomerWorkspaceFilterMetadata,
    CustomerWorkspaceFilterOption,
    CustomerWorkspacePagination,
    CustomerWorkspacePaymentRow,
    CustomerWorkspaceProductRow,
    CustomerWorkspaceProvenance,
    CustomerWorkspaceQuery,
    CustomerWorkspaceResponse,
    CustomerWorkspaceReturnRow,
    CustomerWorkspaceRow,
    CustomerWorkspaceSaleRow,
    CustomerWorkspaceSortBy,
    CustomerWorkspaceSortOrder,
    CustomerWorkspaceSummary,
    CustomerWorkspaceTimelineEvent,
    CustomerWorkspaceVisitRow,
)
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
    CanonicalVisit,
    CanonicalWorkingZone,
)
from app.core.data_layer.contracts import CoreDataStore

T = TypeVar("T")


@dataclass(slots=True)
class _CustomerRowBundle:
    row: CustomerWorkspaceRow
    customer: CanonicalCustomer
    customer_sales: list[CanonicalSale]
    customer_orders: list[CanonicalOrder]
    customer_sale_items: list[CanonicalSaleItem]
    customer_payments: list[CanonicalPayment]
    customer_allocations: list[CanonicalPaymentAllocation]
    customer_returns: list[CanonicalCustomerReturn]
    customer_return_items: list[CanonicalCustomerReturnItem]
    customer_visits: list[CanonicalVisit]


@dataclass(slots=True)
class _ScopedCustomerData:
    organizations: list[CanonicalOrganization]
    organizations_by_id: dict[UUID, CanonicalOrganization]
    customers: list[CanonicalCustomer]
    customers_by_id: dict[UUID, CanonicalCustomer]
    products_by_id: dict[UUID, CanonicalProduct]
    sales_reps_by_id: dict[UUID, CanonicalSalesRep]
    working_zones_by_id: dict[UUID, CanonicalWorkingZone]
    orders: list[CanonicalOrder]
    sales: list[CanonicalSale]
    sale_items: list[CanonicalSaleItem]
    payments: list[CanonicalPayment]
    payment_allocations: list[CanonicalPaymentAllocation]
    customer_returns: list[CanonicalCustomerReturn]
    customer_return_items: list[CanonicalCustomerReturnItem]
    visits: list[CanonicalVisit]


class CustomerWorkspaceService:
    """Build Customers / Customer 360 payloads from Canonical V2."""

    def __init__(self, store: CoreDataStore) -> None:
        self._store = store
        self._analytics = BusinessAnalyticsEngine(store)

    def list_workspace(
        self,
        analytics_query: AnalyticsQuery,
        workspace_query: CustomerWorkspaceQuery,
    ) -> CustomerWorkspaceResponse:
        scoped = self._load_scoped_data(analytics_query)
        summary_payload = self._analytics.build_summary(analytics_query)
        customer_report = self._analytics.build_customers(analytics_query)
        row_bundles = self._build_row_bundles(scoped, customer_report)
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

        return CustomerWorkspaceResponse(
            period=summary_payload.period,
            summary=self._build_summary(summary_payload, customer_report),
            filters=filter_metadata,
            rows=[bundle.row for bundle in page_rows],
            pagination=pagination,
        )

    def get_detail(
        self,
        customer_id: UUID,
        analytics_query: AnalyticsQuery,
    ) -> CustomerWorkspaceDetail | None:
        scoped = self._load_scoped_data(analytics_query)
        customer_report = self._analytics.build_customers(analytics_query)
        bundle = next(
            (
                item
                for item in self._build_row_bundles(scoped, customer_report)
                if item.row.customer_id == customer_id
            ),
            None,
        )
        if bundle is None:
            return None

        reference_sources = {
            bundle.customer.source_endpoint,
            *(sale.source_endpoint for sale in bundle.customer_sales),
            *(payment.source_endpoint for payment in bundle.customer_payments),
            *(customer_return.source_endpoint for customer_return in bundle.customer_returns),
            *(visit.source_endpoint for visit in bundle.customer_visits),
        }

        products = self._build_customer_products(bundle, scoped)
        payments = self._build_customer_payments(bundle, scoped)
        returns = self._build_customer_returns(bundle, scoped)
        visits = self._build_customer_visits(bundle, scoped)
        timeline = self._build_timeline(bundle, scoped)
        sales = self._build_customer_sales(bundle, scoped)

        limitations: list[str] = []
        if bundle.customer.data_quality_status is not CanonicalDataQualityStatus.VERIFIED:
            limitations.append(
                "Профиль клиента заполнен частично. "
                "Бизнес-активность подтверждена, master-поля доступны не полностью."
            )
        if not bundle.customer_sales:
            limitations.append(
                "За выбранный период подтверждённые продажи по клиенту не найдены."
            )
        if not bundle.customer_payments:
            limitations.append(
                "Подтверждённые поступления по клиенту в выбранном срезе не найдены."
            )
        if not bundle.customer_visits:
            limitations.append("Визиты по клиенту в выбранном срезе не найдены.")

        return CustomerWorkspaceDetail(
            customer_id=bundle.row.customer_id,
            row=bundle.row,
            overview=self._build_customer_overview(bundle),
            sales=sales,
            products=products,
            payments=payments,
            returns=returns,
            visits=visits,
            timeline=timeline,
            ai_summary=self._build_ai_summary(bundle),
            provenance=CustomerWorkspaceProvenance(
                canonical_customer_id=bundle.customer.id,
                source_endpoint=bundle.customer.source_endpoint,
                source_external_id=bundle.customer.source_external_id,
                source_raw_record_id=bundle.customer.source_raw_record_id,
                request_filial_id=bundle.customer.request_filial_id,
                response_filial_id=bundle.customer.response_filial_id,
                request_company_id=bundle.customer.request_company_id,
                request_project_code=bundle.customer.request_project_code,
                data_quality_status=bundle.customer.data_quality_status,
                reference_sources=sorted(reference_sources),
            ),
            limitations=limitations,
        )

    def _load_scoped_data(self, analytics_query: AnalyticsQuery) -> _ScopedCustomerData:
        organization_ids = analytics_query.organization_ids
        if analytics_query.organization_id is not None:
            organization_ids = [analytics_query.organization_id]

        organizations = list(self._store.list_canonical_organizations())
        if organization_ids:
            allowed = set(organization_ids)
            organizations = [item for item in organizations if item.organization_id in allowed]

        customers = self._list_scoped(self._store.list_canonical_customers, organization_ids)
        products = self._list_scoped(self._store.list_canonical_products, organization_ids)
        sales_reps = self._list_scoped(self._store.list_canonical_sales_reps, organization_ids)
        working_zones = self._list_scoped(
            self._store.list_canonical_working_zones,
            organization_ids,
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
        visits = self._list_scoped(self._store.list_canonical_visits, organization_ids)

        return _ScopedCustomerData(
            organizations=organizations,
            organizations_by_id={item.organization_id: item for item in organizations},
            customers=customers,
            customers_by_id={item.id: item for item in customers},
            products_by_id={item.id: item for item in products},
            sales_reps_by_id={item.id: item for item in sales_reps},
            working_zones_by_id={item.id: item for item in working_zones},
            orders=orders,
            sales=sales,
            sale_items=sale_items,
            payments=payments,
            payment_allocations=payment_allocations,
            customer_returns=customer_returns,
            customer_return_items=customer_return_items,
            visits=visits,
        )

    def _build_summary(
        self,
        summary_payload: object,
        customer_report: object,
    ) -> CustomerWorkspaceSummary:
        business = summary_payload.business
        customer_items = customer_report.items
        customers_with_sales = sum(
            1 for item in customer_items if (item.orders_count.value or Decimal("0")) > 0
        )
        average_revenue = None
        if customer_items:
            revenue_value = business.revenue.value or Decimal("0")
            average_revenue = revenue_value / Decimal(len(customer_items))

        return CustomerWorkspaceSummary(
            unique_customers=business.unique_customers,
            customers_with_sales=AnalyticsMetricValue(
                value=Decimal(customers_with_sales),
                previous_value=None,
                delta=None,
                percent_delta=None,
                unit="count",
                status=(
                    AnalyticsDataStatus.AVAILABLE
                    if customer_items
                    else AnalyticsDataStatus.NO_DATA
                ),
                data_status=(
                    AnalyticsDataStatus.AVAILABLE
                    if customer_items
                    else AnalyticsDataStatus.NO_DATA
                ),
                coverage=1.0 if customer_items else None,
                confidence=1.0 if customer_items else None,
                currency=None,
                record_count=len(customer_items),
                note=(
                    "Клиенты с подтверждёнными заказами "
                    "или реализациями в выбранном контексте."
                ),
            ),
            revenue=business.revenue,
            average_revenue_per_customer=AnalyticsMetricValue(
                value=average_revenue,
                previous_value=None,
                delta=None,
                percent_delta=None,
                unit="money",
                status=(
                    AnalyticsDataStatus.AVAILABLE
                    if average_revenue is not None
                    else AnalyticsDataStatus.NO_DATA
                ),
                data_status=(
                    AnalyticsDataStatus.AVAILABLE
                    if average_revenue is not None
                    else AnalyticsDataStatus.NO_DATA
                ),
                coverage=business.revenue.coverage,
                confidence=business.revenue.confidence,
                currency=business.revenue.currency,
                record_count=len(customer_items),
                note="Средняя выручка на одного клиента в текущем срезе.",
            ),
            payments_received=business.payments_received,
            return_value=business.customer_return_value,
            visits=business.visits,
            active_customers=AnalyticsMetricValue(
                value=None,
                previous_value=None,
                delta=None,
                percent_delta=None,
                unit="count",
                status=AnalyticsDataStatus.NOT_AVAILABLE,
                data_status=AnalyticsDataStatus.NOT_AVAILABLE,
                coverage=None,
                confidence=None,
                currency=None,
                record_count=0,
                note=(
                    "Строгая детерминированная активность клиента "
                    "ещё не утверждена как отдельная бизнес-метрика."
                ),
            ),
        )

    def _build_row_bundles(
        self,
        scoped: _ScopedCustomerData,
        customer_report: object,
    ) -> list[_CustomerRowBundle]:
        analytics_by_external_id = {
            item.customer_external_id: item for item in customer_report.items
        }
        sales_by_customer_id = _group_by(scoped.sales, lambda item: item.customer_id)
        orders_by_customer_id = _group_by(scoped.orders, lambda item: item.customer_id)
        payments_by_customer_id = _group_by(scoped.payments, lambda item: item.customer_id)
        returns_by_customer_id = _group_by(scoped.customer_returns, lambda item: item.customer_id)
        visits_by_customer_id = _group_by(scoped.visits, lambda item: item.customer_id)
        sale_items_by_sale_id = _group_by(scoped.sale_items, lambda item: item.sale_id)
        payment_allocations_by_payment_id = _group_by(
            scoped.payment_allocations, lambda item: item.payment_id
        )
        return_items_by_return_id = _group_by(
            scoped.customer_return_items, lambda item: item.customer_return_id
        )

        rows: list[_CustomerRowBundle] = []

        for customer in scoped.customers:
            analytics = analytics_by_external_id.get(customer.source_external_id)
            customer_sales = sales_by_customer_id.get(customer.id, [])
            customer_orders = orders_by_customer_id.get(customer.id, [])
            customer_payments = payments_by_customer_id.get(customer.id, [])
            customer_returns = returns_by_customer_id.get(customer.id, [])
            customer_visits = visits_by_customer_id.get(customer.id, [])

            sale_items: list[CanonicalSaleItem] = []
            for sale in customer_sales:
                sale_items.extend(sale_items_by_sale_id.get(sale.id, []))

            allocations: list[CanonicalPaymentAllocation] = []
            for payment in customer_payments:
                allocations.extend(payment_allocations_by_payment_id.get(payment.id, []))

            return_items: list[CanonicalCustomerReturnItem] = []
            for customer_return in customer_returns:
                return_items.extend(return_items_by_return_id.get(customer_return.id, []))

            organization_ids = sorted(
                {
                    customer.organization_id,
                    *(sale.organization_id for sale in customer_sales),
                    *(payment.organization_id for payment in customer_payments),
                    *(customer_return.organization_id for customer_return in customer_returns),
                    *(visit.organization_id for visit in customer_visits),
                },
                key=str,
            )
            organization_names = [
                self._organization_name(org_id, scoped.organizations_by_id)
                for org_id in organization_ids
            ]

            sales_rep_names = sorted(
                {
                    self._sales_rep_name(
                        item.sales_rep_id,
                        scoped.sales_reps_by_id,
                        item.sales_rep_external_id,
                    )
                    for item in [*customer_sales, *customer_visits]
                    if (
                        self._sales_rep_name(
                            item.sales_rep_id,
                            scoped.sales_reps_by_id,
                            item.sales_rep_external_id,
                        )
                        is not None
                    )
                }
            )

            working_zone_names = sorted(
                {
                    self._working_zone_name(
                        item.working_zone_id,
                        scoped.working_zones_by_id,
                        item.working_zone_external_id,
                    )
                    for item in [*customer_sales, *customer_visits]
                    if hasattr(item, "working_zone_id")
                    and self._working_zone_name(
                        item.working_zone_id,
                        scoped.working_zones_by_id,
                        item.working_zone_external_id,
                    )
                    is not None
                }
            )

            payments_received = sum((item.amount for item in customer_payments), Decimal("0"))
            return_value = sum((item.total_amount for item in customer_returns), Decimal("0"))
            realised_sales_count = Decimal(len(customer_sales))
            row = CustomerWorkspaceRow(
                customer_id=customer.id,
                customer_external_id=customer.source_external_id,
                customer_code=customer.code,
                customer_name=customer.name or "Клиент не определён",
                organization_ids=organization_ids,
                organization_names=organization_names,
                customer_type=customer.customer_kind,
                orders_count=(
                    self._metric_decimal(analytics.orders_count)
                    if analytics
                    else Decimal(len(customer_orders))
                ),
                realised_sales_count=realised_sales_count,
                revenue=self._metric_decimal(analytics.revenue) if analytics else sum(
                    (item.total_amount for item in customer_sales), Decimal("0")
                ),
                sold_units=self._metric_decimal(analytics.sold_units) if analytics else sum(
                    (item.sold_quantity for item in sale_items), Decimal("0")
                ),
                average_order_value=self._metric_decimal(analytics.average_order_value)
                if analytics
                else self._safe_divide(
                    sum((item.total_amount for item in customer_sales), Decimal("0")),
                    Decimal(len(customer_sales)),
                ),
                payments_received=payments_received if customer_payments else None,
                return_value=return_value if customer_returns else None,
                visits_count=self._metric_decimal(analytics.visits_count) if analytics else Decimal(
                    len(customer_visits)
                ),
                first_purchase=(
                    analytics.first_order_date
                    if analytics
                    else self._min_date(customer_sales)
                ),
                last_purchase=(
                    analytics.last_order_date
                    if analytics
                    else self._max_date(customer_sales)
                ),
                days_since_last_purchase=self._metric_decimal(analytics.days_since_last_order)
                if analytics
                else self._days_since(self._max_date(customer_sales)),
                products_bought_count=self._metric_decimal(analytics.products_count)
                if analytics
                else Decimal(
                    len(
                        {
                            item.product_id
                            for item in sale_items
                            if item.product_id is not None
                        }
                    )
                ),
                sales_rep_names=sales_rep_names,
                working_zone_names=working_zone_names,
                phone=customer.main_phone,
                email=customer.email,
                address=customer.address,
                group_names=self._customer_group_names(customer),
                segment=analytics.segment if analytics else None,
                data_quality_status=customer.data_quality_status,
                data_status=(
                    analytics.data_status
                    if analytics
                    else self._analytics_status_from_quality(customer.data_quality_status)
                ),
            )
            rows.append(
                _CustomerRowBundle(
                    row=row,
                    customer=customer,
                    customer_sales=customer_sales,
                    customer_orders=customer_orders,
                    customer_sale_items=sale_items,
                    customer_payments=customer_payments,
                    customer_allocations=allocations,
                    customer_returns=customer_returns,
                    customer_return_items=return_items,
                    customer_visits=customer_visits,
                )
            )

        return rows

    def _build_filter_metadata(
        self,
        row_bundles: list[_CustomerRowBundle],
    ) -> CustomerWorkspaceFilterMetadata:
        organizations = Counter()
        customer_types = Counter()
        sales_reps = Counter()
        working_zones = Counter()
        data_quality = Counter()

        for bundle in row_bundles:
            for organization_name in bundle.row.organization_names:
                organizations[organization_name] += 1
            if bundle.row.customer_type:
                customer_types[bundle.row.customer_type] += 1
            for sales_rep_name in bundle.row.sales_rep_names:
                sales_reps[sales_rep_name] += 1
            for working_zone_name in bundle.row.working_zone_names:
                working_zones[working_zone_name] += 1
            data_quality[bundle.row.data_quality_status.value] += 1

        return CustomerWorkspaceFilterMetadata(
            organizations=self._optionize_counter(organizations),
            customer_types=self._optionize_counter(customer_types),
            sales_reps=self._optionize_counter(sales_reps),
            working_zones=self._optionize_counter(working_zones),
            data_quality=self._optionize_counter(data_quality),
        )

    def _apply_workspace_filters(
        self,
        row_bundles: list[_CustomerRowBundle],
        workspace_query: CustomerWorkspaceQuery,
    ) -> list[_CustomerRowBundle]:
        filtered = row_bundles

        if workspace_query.search:
            needle = workspace_query.search.strip().lower()
            filtered = [
                bundle
                for bundle in filtered
                if self._matches_search(bundle, needle)
            ]
        if workspace_query.has_sales is not None:
            if workspace_query.has_sales:
                filtered = [
                    bundle
                    for bundle in filtered
                    if (bundle.row.orders_count or Decimal("0")) > 0
                ]
            else:
                filtered = [
                    bundle
                    for bundle in filtered
                    if (bundle.row.orders_count or Decimal("0")) <= 0
                ]
        if workspace_query.has_payments is not None:
            filtered = [
                bundle
                for bundle in filtered
                if bool(bundle.customer_payments) is workspace_query.has_payments
            ]
        if workspace_query.has_returns is not None:
            filtered = [
                bundle
                for bundle in filtered
                if bool(bundle.customer_returns) is workspace_query.has_returns
            ]
        if workspace_query.has_visits is not None:
            filtered = [
                bundle
                for bundle in filtered
                if bool(bundle.customer_visits) is workspace_query.has_visits
            ]
        if workspace_query.customer_type:
            allowed = {item.lower() for item in workspace_query.customer_type}
            filtered = [
                bundle
                for bundle in filtered
                if (bundle.row.customer_type or "").lower() in allowed
            ]
        if workspace_query.sales_rep:
            allowed = {item.lower() for item in workspace_query.sales_rep}
            filtered = [
                bundle
                for bundle in filtered
                if any(item.lower() in allowed for item in bundle.row.sales_rep_names)
            ]
        if workspace_query.working_zone:
            allowed = {item.lower() for item in workspace_query.working_zone}
            filtered = [
                bundle
                for bundle in filtered
                if any(item.lower() in allowed for item in bundle.row.working_zone_names)
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
        return filtered

    def _sort_rows(
        self,
        row_bundles: list[_CustomerRowBundle],
        sort_by: CustomerWorkspaceSortBy,
        sort_order: CustomerWorkspaceSortOrder,
    ) -> list[_CustomerRowBundle]:
        reverse = sort_order is CustomerWorkspaceSortOrder.DESC
        key_map = {
            CustomerWorkspaceSortBy.CUSTOMER_NAME: lambda bundle: bundle.row.customer_name.lower(),
            CustomerWorkspaceSortBy.REVENUE: lambda bundle: bundle.row.revenue or Decimal("0"),
            CustomerWorkspaceSortBy.ORDERS: lambda bundle: bundle.row.orders_count or Decimal("0"),
            CustomerWorkspaceSortBy.SOLD_UNITS: (
                lambda bundle: bundle.row.sold_units or Decimal("0")
            ),
            CustomerWorkspaceSortBy.AVERAGE_ORDER: (
                lambda bundle: bundle.row.average_order_value or Decimal("0")
            ),
            CustomerWorkspaceSortBy.PAYMENTS: (
                lambda bundle: bundle.row.payments_received or Decimal("0")
            ),
            CustomerWorkspaceSortBy.RETURNS: lambda bundle: bundle.row.return_value or Decimal("0"),
            CustomerWorkspaceSortBy.VISITS: lambda bundle: bundle.row.visits_count or Decimal("0"),
            CustomerWorkspaceSortBy.LAST_PURCHASE: (
                lambda bundle: bundle.row.last_purchase
                or datetime.min.replace(tzinfo=UTC)
            ),
        }
        return sorted(row_bundles, key=key_map[sort_by], reverse=reverse)

    def _paginate(
        self,
        bundles: list[_CustomerRowBundle],
        page: int,
        page_size: int,
    ) -> CustomerWorkspacePagination:
        total_items = len(bundles)
        total_pages = max(1, ceil(total_items / page_size)) if total_items else 1
        current_page = min(page, total_pages)
        return CustomerWorkspacePagination(
            page=current_page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        )

    def _build_customer_overview(self, bundle: _CustomerRowBundle) -> CustomerWorkspaceSummary:
        return CustomerWorkspaceSummary(
            unique_customers=AnalyticsMetricValue(
                value=Decimal("1"),
                unit="count",
                status=AnalyticsDataStatus.AVAILABLE,
                data_status=AnalyticsDataStatus.AVAILABLE,
                record_count=1,
                note="Один выбранный клиент.",
            ),
            customers_with_sales=AnalyticsMetricValue(
                value=(
                    Decimal("1")
                    if bundle.customer_sales or bundle.customer_orders
                    else Decimal("0")
                ),
                unit="count",
                status=AnalyticsDataStatus.AVAILABLE,
                data_status=AnalyticsDataStatus.AVAILABLE,
                record_count=1,
                note="Наличие продаж или заказов по клиенту.",
            ),
            revenue=self._metric_from_decimal(
                bundle.row.revenue,
                "money",
                "UZS",
                len(bundle.customer_sales),
                note="Подтверждённая выручка клиента в выбранном срезе.",
            ),
            average_revenue_per_customer=self._metric_from_decimal(
                bundle.row.revenue,
                "money",
                "UZS",
                len(bundle.customer_sales),
                note="Так как открыт один клиент, значение равно его выручке.",
            ),
            payments_received=self._metric_from_decimal(
                bundle.row.payments_received,
                "money",
                "UZS",
                len(bundle.customer_payments),
                note="Подтверждённые поступления по клиенту.",
            ),
            return_value=self._metric_from_decimal(
                bundle.row.return_value,
                "money",
                "UZS",
                len(bundle.customer_returns),
                note="Стоимость возвратов клиента.",
            ),
            visits=self._metric_from_decimal(
                bundle.row.visits_count,
                "count",
                None,
                len(bundle.customer_visits),
                note="Количество визитов по клиенту.",
            ),
            active_customers=AnalyticsMetricValue(
                value=None,
                unit="count",
                status=AnalyticsDataStatus.NOT_AVAILABLE,
                data_status=AnalyticsDataStatus.NOT_AVAILABLE,
                record_count=0,
                note="Сегмент активности клиента не утверждён как отдельная KPI-метрика.",
            ),
        )

    def _build_customer_sales(
        self,
        bundle: _CustomerRowBundle,
        scoped: _ScopedCustomerData,
    ) -> list[CustomerWorkspaceSaleRow]:
        sales_by_order_id = {
            item.order_id: item
            for item in bundle.customer_sales
            if item.order_id is not None
        }
        rows: list[CustomerWorkspaceSaleRow] = []

        for order in bundle.customer_orders:
            sale = sales_by_order_id.get(order.id)
            rows.append(
                CustomerWorkspaceSaleRow(
                    record_id=order.id,
                    order_id=order.id,
                    sale_id=sale.id if sale is not None else None,
                    deal_id=order.deal_id,
                    order_number=order.order_number,
                    sale_number=sale.sale_number if sale is not None else None,
                    organization_id=order.organization_id,
                    organization_name=self._organization_name(
                        order.organization_id,
                        scoped.organizations_by_id,
                    ),
                    business_date=order.order_at or order.delivery_date,
                    normalized_status=order.normalized_status,
                    display_status=order.display_status,
                    order_amount=order.total_amount,
                    realised_amount=sale.total_amount if sale is not None else None,
                    sold_units=sale.sold_quantity if sale is not None else order.sold_quantity,
                    currency_code=sale.currency_code if sale is not None else order.currency_code,
                    data_quality_status=order.data_quality_status,
                )
            )

        orphan_sales = [
            item for item in bundle.customer_sales if item.order_id is None
        ]
        for sale in orphan_sales:
            rows.append(
                CustomerWorkspaceSaleRow(
                    record_id=sale.id,
                    order_id=None,
                    sale_id=sale.id,
                    deal_id=sale.deal_id,
                    order_number=None,
                    sale_number=sale.sale_number,
                    organization_id=sale.organization_id,
                    organization_name=self._organization_name(
                        sale.organization_id,
                        scoped.organizations_by_id,
                    ),
                    business_date=sale.sale_at or sale.closed_at,
                    normalized_status=sale.normalized_status,
                    display_status=sale.display_status,
                    order_amount=None,
                    realised_amount=sale.total_amount,
                    sold_units=sale.sold_quantity,
                    currency_code=sale.currency_code,
                    data_quality_status=sale.data_quality_status,
                )
            )

        rows.sort(
            key=lambda item: item.business_date or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return rows

    def _build_customer_products(
        self,
        bundle: _CustomerRowBundle,
        scoped: _ScopedCustomerData,
    ) -> list[CustomerWorkspaceProductRow]:
        grouped: dict[UUID | str, list[CanonicalSaleItem]] = defaultdict(list)
        for item in bundle.customer_sale_items:
            grouped[item.product_id or item.product_code or item.source_external_id].append(item)

        returns_by_product: dict[UUID | str, Decimal] = defaultdict(lambda: Decimal("0"))
        for item in bundle.customer_return_items:
            key = item.product_id or item.product_code or item.source_external_id
            returns_by_product[key] += item.returned_quantity

        rows: list[CustomerWorkspaceProductRow] = []
        for key, items in grouped.items():
            first = items[0]
            product = (
                scoped.products_by_id.get(first.product_id)
                if first.product_id is not None
                else None
            )
            orders = {
                item.order_id for item in items if item.order_id is not None
            }
            rows.append(
                CustomerWorkspaceProductRow(
                    product_id=first.product_id,
                    product_code=first.product_code,
                    product_name=(product.name if product is not None else first.product_name),
                    sold_units=sum((item.sold_quantity for item in items), Decimal("0")),
                    revenue=sum((item.amount for item in items), Decimal("0")),
                    orders_count=Decimal(len(orders)),
                    return_quantity=returns_by_product.get(key),
                    last_purchase=self._max_date_from_values(
                        [
                            sale.sale_at
                            for sale in bundle.customer_sales
                            if sale.id
                            in {
                                row.sale_id
                                for row in items
                                if row.sale_id is not None
                            }
                        ]
                    ),
                    currency_code=first.currency_code,
                    data_quality_status=self._worst_quality(
                        [item.data_quality_status for item in items]
                    ),
                )
            )
        rows.sort(key=lambda item: item.revenue or Decimal("0"), reverse=True)
        return rows

    def _build_customer_payments(
        self,
        bundle: _CustomerRowBundle,
        scoped: _ScopedCustomerData,
    ) -> list[CustomerWorkspacePaymentRow]:
        linked_allocations_by_payment: dict[UUID, list[CanonicalPaymentAllocation]] = (
            defaultdict(list)
        )
        for allocation in bundle.customer_allocations:
            linked_allocations_by_payment[allocation.payment_id].append(allocation)

        rows = [
            CustomerWorkspacePaymentRow(
                payment_id=payment.id,
                organization_id=payment.organization_id,
                organization_name=self._organization_name(
                    payment.organization_id,
                    scoped.organizations_by_id,
                ),
                paid_at=payment.paid_at,
                payment_number=payment.cashin_number or payment.cashin_id or payment.payment_id,
                amount=payment.amount,
                currency_code=payment.currency_code,
                normalized_payment_type=payment.normalized_payment_type,
                allocation_type=self._payment_allocation_type(
                    linked_allocations_by_payment.get(payment.id, [])
                ),
                data_quality_status=payment.data_quality_status,
            )
            for payment in sorted(
                bundle.customer_payments,
                key=lambda item: item.paid_at or datetime.min.replace(tzinfo=UTC),
                reverse=True,
            )
        ]
        return rows

    def _build_customer_returns(
        self,
        bundle: _CustomerRowBundle,
        scoped: _ScopedCustomerData,
    ) -> list[CustomerWorkspaceReturnRow]:
        items_by_return_id = _group_by(
            bundle.customer_return_items,
            lambda item: item.customer_return_id,
        )
        rows = []
        for customer_return in sorted(
            bundle.customer_returns,
            key=lambda item: item.return_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        ):
            products = sorted(
                {
                    item.product_name or item.product_code or "Продукт не определён"
                    for item in items_by_return_id.get(customer_return.id, [])
                }
            )
            rows.append(
                CustomerWorkspaceReturnRow(
                    return_id=customer_return.id,
                    organization_id=customer_return.organization_id,
                    organization_name=self._organization_name(
                        customer_return.organization_id,
                        scoped.organizations_by_id,
                    ),
                    return_number=customer_return.return_number or customer_return.return_id,
                    return_at=customer_return.return_at,
                    amount=customer_return.total_amount,
                    returned_quantity=customer_return.returned_quantity,
                    currency_code=customer_return.currency_code,
                    status=customer_return.display_status,
                    products=products,
                    data_quality_status=customer_return.data_quality_status,
                )
            )
        return rows

    def _build_customer_visits(
        self,
        bundle: _CustomerRowBundle,
        scoped: _ScopedCustomerData,
    ) -> list[CustomerWorkspaceVisitRow]:
        rows = []
        for visit in sorted(
            bundle.customer_visits,
            key=lambda item: item.visited_at or item.visit_date or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        ):
            rows.append(
                CustomerWorkspaceVisitRow(
                    visit_id=visit.id,
                    organization_id=visit.organization_id,
                    organization_name=self._organization_name(
                        visit.organization_id,
                        scoped.organizations_by_id,
                    ),
                    visit_date=visit.visited_at or visit.visit_date,
                    sales_rep_name=self._sales_rep_name(
                        visit.sales_rep_id,
                        scoped.sales_reps_by_id,
                        visit.sales_rep_external_id,
                    ),
                    working_zone_name=self._working_zone_name(
                        visit.working_zone_id,
                        scoped.working_zones_by_id,
                        visit.working_zone_external_id,
                    ),
                    status=visit.display_status,
                    duration_seconds=visit.duration_seconds or visit.derived_duration_seconds,
                    data_quality_status=visit.data_quality_status,
                )
            )
        return rows

    def _build_timeline(
        self,
        bundle: _CustomerRowBundle,
        scoped: _ScopedCustomerData,
    ) -> list[CustomerWorkspaceTimelineEvent]:
        events: list[CustomerWorkspaceTimelineEvent] = []

        for sale_row in self._build_customer_sales(bundle, scoped):
            events.append(
                CustomerWorkspaceTimelineEvent(
                    event_id=f"sale:{sale_row.record_id}",
                    event_type="sale",
                    title=(
                        sale_row.order_number
                        or sale_row.sale_number
                        or sale_row.deal_id
                        or "Продажа"
                    ),
                    happened_at=sale_row.business_date,
                    organization_name=sale_row.organization_name,
                    amount=sale_row.realised_amount or sale_row.order_amount,
                    quantity=sale_row.sold_units,
                    currency_code=sale_row.currency_code,
                    reference_id=sale_row.record_id,
                    reference_type="sale",
                    drilldown_target="/sales",
                    description=sale_row.display_status,
                )
            )

        for payment_row in self._build_customer_payments(bundle, scoped):
            events.append(
                CustomerWorkspaceTimelineEvent(
                    event_id=f"payment:{payment_row.payment_id}",
                    event_type="payment",
                    title=payment_row.payment_number or "Платёж",
                    happened_at=payment_row.paid_at,
                    organization_name=payment_row.organization_name,
                    amount=payment_row.amount,
                    quantity=None,
                    currency_code=payment_row.currency_code,
                    reference_id=payment_row.payment_id,
                    reference_type="payment",
                    drilldown_target="/customers",
                    description=payment_row.normalized_payment_type,
                )
            )

        for return_row in self._build_customer_returns(bundle, scoped):
            events.append(
                CustomerWorkspaceTimelineEvent(
                    event_id=f"return:{return_row.return_id}",
                    event_type="return",
                    title=return_row.return_number or "Возврат",
                    happened_at=return_row.return_at,
                    organization_name=return_row.organization_name,
                    amount=return_row.amount,
                    quantity=return_row.returned_quantity,
                    currency_code=return_row.currency_code,
                    reference_id=return_row.return_id,
                    reference_type="return",
                    drilldown_target="/customers",
                    description=return_row.status,
                )
            )

        for visit_row in self._build_customer_visits(bundle, scoped):
            events.append(
                CustomerWorkspaceTimelineEvent(
                    event_id=f"visit:{visit_row.visit_id}",
                    event_type="visit",
                    title="Визит",
                    happened_at=visit_row.visit_date,
                    organization_name=visit_row.organization_name,
                    amount=None,
                    quantity=None,
                    currency_code=None,
                    reference_id=visit_row.visit_id,
                    reference_type="visit",
                    drilldown_target="/customers",
                    description=visit_row.status,
                )
            )

        events.sort(
            key=lambda item: item.happened_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return events

    def _build_ai_summary(self, bundle: _CustomerRowBundle) -> str | None:
        revenue = bundle.row.revenue
        orders = bundle.row.orders_count
        last_purchase = bundle.row.last_purchase
        if revenue is None and orders is None:
            return None

        parts: list[str] = []
        if orders is not None:
            parts.append(f"За выбранный период клиент дал {int(orders)} заказов")
        if revenue is not None:
            parts.append(f"на сумму {revenue:,.0f} UZS".replace(",", " "))
        if last_purchase is not None:
            parts.append(
                f"последняя покупка — {last_purchase.astimezone(UTC).strftime('%d.%m.%Y')}"
            )
        if not parts:
            return None
        return ". ".join(parts).strip() + "."

    def _matches_search(self, bundle: _CustomerRowBundle, needle: str) -> bool:
        haystack = [
            bundle.row.customer_name,
            bundle.row.customer_external_id,
            bundle.row.customer_code,
            bundle.row.phone,
            bundle.row.email,
            *(bundle.row.organization_names),
        ]
        return any(value and needle in value.lower() for value in haystack)

    def _customer_group_names(self, customer: CanonicalCustomer) -> list[str]:
        names = []
        for item in customer.groups:
            name = item.get("name") or item.get("group_name")
            if name:
                names.append(str(name))
        return sorted(dict.fromkeys(names))

    def _organization_name(
        self,
        organization_id: UUID,
        organizations_by_id: dict[UUID, CanonicalOrganization],
    ) -> str:
        organization = organizations_by_id.get(organization_id)
        return organization.name if organization is not None else "Организация не определена"

    def _sales_rep_name(
        self,
        sales_rep_id: UUID | None,
        sales_reps_by_id: dict[UUID, CanonicalSalesRep],
        fallback: str | None,
    ) -> str | None:
        if sales_rep_id is not None and sales_rep_id in sales_reps_by_id:
            rep = sales_reps_by_id[sales_rep_id]
            return rep.sales_manager_name or rep.sales_manager_code or rep.source_external_id
        return fallback

    def _working_zone_name(
        self,
        working_zone_id: UUID | None,
        working_zones_by_id: dict[UUID, CanonicalWorkingZone],
        fallback: str | None,
    ) -> str | None:
        if working_zone_id is not None and working_zone_id in working_zones_by_id:
            zone = working_zones_by_id[working_zone_id]
            return zone.room_name or zone.room_code or zone.source_external_id
        return fallback

    def _payment_allocation_type(
        self,
        allocations: list[CanonicalPaymentAllocation],
    ) -> str | None:
        if not allocations:
            return None
        unique = {item.allocation_type for item in allocations if item.allocation_type}
        return ", ".join(sorted(unique)) if unique else None

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

    def _optionize_counter(self, counter: Counter[str]) -> list[CustomerWorkspaceFilterOption]:
        return [
            CustomerWorkspaceFilterOption(value=value, label=value, count=count)
            for value, count in sorted(counter.items(), key=lambda item: item[0].lower())
        ]

    def _safe_divide(self, numerator: Decimal, denominator: Decimal) -> Decimal | None:
        if denominator == 0:
            return None
        return numerator / denominator

    def _days_since(self, value: datetime | None) -> Decimal | None:
        if value is None:
            return None
        current = datetime.now(UTC)
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return Decimal((current.date() - normalized.date()).days)

    def _min_date(self, rows: list[CanonicalSale]) -> datetime | None:
        values = [row.sale_at or row.closed_at for row in rows if row.sale_at or row.closed_at]
        return min(values) if values else None

    def _max_date(self, rows: list[CanonicalSale]) -> datetime | None:
        values = [row.sale_at or row.closed_at for row in rows if row.sale_at or row.closed_at]
        return max(values) if values else None

    def _max_date_from_values(self, values: list[datetime | None]) -> datetime | None:
        resolved = [item for item in values if item is not None]
        return max(resolved) if resolved else None

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
