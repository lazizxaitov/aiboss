"""Validated, read-only business data access for AI agents."""

from __future__ import annotations

from datetime import date
from logging import getLogger
from typing import Any
from uuid import UUID

from app.core.hermes_tools import HermesBusinessTools

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
        requested_dimensions = [str(item).lower() for item in (dimensions or [])]
        unsupported_dimensions = sorted(set(requested_dimensions) - self.DIMENSIONS[dataset])
        if unsupported_dimensions:
            return self._unavailable(dataset, "Dimension is not available in canonical data.", unsupported_dimensions[0])
        requested_metrics = [str(item).lower() for item in (metrics or [])]
        unsupported_metrics = sorted(set(requested_metrics) - self.METRICS)
        if unsupported_metrics:
            return self._unavailable(dataset, "Metric is not available in canonical data.", unsupported_metrics[0])
        safe_limit = max(1, min(int(limit), 100))
        dimension = requested_dimensions[0] if requested_dimensions else None
        if dataset == "sales":
            return self.tools.aggregate_sales(
                organization_id=organization_id, period=period, date_from=date_from, date_to=date_to,
                group_by=dimension or "date", metrics=requested_metrics or ["revenue", "orders"],
                filters=filters, limit=safe_limit,
            )
        if dataset == "inventory":
            return self.tools.query_inventory(organization_id=organization_id, period=period, filters=filters, limit=safe_limit, sort=self._sort_field(sort, "current_stock"))
        if dataset == "products":
            return self.tools.query_products(organization_id=organization_id, period=period, filters=filters, group_by=dimension, limit=safe_limit, sort=self._sort_field(sort, "revenue"))
        if dataset == "customers":
            return self.tools.query_customers(organization_id=organization_id, period=period, filters=filters, limit=safe_limit, sort=self._sort_field(sort, "revenue"))
        if dataset == "returns":
            return self.tools.query_returns(organization_id=organization_id, period=period, group_by=dimension or "product", limit=safe_limit)
        if dataset == "visits":
            return self.tools.query_visits(organization_id=organization_id, period=period, group_by=dimension, limit=safe_limit)
        return self.tools.query_finance(organization_id=organization_id, period=period, group_by=dimension, limit=safe_limit)

    @staticmethod
    def _sort_field(sort: list[dict[str, str]] | None, default: str) -> str:
        if sort and isinstance(sort[0], dict) and sort[0].get("field"):
            return str(sort[0]["field"])
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
