"""Tests for SmartUp migration completeness diagnostics."""

from datetime import UTC, datetime

from app.core.data_layer.service import InMemoryCoreDataLayer
from app.integrations.smartup.diagnostics import SmartUpRawDataService
from app.integrations.smartup.models import (
    MigrationBatch,
    SmartUpMigrationMode,
    SmartUpMigrationStatus,
    SmartUpOrganization,
)


def test_migration_completeness_reports_missing_intervals() -> None:
    store = InMemoryCoreDataLayer()
    organization = SmartUpOrganization(
        name="Acme",
        company_id="11300",
        filial_id="16114091",
        project_code="trade",
    )
    store.upsert_smartup_organization(organization)

    store.upsert_migration_batch(
        MigrationBatch(
            organization_id=organization.id,
            entity_type="customers",
            migration_mode=SmartUpMigrationMode.ONE_DAY_CHECK,
            date_from=datetime(2026, 7, 1, tzinfo=UTC),
            date_to=datetime(2026, 7, 2, tzinfo=UTC),
            status=SmartUpMigrationStatus.COMPLETED,
            received_count=10,
            inserted_count=10,
            started_at=datetime(2026, 7, 1, tzinfo=UTC),
            finished_at=datetime(2026, 7, 1, tzinfo=UTC),
        ),
    )
    store.upsert_migration_batch(
        MigrationBatch(
            organization_id=organization.id,
            entity_type="customers",
            migration_mode=SmartUpMigrationMode.ONE_DAY_CHECK,
            date_from=datetime(2026, 7, 4, tzinfo=UTC),
            date_to=datetime(2026, 7, 5, tzinfo=UTC),
            status=SmartUpMigrationStatus.COMPLETED,
            received_count=12,
            inserted_count=12,
            started_at=datetime(2026, 7, 4, tzinfo=UTC),
            finished_at=datetime(2026, 7, 4, tzinfo=UTC),
        ),
    )

    service = SmartUpRawDataService(store)
    report = service.migration_completeness(
        organization_id=organization.id,
        entity_type="customers",
        migration_mode=SmartUpMigrationMode.ONE_DAY_CHECK,
    )

    assert report.total_organizations == 1
    assert report.total_entities == 1
    item = report.items[0]
    assert item.status == "partial"
    assert item.failed_batches == 0
    assert item.batch_count == 2
    assert item.raw_records == 0
    assert item.core_records == 0
    assert item.missing_intervals
    assert item.missing_intervals[0].period_start == datetime(2026, 7, 2, tzinfo=UTC)
    assert item.missing_intervals[0].period_end == datetime(2026, 7, 4, tzinfo=UTC)
