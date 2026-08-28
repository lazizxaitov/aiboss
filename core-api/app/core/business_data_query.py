"""Validated, read-only business data access for AI agents."""

from __future__ import annotations

from datetime import UTC, date, datetime
from logging import getLogger
from typing import Any
from uuid import UUID

from app.core.hermes_tools import HermesBusinessTools
from app.core.organization_context import OrganizationContextService

logger = getLogger(__name__)


class BusinessDataQueryService:
    """Execute a generic query through existing canonical analytics services."""

    DATASETS = {"sales", "inventory", "products", "customers", "returns", "visits", "finance"}
    DIMENSIONS = {
        "sales": {"manager", "seller", "employee", "organization", "filial", "product", "category", "client", "customer", "date", "day", "week", "month"},
        "inventory": {"organization", "filial", "warehouse", "product", "category"},
        "products": {"product", "category", "organization"},
        "customers": {"customer", "client", "organization"},
        "returns": {"product", "category", "customer", "client", "manager", "filial", "organization"},
        "visits": {"manager", "seller", "employee", "customer", "client", "organization"},
        "finance": {"type", "category", "organization"},
    }
    METRICS = {
        "revenue", "sales", "sales_amount", "orders", "order_count", "quantity",
        "sold_units", "average_check", "average_order", "returns", "return_amount",
        "return_count", "current_stock", "sales_velocity_30d", "discount", "profit", "margin",
    }
    FILTER_FIELDS = {
        "sales": {"manager_id", "customer_id", "product_id", "organization_id", "filial_id"},
        "inventory": {"product_id", "product_name", "warehouse_id", "category_id"},
        "products": {"product_id", "product_name", "manager_id", "category_id"},
        "customers": {"customer_id", "customer_name"},
        "returns": set(), "visits": set(), "finance": set(),
    }

    def __init__(self, tools: HermesBusinessTools) -> None:
        self.tools = tools

    def query(
        self,
        *,
        dataset: str,
        organization_id: UUID | None = None,
        period: str | None = None,
        dimensions: list[str] | None = None,
        metrics: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        sort: list[dict[str, str]] | None = None,
        limit: int = 50,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, Any]:
        dataset = dataset.strip().lower()
        logger.info(
            "BUSINESS_DATA_QUERY dataset=%s dimensions=%s metrics=%s limit=%s",
            dataset,
            dimensions,
            metrics,
            limit,
        )
        if dataset not in self.DATASETS:
            return self._unavailable(dataset, "Dataset is not available.")
        context = OrganizationContextService(self.tools.store).get_context()
        selected_organizations = set(context.organization_context.organization_ids)
        if organization_id is not None and selected_organizations and organization_id not in selected_organizations:
            return self._unavailable(dataset, "Organization is outside the current AI Business OS scope.", str(organization_id))
        requested_dimensions = [str(item).lower() for item in (dimensions or [])]
        if len(requested_dimensions) > 1:
            return self._unavailable(dataset, "Only one grouping dimension is supported by this analytics query.")
        unsupported_dimensions = sorted(set(requested_dimensions) - self.DIMENSIONS[dataset])
        if unsupported_dimensions:
            return self._unavailable(dataset, "Dimension is not available in canonical data.", unsupported_dimensions[0])
        requested_metrics = [str(item).lower() for item in (metrics or [])]
        unsupported_metrics = sorted(set(requested_metrics) - self.METRICS)
        if unsupported_metrics:
            return self._unavailable(dataset, "Metric is not available in canonical data.", unsupported_metrics[0])
        unsupported_filters = sorted(set(filters or {}) - self.FILTER_FIELDS[dataset])
        if unsupported_filters:
            return self._unavailable(dataset, "Filter field is not available in canonical data.", unsupported_filters[0])
        try:
            safe_limit = max(1, min(int(limit), 100))
        except (TypeError, ValueError):
            safe_limit = 50
        dimension = requested_dimensions[0] if requested_dimensions else None
        if dataset == "sales":
            result = self.tools.aggregate_sales(
                organization_id=organization_id, period=period, date_from=date_from, date_to=date_to,
                group_by=dimension or "date", metrics=requested_metrics or ["revenue", "orders"],
                filters=filters, limit=safe_limit,
            )
        elif dataset == "inventory":
            result = self.tools.query_inventory(organization_id=organization_id, period=period, filters=filters, limit=safe_limit, sort=self._sort_field(sort, "current_stock"))
        elif dataset == "products":
            result = self.tools.query_products(organization_id=organization_id, period=period, filters=filters, group_by=dimension, limit=safe_limit, sort=self._sort_field(sort, "revenue"))
        elif dataset == "customers":
            result = self.tools.query_customers(organization_id=organization_id, period=period, filters=filters, limit=safe_limit, sort=self._sort_field(sort, "revenue"))
        elif dataset == "returns":
            result = self.tools.query_returns(organization_id=organization_id, period=period, group_by=dimension or "product", limit=safe_limit)
        elif dataset == "visits":
            result = self.tools.query_visits(organization_id=organization_id, period=period, group_by=dimension, limit=safe_limit)
        else:
            result = self.tools.query_finance(organization_id=organization_id, period=period, group_by=dimension, limit=safe_limit)
        return self._add_provenance(result, dataset, organization_id, period)

    @staticmethod
    def _sort_field(sort: list[dict[str, str]] | None, default: str) -> str:
        if sort and isinstance(sort[0], dict) and sort[0].get("field"):
            field = str(sort[0]["field"])
            if field in BusinessDataQueryService.METRICS | {
                "orders_count", "days_since_last_order", "purchase_frequency",
            }:
                return field
        return default

    @staticmethod
    def _unavailable(dataset: str, reason: str, missing_dimension: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "available": False,
            "source": "AI Business OS Canonical V2 / analytics",
            "dataset": dataset,
            "reason": reason,
        }
        if missing_dimension:
            result["missing_dimension"] = missing_dimension
        return result

    @staticmethod
    def _add_provenance(
        result: dict[str, Any],
        dataset: str,
        organization_id: UUID | None,
        period: str | None,
    ) -> dict[str, Any]:
        if not isinstance(result, dict):
            return result
        enriched = dict(result)
        enriched.setdefault("source", "AI Business OS Canonical V2 / analytics")
        enriched.setdefault("dataset", dataset)
        enriched.setdefault("organization_id", str(organization_id) if organization_id else None)
        enriched.setdefault("period_requested", period)
        enriched.setdefault("generated_at", datetime.now(UTC).isoformat())
        enriched.setdefault("limitations", ["Only validated, aggregated read-only fields are returned."])
        return enriched
