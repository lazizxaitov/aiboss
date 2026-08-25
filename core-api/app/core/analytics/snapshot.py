"""Business analytics snapshot service for the executive dashboard."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.analytics.models import (
    AnalyticsDomainSummary,
    AnalyticsKPI,
    AnalyticsPeriodWindow,
    BusinessAnalyticsSnapshot,
)
from app.core.data_layer.contracts import CoreDataReader
from app.core.data_layer.entities import FinanceEntryType, SaleStage
from app.core.data_layer.normalized import (
    BusinessDocument,
    InventoryBalance,
    Product,
    ProductPrice,
    Sale,
    SaleItem,
    Visit,
)


class BusinessAnalyticsSnapshotService:
    """Build the structured analytics snapshot used by AI and dashboard widgets."""

    def __init__(self, store: CoreDataReader) -> None:
        self.store = store

    def build_snapshot(
        self,
        *,
        business_id: UUID | None = None,
        organization_ids: list[UUID] | None = None,
        period_key: str = "12m",
    ) -> BusinessAnalyticsSnapshot:
        businesses = list(self.store.list_businesses())
        smartup_orgs = list(self.store.list_smartup_organizations(is_active=True))

        selected_organization_ids = list(dict.fromkeys(organization_ids or []))
        if not selected_organization_ids and business_id is not None:
            selected_organization_ids = [business_id]

        if selected_organization_ids:
            selected_ids = set(selected_organization_ids)
            businesses = [
                business for business in businesses if business.business_id in selected_ids
            ]

        window = _period_window(period_key)

        sales = _filter_organization_items(
            list(self.store.list_sales_v2()),
            selected_organization_ids,
        )
        sale_items = _filter_organization_items(
            list(self.store.list_sale_items()),
            selected_organization_ids,
        )
        customers = _filter_organization_items(
            list(self.store.list_customers()),
            selected_organization_ids,
        )
        products = _filter_organization_items(
            list(self.store.list_products()),
            selected_organization_ids,
        )
        inventory_balances = _filter_organization_items(
            list(self.store.list_inventory_balances()),
            selected_organization_ids,
        )
        payments = _filter_organization_items(
            list(self.store.list_payments()),
            selected_organization_ids,
        )
        finance_entries = _filter_organization_items(
            list(self.store.list_finance_entries()),
            selected_organization_ids,
        )
        visits = _filter_organization_items(
            list(self.store.list_visits()),
            selected_organization_ids,
        )
        bank_operations = _filter_organization_items(
            list(self.store.list_bank_operations()),
            selected_organization_ids,
        )
        documents = _filter_organization_items(
            list(self.store.list_business_documents()),
            selected_organization_ids,
        )
        product_prices = _filter_organization_items(
            list(self.store.list_product_prices()),
            selected_organization_ids,
        )
        marketing_activities = _filter_organization_items(
            list(self.store.list_marketing_activities()),
            selected_organization_ids,
        )

        current_sales = _filter_by_window(sales, window, lambda item: item.sale_at)
        previous_sales = _previous_by_window(sales, window, lambda item: item.sale_at)
        current_sale_items = _sale_items_for_sales(sale_items, current_sales)
        previous_sale_items = _sale_items_for_sales(sale_items, previous_sales)
        current_payments = _filter_by_window(payments, window, lambda item: item.paid_at)
        previous_payments = _previous_by_window(payments, window, lambda item: item.paid_at)
        current_finance = _filter_by_window(
            finance_entries,
            window,
            lambda item: item.occurred_at,
        )
        previous_finance = _previous_by_window(
            finance_entries,
            window,
            lambda item: item.occurred_at,
        )
        current_visits = _filter_by_window(visits, window, lambda item: item.visited_at)
        previous_visits = _previous_by_window(visits, window, lambda item: item.visited_at)
        current_inventory = _filter_by_window(
            inventory_balances,
            window,
            lambda item: item.balance_at,
        )
        previous_inventory = _previous_by_window(
            inventory_balances,
            window,
            lambda item: item.balance_at,
        )
        current_documents = _filter_by_window(
            documents,
            window,
            lambda item: item.document_at,
        )
        previous_documents = _previous_by_window(
            documents,
            window,
            lambda item: item.document_at,
        )
        current_marketing = _filter_by_window(
            marketing_activities,
            window,
            lambda item: item.occurred_at,
        )
        previous_marketing = _previous_by_window(
            marketing_activities,
            window,
            lambda item: item.occurred_at,
        )
        current_bank = _filter_by_window(
            bank_operations,
            window,
            lambda item: item.occurred_at,
        )
        previous_bank = _previous_by_window(
            bank_operations,
            window,
            lambda item: item.occurred_at,
        )

        current_completed_sales = [sale for sale in current_sales if _is_completed_sale(sale)]
        previous_completed_sales = [sale for sale in previous_sales if _is_completed_sale(sale)]
        current_return_sales = [sale for sale in current_sales if _is_returned_sale(sale)]
        previous_return_sales = [sale for sale in previous_sales if _is_returned_sale(sale)]
        current_return_docs = _return_documents(current_documents)
        previous_return_docs = _return_documents(previous_documents)

        current_revenue = sum((sale.amount for sale in current_completed_sales), Decimal("0"))
        previous_revenue = sum((sale.amount for sale in previous_completed_sales), Decimal("0"))
        current_orders = len(current_completed_sales)
        previous_orders = len(previous_completed_sales)
        current_sold_units = sum(
            (item.quantity for item in current_sale_items),
            Decimal("0"),
        )
        previous_sold_units = sum(
            (item.quantity for item in previous_sale_items),
            Decimal("0"),
        )
        current_avg_order = (
            current_revenue / Decimal(current_orders) if current_orders > 0 else Decimal("0")
        )
        previous_avg_order = (
            previous_revenue / Decimal(previous_orders) if previous_orders > 0 else Decimal("0")
        )
        current_payments_received = sum(
            (payment.amount for payment in current_payments), Decimal("0")
        )
        previous_payments_received = sum(
            (payment.amount for payment in previous_payments),
            Decimal("0"),
        )
        current_expenses = sum(
            (
                entry.amount
                for entry in current_finance
                if entry.entry_type == FinanceEntryType.EXPENSE
            ),
            Decimal("0"),
        )
        previous_expenses = sum(
            (
                entry.amount
                for entry in previous_finance
                if entry.entry_type == FinanceEntryType.EXPENSE
            ),
            Decimal("0"),
        )
        current_cash_flow = current_payments_received - current_expenses
        previous_cash_flow = previous_payments_received - previous_expenses
        current_returns = _sum_returns(current_return_sales, current_return_docs)
        previous_returns = _sum_returns(previous_return_sales, previous_return_docs)
        current_receivables = max(Decimal("0"), current_revenue - current_payments_received)
        previous_receivables = max(Decimal("0"), previous_revenue - previous_payments_received)
        current_visit_conversion = (
            (Decimal(current_orders) / Decimal(len(current_visits))) * Decimal("100")
            if current_visits
            else Decimal("0")
        )
        previous_visit_conversion = (
            (Decimal(previous_orders) / Decimal(len(previous_visits))) * Decimal("100")
            if previous_visits
            else Decimal("0")
        )
        current_inventory_value, previous_inventory_value, inventory_value_available = (
            _inventory_value(current_inventory, previous_inventory, product_prices)
        )
        current_active_customers = len(
            {
                sale.customer_external_id
                for sale in current_completed_sales
                if sale.customer_external_id
            }
        )
        previous_active_customers = len(
            {
                sale.customer_external_id
                for sale in previous_completed_sales
                if sale.customer_external_id
            }
        )
        current_sales_rep_summary = _sales_rep_summary(current_completed_sales)
        previous_sales_rep_summary = _sales_rep_summary(previous_completed_sales)
        current_merchandising_spend = sum(
            (activity.spend for activity in current_marketing),
            Decimal("0"),
        )
        previous_merchandising_spend = sum(
            (activity.spend for activity in previous_marketing),
            Decimal("0"),
        )

        current_sales_summary = _domain_summary(
            key="sales",
            label="Продажи",
            current_count=current_orders,
            previous_count=previous_orders,
            current_amount=current_revenue,
            previous_amount=previous_revenue,
            details_href="/api/v1/dashboard/overview?section=sales",
            top_entities=_top_sale_numbers(current_completed_sales),
            unit="currency",
        )
        current_products_summary = _domain_summary(
            key="products",
            label="Товары",
            current_count=len(products),
            previous_count=len(products),
            current_amount=sum((item.amount for item in current_sale_items), Decimal("0")),
            previous_amount=sum((item.amount for item in previous_sale_items), Decimal("0")),
            details_href="/api/v1/dashboard/overview?section=products",
            top_entities=_top_products(products, current_sale_items),
            unit="currency",
        )
        current_customers_summary = _domain_summary(
            key="customers",
            label="Клиенты",
            current_count=len(customers),
            previous_count=len(customers),
            current_amount=Decimal(current_active_customers),
            previous_amount=Decimal(previous_active_customers),
            details_href="/api/v1/dashboard/overview?section=customers",
            top_entities=_top_customers(current_completed_sales),
            unit="count",
        )
        current_org_summary = _domain_summary(
            key="organizations",
            label="Организации",
            current_count=len(businesses),
            previous_count=len(businesses),
            current_amount=Decimal(len(smartup_orgs)),
            previous_amount=Decimal(len(smartup_orgs)),
            details_href="/api/v1/dashboard/overview?section=organizations",
            top_entities=[business.name for business in businesses[:5]],
            unit="count",
        )
        current_sales_rep_domain = _domain_summary(
            key="sales_reps",
            label="Торговые представители",
            current_count=len(current_sales_rep_summary),
            previous_count=len(previous_sales_rep_summary),
            current_amount=sum(
                (row["revenue"] for row in current_sales_rep_summary.values()), Decimal("0")
            ),
            previous_amount=sum(
                (row["revenue"] for row in previous_sales_rep_summary.values()),
                Decimal("0"),
            ),
            details_href="/api/v1/dashboard/overview?section=sales-reps",
            top_entities=list(current_sales_rep_summary.keys())[:5],
            unit="currency",
        )
        current_inventory_domain = _domain_summary(
            key="inventory",
            label="Склад",
            current_count=len(current_inventory),
            previous_count=len(previous_inventory),
            current_amount=current_inventory_value
            if inventory_value_available
            else sum(
                (balance.quantity for balance in current_inventory),
                Decimal("0"),
            ),
            previous_amount=previous_inventory_value
            if inventory_value_available
            else sum(
                (balance.quantity for balance in previous_inventory),
                Decimal("0"),
            ),
            details_href="/api/v1/dashboard/overview?section=inventory",
            top_entities=[balance.product_external_id for balance in current_inventory[:5]],
            unit="currency" if inventory_value_available else "units",
            note="стоимость склада" if inventory_value_available else "остатки по количеству",
        )
        current_finance_domain = _domain_summary(
            key="finance",
            label="Финансы",
            current_count=len(current_finance),
            previous_count=len(previous_finance),
            current_amount=current_payments_received,
            previous_amount=previous_payments_received,
            details_href="/api/v1/dashboard/overview?section=finance",
            top_entities=[entry.category for entry in current_finance[:5] if entry.category],
            unit="currency",
        )
        current_returns_domain = _domain_summary(
            key="returns",
            label="Возвраты",
            current_count=len(current_return_sales) + len(current_return_docs),
            previous_count=len(previous_return_sales) + len(previous_return_docs),
            current_amount=current_returns,
            previous_amount=previous_returns,
            details_href="/api/v1/dashboard/overview?section=returns",
            top_entities=_top_return_sources(current_return_sales, current_return_docs),
            unit="currency",
        )
        current_visits_domain = _domain_summary(
            key="visits",
            label="Визиты",
            current_count=len(current_visits),
            previous_count=len(previous_visits),
            current_amount=Decimal(current_orders),
            previous_amount=Decimal(previous_orders),
            details_href="/api/v1/dashboard/overview?section=visits",
            top_entities=_top_visit_customers(current_visits),
            unit="count",
        )
        current_merchandising_domain = _domain_summary(
            key="merchandising",
            label="Мерчандайзинг",
            current_count=len(current_marketing),
            previous_count=len(previous_marketing),
            current_amount=current_merchandising_spend,
            previous_amount=previous_merchandising_spend,
            details_href="/api/v1/dashboard/overview?section=merchandising",
            top_entities=_top_marketing_campaigns(current_marketing),
            unit="currency",
        )

        kpis = [
            _kpi(
                key="revenue",
                label="Выручка",
                current_value=current_revenue,
                previous_value=previous_revenue,
                unit="currency",
                details_href="/api/v1/data/sales",
            ),
            _kpi(
                key="orders",
                label="Заказы",
                current_value=Decimal(current_orders),
                previous_value=Decimal(previous_orders),
                unit="count",
                details_href="/api/v1/data/sales",
            ),
            _kpi(
                key="sold_units",
                label="Продано единиц",
                current_value=current_sold_units,
                previous_value=previous_sold_units,
                unit="count",
                details_href="/api/v1/data/sale-items",
            ),
            _kpi(
                key="average_order",
                label="Средний заказ",
                current_value=current_avg_order,
                previous_value=previous_avg_order,
                unit="currency",
                details_href="/api/v1/data/sales",
            ),
            _kpi(
                key="payments_received",
                label="Получено денег",
                current_value=current_payments_received,
                previous_value=previous_payments_received,
                unit="currency",
                details_href="/api/v1/data/payments",
            ),
            _kpi(
                key="returns",
                label="Возвраты",
                current_value=current_returns,
                previous_value=previous_returns,
                unit="currency",
                details_href="/api/v1/data/returns",
            ),
            _kpi(
                key="expenses",
                label="Расходы",
                current_value=current_expenses,
                previous_value=previous_expenses,
                unit="currency",
                details_href="/api/v1/data/processing",
            ),
            _kpi(
                key="cash_flow",
                label="Денежный поток",
                current_value=current_cash_flow,
                previous_value=previous_cash_flow,
                unit="currency",
                details_href="/api/v1/data/overview",
            ),
            _kpi(
                key="active_customers",
                label="Активные клиенты",
                current_value=Decimal(current_active_customers),
                previous_value=Decimal(previous_active_customers),
                unit="count",
                details_href="/api/v1/data/customers",
            ),
            _kpi(
                key="receivables",
                label="Дебиторка",
                current_value=current_receivables,
                previous_value=previous_receivables,
                unit="currency",
                details_href="/api/v1/data/payments",
            ),
            _kpi(
                key="visits",
                label="Визиты",
                current_value=Decimal(len(current_visits)),
                previous_value=Decimal(len(previous_visits)),
                unit="count",
                details_href="/api/v1/data/visits",
            ),
            _kpi(
                key="visit_conversion",
                label="Конверсия визитов",
                current_value=current_visit_conversion,
                previous_value=previous_visit_conversion,
                unit="percent",
                details_href="/api/v1/data/visits",
            ),
        ]

        coverage = {
            "sales": len(current_sales),
            "sale_items": len(current_sale_items),
            "customers": len(customers),
            "products": len(products),
            "inventory": len(current_inventory),
            "finance": len(current_finance),
            "payments": len(current_payments),
            "returns": len(current_return_sales) + len(current_return_docs),
            "visits": len(current_visits),
            "merchandising": len(current_marketing),
        }

        return BusinessAnalyticsSnapshot(
            period=window,
            organization_ids=[business.business_id for business in businesses],
            organization_names=[business.name for business in businesses],
            business_count=len(businesses),
            smartup_organization_count=len(smartup_orgs),
            kpis=kpis,
            sales=current_sales_summary,
            products=current_products_summary,
            customers=current_customers_summary,
            organizations=current_org_summary,
            sales_reps=current_sales_rep_domain,
            inventory=current_inventory_domain,
            finance=current_finance_domain,
            returns=current_returns_domain,
            visits=current_visits_domain,
            merchandising=current_merchandising_domain,
            coverage=coverage,
            top_products=_top_products(products, current_sale_items),
            top_sales_reps=list(current_sales_rep_summary.keys())[:5],
            top_customers=_top_customers(current_completed_sales),
            notes=[
                "AI получает только структурированный snapshot, а не raw records.",
                "Widget layout будет вычислен из приоритетов и контента.",
            ],
            metadata={
                "current_sales_count": len(current_sales),
                "previous_sales_count": len(previous_sales),
                "current_payments_count": len(current_payments),
                "previous_payments_count": len(previous_payments),
                "current_finance_count": len(current_finance),
                "previous_finance_count": len(previous_finance),
                "current_visits_count": len(current_visits),
                "previous_visits_count": len(previous_visits),
                "current_bank_operations_count": len(current_bank),
                "previous_bank_operations_count": len(previous_bank),
                "current_documents_count": len(current_documents),
                "previous_documents_count": len(previous_documents),
            },
        )


def _period_window(period_key: str) -> AnalyticsPeriodWindow:
    now = datetime.now(UTC)
    key = (period_key or "12m").strip().casefold()
    if key == "all":
        return AnalyticsPeriodWindow(
            current_start=None,
            current_end=None,
            previous_start=None,
            previous_end=None,
            label="за всё время",
            comparison_label="исторически",
        )

    if key in {"30d", "last_30_days"}:
        current_start = now - timedelta(days=30)
        previous_start = now - timedelta(days=60)
        return AnalyticsPeriodWindow(
            current_start=current_start,
            current_end=now,
            previous_start=previous_start,
            previous_end=current_start,
            label="за 30 дней",
            comparison_label="к предыдущим 30 дням",
        )

    if key in {"90d", "last_90_days"}:
        current_start = now - timedelta(days=90)
        previous_start = now - timedelta(days=180)
        return AnalyticsPeriodWindow(
            current_start=current_start,
            current_end=now,
            previous_start=previous_start,
            previous_end=current_start,
            label="за 90 дней",
            comparison_label="к предыдущим 90 дням",
        )

    current_start = now - timedelta(days=365)
    previous_start = now - timedelta(days=730)
    return AnalyticsPeriodWindow(
        current_start=current_start,
        current_end=now,
        previous_start=previous_start,
        previous_end=current_start,
        label="за 12 месяцев",
        comparison_label="к предыдущим 12 месяцам",
    )


def _filter_by_window(items: list[Any], window: AnalyticsPeriodWindow, getter) -> list[Any]:
    if window.current_start is None:
        return list(items)
    filtered: list[Any] = []
    for item in items:
        timestamp = getter(item)
        if timestamp is None:
            continue
        timestamp = timestamp.astimezone(UTC)
        if window.current_start is not None and timestamp < window.current_start:
            continue
        if window.current_end is not None and timestamp > window.current_end:
            continue
        filtered.append(item)
    return filtered


def _previous_by_window(items: list[Any], window: AnalyticsPeriodWindow, getter) -> list[Any]:
    if window.previous_start is None:
        return []
    filtered: list[Any] = []
    for item in items:
        timestamp = getter(item)
        if timestamp is None:
            continue
        timestamp = timestamp.astimezone(UTC)
        if timestamp < window.previous_start:
            continue
        if window.previous_end is not None and timestamp > window.previous_end:
            continue
        filtered.append(item)
    return filtered


def _sale_items_for_sales(items: list[SaleItem], sales: list[Sale]) -> list[SaleItem]:
    sale_ids = {sale.id for sale in sales}
    sale_external_ids = {sale.source_external_id for sale in sales if sale.source_external_id}
    return [
        item
        for item in items
        if (item.sale_id is not None and item.sale_id in sale_ids)
        or (item.sale_external_id and item.sale_external_id in sale_external_ids)
    ]


def _is_completed_sale(sale: Sale) -> bool:
    return (sale.status or "").strip().casefold() == SaleStage.WON.value


def _is_returned_sale(sale: Sale) -> bool:
    return (sale.status or "").strip().casefold() == SaleStage.REFUNDED.value


def _return_documents(documents: list[BusinessDocument]) -> list[BusinessDocument]:
    return [
        document
        for document in documents
        if (document.document_type or "").strip().casefold() in {"return", "return_to_supplier"}
    ]


def _sum_returns(
    return_sales: list[Sale],
    return_documents: list[BusinessDocument],
) -> Decimal:
    return sum((sale.amount for sale in return_sales), Decimal("0")) + sum(
        (document.amount for document in return_documents),
        Decimal("0"),
    )


def _inventory_value(
    current_inventory: list[InventoryBalance],
    previous_inventory: list[InventoryBalance],
    product_prices: list[ProductPrice],
) -> tuple[Decimal, Decimal, bool]:
    prices = _latest_price_by_product(product_prices)
    if not prices:
        return Decimal("0"), Decimal("0"), False
    current_value = sum(
        (balance.quantity * prices.get(balance.product_external_id, Decimal("0")))
        for balance in current_inventory
    )
    previous_value = sum(
        (balance.quantity * prices.get(balance.product_external_id, Decimal("0")))
        for balance in previous_inventory
    )
    return current_value, previous_value, True


def _latest_price_by_product(product_prices: list[ProductPrice]) -> dict[str, Decimal]:
    latest: dict[str, tuple[datetime, Decimal]] = {}
    for price in product_prices:
        candidate_time = price.effective_from or price.source_updated_at or price.imported_at
        current = latest.get(price.product_external_id)
        if current is None or candidate_time > current[0]:
            latest[price.product_external_id] = (candidate_time, price.price)
    return {product_external_id: price for product_external_id, (_, price) in latest.items()}


def _sales_rep_summary(sales: list[Sale]) -> dict[str, dict[str, Decimal | int]]:
    summary: dict[str, dict[str, Decimal | int]] = {}
    for sale in sales:
        metadata = sale.metadata or {}
        manager_code = (
            _first_text(
                metadata,
                "sales_manager_code",
                "responsible_person_code",
                "person_code",
                "owner_person_code",
            )
            or "Без кода"
        )
        row = summary.setdefault(
            manager_code,
            {"revenue": Decimal("0"), "orders": 0, "units": Decimal("0")},
        )
        row["revenue"] = row["revenue"] + sale.amount
        row["orders"] = int(row["orders"]) + 1
    return summary


def _top_sale_numbers(sales: list[Sale]) -> list[str]:
    return [
        sale.sale_number or sale.source_external_id
        for sale in sales[:5]
        if sale.sale_number or sale.source_external_id
    ]


def _top_products(products: list[Product], sale_items: list[SaleItem]) -> list[str]:
    sold_counts = Counter(
        item.product_external_id for item in sale_items if item.product_external_id
    )
    ranked = []
    product_names = {product.source_external_id: product.name for product in products}
    for product_external_id, count in sold_counts.most_common(5):
        ranked.append(f"{product_names.get(product_external_id, product_external_id)} · {count}")
    if ranked:
        return ranked
    return [product.name for product in products[:5]]


def _top_customers(sales: list[Sale]) -> list[str]:
    counts = Counter(sale.customer_external_id for sale in sales if sale.customer_external_id)
    return [customer for customer, _ in counts.most_common(5)]


def _top_return_sources(
    return_sales: list[Sale],
    return_documents: list[BusinessDocument],
) -> list[str]:
    values = [
        sale.sale_number or sale.source_external_id
        for sale in return_sales
        if sale.sale_number or sale.source_external_id
    ]
    values.extend(
        document.document_number or document.source_external_id
        for document in return_documents
        if document.document_number or document.source_external_id
    )
    return values[:5]


def _top_visit_customers(visits: list[Visit]) -> list[str]:
    return [visit.customer_external_id for visit in visits if visit.customer_external_id][:5]


def _top_marketing_campaigns(activities: list[Any]) -> list[str]:
    return [
        activity.campaign_name
        for activity in activities[:5]
        if getattr(activity, "campaign_name", None)
    ]


def _domain_summary(
    *,
    key: str,
    label: str,
    current_count: int,
    previous_count: int,
    current_amount: Decimal,
    previous_amount: Decimal,
    details_href: str | None,
    top_entities: list[str],
    unit: str,
    note: str | None = None,
) -> AnalyticsDomainSummary:
    count_delta = current_count - previous_count
    amount_delta = current_amount - previous_amount
    count_percent_delta = (
        ((Decimal(current_count) - Decimal(previous_count)) / Decimal(previous_count))
        * Decimal("100")
        if previous_count
        else None
    )
    amount_percent_delta = (
        ((current_amount - previous_amount) / previous_amount) * Decimal("100")
        if previous_amount
        else None
    )
    return AnalyticsDomainSummary(
        key=key,
        label=label,
        current_count=current_count,
        previous_count=previous_count,
        current_amount=current_amount,
        previous_amount=previous_amount,
        count_delta=count_delta,
        amount_delta=amount_delta,
        count_percent_delta=count_percent_delta,
        amount_percent_delta=amount_percent_delta,
        top_entities=top_entities,
        details_href=details_href,
        note=note,
        unit=unit,
        data_status="available"
        if (current_count or previous_count or current_amount or previous_amount)
        else "unavailable",
    )


def _kpi(
    *,
    key: str,
    label: str,
    current_value: Decimal,
    previous_value: Decimal | None,
    unit: str,
    details_href: str | None,
) -> AnalyticsKPI:
    if previous_value is None:
        absolute_delta = None
        percent_delta = None
        direction = "flat"
        status = "stable" if current_value != 0 else "unavailable"
    else:
        absolute_delta = current_value - previous_value
        percent_delta = (
            ((current_value - previous_value) / previous_value) * Decimal("100")
            if previous_value != 0
            else None
        )
        if absolute_delta > 0:
            direction = "up"
        elif absolute_delta < 0:
            direction = "down"
        else:
            direction = "flat"
        status = "growth" if direction == "up" else "decline" if direction == "down" else "stable"

    trend = [previous_value or Decimal("0"), current_value]
    return AnalyticsKPI(
        key=key,
        label=label,
        current_value=current_value,
        previous_value=previous_value,
        absolute_delta=absolute_delta,
        percent_delta=percent_delta,
        trend=trend,
        details_href=details_href,
        unit=unit,
        direction=direction,
        status=status,
        data_status="available"
        if current_value != 0 or (previous_value or Decimal("0")) != 0
        else "unavailable",
    )


def _first_text(metadata: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _filter_organization_items(items: list, organization_ids: list[UUID]) -> list:
    if not organization_ids:
        return items
    selected_ids = set(organization_ids)
    filtered: list = []
    for item in items:
        item_organization_id = getattr(item, "organization_id", None)
        item_business_id = getattr(item, "business_id", None)
        if item_organization_id in selected_ids or item_business_id in selected_ids:
            filtered.append(item)
    return filtered
