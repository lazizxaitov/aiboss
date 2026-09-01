"""Identity-aware handling for canonical visits across organization scopes."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from app.core.data_layer.canonical_v2 import (
    CanonicalCustomerReturn,
    CanonicalCustomerReturnItem,
    CanonicalVisit,
)


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


def deduplicate_cross_organization_returns(
    returns: Iterable[CanonicalCustomerReturn],
) -> list[CanonicalCustomerReturn]:
    """Collapse exact cross-organization copies of one return document."""

    groups: dict[tuple[object, ...], list[CanonicalCustomerReturn]] = defaultdict(list)
    unkeyed: list[CanonicalCustomerReturn] = []
    for item in returns:
        key = (
            item.return_id,
            item.external_document_id,
            item.order_deal_id,
            item.customer_external_id,
            item.sales_rep_external_id,
            item.return_at,
            item.booked_at,
            item.total_amount,
            item.returned_quantity,
            item.item_count,
            item.currency_code,
        ) if item.return_id else None
        if key is None:
            unkeyed.append(item)
        else:
            groups[key].append(item)

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


def deduplicate_cross_organization_return_items(
    items: Iterable[CanonicalCustomerReturnItem],
) -> list[CanonicalCustomerReturnItem]:
    """Collapse exact copies of a return line while preserving line grain."""

    groups: dict[tuple[object, ...], list[CanonicalCustomerReturnItem]] = defaultdict(list)
    unkeyed: list[CanonicalCustomerReturnItem] = []
    for item in items:
        key = (
            item.return_external_id,
            item.line_number,
            item.product_external_id,
            item.product_code,
            item.product_name,
            item.warehouse_external_id,
            item.warehouse_code,
            item.price_type_code,
            item.returned_quantity,
            item.unit_price,
            item.amount,
            item.vat_percent,
            item.vat_amount,
            item.margin_amount,
            item.currency_code,
        ) if item.return_external_id else None
        if key is None:
            unkeyed.append(item)
        else:
            groups[key].append(item)

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
