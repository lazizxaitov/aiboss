"""Identity-aware handling for canonical visits across organization scopes."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from app.core.data_layer.canonical_v2 import CanonicalVisit


def _identity_key(visit: CanonicalVisit) -> tuple[object, ...] | None:
    if not visit.visit_id:
        return None
    return (
        visit.visit_id,
        visit.customer_external_id,
        visit.sales_rep_external_id,
        visit.visit_date,
        visit.visited_at,
        visit.visit_start_time,
        visit.visit_end_time,
        visit.working_zone_external_id,
        visit.duration_seconds,
    )


def deduplicate_cross_organization_visits(
    visits: Iterable[CanonicalVisit],
) -> list[CanonicalVisit]:
    """Collapse exact cross-organization copies of one visit identity."""

    groups: dict[tuple[object, ...], list[CanonicalVisit]] = defaultdict(list)
    unkeyed: list[CanonicalVisit] = []
    for visit in visits:
        key = _identity_key(visit)
        if key is None:
            unkeyed.append(visit)
        else:
            groups[key].append(visit)

    result = list(unkeyed)
    for group in groups.values():
        ordered = sorted(group, key=lambda item: (str(item.organization_id), str(item.id)))
        selected = ordered[0]
        if len({item.organization_id for item in ordered}) > 1:
            metadata = dict(selected.metadata)
            metadata["equivalent_organization_ids"] = [
                str(item.organization_id) for item in ordered
            ]
            selected = selected.model_copy(update={"metadata": metadata})
        result.append(selected)
    return sorted(result, key=lambda item: (str(item.organization_id), str(item.id)))
