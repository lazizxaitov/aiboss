"""Canonical Data Layer V2 foundation backfill from SmartUp RAW."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from app.core.data_layer.canonical_v2 import (
    CanonicalCustomer,
    CanonicalCustomerGroup,
    CanonicalCustomerReturn,
    CanonicalCustomerReturnItem,
    CanonicalDataQualityStatus,
    CanonicalCrossOrgMovement,
    CanonicalCrossOrgMovementItem,
    CanonicalFinancialAccount,
    CanonicalFinancialDirection,
    CanonicalFinancialOperation,
    CanonicalInternalMovement,
    CanonicalInternalMovementItem,
    CanonicalInventoryBalance,
    CanonicalOrder,
    CanonicalOrganization,
    CanonicalPayment,
    CanonicalPaymentAllocation,
    CanonicalPriceType,
    CanonicalProduct,
    CanonicalProductCategory,
    CanonicalProductPrice,
    CanonicalPurchase,
    CanonicalPurchaseItem,
    CanonicalSale,
    CanonicalSaleItem,
    CanonicalSalesRep,
    CanonicalStocktaking,
    CanonicalStocktakingItem,
    CanonicalMediaAsset,
    CanonicalSupplierReturn,
    CanonicalSupplierReturnItem,
    CanonicalV2ValidationReport,
    CanonicalV2ValidationTableReport,
    CanonicalVisit,
    CanonicalVisitComment,
    CanonicalVisitEquipment,
    CanonicalVisitQuizAnswer,
    CanonicalVisitStock,
    CanonicalWarehouse,
    CanonicalWarehouseReceipt,
    CanonicalWarehouseReceiptItem,
    CanonicalWorkingZone,
    CanonicalWriteoff,
    CanonicalWriteoffItem,
    canonical_row_uuid,
)
from app.core.data_layer.contracts import CoreDataStore
from app.integrations.smartup.audit import (
    SmartUpDataIntegrityAuditService,
    SmartUpRawAttributionReport,
)
from app.integrations.smartup.models import (
    NormalizationIssue,
    NormalizationIssueSeverity,
    SMARTUP_INTEGRATION_UUID,
    SmartUpOrganization,
    SmartUpRawRecord,
)

_SAFE_RAW_STATUSES = {"CONSISTENT", "LEGACY_MISSING_REQUEST_CONTEXT"}
_SOURCE_IDENTIFIER_MISSING = "SMARTUP_SOURCE_IDENTIFIER_MISSING"
_BUSINESS_TIMEZONE = ZoneInfo("Asia/Tashkent")


@dataclass(slots=True)
class SmartUpCanonicalV2FoundationService:
    """Build canonical V2 dimensions from verified SmartUp RAW evidence."""

    store: CoreDataStore
    audit_service: SmartUpDataIntegrityAuditService = field(init=False, repr=False)
    _product_index: dict[UUID, dict[str, CanonicalProduct]] = field(init=False, repr=False, default_factory=dict)
    _warehouse_index: dict[UUID, dict[str, CanonicalWarehouse]] = field(init=False, repr=False, default_factory=dict)
    _price_type_index: dict[UUID, dict[str, CanonicalPriceType]] = field(init=False, repr=False, default_factory=dict)
    _purchase_item_product_index: dict[UUID, dict[str, UUID]] = field(
        init=False,
        repr=False,
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        self.audit_service = SmartUpDataIntegrityAuditService(self.store)

    def backfill_phase1(
        self,
        organization_id: UUID | None = None,
    ) -> CanonicalV2ValidationReport:
        """Backfill the first canonical V2 foundation tables."""

        organizations = list(
            self.store.list_smartup_organizations(
                integration_id=SMARTUP_INTEGRATION_UUID,
                is_active=None,
            ),
        )
        if organization_id is not None:
            organizations = [org for org in organizations if org.id == organization_id]
        raw_attribution = self.audit_service.build_raw_attribution_report(
            organization_id=organization_id,
        )
        raw_status_by_record_id = self._raw_status_map(raw_attribution)
        notes = [
            (
                "Canonical V2 foundation built from trusted SmartUp RAW rows only. "
                "Unsafe attribution rows are excluded."
            ),
        ]

        table_reports: list[CanonicalV2ValidationTableReport] = []
        table_reports.append(self._backfill_organizations(organizations))
        table_reports.append(
            self._backfill_customer_groups(organizations, raw_status_by_record_id)
        )
        table_reports.append(self._backfill_customers(organizations, raw_status_by_record_id))
        table_reports.append(
            self._backfill_product_categories(organizations, raw_status_by_record_id)
        )
        table_reports.append(self._backfill_products(organizations, raw_status_by_record_id))
        table_reports.append(self._backfill_warehouses(organizations, raw_status_by_record_id))
        table_reports.append(self._backfill_price_types(organizations, raw_status_by_record_id))
        table_reports.append(self._backfill_product_prices(organizations, raw_status_by_record_id))
        table_reports.append(self._backfill_sales_reps(organizations, raw_status_by_record_id))
        table_reports.append(
            self._backfill_working_zones(organizations, raw_status_by_record_id)
        )

        unsafe_rows = len(
            [issue for issue in raw_attribution.issues if issue.status not in _SAFE_RAW_STATUSES]
        )
        if unsafe_rows:
            notes.append(f"Excluded {unsafe_rows} unsafe RAW rows from canonical backfill.")
        if organization_id is not None:
            notes.append(f"Scope restricted to organization_id={organization_id}.")
        return CanonicalV2ValidationReport(
            organization_scope=(
                self._organization_scope_name(organizations)
                if organization_id is None
                else str(organization_id)
            ),
            tables=table_reports,
            notes=notes,
        )

    def backfill_all(
        self,
        organization_id: UUID | None = None,
    ) -> list[CanonicalV2ValidationReport]:
        """Materialize the full canonical V2 foundation in deterministic phase order."""

        return [
            self.backfill_phase1(organization_id=organization_id),
            self.backfill_phase2_sales(organization_id=organization_id),
            self.backfill_phase2_payments_returns(organization_id=organization_id),
            self.backfill_phase2_inventory_warehouse(organization_id=organization_id),
            self.backfill_phase2_visits(organization_id=organization_id),
            self.backfill_phase2_finance(organization_id=organization_id),
        ]

    def backfill_phase2_sales(
        self,
        organization_id: UUID | None = None,
    ) -> CanonicalV2ValidationReport:
        """Materialize canonical order, sale, and sale-item facts from trusted SmartUp order RAW."""

        organizations = list(
            self.store.list_smartup_organizations(
                integration_id=SMARTUP_INTEGRATION_UUID,
                is_active=None,
            ),
        )
        if organization_id is not None:
            organizations = [org for org in organizations if org.id == organization_id]
        raw_attribution = self.audit_service.build_raw_attribution_report(
            organization_id=organization_id,
        )
        raw_status_by_record_id = self._raw_status_map(raw_attribution)
        table_reports = self._backfill_orders_sales_and_items(organizations, raw_status_by_record_id)
        notes = [
            "Phase 2 sales facts are materialized only from trusted SmartUp order export rows.",
            "Order semantics are preserved separately from realized sales semantics.",
        ]
        if organization_id is not None:
            notes.append(f"Scope restricted to organization_id={organization_id}.")
        return CanonicalV2ValidationReport(
            organization_scope=(
                self._organization_scope_name(organizations)
                if organization_id is None
                else str(organization_id)
            ),
            tables=table_reports,
            notes=notes,
        )

    def backfill_phase2_payments_returns(
        self,
        organization_id: UUID | None = None,
    ) -> CanonicalV2ValidationReport:
        """Materialize canonical payments and customer returns from trusted SmartUp RAW."""

        organizations = list(
            self.store.list_smartup_organizations(
                integration_id=SMARTUP_INTEGRATION_UUID,
                is_active=None,
            ),
        )
        if organization_id is not None:
            organizations = [org for org in organizations if org.id == organization_id]
        raw_attribution = self.audit_service.build_raw_attribution_report(
            organization_id=organization_id,
        )
        raw_status_by_record_id = self._raw_status_map(raw_attribution)
        table_reports = self._backfill_payments_and_returns(organizations, raw_status_by_record_id)
        notes = [
            "Phase 2B facts are materialized only from trusted SmartUp cashin and customer return RAW.",
            "Payment allocations are created only from exact SmartUp document references.",
        ]
        if organization_id is not None:
            notes.append(f"Scope restricted to organization_id={organization_id}.")
        return CanonicalV2ValidationReport(
            organization_scope=(
                self._organization_scope_name(organizations)
                if organization_id is None
                else str(organization_id)
            ),
            tables=table_reports,
            notes=notes,
        )

    def backfill_phase2_inventory_warehouse(
        self,
        organization_id: UUID | None = None,
    ) -> CanonicalV2ValidationReport:
        """Materialize canonical inventory and warehouse transaction facts from trusted RAW."""

        organizations = list(
            self.store.list_smartup_organizations(
                integration_id=SMARTUP_INTEGRATION_UUID,
                is_active=None,
            ),
        )
        if organization_id is not None:
            organizations = [org for org in organizations if org.id == organization_id]
        raw_attribution = self.audit_service.build_raw_attribution_report(
            organization_id=organization_id,
        )
        raw_status_by_record_id = self._raw_status_map(raw_attribution)
        table_reports = self._backfill_inventory_warehouse(organizations, raw_status_by_record_id)
        notes = [
            "Phase 2C uses immutable SmartUp RAW only and preserves warehouse semantics by dataset.",
            "Empty SmartUp wrapper responses are reported as zero materializable facts, not inferred documents.",
        ]
        if organization_id is not None:
            notes.append(f"Scope restricted to organization_id={organization_id}.")
        return CanonicalV2ValidationReport(
            organization_scope=(
                self._organization_scope_name(organizations)
                if organization_id is None
                else str(organization_id)
            ),
            tables=table_reports,
            notes=notes,
        )

    def backfill_phase2_visits(
        self,
        organization_id: UUID | None = None,
    ) -> CanonicalV2ValidationReport:
        """Materialize canonical field-sales visit facts from trusted SmartUp visit RAW."""

        organizations = list(
            self.store.list_smartup_organizations(
                integration_id=SMARTUP_INTEGRATION_UUID,
                is_active=None,
            ),
        )
        if organization_id is not None:
            organizations = [org for org in organizations if org.id == organization_id]
        raw_attribution = self.audit_service.build_raw_attribution_report(
            organization_id=organization_id,
        )
        raw_status_by_record_id = self._raw_status_map(raw_attribution)
        table_reports = self._backfill_visits(organizations, raw_status_by_record_id)
        notes = [
            "Phase 2D uses immutable SmartUp visit RAW only and preserves field-sales semantics without inferred AI metrics.",
            "Visit child tables are materialized only when nested business rows exist in RAW.",
            "Photo/media binaries are not downloaded in this phase; only immutable references are preserved when present.",
        ]
        if organization_id is not None:
            notes.append(f"Scope restricted to organization_id={organization_id}.")
        return CanonicalV2ValidationReport(
            organization_scope=(
                self._organization_scope_name(organizations)
                if organization_id is None
                else str(organization_id)
            ),
            tables=table_reports,
            notes=notes,
        )

    def backfill_phase2_finance(
        self,
        organization_id: UUID | None = None,
    ) -> CanonicalV2ValidationReport:
        """Materialize canonical finance/cash-flow facts from immutable SmartUp RAW."""

        organizations = list(
            self.store.list_smartup_organizations(
                integration_id=SMARTUP_INTEGRATION_UUID,
                is_active=None,
            ),
        )
        if organization_id is not None:
            organizations = [org for org in organizations if org.id == organization_id]
        raw_attribution = self.audit_service.build_raw_attribution_report(
            organization_id=organization_id,
        )
        raw_status_by_record_id = self._raw_status_map(raw_attribution)
        table_reports = self._backfill_finance(organizations, raw_status_by_record_id)
        notes = [
            "Phase 2E uses immutable SmartUp finance RAW only and keeps sales, payments, returns, and cash movements as separate business concepts.",
            "Customer payments remain independent canonical facts; financial operations represent money movement only when source semantics are proven.",
            "Potential overlaps between cashin and cash_operation rows are preserved via provenance and downgraded from strict VERIFIED cash-flow usage when needed.",
        ]
        if organization_id is not None:
            notes.append(f"Scope restricted to organization_id={organization_id}.")
        return CanonicalV2ValidationReport(
            organization_scope=(
                self._organization_scope_name(organizations)
                if organization_id is None
                else str(organization_id)
            ),
            tables=table_reports,
            notes=notes,
        )

    def _backfill_organizations(
        self,
        organizations: list[SmartUpOrganization],
    ) -> CanonicalV2ValidationTableReport:
        rows: list[CanonicalOrganization] = []
        for organization in sorted(organizations, key=lambda item: (item.sort_order, item.name.lower())):
            rows.append(
                CanonicalOrganization(
                    organization_id=organization.id,
                    name=organization.name,
                    company_id=organization.company_id,
                    filial_id=organization.filial_id,
                    filial_code=organization.filial_code,
                    project_code=organization.project_code,
                    is_active=organization.is_active,
                    sort_order=organization.sort_order,
                    source_system="smartup",
                    source_endpoint="smartup_organizations",
                    source_external_id=organization.filial_id,
                    source_raw_record_id=None,
                    request_filial_id=organization.filial_id,
                    response_filial_id=organization.filial_id,
                    request_company_id=organization.company_id,
                    request_project_code=organization.project_code,
                    source_raw_batch_id=None,
                    data_quality_status=CanonicalDataQualityStatus.VERIFIED,
                    imported_at=organization.created_at,
                    last_synced_at=organization.last_sync_at,
                    created_at=organization.created_at,
                    updated_at=organization.updated_at,
                    metadata=dict(organization.metadata),
                ),
            )
        for row in rows:
            self.store.upsert_canonical_organization(row)
        return self._table_report(
            table="canonical_organizations",
            raw_source_count=len(organizations),
            canonical_rows=rows,
            unsafe_count=0,
            unresolved_count=0,
            duplicate_count=0,
            notes=["SmartUp organization settings are the root canonical dimension."],
        )

    def _backfill_customer_groups(
        self,
        organizations: list[SmartUpOrganization],
        raw_status_by_record_id: dict[UUID, str],
    ) -> CanonicalV2ValidationTableReport:
        return self._backfill_dimension_from_raw(
            table="canonical_customer_groups",
            organizations=organizations,
            entity_types=("product_categories",),
            source_endpoints=(
                "/person_group$export",
            ),
            response_keys=("person_group",),
            raw_status_by_record_id=raw_status_by_record_id,
            builder=self._build_customer_group,
        )

    def _backfill_customers(
        self,
        organizations: list[SmartUpOrganization],
        raw_status_by_record_id: dict[UUID, str],
    ) -> CanonicalV2ValidationTableReport:
        raw_source_count = 0
        unsafe_count = 0
        unresolved_count = 0
        duplicate_count = 0
        candidates: dict[tuple[UUID, str], CanonicalCustomer] = {}
        evidence: dict[tuple[UUID, str], list[UUID]] = defaultdict(list)

        for organization in organizations:
            for raw_record, row, source_kind in self._customer_candidate_rows(organization.id):
                if not self._response_filial_matches(organization, raw_record):
                    continue
                status = self._raw_status(raw_status_by_record_id, raw_record.id)
                if status not in _SAFE_RAW_STATUSES:
                    unsafe_count += 1
                    continue
                customer = self._build_customer(raw_record, row, status, source_kind=source_kind)
                if customer is None:
                    unresolved_count += 1
                    continue
                raw_source_count += 1
                key = (customer.organization_id, customer.source_external_id)
                evidence[key].append(raw_record.id)
                existing = candidates.get(key)
                if existing is None or self._prefer_customer_candidate(customer, existing):
                    candidates[key] = customer

        duplicate_count = sum(max(0, len(ids) - 1) for ids in evidence.values())
        rows = sorted(
            candidates.values(),
            key=lambda item: (item.organization_id, item.code or item.name or item.source_external_id),
        )
        for row in rows:
            self.store.upsert_canonical_customer(row)
        return self._table_report(
            table="canonical_customers",
            raw_source_count=raw_source_count,
            canonical_rows=rows,
            unsafe_count=unsafe_count,
            unresolved_count=unresolved_count,
            duplicate_count=duplicate_count,
            notes=["Customers are discovered from master customer exports and transactional references."],
        )

    def _backfill_product_categories(
        self,
        organizations: list[SmartUpOrganization],
        raw_status_by_record_id: dict[UUID, str],
    ) -> CanonicalV2ValidationTableReport:
        return self._backfill_dimension_from_raw(
            table="canonical_product_categories",
            organizations=organizations,
            entity_types=("product_categories",),
            source_endpoints=(
                "/product_group$export",
            ),
            response_keys=("product_group",),
            raw_status_by_record_id=raw_status_by_record_id,
            builder=self._build_product_category,
        )

    def _backfill_products(
        self,
        organizations: list[SmartUpOrganization],
        raw_status_by_record_id: dict[UUID, str],
    ) -> CanonicalV2ValidationTableReport:
        return self._backfill_dimension_from_raw(
            table="canonical_products",
            organizations=organizations,
            entity_types=("products", "inventory", "service", "producer"),
            response_keys=("inventory", "product", "service", "producer"),
            raw_status_by_record_id=raw_status_by_record_id,
            builder=self._build_product,
        )

    def _backfill_warehouses(
        self,
        organizations: list[SmartUpOrganization],
        raw_status_by_record_id: dict[UUID, str],
    ) -> CanonicalV2ValidationTableReport:
        raw_source_count = 0
        unsafe_count = 0
        unresolved_count = 0
        duplicate_count = 0
        candidates: dict[tuple[UUID, str], CanonicalWarehouse] = {}
        evidence: dict[tuple[UUID, str], list[UUID]] = defaultdict(list)

        for organization in organizations:
            for raw_record in self._raw_records_for_warehouse_sources(organization.id):
                if not self._response_filial_matches(organization, raw_record):
                    continue
                status = self._raw_status(raw_status_by_record_id, raw_record.id)
                if status not in _SAFE_RAW_STATUSES:
                    unsafe_count += 1
                    continue
                row = self._payload_row(raw_record)
                if row is None:
                    unresolved_count += 1
                    continue
                warehouse = self._build_warehouse(raw_record, row, status)
                if warehouse is None:
                    unresolved_count += 1
                    continue
                raw_source_count += 1
                key = (warehouse.organization_id, warehouse.source_external_id)
                evidence[key].append(raw_record.id)
                existing = candidates.get(key)
                if existing is None or self._prefer_candidate(warehouse, existing):
                    candidates[key] = warehouse

        duplicate_count = sum(max(0, len(ids) - 1) for ids in evidence.values())
        rows = sorted(
            candidates.values(),
            key=lambda item: (item.organization_id, item.warehouse_code or item.warehouse_name or ""),
        )
        for row in rows:
            self.store.upsert_canonical_warehouse(row)
        return self._table_report(
            table="canonical_warehouses",
            raw_source_count=raw_source_count,
            canonical_rows=rows,
            unsafe_count=unsafe_count,
            unresolved_count=unresolved_count,
            duplicate_count=duplicate_count,
            notes=["Warehouses are discovered from verified warehouse-bearing RAW evidence."],
        )

    def _backfill_price_types(
        self,
        organizations: list[SmartUpOrganization],
        raw_status_by_record_id: dict[UUID, str],
    ) -> CanonicalV2ValidationTableReport:
        return self._backfill_dimension_from_raw(
            table="canonical_price_types",
            organizations=organizations,
            entity_types=("price_types", "price_type"),
            response_keys=("price_type",),
            raw_status_by_record_id=raw_status_by_record_id,
            builder=self._build_price_type,
        )

    def _backfill_product_prices(
        self,
        organizations: list[SmartUpOrganization],
        raw_status_by_record_id: dict[UUID, str],
    ) -> CanonicalV2ValidationTableReport:
        raw_source_count = 0
        unsafe_count = 0
        unresolved_count = 0
        duplicate_count = 0
        candidates: dict[tuple[UUID, str], CanonicalProductPrice] = {}
        evidence: dict[tuple[UUID, str], list[UUID]] = defaultdict(list)

        for organization in organizations:
            for raw_record in self._raw_records(organization.id, ("price_points", "product_prices")):
                if not self._response_filial_matches(organization, raw_record):
                    continue
                status = self._raw_status(raw_status_by_record_id, raw_record.id)
                if status not in _SAFE_RAW_STATUSES:
                    unsafe_count += 1
                    continue
                row = self._payload_row(raw_record)
                if row is None:
                    unresolved_count += 1
                    continue
                for product_price in self._build_product_prices(raw_record, row, status):
                    raw_source_count += 1
                    key = (product_price.organization_id, product_price.source_external_id)
                    evidence[key].append(raw_record.id)
                    existing = candidates.get(key)
                    if existing is None or self._prefer_candidate(product_price, existing):
                        candidates[key] = product_price

        duplicate_count = sum(max(0, len(ids) - 1) for ids in evidence.values())
        rows = sorted(
            candidates.values(),
            key=lambda item: (item.organization_id, item.price_type_code or item.product_code or ""),
        )
        for row in rows:
            self.store.upsert_canonical_product_price(row)
        return self._table_report(
            table="canonical_product_prices",
            raw_source_count=raw_source_count,
            canonical_rows=rows,
            unsafe_count=unsafe_count,
            unresolved_count=unresolved_count,
            duplicate_count=duplicate_count,
            notes=["Price points remain empty when SmartUp returns no price rows."],
        )

    def _backfill_sales_reps(
        self,
        organizations: list[SmartUpOrganization],
        raw_status_by_record_id: dict[UUID, str],
    ) -> CanonicalV2ValidationTableReport:
        raw_source_count = 0
        unsafe_count = 0
        unresolved_count = 0
        duplicate_count = 0
        candidates: dict[tuple[UUID, str], CanonicalSalesRep] = {}
        evidence: dict[tuple[UUID, str], list[UUID]] = defaultdict(list)

        for organization in organizations:
            for raw_record in self._raw_records(organization.id, ("sales", "visits", "payments")):
                if not self._response_filial_matches(organization, raw_record):
                    continue
                status = self._raw_status(raw_status_by_record_id, raw_record.id)
                if status not in _SAFE_RAW_STATUSES:
                    unsafe_count += 1
                    continue
                rows = (
                    self._visit_header_rows(raw_record.response_payload)
                    if raw_record.entity_type == "visits"
                    else [self._payload_row(raw_record)]
                )
                rows = [row for row in rows if row is not None]
                if not rows:
                    unresolved_count += 1
                    continue
                built = False
                for row in rows:
                    rep = self._build_sales_rep(raw_record, row, status)
                    if rep is None:
                        continue
                    built = True
                    raw_source_count += 1
                    key = (rep.organization_id, rep.source_external_id)
                    evidence[key].append(raw_record.id)
                    existing = candidates.get(key)
                    if existing is None or self._prefer_candidate(rep, existing):
                        candidates[key] = rep
                if not built:
                    unresolved_count += 1

        duplicate_count = sum(max(0, len(ids) - 1) for ids in evidence.values())
        rows = sorted(
            candidates.values(),
            key=lambda item: (item.organization_id, item.sales_manager_name.lower()),
        )
        for row in rows:
            self.store.upsert_canonical_sales_rep(row)
        return self._table_report(
            table="canonical_sales_reps",
            raw_source_count=raw_source_count,
            canonical_rows=rows,
            unsafe_count=unsafe_count,
            unresolved_count=unresolved_count,
            duplicate_count=duplicate_count,
            notes=["Sales reps are discovered from Sales, Visits and Payments evidence."],
        )

    def _backfill_working_zones(
        self,
        organizations: list[SmartUpOrganization],
        raw_status_by_record_id: dict[UUID, str],
    ) -> CanonicalV2ValidationTableReport:
        raw_source_count = 0
        unsafe_count = 0
        unresolved_count = 0
        duplicate_count = 0
        candidates: dict[tuple[UUID, str], CanonicalWorkingZone] = {}
        evidence: dict[tuple[UUID, str], list[UUID]] = defaultdict(list)

        for organization in organizations:
            for raw_record in self._raw_records(organization.id, ("sales", "visits")):
                if not self._response_filial_matches(organization, raw_record):
                    continue
                status = self._raw_status(raw_status_by_record_id, raw_record.id)
                if status not in _SAFE_RAW_STATUSES:
                    unsafe_count += 1
                    continue
                rows = (
                    self._visit_header_rows(raw_record.response_payload)
                    if raw_record.entity_type == "visits"
                    else [self._payload_row(raw_record)]
                )
                rows = [row for row in rows if row is not None]
                if not rows:
                    unresolved_count += 1
                    continue
                built = False
                for row in rows:
                    zone = self._build_working_zone(raw_record, row, status)
                    if zone is None:
                        continue
                    built = True
                    raw_source_count += 1
                    key = (zone.organization_id, zone.source_external_id)
                    evidence[key].append(raw_record.id)
                    existing = candidates.get(key)
                    if existing is None or self._prefer_candidate(zone, existing):
                        candidates[key] = zone
                if not built:
                    unresolved_count += 1

        duplicate_count = sum(max(0, len(ids) - 1) for ids in evidence.values())
        rows = sorted(
            candidates.values(),
            key=lambda item: (item.organization_id, item.room_name or item.room_code or ""),
        )
        for row in rows:
            self.store.upsert_canonical_working_zone(row)
        return self._table_report(
            table="canonical_working_zones",
            raw_source_count=raw_source_count,
            canonical_rows=rows,
            unsafe_count=unsafe_count,
            unresolved_count=unresolved_count,
            duplicate_count=duplicate_count,
            notes=["Working zones are discovered from Sales and Visits outlet room evidence."],
        )

    def _backfill_visits(
        self,
        organizations: list[SmartUpOrganization],
        raw_status_by_record_id: dict[UUID, str],
    ) -> list[CanonicalV2ValidationTableReport]:
        visit_candidates: dict[tuple[UUID, str], CanonicalVisit] = {}
        visit_stock_candidates: dict[tuple[UUID, str], CanonicalVisitStock] = {}
        visit_quiz_candidates: dict[tuple[UUID, str], CanonicalVisitQuizAnswer] = {}
        visit_equipment_candidates: dict[tuple[UUID, str], CanonicalVisitEquipment] = {}
        visit_comment_candidates: dict[tuple[UUID, str], CanonicalVisitComment] = {}
        media_candidates: dict[tuple[UUID, str], CanonicalMediaAsset] = {}
        evidence: dict[str, dict[tuple[UUID, str], list[UUID]]] = defaultdict(lambda: defaultdict(list))
        raw_counts: dict[str, int] = defaultdict(int)
        unsafe_counts: dict[str, int] = defaultdict(int)
        unresolved_counts: dict[str, int] = defaultdict(int)

        for organization in organizations:
            for raw_record in self._raw_records(organization.id, ("visits",)):
                if not self._response_filial_matches(organization, raw_record):
                    continue
                status = self._raw_status(raw_status_by_record_id, raw_record.id)
                if status not in _SAFE_RAW_STATUSES:
                    unsafe_counts["visits"] += 1
                    continue
                payload = self._payload_row(raw_record)
                if payload is None:
                    unresolved_counts["visits"] += 1
                    continue
                visit_rows = self._visit_header_rows(payload)
                if not visit_rows:
                    unresolved_counts["visits"] += 1
                    continue

                for visit_index, visit_row in enumerate(visit_rows, start=1):
                    visit = self._build_canonical_visit(
                        raw_record=raw_record,
                        row=visit_row,
                        status=status,
                        payload=payload,
                    )
                    if visit is None:
                        unresolved_counts["visits"] += 1
                        continue
                    raw_counts["visits"] += 1
                    visit_key = (visit.organization_id, visit.source_external_id)
                    evidence["canonical_visits"][visit_key].append(raw_record.id)
                    existing_visit = visit_candidates.get(visit_key)
                    if existing_visit is None or self._prefer_candidate(visit, existing_visit):
                        visit_candidates[visit_key] = visit

                    stock_rows = self._build_canonical_visit_stocks(
                        raw_record=raw_record,
                        payload=payload,
                        status=status,
                        visit=visit,
                    )
                    if stock_rows:
                        for stock in stock_rows:
                            raw_counts["visit_stocks"] += 1
                            stock_key = (stock.organization_id, stock.source_external_id)
                            evidence["canonical_visit_stocks"][stock_key].append(raw_record.id)
                            existing_stock = visit_stock_candidates.get(stock_key)
                            if existing_stock is None or self._prefer_candidate(stock, existing_stock):
                                visit_stock_candidates[stock_key] = stock
                    elif payload.get("stocks") not in (None, []):
                        unresolved_counts["visit_stocks"] += 1

                    quiz_rows = self._build_canonical_visit_quiz_answers(
                        raw_record=raw_record,
                        payload=payload,
                        status=status,
                        visit=visit,
                    )
                    if quiz_rows:
                        for quiz in quiz_rows:
                            raw_counts["visit_quiz_answers"] += 1
                            quiz_key = (quiz.organization_id, quiz.source_external_id)
                            evidence["canonical_visit_quiz_answers"][quiz_key].append(raw_record.id)
                            existing_quiz = visit_quiz_candidates.get(quiz_key)
                            if existing_quiz is None or self._prefer_candidate(quiz, existing_quiz):
                                visit_quiz_candidates[quiz_key] = quiz

                    equipment_rows = self._build_canonical_visit_equipments(
                        raw_record=raw_record,
                        payload=payload,
                        status=status,
                        visit=visit,
                    )
                    if equipment_rows:
                        for equipment in equipment_rows:
                            raw_counts["visit_equipments"] += 1
                            equipment_key = (equipment.organization_id, equipment.source_external_id)
                            evidence["canonical_visit_equipments"][equipment_key].append(raw_record.id)
                            existing_equipment = visit_equipment_candidates.get(equipment_key)
                            if existing_equipment is None or self._prefer_candidate(equipment, existing_equipment):
                                visit_equipment_candidates[equipment_key] = equipment
                    elif payload.get("equipments") not in (None, []):
                        unresolved_counts["visit_equipments"] += 1

                    comment_rows = self._build_canonical_visit_comments(
                        raw_record=raw_record,
                        payload=payload,
                        status=status,
                        visit=visit,
                    )
                    if comment_rows:
                        for comment in comment_rows:
                            raw_counts["visit_comments"] += 1
                            comment_key = (comment.organization_id, comment.source_external_id)
                            evidence["canonical_visit_comments"][comment_key].append(raw_record.id)
                            existing_comment = visit_comment_candidates.get(comment_key)
                            if existing_comment is None or self._prefer_candidate(comment, existing_comment):
                                visit_comment_candidates[comment_key] = comment
                    elif payload.get("comments") not in (None, []):
                        unresolved_counts["visit_comments"] += 1

                    media_rows = self._build_canonical_media_assets(
                        raw_record=raw_record,
                        payload=payload,
                        status=status,
                        visit=visit,
                        visit_index=visit_index,
                    )
                    if media_rows:
                        for media in media_rows:
                            raw_counts["media_assets"] += 1
                            media_key = (media.organization_id, media.source_external_id)
                            evidence["canonical_media_assets"][media_key].append(raw_record.id)
                            existing_media = media_candidates.get(media_key)
                            if existing_media is None or self._prefer_candidate(media, existing_media):
                                media_candidates[media_key] = media

        visit_rows = sorted(
            visit_candidates.values(),
            key=lambda item: (
                item.organization_id,
                item.visit_date or datetime.min.replace(tzinfo=UTC),
                item.source_external_id,
            ),
        )
        stock_rows = sorted(
            visit_stock_candidates.values(),
            key=lambda item: (
                item.organization_id,
                str(item.visit_id),
                item.line_number,
                item.source_external_id,
            ),
        )
        quiz_rows = sorted(
            visit_quiz_candidates.values(),
            key=lambda item: (
                item.organization_id,
                str(item.visit_id),
                item.line_number,
                item.source_external_id,
            ),
        )
        equipment_rows = sorted(
            visit_equipment_candidates.values(),
            key=lambda item: (
                item.organization_id,
                str(item.visit_id),
                item.line_number,
                item.source_external_id,
            ),
        )
        comment_rows = sorted(
            visit_comment_candidates.values(),
            key=lambda item: (
                item.organization_id,
                str(item.visit_id),
                item.line_number,
                item.source_external_id,
            ),
        )
        media_rows = sorted(
            media_candidates.values(),
            key=lambda item: (
                item.organization_id,
                item.source_sha or "",
                item.source_external_id,
            ),
        )

        for row in visit_rows:
            self.store.upsert_canonical_visit(row)
        for row in stock_rows:
            self.store.upsert_canonical_visit_stock(row)
        for row in quiz_rows:
            self.store.upsert_canonical_visit_quiz_answer(row)
        for row in equipment_rows:
            self.store.upsert_canonical_visit_equipment(row)
        for row in comment_rows:
            self.store.upsert_canonical_visit_comment(row)
        for row in media_rows:
            self.store.upsert_canonical_media_asset(row)

        return [
            self._table_report(
                table="canonical_visits",
                raw_source_count=raw_counts["visits"],
                canonical_rows=visit_rows,
                unsafe_count=unsafe_counts["visits"],
                unresolved_count=unresolved_counts["visits"],
                duplicate_count=sum(max(0, len(ids) - 1) for ids in evidence["canonical_visits"].values()),
                notes=[
                    "Visit headers are materialized from SmartUp visit_headers rows only.",
                    "Visit identity uses SmartUp visit_id within organization scope.",
                ],
            ),
            self._table_report(
                table="canonical_visit_stocks",
                raw_source_count=raw_counts["visit_stocks"],
                canonical_rows=stock_rows,
                unsafe_count=0,
                unresolved_count=unresolved_counts["visit_stocks"],
                duplicate_count=sum(max(0, len(ids) - 1) for ids in evidence["canonical_visit_stocks"].values()),
                notes=["Retail-point stock observations stay separate from warehouse inventory."],
            ),
            self._table_report(
                table="canonical_visit_quiz_answers",
                raw_source_count=raw_counts["visit_quiz_answers"],
                canonical_rows=quiz_rows,
                unsafe_count=0,
                unresolved_count=0,
                duplicate_count=sum(max(0, len(ids) - 1) for ids in evidence["canonical_visit_quiz_answers"].values()),
                notes=["Quiz answers preserve factual field-sales answer rows only when present in RAW."],
            ),
            self._table_report(
                table="canonical_visit_equipments",
                raw_source_count=raw_counts["visit_equipments"],
                canonical_rows=equipment_rows,
                unsafe_count=0,
                unresolved_count=unresolved_counts["visit_equipments"],
                duplicate_count=sum(max(0, len(ids) - 1) for ids in evidence["canonical_visit_equipments"].values()),
                notes=["Visit equipment evidence remains separate from warehouse/equipment movement domains."],
            ),
            self._table_report(
                table="canonical_visit_comments",
                raw_source_count=raw_counts["visit_comments"],
                canonical_rows=comment_rows,
                unsafe_count=0,
                unresolved_count=unresolved_counts["visit_comments"],
                duplicate_count=sum(max(0, len(ids) - 1) for ids in evidence["canonical_visit_comments"].values()),
                notes=["Structured comments are preserved only when comment rows exist in RAW."],
            ),
            self._table_report(
                table="canonical_media_assets",
                raw_source_count=raw_counts["media_assets"],
                canonical_rows=media_rows,
                unsafe_count=0,
                unresolved_count=0,
                duplicate_count=sum(max(0, len(ids) - 1) for ids in evidence["canonical_media_assets"].values()),
                notes=["Media references preserve immutable SHA/reference evidence without binary download."],
            ),
        ]

    def _backfill_orders_sales_and_items(
        self,
        organizations: list[SmartUpOrganization],
        raw_status_by_record_id: dict[UUID, str],
    ) -> list[CanonicalV2ValidationTableReport]:
        order_candidates: dict[tuple[UUID, str], CanonicalOrder] = {}
        sale_candidates: dict[tuple[UUID, str], CanonicalSale] = {}
        item_candidates: dict[tuple[UUID, str], CanonicalSaleItem] = {}
        order_evidence: dict[tuple[UUID, str], list[UUID]] = defaultdict(list)
        sale_evidence: dict[tuple[UUID, str], list[UUID]] = defaultdict(list)
        item_evidence: dict[tuple[UUID, str], list[UUID]] = defaultdict(list)

        order_raw_source_count = 0
        sale_raw_source_count = 0
        item_raw_source_count = 0
        order_unsafe_count = 0
        sale_unsafe_count = 0
        item_unsafe_count = 0
        unresolved_orders = 0
        unresolved_sales = 0
        unresolved_items = 0

        for organization in organizations:
            for raw_record in self._raw_records(organization.id, ("sales",)):
                if not self._response_filial_matches(organization, raw_record):
                    continue
                status = self._raw_status(raw_status_by_record_id, raw_record.id)
                if status not in _SAFE_RAW_STATUSES:
                    order_unsafe_count += 1
                    sale_unsafe_count += 1
                    item_unsafe_count += 1
                    continue
                row = self._payload_row(raw_record)
                if row is None:
                    unresolved_orders += 1
                    unresolved_sales += 1
                    unresolved_items += 1
                    continue

                order = self._build_canonical_order(raw_record, row, status)
                if order is None:
                    unresolved_orders += 1
                    unresolved_sales += 1
                    unresolved_items += 1
                    continue
                order_raw_source_count += 1
                order_key = (order.organization_id, order.source_external_id)
                order_evidence[order_key].append(raw_record.id)
                existing_order = order_candidates.get(order_key)
                if existing_order is None or self._prefer_candidate(order, existing_order):
                    order_candidates[order_key] = order

                sale = self._build_canonical_sale(raw_record, row, status, order)
                if sale is None:
                    unresolved_sales += 1
                else:
                    sale_raw_source_count += 1
                    sale_key = (sale.organization_id, sale.source_external_id)
                    sale_evidence[sale_key].append(raw_record.id)
                    existing_sale = sale_candidates.get(sale_key)
                    if existing_sale is None or self._prefer_candidate(sale, existing_sale):
                        sale_candidates[sale_key] = sale

                sale_items = self._build_canonical_sale_items(
                    raw_record=raw_record,
                    row=row,
                    status=status,
                    order=order,
                    sale=sale,
                )
                if not sale_items:
                    unresolved_items += 1
                    continue
                item_raw_source_count += len(sale_items)
                for sale_item in sale_items:
                    item_key = (sale_item.organization_id, sale_item.source_external_id)
                    item_evidence[item_key].append(raw_record.id)
                    existing_item = item_candidates.get(item_key)
                    if existing_item is None or self._prefer_candidate(sale_item, existing_item):
                        item_candidates[item_key] = sale_item

        order_rows = sorted(
            order_candidates.values(),
            key=lambda item: (
                item.organization_id,
                item.order_at or datetime.min.replace(tzinfo=UTC),
                item.source_external_id,
            ),
        )
        sale_rows = sorted(
            sale_candidates.values(),
            key=lambda item: (
                item.organization_id,
                item.sale_at or datetime.min.replace(tzinfo=UTC),
                item.source_external_id,
            ),
        )
        sale_item_rows = sorted(
            item_candidates.values(),
            key=lambda item: (
                item.organization_id,
                item.sale_external_id or "",
                item.line_number,
                item.source_external_id,
            ),
        )

        for row in order_rows:
            self.store.upsert_canonical_order(row)
        for row in sale_rows:
            self.store.upsert_canonical_sale(row)
        for row in sale_item_rows:
            self.store.upsert_canonical_sale_item(row)

        return [
            self._table_report(
                table="canonical_orders",
                raw_source_count=order_raw_source_count,
                canonical_rows=order_rows,
                unsafe_count=order_unsafe_count,
                unresolved_count=unresolved_orders,
                duplicate_count=sum(max(0, len(ids) - 1) for ids in order_evidence.values()),
                notes=["Orders preserve SmartUp order semantics before realization."],
            ),
            self._table_report(
                table="canonical_sales",
                raw_source_count=sale_raw_source_count,
                canonical_rows=sale_rows,
                unsafe_count=sale_unsafe_count,
                unresolved_count=unresolved_sales,
                duplicate_count=sum(max(0, len(ids) - 1) for ids in sale_evidence.values()),
                notes=["Sales are emitted only when rows contain explicit realization evidence."],
            ),
            self._table_report(
                table="canonical_sale_items",
                raw_source_count=item_raw_source_count,
                canonical_rows=sale_item_rows,
                unsafe_count=item_unsafe_count,
                unresolved_count=unresolved_items,
                duplicate_count=sum(max(0, len(ids) - 1) for ids in item_evidence.values()),
                notes=["Sale items keep ordered, sold, and returned quantities as separate facts."],
            ),
        ]

    def _backfill_payments_and_returns(
        self,
        organizations: list[SmartUpOrganization],
        raw_status_by_record_id: dict[UUID, str],
    ) -> list[CanonicalV2ValidationTableReport]:
        payment_candidates: dict[tuple[UUID, str], CanonicalPayment] = {}
        allocation_candidates: dict[tuple[UUID, str], CanonicalPaymentAllocation] = {}
        return_candidates: dict[tuple[UUID, str], CanonicalCustomerReturn] = {}
        return_item_candidates: dict[tuple[UUID, str], CanonicalCustomerReturnItem] = {}
        payment_evidence: dict[tuple[UUID, str], list[UUID]] = defaultdict(list)
        allocation_evidence: dict[tuple[UUID, str], list[UUID]] = defaultdict(list)
        return_evidence: dict[tuple[UUID, str], list[UUID]] = defaultdict(list)
        return_item_evidence: dict[tuple[UUID, str], list[UUID]] = defaultdict(list)

        payment_raw_source_count = 0
        payment_unsafe_count = 0
        unresolved_payments = 0
        unresolved_allocations = 0
        return_raw_source_count = 0
        return_item_raw_source_count = 0
        return_unsafe_count = 0
        return_item_unsafe_count = 0
        unresolved_returns = 0
        unresolved_return_items = 0

        for organization in organizations:
            for raw_record in self._raw_records(organization.id, ("payments",)):
                if not self._response_filial_matches(organization, raw_record):
                    continue
                status = self._raw_status(raw_status_by_record_id, raw_record.id)
                if status not in _SAFE_RAW_STATUSES:
                    payment_unsafe_count += 1
                    continue
                row = self._payload_row(raw_record)
                if row is None:
                    unresolved_payments += 1
                    continue
                payment = self._build_canonical_payment(raw_record, row, status)
                if payment is None:
                    unresolved_payments += 1
                    continue
                payment_raw_source_count += 1
                payment_key = (payment.organization_id, payment.source_external_id)
                payment_evidence[payment_key].append(raw_record.id)
                existing_payment = payment_candidates.get(payment_key)
                if existing_payment is None or self._prefer_candidate(payment, existing_payment):
                    payment_candidates[payment_key] = payment

                allocations = self._build_canonical_payment_allocations(raw_record, row, status, payment)
                if allocations:
                    for allocation in allocations:
                        allocation_key = (allocation.organization_id, allocation.source_external_id)
                        allocation_evidence[allocation_key].append(raw_record.id)
                        existing_allocation = allocation_candidates.get(allocation_key)
                        if existing_allocation is None or self._prefer_candidate(
                            allocation,
                            existing_allocation,
                        ):
                            allocation_candidates[allocation_key] = allocation
                else:
                    unresolved_allocations += 1

            for raw_record in self._raw_records(organization.id, ("returns",)):
                if not self._response_filial_matches(organization, raw_record):
                    continue
                status = self._raw_status(raw_status_by_record_id, raw_record.id)
                if status not in _SAFE_RAW_STATUSES:
                    return_unsafe_count += 1
                    return_item_unsafe_count += 1
                    continue
                row = self._payload_row(raw_record)
                if row is None:
                    unresolved_returns += 1
                    unresolved_return_items += 1
                    continue
                customer_return = self._build_canonical_customer_return(raw_record, row, status)
                if customer_return is None:
                    unresolved_returns += 1
                    unresolved_return_items += 1
                    continue
                return_raw_source_count += 1
                return_key = (customer_return.organization_id, customer_return.source_external_id)
                return_evidence[return_key].append(raw_record.id)
                existing_return = return_candidates.get(return_key)
                if existing_return is None or self._prefer_candidate(customer_return, existing_return):
                    return_candidates[return_key] = customer_return

                return_items = self._build_canonical_customer_return_items(
                    raw_record=raw_record,
                    row=row,
                    status=status,
                    customer_return=customer_return,
                )
                if not return_items:
                    unresolved_return_items += 1
                    continue
                return_item_raw_source_count += len(return_items)
                for return_item in return_items:
                    return_item_key = (
                        return_item.organization_id,
                        return_item.source_external_id,
                    )
                    return_item_evidence[return_item_key].append(raw_record.id)
                    existing_return_item = return_item_candidates.get(return_item_key)
                    if existing_return_item is None or self._prefer_candidate(
                        return_item,
                        existing_return_item,
                    ):
                        return_item_candidates[return_item_key] = return_item

        payment_rows = sorted(
            payment_candidates.values(),
            key=lambda item: (
                item.organization_id,
                item.paid_at or datetime.min.replace(tzinfo=UTC),
                item.source_external_id,
            ),
        )
        allocation_rows = sorted(
            allocation_candidates.values(),
            key=lambda item: (
                item.organization_id,
                str(item.payment_id),
                item.source_external_id,
            ),
        )
        return_rows = sorted(
            return_candidates.values(),
            key=lambda item: (
                item.organization_id,
                item.return_at or datetime.min.replace(tzinfo=UTC),
                item.source_external_id,
            ),
        )
        return_item_rows = sorted(
            return_item_candidates.values(),
            key=lambda item: (
                item.organization_id,
                str(item.customer_return_id),
                item.line_number,
                item.source_external_id,
            ),
        )

        for row in payment_rows:
            self.store.upsert_canonical_payment(row)
        for row in allocation_rows:
            self.store.upsert_canonical_payment_allocation(row)
        for row in return_rows:
            self.store.upsert_canonical_customer_return(row)
        for row in return_item_rows:
            self.store.upsert_canonical_customer_return_item(row)

        return [
            self._table_report(
                table="canonical_payments",
                raw_source_count=payment_raw_source_count,
                canonical_rows=payment_rows,
                unsafe_count=payment_unsafe_count,
                unresolved_count=unresolved_payments,
                duplicate_count=sum(max(0, len(ids) - 1) for ids in payment_evidence.values()),
                notes=["Payments preserve SmartUp cashin semantics and customer linkage."],
            ),
            self._table_report(
                table="canonical_payment_allocations",
                raw_source_count=len(allocation_rows),
                canonical_rows=allocation_rows,
                unsafe_count=0,
                unresolved_count=unresolved_allocations,
                duplicate_count=sum(max(0, len(ids) - 1) for ids in allocation_evidence.values()),
                notes=["Allocations are created only from exact SmartUp document references."],
            ),
            self._table_report(
                table="canonical_customer_returns",
                raw_source_count=return_raw_source_count,
                canonical_rows=return_rows,
                unsafe_count=return_unsafe_count,
                unresolved_count=unresolved_returns,
                duplicate_count=sum(max(0, len(ids) - 1) for ids in return_evidence.values()),
                notes=["Customer returns remain separate from supplier-return warehouse semantics."],
            ),
            self._table_report(
                table="canonical_customer_return_items",
                raw_source_count=return_item_raw_source_count,
                canonical_rows=return_item_rows,
                unsafe_count=return_item_unsafe_count,
                unresolved_count=unresolved_return_items,
                duplicate_count=sum(max(0, len(ids) - 1) for ids in return_item_evidence.values()),
                notes=["Return items preserve quantities, prices, amounts, VAT, and margin fields."],
            ),
        ]

    def _backfill_finance(
        self,
        organizations: list[SmartUpOrganization],
        raw_status_by_record_id: dict[UUID, str],
    ) -> list[CanonicalV2ValidationTableReport]:
        account_candidates: dict[tuple[UUID, str], CanonicalFinancialAccount] = {}
        operation_candidates: dict[tuple[UUID, str], CanonicalFinancialOperation] = {}
        account_evidence: dict[tuple[UUID, str], list[UUID]] = defaultdict(list)
        operation_evidence: dict[tuple[UUID, str], list[UUID]] = defaultdict(list)
        raw_counts: dict[str, int] = defaultdict(int)
        unsafe_counts: dict[str, int] = defaultdict(int)
        unresolved_counts: dict[str, int] = defaultdict(int)

        for organization in organizations:
            overlap_signatures = self._payment_overlap_signatures(organization.id)
            for raw_record in self._raw_records(
                organization.id,
                ("payments", "bank_operations"),
            ):
                if not self._response_filial_matches(organization, raw_record):
                    continue
                status = self._raw_status(raw_status_by_record_id, raw_record.id)
                if status not in _SAFE_RAW_STATUSES:
                    unsafe_counts[raw_record.entity_type] += 1
                    continue
                row = self._payload_row(raw_record)
                if row is None or self._is_wrapper_only_row(row):
                    unresolved_counts[raw_record.entity_type] += 1
                    continue

                if raw_record.entity_type == "payments":
                    raw_counts["payments"] += 1
                    account = self._build_financial_account_from_payment(raw_record, row, status)
                    if account is not None:
                        key = (account.organization_id, account.source_external_id)
                        account_evidence[key].append(raw_record.id)
                        existing = account_candidates.get(key)
                        if existing is None or self._prefer_candidate(account, existing):
                            account_candidates[key] = account
                    operation = self._build_financial_operation_from_payment(
                        raw_record,
                        row,
                        status,
                    )
                    if operation is None:
                        unresolved_counts["canonical_financial_operations"] += 1
                        continue
                    op_key = (operation.organization_id, operation.source_external_id)
                    operation_evidence[op_key].append(raw_record.id)
                    existing_op = operation_candidates.get(op_key)
                    if existing_op is None or self._prefer_candidate(operation, existing_op):
                        operation_candidates[op_key] = operation
                    continue

                if raw_record.entity_type == "bank_operations":
                    if self._source_is_cash_operation(raw_record.source_endpoint):
                        raw_counts["cash_operations"] += 1
                        account = self._build_financial_account_from_cash_operation(
                            raw_record,
                            row,
                            status,
                        )
                        if account is not None:
                            key = (account.organization_id, account.source_external_id)
                            account_evidence[key].append(raw_record.id)
                            existing = account_candidates.get(key)
                            if existing is None or self._prefer_candidate(account, existing):
                                account_candidates[key] = account
                        operation = self._build_financial_operation_from_cash_operation(
                            raw_record,
                            row,
                            status,
                            overlap_signatures=overlap_signatures,
                        )
                        if operation is None:
                            unresolved_counts["canonical_financial_operations"] += 1
                            continue
                        op_key = (operation.organization_id, operation.source_external_id)
                        operation_evidence[op_key].append(raw_record.id)
                        existing_op = operation_candidates.get(op_key)
                        if existing_op is None or self._prefer_candidate(operation, existing_op):
                            operation_candidates[op_key] = operation
                        continue

                    raw_counts["bank_operations"] += 1
                    account = self._build_financial_account_from_bank_operation(
                        raw_record,
                        row,
                        status,
                    )
                    if account is not None:
                        key = (account.organization_id, account.source_external_id)
                        account_evidence[key].append(raw_record.id)
                        existing = account_candidates.get(key)
                        if existing is None or self._prefer_candidate(account, existing):
                            account_candidates[key] = account
                    operation = self._build_financial_operation_from_bank_operation(
                        raw_record,
                        row,
                        status,
                    )
                    if operation is None:
                        unresolved_counts["canonical_financial_operations"] += 1
                        continue
                    op_key = (operation.organization_id, operation.source_external_id)
                    operation_evidence[op_key].append(raw_record.id)
                    existing_op = operation_candidates.get(op_key)
                    if existing_op is None or self._prefer_candidate(operation, existing_op):
                        operation_candidates[op_key] = operation

        account_rows = sorted(
            account_candidates.values(),
            key=lambda item: (item.organization_id, item.account_type, item.account_code or item.source_external_id),
        )
        operation_rows = sorted(
            operation_candidates.values(),
            key=lambda item: (
                item.organization_id,
                item.operation_at or datetime.min.replace(tzinfo=UTC),
                item.source_external_id,
            ),
        )

        for row in account_rows:
            self.store.upsert_canonical_financial_account(row)
        for row in operation_rows:
            self.store.upsert_canonical_financial_operation(row)

        finance_raw_source_count = (
            raw_counts["payments"] + raw_counts["cash_operations"] + raw_counts["bank_operations"]
        )
        account_raw_source_count = len(account_rows)
        cashflow_notes = [
            "Only VERIFIED operations with deterministic direction and currency are eligible for strict cash-flow analytics.",
            "Customer payments and cash operations are kept separate; overlap evidence is preserved in metadata.",
        ]
        if raw_counts["bank_operations"] == 0:
            cashflow_notes.append("No materializable bank_operation rows were discovered in current immutable RAW.")
        return [
            self._table_report(
                table="canonical_financial_accounts",
                raw_source_count=account_raw_source_count,
                canonical_rows=account_rows,
                unsafe_count=unsafe_counts["payments"] + unsafe_counts["bank_operations"],
                unresolved_count=unresolved_counts["payments"] + unresolved_counts["bank_operations"],
                duplicate_count=sum(max(0, len(ids) - 1) for ids in account_evidence.values()),
                notes=[
                    "Financial accounts are derived only from explicit SmartUp cashbox/bank/coa/account fields.",
                ],
            ),
            self._table_report(
                table="canonical_financial_operations",
                raw_source_count=finance_raw_source_count,
                canonical_rows=operation_rows,
                unsafe_count=unsafe_counts["payments"] + unsafe_counts["bank_operations"],
                unresolved_count=unresolved_counts["canonical_financial_operations"],
                duplicate_count=sum(max(0, len(ids) - 1) for ids in operation_evidence.values()),
                notes=cashflow_notes,
            ),
        ]

    def _backfill_inventory_warehouse(
        self,
        organizations: list[SmartUpOrganization],
        raw_status_by_record_id: dict[UUID, str],
    ) -> list[CanonicalV2ValidationTableReport]:
        self._purchase_item_product_index.clear()
        balance_candidates: dict[tuple[UUID, str], CanonicalInventoryBalance] = {}
        purchase_candidates: dict[tuple[UUID, str], CanonicalPurchase] = {}
        purchase_item_candidates: dict[tuple[UUID, str], CanonicalPurchaseItem] = {}
        purchase_item_product_candidates: dict[UUID, dict[str, UUID]] = defaultdict(dict)
        receipt_candidates: dict[tuple[UUID, str], CanonicalWarehouseReceipt] = {}
        receipt_item_candidates: dict[tuple[UUID, str], CanonicalWarehouseReceiptItem] = {}
        writeoff_candidates: dict[tuple[UUID, str], CanonicalWriteoff] = {}
        writeoff_item_candidates: dict[tuple[UUID, str], CanonicalWriteoffItem] = {}
        cross_org_candidates: dict[tuple[UUID, str], CanonicalCrossOrgMovement] = {}
        cross_org_item_candidates: dict[tuple[UUID, str], CanonicalCrossOrgMovementItem] = {}
        evidence: dict[str, dict[tuple[UUID, str], list[UUID]]] = defaultdict(lambda: defaultdict(list))
        raw_counts: dict[str, int] = defaultdict(int)
        unsafe_counts: dict[str, int] = defaultdict(int)
        unresolved_counts: dict[str, int] = defaultdict(int)

        for organization in organizations:
            for raw_record in self._raw_records_for_warehouse_sources(organization.id):
                if not self._response_filial_matches(organization, raw_record):
                    continue
                status = self._raw_status(raw_status_by_record_id, raw_record.id)
                if status not in _SAFE_RAW_STATUSES:
                    unsafe_counts[raw_record.entity_type] += 1
                    continue
                row = self._payload_row(raw_record)
                if row is None:
                    unresolved_counts[raw_record.entity_type] += 1
                    continue

                if raw_record.entity_type == "inventory_balances":
                    balance = self._build_canonical_inventory_balance(raw_record, row, status)
                    if balance is None:
                        unresolved_counts["inventory_balances"] += 1
                        continue
                    raw_counts["inventory_balances"] += 1
                    key = (balance.organization_id, balance.source_external_id)
                    evidence["canonical_inventory_balances"][key].append(raw_record.id)
                    existing = balance_candidates.get(key)
                    if existing is None or self._prefer_candidate(balance, existing):
                        balance_candidates[key] = balance
                    continue

                if raw_record.entity_type == "purchases":
                    purchase = self._build_canonical_purchase(raw_record, row, status)
                    if purchase is None:
                        unresolved_counts["purchases"] += 1
                        unresolved_counts["purchase_items"] += 1
                        continue
                    raw_counts["purchases"] += 1
                    key = (purchase.organization_id, purchase.source_external_id)
                    evidence["canonical_purchases"][key].append(raw_record.id)
                    existing = purchase_candidates.get(key)
                    if existing is None or self._prefer_candidate(purchase, existing):
                        purchase_candidates[key] = purchase
                    items = self._build_canonical_purchase_items(
                        raw_record=raw_record,
                        row=row,
                        status=status,
                        purchase=purchase,
                    )
                    if not items:
                        unresolved_counts["purchase_items"] += 1
                    for item in items:
                        raw_counts["purchase_items"] += 1
                        item_key = (item.organization_id, item.source_external_id)
                        evidence["canonical_purchase_items"][item_key].append(raw_record.id)
                        existing_item = purchase_item_candidates.get(item_key)
                        if existing_item is None or self._prefer_candidate(item, existing_item):
                            purchase_item_candidates[item_key] = item
                        if item.purchase_item_id and item.product_id is not None:
                            purchase_item_product_candidates[item.organization_id][item.purchase_item_id] = item.product_id
                    continue

                if raw_record.entity_type == "warehouse_receipts":
                    receipt = self._build_canonical_warehouse_receipt(raw_record, row, status)
                    if receipt is None:
                        unresolved_counts["warehouse_receipts"] += 1
                        unresolved_counts["warehouse_receipt_items"] += 1
                        continue
                    raw_counts["warehouse_receipts"] += 1
                    key = (receipt.organization_id, receipt.source_external_id)
                    evidence["canonical_warehouse_receipts"][key].append(raw_record.id)
                    existing = receipt_candidates.get(key)
                    if existing is None or self._prefer_candidate(receipt, existing):
                        receipt_candidates[key] = receipt
                    items = self._build_canonical_warehouse_receipt_items(
                        raw_record=raw_record,
                        row=row,
                        status=status,
                        receipt=receipt,
                        inherited_purchase_item_products=purchase_item_product_candidates[
                            raw_record.organization_id
                        ],
                    )
                    if not items:
                        unresolved_counts["warehouse_receipt_items"] += 1
                    for item in items:
                        raw_counts["warehouse_receipt_items"] += 1
                        item_key = (item.organization_id, item.source_external_id)
                        evidence["canonical_warehouse_receipt_items"][item_key].append(raw_record.id)
                        existing_item = receipt_item_candidates.get(item_key)
                        if existing_item is None or self._prefer_candidate(item, existing_item):
                            receipt_item_candidates[item_key] = item
                    continue

                if raw_record.entity_type == "write_offs":
                    writeoff = self._build_canonical_writeoff(raw_record, row, status)
                    if writeoff is None:
                        unresolved_counts["write_offs"] += 1
                        unresolved_counts["writeoff_items"] += 1
                        continue
                    raw_counts["write_offs"] += 1
                    key = (writeoff.organization_id, writeoff.source_external_id)
                    evidence["canonical_writeoffs"][key].append(raw_record.id)
                    existing = writeoff_candidates.get(key)
                    if existing is None or self._prefer_candidate(writeoff, existing):
                        writeoff_candidates[key] = writeoff
                    items = self._build_canonical_writeoff_items(
                        raw_record=raw_record,
                        row=row,
                        status=status,
                        writeoff=writeoff,
                    )
                    if not items:
                        unresolved_counts["writeoff_items"] += 1
                    for item in items:
                        raw_counts["writeoff_items"] += 1
                        item_key = (item.organization_id, item.source_external_id)
                        evidence["canonical_writeoff_items"][item_key].append(raw_record.id)
                        existing_item = writeoff_item_candidates.get(item_key)
                        if existing_item is None or self._prefer_candidate(item, existing_item):
                            writeoff_item_candidates[item_key] = item
                    continue

                if raw_record.entity_type == "cross_organizational_movements":
                    movement = self._build_canonical_cross_org_movement(raw_record, row, status)
                    if movement is None:
                        unresolved_counts["cross_organizational_movements"] += 1
                        unresolved_counts["cross_org_movement_items"] += 1
                        continue
                    raw_counts["cross_organizational_movements"] += 1
                    key = (movement.organization_id, movement.source_external_id)
                    evidence["canonical_cross_org_movements"][key].append(raw_record.id)
                    existing = cross_org_candidates.get(key)
                    if existing is None or self._prefer_candidate(movement, existing):
                        cross_org_candidates[key] = movement
                    items = self._build_canonical_cross_org_movement_items(
                        raw_record=raw_record,
                        row=row,
                        status=status,
                        movement=movement,
                    )
                    if not items:
                        unresolved_counts["cross_org_movement_items"] += 1
                    for item in items:
                        raw_counts["cross_org_movement_items"] += 1
                        item_key = (item.organization_id, item.source_external_id)
                        evidence["canonical_cross_org_movement_items"][item_key].append(raw_record.id)
                        existing_item = cross_org_item_candidates.get(item_key)
                        if existing_item is None or self._prefer_candidate(item, existing_item):
                            cross_org_item_candidates[item_key] = item
                    continue

                if raw_record.entity_type in {"return_to_suppliers", "stocktakings", "internal_movements"}:
                    rows = self._rows_from_value(
                        raw_record.response_payload,
                        self._inventory_response_keys(raw_record.entity_type),
                    )
                    if rows:
                        unresolved_counts[raw_record.entity_type] += len(rows)

        balance_rows = sorted(balance_candidates.values(), key=lambda item: (item.organization_id, item.snapshot_date or datetime.min.replace(tzinfo=UTC), item.warehouse_code or "", item.product_code or "", item.grain_key or ""))
        purchase_rows = sorted(purchase_candidates.values(), key=lambda item: (item.organization_id, item.document_at or datetime.min.replace(tzinfo=UTC), item.source_external_id))
        purchase_item_rows = sorted(purchase_item_candidates.values(), key=lambda item: (item.organization_id, item.document_external_id or "", item.line_number, item.source_external_id))
        receipt_rows = sorted(receipt_candidates.values(), key=lambda item: (item.organization_id, item.document_at or datetime.min.replace(tzinfo=UTC), item.source_external_id))
        receipt_item_rows = sorted(receipt_item_candidates.values(), key=lambda item: (item.organization_id, item.document_external_id or "", item.line_number, item.source_external_id))
        writeoff_rows = sorted(writeoff_candidates.values(), key=lambda item: (item.organization_id, item.document_at or datetime.min.replace(tzinfo=UTC), item.source_external_id))
        writeoff_item_rows = sorted(writeoff_item_candidates.values(), key=lambda item: (item.organization_id, item.document_external_id or "", item.line_number, item.source_external_id))
        cross_org_rows = sorted(cross_org_candidates.values(), key=lambda item: (item.organization_id, item.document_at or datetime.min.replace(tzinfo=UTC), item.source_external_id))
        cross_org_item_rows = sorted(cross_org_item_candidates.values(), key=lambda item: (item.organization_id, item.document_external_id or "", item.line_number, item.source_external_id))

        purchase_item_product_linkage = self._linkage_coverage(
            len(purchase_item_rows),
            sum(1 for row in purchase_item_rows if row.product_id is not None),
        )
        purchase_warehouse_linkage = self._linkage_coverage(
            len(purchase_rows),
            sum(1 for row in purchase_rows if row.warehouse_id is not None),
        )
        purchase_document_amount_coverage = self._linkage_coverage(
            len(purchase_rows),
            sum(1 for row in purchase_rows if row.total_amount is not None),
        )
        receipt_item_product_linkage = self._linkage_coverage(
            len(receipt_item_rows),
            sum(1 for row in receipt_item_rows if row.product_id is not None),
        )
        receipt_warehouse_linkage = self._linkage_coverage(
            len(receipt_rows),
            sum(1 for row in receipt_rows if row.warehouse_id is not None),
        )
        receipt_document_amount_coverage = self._linkage_coverage(
            len(receipt_rows),
            sum(1 for row in receipt_rows if row.total_amount is not None),
        )

        for row in purchase_rows:
            row.metadata.setdefault("coverage", {})
            row.metadata["coverage"].update(
                {
                    "product_linkage_coverage": purchase_item_product_linkage,
                    "warehouse_linkage_coverage": purchase_warehouse_linkage,
                    "document_amount_coverage": purchase_document_amount_coverage,
                },
            )
        for row in purchase_item_rows:
            row.metadata.setdefault("coverage", {})
            row.metadata["coverage"].update(
                {
                    "product_linkage_coverage": purchase_item_product_linkage,
                    "warehouse_linkage_coverage": purchase_warehouse_linkage,
                    "document_amount_coverage": purchase_document_amount_coverage,
                },
            )
        for row in receipt_rows:
            row.metadata.setdefault("coverage", {})
            row.metadata["coverage"].update(
                {
                    "product_linkage_coverage": receipt_item_product_linkage,
                    "warehouse_linkage_coverage": receipt_warehouse_linkage,
                    "document_amount_coverage": receipt_document_amount_coverage,
                },
            )
        for row in receipt_item_rows:
            row.metadata.setdefault("coverage", {})
            row.metadata["coverage"].update(
                {
                    "product_linkage_coverage": receipt_item_product_linkage,
                    "warehouse_linkage_coverage": receipt_warehouse_linkage,
                    "document_amount_coverage": receipt_document_amount_coverage,
                },
            )

        for row in balance_rows:
            self.store.upsert_canonical_inventory_balance(row)
        for row in purchase_rows:
            self.store.upsert_canonical_purchase(row)
        for row in purchase_item_rows:
            self.store.upsert_canonical_purchase_item(row)
        for row in receipt_rows:
            self.store.upsert_canonical_warehouse_receipt(row)
        for row in receipt_item_rows:
            self.store.upsert_canonical_warehouse_receipt_item(row)
        for row in writeoff_rows:
            self.store.upsert_canonical_writeoff(row)
        for row in writeoff_item_rows:
            self.store.upsert_canonical_writeoff_item(row)
        for row in cross_org_rows:
            self.store.upsert_canonical_cross_org_movement(row)
        for row in cross_org_item_rows:
            self.store.upsert_canonical_cross_org_movement_item(row)

        return [
            self._table_report(table="canonical_inventory_balances", raw_source_count=raw_counts["inventory_balances"], canonical_rows=balance_rows, unsafe_count=unsafe_counts["inventory_balances"], unresolved_count=unresolved_counts["inventory_balances"], duplicate_count=sum(max(0, len(ids) - 1) for ids in evidence["canonical_inventory_balances"].values()), notes=["Balance rows are stock snapshots, not movements.", "Grain: organization + warehouse + product + batch/card/serial + snapshot date."]),
            self._table_report(table="canonical_purchases", raw_source_count=raw_counts["purchases"], canonical_rows=purchase_rows, unsafe_count=unsafe_counts["purchases"], unresolved_count=unresolved_counts["purchases"], duplicate_count=sum(max(0, len(ids) - 1) for ids in evidence["canonical_purchases"].values()), notes=["Purchases preserve supplier, date, currency, and total amount semantics.", f"warehouse_linkage_coverage={purchase_warehouse_linkage}", f"document_amount_coverage={purchase_document_amount_coverage}"]),
            self._table_report(table="canonical_purchase_items", raw_source_count=raw_counts["purchase_items"], canonical_rows=purchase_item_rows, unsafe_count=0, unresolved_count=unresolved_counts["purchase_items"], duplicate_count=sum(max(0, len(ids) - 1) for ids in evidence["canonical_purchase_items"].values()), notes=["Purchase items preserve quantity and line-level cost without inventing product identities.", f"product_linkage_coverage={purchase_item_product_linkage}", "Unresolved product references remain NULL and are excluded from SKU analytics by default."]),
            self._table_report(table="canonical_warehouse_receipts", raw_source_count=raw_counts["warehouse_receipts"], canonical_rows=receipt_rows, unsafe_count=unsafe_counts["warehouse_receipts"], unresolved_count=unresolved_counts["warehouse_receipts"], duplicate_count=sum(max(0, len(ids) - 1) for ids in evidence["canonical_warehouse_receipts"].values()), notes=["Warehouse receipts remain distinct from purchases and may stay PARTIAL at header level when warehouse identity is absent in source RAW.", f"warehouse_linkage_coverage={receipt_warehouse_linkage}", f"document_amount_coverage={receipt_document_amount_coverage}"]),
            self._table_report(table="canonical_warehouse_receipt_items", raw_source_count=raw_counts["warehouse_receipt_items"], canonical_rows=receipt_item_rows, unsafe_count=0, unresolved_count=unresolved_counts["warehouse_receipt_items"], duplicate_count=sum(max(0, len(ids) - 1) for ids in evidence["canonical_warehouse_receipt_items"].values()), notes=["Receipt items preserve physical inbound stock lines without fake product fallback.", f"product_linkage_coverage={receipt_item_product_linkage}", "Unresolved source references remain NULL and are visible for future enrichment."]),
            self._table_report(table="canonical_writeoffs", raw_source_count=raw_counts["write_offs"], canonical_rows=writeoff_rows, unsafe_count=unsafe_counts["write_offs"], unresolved_count=unresolved_counts["write_offs"], duplicate_count=sum(max(0, len(ids) - 1) for ids in evidence["canonical_writeoffs"].values()), notes=["Write-offs stay separate from expenses and returns."]),
            self._table_report(table="canonical_writeoff_items", raw_source_count=raw_counts["writeoff_items"], canonical_rows=writeoff_item_rows, unsafe_count=0, unresolved_count=unresolved_counts["writeoff_items"], duplicate_count=sum(max(0, len(ids) - 1) for ids in evidence["canonical_writeoff_items"].values()), notes=["Write-off items preserve product-level quantity evidence."]),
            self._table_report(table="canonical_supplier_returns", raw_source_count=0, canonical_rows=[], unsafe_count=unsafe_counts["return_to_suppliers"], unresolved_count=unresolved_counts["return_to_suppliers"], duplicate_count=0, notes=["Current immutable RAW contains wrapper-only supplier return responses; no business rows discovered."]),
            self._table_report(table="canonical_supplier_return_items", raw_source_count=0, canonical_rows=[], unsafe_count=0, unresolved_count=0, duplicate_count=0, notes=["No supplier return line items discovered in current immutable RAW."]),
            self._table_report(table="canonical_stocktakings", raw_source_count=0, canonical_rows=[], unsafe_count=unsafe_counts["stocktakings"], unresolved_count=unresolved_counts["stocktakings"], duplicate_count=0, notes=["Current immutable RAW contains no stocktaking business rows beyond empty wrapper responses."]),
            self._table_report(table="canonical_stocktaking_items", raw_source_count=0, canonical_rows=[], unsafe_count=0, unresolved_count=0, duplicate_count=0, notes=["No stocktaking line items discovered in current immutable RAW."]),
            self._table_report(table="canonical_internal_movements", raw_source_count=0, canonical_rows=[], unsafe_count=unsafe_counts["internal_movements"], unresolved_count=unresolved_counts["internal_movements"], duplicate_count=0, notes=["Current immutable RAW contains no internal movement business rows beyond empty wrapper responses."]),
            self._table_report(table="canonical_internal_movement_items", raw_source_count=0, canonical_rows=[], unsafe_count=0, unresolved_count=0, duplicate_count=0, notes=["No internal movement line items discovered in current immutable RAW."]),
            self._table_report(table="canonical_cross_org_movements", raw_source_count=raw_counts["cross_organizational_movements"], canonical_rows=cross_org_rows, unsafe_count=unsafe_counts["cross_organizational_movements"], unresolved_count=unresolved_counts["cross_organizational_movements"], duplicate_count=sum(max(0, len(ids) - 1) for ids in evidence["canonical_cross_org_movements"].values()), notes=["Cross-org movements preserve source and destination filial/warehouse evidence."]),
            self._table_report(table="canonical_cross_org_movement_items", raw_source_count=raw_counts["cross_org_movement_items"], canonical_rows=cross_org_item_rows, unsafe_count=0, unresolved_count=unresolved_counts["cross_org_movement_items"], duplicate_count=sum(max(0, len(ids) - 1) for ids in evidence["canonical_cross_org_movement_items"].values()), notes=["Cross-org movement items preserve transfer quantity and transfer cost separately."]),
        ]

    def _backfill_dimension_from_raw(
        self,
        *,
        table: str,
        organizations: list[SmartUpOrganization],
        entity_types: tuple[str, ...],
        source_endpoints: tuple[str, ...] | None = None,
        response_keys: tuple[str, ...],
        raw_status_by_record_id: dict[UUID, str],
        builder: Any,
    ) -> CanonicalV2ValidationTableReport:
        raw_source_count = 0
        unsafe_count = 0
        unresolved_count = 0
        duplicate_count = 0
        candidates: dict[tuple[UUID, str], Any] = {}
        evidence: dict[tuple[UUID, str], list[UUID]] = defaultdict(list)

        for organization in organizations:
            for raw_record in self._raw_records(organization.id, entity_types):
                if not self._response_filial_matches(organization, raw_record):
                    continue
                if source_endpoints is not None and not any(
                    raw_record.source_endpoint.endswith(endpoint)
                    for endpoint in source_endpoints
                ):
                    continue
                status = self._raw_status(raw_status_by_record_id, raw_record.id)
                if status not in _SAFE_RAW_STATUSES:
                    unsafe_count += 1
                    continue
                rows = self._candidate_rows(raw_record, response_keys)
                if not rows:
                    unresolved_count += 1
                    continue
                for row in rows:
                    canonical = builder(raw_record, row, status)
                    if canonical is None:
                        unresolved_count += 1
                        continue
                    raw_source_count += 1
                    key = (canonical.organization_id, canonical.source_external_id)
                    evidence[key].append(raw_record.id)
                    existing = candidates.get(key)
                    if existing is None or self._prefer_candidate(canonical, existing):
                        candidates[key] = canonical

        duplicate_count = sum(max(0, len(ids) - 1) for ids in evidence.values())
        rows = sorted(candidates.values(), key=lambda item: (item.organization_id, item.source_external_id))
        self._upsert_rows(table, rows)
        notes = [f"{table} backfilled from direct SmartUp RAW evidence."]
        return self._table_report(
            table=table,
            raw_source_count=raw_source_count,
            canonical_rows=rows,
            unsafe_count=unsafe_count,
            unresolved_count=unresolved_count,
            duplicate_count=duplicate_count,
            notes=notes,
        )

    def _build_customer_group(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalCustomerGroup | None:
        source_external_id = self._first_text(
            row,
            "person_group_id",
            "code",
            "external_id",
            "id",
        )
        name = self._first_text(row, "name", "short_name", "code")
        if source_external_id is None or name is None:
            return None
        return CanonicalCustomerGroup(
            id=canonical_row_uuid("canonical_customer_groups", raw_record.organization_id, source_external_id),
            organization_id=raw_record.organization_id,
            group_id=self._first_text(row, "person_group_id", "group_id"),
            code=self._first_text(row, "code"),
            name=name,
            customer_kind=self._first_text(row, "person_kind", "customer_kind"),
            state=self._first_text(row, "state"),
            group_types=self._list_of_dicts(row, "person_group_types", "group_types"),
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=source_external_id,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
            },
        )

    def _build_customer(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
        *,
        source_kind: str | None = None,
    ) -> CanonicalCustomer | None:
        source_external_id = self._first_text(
            row,
            "person_id",
            "client_id",
            "code",
            "external_id",
            "id",
        )
        name = self._first_text(row, "name", "short_name", "person_name", "client_name")
        if self._is_placeholder_label(name):
            return None
        if source_external_id is None or name is None:
            return None
        customer_source_kind = source_kind or self._customer_source_kind(raw_record)
        return CanonicalCustomer(
            id=canonical_row_uuid("canonical_customers", raw_record.organization_id, source_external_id),
            organization_id=raw_record.organization_id,
            person_id=self._first_text(row, "person_id", "client_id", "id"),
            code=self._first_text(row, "code", "client_code"),
            name=name,
            short_name=self._first_text(row, "short_name"),
            main_phone=self._first_text(row, "main_phone", "phone", "client_phone"),
            email=self._first_text(row, "email"),
            address=self._first_text(row, "address"),
            groups=self._list_of_dicts(row, "groups", "person_groups"),
            state=self._first_text(row, "state", "customer_status", "status"),
            customer_kind=self._first_text(row, "person_kind", "customer_kind"),
            tin=self._first_text(row, "tin", "person_tin", "client_tin"),
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=source_external_id,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._customer_quality_for_status(status, customer_source_kind),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
                "customer_source_kind": customer_source_kind,
                "customer_source_role": customer_source_kind,
            },
        )

    def _build_product_category(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalProductCategory | None:
        source_external_id = self._first_text(
            row,
            "product_group_id",
            "code",
            "external_id",
            "id",
        )
        name = self._first_text(row, "name", "short_name", "code")
        if source_external_id is None or name is None:
            return None
        return CanonicalProductCategory(
            id=canonical_row_uuid(
                "canonical_product_categories",
                raw_record.organization_id,
                source_external_id,
            ),
            organization_id=raw_record.organization_id,
            group_id=self._first_text(row, "product_group_id", "group_id"),
            code=self._first_text(row, "code"),
            name=name,
            product_kind=self._first_text(row, "product_kind"),
            state=self._first_text(row, "state"),
            group_types=self._list_of_dicts(row, "product_group_types", "group_types"),
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=source_external_id,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
            },
        )

    def _build_product(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalProduct | None:
        source_external_id = self._first_text(
            row,
            "product_id",
            "inventory_code",
            "code",
            "external_id",
            "id",
        )
        name = self._first_text(row, "name", "short_name", "code")
        if source_external_id is None or name is None:
            return None
        source_kind = self._source_kind_for_product(raw_record.source_endpoint, row)
        return CanonicalProduct(
            id=canonical_row_uuid("canonical_products", raw_record.organization_id, source_external_id),
            organization_id=raw_record.organization_id,
            product_id=self._first_text(row, "product_id", "inventory_code", "code"),
            code=self._first_text(row, "code", "inventory_code"),
            name=name,
            short_name=self._first_text(row, "short_name"),
            measure_code=self._first_text(row, "measure_code", "unit_code"),
            article_code=self._first_text(row, "article_code"),
            producer_code=self._first_text(row, "producer_code"),
            barcodes=self._list_of_text(row, "barcodes", "barcode"),
            inventory_kinds=self._list_of_dicts(row, "inventory_kinds"),
            groups=self._list_of_dicts(row, "groups"),
            state=self._first_text(row, "state"),
            source_kind=source_kind,
            gtin=self._first_text(row, "gtin"),
            ikpu=self._first_text(row, "ikpu"),
            box_quant=self._first_text(row, "box_quant"),
            box_type_code=self._first_text(row, "box_type_code"),
            litr=self._first_text(row, "litr"),
            marking_group_code=self._first_text(row, "marking_group_code"),
            sector_codes=self._list_of_dicts(row, "sector_codes"),
            tnved=self._first_text(row, "tnved"),
            weight_brutto=self._first_text(row, "weight_brutto"),
            weight_netto=self._first_text(row, "weight_netto"),
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=source_external_id,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
                "source_kind": source_kind,
            },
        )

    def _build_warehouse(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalWarehouse | None:
        source_external_id = self._first_text(
            row,
            "warehouse_id",
            "room_id",
            "warehouse_code",
            "room_code",
            "warehouse_name",
            "room_name",
        )
        if source_external_id is None:
            return None
        return CanonicalWarehouse(
            id=canonical_row_uuid("canonical_warehouses", raw_record.organization_id, source_external_id),
            organization_id=raw_record.organization_id,
            warehouse_id=self._first_text(row, "warehouse_id", "room_id"),
            warehouse_code=self._first_text(row, "warehouse_code", "room_code", "code"),
            warehouse_name=self._first_text(row, "warehouse_name", "room_name", "name"),
            state=self._first_text(row, "state"),
            source_kind=self._source_kind_for_warehouse(raw_record.source_endpoint, row),
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=source_external_id,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
            },
        )

    def _build_price_type(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalPriceType | None:
        source_external_id = self._first_text(row, "code", "price_type_id", "external_id", "id")
        name = self._first_text(row, "name", "short_name", "code")
        if source_external_id is None or name is None:
            return None
        return CanonicalPriceType(
            id=canonical_row_uuid("canonical_price_types", raw_record.organization_id, source_external_id),
            organization_id=raw_record.organization_id,
            price_type_id=self._first_text(row, "price_type_id", "id"),
            code=source_external_id,
            name=name,
            short_name=self._first_text(row, "short_name"),
            currency_code=self._first_text(row, "currency_code"),
            price_type_kind=self._first_text(row, "price_type_kind"),
            with_card=self._first_text(row, "with_card"),
            state=self._first_text(row, "state"),
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=source_external_id,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
            },
        )

    def _build_product_prices(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> list[CanonicalProductPrice]:
        product_external_id = self._first_text(
            row,
            "inventory_code",
            "product_code",
            "product_id",
            "code",
        )
        if product_external_id is None:
            return []
        price_rows = row.get("price_type")
        normalized_price_rows: list[dict[str, Any]]
        if isinstance(price_rows, list) and price_rows:
            normalized_price_rows = [item for item in price_rows if isinstance(item, dict)]
        else:
            normalized_price_rows = [row]
        results: list[CanonicalProductPrice] = []
        for index, price_row in enumerate(normalized_price_rows, start=1):
            price_type_code = self._first_text(price_row, "price_type_code", "card_code", "code")
            if price_type_code is None:
                price_type_code = f"{product_external_id}:{index}"
            source_external_id = price_type_code
            product_row = self._find_canonical_product(raw_record.organization_id, product_external_id)
            if product_row is None:
                continue
            product_id = product_row.id
            price_type_id = canonical_row_uuid(
                "canonical_price_types",
                raw_record.organization_id,
                price_type_code,
            )
            if self.store.get_canonical_price_type(price_type_id) is None:
                continue
            results.append(
                CanonicalProductPrice(
                    id=canonical_row_uuid(
                        "canonical_product_prices",
                        raw_record.organization_id,
                        source_external_id,
                    ),
                    organization_id=raw_record.organization_id,
                    product_id=product_id,
                    product_code=product_external_id,
                    inventory_code=self._first_text(row, "inventory_code", "product_code"),
                    inventory_barcode=self._first_text(row, "inventory_barcode", "barcode"),
                    price_type_id=price_type_id,
                    price_type_code=price_type_code,
                    price_type_card_code=self._first_text(price_row, "card_code"),
                    price=self._parse_decimal(price_row.get("price") or price_row.get("product_price")),
                    currency_code=self._first_text(row, "currency_code"),
                    state=self._first_text(row, "state"),
                    source_system="smartup",
                    source_endpoint=raw_record.source_endpoint,
                    source_external_id=source_external_id,
                    source_raw_record_id=raw_record.id,
                    request_filial_id=raw_record.request_filial_id,
                    response_filial_id=raw_record.response_filial_id,
                    request_company_id=raw_record.request_company_id,
                    request_project_code=raw_record.request_project_code,
                    source_raw_batch_id=raw_record.batch_id,
                    data_quality_status=self._quality_for_status(status),
                    imported_at=raw_record.imported_at,
                    last_synced_at=raw_record.source_updated_at,
                    metadata={
                        "source_entity": raw_record.entity_type,
                        "source_endpoint": raw_record.source_endpoint,
                        "inventory_barcode": self._first_text(row, "inventory_barcode", "barcode"),
                    },
                ),
            )
        return results

    def _find_canonical_product(
        self,
        organization_id: UUID,
        product_external_id: str,
    ) -> CanonicalProduct | None:
        return self._product_index_for_organization(organization_id).get(product_external_id)

    def _build_sales_rep(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalSalesRep | None:
        sales_manager_id = self._first_text(
            row,
            "sales_manager_id",
            "user_id",
            "responsible_person_code",
        )
        sales_manager_code = self._first_text(
            row,
            "sales_manager_code",
            "sales_manager_code_id",
            "user_code",
            "code",
        )
        sales_manager_name = self._first_text(
            row,
            "sales_manager_name",
            "user_name",
            "responsible_person_name",
            "name",
        )
        source_external_id = sales_manager_id or sales_manager_code or sales_manager_name
        if source_external_id is None:
            return None
        return CanonicalSalesRep(
            id=canonical_row_uuid("canonical_sales_reps", raw_record.organization_id, source_external_id),
            organization_id=raw_record.organization_id,
            sales_manager_id=sales_manager_id,
            sales_manager_code=sales_manager_code,
            sales_manager_name=sales_manager_name or source_external_id,
            role=self._first_text(row, "role", "position"),
            state=self._first_text(row, "state"),
            source_kind=self._source_kind_for_sales_rep(raw_record.source_endpoint, row),
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=source_external_id,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
            },
        )

    def _build_working_zone(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalWorkingZone | None:
        room_id = self._first_text(row, "room_id", "warehouse_id")
        room_code = self._first_text(row, "room_code", "warehouse_code", "code")
        room_name = self._first_text(row, "room_name", "warehouse_name", "name")
        source_external_id = room_id or room_code or room_name
        if source_external_id is None:
            return None
        return CanonicalWorkingZone(
            id=canonical_row_uuid("canonical_working_zones", raw_record.organization_id, source_external_id),
            organization_id=raw_record.organization_id,
            room_id=room_id,
            room_code=room_code,
            room_name=room_name or source_external_id,
            state=self._first_text(row, "state"),
            source_kind=self._source_kind_for_working_zone(raw_record.source_endpoint, row),
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=source_external_id,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
            },
        )

    def _build_canonical_visit(
        self,
        *,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
        payload: dict[str, Any],
    ) -> CanonicalVisit | None:
        source_external_id = self._first_text(row, "visit_id", "external_id")
        if source_external_id is None:
            return None
        customer_external_id = self._first_text(row, "person_id", "person_code")
        sales_rep_external_id = self._first_text(row, "sales_manager_id", "sales_manager_code")
        working_zone_external_id = self._first_text(row, "room_id", "room_code", "room_name")
        visit_date = self._parse_source_datetime(row.get("visit_date"))
        # SmartUp visit start/end values are business-local wall-clock values.
        # Keep the generic UTC parser for other canonical domains and only
        # apply the visit timestamp contract at this boundary.
        visit_start_time = self._parse_visit_datetime(row.get("visit_start_time"))
        visit_end_time = self._parse_visit_datetime(row.get("visit_end_time"))
        source_duration = self._parse_optional_int(
            row.get("time_at_retail_outlet_sec") or row.get("spent_time"),
        )
        derived_duration = self._derive_duration_seconds(visit_start_time, visit_end_time)
        normalized_status = self._normalize_visit_status(self._first_text(row, "visit_status"))
        start_latitude, start_longitude = self._parse_lat_lng(row.get("visit_start_location"))
        end_latitude, end_longitude = self._parse_lat_lng(row.get("visit_end_location"))
        note = self._extract_visit_note(payload)
        return CanonicalVisit(
            id=canonical_row_uuid("canonical_visits", raw_record.organization_id, source_external_id),
            organization_id=raw_record.organization_id,
            visit_id=self._first_text(row, "visit_id"),
            customer_id=self._resolve_canonical_customer_id(
                raw_record.organization_id,
                customer_external_id,
            ),
            customer_external_id=customer_external_id,
            customer_code=self._first_text(row, "person_code"),
            customer_name=self._first_text(row, "person_name"),
            sales_rep_id=self._resolve_canonical_sales_rep_id(
                raw_record.organization_id,
                sales_rep_external_id,
            ),
            sales_rep_external_id=sales_rep_external_id,
            sales_rep_code=self._first_text(row, "sales_manager_code"),
            sales_rep_name=self._first_text(row, "sales_manager_name"),
            working_zone_id=self._resolve_canonical_working_zone_id(
                raw_record.organization_id,
                working_zone_external_id,
            ),
            working_zone_external_id=working_zone_external_id,
            working_zone_code=self._first_text(row, "room_code"),
            working_zone_name=self._first_text(row, "room_name"),
            visit_date=visit_date,
            visit_start_time=visit_start_time,
            visit_end_time=visit_end_time,
            visited_at=visit_start_time or visit_date,
            duration_seconds=source_duration,
            derived_duration_seconds=derived_duration,
            source_status_code=self._first_text(row, "visit_status"),
            normalized_status=normalized_status,
            display_status=(self._first_text(row, "visit_status") or normalized_status).upper(),
            is_planned=self._parse_yes_no(row.get("is_planned")),
            source_is_planned=self._first_text(row, "is_planned"),
            supervisor_external_id=self._first_text(row, "supervisor_id"),
            start_latitude=start_latitude,
            start_longitude=start_longitude,
            end_latitude=end_latitude,
            end_longitude=end_longitude,
            note=note,
            person_types=self._list_of_dicts(row, "person_types"),
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=source_external_id,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._visit_quality_for_status(
                status=status,
                customer_external_id=customer_external_id,
                sales_rep_external_id=sales_rep_external_id,
            ),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
                "visit_start_location": self._clean_text(row.get("visit_start_location")),
                "visit_end_location": self._clean_text(row.get("visit_end_location")),
                "duration_source": "source"
                if source_duration is not None
                else ("derived" if derived_duration is not None else None),
            },
        )

    def _build_canonical_visit_stocks(
        self,
        *,
        raw_record: SmartUpRawRecord,
        payload: dict[str, Any],
        status: str,
        visit: CanonicalVisit,
    ) -> list[CanonicalVisitStock]:
        rows = self._nested_object_rows(payload.get("stocks"))
        items: list[CanonicalVisitStock] = []
        for index, item in enumerate(rows, start=1):
            product_external_id = self._first_text(
                item,
                "product_id",
                "product_code",
                "inventory_code",
                "code",
            )
            items.append(
                CanonicalVisitStock(
                    id=canonical_row_uuid(
                        "canonical_visit_stocks",
                        raw_record.organization_id,
                        visit.source_external_id,
                        index,
                    ),
                    organization_id=raw_record.organization_id,
                    visit_id=visit.id,
                    visit_external_id=visit.source_external_id,
                    line_number=index,
                    product_id=self._resolve_canonical_product_id(
                        raw_record.organization_id,
                        product_external_id,
                    ),
                    product_external_id=product_external_id,
                    product_code=self._first_text(item, "product_code", "inventory_code"),
                    product_name=self._first_text(item, "product_name", "name", "short_name"),
                    quantity=self._parse_optional_decimal(
                        item.get("quantity") or item.get("stock_quant") or item.get("quant"),
                    ),
                    expiry_date=self._parse_source_datetime(item.get("expiry_date")),
                    card_code=self._first_text(item, "card_code"),
                    serial_number=self._first_text(item, "serial_number"),
                    inventory_kind=self._first_text(item, "inventory_kind"),
                    unavailable_reason=self._first_text(
                        item,
                        "unavailable_reason",
                        "reason",
                    ),
                    source_system="smartup",
                    source_endpoint=raw_record.source_endpoint,
                    source_external_id=f"{visit.source_external_id}:stock:{index}",
                    source_raw_record_id=raw_record.id,
                    request_filial_id=raw_record.request_filial_id,
                    response_filial_id=raw_record.response_filial_id,
                    request_company_id=raw_record.request_company_id,
                    request_project_code=raw_record.request_project_code,
                    source_raw_batch_id=raw_record.batch_id,
                    data_quality_status=self._quality_for_status(status),
                    imported_at=raw_record.imported_at,
                    last_synced_at=raw_record.source_updated_at,
                    metadata={"source_entity": raw_record.entity_type, "source_endpoint": raw_record.source_endpoint},
                ),
            )
        return items

    def _build_canonical_visit_quiz_answers(
        self,
        *,
        raw_record: SmartUpRawRecord,
        payload: dict[str, Any],
        status: str,
        visit: CanonicalVisit,
    ) -> list[CanonicalVisitQuizAnswer]:
        items: list[CanonicalVisitQuizAnswer] = []
        quiz_groups = self._nested_object_rows(payload.get("quizzes"))
        line_number = 0
        for quiz_index, quiz_group in enumerate(quiz_groups, start=1):
            quiz_sets = self._nested_object_rows(quiz_group.get("quiz_sets"))
            for set_index, quiz_set in enumerate(quiz_sets, start=1):
                answers = self._nested_object_rows(
                    quiz_set.get("answers"),
                    quiz_set.get("quiz_answers"),
                    quiz_set.get("questions"),
                )
                if not answers:
                    answer_value = self._first_text(quiz_set, "answer", "value")
                    question_text = self._first_text(quiz_set, "question_text", "question_name", "question")
                    question_external_id = self._first_text(
                        quiz_set,
                        "question_id",
                        "question_code",
                        "code",
                    )
                    if answer_value is None and question_text is None and question_external_id is None:
                        continue
                    answers = [quiz_set]
                for answer_index, answer in enumerate(answers, start=1):
                    line_number += 1
                    items.append(
                        CanonicalVisitQuizAnswer(
                            id=canonical_row_uuid(
                                "canonical_visit_quiz_answers",
                                raw_record.organization_id,
                                visit.source_external_id,
                                line_number,
                            ),
                            organization_id=raw_record.organization_id,
                            visit_id=visit.id,
                            visit_external_id=visit.source_external_id,
                            quiz_external_id=self._first_text(
                                quiz_set,
                                "quiz_set_id",
                                "quiz_id",
                                "id",
                                "code",
                            )
                            or self._first_text(quiz_group, "quiz_id", "id", "code"),
                            quiz_name=self._first_text(quiz_set, "quiz_name", "name")
                            or self._first_text(quiz_group, "quiz_name", "name"),
                            question_external_id=self._first_text(
                                answer,
                                "question_id",
                                "question_code",
                                "code",
                            ),
                            question_text=self._first_text(
                                answer,
                                "question_text",
                                "question_name",
                                "question",
                                "name",
                            ),
                            answer_value=self._first_text(
                                answer,
                                "answer",
                                "value",
                                "answer_value",
                            ),
                            answer_type=self._first_text(
                                answer,
                                "answer_type",
                                "type",
                            ),
                            photo_sha=self._first_text(
                                answer,
                                "photo_sha",
                                "sha",
                            ),
                            line_number=line_number,
                            source_system="smartup",
                            source_endpoint=raw_record.source_endpoint,
                            source_external_id=f"{visit.source_external_id}:quiz:{line_number}",
                            source_raw_record_id=raw_record.id,
                            request_filial_id=raw_record.request_filial_id,
                            response_filial_id=raw_record.response_filial_id,
                            request_company_id=raw_record.request_company_id,
                            request_project_code=raw_record.request_project_code,
                            source_raw_batch_id=raw_record.batch_id,
                            data_quality_status=self._quality_for_status(status),
                            imported_at=raw_record.imported_at,
                            last_synced_at=raw_record.source_updated_at,
                            metadata={
                                "source_entity": raw_record.entity_type,
                                "source_endpoint": raw_record.source_endpoint,
                                "quiz_group_index": quiz_index,
                                "quiz_set_index": set_index,
                                "answer_index": answer_index,
                            },
                        ),
                    )
        return items

    def _build_canonical_visit_equipments(
        self,
        *,
        raw_record: SmartUpRawRecord,
        payload: dict[str, Any],
        status: str,
        visit: CanonicalVisit,
    ) -> list[CanonicalVisitEquipment]:
        rows = self._nested_object_rows(payload.get("equipments"))
        items: list[CanonicalVisitEquipment] = []
        for index, item in enumerate(rows, start=1):
            source_external_id = self._first_text(
                item,
                "equipment_id",
                "serial_number",
                "equipment_code",
                "code",
                "name",
            )
            if source_external_id is None:
                continue
            items.append(
                CanonicalVisitEquipment(
                    id=canonical_row_uuid(
                        "canonical_visit_equipments",
                        raw_record.organization_id,
                        visit.source_external_id,
                        index,
                    ),
                    organization_id=raw_record.organization_id,
                    visit_id=visit.id,
                    visit_external_id=visit.source_external_id,
                    equipment_external_id=self._first_text(item, "equipment_id", "id") or source_external_id,
                    equipment_code=self._first_text(item, "equipment_code", "code"),
                    equipment_name=self._first_text(item, "equipment_name", "name"),
                    serial_number=self._first_text(item, "serial_number"),
                    status_code=self._first_text(item, "status", "status_code"),
                    note=self._first_text(item, "note", "comment"),
                    line_number=index,
                    source_system="smartup",
                    source_endpoint=raw_record.source_endpoint,
                    source_external_id=f"{visit.source_external_id}:equipment:{index}",
                    source_raw_record_id=raw_record.id,
                    request_filial_id=raw_record.request_filial_id,
                    response_filial_id=raw_record.response_filial_id,
                    request_company_id=raw_record.request_company_id,
                    request_project_code=raw_record.request_project_code,
                    source_raw_batch_id=raw_record.batch_id,
                    data_quality_status=self._quality_for_status(status),
                    imported_at=raw_record.imported_at,
                    last_synced_at=raw_record.source_updated_at,
                    metadata={"source_entity": raw_record.entity_type, "source_endpoint": raw_record.source_endpoint},
                ),
            )
        return items

    def _build_canonical_visit_comments(
        self,
        *,
        raw_record: SmartUpRawRecord,
        payload: dict[str, Any],
        status: str,
        visit: CanonicalVisit,
    ) -> list[CanonicalVisitComment]:
        rows = self._nested_object_rows(payload.get("comments"))
        items: list[CanonicalVisitComment] = []
        for index, item in enumerate(rows, start=1):
            comment_text = self._first_text(item, "comment", "text", "note", "value")
            if comment_text is None:
                continue
            items.append(
                CanonicalVisitComment(
                    id=canonical_row_uuid(
                        "canonical_visit_comments",
                        raw_record.organization_id,
                        visit.source_external_id,
                        index,
                    ),
                    organization_id=raw_record.organization_id,
                    visit_id=visit.id,
                    visit_external_id=visit.source_external_id,
                    comment_text=comment_text,
                    comment_type=self._first_text(item, "type", "comment_type", "name"),
                    created_by_external_id=self._first_text(
                        item,
                        "created_by",
                        "user_id",
                        "author_id",
                    ),
                    created_at_source=self._parse_source_datetime(
                        item.get("created_at") or item.get("created_on"),
                    ),
                    line_number=index,
                    source_system="smartup",
                    source_endpoint=raw_record.source_endpoint,
                    source_external_id=f"{visit.source_external_id}:comment:{index}",
                    source_raw_record_id=raw_record.id,
                    request_filial_id=raw_record.request_filial_id,
                    response_filial_id=raw_record.response_filial_id,
                    request_company_id=raw_record.request_company_id,
                    request_project_code=raw_record.request_project_code,
                    source_raw_batch_id=raw_record.batch_id,
                    data_quality_status=self._quality_for_status(status),
                    imported_at=raw_record.imported_at,
                    last_synced_at=raw_record.source_updated_at,
                    metadata={"source_entity": raw_record.entity_type, "source_endpoint": raw_record.source_endpoint},
                ),
            )
        return items

    def _build_canonical_media_assets(
        self,
        *,
        raw_record: SmartUpRawRecord,
        payload: dict[str, Any],
        status: str,
        visit: CanonicalVisit,
        visit_index: int,
    ) -> list[CanonicalMediaAsset]:
        references = self._collect_media_references(payload)
        items: list[CanonicalMediaAsset] = []
        for index, reference in enumerate(references, start=1):
            source_identity = reference.get("sha") or reference.get("reference")
            if source_identity is None:
                continue
            items.append(
                CanonicalMediaAsset(
                    id=canonical_row_uuid(
                        "canonical_media_assets",
                        raw_record.organization_id,
                        reference.get("sha") or f"{visit.source_external_id}:{index}",
                        visit_index,
                    ),
                    organization_id=raw_record.organization_id,
                    media_id=reference.get("sha") or f"{visit.source_external_id}:{index}",
                    source_entity_type=reference.get("source_entity_type"),
                    source_entity_id=reference.get("source_entity_id"),
                    visit_id=visit.id,
                    visit_external_id=visit.source_external_id,
                    media_type=reference.get("media_type"),
                    source_sha=reference.get("sha"),
                    source_reference=reference.get("reference"),
                    download_status="not_requested",
                    local_path=None,
                    mime_type=None,
                    source_system="smartup",
                    source_endpoint=raw_record.source_endpoint,
                    source_external_id=f"{visit.source_external_id}:media:{reference.get('sha') or index}",
                    source_raw_record_id=raw_record.id,
                    request_filial_id=raw_record.request_filial_id,
                    response_filial_id=raw_record.response_filial_id,
                    request_company_id=raw_record.request_company_id,
                    request_project_code=raw_record.request_project_code,
                    source_raw_batch_id=raw_record.batch_id,
                    data_quality_status=self._quality_for_status(status),
                    imported_at=raw_record.imported_at,
                    last_synced_at=raw_record.source_updated_at,
                    metadata={"source_entity": raw_record.entity_type, "source_endpoint": raw_record.source_endpoint},
                ),
            )
        return items

    def _build_canonical_order(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalOrder | None:
        source_external_id = self._first_text(row, "deal_id", "external_id", "delivery_number")
        if source_external_id is None:
            return None
        customer_external_id = self._first_text(
            row,
            "person_id",
            "person_code",
            "client_id",
            "client_code",
        )
        sales_rep_external_id = self._first_text(
            row,
            "sales_manager_id",
            "sales_manager_code",
            "user_id",
            "responsible_person_code",
        )
        working_zone_external_id = self._first_text(
            row,
            "room_id",
            "room_code",
            "warehouse_id",
            "warehouse_code",
        )
        order_products = self._line_items_from_order_row(row)
        aggregate = self._aggregate_order_line_metrics(order_products)
        status_code = self._first_text(row, "status")
        normalized_status = self._normalize_smartup_status(status_code)
        return CanonicalOrder(
            id=canonical_row_uuid("canonical_orders", raw_record.organization_id, source_external_id),
            organization_id=raw_record.organization_id,
            order_id=self._first_text(row, "deal_id", "external_id"),
            deal_id=self._first_text(row, "deal_id"),
            external_document_id=self._first_text(row, "external_id"),
            order_number=self._first_text(
                row,
                "deal_id",
                "code",
                "order_no",
                "delivery_number",
            ),
            delivery_number=self._first_text(row, "delivery_number"),
            order_at=self._parse_source_datetime(
                row.get("deal_time") or row.get("created_on") or row.get("deal_date"),
            ),
            delivery_date=self._parse_source_datetime(row.get("delivery_date")),
            customer_id=self._resolve_canonical_customer_id(raw_record.organization_id, customer_external_id),
            customer_external_id=customer_external_id,
            customer_code=self._first_text(row, "person_code", "client_code"),
            customer_name=self._first_text(row, "person_name", "client_name"),
            sales_rep_id=self._resolve_canonical_sales_rep_id(
                raw_record.organization_id,
                sales_rep_external_id,
            ),
            sales_rep_external_id=sales_rep_external_id,
            working_zone_id=self._resolve_canonical_working_zone_id(
                raw_record.organization_id,
                working_zone_external_id,
            ),
            working_zone_external_id=working_zone_external_id,
            source_status_code=status_code,
            source_status_name=status_code,
            normalized_status=normalized_status,
            display_status=normalized_status.upper(),
            total_amount=self._parse_decimal(row.get("total_amount") or row.get("amount")),
            currency_code=self._normalize_currency_code(self._first_text(row, "currency_code", "currency")),
            source_currency_code=self._first_text(row, "currency_code", "currency"),
            item_count=len(order_products),
            ordered_quantity=aggregate["ordered_quantity"],
            sold_quantity=aggregate["sold_quantity"],
            has_realization_evidence=aggregate["has_realization_evidence"],
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=source_external_id,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
            },
        )

    def _build_canonical_sale(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
        order: CanonicalOrder,
    ) -> CanonicalSale | None:
        order_products = self._line_items_from_order_row(row)
        aggregate = self._aggregate_order_line_metrics(order_products)
        if not aggregate["has_realization_evidence"]:
            return None
        source_external_id = order.source_external_id
        realization_basis = "sold_quant" if aggregate["sold_quantity"] > Decimal("0") else "sold_amount"
        return CanonicalSale(
            id=canonical_row_uuid("canonical_sales", raw_record.organization_id, source_external_id),
            organization_id=raw_record.organization_id,
            sale_id=source_external_id,
            order_id=order.id,
            order_external_id=order.source_external_id,
            deal_id=order.deal_id,
            sale_number=order.order_number,
            sale_at=order.order_at,
            closed_at=order.delivery_date,
            customer_id=order.customer_id,
            customer_external_id=order.customer_external_id,
            customer_code=order.customer_code,
            customer_name=order.customer_name,
            sales_rep_id=order.sales_rep_id,
            sales_rep_external_id=order.sales_rep_external_id,
            working_zone_id=order.working_zone_id,
            working_zone_external_id=order.working_zone_external_id,
            source_status_code=order.source_status_code,
            source_status_name=order.source_status_name,
            normalized_status=order.normalized_status,
            display_status=order.display_status,
            total_amount=self._parse_decimal(row.get("total_amount") or row.get("amount")),
            currency_code=order.currency_code,
            source_currency_code=order.source_currency_code,
            item_count=len(order_products),
            ordered_quantity=aggregate["ordered_quantity"],
            sold_quantity=aggregate["sold_quantity"],
            returned_quantity=aggregate["returned_quantity"],
            realization_basis=realization_basis,
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=source_external_id,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
            },
        )

    def _build_canonical_sale_items(
        self,
        *,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
        order: CanonicalOrder,
        sale: CanonicalSale | None,
    ) -> list[CanonicalSaleItem]:
        order_products = self._line_items_from_order_row(row)
        sale_items: list[CanonicalSaleItem] = []
        for index, item in enumerate(order_products, start=1):
            product_external_id = self._first_text(
                item,
                "product_code",
                "inventory_code",
                "code",
            )
            warehouse_external_id = self._first_text(
                item,
                "warehouse_id",
                "warehouse_code",
            ) or order.working_zone_external_id
            price_type_code = self._first_text(item, "price_type_code", "card_code")
            ordered_quantity = self._parse_decimal(item.get("order_quant") or item.get("quantity"))
            sold_quantity = self._line_sold_quantity(item)
            returned_quantity = self._parse_decimal(item.get("return_quant"))
            amount = self._parse_decimal(
                item.get("amount") or item.get("sold_amount") or item.get("total_amount"),
            )
            has_realization_evidence = sold_quantity > Decimal("0") or amount > Decimal("0")
            sale_items.append(
                CanonicalSaleItem(
                    id=canonical_row_uuid(
                        "canonical_sale_items",
                        raw_record.organization_id,
                        order.source_external_id,
                        index,
                    ),
                    organization_id=raw_record.organization_id,
                    sale_id=sale.id if sale is not None else None,
                    order_id=order.id,
                    sale_external_id=sale.source_external_id if sale is not None else None,
                    order_external_id=order.source_external_id,
                    line_number=index,
                    product_id=self._resolve_canonical_product_id(
                        raw_record.organization_id,
                        product_external_id,
                    ),
                    product_external_id=product_external_id,
                    product_code=self._first_text(item, "product_code", "inventory_code", "code"),
                    product_name=self._first_text(item, "product_name", "name", "short_name"),
                    warehouse_id=self._resolve_canonical_warehouse_id(
                        raw_record.organization_id,
                        warehouse_external_id,
                    ),
                    warehouse_external_id=warehouse_external_id,
                    warehouse_code=self._first_text(item, "warehouse_code") or order.working_zone_external_id,
                    price_type_id=self._resolve_canonical_price_type_id(
                        raw_record.organization_id,
                        price_type_code,
                    ),
                    price_type_code=price_type_code,
                    source_status_code=order.source_status_code,
                    ordered_quantity=ordered_quantity,
                    sold_quantity=sold_quantity,
                    returned_quantity=returned_quantity,
                    unit_price=self._parse_decimal(item.get("price") or item.get("product_price")),
                    amount=amount,
                    vat_percent=self._parse_optional_decimal(item.get("vat_percent")),
                    vat_amount=self._parse_optional_decimal(item.get("vat_amount")),
                    margin_amount=self._parse_optional_decimal(item.get("margin_amount")),
                    currency_code=order.currency_code,
                    source_currency_code=order.source_currency_code,
                    has_realization_evidence=has_realization_evidence,
                    source_system="smartup",
                    source_endpoint=raw_record.source_endpoint,
                    source_external_id=f"{order.source_external_id}:{index}",
                    source_raw_record_id=raw_record.id,
                    request_filial_id=raw_record.request_filial_id,
                    response_filial_id=raw_record.response_filial_id,
                    request_company_id=raw_record.request_company_id,
                    request_project_code=raw_record.request_project_code,
                    source_raw_batch_id=raw_record.batch_id,
                    data_quality_status=self._quality_for_status(status),
                    imported_at=raw_record.imported_at,
                    last_synced_at=raw_record.source_updated_at,
                    metadata={
                        "source_entity": raw_record.entity_type,
                        "source_endpoint": raw_record.source_endpoint,
                    },
                ),
            )
        return sale_items

    def _build_canonical_payment(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalPayment | None:
        source_external_id = self._first_text(row, "cashin_id", "external_id", "payment_id")
        if source_external_id is None:
            return None
        customer_external_id = self._first_text(
            row,
            "client_id",
            "person_id",
            "client_code",
            "person_code",
        )
        source_currency_code = self._first_text(row, "currency_code", "currency")
        return CanonicalPayment(
            id=canonical_row_uuid("canonical_payments", raw_record.organization_id, source_external_id),
            organization_id=raw_record.organization_id,
            payment_id=source_external_id,
            cashin_id=self._first_text(row, "cashin_id"),
            cashin_number=self._first_text(row, "cashin_number"),
            paid_at=self._parse_source_datetime(row.get("cashin_time") or row.get("cashin_date")),
            cashin_date=self._first_text(row, "cashin_date"),
            cashin_time=self._first_text(row, "cashin_time"),
            customer_id=self._resolve_canonical_customer_id(raw_record.organization_id, customer_external_id),
            customer_external_id=customer_external_id,
            customer_code=self._first_text(row, "client_code", "person_code"),
            customer_name=self._first_text(row, "client_name", "person_name"),
            cashbox_code=self._first_text(row, "cashbox_code"),
            bank_account_code=self._first_text(row, "bank_account_code"),
            source_payment_type_code=self._first_text(row, "payment_type_code"),
            normalized_payment_type=self._normalize_payment_type(
                self._first_text(row, "payment_type_code"),
            ),
            amount=self._parse_decimal(row.get("amount")),
            currency_code=self._normalize_currency_code(source_currency_code),
            source_currency_code=source_currency_code,
            posted=self._first_text(row, "posted"),
            purpose=self._first_text(row, "purpose"),
            subfilial_code=self._first_text(row, "subfilial_code"),
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=source_external_id,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
            },
        )

    def _build_canonical_payment_allocations(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
        payment: CanonicalPayment,
    ) -> list[CanonicalPaymentAllocation]:
        references = self._payment_reference_candidates(row)
        if not references:
            return []
        allocations: list[CanonicalPaymentAllocation] = []
        for index, reference in enumerate(references, start=1):
            order_id = self._resolve_canonical_order_id(
                raw_record.organization_id,
                reference["external_id"],
            )
            sale_id = self._resolve_canonical_sale_id(
                raw_record.organization_id,
                reference["external_id"],
            )
            if order_id is None and sale_id is None:
                continue
            allocated_amount: Decimal | None = None
            if len(references) == 1:
                allocated_amount = payment.amount
            source_external_id = f"{payment.source_external_id}:{reference['external_id']}:{index}"
            allocations.append(
                CanonicalPaymentAllocation(
                    id=canonical_row_uuid(
                        "canonical_payment_allocations",
                        raw_record.organization_id,
                        source_external_id,
                    ),
                    organization_id=raw_record.organization_id,
                    payment_id=payment.id,
                    sale_id=sale_id,
                    sale_external_id=reference["external_id"] if sale_id is not None else None,
                    order_id=order_id,
                    order_external_id=reference["external_id"] if order_id is not None else None,
                    allocated_amount=allocated_amount,
                    currency_code=payment.currency_code,
                    allocation_type="exact_reference" if allocated_amount is not None else "multi_reference",
                    source_reference=reference,
                    source_system="smartup",
                    source_endpoint=raw_record.source_endpoint,
                    source_external_id=source_external_id,
                    source_raw_record_id=raw_record.id,
                    request_filial_id=raw_record.request_filial_id,
                    response_filial_id=raw_record.response_filial_id,
                    request_company_id=raw_record.request_company_id,
                    request_project_code=raw_record.request_project_code,
                    source_raw_batch_id=raw_record.batch_id,
                    data_quality_status=self._quality_for_status(status),
                    imported_at=raw_record.imported_at,
                    last_synced_at=raw_record.source_updated_at,
                    metadata={
                        "source_entity": raw_record.entity_type,
                        "source_endpoint": raw_record.source_endpoint,
                    },
                ),
            )
        return allocations

    def _build_financial_account_from_payment(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalFinancialAccount | None:
        account_code = self._first_text(row, "cashbox_code", "bank_account_code")
        if account_code is None:
            return None
        account_type = "cashbox" if self._first_text(row, "cashbox_code") is not None else "bank_account"
        return CanonicalFinancialAccount(
            id=canonical_row_uuid("canonical_financial_accounts", raw_record.organization_id, account_type, account_code),
            organization_id=raw_record.organization_id,
            account_code=account_code,
            account_name=account_code,
            account_type=account_type,
            source_account_id=account_code,
            currency_code=self._normalize_currency_code(self._first_text(row, "currency_code")),
            source_currency_code=self._first_text(row, "currency_code"),
            bank_account_code=self._first_text(row, "bank_account_code"),
            cashbox_code=self._first_text(row, "cashbox_code"),
            subfilial_code=self._first_text(row, "subfilial_code"),
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=f"{account_type}:{account_code}",
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={"source_entity": raw_record.entity_type, "source_endpoint": raw_record.source_endpoint},
        )

    def _build_financial_operation_from_payment(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalFinancialOperation | None:
        source_external_id = self._first_text(row, "cashin_id", "external_id", "payment_id")
        if source_external_id is None:
            return None
        amount = self._parse_decimal(row.get("amount"))
        source_currency_code = self._first_text(row, "currency_code")
        account = self._build_financial_account_from_payment(raw_record, row, status)
        customer_external_id = self._first_text(row, "client_id", "person_id", "client_code", "person_code")
        return CanonicalFinancialOperation(
            id=canonical_row_uuid("canonical_financial_operations", raw_record.organization_id, "payment", source_external_id),
            organization_id=raw_record.organization_id,
            operation_id=source_external_id,
            operation_number=self._first_text(row, "cashin_number"),
            operation_at=self._parse_source_datetime(row.get("cashin_time") or row.get("cashin_date")),
            operation_date=self._parse_source_datetime(row.get("cashin_date")),
            source_operation_type=self._first_text(row, "payment_type_code"),
            normalized_operation_type="customer_payment",
            direction=CanonicalFinancialDirection.INFLOW,
            amount=amount,
            source_amount=amount,
            currency_code=self._normalize_currency_code(source_currency_code),
            source_currency_code=source_currency_code,
            account_id=account.id if account is not None else None,
            account_external_id=account.source_external_id if account is not None else None,
            account_code=account.account_code if account is not None else self._first_text(row, "cashbox_code", "bank_account_code"),
            counterparty_type="customer",
            counterparty_customer_id=self._resolve_canonical_customer_id(raw_record.organization_id, customer_external_id),
            counterparty_external_id=customer_external_id,
            counterparty_code=self._first_text(row, "client_code", "person_code"),
            counterparty_name=self._first_text(row, "client_name", "person_name"),
            purpose=self._first_text(row, "purpose"),
            note=self._first_text(row, "note"),
            posted=self._first_text(row, "posted"),
            source_document_type="cashin",
            source_document_external_id=source_external_id,
            reference_codes=[],
            is_internal_transfer=False,
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=f"payment:{source_external_id}",
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
                "cashbox_code": self._first_text(row, "cashbox_code"),
                "bank_account_code": self._first_text(row, "bank_account_code"),
            },
        )

    def _build_financial_account_from_cash_operation(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalFinancialAccount | None:
        account_code = self._first_text(row, "cashbox_code", "bank_account_code", "corr_bank_account_code")
        coa_code = self._first_text(row, "corr_coa_code")
        if account_code is None and coa_code is None:
            return None
        account_type = "cash_operation_account"
        source_key = account_code or coa_code
        return CanonicalFinancialAccount(
            id=canonical_row_uuid("canonical_financial_accounts", raw_record.organization_id, account_type, source_key),
            organization_id=raw_record.organization_id,
            account_code=account_code or coa_code,
            account_name=account_code or coa_code,
            account_type=account_type,
            source_account_id=source_key,
            currency_code=self._normalize_currency_code(self._first_text(row, "currency_code")),
            source_currency_code=self._first_text(row, "currency_code"),
            bank_account_code=self._first_text(row, "bank_account_code", "corr_bank_account_code"),
            cashbox_code=self._first_text(row, "cashbox_code"),
            coa_code=coa_code,
            subfilial_code=self._first_text(row, "subfilial_code"),
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=f"{account_type}:{source_key}",
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={"source_entity": raw_record.entity_type, "source_endpoint": raw_record.source_endpoint},
        )

    def _build_financial_operation_from_cash_operation(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
        *,
        overlap_signatures: set[tuple[str, str, str, str]],
    ) -> CanonicalFinancialOperation | None:
        source_external_id = self._first_text(row, "operation_id", "external_id")
        if source_external_id is None:
            return None
        amount = self._parse_decimal(row.get("amount"))
        source_currency_code = self._first_text(row, "currency_code")
        direction = self._direction_from_cashflow_kind(self._first_text(row, "cashflow_kind"))
        account = self._build_financial_account_from_cash_operation(raw_record, row, status)
        counterparty_external_id = self._first_text(row, "corr_person_code")
        signature = self._payment_like_signature_from_cash_operation(row)
        overlap = signature in overlap_signatures if signature is not None else False
        quality = self._quality_for_status(status)
        if overlap and quality == CanonicalDataQualityStatus.VERIFIED:
            quality = CanonicalDataQualityStatus.PARTIAL
        return CanonicalFinancialOperation(
            id=canonical_row_uuid("canonical_financial_operations", raw_record.organization_id, "cash_operation", source_external_id),
            organization_id=raw_record.organization_id,
            operation_id=source_external_id,
            operation_number=self._first_text(row, "operation_number"),
            operation_at=self._parse_source_datetime(row.get("operation_date")),
            operation_date=self._parse_source_datetime(row.get("operation_date")),
            source_operation_type=self._first_text(row, "cashflow_kind", "cashflow_reason_code"),
            normalized_operation_type="cash_operation",
            direction=direction,
            amount=amount,
            source_amount=amount,
            currency_code=self._normalize_currency_code(source_currency_code),
            source_currency_code=source_currency_code,
            account_id=account.id if account is not None else None,
            account_external_id=account.source_external_id if account is not None else None,
            account_code=account.account_code if account is not None else None,
            counterparty_type="customer" if counterparty_external_id else "unknown",
            counterparty_customer_id=self._resolve_canonical_customer_id(raw_record.organization_id, counterparty_external_id),
            counterparty_external_id=counterparty_external_id,
            counterparty_code=counterparty_external_id,
            counterparty_name=None,
            purpose=self._first_text(row, "purpose"),
            note=self._first_text(row, "note"),
            posted=self._first_text(row, "posted"),
            source_document_type="cash_operation",
            source_document_external_id=source_external_id,
            reference_codes=self._list_of_dicts(row, "ref_codes"),
            is_internal_transfer=direction == CanonicalFinancialDirection.TRANSFER,
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=f"cash_operation:{source_external_id}",
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=quality,
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
                "cashflow_reason_code": self._first_text(row, "cashflow_reason_code"),
                "corr_coa_code": self._first_text(row, "corr_coa_code"),
                "overlaps_payment": overlap,
            },
        )

    def _build_financial_account_from_bank_operation(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalFinancialAccount | None:
        account_code = self._first_text(row, "bank_account_code", "corr_bank_account_code")
        if account_code is None:
            return None
        return CanonicalFinancialAccount(
            id=canonical_row_uuid("canonical_financial_accounts", raw_record.organization_id, "bank_operation_account", account_code),
            organization_id=raw_record.organization_id,
            account_code=account_code,
            account_name=account_code,
            account_type="bank_account",
            source_account_id=account_code,
            currency_code=self._normalize_currency_code(self._first_text(row, "currency_code")),
            source_currency_code=self._first_text(row, "currency_code"),
            bank_account_code=self._first_text(row, "bank_account_code"),
            coa_code=self._first_text(row, "corr_coa_code"),
            subfilial_code=self._first_text(row, "subfilial_code"),
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=f"bank_account:{account_code}",
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={"source_entity": raw_record.entity_type, "source_endpoint": raw_record.source_endpoint},
        )

    def _build_financial_operation_from_bank_operation(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalFinancialOperation | None:
        source_external_id = self._first_text(row, "operation_id", "external_id")
        if source_external_id is None:
            return None
        amount = self._parse_decimal(row.get("amount"))
        source_currency_code = self._first_text(row, "currency_code")
        account = self._build_financial_account_from_bank_operation(raw_record, row, status)
        direction = self._direction_from_bank_operation(row)
        return CanonicalFinancialOperation(
            id=canonical_row_uuid("canonical_financial_operations", raw_record.organization_id, "bank_operation", source_external_id),
            organization_id=raw_record.organization_id,
            operation_id=source_external_id,
            operation_number=self._first_text(row, "operation_number", "bank_trans_number"),
            operation_at=self._parse_source_datetime(row.get("operation_date") or row.get("bank_trans_date")),
            operation_date=self._parse_source_datetime(row.get("operation_date") or row.get("bank_trans_date")),
            source_operation_type=self._first_text(row, "cashflow_kind", "payment_code"),
            normalized_operation_type="bank_operation",
            direction=direction,
            amount=amount,
            source_amount=amount,
            currency_code=self._normalize_currency_code(source_currency_code),
            source_currency_code=source_currency_code,
            account_id=account.id if account is not None else None,
            account_external_id=account.source_external_id if account is not None else None,
            account_code=account.account_code if account is not None else None,
            counterparty_type="unknown",
            counterparty_customer_id=None,
            counterparty_external_id=self._first_text(row, "corr_person_code"),
            counterparty_code=self._first_text(row, "corr_person_code"),
            counterparty_name=None,
            purpose=self._first_text(row, "purpose"),
            note=self._first_text(row, "note"),
            posted=self._first_text(row, "posted"),
            source_document_type="bank_operation",
            source_document_external_id=source_external_id,
            reference_codes=self._list_of_dicts(row, "ref_codes"),
            is_internal_transfer=direction == CanonicalFinancialDirection.TRANSFER,
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=f"bank_operation:{source_external_id}",
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
                "payment_code": self._first_text(row, "payment_code"),
            },
        )

    def _build_canonical_customer_return(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalCustomerReturn | None:
        source_external_id = self._first_text(row, "deal_id", "external_id", "return_id")
        if source_external_id is None:
            return None
        customer_external_id = self._first_text(
            row,
            "person_id",
            "person_code",
            "client_id",
            "client_code",
        )
        sales_rep_external_id = self._first_text(
            row,
            "sales_manager_id",
            "sales_manager_code",
            "manager_code",
        )
        original_external_id = self._first_text(row, "order_deal_id", "order_id")
        return_products = self._line_items_from_return_row(row)
        returned_quantity = sum(
            (self._parse_decimal(item.get("return_quant")) for item in return_products),
            start=Decimal("0"),
        )
        status_code = self._first_text(row, "status")
        normalized_status = self._normalize_smartup_status(status_code)
        return CanonicalCustomerReturn(
            id=canonical_row_uuid(
                "canonical_customer_returns",
                raw_record.organization_id,
                source_external_id,
            ),
            organization_id=raw_record.organization_id,
            return_id=self._first_text(row, "deal_id", "return_id"),
            deal_id=self._first_text(row, "deal_id"),
            order_deal_id=original_external_id,
            external_document_id=self._first_text(row, "external_id"),
            return_number=self._first_text(
                row,
                "invoice_number",
                "delivery_number",
                "batch_number",
            ),
            return_at=self._parse_source_datetime(row.get("deal_time")),
            booked_at=self._parse_source_datetime(row.get("booked_date")),
            delivery_date=self._parse_source_datetime(row.get("delivery_date")),
            customer_id=self._resolve_canonical_customer_id(raw_record.organization_id, customer_external_id),
            customer_external_id=customer_external_id,
            customer_code=self._first_text(row, "person_code", "client_code"),
            customer_name=self._first_text(row, "person_name", "client_name"),
            sales_rep_id=self._resolve_canonical_sales_rep_id(
                raw_record.organization_id,
                sales_rep_external_id,
            ),
            sales_rep_external_id=sales_rep_external_id,
            source_status_code=status_code,
            source_status_name=status_code,
            normalized_status=normalized_status,
            display_status=normalized_status.upper(),
            total_amount=self._parse_decimal(row.get("total_amount") or row.get("amount")),
            currency_code=self._normalize_currency_code(
                self._first_text(row, "currency_code", "currency"),
            ),
            source_currency_code=self._first_text(row, "currency_code", "currency"),
            return_reason_id=self._first_text(row, "return_reason_id"),
            return_reason_code=self._first_text(row, "return_reason_code"),
            linked_order_id=self._resolve_canonical_order_id(
                raw_record.organization_id,
                original_external_id,
            ),
            linked_order_external_id=original_external_id,
            linked_sale_id=self._resolve_canonical_sale_id(
                raw_record.organization_id,
                original_external_id,
            ),
            linked_sale_external_id=original_external_id,
            item_count=len(return_products),
            returned_quantity=returned_quantity,
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=source_external_id,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
            },
        )

    def _build_canonical_customer_return_items(
        self,
        *,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
        customer_return: CanonicalCustomerReturn,
    ) -> list[CanonicalCustomerReturnItem]:
        return_products = self._line_items_from_return_row(row)
        items: list[CanonicalCustomerReturnItem] = []
        for index, item in enumerate(return_products, start=1):
            product_external_id = self._first_text(
                item,
                "product_code",
                "product_id",
                "inventory_code",
            )
            warehouse_external_id = self._first_text(item, "warehouse_id", "warehouse_code")
            price_type_code = self._first_text(item, "price_type_code", "card_code")
            items.append(
                CanonicalCustomerReturnItem(
                    id=canonical_row_uuid(
                        "canonical_customer_return_items",
                        raw_record.organization_id,
                        customer_return.source_external_id,
                        index,
                    ),
                    organization_id=raw_record.organization_id,
                    customer_return_id=customer_return.id,
                    return_external_id=customer_return.source_external_id,
                    line_number=index,
                    product_id=self._resolve_canonical_product_id(
                        raw_record.organization_id,
                        product_external_id,
                    ),
                    product_external_id=product_external_id,
                    product_code=self._first_text(item, "product_code", "inventory_code"),
                    product_name=self._first_text(item, "product_name", "name", "short_name"),
                    warehouse_id=self._resolve_canonical_warehouse_id(
                        raw_record.organization_id,
                        warehouse_external_id,
                    ),
                    warehouse_external_id=warehouse_external_id,
                    warehouse_code=self._first_text(item, "warehouse_code"),
                    price_type_id=self._resolve_canonical_price_type_id(
                        raw_record.organization_id,
                        price_type_code,
                    ),
                    price_type_code=price_type_code,
                    returned_quantity=self._parse_decimal(item.get("return_quant")),
                    unit_price=self._parse_optional_decimal(
                        item.get("product_price") or item.get("price"),
                    ),
                    amount=self._parse_decimal(
                        item.get("sold_amount") or item.get("amount") or item.get("total_amount"),
                    ),
                    vat_percent=self._parse_optional_decimal(item.get("vat_percent")),
                    vat_amount=self._parse_optional_decimal(item.get("vat_amount")),
                    margin_amount=self._parse_optional_decimal(item.get("margin_amount")),
                    currency_code=customer_return.currency_code,
                    source_currency_code=customer_return.source_currency_code,
                    linked_order_id=customer_return.linked_order_id,
                    linked_sale_id=customer_return.linked_sale_id,
                    source_system="smartup",
                    source_endpoint=raw_record.source_endpoint,
                    source_external_id=f"{customer_return.source_external_id}:{index}",
                    source_raw_record_id=raw_record.id,
                    request_filial_id=raw_record.request_filial_id,
                    response_filial_id=raw_record.response_filial_id,
                    request_company_id=raw_record.request_company_id,
                    request_project_code=raw_record.request_project_code,
                    source_raw_batch_id=raw_record.batch_id,
                    data_quality_status=self._quality_for_status(status),
                    imported_at=raw_record.imported_at,
                    last_synced_at=raw_record.source_updated_at,
                    metadata={
                        "source_entity": raw_record.entity_type,
                        "source_endpoint": raw_record.source_endpoint,
                        "action_code": self._first_text(item, "action_code"),
                        "action_name": self._first_text(item, "action_name"),
                    },
                ),
            )
        return items

    def _build_canonical_inventory_balance(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalInventoryBalance | None:
        product_external_id = self._first_text(row, "product_id", "product_code", "inventory_code")
        warehouse_external_id = self._first_text(row, "warehouse_id", "warehouse_code")
        snapshot_date = self._parse_source_datetime(row.get("date"))
        if product_external_id is None or warehouse_external_id is None or snapshot_date is None:
            return None
        batch_number = self._first_text(row, "batch_number")
        card_code = self._first_text(row, "card_code")
        serial_number = self._first_text(row, "serial_number")
        grain_key = "|".join(
            part
            for part in (
                warehouse_external_id,
                product_external_id,
                batch_number or "",
                card_code or "",
                serial_number or "",
                snapshot_date.date().isoformat(),
            )
        )
        input_price = self._parse_optional_decimal(row.get("input_price"))
        quantity = self._parse_decimal(row.get("quantity"))
        valuation_amount = input_price * quantity if input_price is not None else None
        return CanonicalInventoryBalance(
            id=canonical_row_uuid("canonical_inventory_balances", raw_record.organization_id, grain_key),
            organization_id=raw_record.organization_id,
            snapshot_date=snapshot_date,
            warehouse_id=self._resolve_canonical_warehouse_id(raw_record.organization_id, warehouse_external_id),
            warehouse_external_id=warehouse_external_id,
            warehouse_code=self._first_text(row, "warehouse_code"),
            product_id=self._resolve_canonical_product_id(raw_record.organization_id, product_external_id),
            product_external_id=product_external_id,
            product_code=self._first_text(row, "product_code", "inventory_code"),
            product_name=self._first_text(row, "product_name", "name", "short_name"),
            quantity=quantity,
            available_quantity=self._parse_optional_decimal(row.get("available_quantity")),
            reserved_quantity=self._parse_optional_decimal(row.get("reserved_quantity")),
            input_price=input_price,
            valuation_amount=valuation_amount,
            currency_code=self._normalize_currency_code(self._first_text(row, "currency_code")),
            source_currency_code=self._first_text(row, "currency_code"),
            batch_number=batch_number,
            card_code=card_code,
            serial_number=serial_number,
            expiry_date=self._parse_source_datetime(row.get("expiry_date")),
            inventory_kind=self._first_text(row, "inventory_kind"),
            measure_code=self._first_text(row, "measure_code"),
            grain_key=grain_key,
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=grain_key,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={"source_entity": raw_record.entity_type, "source_endpoint": raw_record.source_endpoint},
        )

    def _build_canonical_purchase(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalPurchase | None:
        source_external_id = self._first_text(row, "purchase_id", "external_id", "purchase_number")
        if source_external_id is None:
            return None
        items = self._line_items_from_purchase_row(row)
        total_quantity = sum((self._parse_decimal(item.get("quantity")) for item in items), start=Decimal("0"))
        warehouse_external_id = self._first_text(row, "warehouse_code")
        base_quality = self._quality_for_status(status)
        header_quality = (
            base_quality if warehouse_external_id is not None else CanonicalDataQualityStatus.PARTIAL
        )
        metadata = {"source_entity": raw_record.entity_type, "source_endpoint": raw_record.source_endpoint}
        if warehouse_external_id is None:
            metadata["unresolved_reason"] = "UNRESOLVED_SOURCE_REFERENCE"
            metadata["missing_identity_type"] = "WAREHOUSE"
            metadata["available_source_fields"] = {
                "warehouse_code": row.get("warehouse_code"),
                "warehouse_external_id": row.get("warehouse_external_id"),
                "subfilial_code": row.get("subfilial_code"),
                "purchase_id": row.get("purchase_id"),
            }
            self._issue_source_identifier_missing(
                raw_record=raw_record,
                dataset="purchases",
                missing_identity_type="WAREHOUSE",
                available_source_fields=metadata["available_source_fields"],
                field_name="warehouse_code",
            )
        return CanonicalPurchase(
            id=canonical_row_uuid("canonical_purchases", raw_record.organization_id, source_external_id),
            organization_id=raw_record.organization_id,
            document_id=source_external_id,
            document_number=self._first_text(row, "purchase_number", "invoice_number"),
            document_at=self._parse_source_datetime(row.get("purchase_time") or row.get("input_date") or row.get("invoice_date")),
            source_status_code=self._first_text(row, "status_code", "posted"),
            source_status_name=self._first_text(row, "status_code", "posted"),
            warehouse_id=self._resolve_canonical_warehouse_id(raw_record.organization_id, warehouse_external_id),
            warehouse_external_id=warehouse_external_id,
            warehouse_code=warehouse_external_id,
            total_amount=self._parse_optional_decimal(row.get("total_amount") or row.get("amount")),
            currency_code=self._normalize_currency_code(self._first_text(row, "currency_code")),
            source_currency_code=self._first_text(row, "currency_code"),
            note=self._first_text(row, "note"),
            item_count=len(items),
            total_quantity=total_quantity,
            purchase_id=self._first_text(row, "purchase_id"),
            purchase_number=self._first_text(row, "purchase_number"),
            supplier_external_id=self._first_text(row, "supplier_id", "supplier_code"),
            supplier_code=self._first_text(row, "supplier_code"),
            contract_code=self._first_text(row, "contract_code"),
            invoice_number=self._first_text(row, "invoice_number"),
            invoice_external_id=self._first_text(row, "invoice_external_id"),
            invoice_date=self._parse_source_datetime(row.get("invoice_date")),
            input_date=self._parse_source_datetime(row.get("input_date")),
            posted=self._first_text(row, "posted"),
            total_margin_kind=self._first_text(row, "total_margin_kind"),
            total_margin_value=self._parse_optional_decimal(row.get("total_margin_value")),
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=source_external_id,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=header_quality,
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata=metadata,
        )

    def _build_canonical_purchase_items(
        self,
        *,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
        purchase: CanonicalPurchase,
    ) -> list[CanonicalPurchaseItem]:
        items: list[CanonicalPurchaseItem] = []
        for index, item in enumerate(self._line_items_from_purchase_row(row), start=1):
            product_external_id = self._first_text(item, "product_code", "product_id", "inventory_code")
            product_id = self._resolve_canonical_product_id(raw_record.organization_id, product_external_id)
            quantity = self._parse_decimal(item.get("quantity"))
            unit_price = self._parse_optional_decimal(item.get("price"))
            base_quality = self._quality_for_status(status)
            item_quality = (
                CanonicalDataQualityStatus.UNRESOLVED
                if product_id is None
                else base_quality
            )
            metadata = {
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
            }
            if product_id is None:
                metadata["unresolved_reason"] = "UNRESOLVED_SOURCE_REFERENCE"
                metadata["missing_identity_type"] = "PRODUCT"
                metadata["available_source_fields"] = self._available_purchase_identity_fields(item)
                self._issue_source_identifier_missing(
                    raw_record=raw_record,
                    dataset="purchases",
                    missing_identity_type="PRODUCT",
                    available_source_fields=self._available_purchase_identity_fields(item),
                    field_name="product_code",
                )
            items.append(
                CanonicalPurchaseItem(
                    id=canonical_row_uuid("canonical_purchase_items", raw_record.organization_id, purchase.source_external_id, index),
                    organization_id=raw_record.organization_id,
                    document_id=purchase.id,
                    document_external_id=purchase.source_external_id,
                    line_number=index,
                    product_id=product_id,
                    product_external_id=product_external_id,
                    product_code=self._first_text(item, "product_code", "inventory_code"),
                    product_name=self._first_text(item, "product_name", "name", "short_name"),
                    warehouse_id=purchase.warehouse_id,
                    warehouse_external_id=purchase.warehouse_external_id,
                    warehouse_code=purchase.warehouse_code,
                    quantity=quantity,
                    unit_price=unit_price,
                    amount=self._line_amount(quantity, unit_price),
                    currency_code=purchase.currency_code,
                    source_currency_code=purchase.source_currency_code,
                    batch_number=self._first_text(item, "batch_number"),
                    card_code=self._first_text(item, "card_code"),
                    serial_number=self._first_text(item, "serial_number"),
                    expiry_date=self._parse_source_datetime(item.get("expiry_date")),
                    inventory_kind=self._first_text(item, "inventory_kind"),
                    measure_code=self._first_text(item, "measure_code"),
                    purchase_external_id=purchase.source_external_id,
                    purchase_item_id=self._first_text(item, "purchase_item_id"),
                    purchase_order_item_id=self._first_text(item, "order_item_id"),
                    product_article_code=self._first_text(item, "product_article_code"),
                    on_balance=self._first_text(item, "on_balance"),
                    base_price=self._parse_optional_decimal(item.get("base_price")),
                    vat_percent=self._parse_optional_decimal(item.get("vat_percent")),
                    vat_amount=self._parse_optional_decimal(item.get("vat_amount")),
                    margin_kind=self._first_text(item, "margin_kind"),
                    margin_value=self._parse_optional_decimal(item.get("margin_value")),
                    source_system="smartup",
                    source_endpoint=raw_record.source_endpoint,
                    source_external_id=f"{purchase.source_external_id}:{index}",
                    source_raw_record_id=raw_record.id,
                    request_filial_id=raw_record.request_filial_id,
                    response_filial_id=raw_record.response_filial_id,
                    request_company_id=raw_record.request_company_id,
                    request_project_code=raw_record.request_project_code,
                    source_raw_batch_id=raw_record.batch_id,
                    data_quality_status=item_quality,
                    imported_at=raw_record.imported_at,
                    last_synced_at=raw_record.source_updated_at,
                    metadata=metadata,
                ),
            )
        return items

    def _build_canonical_warehouse_receipt(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalWarehouseReceipt | None:
        source_external_id = self._first_text(row, "input_id", "external_id", "input_number")
        if source_external_id is None:
            return None
        items = self._line_items_from_receipt_row(row)
        total_quantity = sum((self._parse_decimal(item.get("quantity")) for item in items), start=Decimal("0"))
        supplier_code = self._first_supplier_code(row.get("supplier_codes")) or self._first_text(row, "supplier_code")
        warehouse_external_id = self._first_text(row, "warehouse_code")
        base_quality = self._quality_for_status(status)
        header_quality = (
            base_quality
            if warehouse_external_id is not None
            else CanonicalDataQualityStatus.PARTIAL
        )
        metadata = {"source_entity": raw_record.entity_type, "source_endpoint": raw_record.source_endpoint}
        if warehouse_external_id is None:
            metadata["unresolved_reason"] = "UNRESOLVED_SOURCE_REFERENCE"
            metadata["missing_identity_type"] = "WAREHOUSE"
            metadata["available_source_fields"] = {
                "warehouse_code": row.get("warehouse_code"),
                "warehouse_external_id": row.get("warehouse_external_id"),
                "subfilial_code": row.get("subfilial_code"),
                "purchase_id": row.get("purchase_id"),
            }
            self._issue_source_identifier_missing(
                raw_record=raw_record,
                dataset="warehouse_receipts",
                missing_identity_type="WAREHOUSE",
                available_source_fields=metadata["available_source_fields"],
                field_name="warehouse_code",
            )
        return CanonicalWarehouseReceipt(
            id=canonical_row_uuid("canonical_warehouse_receipts", raw_record.organization_id, source_external_id),
            organization_id=raw_record.organization_id,
            document_id=source_external_id,
            document_number=self._first_text(row, "input_number"),
            document_at=self._parse_source_datetime(row.get("input_time")),
            source_status_code=self._first_text(row, "status"),
            source_status_name=self._first_text(row, "status"),
            warehouse_id=self._resolve_canonical_warehouse_id(raw_record.organization_id, warehouse_external_id),
            warehouse_external_id=warehouse_external_id,
            warehouse_code=warehouse_external_id,
            total_amount=None,
            currency_code=None,
            source_currency_code=None,
            note=self._first_text(row, "note"),
            item_count=len(items),
            total_quantity=total_quantity,
            receipt_id=self._first_text(row, "input_id"),
            receipt_number=self._first_text(row, "input_number"),
            supplier_external_id=supplier_code,
            supplier_code=supplier_code,
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=source_external_id,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=header_quality,
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata=metadata,
        )

    def _build_canonical_warehouse_receipt_items(
        self,
        *,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
        receipt: CanonicalWarehouseReceipt,
        inherited_purchase_item_products: dict[str, UUID] | None = None,
    ) -> list[CanonicalWarehouseReceiptItem]:
        items: list[CanonicalWarehouseReceiptItem] = []
        for index, item in enumerate(self._line_items_from_receipt_row(row), start=1):
            product_external_id = self._first_text(item, "product_code", "product_id", "inventory_code")
            quantity = self._parse_decimal(item.get("quantity"))
            unit_price = self._parse_optional_decimal(item.get("price"))
            purchase_item_external_id = self._first_text(item, "purchase_item_id")
            resolved_product_id = self._resolve_canonical_product_id(
                raw_record.organization_id,
                product_external_id,
            )
            if resolved_product_id is None:
                resolved_product_id = self._resolve_purchase_item_product_id(
                    raw_record.organization_id,
                    purchase_item_external_id,
                )
            if (
                resolved_product_id is None
                and inherited_purchase_item_products is not None
                and purchase_item_external_id is not None
            ):
                resolved_product_id = inherited_purchase_item_products.get(
                    purchase_item_external_id,
                )
            base_quality = self._quality_for_status(status)
            item_quality = (
                CanonicalDataQualityStatus.UNRESOLVED
                if resolved_product_id is None
                else base_quality
            )
            metadata = {
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
            }
            if resolved_product_id is None:
                metadata["unresolved_reason"] = "UNRESOLVED_SOURCE_REFERENCE"
                metadata["missing_identity_type"] = "PRODUCT"
                metadata["available_source_fields"] = self._available_receipt_identity_fields(item)
                self._issue_source_identifier_missing(
                    raw_record=raw_record,
                    dataset="warehouse_receipts",
                    missing_identity_type="PRODUCT",
                    available_source_fields=self._available_receipt_identity_fields(item),
                    field_name="product_code",
                )
            items.append(
                CanonicalWarehouseReceiptItem(
                    id=canonical_row_uuid("canonical_warehouse_receipt_items", raw_record.organization_id, receipt.source_external_id, index),
                    organization_id=raw_record.organization_id,
                    document_id=receipt.id,
                    document_external_id=receipt.source_external_id,
                    line_number=index,
                    product_id=resolved_product_id,
                    product_external_id=product_external_id,
                    product_code=self._first_text(item, "product_code", "inventory_code"),
                    product_name=self._first_text(item, "product_name", "name", "short_name"),
                    warehouse_id=receipt.warehouse_id,
                    warehouse_external_id=receipt.warehouse_external_id,
                    warehouse_code=receipt.warehouse_code,
                    quantity=quantity,
                    unit_price=unit_price,
                    amount=self._line_amount(quantity, unit_price),
                    currency_code=None,
                    source_currency_code=None,
                    batch_number=self._first_text(item, "batch_number"),
                    card_code=self._first_text(item, "card_code"),
                    serial_number=self._first_text(item, "serial_number"),
                    expiry_date=self._parse_source_datetime(item.get("expiry_date")),
                    inventory_kind=self._first_text(item, "inventory_kind"),
                    measure_code=self._first_text(item, "measure_code"),
                    receipt_external_id=receipt.source_external_id,
                    receipt_item_id=self._first_text(item, "input_item_id"),
                    purchase_external_id=self._first_text(item, "purchase_id"),
                    purchase_item_external_id=purchase_item_external_id,
                    product_article_code=self._first_text(item, "product_article_code"),
                    vat_percent=self._parse_optional_decimal(item.get("vat_percent")),
                    vat_amount=self._parse_optional_decimal(item.get("vat_amount")),
                    margin_kind=self._first_text(item, "margin_kind"),
                    margin_value=self._parse_optional_decimal(item.get("margin_value")),
                    source_system="smartup",
                    source_endpoint=raw_record.source_endpoint,
                    source_external_id=f"{receipt.source_external_id}:{index}",
                    source_raw_record_id=raw_record.id,
                    request_filial_id=raw_record.request_filial_id,
                    response_filial_id=raw_record.response_filial_id,
                    request_company_id=raw_record.request_company_id,
                    request_project_code=raw_record.request_project_code,
                    source_raw_batch_id=raw_record.batch_id,
                    data_quality_status=item_quality,
                    imported_at=raw_record.imported_at,
                    last_synced_at=raw_record.source_updated_at,
                    metadata=metadata,
                ),
            )
        return items

    def _build_canonical_writeoff(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalWriteoff | None:
        source_external_id = self._first_text(row, "writeoff_id", "external_id", "writeoff_number")
        if source_external_id is None:
            return None
        items = self._line_items_from_writeoff_row(row)
        total_quantity = sum((self._parse_decimal(item.get("quantity")) for item in items), start=Decimal("0"))
        warehouse_external_id = self._first_text(row, "warehouse_code")
        return CanonicalWriteoff(
            id=canonical_row_uuid("canonical_writeoffs", raw_record.organization_id, source_external_id),
            organization_id=raw_record.organization_id,
            document_id=source_external_id,
            document_number=self._first_text(row, "writeoff_number"),
            document_at=self._parse_source_datetime(row.get("writeoff_date")),
            source_status_code=self._first_text(row, "status"),
            source_status_name=self._first_text(row, "status"),
            warehouse_id=self._resolve_canonical_warehouse_id(raw_record.organization_id, warehouse_external_id),
            warehouse_external_id=warehouse_external_id,
            warehouse_code=warehouse_external_id,
            total_amount=self._parse_optional_decimal(row.get("c_amount")),
            currency_code=self._normalize_currency_code(self._first_text(row, "currency_code")),
            source_currency_code=self._first_text(row, "currency_code"),
            note=self._first_text(row, "note"),
            item_count=len(items),
            total_quantity=total_quantity,
            writeoff_id=self._first_text(row, "writeoff_id"),
            writeoff_number=self._first_text(row, "writeoff_number"),
            writeoff_date=self._parse_source_datetime(row.get("writeoff_date")),
            reason_code=self._first_text(row, "reason_code"),
            barcode=self._first_text(row, "barcode"),
            c_amount=self._parse_optional_decimal(row.get("c_amount")),
            c_amount_base=self._parse_optional_decimal(row.get("c_amount_base")),
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=source_external_id,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={"source_entity": raw_record.entity_type, "source_endpoint": raw_record.source_endpoint},
        )

    def _build_canonical_writeoff_items(
        self,
        *,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
        writeoff: CanonicalWriteoff,
    ) -> list[CanonicalWriteoffItem]:
        items: list[CanonicalWriteoffItem] = []
        for index, item in enumerate(self._line_items_from_writeoff_row(row), start=1):
            product_external_id = self._first_text(item, "product_code", "product_id", "inventory_code")
            items.append(
                CanonicalWriteoffItem(
                    id=canonical_row_uuid("canonical_writeoff_items", raw_record.organization_id, writeoff.source_external_id, index),
                    organization_id=raw_record.organization_id,
                    document_id=writeoff.id,
                    document_external_id=writeoff.source_external_id,
                    line_number=index,
                    product_id=self._resolve_canonical_product_id(raw_record.organization_id, product_external_id),
                    product_external_id=product_external_id,
                    product_code=self._first_text(item, "product_code", "inventory_code"),
                    product_name=self._first_text(item, "product_name", "name", "short_name"),
                    warehouse_id=writeoff.warehouse_id,
                    warehouse_external_id=writeoff.warehouse_external_id,
                    warehouse_code=writeoff.warehouse_code,
                    quantity=self._parse_decimal(item.get("quantity")),
                    unit_price=None,
                    amount=None,
                    currency_code=writeoff.currency_code,
                    source_currency_code=writeoff.source_currency_code,
                    batch_number=self._first_text(item, "batch_number"),
                    card_code=self._first_text(item, "card_code"),
                    serial_number=self._first_text(item, "serial_number"),
                    expiry_date=self._parse_source_datetime(item.get("expiry_date")),
                    inventory_kind=self._first_text(item, "inventory_kind"),
                    measure_code=self._first_text(item, "measure_code"),
                    writeoff_external_id=writeoff.source_external_id,
                    writeoff_item_id=self._first_text(item, "writeoff_item_id"),
                    product_article_code=self._first_text(item, "product_article_code"),
                    source_system="smartup",
                    source_endpoint=raw_record.source_endpoint,
                    source_external_id=f"{writeoff.source_external_id}:{index}",
                    source_raw_record_id=raw_record.id,
                    request_filial_id=raw_record.request_filial_id,
                    response_filial_id=raw_record.response_filial_id,
                    request_company_id=raw_record.request_company_id,
                    request_project_code=raw_record.request_project_code,
                    source_raw_batch_id=raw_record.batch_id,
                    data_quality_status=self._quality_for_status(status),
                    imported_at=raw_record.imported_at,
                    last_synced_at=raw_record.source_updated_at,
                    metadata={"source_entity": raw_record.entity_type, "source_endpoint": raw_record.source_endpoint},
                ),
            )
        return items

    def _build_canonical_cross_org_movement(
        self,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
    ) -> CanonicalCrossOrgMovement | None:
        source_external_id = self._first_text(row, "movement_id", "external_id", "delivery_number")
        if source_external_id is None:
            return None
        items = self._line_items_from_cross_org_movement_row(row)
        total_quantity = sum((self._parse_decimal(item.get("quantity")) for item in items), start=Decimal("0"))
        source_warehouse_external_id = self._first_text(row, "from_warehouse_code")
        destination_warehouse_external_id = self._first_text(row, "to_warehouse_code")
        return CanonicalCrossOrgMovement(
            id=canonical_row_uuid("canonical_cross_org_movements", raw_record.organization_id, source_external_id),
            organization_id=raw_record.organization_id,
            document_id=source_external_id,
            document_number=self._first_text(row, "delivery_number", "movement_id"),
            document_at=self._parse_source_datetime(row.get("from_time")),
            source_status_code=self._first_text(row, "status"),
            source_status_name=self._first_text(row, "status"),
            warehouse_id=self._resolve_canonical_warehouse_id(raw_record.organization_id, source_warehouse_external_id),
            warehouse_external_id=source_warehouse_external_id,
            warehouse_code=source_warehouse_external_id,
            total_amount=self._parse_optional_decimal(row.get("amount")),
            currency_code=self._normalize_currency_code(self._first_text(row, "currency_code")),
            source_currency_code=self._first_text(row, "currency_code"),
            note=self._first_text(row, "note"),
            item_count=len(items),
            total_quantity=total_quantity,
            movement_id=self._first_text(row, "movement_id"),
            delivery_number=self._first_text(row, "delivery_number"),
            source_filial_code=self._first_text(row, "from_filial_code"),
            destination_filial_code=self._first_text(row, "to_filial_code"),
            source_warehouse_id=self._resolve_canonical_warehouse_id(raw_record.organization_id, source_warehouse_external_id),
            source_warehouse_external_id=source_warehouse_external_id,
            source_warehouse_code=source_warehouse_external_id,
            destination_warehouse_id=self._resolve_canonical_warehouse_id(raw_record.organization_id, destination_warehouse_external_id),
            destination_warehouse_external_id=destination_warehouse_external_id,
            destination_warehouse_code=destination_warehouse_external_id,
            subfilial_code=self._first_text(row, "subfilial_code"),
            to_subfilial_code=self._first_text(row, "to_subfilial_code"),
            price_type_code=self._first_text(row, "price_type_code"),
            payment_type_code=self._first_text(row, "payment_type_code"),
            to_payment_type_code=self._first_text(row, "to_payment_type_code"),
            reason_id=self._first_text(row, "reason_id"),
            request_id=self._first_text(row, "request_id"),
            source_system="smartup",
            source_endpoint=raw_record.source_endpoint,
            source_external_id=source_external_id,
            source_raw_record_id=raw_record.id,
            request_filial_id=raw_record.request_filial_id,
            response_filial_id=raw_record.response_filial_id,
            request_company_id=raw_record.request_company_id,
            request_project_code=raw_record.request_project_code,
            source_raw_batch_id=raw_record.batch_id,
            data_quality_status=self._quality_for_status(status),
            imported_at=raw_record.imported_at,
            last_synced_at=raw_record.source_updated_at,
            metadata={"source_entity": raw_record.entity_type, "source_endpoint": raw_record.source_endpoint},
        )

    def _build_canonical_cross_org_movement_items(
        self,
        *,
        raw_record: SmartUpRawRecord,
        row: dict[str, Any],
        status: str,
        movement: CanonicalCrossOrgMovement,
    ) -> list[CanonicalCrossOrgMovementItem]:
        items: list[CanonicalCrossOrgMovementItem] = []
        for index, item in enumerate(self._line_items_from_cross_org_movement_row(row), start=1):
            product_external_id = self._first_text(item, "product_code", "product_id", "inventory_code")
            quantity = self._parse_decimal(item.get("quantity"))
            unit_price = self._parse_optional_decimal(item.get("price"))
            items.append(
                CanonicalCrossOrgMovementItem(
                    id=canonical_row_uuid("canonical_cross_org_movement_items", raw_record.organization_id, movement.source_external_id, index),
                    organization_id=raw_record.organization_id,
                    document_id=movement.id,
                    document_external_id=movement.source_external_id,
                    line_number=index,
                    product_id=self._resolve_canonical_product_id(raw_record.organization_id, product_external_id),
                    product_external_id=product_external_id,
                    product_code=self._first_text(item, "product_code", "inventory_code"),
                    product_name=self._first_text(item, "product_name", "name", "short_name"),
                    warehouse_id=movement.warehouse_id,
                    warehouse_external_id=movement.warehouse_external_id,
                    warehouse_code=movement.warehouse_code,
                    quantity=quantity,
                    unit_price=unit_price,
                    amount=self._line_amount(quantity, unit_price),
                    currency_code=movement.currency_code,
                    source_currency_code=movement.source_currency_code,
                    batch_number=self._first_text(item, "batch_number"),
                    card_code=self._first_text(item, "card_code"),
                    serial_number=self._first_text(item, "serial_number"),
                    expiry_date=self._parse_source_datetime(item.get("expiry_date")),
                    inventory_kind=self._first_text(item, "from_inventory_kind", "to_inventory_kind", "inventory_kind"),
                    measure_code=self._first_text(item, "measure_code"),
                    movement_external_id=movement.source_external_id,
                    movement_unit_id=self._first_text(item, "movement_unit_id"),
                    source_warehouse_id=movement.source_warehouse_id,
                    source_warehouse_external_id=movement.source_warehouse_external_id,
                    source_warehouse_code=movement.source_warehouse_code,
                    destination_warehouse_id=movement.destination_warehouse_id,
                    destination_warehouse_external_id=movement.destination_warehouse_external_id,
                    destination_warehouse_code=movement.destination_warehouse_code,
                    base_amount=self._parse_optional_decimal(item.get("amount_base")),
                    vat_percent=self._parse_optional_decimal(item.get("vat_percent")),
                    vat_amount=self._parse_optional_decimal(item.get("vat_amount")),
                    margin_kind=self._first_text(item, "margin_kind"),
                    margin_value=self._parse_optional_decimal(item.get("margin_value")),
                    margin_amount=self._parse_optional_decimal(item.get("margin_amount")),
                    on_balance=self._first_text(item, "on_balance"),
                    source_system="smartup",
                    source_endpoint=raw_record.source_endpoint,
                    source_external_id=f"{movement.source_external_id}:{index}",
                    source_raw_record_id=raw_record.id,
                    request_filial_id=raw_record.request_filial_id,
                    response_filial_id=raw_record.response_filial_id,
                    request_company_id=raw_record.request_company_id,
                    request_project_code=raw_record.request_project_code,
                    source_raw_batch_id=raw_record.batch_id,
                    data_quality_status=self._quality_for_status(status),
                    imported_at=raw_record.imported_at,
                    last_synced_at=raw_record.source_updated_at,
                    metadata={"source_entity": raw_record.entity_type, "source_endpoint": raw_record.source_endpoint},
                ),
            )
        return items

    def _raw_records(
        self,
        organization_id: UUID,
        entity_types: tuple[str, ...],
    ) -> list[SmartUpRawRecord]:
        records: list[SmartUpRawRecord] = []
        for entity_type in entity_types:
            records.extend(
                self.store.list_smartup_raw_records(
                    organization_id=organization_id,
                    entity_type=entity_type,
                ),
            )
        return sorted(records, key=lambda item: (item.imported_at, str(item.id)))

    def _raw_records_for_warehouse_sources(self, organization_id: UUID) -> list[SmartUpRawRecord]:
        records = self._raw_records(
            organization_id,
            (
                "inventory_balances",
                "sales",
                "returns",
                "purchases",
                "warehouse_receipts",
                "return_to_suppliers",
                "stocktakings",
                "write_offs",
                "cross_organizational_movements",
                "internal_movements",
                "logistics",
                "equipment_movements",
                "equipment_requests",
            ),
        )
        priority = {
            "inventory_balances": 10,
            "purchases": 20,
            "warehouse_receipts": 30,
            "return_to_suppliers": 40,
            "stocktakings": 50,
            "write_offs": 60,
            "cross_organizational_movements": 70,
            "internal_movements": 80,
            "sales": 90,
            "returns": 100,
            "logistics": 110,
            "equipment_movements": 120,
            "equipment_requests": 130,
        }
        return sorted(
            records,
            key=lambda item: (
                priority.get(item.entity_type, 999),
                item.imported_at,
                str(item.id),
            ),
        )

    @staticmethod
    def _line_items_from_order_row(row: dict[str, Any]) -> list[dict[str, Any]]:
        value = row.get("order_products")
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _line_items_from_return_row(row: dict[str, Any]) -> list[dict[str, Any]]:
        value = row.get("return_products")
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _line_items_from_purchase_row(row: dict[str, Any]) -> list[dict[str, Any]]:
        value = row.get("purchase_items")
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _line_items_from_receipt_row(row: dict[str, Any]) -> list[dict[str, Any]]:
        value = row.get("input_items")
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _line_items_from_writeoff_row(row: dict[str, Any]) -> list[dict[str, Any]]:
        value = row.get("writeoff_items")
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _line_items_from_cross_org_movement_row(row: dict[str, Any]) -> list[dict[str, Any]]:
        value = row.get("movement_items")
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _is_wrapper_only_row(row: dict[str, Any]) -> bool:
        business_keys = set(row) - {"limits", "request_payload", "response_envelope", "metadata"}
        if not business_keys:
            return True
        if business_keys == {"bank_operation"} and isinstance(row.get("bank_operation"), list):
            return len(row.get("bank_operation", [])) == 0
        if business_keys == {"cashin"} and isinstance(row.get("cashin"), list):
            return len(row.get("cashin", [])) == 0
        return False

    @staticmethod
    def _source_is_cash_operation(source_endpoint: str) -> bool:
        return source_endpoint.endswith("/cash_operation$export")

    def _payment_overlap_signatures(
        self,
        organization_id: UUID,
    ) -> set[tuple[str, str, str, str]]:
        signatures: set[tuple[str, str, str, str]] = set()
        for payment in self.store.list_canonical_payments(organization_id=organization_id):
            signature = (
                (payment.customer_external_id or "").strip(),
                (payment.amount or Decimal("0")).normalize().to_eng_string(),
                payment.currency_code or payment.source_currency_code or "",
                payment.cashin_date or "",
            )
            signatures.add(signature)
        return signatures

    def _payment_like_signature_from_cash_operation(
        self,
        row: dict[str, Any],
    ) -> tuple[str, str, str, str] | None:
        customer_external_id = self._counterparty_customer_from_ref_codes(row) or self._first_text(
            row,
            "corr_person_code",
        )
        amount = self._parse_decimal(row.get("amount"))
        currency = self._normalize_currency_code(self._first_text(row, "currency_code")) or ""
        operation_date = self._first_text(row, "operation_date") or ""
        if customer_external_id is None:
            return None
        return (
            customer_external_id,
            amount.normalize().to_eng_string(),
            currency,
            operation_date,
        )

    @staticmethod
    def _direction_from_cashflow_kind(value: str | None) -> CanonicalFinancialDirection:
        normalized = SmartUpCanonicalV2FoundationService._clean_text(value)
        if normalized is None:
            return CanonicalFinancialDirection.UNKNOWN
        mapping = {
            "I": CanonicalFinancialDirection.INFLOW,
            "O": CanonicalFinancialDirection.OUTFLOW,
            "T": CanonicalFinancialDirection.TRANSFER,
        }
        return mapping.get(normalized.upper(), CanonicalFinancialDirection.UNKNOWN)

    def _direction_from_bank_operation(
        self,
        row: dict[str, Any],
    ) -> CanonicalFinancialDirection:
        return self._direction_from_cashflow_kind(
            self._first_text(row, "cashflow_kind", "debit_credit"),
        )

    def _counterparty_customer_from_ref_codes(
        self,
        row: dict[str, Any],
    ) -> str | None:
        for ref in self._list_of_dicts(row, "ref_codes"):
            ref_type = self._first_text(ref, "ref_type")
            ref_id = self._first_text(ref, "ref_id")
            if ref_type == "1010" and ref_id is not None:
                return ref_id
        return None

    def _aggregate_order_line_metrics(self, order_products: list[dict[str, Any]]) -> dict[str, Any]:
        ordered_quantity = Decimal("0")
        sold_quantity = Decimal("0")
        returned_quantity = Decimal("0")
        has_sold_quantity = False
        has_realization_evidence = False
        for item in order_products:
            ordered_quantity += self._parse_decimal(item.get("order_quant") or item.get("quantity"))
            item_sold_quantity = self._line_sold_quantity(item)
            if item_sold_quantity > Decimal("0"):
                has_sold_quantity = True
                sold_quantity += item_sold_quantity
                has_realization_evidence = True
            returned_quantity += self._parse_decimal(item.get("return_quant"))
            line_amount = self._parse_decimal(
                item.get("amount") or item.get("sold_amount") or item.get("total_amount"),
            )
            if line_amount > Decimal("0"):
                has_realization_evidence = True
        if not has_sold_quantity:
            sold_quantity = Decimal("0")
        return {
            "ordered_quantity": ordered_quantity,
            "sold_quantity": sold_quantity,
            "returned_quantity": returned_quantity,
            "has_realization_evidence": has_realization_evidence,
        }

    def _line_sold_quantity(self, item: dict[str, Any]) -> Decimal:
        details = item.get("details")
        if isinstance(details, list):
            total = Decimal("0")
            found = False
            for detail in details:
                if not isinstance(detail, dict):
                    continue
                if "sold_quant" not in detail:
                    continue
                total += self._parse_decimal(detail.get("sold_quant"))
                found = True
            if found:
                return total
        if item.get("sold_quant") is not None:
            return self._parse_decimal(item.get("sold_quant"))
        return Decimal("0")

    @staticmethod
    def _line_amount(quantity: Decimal, unit_price: Decimal | None) -> Decimal | None:
        if unit_price is None:
            return None
        return quantity * unit_price

    @staticmethod
    def _first_supplier_code(value: object | None) -> str | None:
        if not isinstance(value, list):
            return None
        for item in value:
            if not isinstance(item, dict):
                continue
            supplier_code = SmartUpCanonicalV2FoundationService._first_text(
                item,
                "supplier_code",
                "code",
            )
            if supplier_code is not None:
                return supplier_code
        return None

    @staticmethod
    def _inventory_response_keys(entity_type: str) -> tuple[str, ...]:
        mapping = {
            "return_to_suppliers": ("return",),
            "stocktakings": ("stocktaking",),
            "internal_movements": ("movement",),
        }
        return mapping.get(entity_type, ())

    def _resolve_canonical_customer_id(
        self,
        organization_id: UUID,
        source_external_id: str | None,
    ) -> UUID | None:
        if source_external_id is None:
            return None
        customer_id = canonical_row_uuid(
            "canonical_customers",
            organization_id,
            source_external_id,
        )
        return customer_id if self.store.get_canonical_customer(customer_id) is not None else None

    def _resolve_canonical_sales_rep_id(
        self,
        organization_id: UUID,
        source_external_id: str | None,
    ) -> UUID | None:
        if source_external_id is None:
            return None
        sales_rep_id = canonical_row_uuid(
            "canonical_sales_reps",
            organization_id,
            source_external_id,
        )
        return sales_rep_id if self.store.get_canonical_sales_rep(sales_rep_id) is not None else None

    def _resolve_canonical_working_zone_id(
        self,
        organization_id: UUID,
        source_external_id: str | None,
    ) -> UUID | None:
        if source_external_id is None:
            return None
        working_zone_id = canonical_row_uuid(
            "canonical_working_zones",
            organization_id,
            source_external_id,
        )
        return (
            working_zone_id
            if self.store.get_canonical_working_zone(working_zone_id) is not None
            else None
        )

    def _resolve_canonical_product_id(
        self,
        organization_id: UUID,
        source_external_id: str | None,
    ) -> UUID | None:
        if source_external_id is None:
            return None
        product = self._find_canonical_product(organization_id, source_external_id)
        return product.id if product is not None else None

    def _resolve_canonical_warehouse_id(
        self,
        organization_id: UUID,
        source_external_id: str | None,
    ) -> UUID | None:
        if source_external_id is None:
            return None
        warehouse = self._warehouse_index_for_organization(organization_id).get(source_external_id)
        return warehouse.id if warehouse is not None else None

    def _resolve_canonical_price_type_id(
        self,
        organization_id: UUID,
        price_type_code: str | None,
    ) -> UUID | None:
        if price_type_code is None:
            return None
        price_type = self._price_type_index_for_organization(organization_id).get(price_type_code)
        return price_type.id if price_type is not None else None

    def _resolve_purchase_item_product_id(
        self,
        organization_id: UUID,
        purchase_item_external_id: str | None,
    ) -> UUID | None:
        if purchase_item_external_id is None:
            return None
        return self._purchase_item_product_index_for_organization(organization_id).get(
            purchase_item_external_id,
        )

    def _resolve_canonical_order_id(
        self,
        organization_id: UUID,
        source_external_id: str | None,
    ) -> UUID | None:
        if source_external_id is None:
            return None
        order_id = canonical_row_uuid("canonical_orders", organization_id, source_external_id)
        if self.store.get_canonical_order(order_id) is not None:
            return order_id
        for order in self.store.list_canonical_orders(organization_id=organization_id):
            if order.source_external_id == source_external_id or order.deal_id == source_external_id:
                return order.id
        return None

    def _resolve_canonical_sale_id(
        self,
        organization_id: UUID,
        source_external_id: str | None,
    ) -> UUID | None:
        if source_external_id is None:
            return None
        sale_id = canonical_row_uuid("canonical_sales", organization_id, source_external_id)
        if self.store.get_canonical_sale(sale_id) is not None:
            return sale_id
        for sale in self.store.list_canonical_sales(organization_id=organization_id):
            if sale.source_external_id == source_external_id or sale.deal_id == source_external_id:
                return sale.id
        return None

    def _payment_reference_candidates(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for key, reference_type in (
            ("deal_id", "sale"),
            ("order_deal_id", "order"),
            ("order_id", "order"),
            ("sale_id", "sale"),
            ("external_sale_id", "sale"),
        ):
            external_id = self._first_text(row, key)
            if external_id is None:
                continue
            candidates.append(
                {
                    "reference_type": reference_type,
                    "source_key": key,
                    "external_id": external_id,
                },
            )
        ref_codes = row.get("ref_codes")
        if isinstance(ref_codes, list):
            for ref in ref_codes:
                if not isinstance(ref, dict):
                    continue
                external_id = self._first_text(ref, "ref_id", "id", "code")
                if external_id is None:
                    continue
                candidates.append(
                    {
                        "reference_type": self._first_text(ref, "ref_type") or "ref_code",
                        "source_key": "ref_codes",
                        "external_id": external_id,
                    },
                )
        unique: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for candidate in candidates:
            signature = (
                str(candidate["reference_type"]),
                str(candidate["source_key"]),
                str(candidate["external_id"]),
            )
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(candidate)
        return unique

    @staticmethod
    def _normalize_smartup_status(value: str | None) -> str:
        if value is None:
            return "unmapped"
        normalized = value.strip().upper()
        if "#C" in normalized or normalized == "C":
            return "cancelled"
        if "#A" in normalized or normalized == "A":
            return "approved"
        if "#N" in normalized or normalized == "N":
            return "new"
        return "unmapped"

    @staticmethod
    def _normalize_payment_type(value: str | None) -> str:
        normalized = SmartUpCanonicalV2FoundationService._clean_text(value)
        if normalized is None:
            return "unknown"
        lowered = normalized.lower()
        if lowered in {"cash", "cash_in_hand"}:
            return "cash"
        if lowered in {"bank_transfer", "transfer"}:
            return "bank_transfer"
        if lowered in {"terminal", "pos"}:
            return "terminal"
        return "unknown"

    @staticmethod
    def _normalize_currency_code(value: str | None) -> str | None:
        normalized = SmartUpCanonicalV2FoundationService._clean_text(value)
        if normalized == "860":
            return "UZS"
        return normalized

    @staticmethod
    def _parse_optional_decimal(value: object | None) -> Decimal | None:
        if value is None or value == "":
            return None
        return SmartUpCanonicalV2FoundationService._parse_decimal(value)

    @staticmethod
    def _parse_source_datetime(value: object | None) -> datetime | None:
        text = SmartUpCanonicalV2FoundationService._clean_text(value)
        if text is None:
            return None
        for fmt in (
            "%d.%m.%Y %H:%M:%S",
            "%d.%m.%y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%d.%m.%Y",
            "%d.%m.%y",
            "%Y-%m-%d",
        ):
            try:
                parsed = datetime.strptime(text, fmt)
            except ValueError:
                continue
            return parsed.replace(tzinfo=UTC)
        return None

    @staticmethod
    def _parse_visit_datetime(value: object | None) -> datetime | None:
        """Parse visit event times as Asia/Tashkent wall-clock values.

        SmartUp exports visit times without an offset, and those values are
        local business time rather than UTC. Explicitly zoned inputs retain
        their supplied instant instead of being reinterpreted as local time.
        ``visit_date`` intentionally continues using the date-field contract
        in ``_parse_source_datetime``; it is a business date, not an event
        timestamp.
        """

        if isinstance(value, datetime):
            return value.replace(tzinfo=_BUSINESS_TIMEZONE) if value.tzinfo is None else value
        text = SmartUpCanonicalV2FoundationService._clean_text(value)
        if text is None:
            return None
        iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            parsed = datetime.fromisoformat(iso_text)
        except ValueError:
            parsed = None
        if parsed is not None:
            return parsed.replace(tzinfo=_BUSINESS_TIMEZONE) if parsed.tzinfo is None else parsed
        for fmt in (
            "%d.%m.%Y %H:%M:%S",
            "%d.%m.%y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=_BUSINESS_TIMEZONE)
            except ValueError:
                continue
        return None

    def _customer_candidate_rows(
        self,
        organization_id: UUID,
    ) -> list[tuple[SmartUpRawRecord, dict[str, Any], str]]:
        candidates: list[tuple[SmartUpRawRecord, dict[str, Any], str]] = []
        for raw_record in self._raw_records(organization_id, ("customers", "sales", "payments", "visits", "returns")):
            payload = self._payload_row(raw_record)
            if payload is None:
                continue
            source_kind = self._customer_source_kind(raw_record)
            if raw_record.entity_type == "customers":
                for row in self._candidate_rows(raw_record, ("legal_person", "natural_person")):
                    candidates.append((raw_record, row, "master"))
                continue
            if raw_record.entity_type == "visits":
                for row in self._visit_customer_rows(payload):
                    candidates.append((raw_record, row, "visit"))
                continue
            if raw_record.entity_type == "sales":
                row = self._customer_row_from_sale(payload)
                if row is not None:
                    candidates.append((raw_record, row, "sale"))
                continue
            if raw_record.entity_type == "payments":
                row = self._customer_row_from_payment(payload)
                if row is not None:
                    candidates.append((raw_record, row, "payment"))
                continue
            if raw_record.entity_type == "returns":
                row = self._customer_row_from_return(payload)
                if row is not None:
                    candidates.append((raw_record, row, "return"))
                continue
            if source_kind is not None:
                row = self._extract_customer_reference_row(payload)
                if row is not None:
                    candidates.append((raw_record, row, source_kind))
        return candidates

    @staticmethod
    def _visit_header_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows = payload.get("visit_headers")
        if isinstance(rows, list):
            return [item for item in rows if isinstance(item, dict)]
        if "visit_id" in payload and isinstance(payload, dict):
            return [payload]
        return []

    @staticmethod
    def _nested_object_rows(*values: object | None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for value in values:
            if isinstance(value, list):
                rows.extend(item for item in value if isinstance(item, dict))
        return rows

    @staticmethod
    def _parse_yes_no(value: object | None) -> bool | None:
        text = SmartUpCanonicalV2FoundationService._clean_text(value)
        if text is None:
            return None
        normalized = text.upper()
        if normalized == "Y":
            return True
        if normalized == "N":
            return False
        return None

    @staticmethod
    def _parse_optional_int(value: object | None) -> int | None:
        text = SmartUpCanonicalV2FoundationService._clean_text(value)
        if text is None:
            return None
        try:
            return int(text)
        except ValueError:
            return None

    @staticmethod
    def _derive_duration_seconds(
        start: datetime | None,
        end: datetime | None,
    ) -> int | None:
        if start is None or end is None:
            return None
        delta = int((end - start).total_seconds())
        if delta < 0:
            return None
        return delta

    @staticmethod
    def _parse_lat_lng(value: object | None) -> tuple[Decimal | None, Decimal | None]:
        text = SmartUpCanonicalV2FoundationService._clean_text(value)
        if text is None or "," not in text:
            return None, None
        left, right = [part.strip() for part in text.split(",", 1)]
        try:
            return Decimal(left), Decimal(right)
        except InvalidOperation:
            return None, None

    @staticmethod
    def _normalize_visit_status(value: str | None) -> str:
        text = SmartUpCanonicalV2FoundationService._clean_text(value)
        if text is None:
            return "unmapped"
        normalized = text.upper()
        mapping = {
            "A": "approved",
            "C": "completed",
            "N": "new",
        }
        return mapping.get(normalized, "unmapped")

    def _visit_quality_for_status(
        self,
        *,
        status: str,
        customer_external_id: str | None,
        sales_rep_external_id: str | None,
    ) -> CanonicalDataQualityStatus:
        base = self._quality_for_status(status)
        if base == CanonicalDataQualityStatus.UNSAFE:
            return base
        if customer_external_id is not None and sales_rep_external_id is not None:
            return base
        return CanonicalDataQualityStatus.PARTIAL

    @staticmethod
    def _extract_visit_note(payload: dict[str, Any]) -> str | None:
        note = payload.get("note")
        if isinstance(note, list):
            parts: list[str] = []
            for item in note:
                if isinstance(item, dict):
                    text = SmartUpCanonicalV2FoundationService._first_text(
                        item,
                        "note",
                        "text",
                        "comment",
                        "value",
                    )
                    if text:
                        parts.append(text)
                else:
                    text = SmartUpCanonicalV2FoundationService._clean_text(item)
                    if text:
                        parts.append(text)
            return " | ".join(parts) if parts else None
        if isinstance(note, dict):
            return SmartUpCanonicalV2FoundationService._first_text(
                note,
                "note",
                "text",
                "comment",
                "value",
            )
        return SmartUpCanonicalV2FoundationService._clean_text(note)

    def _collect_media_references(self, payload: object) -> list[dict[str, str]]:
        references: list[dict[str, str]] = []
        self._walk_media_references(payload, references, source_entity_type="visit")
        unique: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for reference in references:
            signature = (
                reference.get("source_entity_type", ""),
                reference.get("sha", ""),
                reference.get("reference", ""),
            )
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(reference)
        return unique

    def _walk_media_references(
        self,
        value: object,
        references: list[dict[str, str]],
        *,
        source_entity_type: str,
        source_entity_id: str | None = None,
    ) -> None:
        if isinstance(value, dict):
            sha = self._first_text(value, "sha", "photo_sha", "image_sha")
            reference = self._first_text(
                value,
                "photo_url",
                "image_url",
                "file_url",
                "source_reference",
                "photo_reference",
            )
            if sha is not None or reference is not None:
                references.append(
                    {
                        "source_entity_type": source_entity_type,
                        "source_entity_id": source_entity_id or self._first_text(value, "id", "code"),
                        "media_type": self._first_text(value, "media_type", "type") or "photo",
                        "sha": sha or "",
                        "reference": reference or "",
                    },
                )
            for key, nested in value.items():
                nested_type = key.rstrip("s")
                nested_id = self._first_text(value, "id", "code")
                self._walk_media_references(
                    nested,
                    references,
                    source_entity_type=nested_type or source_entity_type,
                    source_entity_id=nested_id or source_entity_id,
                )
            return
        if isinstance(value, list):
            for item in value:
                self._walk_media_references(
                    item,
                    references,
                    source_entity_type=source_entity_type,
                    source_entity_id=source_entity_id,
                )

    @staticmethod
    def _response_filial_matches(
        organization: SmartUpOrganization,
        raw_record: SmartUpRawRecord,
    ) -> bool:
        response_filial_id = SmartUpCanonicalV2FoundationService._clean_text(
            raw_record.response_filial_id,
        )
        if response_filial_id is None:
            return True
        return response_filial_id == SmartUpCanonicalV2FoundationService._clean_text(
            organization.filial_id,
        )

    def _customer_row_from_sale(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        row = self._extract_customer_reference_row(payload)
        if row is None:
            return None
        return row

    def _customer_row_from_payment(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        row = self._extract_customer_reference_row(payload, id_keys=("client_id", "person_id"))
        if row is None:
            return None
        return row

    def _customer_row_from_return(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        row = self._extract_customer_reference_row(payload)
        if row is None:
            return None
        return row

    def _visit_customer_rows(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        nested = payload.get("visit_headers")
        if isinstance(nested, list):
            for item in nested:
                if isinstance(item, dict):
                    row = self._extract_customer_reference_row(
                        item,
                        id_keys=("person_id", "client_id"),
                        name_keys=("person_name", "client_name"),
                        code_keys=("person_code", "client_code"),
                    )
                    if row is not None:
                        rows.append(row)
        row = self._extract_customer_reference_row(
            payload,
            id_keys=("person_id", "client_id"),
            name_keys=("person_name", "client_name"),
            code_keys=("person_code", "client_code"),
        )
        if row is not None:
            rows.append(row)
        return rows

    def _extract_customer_reference_row(
        self,
        payload: dict[str, Any],
        *,
        id_keys: tuple[str, ...] = ("person_id", "client_id", "id"),
        code_keys: tuple[str, ...] = ("person_code", "client_code", "code"),
        name_keys: tuple[str, ...] = ("person_name", "client_name", "name", "short_name"),
    ) -> dict[str, Any] | None:
        source_external_id = self._first_text(payload, *id_keys, *code_keys)
        name = self._first_text(payload, *name_keys)
        if source_external_id is None or name is None:
            return None
        if self._is_placeholder_label(name):
            return None
        row: dict[str, Any] = dict(payload)
        row.setdefault("source_external_id", source_external_id)
        row.setdefault("customer_name", name)
        return row

    @staticmethod
    def _customer_source_kind(raw_record: SmartUpRawRecord) -> str | None:
        if raw_record.entity_type == "customers":
            return "master"
        if raw_record.entity_type == "sales":
            return "sale"
        if raw_record.entity_type == "payments":
            return "payment"
        if raw_record.entity_type == "visits":
            return "visit"
        if raw_record.entity_type == "returns":
            return "return"
        return SmartUpCanonicalV2FoundationService._clean_text(raw_record.entity_type)

    @staticmethod
    def _is_placeholder_label(value: str | None) -> bool:
        if value is None:
            return True
        normalized = value.strip().lower()
        return normalized in {"", "-", "—", "unknown", "n/a", "na", "none"} or normalized.startswith(
            "producer",
        )

    @staticmethod
    def _customer_candidate_score(customer: CanonicalCustomer) -> tuple[int, int, int]:
        source_kind = str(customer.metadata.get("customer_source_kind") or "").lower()
        priority_map = {
            "master": 0,
            "sale": 1,
            "payment": 2,
            "visit": 3,
            "return": 4,
        }
        priority = priority_map.get(source_kind, 5)
        completeness = sum(
            1
            for value in (
                customer.code,
                customer.short_name,
                customer.main_phone,
                customer.email,
                customer.address,
                customer.customer_kind,
                customer.tin,
            )
            if value
        )
        return priority, -completeness, 0

    def _prefer_customer_candidate(self, candidate: CanonicalCustomer, existing: CanonicalCustomer) -> bool:
        return self._customer_candidate_score(candidate) < self._customer_candidate_score(existing)

    def _candidate_rows(
        self,
        raw_record: SmartUpRawRecord,
        response_keys: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        for payload in (raw_record.response_payload, raw_record.response_envelope):
            rows = self._rows_from_value(payload, response_keys)
            if rows:
                return rows
        payload = raw_record.response_payload
        if isinstance(payload, dict):
            return [payload]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        envelope = raw_record.response_envelope
        if isinstance(envelope, dict):
            return [envelope]
        if isinstance(envelope, list):
            return [item for item in envelope if isinstance(item, dict)]
        return []

    def _payload_row(self, raw_record: SmartUpRawRecord) -> dict[str, Any] | None:
        payload = raw_record.response_payload
        if isinstance(payload, dict):
            return payload
        envelope = raw_record.response_envelope
        if isinstance(envelope, dict):
            return envelope
        return None

    def _rows_from_value(
        self,
        value: object | None,
        response_keys: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if not isinstance(value, dict):
            return []
        rows: list[dict[str, Any]] = []
        for key in response_keys:
            nested = value.get(key)
            if isinstance(nested, list):
                rows.extend(item for item in nested if isinstance(item, dict))
        return rows

    def _raw_status_map(
        self,
        report: SmartUpRawAttributionReport,
    ) -> dict[UUID, str]:
        return {issue.raw_record_id: issue.status for issue in report.issues}

    def _raw_status(
        self,
        raw_status_by_record_id: dict[UUID, str],
        raw_record_id: UUID,
    ) -> str:
        return raw_status_by_record_id.get(raw_record_id, "CONSISTENT")

    def _quality_for_status(self, status: str) -> CanonicalDataQualityStatus:
        if status == "CONSISTENT":
            return CanonicalDataQualityStatus.VERIFIED
        if status == "LEGACY_MISSING_REQUEST_CONTEXT":
            return CanonicalDataQualityStatus.PARTIAL
        return CanonicalDataQualityStatus.UNSAFE

    def _issue_source_identifier_missing(
        self,
        *,
        raw_record: SmartUpRawRecord,
        dataset: str,
        missing_identity_type: str,
        available_source_fields: dict[str, Any],
        field_name: str | None = None,
        message: str | None = None,
    ) -> None:
        self.store.upsert_normalization_issue(
            NormalizationIssue(
                raw_record_id=raw_record.id,
                organization_id=raw_record.organization_id,
                entity_type=dataset,
                issue_type=_SOURCE_IDENTIFIER_MISSING,
                field_name=field_name,
                message=message
                or (
                    f"SmartUp RAW does not provide deterministic {missing_identity_type.lower()} "
                    f"identifier for {dataset}."
                ),
                source_value={
                    "dataset": dataset,
                    "missing_identity_type": missing_identity_type,
                    "available_source_fields": available_source_fields,
                },
                severity=NormalizationIssueSeverity.WARNING,
            ),
        )

    @staticmethod
    def _linkage_coverage(
        total: int,
        resolved: int,
    ) -> dict[str, Any]:
        if total <= 0:
            return {"resolved": 0, "total": 0, "ratio": None}
        return {
            "resolved": resolved,
            "total": total,
            "ratio": round(resolved / total, 6),
        }

    @staticmethod
    def _available_purchase_identity_fields(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "product_code": item.get("product_code"),
            "product_id": item.get("product_id"),
            "inventory_code": item.get("inventory_code"),
            "barcode": item.get("barcode"),
            "article_code": item.get("article_code"),
            "serial_number": item.get("serial_number"),
            "inventory_kind": item.get("inventory_kind"),
            "card_code": item.get("card_code"),
            "purchase_item_id": item.get("purchase_item_id"),
        }

    @staticmethod
    def _available_receipt_identity_fields(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "product_code": item.get("product_code"),
            "product_id": item.get("product_id"),
            "inventory_code": item.get("inventory_code"),
            "barcode": item.get("barcode"),
            "article_code": item.get("article_code"),
            "serial_number": item.get("serial_number"),
            "inventory_kind": item.get("inventory_kind"),
            "card_code": item.get("card_code"),
            "purchase_item_id": item.get("purchase_item_id"),
            "input_item_id": item.get("input_item_id"),
        }

    @staticmethod
    def _customer_quality_for_status(
        status: str,
        source_kind: str | None,
    ) -> CanonicalDataQualityStatus:
        if status not in _SAFE_RAW_STATUSES:
            return CanonicalDataQualityStatus.UNSAFE
        if source_kind == "master":
            return (
                CanonicalDataQualityStatus.VERIFIED
                if status == "CONSISTENT"
                else CanonicalDataQualityStatus.PARTIAL
            )
        return CanonicalDataQualityStatus.PARTIAL

    def _prefer_candidate(self, new: Any, existing: Any) -> bool:
        new_score = self._candidate_score(new)
        existing_score = self._candidate_score(existing)
        if new_score != existing_score:
            return new_score > existing_score
        new_synced = getattr(new, "last_synced_at", None) or getattr(new, "imported_at", None)
        existing_synced = getattr(existing, "last_synced_at", None) or getattr(
            existing,
            "imported_at",
            None,
        )
        return (new_synced or datetime.min.replace(tzinfo=UTC)) > (
            existing_synced or datetime.min.replace(tzinfo=UTC)
        )

    def _candidate_score(self, candidate: Any) -> int:
        score = 0
        if getattr(candidate, "data_quality_status", None) == CanonicalDataQualityStatus.VERIFIED:
            score += 2
        elif getattr(candidate, "data_quality_status", None) == CanonicalDataQualityStatus.PARTIAL:
            score += 1
        if getattr(candidate, "source_raw_record_id", None) is not None:
            score += 1
        return score

    def _upsert_rows(self, table: str, rows: list[Any]) -> None:
        for row in rows:
            if table == "canonical_customer_groups":
                self.store.upsert_canonical_customer_group(row)
            elif table == "canonical_customers":
                self.store.upsert_canonical_customer(row)
            elif table == "canonical_product_categories":
                self.store.upsert_canonical_product_category(row)
            elif table == "canonical_products":
                self.store.upsert_canonical_product(row)
            elif table == "canonical_warehouses":
                self.store.upsert_canonical_warehouse(row)
            elif table == "canonical_price_types":
                self.store.upsert_canonical_price_type(row)
            elif table == "canonical_product_prices":
                self.store.upsert_canonical_product_price(row)
            elif table == "canonical_sales_reps":
                self.store.upsert_canonical_sales_rep(row)
            elif table == "canonical_working_zones":
                self.store.upsert_canonical_working_zone(row)
            elif table == "canonical_visits":
                self.store.upsert_canonical_visit(row)
            elif table == "canonical_visit_stocks":
                self.store.upsert_canonical_visit_stock(row)
            elif table == "canonical_visit_quiz_answers":
                self.store.upsert_canonical_visit_quiz_answer(row)
            elif table == "canonical_visit_equipments":
                self.store.upsert_canonical_visit_equipment(row)
            elif table == "canonical_visit_comments":
                self.store.upsert_canonical_visit_comment(row)
            elif table == "canonical_media_assets":
                self.store.upsert_canonical_media_asset(row)
            else:  # pragma: no cover - defensive guard
                msg = f"Unsupported canonical table: {table}"
                raise ValueError(msg)

    def _table_report(
        self,
        *,
        table: str,
        raw_source_count: int,
        canonical_rows: list[Any],
        unsafe_count: int,
        unresolved_count: int,
        duplicate_count: int,
        notes: list[str],
    ) -> CanonicalV2ValidationTableReport:
        canonical_count = len(canonical_rows)
        verified = sum(
            1
            for row in canonical_rows
            if getattr(row, "data_quality_status", None) == CanonicalDataQualityStatus.VERIFIED
        )
        partial = sum(
            1
            for row in canonical_rows
            if getattr(row, "data_quality_status", None) == CanonicalDataQualityStatus.PARTIAL
        )
        unresolved = unresolved_count
        unsafe = unsafe_count
        samples = [self._sample_row(row) for row in canonical_rows[:3]]
        return CanonicalV2ValidationTableReport(
            table=table,
            raw_source_count=raw_source_count,
            canonical_count=canonical_count,
            verified=verified,
            partial=partial,
            unresolved=unresolved,
            unsafe=unsafe,
            duplicates=duplicate_count,
            samples=samples,
            notes=notes,
        )

    def _sample_row(self, row: Any) -> dict[str, Any]:
        if hasattr(row, "model_dump"):
            return row.model_dump(mode="json")
        if isinstance(row, dict):
            return dict(row)
        return {"value": str(row)}

    @staticmethod
    def _organization_scope_name(organizations: list[SmartUpOrganization]) -> str:
        if not organizations:
            return "no organizations"
        if len(organizations) == 1:
            return organizations[0].name
        return ", ".join(organization.name for organization in organizations)

    def _product_index_for_organization(
        self,
        organization_id: UUID,
    ) -> dict[str, CanonicalProduct]:
        cached = self._product_index.get(organization_id)
        if cached is not None:
            return cached
        index: dict[str, CanonicalProduct] = {}
        for product in self.store.list_canonical_products(organization_id=organization_id):
            for key in (
                product.source_external_id,
                product.product_id,
                product.code,
                product.article_code,
            ):
                normalized = self._clean_text(key)
                if normalized is not None and normalized not in index:
                    index[normalized] = product
        self._product_index[organization_id] = index
        return index

    def _warehouse_index_for_organization(
        self,
        organization_id: UUID,
    ) -> dict[str, CanonicalWarehouse]:
        cached = self._warehouse_index.get(organization_id)
        if cached is not None:
            return cached
        index: dict[str, CanonicalWarehouse] = {}
        for warehouse in self.store.list_canonical_warehouses(organization_id=organization_id):
            for key in (
                warehouse.source_external_id,
                warehouse.warehouse_id,
                warehouse.warehouse_code,
                warehouse.warehouse_name,
            ):
                normalized = self._clean_text(key)
                if normalized is not None and normalized not in index:
                    index[normalized] = warehouse
        self._warehouse_index[organization_id] = index
        return index

    def _price_type_index_for_organization(
        self,
        organization_id: UUID,
    ) -> dict[str, CanonicalPriceType]:
        cached = self._price_type_index.get(organization_id)
        if cached is not None:
            return cached
        index: dict[str, CanonicalPriceType] = {}
        for price_type in self.store.list_canonical_price_types(organization_id=organization_id):
            for key in (
                price_type.source_external_id,
                price_type.price_type_id,
                price_type.code,
                price_type.short_name,
            ):
                normalized = self._clean_text(key)
                if normalized is not None and normalized not in index:
                    index[normalized] = price_type
        self._price_type_index[organization_id] = index
        return index

    def _purchase_item_product_index_for_organization(
        self,
        organization_id: UUID,
    ) -> dict[str, UUID]:
        cached = self._purchase_item_product_index.get(organization_id)
        if cached is not None:
            return cached
        index: dict[str, UUID] = {}
        for item in self.store.list_canonical_purchase_items(organization_id=organization_id):
            key = self._clean_text(item.purchase_item_id)
            if key is None or item.product_id is None:
                continue
            index.setdefault(key, item.product_id)
        self._purchase_item_product_index[organization_id] = index
        return index

    @staticmethod
    def _clean_text(value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _parse_decimal(value: object | None, default: str = "0") -> Decimal:
        if isinstance(value, Decimal):
            return value
        if value is None or value == "":
            return Decimal(default)
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return Decimal(default)

    @staticmethod
    def _first_text(row: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = row.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    @staticmethod
    def _list_of_text(row: dict[str, Any], *keys: str) -> list[str]:
        values: list[str] = []
        for key in keys:
            value = row.get(key)
            if isinstance(value, list):
                for item in value:
                    text = SmartUpCanonicalV2FoundationService._clean_text(item)
                    if text and text not in values:
                        values.append(text)
            else:
                text = SmartUpCanonicalV2FoundationService._clean_text(value)
                if text and text not in values:
                    values.append(text)
        return values

    @staticmethod
    def _list_of_dicts(row: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
        for key in keys:
            value = row.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _source_kind_for_product(source_endpoint: str, row: dict[str, Any]) -> str | None:
        if source_endpoint.endswith("inventory$export"):
            return "inventory"
        if source_endpoint.endswith("service$export"):
            return "service"
        if source_endpoint.endswith("producer$export"):
            return "producer"
        return SmartUpCanonicalV2FoundationService._clean_text(
            row.get("source_kind") or row.get("product_kind") or row.get("kind"),
        )

    @staticmethod
    def _source_kind_for_warehouse(source_endpoint: str, row: dict[str, Any]) -> str | None:
        return SmartUpCanonicalV2FoundationService._clean_text(
            row.get("source_kind") or row.get("warehouse_kind") or source_endpoint.rsplit("/", 1)[-1],
        )

    @staticmethod
    def _source_kind_for_sales_rep(source_endpoint: str, row: dict[str, Any]) -> str | None:
        if source_endpoint.endswith("visit$export"):
            return "visit"
        if source_endpoint.endswith("cashin$export"):
            return "payment"
        return SmartUpCanonicalV2FoundationService._clean_text(row.get("role") or row.get("kind"))

    @staticmethod
    def _source_kind_for_working_zone(source_endpoint: str, row: dict[str, Any]) -> str | None:
        if source_endpoint.endswith("visit$export"):
            return "visit"
        if source_endpoint.endswith("order$export"):
            return "sale"
        return SmartUpCanonicalV2FoundationService._clean_text(row.get("source_kind"))
