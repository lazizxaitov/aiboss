"""SmartUp mirror / data explorer foundation."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.data_explorer import (
    DataExplorerCollection,
    DataExplorerPageResponse,
    DataExplorerService,
)
from app.core.data_layer.normalized import (
    Customer,
    Sale,
)
from app.integrations.smartup.verification import (
    SmartUpTraceResponse,
    SmartUpVerificationReport,
    SmartUpVerificationService,
)


@dataclass(slots=True)
class SmartUpMirrorService:
    """Build dense SmartUp mirror pages."""

    store: CoreDataStore
    verification: SmartUpVerificationService = field(init=False, repr=False)
    _organization_names: dict[UUID, str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.verification = SmartUpVerificationService(self.store)
        self._organization_names = {
            organization.id: organization.name
            for organization in self.store.list_smartup_organizations()
        }

    def build_overview(self, organization_id: UUID | None = None) -> SmartUpVerificationReport:
        return self.verification.build_coverage_report(organization_id=organization_id)

    def build_coverage(self, organization_id: UUID | None = None) -> SmartUpVerificationReport:
        return self.verification.build_coverage_report(organization_id=organization_id)

    def build_orders_page(
        self,
        *,
        organization_id: UUID | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> DataExplorerPageResponse:
        rows = self._build_order_rows(organization_id)
        return self._page("orders", "Orders", rows, page=page, page_size=page_size)

    def build_customers_page(
        self,
        *,
        organization_id: UUID | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> DataExplorerPageResponse:
        rows = self._build_customer_rows(organization_id)
        return self._page("customers", "Customers", rows, page=page, page_size=page_size)

    def build_products_page(
        self,
        *,
        organization_id: UUID | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> DataExplorerPageResponse:
        rows = self._build_product_rows(organization_id)
        return self._page("products", "Products", rows, page=page, page_size=page_size)

    def build_visits_page(
        self,
        *,
        organization_id: UUID | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> DataExplorerPageResponse:
        rows = self._build_visit_rows(organization_id)
        return self._page("visits", "Visits", rows, page=page, page_size=page_size)

    def build_inventory_page(
        self,
        *,
        organization_id: UUID | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> DataExplorerPageResponse:
        rows = self._build_inventory_rows(organization_id)
        return self._page("inventory", "Inventory", rows, page=page, page_size=page_size)

    def build_payments_page(
        self,
        *,
        organization_id: UUID | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> DataExplorerPageResponse:
        rows = self._build_payment_rows(organization_id)
        return self._page("payments", "Payments", rows, page=page, page_size=page_size)

    def build_returns_page(
        self,
        *,
        organization_id: UUID | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> DataExplorerPageResponse:
        rows = self._build_return_rows(organization_id)
        return self._page("returns", "Returns", rows, page=page, page_size=page_size)

    def build_finance_page(
        self,
        *,
        organization_id: UUID | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> DataExplorerPageResponse:
        rows = self._build_finance_rows(organization_id)
        return self._page("finance", "Finance", rows, page=page, page_size=page_size)

    def build_references_page(
        self,
        *,
        organization_id: UUID | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> DataExplorerPageResponse:
        rows = self._build_reference_rows(organization_id)
        return self._page("references", "References", rows, page=page, page_size=page_size)

    def build_raw_page(
        self,
        *,
        organization_id: UUID | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> DataExplorerPageResponse:
        return DataExplorerService(self.store).build_page(
            DataExplorerCollection.SMARTUP_RAW,
            organization_id=organization_id,
            page=page,
            page_size=page_size,
        )

    def build_processing_page(
        self,
        *,
        organization_id: UUID | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> DataExplorerPageResponse:
        return DataExplorerService(self.store).build_page(
            DataExplorerCollection.PROCESSING,
            organization_id=organization_id,
            page=page,
            page_size=page_size,
        )

    def build_entity_trace(self, entity: str, entity_id: str) -> SmartUpTraceResponse:
        return self.verification.trace_entity(entity, entity_id)

    def _build_order_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        sales = sorted(
            self.store.list_sales_v2(organization_id=organization_id),
            key=lambda sale: sale.sale_at,
            reverse=True,
        )
        raw_sales = {
            record.external_id: record
            for record in self.store.list_smartup_raw_records(organization_id=organization_id)
            if record.entity_type == "sales" and record.external_id
        }
        customers = {
            customer.source_external_id: customer
            for customer in self.store.list_customers(organization_id=organization_id)
        }
        rows: list[dict[str, Any]] = []
        for sale in sales:
            raw = raw_sales.get(sale.source_external_id)
            raw_payload = raw.response_payload if raw else {}
            first_product = None
            if isinstance(raw_payload, dict):
                order_products = raw_payload.get("order_products")
                if isinstance(order_products, list) and order_products:
                    first_product = order_products[0]
            rows.append(
                {
                    "ttn": self._pick_text(raw_payload, "delivery_number", "invoice_number", "ttn"),
                    "deal_id": sale.source_external_id,
                    "customer": self._customer_label(sale, customers),
                    "organization": self._organization_names.get(
                        sale.organization_id, str(sale.organization_id)
                    ),
                    "staff": self._pick_text(
                        raw_payload, "sales_manager_name", "sales_manager_code", "person_name"
                    ),
                    "working_zone": self._pick_text(raw_payload, "room_name", "room_code"),
                    "payment_type": self._pick_text(raw_payload, "payment_type_code"),
                    "order_date": self._pick_text(raw_payload, "deal_time") or sale.sale_at,
                    "consignment_date": self._pick_text(raw_payload, "consignment_date"),
                    "delivery_date": self._pick_text(raw_payload, "delivery_date"),
                    "amount": sale.amount,
                    "currency": sale.currency,
                    "source_status": self._pick_text(raw_payload, "status"),
                    "normalized_status": sale.status,
                    "note": self._pick_text(raw_payload, "note"),
                    "items_count": self._sale_items_count(sale),
                    "first_item": first_product,
                },
            )
        return rows

    def _build_customer_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        customers = sorted(
            self.store.list_customers(organization_id=organization_id),
            key=lambda customer: customer.name.lower(),
        )
        sales = list(self.store.list_sales_v2(organization_id=organization_id))
        visits = list(self.store.list_visits(organization_id=organization_id))
        payments = list(self.store.list_payments(organization_id=organization_id))
        documents = list(self.store.list_business_documents(organization_id=organization_id))
        raw_customers = {
            record.external_id: record
            for record in self.store.list_smartup_raw_records(organization_id=organization_id)
            if record.entity_type == "customers" and record.external_id
        }
        rows: list[dict[str, Any]] = []
        for customer in customers:
            related_sales = [
                sale
                for sale in sales
                if sale.customer_id == customer.id
                or sale.customer_external_id == customer.source_external_id
            ]
            related_visits = [
                visit
                for visit in visits
                if visit.customer_id == customer.id
                or visit.customer_external_id == customer.source_external_id
            ]
            related_returns = [
                document
                for document in documents
                if document.counterparty_external_id == customer.source_external_id
            ]
            rows.append(
                {
                    "customer": customer.name,
                    "code": self._pick_text(
                        self._raw_payload(raw_customers.get(customer.source_external_id)),
                        "code",
                        "person_code",
                    )
                    or customer.source_external_id,
                    "type": self._pick_text(
                        self._raw_payload(raw_customers.get(customer.source_external_id)),
                        "type",
                        "person_type",
                    ),
                    "group": self._pick_text(
                        self._raw_payload(raw_customers.get(customer.source_external_id)),
                        "group",
                        "person_group",
                    ),
                    "phone": customer.phone,
                    "region": self._pick_text(
                        self._raw_payload(raw_customers.get(customer.source_external_id)), "region"
                    ),
                    "orders": len(related_sales),
                    "revenue": sum((sale.amount for sale in related_sales), Decimal("0")),
                    "average_check": self._average_amount(related_sales),
                    "returns": len(related_returns),
                    "last_purchase": max((sale.sale_at for sale in related_sales), default=None),
                    "visits": len(related_visits),
                    "payments": len(
                        [
                            payment
                            for payment in payments
                            if payment.sale_id in {sale.id for sale in related_sales}
                        ],
                    ),
                    "organization": self._organization_names.get(
                        customer.organization_id, str(customer.organization_id)
                    ),
                    "source_external_id": customer.source_external_id,
                },
            )
        return rows

    def _build_product_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        products = sorted(
            self.store.list_products(organization_id=organization_id),
            key=lambda product: product.name.lower(),
        )
        price_points = list(self.store.list_product_prices(organization_id=organization_id))
        balances = list(self.store.list_inventory_balances(organization_id=organization_id))
        sale_items = list(self.store.list_sale_items(organization_id=organization_id))
        sales = list(self.store.list_sales_v2(organization_id=organization_id))
        raw_products = {
            record.external_id: record
            for record in self.store.list_smartup_raw_records(organization_id=organization_id)
            if record.entity_type == "products" and record.external_id
        }
        rows: list[dict[str, Any]] = []
        for product in products:
            product_price = next(
                (
                    price
                    for price in price_points
                    if price.product_id == product.id
                    or price.product_external_id == product.source_external_id
                ),
                None,
            )
            related_items = [
                item
                for item in sale_items
                if item.product_id == product.id
                or item.product_external_id == product.source_external_id
            ]
            related_sales = [
                sale for sale in sales if any(item.sale_id == sale.id for item in related_items)
            ]
            related_balances = [
                balance
                for balance in balances
                if balance.product_id == product.id
                or balance.product_external_id == product.source_external_id
            ]
            raw_payload = self._raw_payload(raw_products.get(product.source_external_id))
            rows.append(
                {
                    "product": product.name,
                    "code": self._pick_text(raw_payload, "product_code", "inventory_code")
                    or product.source_external_id,
                    "category": product.category_external_id,
                    "producer": self._pick_text(raw_payload, "producer_code", "producer_name"),
                    "unit": product.unit,
                    "barcode": self._pick_text(raw_payload, "barcode", "inventory_barcode"),
                    "price": product_price.price if product_price else None,
                    "price_type": product_price.price_type_code if product_price else None,
                    "sold_units": sum((item.quantity for item in related_items), Decimal("0")),
                    "revenue": sum((item.amount for item in related_items), Decimal("0")),
                    "stock": sum((balance.quantity for balance in related_balances), Decimal("0")),
                    "last_sale": max((sale.sale_at for sale in related_sales), default=None),
                    "organization": self._organization_names.get(
                        product.organization_id, str(product.organization_id)
                    ),
                    "source_external_id": product.source_external_id,
                },
            )
        return rows

    def _build_visit_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        visits = sorted(
            self.store.list_visits(organization_id=organization_id),
            key=lambda visit: visit.visited_at,
            reverse=True,
        )
        raw_visits = {
            record.external_id: record
            for record in self.store.list_smartup_raw_records(organization_id=organization_id)
            if record.entity_type == "visits" and record.external_id
        }
        rows: list[dict[str, Any]] = []
        for visit in visits:
            raw_payload = self._raw_payload(raw_visits.get(visit.source_external_id))
            customer = self.store.get_customer(visit.customer_id) if visit.customer_id else None
            rows.append(
                {
                    "date_time": visit.visited_at,
                    "customer": customer.name if customer else visit.customer_external_id,
                    "working_zone": self._pick_text(raw_payload, "room_name", "room_code"),
                    "user_sales_rep": self._pick_text(
                        raw_payload, "user_name", "user_id", "sales_manager_code"
                    ),
                    "visit_type": self._pick_text(raw_payload, "visit_type"),
                    "status": visit.status or self._pick_text(raw_payload, "visit_status"),
                    "organization": self._organization_names.get(
                        visit.organization_id, str(visit.organization_id)
                    ),
                    "source_external_id": visit.source_external_id,
                },
            )
        return rows

    def _build_inventory_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        balances = sorted(
            self.store.list_inventory_balances(organization_id=organization_id),
            key=lambda balance: balance.balance_at,
            reverse=True,
        )
        raw_balances = {
            record.external_id: record
            for record in self.store.list_smartup_raw_records(organization_id=organization_id)
            if record.entity_type in {"inventory_balances", "balance"} and record.external_id
        }
        rows: list[dict[str, Any]] = []
        for balance in balances:
            raw_payload = self._raw_payload(raw_balances.get(balance.source_external_id))
            warehouse = (
                self.store.get_warehouse(balance.warehouse_id) if balance.warehouse_id else None
            )
            product = self.store.get_product(balance.product_id) if balance.product_id else None
            rows.append(
                {
                    "organization": self._organization_names.get(
                        balance.organization_id, str(balance.organization_id)
                    ),
                    "warehouse": warehouse.name if warehouse else balance.warehouse_external_id,
                    "product": product.name if product else balance.product_external_id,
                    "quantity": balance.quantity,
                    "input_price": self._pick_decimal(raw_payload, "input_price"),
                    "base_price": self._pick_decimal(raw_payload, "base_price", "price"),
                    "currency": self._pick_text(raw_payload, "currency_code", "currency"),
                    "snapshot_date": balance.balance_at,
                    "batch": self._pick_text(raw_payload, "batch_id", "external_id"),
                    "expiry": self._pick_text(raw_payload, "expiry_date"),
                    "source_external_id": balance.source_external_id,
                },
            )
        return rows

    def _build_payment_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        payments = sorted(
            self.store.list_payments(organization_id=organization_id),
            key=lambda payment: payment.paid_at,
            reverse=True,
        )
        raw_payments = {
            record.external_id: record
            for record in self.store.list_smartup_raw_records(organization_id=organization_id)
            if record.entity_type == "payments" and record.external_id
        }
        rows: list[dict[str, Any]] = []
        for payment in payments:
            raw_payload = self._raw_payload(raw_payments.get(payment.source_external_id))
            sale = self.store.get_sale_v2(payment.sale_id) if payment.sale_id else None
            customer = (
                self.store.get_customer(sale.customer_id) if sale and sale.customer_id else None
            )
            rows.append(
                {
                    "date": payment.paid_at,
                    "customer": customer.name if customer else None,
                    "sale": sale.sale_number if sale else payment.sale_external_id,
                    "payment_type": self._pick_text(
                        raw_payload, "payment_type_code", "payment_type"
                    ),
                    "cashbox_account": self._pick_text(
                        raw_payload, "cashbox_code", "bank_account_code", "account_code"
                    ),
                    "amount": payment.amount,
                    "currency": payment.currency,
                    "status": self._pick_text(raw_payload, "status"),
                    "reference": self._pick_text(raw_payload, "reference", "external_id"),
                    "organization": self._organization_names.get(
                        payment.organization_id, str(payment.organization_id)
                    ),
                    "source_external_id": payment.source_external_id,
                },
            )
        return rows

    def _build_return_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        documents = [
            document
            for document in self.store.list_business_documents(organization_id=organization_id)
            if document.document_type in {"return", "return_to_supplier"}
        ]
        raw_returns = {
            record.external_id: record
            for record in self.store.list_smartup_raw_records(organization_id=organization_id)
            if record.entity_type in {"returns", "return", "return_to_supplier"}
            and record.external_id
        }
        rows: list[dict[str, Any]] = []
        for document in sorted(documents, key=lambda doc: doc.document_at, reverse=True):
            raw_payload = self._raw_payload(raw_returns.get(document.source_external_id))
            items = [
                item
                for item in self.store.list_business_document_items(organization_id=organization_id)
                if item.document_id == document.id
            ]
            customer = self._find_customer_by_external_id(
                organization_id, document.counterparty_external_id
            )
            rows.append(
                {
                    "date": document.document_at,
                    "customer": customer.name if customer else document.counterparty_external_id,
                    "sale": self._pick_text(raw_payload, "deal_id", "sale_id"),
                    "product_count": len(
                        {item.product_external_id for item in items if item.product_external_id}
                    ),
                    "quantity": sum((item.quantity for item in items), Decimal("0")),
                    "amount": document.amount,
                    "currency": document.currency,
                    "reason": self._pick_text(raw_payload, "return_reason_code", "reason"),
                    "organization": self._organization_names.get(
                        document.organization_id, str(document.organization_id)
                    ),
                    "source_external_id": document.source_external_id,
                },
            )
        return rows

    def _build_finance_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        operations = sorted(
            self.store.list_bank_operations(organization_id=organization_id),
            key=lambda operation: operation.occurred_at,
            reverse=True,
        )
        rows: list[dict[str, Any]] = []
        for operation in operations:
            kind = (
                "cash"
                if str(operation.metadata.get("source_endpoint", "")).endswith(
                    "cash_operation$export"
                )
                else "bank"
            )
            rows.append(
                {
                    "kind": kind,
                    "date": operation.occurred_at,
                    "amount": operation.amount,
                    "currency": operation.currency,
                    "type": operation.operation_type,
                    "description": operation.description,
                    "endpoint": operation.metadata.get("source_endpoint"),
                    "reference": operation.source_external_id,
                    "organization": self._organization_names.get(
                        operation.organization_id, str(operation.organization_id)
                    ),
                },
            )
        return rows

    def _build_reference_rows(self, organization_id: UUID | None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for category in self.store.list_product_categories(organization_id=organization_id):
            rows.append(
                {
                    "kind": "category",
                    "code": category.source_external_id,
                    "name": category.name,
                    "parent": category.parent_external_id,
                },
            )
        for price_type in self.store.list_price_types(organization_id=organization_id):
            rows.append(
                {
                    "kind": "price_type",
                    "code": price_type.code,
                    "name": price_type.name,
                    "currency": price_type.currency_code,
                    "status": price_type.status,
                },
            )
        for price_point in self.store.list_product_prices(organization_id=organization_id):
            rows.append(
                {
                    "kind": "price_point",
                    "product": price_point.product_external_id,
                    "price_type": price_point.price_type_code,
                    "price": price_point.price,
                    "currency": price_point.currency_code,
                    "source_external_id": price_point.source_external_id,
                },
            )
        for warehouse in self.store.list_warehouses(organization_id=organization_id):
            rows.append(
                {
                    "kind": "warehouse",
                    "code": warehouse.code,
                    "name": warehouse.name,
                    "source_external_id": warehouse.source_external_id,
                },
            )
        for record in self.store.list_smartup_raw_records(organization_id=organization_id):
            if record.entity_type in {"return_reasons", "return_reason"}:
                rows.append(
                    {
                        "kind": "return_reason",
                        "code": record.external_id,
                        "name": self._pick_text(self._raw_payload(record), "name", "title"),
                        "source_external_id": record.external_id,
                    },
                )
        rows.sort(
            key=lambda item: (str(item.get("kind")), str(item.get("code") or item.get("name")))
        )
        return rows

    def _page(
        self,
        dataset: str,
        label: str,
        rows: list[dict[str, Any]],
        *,
        page: int,
        page_size: int,
    ) -> DataExplorerPageResponse:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        total = len(rows)
        total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
        start = (page - 1) * page_size
        end = start + page_size
        return DataExplorerPageResponse(
            dataset=dataset,
            label=label,
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            items=rows[start:end],
        )

    @staticmethod
    def _raw_payload(record: Any | None) -> dict[str, Any] | list[Any] | None:
        if record is None:
            return None
        return record.response_payload

    @staticmethod
    def _pick_text(payload: dict[str, Any] | list[Any] | None, *keys: str) -> str | None:
        if not isinstance(payload, dict):
            return None
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return str(value)
        return None

    @staticmethod
    def _pick_decimal(payload: dict[str, Any] | list[Any] | None, *keys: str) -> Decimal | None:
        if not isinstance(payload, dict):
            return None
        for key in keys:
            value = payload.get(key)
            if value in (None, ""):
                continue
            try:
                return Decimal(str(value))
            except Exception:  # pragma: no cover - defensive
                continue
        return None

    @staticmethod
    def _average_amount(sales: list[Sale]) -> Decimal | None:
        if not sales:
            return None
        total = sum((sale.amount for sale in sales), Decimal("0"))
        return total / Decimal(len(sales))

    def _sale_items_count(self, sale: Sale) -> int:
        return len(
            [
                item
                for item in self.store.list_sale_items(organization_id=sale.organization_id)
                if item.sale_id == sale.id or item.sale_external_id == sale.source_external_id
            ],
        )

    def _customer_label(
        self,
        sale: Sale,
        customers: dict[str, Customer],
    ) -> str | None:
        if sale.customer_external_id and sale.customer_external_id in customers:
            return customers[sale.customer_external_id].name
        if sale.customer_id:
            customer = self.store.get_customer(sale.customer_id)
            if customer is not None:
                return customer.name
        return sale.customer_external_id

    def _find_customer_by_external_id(
        self,
        organization_id: UUID | None,
        external_id: str | None,
    ) -> Customer | None:
        if external_id is None:
            return None
        for customer in self.store.list_customers(organization_id=organization_id):
            if customer.source_external_id == external_id:
                return customer
        return None
