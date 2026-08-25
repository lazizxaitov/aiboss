"""SmartUp core-data rebuild from stored raw records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.core_upsert import CoreUpsertService
from app.integrations.smartup.models import SmartUpOrganization, SmartUpRawRecord
from app.integrations.smartup.pipeline import SmartUpImportPipeline

_ENTITY_PLAN: list[str] = [
    "customers",
    "product_categories",
    "products",
    "warehouses",
    "price_types",
    "product_prices",
    "sales",
    "sale_items",
    "payments",
    "returns",
    "visits",
    "inventory_balances",
    "purchases",
    "warehouse_receipts",
    "cross_organizational_movements",
    "internal_movements",
    "write_offs",
    "stocktakings",
    "return_to_suppliers",
    "bank_operations",
    "logistics",
    "equipment_movements",
    "equipment_requests",
]

_RAW_ENTITY_BY_TARGET = {
    "product_prices": ("price_points",),
    "customers": ("customers", "sales", "payments", "visits"),
    "warehouses": (
        "warehouses",
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
}

_CUSTOMER_SOURCE_FIELDS = (
    ("person_id", "person_code", "client_id", "client_code", "person_local_code"),
    ("person_name", "client_name", "name", "short_name"),
)

_WAREHOUSE_CODE_FIELDS = (
    "warehouse_code",
    "room_code",
    "warehouse_id",
    "room_id",
)

_WAREHOUSE_NAME_FIELDS = (
    "warehouse_name",
    "room_name",
    "name",
    "short_name",
)


class SmartUpCoreRebuildEntityReport(BaseModel):
    """One entity-level rebuild report."""

    organization_id: UUID
    organization_name: str
    entity_type: str
    raw_records: int = 0
    before_core: int = 0
    after_core: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    derived_records: int = 0
    unresolved: int = 0
    notes: list[str] = Field(default_factory=list)


class SmartUpCoreRebuildReport(BaseModel):
    """Aggregate report returned by a rebuild run."""

    dry_run: bool
    force: bool
    organization_id: UUID | None = None
    entity_type: str | None = None
    organizations: int = 0
    raw_records: int = 0
    before_core: dict[str, int] = Field(default_factory=dict)
    after_core: dict[str, int] = Field(default_factory=dict)
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    derived_records: int = 0
    unresolved: int = 0
    would_insert: int = 0
    would_update: int = 0
    would_archive: int = 0
    items: list[SmartUpCoreRebuildEntityReport] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class SmartUpCoreRebuildService:
    """Rebuild normalized core data from SmartUp raw records."""

    store: CoreDataStore
    pipeline: SmartUpImportPipeline = field(init=False)
    upsert_service: CoreUpsertService = field(init=False)

    def __post_init__(self) -> None:
        self.pipeline = SmartUpImportPipeline(self.store)
        self.upsert_service = CoreUpsertService(self.store)

    def rebuild_all(
        self,
        *,
        dry_run: bool = False,
        force: bool = False,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
    ) -> SmartUpCoreRebuildReport:
        organizations = self._target_organizations(organization_id)
        target_entities = self._target_entities(entity_type)
        before_core = self._snapshot_core_counts_for_organizations(organizations, target_entities)
        report = SmartUpCoreRebuildReport(
            dry_run=dry_run,
            force=force,
            organization_id=organization_id,
            entity_type=entity_type,
            organizations=len(organizations),
            before_core=before_core,
        )
        for organization in organizations:
            for current_entity in target_entities:
                item = self._rebuild_entity_for_organization(
                    organization=organization,
                    entity_type=current_entity,
                    dry_run=dry_run,
                    force=force,
                )
                report.items.append(item)
                self._accumulate(report, item)
        report.after_core = self._snapshot_core_counts_for_organizations(
            organizations, target_entities
        )
        return report

    def rebuild_organization(
        self,
        organization_id: UUID,
        *,
        dry_run: bool = False,
        force: bool = False,
        entity_type: str | None = None,
    ) -> SmartUpCoreRebuildReport:
        return self.rebuild_all(
            dry_run=dry_run,
            force=force,
            organization_id=organization_id,
            entity_type=entity_type,
        )

    def rebuild_entity(
        self,
        entity_type: str,
        *,
        dry_run: bool = False,
        force: bool = False,
        organization_id: UUID | None = None,
    ) -> SmartUpCoreRebuildReport:
        return self.rebuild_all(
            dry_run=dry_run,
            force=force,
            organization_id=organization_id,
            entity_type=entity_type,
        )

    def rebuild_raw_record(
        self,
        raw_id: UUID,
        *,
        dry_run: bool = False,
        force: bool = False,
    ) -> SmartUpCoreRebuildReport:
        raw_record = self.store.get_smartup_raw_record(raw_id)
        if raw_record is None:
            raise ValueError("Raw SmartUp record not found")
        organization = self.store.get_smartup_organization(raw_record.organization_id)
        if organization is None:
            raise ValueError("SmartUp organization not found for raw record")

        report = SmartUpCoreRebuildReport(
            dry_run=dry_run,
            force=force,
            organization_id=organization.id,
            entity_type=raw_record.entity_type,
            organizations=1,
        )
        item = self._rebuild_single_raw_record(
            organization, raw_record, dry_run=dry_run, force=force
        )
        report.items.append(item)
        self._accumulate(report, item)
        report.before_core = self._snapshot_core_counts(organization.id, [item.entity_type])
        report.after_core = self._snapshot_core_counts(organization.id, [item.entity_type])
        return report

    def _target_organizations(self, organization_id: UUID | None) -> list[SmartUpOrganization]:
        organizations = list(
            self.store.list_smartup_organizations(is_active=True),
        )
        if organization_id is not None:
            organizations = [item for item in organizations if item.id == organization_id]
        return organizations

    def _target_entities(self, entity_type: str | None) -> list[str]:
        if entity_type is None:
            return list(_ENTITY_PLAN)
        target = self._normalize_target_entity_type(entity_type)
        if target not in _ENTITY_PLAN:
            raise ValueError(f"Unsupported rebuild entity type: {entity_type}")
        return [target]

    def _normalize_target_entity_type(self, entity_type: str) -> str:
        if entity_type == "price_points":
            return "product_prices"
        return entity_type

    def _rebuild_entity_for_organization(
        self,
        *,
        organization: SmartUpOrganization,
        entity_type: str,
        dry_run: bool,
        force: bool,
    ) -> SmartUpCoreRebuildEntityReport:
        if entity_type == "customers":
            return self._rebuild_customers(organization, dry_run=dry_run, force=force)
        if entity_type == "warehouses":
            return self._rebuild_warehouses(organization, dry_run=dry_run, force=force)
        if entity_type == "price_types":
            return self._rebuild_raw_entity(
                organization,
                source_entity_types=("price_types",),
                target_entity_type="price_types",
                dry_run=dry_run,
                force=force,
            )
        if entity_type == "sale_items":
            before_core = self._count_core_entities(organization.id, "sale_items")
            after_core = before_core
            return SmartUpCoreRebuildEntityReport(
                organization_id=organization.id,
                organization_name=organization.name,
                entity_type="sale_items",
                raw_records=0,
                before_core=before_core,
                after_core=after_core,
                notes=["derived_from_sales"],
            )
        if entity_type == "product_prices":
            return self._rebuild_raw_entity(
                organization,
                source_entity_types=("price_points",),
                target_entity_type="product_prices",
                dry_run=dry_run,
                force=force,
            )
        return self._rebuild_raw_entity(
            organization,
            source_entity_types=(entity_type,),
            target_entity_type=entity_type,
            dry_run=dry_run,
            force=force,
        )

    def _rebuild_raw_entity(
        self,
        organization: SmartUpOrganization,
        *,
        source_entity_types: tuple[str, ...],
        target_entity_type: str,
        dry_run: bool,
        force: bool,
    ) -> SmartUpCoreRebuildEntityReport:
        raw_records: list[SmartUpRawRecord] = []
        for source_entity_type in source_entity_types:
            raw_records.extend(
                self.store.list_smartup_raw_records(
                    organization_id=organization.id,
                    entity_type=source_entity_type,
                ),
            )
        before_core = self._count_core_entities(organization.id, target_entity_type)
        inserted = updated = skipped = failed = unresolved = derived_records = 0
        notes: list[str] = []

        for raw_record in raw_records:
            normalized = self.pipeline.normalizers.get(raw_record.entity_type)
            if normalized is None and raw_record.entity_type == "price_points":
                normalized = self.pipeline.normalizers.get("product_prices")
            if normalized is None:
                skipped += 1
                notes.append(f"no_normalizer:{raw_record.entity_type}")
                continue
            preview = normalized.normalize(raw_record)
            if preview.skipped:
                skipped += 1
                if preview.skip_reason:
                    notes.append(preview.skip_reason)
                continue
            derived_records += len(preview.related_entities)
            if dry_run:
                inserted += int(
                    self._preview_is_insert(
                        organization.id,
                        preview.entity_type,
                        preview.normalized_data,
                    ),
                )
                updated += int(
                    not self._preview_is_insert(
                        organization.id,
                        preview.entity_type,
                        preview.normalized_data,
                    )
                )
                continue
            result = self.pipeline.process_raw_record_with_options(raw_record, force=force)
            if result.action == "failed":
                failed += 1
            elif result.action == "skipped":
                skipped += 1
            elif result.action == "inserted":
                inserted += 1
            elif result.action == "updated":
                updated += 1
            else:
                skipped += 1
            unresolved += result.issue_count

        after_core = self._count_core_entities(organization.id, target_entity_type)
        return SmartUpCoreRebuildEntityReport(
            organization_id=organization.id,
            organization_name=organization.name,
            entity_type=target_entity_type,
            raw_records=len(raw_records),
            before_core=before_core,
            after_core=after_core,
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            failed=failed,
            derived_records=derived_records,
            unresolved=unresolved,
            notes=notes,
        )

    def _rebuild_customers(
        self,
        organization: SmartUpOrganization,
        *,
        dry_run: bool,
        force: bool,
    ) -> SmartUpCoreRebuildEntityReport:
        raw_records = list(
            self.store.list_smartup_raw_records(
                organization_id=organization.id,
                entity_type="customers",
            ),
        )
        before_core = self._count_core_entities(organization.id, "customers")
        inserted = updated = skipped = failed = unresolved = derived_records = 0
        notes: list[str] = []

        for raw_record in raw_records:
            if dry_run:
                normalized = self.pipeline.normalizers.get("customers")
                if normalized is None:
                    skipped += 1
                    continue
                preview = normalized.normalize(raw_record)
                if preview.skipped:
                    skipped += 1
                    if preview.skip_reason:
                        notes.append(preview.skip_reason)
                    continue
                derived_records += 1
                if self._preview_is_insert(
                    organization.id, preview.entity_type, preview.normalized_data
                ):
                    inserted += 1
                else:
                    updated += 1
                continue
            result = self.pipeline.process_raw_record_with_options(raw_record, force=force)
            if result.action == "failed":
                failed += 1
            elif result.action == "skipped":
                skipped += 1
            elif result.action == "inserted":
                inserted += 1
            elif result.action == "updated":
                updated += 1
            else:
                skipped += 1
            unresolved += result.issue_count

        for candidate in self._customer_candidates(organization.id):
            derived_records += 1
            if dry_run:
                if self._preview_is_insert(organization.id, "customers", candidate):
                    inserted += 1
                else:
                    updated += 1
                continue
            outcome = self.upsert_service.upsert_entity("customers", candidate)
            if outcome.action == "inserted":
                inserted += 1
            elif outcome.action == "updated":
                updated += 1
            else:
                skipped += 1

        after_core = self._count_core_entities(organization.id, "customers")
        if before_core and after_core > before_core:
            notes.append("derived_customers_from_sales_payments_visits")
        return SmartUpCoreRebuildEntityReport(
            organization_id=organization.id,
            organization_name=organization.name,
            entity_type="customers",
            raw_records=len(raw_records),
            before_core=before_core,
            after_core=after_core,
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            failed=failed,
            derived_records=derived_records,
            unresolved=unresolved,
            notes=notes,
        )

    def _rebuild_warehouses(
        self,
        organization: SmartUpOrganization,
        *,
        dry_run: bool,
        force: bool,
    ) -> SmartUpCoreRebuildEntityReport:
        before_core = self._count_core_entities(organization.id, "warehouses")
        inserted = updated = skipped = failed = unresolved = derived_records = 0
        notes: list[str] = []
        raw_records = list(
            self.store.list_smartup_raw_records(
                organization_id=organization.id,
                entity_type="warehouses",
            ),
        )

        for raw_record in raw_records:
            if dry_run:
                normalized = self.pipeline.normalizers.get("warehouses")
                if normalized is None:
                    skipped += 1
                    continue
                preview = normalized.normalize(raw_record)
                if preview.skipped:
                    skipped += 1
                    if preview.skip_reason:
                        notes.append(preview.skip_reason)
                    continue
                derived_records += 1
                if self._preview_is_insert(
                    organization.id, preview.entity_type, preview.normalized_data
                ):
                    inserted += 1
                else:
                    updated += 1
                continue
            result = self.pipeline.process_raw_record_with_options(raw_record, force=force)
            if result.action == "failed":
                failed += 1
            elif result.action == "skipped":
                skipped += 1
            elif result.action == "inserted":
                inserted += 1
            elif result.action == "updated":
                updated += 1
            else:
                skipped += 1
            unresolved += result.issue_count

        for candidate in self._warehouse_candidates(organization.id):
            derived_records += 1
            if dry_run:
                if self._preview_is_insert(organization.id, "warehouses", candidate):
                    inserted += 1
                else:
                    updated += 1
                continue
            outcome = self.upsert_service.upsert_entity("warehouses", candidate)
            if outcome.action == "inserted":
                inserted += 1
            elif outcome.action == "updated":
                updated += 1
            else:
                skipped += 1
        after_core = self._count_core_entities(organization.id, "warehouses")
        if after_core > before_core:
            notes.append("derived_from_transactional_warehouse_codes")
        return SmartUpCoreRebuildEntityReport(
            organization_id=organization.id,
            organization_name=organization.name,
            entity_type="warehouses",
            raw_records=0,
            before_core=before_core,
            after_core=after_core,
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            failed=failed,
            derived_records=derived_records,
            unresolved=unresolved,
            notes=notes,
        )

    def _rebuild_single_raw_record(
        self,
        organization: SmartUpOrganization,
        raw_record: SmartUpRawRecord,
        *,
        dry_run: bool,
        force: bool,
    ) -> SmartUpCoreRebuildEntityReport:
        before_core = self._count_core_entities(
            organization.id,
            self._normalize_target_entity_type(raw_record.entity_type),
        )
        if dry_run:
            result = self.pipeline.normalizers.get(raw_record.entity_type)
            if result is None and raw_record.entity_type == "price_points":
                result = self.pipeline.normalizers.get("product_prices")
            if result is None:
                return SmartUpCoreRebuildEntityReport(
                    organization_id=organization.id,
                    organization_name=organization.name,
                    entity_type=raw_record.entity_type,
                    raw_records=1,
                    before_core=before_core,
                    after_core=before_core,
                    skipped=1,
                    notes=[f"no_normalizer:{raw_record.entity_type}"],
                )
            preview = result.normalize(raw_record)
            if preview.skipped:
                return SmartUpCoreRebuildEntityReport(
                    organization_id=organization.id,
                    organization_name=organization.name,
                    entity_type=preview.entity_type,
                    raw_records=1,
                    before_core=before_core,
                    after_core=before_core,
                    skipped=1,
                    notes=[preview.skip_reason or "skipped"],
                )
            inserted = int(
                self._preview_is_insert(
                    organization.id, preview.entity_type, preview.normalized_data
                )
            )
            updated = int(
                not self._preview_is_insert(
                    organization.id, preview.entity_type, preview.normalized_data
                )
            )
            after_core = before_core + inserted
            return SmartUpCoreRebuildEntityReport(
                organization_id=organization.id,
                organization_name=organization.name,
                entity_type=preview.entity_type,
                raw_records=1,
                before_core=before_core,
                after_core=after_core,
                inserted=inserted,
                updated=updated,
            )

        result = self.pipeline.process_raw_record_with_options(raw_record, force=force)
        after_core = self._count_core_entities(
            organization.id,
            self._normalize_target_entity_type(raw_record.entity_type),
        )
        return SmartUpCoreRebuildEntityReport(
            organization_id=organization.id,
            organization_name=organization.name,
            entity_type=self._normalize_target_entity_type(raw_record.entity_type),
            raw_records=1,
            before_core=before_core,
            after_core=after_core,
            inserted=int(result.action == "inserted"),
            updated=int(result.action == "updated"),
            skipped=int(result.action == "skipped"),
            failed=int(result.action == "failed"),
            unresolved=result.issue_count,
            notes=[] if result.action != "skipped" else ["single_raw_record_rebuilt"],
        )

    def _customer_candidates(self, organization_id: UUID) -> list[dict[str, Any]]:
        candidates: dict[str, dict[str, Any]] = {}
        for entity_type in ("sales", "payments", "visits"):
            for raw_record in self.store.list_smartup_raw_records(
                organization_id=organization_id,
                entity_type=entity_type,
            ):
                payload = raw_record.response_payload
                if not isinstance(payload, dict):
                    continue
                source_external_id = self._first_text(payload, *_CUSTOMER_SOURCE_FIELDS[0])
                display_name = self._first_text(payload, *_CUSTOMER_SOURCE_FIELDS[1])
                if source_external_id is None:
                    source_external_id = display_name
                if source_external_id is None:
                    continue
                if display_name is None:
                    display_name = source_external_id
                candidate = {
                    "organization_id": organization_id,
                    "source_system": "smartup",
                    "source_external_id": source_external_id,
                    "source_filial_id": str(payload.get("filial_id") or raw_record.filial_id or ""),
                    "source_payload_id": str(
                        payload.get("person_id")
                        or payload.get("client_id")
                        or payload.get("visit_id")
                        or source_external_id
                    ),
                    "name": display_name,
                    "display_name": display_name,
                    "phone": self._first_text(payload, "main_phone", "phone", "mobile_phone"),
                    "email": self._first_text(payload, "email"),
                    "metadata": {
                        "source_entity_type": entity_type,
                        "source_raw_record_id": str(raw_record.id),
                        "tax_id": self._first_text(payload, "person_tin", "client_tin"),
                        "customer_type": "derived",
                    },
                }
                candidates[source_external_id] = candidate
        return list(candidates.values())

    def _warehouse_candidates(self, organization_id: UUID) -> list[dict[str, Any]]:
        candidates: dict[str, dict[str, Any]] = {}
        source_entities = (
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
        )
        for entity_type in source_entities:
            for raw_record in self.store.list_smartup_raw_records(
                organization_id=organization_id,
                entity_type=entity_type,
            ):
                payload = raw_record.response_payload
                if not isinstance(payload, dict):
                    continue
                code = self._first_text(payload, *_WAREHOUSE_CODE_FIELDS)
                if code is None:
                    continue
                name = self._first_text(payload, *_WAREHOUSE_NAME_FIELDS)
                candidate = {
                    "organization_id": organization_id,
                    "source_system": "smartup",
                    "source_external_id": code,
                    "source_filial_id": str(payload.get("filial_id") or raw_record.filial_id or ""),
                    "source_payload_id": str(
                        payload.get("warehouse_id")
                        or payload.get("room_id")
                        or payload.get("warehouse_code")
                        or payload.get("room_code")
                        or code
                    ),
                    "name": name,
                    "code": code,
                    "metadata": {
                        "source_entity_type": entity_type,
                        "source_raw_record_id": str(raw_record.id),
                        "derived_from_transactions": True,
                    },
                }
                existing = candidates.get(code)
                if existing is None or (not existing.get("name") and name):
                    candidates[code] = candidate
        return list(candidates.values())

    def _preview_is_insert(
        self,
        organization_id: UUID,
        entity_type: str,
        payload: dict[str, Any],
    ) -> bool:
        source_external_id = payload.get("source_external_id")
        if not source_external_id:
            return False
        entity_id = self.upsert_service._stable_entity_id(  # noqa: SLF001
            organization_id=organization_id,
            entity_type=entity_type,
            source_system=str(payload.get("source_system") or "smartup"),
            source_external_id=str(source_external_id),
        )
        existing = self._fetch_existing(entity_type, entity_id)
        return existing is None

    def _fetch_existing(self, entity_type: str, entity_id: UUID) -> object | None:
        lookup = {
            "customers": self.store.get_customer,
            "product_categories": self.store.get_product_category,
            "products": self.store.get_product,
            "warehouses": self.store.get_warehouse,
            "price_types": self.store.get_price_type,
            "product_prices": self.store.get_product_price,
            "sales": self.store.get_sale_v2,
            "sale_items": self.store.get_sale_item,
            "payments": self.store.get_payment,
            "inventory_balances": self.store.get_inventory_balance,
            "visits": self.store.get_visit,
            "bank_operations": self.store.get_bank_operation,
            "business_documents": self.store.get_business_document,
            "business_document_items": self.store.get_business_document_item,
        }.get(entity_type)
        if lookup is None:
            return None
        return lookup(entity_id)

    def _count_core_entities(self, organization_id: UUID, entity_type: str) -> int:
        lookup = {
            "customers": self.store.list_customers,
            "product_categories": self.store.list_product_categories,
            "products": self.store.list_products,
            "warehouses": self.store.list_warehouses,
            "price_types": self.store.list_price_types,
            "product_prices": self.store.list_product_prices,
            "sales": self.store.list_sales_v2,
            "sale_items": self.store.list_sale_items,
            "payments": self.store.list_payments,
            "inventory_balances": self.store.list_inventory_balances,
            "visits": self.store.list_visits,
            "bank_operations": self.store.list_bank_operations,
            "business_documents": self.store.list_business_documents,
            "business_document_items": self.store.list_business_document_items,
        }.get(entity_type)
        if lookup is None:
            return 0
        return len(list(lookup(organization_id=organization_id)))

    def _snapshot_core_counts(
        self,
        organization_id: UUID | None,
        entity_types: list[str],
    ) -> dict[str, int]:
        if organization_id is None:
            return {entity: 0 for entity in entity_types}
        return {
            entity: self._count_core_entities(organization_id, entity) for entity in entity_types
        }

    def _snapshot_core_counts_for_organizations(
        self,
        organizations: list[SmartUpOrganization],
        entity_types: list[str],
    ) -> dict[str, int]:
        totals = {entity: 0 for entity in entity_types}
        for organization in organizations:
            for entity in entity_types:
                totals[entity] += self._count_core_entities(organization.id, entity)
        return totals

    def _accumulate(
        self,
        report: SmartUpCoreRebuildReport,
        item: SmartUpCoreRebuildEntityReport,
    ) -> None:
        report.raw_records += item.raw_records
        report.inserted += item.inserted
        report.updated += item.updated
        report.skipped += item.skipped
        report.failed += item.failed
        report.derived_records += item.derived_records
        report.unresolved += item.unresolved
        report.would_insert += item.inserted
        report.would_update += item.updated
        report.would_archive += 0

    @staticmethod
    def _first_text(payload: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None
