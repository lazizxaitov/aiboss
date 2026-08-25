"""Core verification and trace helpers for SmartUp data."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.data_explorer import DataExplorerService
from app.core.data_layer.normalized import (
    BusinessDocument,
    BusinessDocumentItem,
    Customer,
    Payment,
    Product,
    Sale,
    Visit,
)
from app.integrations.smartup.models import (
    NormalizationIssue,
    SmartUpMigrationStatus,
    SmartUpRawRecord,
)


class SmartUpCoverageEntityReport(BaseModel):
    """Coverage row for one SmartUp entity family."""

    entity: str
    raw: int = 0
    core: int = 0
    linked: int = 0
    unresolved: int = 0
    coverage_percent: float = 0
    status: Literal[
        "full",
        "partial",
        "raw_only",
        "core_only",
        "permission_denied",
        "auth_restricted",
        "not_imported",
        "unresolved",
    ] = "not_imported"
    note: str | None = None


class SmartUpVerificationReport(BaseModel):
    """Aggregated SmartUp coverage report."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_system: str = "SmartUp"
    organization_id: UUID | None = None
    organization_name: str | None = None
    raw_total: int = 0
    core_total: int = 0
    linked_total: int = 0
    unresolved_total: int = 0
    coverage_percent: float = 0
    errors: int = 0
    permission_restricted: int = 0
    unresolved_references: int = 0
    entities: list[SmartUpCoverageEntityReport] = Field(default_factory=list)


class SmartUpTraceResponse(BaseModel):
    """Detailed trace payload for one SmartUp entity instance."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_system: str = "SmartUp"
    entity: str
    entity_id: str
    organization_id: UUID | None = None
    organization_name: str | None = None
    raw_summary: dict[str, Any] = Field(default_factory=dict)
    raw_record: dict[str, Any] | None = None
    normalized_entity: dict[str, Any] | None = None
    related_entities: list[dict[str, Any]] = Field(default_factory=list)
    source_mapping: dict[str, Any] = Field(default_factory=dict)
    processing_history: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class SmartUpVerificationService:
    """Build core verification and entity trace reports."""

    store: CoreDataStore
    _explorer: DataExplorerService = field(init=False, repr=False)
    _organization_names: dict[UUID, str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._explorer = DataExplorerService(self.store)
        self._organization_names = {
            organization.id: organization.name
            for organization in self.store.list_smartup_organizations()
        }

    def build_coverage_report(
        self, organization_id: UUID | None = None
    ) -> SmartUpVerificationReport:
        """Return the coverage report for the selected organizations."""

        entities = [
            self._coverage_customers(organization_id),
            self._coverage_products(organization_id),
            self._coverage_warehouses(organization_id),
            self._coverage_sales(organization_id),
            self._coverage_sale_items(organization_id),
            self._coverage_payments(organization_id),
            self._coverage_returns(organization_id),
            self._coverage_return_items(organization_id),
            self._coverage_visits(organization_id),
            self._coverage_inventory(organization_id),
            self._coverage_price_types(organization_id),
            self._coverage_price_points(organization_id),
            self._coverage_cash_operations(organization_id),
            self._coverage_bank_operations(organization_id),
            self._coverage_business_documents(organization_id),
        ]
        raw_total = sum(item.raw for item in entities)
        core_total = sum(item.core for item in entities)
        linked_total = sum(item.linked for item in entities)
        unresolved_total = sum(item.unresolved for item in entities)
        permission_restricted = sum(
            1 for item in entities if item.status in {"permission_denied", "auth_restricted"}
        )
        return SmartUpVerificationReport(
            organization_id=organization_id,
            organization_name=self._resolve_organization_name(organization_id),
            raw_total=raw_total,
            core_total=core_total,
            linked_total=linked_total,
            unresolved_total=unresolved_total,
            coverage_percent=self._coverage_percent(linked_total, core_total),
            errors=unresolved_total
            + self._count_failed_batches(organization_id=organization_id)
            + self._count_normalization_issues(organization_id=organization_id),
            permission_restricted=permission_restricted,
            unresolved_references=self._count_normalization_issues(organization_id=organization_id),
            entities=entities,
        )

    def trace_entity(self, entity: str, entity_id: str) -> SmartUpTraceResponse:
        """Return a detailed trace for one entity instance."""

        normalized_entity_type = self._normalize_entity_type(entity)
        raw_record = self._find_raw_record(normalized_entity_type, entity_id)
        normalized_entity = self._find_normalized_entity(normalized_entity_type, entity_id)
        organization_id = (
            raw_record.organization_id
            if raw_record is not None
            else normalized_entity.organization_id
            if normalized_entity is not None
            else None
        )
        raw_summary = self._build_raw_summary(normalized_entity_type, raw_record, entity_id)
        related_entities, warnings = self._build_related_entities(
            normalized_entity_type,
            organization_id,
            entity_id,
            raw_record,
            normalized_entity,
        )
        processing_history = self._build_processing_history(raw_record, organization_id)
        source_mapping = {
            "entity": normalized_entity_type,
            "requested_entity": entity,
            "entity_id": entity_id,
            "organization_id": str(organization_id) if organization_id else None,
            "organization_name": self._resolve_organization_name(organization_id),
            "raw_record_id": str(raw_record.id) if raw_record else None,
            "raw_external_id": raw_record.external_id if raw_record else None,
            "source_endpoint": raw_record.source_endpoint if raw_record else None,
            "normalized_id": str(normalized_entity.id) if normalized_entity else None,
            "normalized_source_external_id": (
                normalized_entity.source_external_id if normalized_entity else None
            ),
        }
        return SmartUpTraceResponse(
            entity=normalized_entity_type,
            entity_id=entity_id,
            organization_id=organization_id,
            organization_name=self._resolve_organization_name(organization_id),
            raw_summary=raw_summary,
            raw_record=self._model_dump(raw_record),
            normalized_entity=self._model_dump(normalized_entity),
            related_entities=related_entities,
            source_mapping=source_mapping,
            processing_history=processing_history,
            warnings=warnings,
        )

    def _coverage_customers(self, organization_id: UUID | None) -> SmartUpCoverageEntityReport:
        raw = self._count_raw_records(entity_types=("customers",), organization_id=organization_id)
        customers = list(self.store.list_customers(organization_id=organization_id))
        referenced_customer_ids = {
            sale.customer_id
            for sale in self.store.list_sales_v2(organization_id=organization_id)
            if sale.customer_id is not None
        }
        referenced_customer_ids.update(
            visit.customer_id
            for visit in self.store.list_visits(organization_id=organization_id)
            if visit.customer_id is not None
        )
        linked = sum(1 for customer in customers if customer.id in referenced_customer_ids)
        unresolved = max(len(customers) - linked, 0)
        return self._coverage_row(
            entity="customers",
            raw=raw,
            core=len(customers),
            linked=linked,
            unresolved=unresolved,
            note="RAW customers -> normalized customers -> sales/visits references",
            organization_id=organization_id,
        )

    def _coverage_products(self, organization_id: UUID | None) -> SmartUpCoverageEntityReport:
        raw = self._count_raw_records(
            entity_types=("products", "product", "inventory", "service"),
            organization_id=organization_id,
        )
        products = list(self.store.list_products(organization_id=organization_id))
        used_product_ids = {
            item.product_id
            for item in self.store.list_sale_items(organization_id=organization_id)
            if item.product_id is not None
        }
        used_product_ids.update(
            balance.product_id
            for balance in self.store.list_inventory_balances(organization_id=organization_id)
            if balance.product_id is not None
        )
        used_product_ids.update(
            price.product_id
            for price in self.store.list_product_prices(organization_id=organization_id)
            if price.product_id is not None
        )
        linked = sum(1 for product in products if product.id in used_product_ids)
        unresolved = max(len(products) - linked, 0)
        return self._coverage_row(
            entity="products",
            raw=raw,
            core=len(products),
            linked=linked,
            unresolved=unresolved,
            note="Products linked through sales, inventory and price points",
            organization_id=organization_id,
        )

    def _coverage_warehouses(self, organization_id: UUID | None) -> SmartUpCoverageEntityReport:
        raw = self._count_raw_records(
            entity_types=("warehouses", "rooms"), organization_id=organization_id
        )
        warehouses = list(self.store.list_warehouses(organization_id=organization_id))
        used_warehouse_ids = {
            balance.warehouse_id
            for balance in self.store.list_inventory_balances(organization_id=organization_id)
            if balance.warehouse_id is not None
        }
        warehouse_ids_by_external_id = {
            warehouse.source_external_id: warehouse.id for warehouse in warehouses
        }
        for document in self.store.list_business_documents(organization_id=organization_id):
            if document.warehouse_external_id is None:
                continue
            warehouse_id = warehouse_ids_by_external_id.get(document.warehouse_external_id)
            if warehouse_id is not None:
                used_warehouse_ids.add(warehouse_id)
        linked = sum(1 for warehouse in warehouses if warehouse.id in used_warehouse_ids)
        unresolved = max(len(warehouses) - linked, 0)
        return self._coverage_row(
            entity="warehouses",
            raw=raw,
            core=len(warehouses),
            linked=linked,
            unresolved=unresolved,
            note="Warehouses linked through inventory and documents",
            organization_id=organization_id,
        )

    def _coverage_sales(self, organization_id: UUID | None) -> SmartUpCoverageEntityReport:
        raw = self._count_raw_records(
            entity_types=("sales", "orders"), organization_id=organization_id
        )
        sales = list(self.store.list_sales_v2(organization_id=organization_id))
        sale_items_by_sale = defaultdict(int)
        for item in self.store.list_sale_items(organization_id=organization_id):
            if item.sale_id is not None:
                sale_items_by_sale[item.sale_id] += 1
        linked = sum(
            1
            for sale in sales
            if sale.customer_id is not None and sale_items_by_sale.get(sale.id, 0) > 0
        )
        unresolved = max(len(sales) - linked, 0)
        return self._coverage_row(
            entity="sales",
            raw=raw,
            core=len(sales),
            linked=linked,
            unresolved=unresolved,
            note="Sales linked to customers and sale items",
            organization_id=organization_id,
        )

    def _coverage_sale_items(self, organization_id: UUID | None) -> SmartUpCoverageEntityReport:
        raw = self._count_nested_raw_items(
            entity_types=("sales", "orders"),
            item_keys=("order_products", "products", "items", "details"),
            organization_id=organization_id,
        )
        sale_items = list(self.store.list_sale_items(organization_id=organization_id))
        linked = sum(
            1 for item in sale_items if item.sale_id is not None and item.product_id is not None
        )
        unresolved = max(len(sale_items) - linked, 0)
        return self._coverage_row(
            entity="sale_items",
            raw=raw,
            core=len(sale_items),
            linked=linked,
            unresolved=unresolved,
            note="Sale items linked to sale and product",
            organization_id=organization_id,
        )

    def _coverage_payments(self, organization_id: UUID | None) -> SmartUpCoverageEntityReport:
        raw = self._count_raw_records(
            entity_types=("payments", "cashins", "cashin"),
            organization_id=organization_id,
        )
        payments = list(self.store.list_payments(organization_id=organization_id))
        linked = sum(1 for payment in payments if payment.sale_id is not None)
        unresolved = max(len(payments) - linked, 0)
        return self._coverage_row(
            entity="payments",
            raw=raw,
            core=len(payments),
            linked=linked,
            unresolved=unresolved,
            note="Payments linked to sales when possible",
            organization_id=organization_id,
        )

    def _coverage_returns(self, organization_id: UUID | None) -> SmartUpCoverageEntityReport:
        raw = self._count_raw_records(
            entity_types=("returns", "return", "return_to_supplier"),
            organization_id=organization_id,
        )
        documents = self._return_documents(organization_id)
        linked = sum(
            1
            for document in documents
            if self._document_items_count(document.id, organization_id) > 0
        )
        unresolved = max(len(documents) - linked, 0)
        return self._coverage_row(
            entity="returns",
            raw=raw,
            core=len(documents),
            linked=linked,
            unresolved=unresolved,
            note="Return documents with child items",
            organization_id=organization_id,
        )

    def _coverage_return_items(self, organization_id: UUID | None) -> SmartUpCoverageEntityReport:
        raw = self._count_nested_raw_items(
            entity_types=("returns", "return", "return_to_supplier"),
            item_keys=("return_products", "order_products", "products", "items"),
            organization_id=organization_id,
        )
        items = self._return_items(organization_id)
        linked = sum(
            1 for item in items if item.document_id is not None and item.product_external_id
        )
        unresolved = max(len(items) - linked, 0)
        return self._coverage_row(
            entity="return_items",
            raw=raw,
            core=len(items),
            linked=linked,
            unresolved=unresolved,
            note="Return line items linked to documents and products",
            organization_id=organization_id,
        )

    def _coverage_visits(self, organization_id: UUID | None) -> SmartUpCoverageEntityReport:
        raw = self._count_raw_records(
            entity_types=("visits", "visit"), organization_id=organization_id
        )
        visits = list(self.store.list_visits(organization_id=organization_id))
        linked = sum(1 for visit in visits if visit.customer_id is not None)
        unresolved = max(len(visits) - linked, 0)
        return self._coverage_row(
            entity="visits",
            raw=raw,
            core=len(visits),
            linked=linked,
            unresolved=unresolved,
            note="Visits linked to customers",
            organization_id=organization_id,
        )

    def _coverage_inventory(self, organization_id: UUID | None) -> SmartUpCoverageEntityReport:
        raw = self._count_raw_records(
            entity_types=("inventory_balances", "balance", "inventories"),
            organization_id=organization_id,
        )
        balances = list(self.store.list_inventory_balances(organization_id=organization_id))
        linked = sum(
            1
            for balance in balances
            if balance.warehouse_id is not None and balance.product_id is not None
        )
        unresolved = max(len(balances) - linked, 0)
        return self._coverage_row(
            entity="inventory",
            raw=raw,
            core=len(balances),
            linked=linked,
            unresolved=unresolved,
            note="Inventory balances linked to warehouses and products",
            organization_id=organization_id,
        )

    def _coverage_price_types(self, organization_id: UUID | None) -> SmartUpCoverageEntityReport:
        raw = self._count_raw_records(
            entity_types=("price_types", "price_type"),
            organization_id=organization_id,
        )
        price_types = list(self.store.list_price_types(organization_id=organization_id))
        linked = sum(1 for price_type in price_types if price_type.code and price_type.name)
        unresolved = max(len(price_types) - linked, 0)
        return self._coverage_row(
            entity="price_types",
            raw=raw,
            core=len(price_types),
            linked=linked,
            unresolved=unresolved,
            note="Price types are reference data",
            organization_id=organization_id,
        )

    def _coverage_price_points(self, organization_id: UUID | None) -> SmartUpCoverageEntityReport:
        raw = self._count_raw_records(
            entity_types=("price_points", "product_prices"),
            organization_id=organization_id,
        )
        price_points = list(self.store.list_product_prices(organization_id=organization_id))
        linked = sum(
            1
            for price_point in price_points
            if price_point.product_id is not None and price_point.price_type_id is not None
        )
        unresolved = max(len(price_points) - linked, 0)
        return self._coverage_row(
            entity="price_points",
            raw=raw,
            core=len(price_points),
            linked=linked,
            unresolved=unresolved,
            note="Price points linked to products and price types",
            organization_id=organization_id,
        )

    def _coverage_cash_operations(
        self, organization_id: UUID | None
    ) -> SmartUpCoverageEntityReport:
        raw = self._count_raw_records_by_endpoint_suffixes(
            ("cash_operation$export",),
            organization_id=organization_id,
        )
        operations = [
            operation
            for operation in self.store.list_bank_operations(organization_id=organization_id)
            if getattr(operation, "operation_type", None) == "cash"
        ]
        linked = self._linked_operation_count(
            organization_id=organization_id,
            raw_suffix="cash_operation$export",
            normalized_operations=operations,
        )
        return self._coverage_row(
            entity="cash_operations",
            raw=raw,
            core=len(operations),
            linked=linked,
            unresolved=0 if linked else len(operations),
            note="Cash operations mirror bank operations core table",
            organization_id=organization_id,
        )

    def _coverage_bank_operations(
        self, organization_id: UUID | None
    ) -> SmartUpCoverageEntityReport:
        raw = self._count_raw_records_by_endpoint_suffixes(
            ("bank_operation$export",),
            organization_id=organization_id,
        )
        operations = [
            operation
            for operation in self.store.list_bank_operations(organization_id=organization_id)
            if getattr(operation, "operation_type", None) == "bank"
        ]
        linked = self._linked_operation_count(
            organization_id=organization_id,
            raw_suffix="bank_operation$export",
            normalized_operations=operations,
        )
        return self._coverage_row(
            entity="bank_operations",
            raw=raw,
            core=len(operations),
            linked=linked,
            unresolved=0 if linked else len(operations),
            note="Bank operations mirror the normalized bank operations table",
            organization_id=organization_id,
        )

    def _coverage_business_documents(
        self,
        organization_id: UUID | None,
    ) -> SmartUpCoverageEntityReport:
        raw = self._count_raw_records_by_endpoint_suffixes(
            (
                "purchase$export",
                "input$export",
                "movement$export",
                "stocktaking$export",
                "writeoff$export",
                "return$export",
            ),
            organization_id=organization_id,
        )
        documents = list(self.store.list_business_documents(organization_id=organization_id))
        linked = sum(
            1
            for document in documents
            if self._document_items_count(document.id, organization_id) > 0
        )
        unresolved = max(len(documents) - linked, 0)
        return self._coverage_row(
            entity="business_documents",
            raw=raw,
            core=len(documents),
            linked=linked,
            unresolved=unresolved,
            note="Business documents with at least one item",
            organization_id=organization_id,
        )

    def _build_raw_summary(
        self,
        entity_type: str,
        raw_record: SmartUpRawRecord | None,
        entity_id: str,
    ) -> dict[str, Any]:
        if raw_record is None:
            return {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "found": False,
            }
        payload = raw_record.response_payload
        if isinstance(payload, dict):
            top_level_keys = list(payload.keys())
        else:
            top_level_keys = []
        summary: dict[str, Any] = {
            "entity_type": raw_record.entity_type,
            "entity_id": entity_id,
            "raw_record_id": str(raw_record.id),
            "external_id": raw_record.external_id,
            "source_endpoint": raw_record.source_endpoint,
            "top_level_keys": top_level_keys,
            "processing_status": str(raw_record.processing_status),
            "processing_error": raw_record.processing_error,
            "imported_at": raw_record.imported_at,
            "batch_id": str(raw_record.batch_id) if raw_record.batch_id else None,
        }
        if entity_type == "sales":
            summary.update(self._build_sale_raw_summary(payload))
        elif entity_type == "customers":
            summary.update(self._build_customer_raw_summary(payload))
        elif entity_type == "visits":
            summary.update(self._build_visit_raw_summary(payload))
        elif entity_type == "products":
            summary.update(self._build_product_raw_summary(payload))
        elif entity_type == "payments":
            summary.update(self._build_payment_raw_summary(payload))
        return summary

    def _build_sale_raw_summary(self, payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        order_products = payload.get("order_products")
        first_order_product = (
            order_products[0] if isinstance(order_products, list) and order_products else None
        )
        details = None
        if isinstance(first_order_product, dict):
            details = first_order_product.get("details")
        return {
            "total_amount_raw": payload.get("total_amount"),
            "currency_code_raw": payload.get("currency_code"),
            "status_raw": payload.get("status"),
            "order_products_exists": isinstance(order_products, list),
            "order_products_type": type(order_products).__name__
            if order_products is not None
            else None,
            "order_products_count": len(order_products) if isinstance(order_products, list) else 0,
            "first_order_product_keys": list(first_order_product.keys())
            if isinstance(first_order_product, dict)
            else [],
            "first_order_product": first_order_product,
            "first_order_product_details_count": len(details) if isinstance(details, list) else 0,
            "first_order_product_has_sold_quant": any(
                isinstance(detail, dict) and detail.get("sold_quant") is not None
                for detail in details
            )
            if isinstance(details, list)
            else False,
        }

    def _build_customer_raw_summary(self, payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        return {
            "customer_type_raw": payload.get("type") or payload.get("person_type"),
            "customer_code_raw": payload.get("code") or payload.get("person_code"),
            "group_raw": payload.get("group") or payload.get("person_group"),
            "region_raw": payload.get("region"),
            "phone_raw": payload.get("phone"),
        }

    def _build_visit_raw_summary(self, payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        return {
            "visit_time_raw": payload.get("visit_date") or payload.get("visited_at"),
            "user_raw": payload.get("user_id") or payload.get("sales_manager_code"),
            "working_zone_raw": payload.get("room_code") or payload.get("working_zone_code"),
            "visit_status_raw": payload.get("visit_status") or payload.get("status"),
        }

    def _build_product_raw_summary(self, payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        return {
            "product_code_raw": payload.get("product_code") or payload.get("inventory_code"),
            "barcode_raw": payload.get("barcode") or payload.get("inventory_barcode"),
            "category_raw": payload.get("category_code") or payload.get("product_group_code"),
            "producer_raw": payload.get("producer_code"),
            "unit_raw": payload.get("unit"),
        }

    def _build_payment_raw_summary(self, payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        return {
            "payment_type_raw": payload.get("payment_type_code"),
            "cashbox_raw": payload.get("cashbox_code") or payload.get("bank_account_code"),
            "sale_external_id_raw": payload.get("sale_id") or payload.get("deal_id"),
            "currency_code_raw": payload.get("currency_code"),
        }

    def _build_related_entities(
        self,
        entity_type: str,
        organization_id: UUID | None,
        entity_id: str,
        raw_record: SmartUpRawRecord | None,
        normalized_entity: Any | None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        warnings: list[str] = []
        if organization_id is None:
            warnings.append("Organization could not be resolved for this trace.")
            return [], warnings
        if entity_type == "sales":
            return self._trace_sale_related_entities(
                organization_id, entity_id, raw_record, normalized_entity
            ), warnings
        if entity_type == "customers":
            return self._trace_customer_related_entities(
                organization_id, entity_id, raw_record, normalized_entity
            ), warnings
        if entity_type == "visits":
            return self._trace_visit_related_entities(
                organization_id, entity_id, raw_record, normalized_entity
            ), warnings
        if entity_type == "products":
            return self._trace_product_related_entities(
                organization_id, entity_id, raw_record, normalized_entity
            ), warnings
        if entity_type == "payments":
            return self._trace_payment_related_entities(
                organization_id, entity_id, raw_record, normalized_entity
            ), warnings
        return [], warnings

    def _trace_sale_related_entities(
        self,
        organization_id: UUID,
        entity_id: str,
        raw_record: SmartUpRawRecord | None,
        normalized_entity: Sale | None,
    ) -> list[dict[str, Any]]:
        sale = normalized_entity or self._find_sale(organization_id, entity_id)
        if sale is None:
            return []
        items = [
            item
            for item in self.store.list_sale_items(organization_id=organization_id)
            if item.sale_id == sale.id or item.sale_external_id == sale.source_external_id
        ]
        customer = self.store.get_customer(sale.customer_id) if sale.customer_id else None
        payments = [
            payment
            for payment in self.store.list_payments(organization_id=organization_id)
            if payment.sale_id == sale.id or payment.sale_external_id == sale.source_external_id
        ]
        related: list[dict[str, Any]] = []
        if customer is not None:
            related.append(
                self._related_row(
                    "customer", customer.id, customer.name, customer.source_external_id
                )
            )
        for item in items:
            related.append(
                self._related_row(
                    "sale_item",
                    item.id,
                    item.product_external_id or item.source_external_id,
                    item.source_external_id,
                ),
            )
        for payment in payments:
            related.append(
                self._related_row(
                    "payment",
                    payment.id,
                    payment.method or payment.source_external_id,
                    payment.source_external_id,
                ),
            )
        if raw_record is not None:
            related.append(
                {
                    "kind": "raw_record",
                    "id": str(raw_record.id),
                    "source_endpoint": raw_record.source_endpoint,
                    "external_id": raw_record.external_id,
                },
            )
        return related

    def _trace_customer_related_entities(
        self,
        organization_id: UUID,
        entity_id: str,
        raw_record: SmartUpRawRecord | None,
        normalized_entity: Customer | None,
    ) -> list[dict[str, Any]]:
        customer = normalized_entity or self._find_customer(organization_id, entity_id)
        if customer is None:
            return []
        sales = [
            sale
            for sale in self.store.list_sales_v2(organization_id=organization_id)
            if sale.customer_id == customer.id
            or sale.customer_external_id == customer.source_external_id
        ]
        visits = [
            visit
            for visit in self.store.list_visits(organization_id=organization_id)
            if visit.customer_id == customer.id
            or visit.customer_external_id == customer.source_external_id
        ]
        returns = [
            document
            for document in self._return_documents(organization_id)
            if document.counterparty_external_id == customer.source_external_id
        ]
        related = [
            self._related_row("customer", customer.id, customer.name, customer.source_external_id)
        ]
        for sale in sales:
            related.append(
                self._related_row(
                    "sale",
                    sale.id,
                    sale.sale_number or sale.source_external_id,
                    sale.source_external_id,
                )
            )
        for visit in visits:
            related.append(
                self._related_row(
                    "visit",
                    visit.id,
                    visit.status or visit.source_external_id,
                    visit.source_external_id,
                )
            )
        for document in returns:
            related.append(
                self._related_row(
                    "return",
                    document.id,
                    document.document_number or document.source_external_id,
                    document.source_external_id,
                ),
            )
        if raw_record is not None:
            related.append(
                {
                    "kind": "raw_record",
                    "id": str(raw_record.id),
                    "source_endpoint": raw_record.source_endpoint,
                    "external_id": raw_record.external_id,
                },
            )
        return related

    def _trace_visit_related_entities(
        self,
        organization_id: UUID,
        entity_id: str,
        raw_record: SmartUpRawRecord | None,
        normalized_entity: Visit | None,
    ) -> list[dict[str, Any]]:
        visit = normalized_entity or self._find_visit(organization_id, entity_id)
        if visit is None:
            return []
        customer = self.store.get_customer(visit.customer_id) if visit.customer_id else None
        related: list[dict[str, Any]] = []
        if customer is not None:
            related.append(
                self._related_row(
                    "customer", customer.id, customer.name, customer.source_external_id
                )
            )
        related.append(
            self._related_row(
                "visit",
                visit.id,
                visit.status or visit.source_external_id,
                visit.source_external_id,
            )
        )
        if raw_record is not None:
            related.append(
                {
                    "kind": "raw_record",
                    "id": str(raw_record.id),
                    "source_endpoint": raw_record.source_endpoint,
                    "external_id": raw_record.external_id,
                },
            )
        return related

    def _trace_product_related_entities(
        self,
        organization_id: UUID,
        entity_id: str,
        raw_record: SmartUpRawRecord | None,
        normalized_entity: Product | None,
    ) -> list[dict[str, Any]]:
        product = normalized_entity or self._find_product(organization_id, entity_id)
        if product is None:
            return []
        price_points = [
            price
            for price in self.store.list_product_prices(organization_id=organization_id)
            if price.product_id == product.id
            or price.product_external_id == product.source_external_id
        ]
        balances = [
            balance
            for balance in self.store.list_inventory_balances(organization_id=organization_id)
            if balance.product_id == product.id
            or balance.product_external_id == product.source_external_id
        ]
        sale_items = [
            item
            for item in self.store.list_sale_items(organization_id=organization_id)
            if item.product_id == product.id
            or item.product_external_id == product.source_external_id
        ]
        related = [
            self._related_row("product", product.id, product.name, product.source_external_id)
        ]
        for price in price_points:
            related.append(
                self._related_row(
                    "price_point",
                    price.id,
                    price.price_type_code or price.source_external_id,
                    price.source_external_id,
                )
            )
        for balance in balances:
            related.append(
                self._related_row(
                    "inventory_balance",
                    balance.id,
                    balance.warehouse_external_id,
                    balance.source_external_id,
                )
            )
        for item in sale_items:
            related.append(
                self._related_row(
                    "sale_item", item.id, item.sale_external_id, item.source_external_id
                )
            )
        if raw_record is not None:
            related.append(
                {
                    "kind": "raw_record",
                    "id": str(raw_record.id),
                    "source_endpoint": raw_record.source_endpoint,
                    "external_id": raw_record.external_id,
                },
            )
        return related

    def _trace_payment_related_entities(
        self,
        organization_id: UUID,
        entity_id: str,
        raw_record: SmartUpRawRecord | None,
        normalized_entity: Payment | None,
    ) -> list[dict[str, Any]]:
        payment = normalized_entity or self._find_payment(organization_id, entity_id)
        if payment is None:
            return []
        sale = self.store.get_sale_v2(payment.sale_id) if payment.sale_id else None
        related: list[dict[str, Any]] = []
        if sale is not None:
            related.append(
                self._related_row(
                    "sale",
                    sale.id,
                    sale.sale_number or sale.source_external_id,
                    sale.source_external_id,
                )
            )
            if sale.customer_id:
                customer = self.store.get_customer(sale.customer_id)
                if customer is not None:
                    related.append(
                        self._related_row(
                            "customer", customer.id, customer.name, customer.source_external_id
                        )
                    )
        related.append(
            self._related_row(
                "payment",
                payment.id,
                payment.method or payment.source_external_id,
                payment.source_external_id,
            )
        )
        if raw_record is not None:
            related.append(
                {
                    "kind": "raw_record",
                    "id": str(raw_record.id),
                    "source_endpoint": raw_record.source_endpoint,
                    "external_id": raw_record.external_id,
                },
            )
        return related

    def _build_processing_history(
        self,
        raw_record: SmartUpRawRecord | None,
        organization_id: UUID | None,
    ) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        if raw_record is not None:
            history.append(
                {
                    "kind": "raw_record",
                    "status": str(raw_record.processing_status),
                    "processing_error": raw_record.processing_error,
                    "imported_at": raw_record.imported_at,
                },
            )
            issues = list(self.store.list_normalization_issues(raw_record_id=raw_record.id))
            for issue in issues:
                history.append(self._issue_row(issue))
        if organization_id is not None and raw_record is None:
            issues = list(self.store.list_normalization_issues(organization_id=organization_id))
            for issue in issues[:10]:
                history.append(self._issue_row(issue))
        return history

    @staticmethod
    def _issue_row(issue: NormalizationIssue) -> dict[str, Any]:
        return {
            "kind": "normalization_issue",
            "id": str(issue.id),
            "issue_type": issue.issue_type,
            "field_name": issue.field_name,
            "message": issue.message,
            "severity": str(issue.severity),
            "created_at": issue.created_at,
            "raw_record_id": str(issue.raw_record_id),
        }

    @staticmethod
    def _related_row(
        kind: str, entity_id: UUID, label: str | None, source_external_id: str | None
    ) -> dict[str, Any]:
        return {
            "kind": kind,
            "id": str(entity_id),
            "label": label,
            "source_external_id": source_external_id,
        }

    def _coverage_row(
        self,
        *,
        entity: str,
        raw: int,
        core: int,
        linked: int,
        unresolved: int,
        note: str | None,
        organization_id: UUID | None,
    ) -> SmartUpCoverageEntityReport:
        status = self._coverage_status(
            entity=entity,
            raw=raw,
            core=core,
            linked=linked,
            unresolved=unresolved,
            organization_id=organization_id,
        )
        return SmartUpCoverageEntityReport(
            entity=entity,
            raw=raw,
            core=core,
            linked=linked,
            unresolved=max(unresolved, 0),
            coverage_percent=self._coverage_percent(linked, core),
            status=status,
            note=note,
        )

    def _coverage_status(
        self,
        *,
        entity: str,
        raw: int,
        core: int,
        linked: int,
        unresolved: int,
        organization_id: UUID | None,
    ) -> Literal[
        "full",
        "partial",
        "raw_only",
        "core_only",
        "permission_denied",
        "auth_restricted",
        "not_imported",
        "unresolved",
    ]:
        if self._has_permission_restricted_batches(entity, organization_id):
            return "permission_denied"
        if raw == 0 and core == 0:
            return "not_imported"
        if raw > 0 and core == 0:
            return "raw_only"
        if core > 0 and raw == 0:
            return "core_only"
        if unresolved > 0 and linked > 0:
            return "partial"
        if unresolved > 0:
            return "unresolved"
        return "full"

    @staticmethod
    def _coverage_percent(linked: int, core: int) -> float:
        if core <= 0:
            return 0
        return round((linked / core) * 100, 2)

    def _count_raw_records(
        self,
        *,
        entity_types: tuple[str, ...],
        organization_id: UUID | None,
    ) -> int:
        records = list(self.store.list_smartup_raw_records(organization_id=organization_id))
        return sum(1 for record in records if record.entity_type in entity_types)

    def _count_raw_records_by_endpoint_suffixes(
        self,
        suffixes: tuple[str, ...],
        *,
        organization_id: UUID | None,
    ) -> int:
        records = list(self.store.list_smartup_raw_records(organization_id=organization_id))
        return sum(
            1
            for record in records
            if any(str(record.source_endpoint).endswith(suffix) for suffix in suffixes)
        )

    def _count_nested_raw_items(
        self,
        *,
        entity_types: tuple[str, ...],
        item_keys: tuple[str, ...],
        organization_id: UUID | None,
    ) -> int:
        records = list(self.store.list_smartup_raw_records(organization_id=organization_id))
        total = 0
        for record in records:
            if record.entity_type not in entity_types:
                continue
            payload = record.response_payload
            if isinstance(payload, dict):
                for key in item_keys:
                    value = payload.get(key)
                    if isinstance(value, list):
                        total += len([row for row in value if isinstance(row, dict)])
                        break
                else:
                    total += 1
            elif isinstance(payload, list):
                total += len([row for row in payload if isinstance(row, dict)])
        return total

    def _count_failed_batches(self, organization_id: UUID | None) -> int:
        batches = list(self.store.list_migration_batches(organization_id=organization_id))
        return sum(
            1 for batch in batches if str(batch.status) == SmartUpMigrationStatus.FAILED.value
        )

    def _count_normalization_issues(self, organization_id: UUID | None) -> int:
        return len(list(self.store.list_normalization_issues(organization_id=organization_id)))

    def _has_permission_restricted_batches(self, entity: str, organization_id: UUID | None) -> bool:
        for batch in self.store.list_migration_batches(organization_id=organization_id):
            if batch.entity_type != entity:
                continue
            if str(batch.status) == SmartUpMigrationStatus.PERMISSION_DENIED.value:
                return True
            if batch.upstream_status in {401, 403}:
                return True
        return False

    def _return_documents(self, organization_id: UUID | None) -> list[BusinessDocument]:
        return [
            document
            for document in self.store.list_business_documents(organization_id=organization_id)
            if document.document_type in {"return", "return_to_supplier"}
        ]

    def _return_items(self, organization_id: UUID | None) -> list[BusinessDocumentItem]:
        documents = self._return_documents(organization_id)
        document_ids = {document.id for document in documents}
        return [
            item
            for item in self.store.list_business_document_items(organization_id=organization_id)
            if item.document_id in document_ids
        ]

    def _document_items_count(self, document_id: UUID, organization_id: UUID | None) -> int:
        return len(
            [
                item
                for item in self.store.list_business_document_items(organization_id=organization_id)
                if item.document_id == document_id
            ]
        )

    def _linked_operation_count(
        self,
        *,
        organization_id: UUID | None,
        raw_suffix: str,
        normalized_operations: list[Any],
    ) -> int:
        raw_external_ids = {
            record.external_id
            for record in self.store.list_smartup_raw_records(organization_id=organization_id)
            if record.external_id and str(record.source_endpoint).endswith(raw_suffix)
        }
        if not raw_external_ids:
            return len(normalized_operations)
        return sum(
            1
            for operation in normalized_operations
            if getattr(operation, "source_external_id", None) in raw_external_ids
        )

    def _find_raw_record(self, entity_type: str, entity_id: str) -> SmartUpRawRecord | None:
        try:
            raw_uuid = UUID(entity_id)
        except ValueError:
            raw_uuid = None
        if raw_uuid is not None:
            record = self.store.get_smartup_raw_record(raw_uuid)
            if record is not None and record.entity_type == entity_type:
                return record
        for record in self.store.list_smartup_raw_records():
            if record.entity_type != entity_type:
                continue
            if record.external_id == entity_id:
                return record
            if self._raw_payload_matches(record.response_payload, entity_id):
                return record
        return None

    def _find_normalized_entity(self, entity_type: str, entity_id: str) -> Any | None:
        getter, lister = self._normalized_accessors(entity_type)
        if getter is None or lister is None:
            return None
        try:
            entity_uuid = UUID(entity_id)
        except ValueError:
            entity_uuid = None
        if entity_uuid is not None:
            entity = getter(entity_uuid)
            if entity is not None:
                return entity
        for item in lister():
            if getattr(item, "source_external_id", None) == entity_id:
                return item
            if getattr(item, "sale_number", None) == entity_id:
                return item
            if getattr(item, "document_number", None) == entity_id:
                return item
            if getattr(item, "name", None) == entity_id:
                return item
        return None

    def _find_sale(self, organization_id: UUID, entity_id: str) -> Sale | None:
        sale = self._find_normalized_entity("sales", entity_id)
        if isinstance(sale, Sale):
            return sale
        return None

    def _find_customer(self, organization_id: UUID, entity_id: str) -> Customer | None:
        customer = self._find_normalized_entity("customers", entity_id)
        if isinstance(customer, Customer):
            return customer
        return None

    def _find_product(self, organization_id: UUID, entity_id: str) -> Product | None:
        product = self._find_normalized_entity("products", entity_id)
        if isinstance(product, Product):
            return product
        return None

    def _find_visit(self, organization_id: UUID, entity_id: str) -> Visit | None:
        visit = self._find_normalized_entity("visits", entity_id)
        if isinstance(visit, Visit):
            return visit
        return None

    def _find_payment(self, organization_id: UUID, entity_id: str) -> Payment | None:
        payment = self._find_normalized_entity("payments", entity_id)
        if isinstance(payment, Payment):
            return payment
        return None

    def _normalized_accessors(
        self,
        entity_type: str,
    ) -> tuple[
        Callable[[UUID], Any | None] | None,
        Callable[[], list[Any]] | None,
    ]:
        lookup = {
            "customers": (self.store.get_customer, self.store.list_customers),
            "products": (self.store.get_product, self.store.list_products),
            "warehouses": (self.store.get_warehouse, self.store.list_warehouses),
            "price_types": (self.store.get_price_type, self.store.list_price_types),
            "product_prices": (self.store.get_product_price, self.store.list_product_prices),
            "sales": (self.store.get_sale_v2, self.store.list_sales_v2),
            "sale_items": (self.store.get_sale_item, self.store.list_sale_items),
            "payments": (self.store.get_payment, self.store.list_payments),
            "inventory_balances": (
                self.store.get_inventory_balance,
                self.store.list_inventory_balances,
            ),
            "visits": (self.store.get_visit, self.store.list_visits),
            "bank_operations": (self.store.get_bank_operation, self.store.list_bank_operations),
            "business_documents": (
                self.store.get_business_document,
                self.store.list_business_documents,
            ),
            "business_document_items": (
                self.store.get_business_document_item,
                self.store.list_business_document_items,
            ),
        }.get(entity_type)
        if lookup is None:
            return None, None
        return lookup

    def _raw_payload_matches(self, payload: dict[str, Any] | list[Any], entity_id: str) -> bool:
        if isinstance(payload, dict):
            candidate_keys = (
                "deal_id",
                "order_id",
                "customer_id",
                "person_id",
                "product_id",
                "visit_id",
                "payment_id",
                "operation_id",
                "document_id",
                "return_reason_id",
                "external_id",
                "id",
            )
            for key in candidate_keys:
                if str(payload.get(key)) == entity_id:
                    return True
            for value in payload.values():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and self._raw_payload_matches(item, entity_id):
                            return True
        elif isinstance(payload, list):
            return any(
                isinstance(item, dict) and self._raw_payload_matches(item, entity_id)
                for item in payload
            )
        return False

    @staticmethod
    def _model_dump(value: Any | None) -> dict[str, Any] | None:
        if value is None:
            return None
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return value
        return None

    @staticmethod
    def _normalize_entity_type(entity: str) -> str:
        alias_map = {
            "sale": "sales",
            "order": "sales",
            "customer": "customers",
            "visit": "visits",
            "product": "products",
            "payment": "payments",
            "inventory": "inventory_balances",
            "price_type": "price_types",
            "price_point": "product_prices",
            "return": "business_documents",
            "return_item": "business_document_items",
            "cash_operation": "bank_operations",
            "bank_operation": "bank_operations",
            "business_document": "business_documents",
            "business_document_item": "business_document_items",
        }
        return alias_map.get(entity, entity)

    def _resolve_organization_name(self, organization_id: UUID | None) -> str | None:
        if organization_id is None:
            return None
        organization_name = self._organization_names.get(organization_id)
        if organization_name is not None:
            return organization_name
        organization_id_text = str(organization_id)
        for stored_id, stored_name in self._organization_names.items():
            if str(stored_id) == organization_id_text:
                return stored_name
        return None
