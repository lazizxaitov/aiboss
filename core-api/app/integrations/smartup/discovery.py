"""SmartUp discovery and mapping matrix helpers.

Stage 3A treats SmartUp as a source system, not a user-facing mirror UI.
This module builds the discovery report that maps SmartUp source fields into
the primary AI Business OS business modules, pages, analytics, and AI use
cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.normalized import (
    BusinessDocument,
    Customer,
    InventoryBalance,
    Payment,
    PriceType,
    Product,
    ProductPrice,
    Sale,
    Visit,
    Warehouse,
)
from app.integrations.smartup.mapping import SMARTUP_CORE_MAPPING_V1, SmartUpMapping


class SmartUpDiscoveryFieldRow(BaseModel):
    """One SmartUp field mapped into the AI Business OS."""

    source_entity: str
    source_field: str
    target_field: str
    target_table: str
    core_domain: str
    business_module: str
    page: str
    component: str
    analytics_use: str
    ai_use: str
    smartup_endpoint: str
    smartup_method: str
    smartup_object: str
    sync_mode: str


class SmartUpDiscoveryEntitySummary(BaseModel):
    """Discovery summary for one SmartUp entity family."""

    source_entity: str
    target_table: str
    target_entity: str
    core_domain: str
    business_module: str
    page: str
    component: str
    analytics_use: str
    ai_use: str
    smartup_endpoint: str
    smartup_method: str
    smartup_object: str
    sync_mode: str
    key_fields: list[str] = Field(default_factory=list)
    field_count: int = 0
    fields: list[SmartUpDiscoveryFieldRow] = Field(default_factory=list)


class SmartUpDiscoveryOrganizationDifference(BaseModel):
    """Data-driven capability differences between SmartUp organizations."""

    organization_id: UUID
    organization_name: str
    filial_id: str | None = None
    raw_entity_types: list[str] = Field(default_factory=list)
    raw_endpoints: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SmartUpDiscoveryReport(BaseModel):
    """Full SmartUp discovery report."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_system: str = "SmartUp"
    organizations_count: int = 0
    entities_count: int = 0
    fields_count: int = 0
    modules_count: int = 0
    pages_count: int = 0
    entities: list[SmartUpDiscoveryEntitySummary] = Field(default_factory=list)
    matrix: list[SmartUpDiscoveryFieldRow] = Field(default_factory=list)
    organization_differences: list[SmartUpDiscoveryOrganizationDifference] = Field(
        default_factory=list,
    )
    missing_core_entities: list[str] = Field(default_factory=list)
    missing_core_fields: list[str] = Field(default_factory=list)
    missing_relationships: list[str] = Field(default_factory=list)
    missing_business_os_pages: list[str] = Field(default_factory=list)
    missing_analytics: list[str] = Field(default_factory=list)
    missing_dashboard_kpis: list[str] = Field(default_factory=list)
    missing_drill_down_paths: list[str] = Field(default_factory=list)
    missing_ai_opportunities: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class SmartUpDiscoveryService:
    """Build the SmartUp discovery report and mapping matrix."""

    store: CoreDataStore

    def build_report(self, organization_id: UUID | None = None) -> SmartUpDiscoveryReport:
        mappings = self._mappings()
        entities = [self._build_entity_summary(mapping) for mapping in mappings]
        matrix = [row for mapping in mappings for row in self._build_matrix_rows(mapping)]
        organization_differences = self._build_organization_differences(organization_id)
        missing_core_entities = self._missing_core_entities()
        missing_core_fields = self._missing_core_fields()
        missing_relationships = self._missing_relationships()
        missing_business_os_pages = self._missing_business_os_pages()
        missing_analytics = self._missing_analytics()
        missing_dashboard_kpis = self._missing_dashboard_kpis()
        missing_drill_down_paths = self._missing_drill_down_paths()
        missing_ai_opportunities = self._missing_ai_opportunities()
        return SmartUpDiscoveryReport(
            organizations_count=len(organization_differences),
            entities_count=len(entities),
            fields_count=len(matrix),
            modules_count=len({entity.business_module for entity in entities}),
            pages_count=len({entity.page for entity in entities}),
            entities=entities,
            matrix=matrix,
            organization_differences=organization_differences,
            missing_core_entities=missing_core_entities,
            missing_core_fields=missing_core_fields,
            missing_relationships=missing_relationships,
            missing_business_os_pages=missing_business_os_pages,
            missing_analytics=missing_analytics,
            missing_dashboard_kpis=missing_dashboard_kpis,
            missing_drill_down_paths=missing_drill_down_paths,
            missing_ai_opportunities=missing_ai_opportunities,
        )

    def _build_entity_summary(self, mapping: SmartUpMapping) -> SmartUpDiscoveryEntitySummary:
        fields = list(mapping.field_mappings)
        summary_fields = [
            self._build_field_row(mapping, field.source_field, field.target_field)
            for field in fields
        ]
        return SmartUpDiscoveryEntitySummary(
            source_entity=mapping.name,
            target_table=mapping.target_table,
            target_entity=mapping.target_entity,
            core_domain=self._core_domain(mapping),
            business_module=self._business_module(mapping),
            page=self._page_name(mapping),
            component=self._component_name(mapping),
            analytics_use=self._analytics_use(mapping),
            ai_use=self._ai_use(mapping),
            smartup_endpoint=mapping.smartup_endpoint,
            smartup_method=mapping.smartup_method,
            smartup_object=mapping.smartup_object,
            sync_mode=mapping.sync_mode,
            key_fields=list(mapping.key_fields),
            field_count=len(fields),
            fields=summary_fields,
        )

    def _build_matrix_rows(self, mapping: SmartUpMapping) -> list[SmartUpDiscoveryFieldRow]:
        if not mapping.field_mappings:
            return [
                self._build_field_row(
                    mapping,
                    source_field="(no explicit field map)",
                    target_field="(mapping-level)",
                ),
            ]
        return [
            self._build_field_row(mapping, field.source_field, field.target_field)
            for field in mapping.field_mappings
        ]

    def _build_field_row(
        self,
        mapping: SmartUpMapping,
        source_field: str,
        target_field: str,
    ) -> SmartUpDiscoveryFieldRow:
        return SmartUpDiscoveryFieldRow(
            source_entity=mapping.name,
            source_field=source_field,
            target_field=target_field,
            target_table=mapping.target_table,
            core_domain=self._core_domain(mapping),
            business_module=self._business_module(mapping),
            page=self._page_name(mapping),
            component=self._component_name(
                mapping, source_field=source_field, target_field=target_field
            ),
            analytics_use=self._analytics_use(
                mapping, source_field=source_field, target_field=target_field
            ),
            ai_use=self._ai_use(mapping, source_field=source_field, target_field=target_field),
            smartup_endpoint=mapping.smartup_endpoint,
            smartup_method=mapping.smartup_method,
            smartup_object=mapping.smartup_object,
            sync_mode=mapping.sync_mode,
        )

    def _build_organization_differences(
        self,
        organization_id: UUID | None,
    ) -> list[SmartUpDiscoveryOrganizationDifference]:
        organizations = list(self.store.list_smartup_organizations())
        if organization_id is not None:
            organizations = [
                organization for organization in organizations if organization.id == organization_id
            ]
        differences: list[SmartUpDiscoveryOrganizationDifference] = []
        for organization in organizations:
            raw_records = list(self.store.list_smartup_raw_records(organization_id=organization.id))
            raw_entity_types = sorted(
                {record.entity_type for record in raw_records if record.entity_type}
            )
            raw_endpoints = sorted(
                {record.source_endpoint for record in raw_records if record.source_endpoint}
            )
            capabilities = self._capabilities_for_raw_records(raw_records)
            notes = [
                "Capability set is data-driven and depends on the imported raw records.",
                "Organizations with no raw records will not expose module-specific drill-downs.",
            ]
            differences.append(
                SmartUpDiscoveryOrganizationDifference(
                    organization_id=organization.id,
                    organization_name=organization.name,
                    filial_id=organization.filial_id,
                    raw_entity_types=raw_entity_types,
                    raw_endpoints=raw_endpoints,
                    capabilities=capabilities,
                    notes=notes,
                ),
            )
        return differences

    def _capabilities_for_raw_records(self, raw_records: list[Any]) -> list[str]:
        capabilities: set[str] = set()
        for record in raw_records:
            entity_type = str(getattr(record, "entity_type", "")).strip().lower()
            endpoint = str(getattr(record, "source_endpoint", "")).strip().lower()
            payload = getattr(record, "response_payload", None)
            payload_text = str(payload).lower() if payload is not None else ""
            if entity_type in {"sales", "sales_returns"} or "order$export" in endpoint:
                capabilities.add("Sales drill-down")
            if entity_type in {"customers"} or "person" in endpoint:
                capabilities.add("Customer 360")
            if entity_type in {"products", "inventory_balances"} or "inventory" in endpoint:
                capabilities.add("Product and stock analytics")
            if entity_type in {"visits"} or "visit$export" in endpoint:
                capabilities.add("Field Sales")
            if entity_type in {"payments", "cash_operations", "bank_operations"}:
                capabilities.add("Finance")
            if "photo" in endpoint or any(
                token in payload_text for token in ("photo", "sha", "visit_photo")
            ):
                capabilities.add("Photo Reports")
            if "room" in endpoint or any(
                token in payload_text for token in ("working_zone", "room_code")
            ):
                capabilities.add("Working Zones")
        return sorted(capabilities)

    def _missing_core_entities(self) -> list[str]:
        discovered = {mapping.target_table for mapping in self._mappings()}
        represented = self._represented_core_entities()
        missing = sorted(discovered - represented)
        return missing

    def _missing_core_fields(self) -> list[str]:
        direct_core_fields = self._direct_core_fields()
        missing: set[str] = set()
        for mapping in self._mappings():
            for field in mapping.field_mappings:
                if field.target_field.startswith("metadata."):
                    missing.add(f"{mapping.name}.{field.source_field} -> metadata")
                    continue
                target_field = field.target_field.split(".")[0]
                if target_field not in direct_core_fields.get(mapping.target_table, set()):
                    missing.add(f"{mapping.name}.{field.source_field} -> {field.target_field}")
        return sorted(missing)

    def _missing_relationships(self) -> list[str]:
        return [
            "Revenue -> Organization -> Sales Rep -> Customer -> Order -> Order Items -> Product",
            "Sales -> Payments -> Receivables",
            "Sales -> Returns -> Return Reasons",
            "Sales -> Visits -> Working Zones -> Photo Reports",
            "Inventory -> Warehouse -> Product -> Batch -> Expiry Date",
            "Finance -> Cash -> Bank -> Expenses -> Cash Flow",
            "Product -> Price Types -> Price Points -> Revenue",
            "Customer -> Orders -> Returns -> Visit Timeline",
            "Equipment -> Organization -> Warehouse -> Movement -> Request",
        ]

    def _missing_business_os_pages(self) -> list[str]:
        return [
            "Dashboard",
            "Sales Overview",
            "Sales Orders",
            "Order Detail",
            "Order Items",
            "Customers",
            "Customer 360",
            "Products",
            "Product 360",
            "Inventory",
            "Finance",
            "Field Sales",
            "Photo Reports",
            "Assets",
            "References",
            "Raw Explorer (admin debug)",
            "Processing (admin debug)",
            "Coverage",
        ]

    def _missing_analytics(self) -> list[str]:
        return [
            "Revenue by organization, sales rep, customer, product, and working zone",
            "Customer segmentation: new, returning, inactive, lost",
            "Product velocity: top products, slow movers, stock pressure",
            "Visit conversion and route efficiency",
            "Inventory aging, batch expiry, low stock alerts",
            "Payment delays and receivable aging",
            "Return reasons and return impact",
            "Asset utilization and movement trends",
        ]

    def _missing_dashboard_kpis(self) -> list[str]:
        return [
            "Revenue",
            "Orders",
            "Sold Units",
            "Average Order",
            "Payments Received",
            "Outstanding Receivables",
            "Returns",
            "Expenses",
            "Cash Flow",
            "Inventory Value",
            "Low Stock",
            "Top Products",
            "Slow Products",
            "Top Customers",
            "Lost Customers",
            "Top Sales Reps",
            "Visits",
            "Visit Conversion",
            "Organizations comparison",
            "Anomalies",
            "AI Recommendations",
        ]

    def _missing_drill_down_paths(self) -> list[str]:
        return [
            "Revenue -> Organization -> Sales Rep -> Customer -> Order -> Order Items -> Product",
            "Customer KPI -> Customer 360 -> Orders -> Returns -> Payments -> Visits",
            "Product KPI -> Product 360 -> Prices -> Stock -> Returns -> Customers",
            "Inventory KPI -> Organization -> Warehouse -> Product -> Batch -> Expiry",
            "Visit KPI -> Sales Rep -> Working Zone -> Route -> Photo Report",
            "Finance KPI -> Payment -> Cash -> Bank -> Receivable -> Expense",
        ]

    def _missing_ai_opportunities(self) -> list[str]:
        return [
            "Revenue forecasting by organization, sales rep, customer, product, and zone",
            "Anomaly detection for orders, returns, and payments",
            "Customer churn and reactivation recommendations",
            "Product recommendation and demand forecasting",
            "Route optimization for field sales reps",
            "Photo report analysis for merchandising compliance",
            "Stockout and overstock risk prediction",
            "Cash flow and receivables forecasting",
        ]

    def _represented_core_entities(self) -> set[str]:
        return {
            "contacts",
            "products",
            "product_groups",
            "price_types",
            "price_points",
            "producers",
            "contracts",
            "workspaces",
            "services",
            "person_groups",
            "sales",
            "sales_returns",
            "return_reasons",
            "payments",
            "finance_entries",
            "logistics",
            "cross_organizational_movements",
            "internal_movements",
            "stocktakings",
            "write_offs",
            "supplier_returns",
            "warehouse_receipts",
            "purchases",
            "inventory_balances",
            "equipment_assets",
            "equipment_movements",
            "equipment_requests",
            "field_visits",
        }

    def _direct_core_fields(self) -> dict[str, set[str]]:
        return {
            "contacts": set(Customer.model_fields),
            "products": set(Product.model_fields),
            "product_groups": {
                "id",
                "organization_id",
                "source_system",
                "source_external_id",
                "name",
                "parent_external_id",
            },
            "warehouses": set(Warehouse.model_fields),
            "price_types": set(PriceType.model_fields),
            "price_points": set(ProductPrice.model_fields),
            "producers": {
                "id",
                "organization_id",
                "source_system",
                "source_external_id",
                "name",
                "display_name",
                "metadata",
            },
            "contracts": {
                "id",
                "organization_id",
                "source_system",
                "source_external_id",
                "metadata",
            },
            "workspaces": {
                "id",
                "organization_id",
                "source_system",
                "source_external_id",
                "name",
                "metadata",
            },
            "services": {
                "id",
                "organization_id",
                "source_system",
                "source_external_id",
                "name",
                "metadata",
            },
            "person_groups": {
                "id",
                "organization_id",
                "source_system",
                "source_external_id",
                "name",
                "metadata",
            },
            "sales": set(Sale.model_fields),
            "sales_returns": set(BusinessDocument.model_fields),
            "return_reasons": {
                "id",
                "organization_id",
                "source_system",
                "source_external_id",
                "code",
                "name",
                "metadata",
            },
            "payments": set(Payment.model_fields),
            "finance_entries": {
                "id",
                "organization_id",
                "source_system",
                "source_external_id",
                "metadata",
            },
            "logistics": {
                "id",
                "organization_id",
                "source_system",
                "source_external_id",
                "metadata",
            },
            "cross_organizational_movements": set(BusinessDocument.model_fields),
            "internal_movements": set(BusinessDocument.model_fields),
            "stocktakings": set(BusinessDocument.model_fields),
            "write_offs": set(BusinessDocument.model_fields),
            "supplier_returns": set(BusinessDocument.model_fields),
            "warehouse_receipts": set(BusinessDocument.model_fields),
            "purchases": set(BusinessDocument.model_fields),
            "inventory_balances": set(InventoryBalance.model_fields),
            "equipment_assets": {
                "id",
                "organization_id",
                "source_system",
                "source_external_id",
                "metadata",
            },
            "equipment_movements": {
                "id",
                "organization_id",
                "source_system",
                "source_external_id",
                "metadata",
            },
            "equipment_requests": {
                "id",
                "organization_id",
                "source_system",
                "source_external_id",
                "metadata",
            },
            "field_visits": set(Visit.model_fields),
        }

    def _mappings(self) -> list[SmartUpMapping]:
        return list(SMARTUP_CORE_MAPPING_V1)

    def _core_domain(self, mapping: SmartUpMapping) -> str:
        if mapping.group == "master_data":
            return "Master Data"
        if mapping.group == "sales":
            return "Sales"
        if mapping.group == "finance":
            return "Finance"
        if mapping.group == "inventory":
            return "Inventory"
        if mapping.group == "assets":
            return "Assets"
        return "Operations"

    def _business_module(self, mapping: SmartUpMapping) -> str:
        table = mapping.target_table
        if table in {"contacts"}:
            return "Customers"
        if table in {"products"}:
            return "Products"
        if table in {"product_groups"}:
            return "Product Categories"
        if table in {"price_types", "price_points"}:
            return "Price Management"
        if table in {"producers"}:
            return "Producers"
        if table in {"contracts"}:
            return "Contracts"
        if table in {"workspaces"}:
            return "Working Zones"
        if table in {"services"}:
            return "Service Catalog"
        if table in {"person_groups"}:
            return "Customer Groups"
        if table in {"sales"}:
            return "Orders"
        if table in {"sales_returns", "return_reasons"}:
            return "Returns"
        if table in {"payments", "finance_entries"}:
            return "Finance"
        if table in {"logistics"}:
            return "Logistics"
        if table in {
            "cross_organizational_movements",
            "internal_movements",
            "stocktakings",
            "write_offs",
            "supplier_returns",
            "warehouse_receipts",
            "purchases",
        }:
            return "Warehouse Operations"
        if table in {"inventory_balances"}:
            return "Inventory"
        if table in {"equipment_assets", "equipment_movements", "equipment_requests"}:
            return "Assets"
        if table in {"field_visits"}:
            return "Field Sales"
        return mapping.target_entity

    def _page_name(self, mapping: SmartUpMapping) -> str:
        module = self._business_module(mapping)
        if module == "Customers":
            return "Customers / Customer 360"
        if module == "Products":
            return "Products / Product 360"
        if module == "Orders":
            return "Sales / Orders"
        if module == "Returns":
            return "Sales / Returns"
        if module == "Finance":
            return "Finance / Cash Flow"
        if module == "Inventory":
            return "Inventory / Stock"
        if module == "Field Sales":
            return "Field Sales / Visits"
        if module == "Assets":
            return "Assets / Equipment"
        if module in {
            "Product Categories",
            "Price Management",
            "Producers",
            "Contracts",
            "Working Zones",
            "Service Catalog",
            "Customer Groups",
        }:
            return "References / Master Data"
        if module == "Warehouse Operations":
            return "Inventory / Warehouse Operations"
        if module == "Logistics":
            return "Operations / Logistics"
        return "Data Explorer / Admin Debug"

    def _component_name(
        self,
        mapping: SmartUpMapping,
        *,
        source_field: str | None = None,
        target_field: str | None = None,
    ) -> str:
        if source_field and any(
            token in source_field.lower() for token in ("photo", "image", "sha")
        ):
            return "Gallery + detail drawer"
        if target_field and target_field.startswith("metadata."):
            return "Dense table + side panel"
        if mapping.target_table in {
            "sales",
            "sales_returns",
            "payments",
            "finance_entries",
            "inventory_balances",
            "field_visits",
        }:
            return "Dense table + drill-down"
        if mapping.target_table in {
            "products",
            "product_groups",
            "price_types",
            "price_points",
            "producers",
            "contracts",
            "workspaces",
            "services",
            "person_groups",
        }:
            return "Reference table"
        if mapping.target_table in {
            "equipment_assets",
            "equipment_movements",
            "equipment_requests",
        }:
            return "Asset table + inspector"
        return "Table + analytics panel"

    def _analytics_use(
        self,
        mapping: SmartUpMapping,
        *,
        source_field: str | None = None,
        target_field: str | None = None,
    ) -> str:
        if mapping.group == "sales":
            return "Revenue, conversion, basket, returns, drill-down"
        if mapping.group == "finance":
            return "Cash flow, payments, receivables, expenses"
        if mapping.group == "inventory":
            return "Stock value, low stock, balance trends"
        if mapping.group == "assets":
            return "Equipment stock, movement, and request analytics"
        if mapping.group == "operations":
            return "Visit performance, routes, warehouse operations"
        if mapping.group == "master_data":
            return "Reference integrity, completeness, and enrichment"
        return "Business analytics"

    def _ai_use(
        self,
        mapping: SmartUpMapping,
        *,
        source_field: str | None = None,
        target_field: str | None = None,
    ) -> str:
        if source_field and any(
            token in source_field.lower() for token in ("photo", "image", "sha")
        ):
            return "Vision AI for photo compliance and merchandising analysis"
        if mapping.group == "sales":
            return "Sales forecasting, anomaly detection, and recommendation engine"
        if mapping.group == "finance":
            return "Cash forecast, payment risk detection, and expense anomaly analysis"
        if mapping.group == "inventory":
            return "Stockout prediction, slow-mover detection, and replenishment suggestions"
        if mapping.group == "operations":
            return "Route optimization, visit quality analysis, and field sales guidance"
        if mapping.group == "assets":
            return "Equipment lifecycle and utilization intelligence"
        if mapping.group == "master_data":
            return "Master-data cleanup, duplicate detection, and enrichment"
        return "Business intelligence assistance"
