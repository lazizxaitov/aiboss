"""SmartUp migration helpers for the core data layer."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, Field

from app.core.data_layer.entities import (
    BusinessProfile,
    ContactProfile,
    FinanceEntry,
    FinanceEntryType,
    MarketingActivity,
    MarketingChannel,
    SaleRecord,
    SaleStage,
    SourceSystem,
)
from app.core.data_layer.models import CoreRecord, CoreRecordKind, DataSourceType


class SmartUpBusinessRow(BaseModel):
    """Raw business row from SmartUp export."""

    external_business_id: str
    name: str
    legal_name: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class SmartUpContactRow(BaseModel):
    """Raw contact row from SmartUp export."""

    external_customer_id: str
    external_business_id: str
    full_name: str
    email: str | None = None
    phone: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class SmartUpSaleRow(BaseModel):
    """Raw sale row from SmartUp export."""

    external_sale_id: str
    external_business_id: str
    external_customer_id: str | None = None
    amount: Decimal
    currency: str = "USD"
    stage: SaleStage = SaleStage.WON
    occurred_at: datetime
    metadata: dict[str, object] = Field(default_factory=dict)


class SmartUpMarketingRow(BaseModel):
    """Raw marketing row from SmartUp export."""

    external_activity_id: str
    external_business_id: str
    channel: MarketingChannel
    campaign_name: str
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    spend: Decimal = Decimal("0")
    occurred_at: datetime
    metadata: dict[str, object] = Field(default_factory=dict)


class SmartUpFinanceRow(BaseModel):
    """Raw finance row from SmartUp export."""

    external_entry_id: str
    external_business_id: str
    entry_type: FinanceEntryType
    category: str
    amount: Decimal
    currency: str = "USD"
    occurred_at: datetime
    metadata: dict[str, object] = Field(default_factory=dict)


class SmartUpExportBundle(BaseModel):
    """Container for an exported SmartUp dataset."""

    businesses: list[SmartUpBusinessRow] = Field(default_factory=list)
    contacts: list[SmartUpContactRow] = Field(default_factory=list)
    sales: list[SmartUpSaleRow] = Field(default_factory=list)
    marketing: list[SmartUpMarketingRow] = Field(default_factory=list)
    finance: list[SmartUpFinanceRow] = Field(default_factory=list)


class SmartUpMigrationReport(BaseModel):
    """Summary of a SmartUp migration run."""

    source_systems_imported: int = 0
    businesses_imported: int = 0
    contacts_imported: int = 0
    sales_imported: int = 0
    marketing_imported: int = 0
    finance_imported: int = 0
    warnings: list[str] = Field(default_factory=list)


class SmartUpBundleValidationReport(BaseModel):
    """Validation summary for a SmartUp export bundle."""

    valid: bool = True
    businesses: int = 0
    contacts: int = 0
    sales: int = 0
    marketing: int = 0
    finance: int = 0
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class SmartUpOfflineMigrationReport(BaseModel):
    """Combined validation and import report for offline SmartUp migration."""

    validation: SmartUpBundleValidationReport
    import_report: SmartUpMigrationReport
    status: str = "completed"


class SmartUpHistoryMigrationReport(BaseModel):
    """Final report for a history migration run."""

    run_type: Literal["history"] = "history"
    status: str = "completed"
    business_id: UUID
    business_name: str
    history_start: datetime
    history_end: datetime | None = None
    chunk_days: int
    storage_backend: str
    counters: dict[str, int]
    warnings: list[str] = Field(default_factory=list)


def _stable_uuid(scope: str, external_id: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"smartup:{scope}:{external_id}")


@dataclass(slots=True)
class SmartUpMigrationService:
    """Transform SmartUp exports into the core data layer."""

    target: object
    imported_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def import_bundle(self, bundle: SmartUpExportBundle) -> SmartUpMigrationReport:
        business_map: dict[str, UUID] = {}
        contact_map: dict[tuple[str, str], UUID] = {}
        report = SmartUpMigrationReport()

        for row in bundle.businesses:
            business = BusinessProfile(
                business_id=_stable_uuid("business", row.external_business_id),
                name=row.name,
                legal_name=row.legal_name,
                external_ref=row.external_business_id,
                metadata={"source": "SmartUp", **row.metadata},
            )
            self.target.register_business(business)
            self.target.register_source_system(
                SourceSystem(
                    source_system_id=_stable_uuid("source_system", row.external_business_id),
                    business_id=business.business_id,
                    name="SmartUp",
                    source_type="erp",
                    external_ref=row.external_business_id,
                    metadata={"source": "SmartUp", **row.metadata},
                ),
            )
            business_map[row.external_business_id] = business.business_id
            report.source_systems_imported += 1
            report.businesses_imported += 1

        for row in bundle.contacts:
            business_id = business_map.get(row.external_business_id)
            if business_id is None:
                report.warnings.append(
                    "Contact "
                    f"{row.external_customer_id} skipped: business "
                    f"{row.external_business_id} missing",
                )
                continue
            contact = ContactProfile(
                contact_id=_stable_uuid("contact", row.external_customer_id),
                business_id=business_id,
                full_name=row.full_name,
                email=row.email,
                phone=row.phone,
                source="SmartUp",
                external_ref=row.external_customer_id,
                metadata={"source": "SmartUp", **row.metadata},
            )
            self.target.upsert_contact(contact)
            contact_map[(row.external_business_id, row.external_customer_id)] = contact.contact_id
            self.target.ingest_record(
                CoreRecord(
                    record_id=_stable_uuid("record:contact", row.external_customer_id),
                    business_id=business_id,
                    source="SmartUp",
                    source_type=DataSourceType.IMPORT,
                    kind=CoreRecordKind.CUSTOMER,
                    payload=contact.model_dump(),
                    occurred_at=self.imported_at,
                    ingested_at=self.imported_at,
                    metadata={"external_business_id": row.external_business_id},
                ),
            )
            report.contacts_imported += 1

        for row in bundle.sales:
            business_id = business_map.get(row.external_business_id)
            if business_id is None:
                report.warnings.append(
                    "Sale "
                    f"{row.external_sale_id} skipped: business "
                    f"{row.external_business_id} missing",
                )
                continue
            contact_id = None
            if row.external_customer_id is not None:
                contact_id = contact_map.get((row.external_business_id, row.external_customer_id))
            sale = SaleRecord(
                sale_id=_stable_uuid("sale", row.external_sale_id),
                business_id=business_id,
                contact_id=contact_id,
                external_ref=row.external_sale_id,
                amount=row.amount,
                currency=row.currency,
                stage=row.stage,
                occurred_at=row.occurred_at,
                source="SmartUp",
                metadata={"source": "SmartUp", **row.metadata},
            )
            self.target.upsert_sale(sale)
            self.target.ingest_record(
                CoreRecord(
                    record_id=_stable_uuid("record:sale", row.external_sale_id),
                    business_id=business_id,
                    source="SmartUp",
                    source_type=DataSourceType.IMPORT,
                    kind=CoreRecordKind.SALE,
                    payload=sale.model_dump(),
                    occurred_at=row.occurred_at,
                    ingested_at=self.imported_at,
                    metadata={"external_business_id": row.external_business_id},
                ),
            )
            report.sales_imported += 1

        for row in bundle.marketing:
            business_id = business_map.get(row.external_business_id)
            if business_id is None:
                report.warnings.append(
                    "Marketing activity "
                    f"{row.external_activity_id} skipped: business "
                    f"{row.external_business_id} missing",
                )
                continue
            activity = MarketingActivity(
                activity_id=_stable_uuid("marketing", row.external_activity_id),
                business_id=business_id,
                external_ref=row.external_activity_id,
                channel=row.channel,
                campaign_name=row.campaign_name,
                impressions=row.impressions,
                clicks=row.clicks,
                conversions=row.conversions,
                spend=row.spend,
                occurred_at=row.occurred_at,
                source="SmartUp",
                metadata={"source": "SmartUp", **row.metadata},
            )
            self.target.upsert_marketing_activity(activity)
            self.target.ingest_record(
                CoreRecord(
                    record_id=_stable_uuid("record:marketing", row.external_activity_id),
                    business_id=business_id,
                    source="SmartUp",
                    source_type=DataSourceType.IMPORT,
                    kind=CoreRecordKind.MARKETING,
                    payload=activity.model_dump(),
                    occurred_at=row.occurred_at,
                    ingested_at=self.imported_at,
                    metadata={"external_business_id": row.external_business_id},
                ),
            )
            report.marketing_imported += 1

        for row in bundle.finance:
            business_id = business_map.get(row.external_business_id)
            if business_id is None:
                report.warnings.append(
                    "Finance entry "
                    f"{row.external_entry_id} skipped: business "
                    f"{row.external_business_id} missing",
                )
                continue
            entry = FinanceEntry(
                entry_id=_stable_uuid("finance", row.external_entry_id),
                business_id=business_id,
                external_ref=row.external_entry_id,
                entry_type=row.entry_type,
                category=row.category,
                amount=row.amount,
                currency=row.currency,
                occurred_at=row.occurred_at,
                source="SmartUp",
                metadata={"source": "SmartUp", **row.metadata},
            )
            self.target.upsert_finance_entry(entry)
            self.target.ingest_record(
                CoreRecord(
                    record_id=_stable_uuid("record:finance", row.external_entry_id),
                    business_id=business_id,
                    source="SmartUp",
                    source_type=DataSourceType.IMPORT,
                    kind=CoreRecordKind.FINANCE,
                    payload=entry.model_dump(),
                    occurred_at=row.occurred_at,
                    ingested_at=self.imported_at,
                    metadata={"external_business_id": row.external_business_id},
                ),
            )
            report.finance_imported += 1

        return report


@dataclass(slots=True)
class SmartUpOfflineMigrationService:
    """Validate and import SmartUp export bundles without a live account."""

    target: object
    imported_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def run(self, bundle: SmartUpExportBundle) -> SmartUpOfflineMigrationReport:
        validation = validate_bundle(bundle)
        import_report = SmartUpMigrationService(
            target=self.target,
            imported_at=self.imported_at,
        ).import_bundle(bundle)
        status = "completed" if validation.valid else "completed_with_warnings"
        return SmartUpOfflineMigrationReport(
            validation=validation,
            import_report=import_report,
            status=status,
        )


def validate_bundle(bundle: SmartUpExportBundle) -> SmartUpBundleValidationReport:
    """Validate a SmartUp export bundle before import."""

    report = SmartUpBundleValidationReport(
        businesses=len(bundle.businesses),
        contacts=len(bundle.contacts),
        sales=len(bundle.sales),
        marketing=len(bundle.marketing),
        finance=len(bundle.finance),
    )
    business_ids = [row.external_business_id for row in bundle.businesses]
    known_business_ids = set(business_ids)

    _record_duplicates(report, business_ids, "business")

    for row in bundle.contacts:
        if row.external_business_id not in known_business_ids:
            report.errors.append(
                "Contact "
                f"{row.external_customer_id} references missing business "
                f"{row.external_business_id}",
            )

    for row in bundle.sales:
        if row.external_business_id not in known_business_ids:
            report.errors.append(
                "Sale "
                f"{row.external_sale_id} references missing business "
                f"{row.external_business_id}",
            )

    for row in bundle.marketing:
        if row.external_business_id not in known_business_ids:
            report.errors.append(
                "Marketing activity "
                f"{row.external_activity_id} references missing business "
                f"{row.external_business_id}",
            )

    for row in bundle.finance:
        if row.external_business_id not in known_business_ids:
            report.errors.append(
                "Finance entry "
                f"{row.external_entry_id} references missing business "
                f"{row.external_business_id}",
            )

    report.valid = not report.errors
    if report.valid and not report.warnings:
        report.warnings.append("Bundle is valid for offline import.")
    return report


def _record_duplicates(
    report: SmartUpBundleValidationReport,
    values: list[str],
    label: str,
) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    for value in sorted(duplicates):
        report.errors.append(f"Duplicate {label} identifier found: {value}")


def iter_records(bundle: SmartUpExportBundle) -> Iterable[BaseModel]:
    """Iterate over every raw row in an export bundle."""

    yield from bundle.businesses
    yield from bundle.contacts
    yield from bundle.sales
    yield from bundle.marketing
    yield from bundle.finance
