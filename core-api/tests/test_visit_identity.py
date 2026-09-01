from datetime import UTC, datetime
from uuid import uuid4

from app.core.data_layer.canonical_v2 import CanonicalVisit
from app.core.data_layer.visit_identity import deduplicate_cross_organization_visits


def _visit(*, organization_id, visit_id="199455599", visited_at=None):
    return CanonicalVisit(
        organization_id=organization_id,
        source_endpoint="visits",
        source_external_id=visit_id,
        visit_id=visit_id,
        customer_external_id="customer-1",
        sales_rep_external_id="seller-1",
        visit_date=visited_at,
        visited_at=visited_at,
        working_zone_external_id="zone-1",
        duration_seconds=600,
    )


def test_exact_cross_organization_visit_copy_is_one_business_visit():
    organization_a = uuid4()
    organization_b = uuid4()
    timestamp = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)

    result = deduplicate_cross_organization_visits([
        _visit(organization_id=organization_a, visited_at=timestamp),
        _visit(organization_id=organization_b, visited_at=timestamp),
    ])

    assert len(result) == 1
    assert result[0].metadata["equivalent_organization_ids"] == sorted(
        [str(organization_a), str(organization_b)],
    )


def test_same_visit_id_with_different_business_identity_stays_separate():
    timestamp = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)

    result = deduplicate_cross_organization_visits([
        _visit(organization_id=uuid4(), visited_at=timestamp),
        _visit(organization_id=uuid4(), visited_at=timestamp.replace(hour=11)),
    ])

    assert len(result) == 2
