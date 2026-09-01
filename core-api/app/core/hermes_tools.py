"""Hermes backend tools backed by existing AI Business OS services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from app.core.analytics.engine import BusinessAnalyticsEngine
from app.core.analytics.models import AnalyticsComparisonMode, AnalyticsPeriodPreset, AnalyticsQuery
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.dashboard import build_dashboard_overview
from app.core.organization_context import (
    AnalyticsContextState,
    OrganizationContextService,
    resolve_business_period,
)


@dataclass(slots=True)
class HermesBusinessTools:
    """Execute Hermes business-data tools through canonical / analytics / workspace services."""

    store: CoreDataStore

    def build_business_context(
        self,
        question: str,
        *,
        organization_id: UUID | None = None,
        period: str | None = None,
    ) -> dict:
        """Build a small authoritative context for the current AI request."""

        text = question.lower()
        effective_period = period or self._infer_period(text)
        query = self._build_query(organization_id=organization_id, period=effective_period)
        engine = BusinessAnalyticsEngine(self.store)
        context: dict[str, object] = {
            "source": "AI Business OS canonical/analytics services",
            "authoritative": True,
            "organization_ids": [str(item) for item in query.organization_ids],
            "period": self._period_payload(query),
        }

        wants_inventory = any(word in text for word in ("склад", "остат", "инвентар", "stock", "inventory", "warehouse"))
        wants_customers = any(word in text for word in ("клиент", "покупател", "customer", "перестали покупать", "ушли"))
        wants_visits = any(word in text for word in ("визит", "посещен", "торгов", "visit"))
        wants_products = any(word in text for word in ("товар", "продукт", "категор", "product"))
        wants_sales = any(word in text for word in ("продаж", "выруч", "заказ", "продано", "kpi", "sales", "revenue", "order"))
        group_by = self._infer_group_by(text)
        context["data_plan"] = self._plan_data_tools(text, group_by)

        # Summary is the baseline for broad questions and sales requests.
        if wants_sales or not any((wants_inventory, wants_customers, wants_visits, wants_products)):
            context["sales_summary"] = self.get_sales_summary(
                organization_id=organization_id,
                period=effective_period,
            )
            context["business_summary"] = self.get_business_summary(
                organization_id=organization_id,
                period=effective_period,
            )
        if wants_products or wants_sales:
            context["products"] = self.get_top_products(
                organization_id=organization_id,
                period=effective_period,
                limit=20,
            )
        if wants_products:
            context["products_query"] = self.query_products(organization_id=organization_id, period=effective_period)
        if wants_inventory:
            context["inventory"] = engine.build_inventory(query).model_dump(mode="json")
            context["inventory_query"] = self.query_inventory(organization_id=organization_id, period=effective_period)
        if wants_customers:
            context["customers"] = engine.build_customers(query).model_dump(mode="json")
            context["customers_query"] = self.query_customers(organization_id=organization_id, period=effective_period)
        if wants_visits:
            context["visits"] = engine.build_visits(query).model_dump(mode="json")
            context["visits_query"] = self.query_visits(organization_id=organization_id, period=effective_period)
        if wants_sales:
            context["business_alerts"] = self.get_business_alerts(
                organization_id=organization_id,
                period=effective_period,
            )
        if group_by is not None:
            context["sales_aggregation"] = self.aggregate_sales(
                organization_id=organization_id,
                period=effective_period,
                group_by=group_by,
                metrics=["revenue", "orders", "sold_units", "average_order"],
            )
        if any(word in text for word in ("возврат", "return")):
            context["returns_query"] = self.query_returns(organization_id=organization_id, period=effective_period, group_by=group_by or "product")
        if any(word in text for word in ("финанс", "оплат", "деньг", "cash", "bank", "receivable")):
            context["finance_query"] = self.query_finance(organization_id=organization_id, period=effective_period)
        if any(word in text for word in ("аномал", "странност", "необыч", "почему упал", "почему сниз")):
            context["anomalies"] = self.detect_anomalies(organization_id=organization_id, period=effective_period)
        if any(word in text for word in ("сравни", "динамик", "прошл", "изменил", "упал", "вырос")):
            context["period_comparison"] = self.compare_periods(
                organization_id=organization_id, period=effective_period, group_by=group_by or "date",
            )
        return context

    def aggregate_sales(
        self,
        *,
        organization_id: UUID | None = None,
        period: str | None = None,
        group_by: str,
        metrics: list[str] | None = None,
        filters: dict | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 100,
    ) -> dict:
        """Return a compact grouped sales slice using the existing analytics engine."""

        dimension = self._normalize_dimension(group_by)
        supported = {"sales_rep", "organization", "filial", "product", "category", "customer", "date", "week", "month"}
        if dimension not in supported:
            return {
                "available": False,
                "reason": f"Dimension '{group_by}' is not supported by canonical sales data.",
                "missing_dimension": dimension,
            }

        query = self._build_query(
            organization_id=organization_id,
            period=period,
            date_from=date_from,
            date_to=date_to,
        )
        report = BusinessAnalyticsEngine(self.store).build_sales(query)
        rows = self._report_rows_for_dimension(report, dimension)
        if rows is None:
            return {
                "available": False,
                "reason": f"No canonical sales dimension is available for '{dimension}'.",
                "missing_dimension": dimension,
                "period": self._period_payload(query),
            }

        requested = self._normalize_metrics(metrics)
        items = []
        for row in rows:
            if not self._aggregation_row_matches(row, dimension, filters):
                continue
            normalized = self._serialize_aggregation_row(row, dimension, requested)
            if normalized is not None:
                items.append(normalized)
        items.sort(key=lambda item: self._numeric_sort_value(item.get("metrics", {}).get("revenue")), reverse=True)
        safe_limit = max(1, min(int(limit), 100))
        return {
            "available": True,
            "period": self._period_payload(query),
            "group_by": "manager" if dimension == "sales_rep" else dimension,
            "metric": "revenue" if "revenue" in requested else requested[0],
            "metrics": requested,
            "rows": items[:safe_limit],
            "data_quality": report.data_quality.model_dump(mode="json"),
        }

    def query_inventory(
        self, *, organization_id: UUID | None = None, period: str | None = None,
        filters: dict | None = None, limit: int = 50, sort: str = "current_stock",
    ) -> dict:
        query = self._build_query(organization_id=organization_id, period=period)
        report = BusinessAnalyticsEngine(self.store).build_inventory(query)
        items = self._filter_items(report.items, filters)
        items = self._sort_items(items, sort, ("current_stock", "sales_velocity_30d", "revenue"))
        return self._domain_result("inventory", query, items[:self._safe_limit(limit)], report.data_quality, {
            "low_stock": [item.model_dump(mode="json") for item in report.low_stock[:self._safe_limit(limit)]],
            "zero_stock": [item.model_dump(mode="json") for item in items if self._metric_value(item.current_stock) == 0][:self._safe_limit(limit)],
            "overstock": [item.model_dump(mode="json") for item in report.overstock[:self._safe_limit(limit)]],
            "stockout_risk": [item.model_dump(mode="json") for item in report.stockout_risk[:self._safe_limit(limit)]],
            "transfer_opportunities": [item.model_dump(mode="json") for item in report.transfer_opportunities[:self._safe_limit(limit)]],
        })

    def query_products(
        self, *, organization_id: UUID | None = None, period: str | None = None,
        filters: dict | None = None, group_by: str | None = None,
        limit: int = 50, sort: str = "revenue",
    ) -> dict:
        query = self._build_query(organization_id=organization_id, period=period)
        report = BusinessAnalyticsEngine(self.store).build_products(query)
        items = self._sort_items(self._filter_products_by_manager(report.items, filters), sort, (
            "revenue", "sold_units", "sales_velocity_30d", "current_stock",
        ))
        return self._domain_result("products", query, items[:self._safe_limit(limit)], report.data_quality, {
            "top": [item.model_dump(mode="json") for item in report.top[:self._safe_limit(limit)]],
            "growing": [item.model_dump(mode="json") for item in report.growing[:self._safe_limit(limit)]],
            "declining": [item.model_dump(mode="json") for item in report.declining[:self._safe_limit(limit)]],
            "fast_movers": [item.model_dump(mode="json") for item in report.growing[:self._safe_limit(limit)]],
            "slow_movers": [item.model_dump(mode="json") for item in report.slow_movers[:self._safe_limit(limit)]],
            "no_sales": [item.model_dump(mode="json") for item in items if self._metric_value(item.sold_units) == 0][:self._safe_limit(limit)],
        })

    def query_customers(
        self, *, organization_id: UUID | None = None, period: str | None = None,
        filters: dict | None = None, limit: int = 50, sort: str = "revenue",
    ) -> dict:
        query = self._build_query(organization_id=organization_id, period=period)
        report = BusinessAnalyticsEngine(self.store).build_customers(query)
        items = self._sort_items(self._filter_items(report.items, filters), sort, (
            "revenue", "orders_count", "days_since_last_order", "purchase_frequency",
        ))
        safe_limit = self._safe_limit(limit)
        return self._domain_result("customers", query, items[:safe_limit], report.data_quality, {
            "top": [item.model_dump(mode="json") for item in report.top[:safe_limit]],
            "at_risk": [item.model_dump(mode="json") for item in report.at_risk[:safe_limit]],
            "lost": [item.model_dump(mode="json") for item in report.lost[:safe_limit]],
            "inactive": [item.model_dump(mode="json") for item in report.lost[:safe_limit]],
        })

    def query_returns(
        self, *, organization_id: UUID | None = None, period: str | None = None,
        group_by: str = "product", limit: int = 50,
    ) -> dict:
        result = self.aggregate_sales(
            organization_id=organization_id, period=period, group_by=group_by,
            metrics=["returns", "revenue", "orders"], limit=limit,
        )
        result["domain"] = "returns"
        return result

    def query_visits(
        self, *, organization_id: UUID | None = None, period: str | None = None,
        group_by: str | None = None, limit: int = 50,
    ) -> dict:
        query = self._build_query(organization_id=organization_id, period=period)
        report = BusinessAnalyticsEngine(self.store).build_visits(query)
        safe_limit = self._safe_limit(limit)
        grouped = {
            "organization": report.by_organization,
            "manager": report.by_sales_rep,
            "seller": report.by_sales_rep,
            "customer": report.by_customer,
            "client": report.by_customer,
        }
        if group_by and group_by.lower() not in grouped:
            return self._unavailable("visits", query, f"Visit dimension '{group_by}' is unavailable.", group_by)
        rows = grouped.get((group_by or "").lower()) if group_by else None
        payload = [row.model_dump(mode="json") for row in (rows or report.items)[:safe_limit]]
        return self._domain_result("visits", query, payload, report.data_quality, {"group_by": group_by})

    def query_finance(
        self, *, organization_id: UUID | None = None, period: str | None = None,
        group_by: str | None = None, limit: int = 50,
    ) -> dict:
        query = self._build_query(organization_id=organization_id, period=period)
        report = BusinessAnalyticsEngine(self.store).build_finance(query)
        payload = report.model_dump(mode="json")
        if group_by and group_by not in {"type", "category"}:
            return self._unavailable("finance", query, f"Finance dimension '{group_by}' is unavailable.", group_by)
        if group_by:
            key = "by_type" if group_by == "type" else "by_category"
            payload = {key: payload.get(key, [])[:self._safe_limit(limit)]}
        return self._domain_result("finance", query, payload, report.data_quality)

    def search_entities(self, *, entity_type: str, search: str, organization_id: UUID | None = None, limit: int = 20) -> dict:
        query = self._build_query(organization_id=organization_id, period=None)
        term = search.strip().casefold()
        selected = set(query.organization_ids)
        sources = {
            "product": (self.store.list_canonical_products(), lambda item: {item.name, item.code, item.product_id}),
            "category": (self.store.list_canonical_product_categories(), lambda item: {item.name, item.code, item.group_id}),
            "customer": (self.store.list_canonical_customers(), lambda item: {item.name, item.code, item.person_id}),
            "manager": (self.store.list_canonical_sales_reps(), lambda item: {item.sales_manager_name, item.sales_manager_code, item.sales_manager_id}),
            "warehouse": (self.store.list_canonical_warehouses(), lambda item: {item.warehouse_name, item.warehouse_code, item.warehouse_id}),
            "organization": (self.store.list_canonical_organizations(), lambda item: {item.name, item.project_code, item.filial_code, item.filial_id}),
            "filial": (self.store.list_canonical_organizations(), lambda item: {item.filial_code, item.filial_id, item.name}),
        }
        normalized_type = "manager" if entity_type in {"seller", "employee"} else entity_type
        source = sources.get(normalized_type)
        if source is None:
            return self._unavailable("entity_search", query, f"Entity type '{entity_type}' is unavailable.", entity_type)
        matches = []
        for item in source[0]:
            if getattr(item, "organization_id", None) and selected and item.organization_id not in selected:
                continue
            values = {str(value).casefold() for value in source[1](item) if value is not None}
            if term and not any(term in value for value in values):
                continue
            matches.append(item.model_dump(mode="json"))
        return self._domain_result("entity_search", query, matches[:self._safe_limit(limit)], None, {"entity_type": normalized_type, "search": search})

    def compare_periods(
        self, *, organization_id: UUID | None = None, period: str | None = None,
        comparison_period: str | None = None, group_by: str | None = None, limit: int = 20,
    ) -> dict:
        current = self.aggregate_sales(organization_id=organization_id, period=period, group_by=group_by or "date", limit=limit)
        previous = self.aggregate_sales(organization_id=organization_id, period=comparison_period or self._comparison_period(period), group_by=group_by or "date", limit=limit)
        return {"available": current.get("available") and previous.get("available"), "current": current, "previous": previous,
                "source": "AI Business OS canonical/analytics services", "limitations": ["Comparison rows are calculated independently for the requested periods."]}

    def detect_anomalies(self, *, organization_id: UUID | None = None, period: str | None = None, limit: int = 30) -> dict:
        query = self._build_query(organization_id=organization_id, period=period)
        engine = BusinessAnalyticsEngine(self.store)
        products = engine.build_products(query)
        customers = engine.build_customers(query)
        reps = engine.build_sales_reps(query)
        findings = []
        no_sales = [item for item in products.items if self._metric_value(item.sold_units) == 0]
        for item in products.growing + products.declining + products.stockout_risk + products.overstock + no_sales:
            signal_type = "no_sales" if item in no_sales else item.classification or item.stockout_risk or "product_signal"
            findings.append({"type": signal_type, "entity": item.product_name,
                             "metric": "revenue_change_pct" if item in products.growing + products.declining else "current_stock",
                             "evidence": item.model_dump(mode="json")})
        for item in customers.lost + customers.at_risk:
            findings.append({"type": "customer_activity_drop", "entity": item.customer_name, "metric": "days_since_last_order",
                             "evidence": item.model_dump(mode="json")})
        for item in reps.items:
            if item.revenue.percent_delta is not None and abs(item.revenue.percent_delta) >= 20:
                findings.append({"type": "sales_rep_change", "entity": item.sales_rep_name, "metric": "revenue",
                                 "evidence": item.model_dump(mode="json")})
        return self._domain_result("anomalies", query, findings[:self._safe_limit(limit)], None, {
            "rules": ["growing/declining products", "products without sales", "stockout/overstock risk", "lost/at-risk customers", "sales representative revenue change >= 20%"],
        })

    @staticmethod
    def _safe_limit(value: int) -> int:
        try:
            return max(1, min(int(value), 100))
        except (TypeError, ValueError):
            return 50

    @staticmethod
    def _metric_value(metric) -> float:
        value = getattr(metric, "value", metric)
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def _filter_items(self, items: list, filters: dict | None) -> list:
        if not isinstance(filters, dict):
            return list(items)
        result = []
        for item in items:
            payload = item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            matches = True
            for key, expected in filters.items():
                actual = payload.get(key)
                if isinstance(expected, str) and isinstance(actual, str):
                    matches = expected.casefold() in actual.casefold()
                elif isinstance(expected, list):
                    matches = actual in expected
                else:
                    matches = actual == expected
                if not matches:
                    break
            if matches:
                result.append(item)
        return result

    def _filter_products_by_manager(self, items: list, filters: dict | None) -> list:
        if not isinstance(filters, dict) or not filters.get("manager_id"):
            return self._filter_items(items, filters)
        manager_id = str(filters["manager_id"])
        product_ids = self._product_ids_for_manager(manager_id)
        remaining = {key: value for key, value in filters.items() if key != "manager_id"}
        filtered = [item for item in items if item.product_external_id in product_ids]
        return self._filter_items(filtered, remaining)

    def _product_ids_for_manager(self, manager_id: str) -> set[str]:
        reps = [item for item in self.store.list_canonical_sales_reps()
                if manager_id in {str(item.id), item.sales_manager_id, item.sales_manager_code}]
        rep_ids = {item.sales_manager_id for item in reps} | {item.sales_manager_code for item in reps}
        sale_ids = {sale.id for sale in self.store.list_canonical_sales()
                     if sale.sales_rep_external_id in rep_ids or str(sale.sales_rep_id) == manager_id}
        return {item.product_external_id for item in self.store.list_canonical_sale_items()
                if item.sale_id in sale_ids and item.product_external_id}

    def _aggregation_row_matches(self, row, dimension: str, filters: dict | None) -> bool:
        if not isinstance(filters, dict):
            return True
        expected = filters.get({"sales_rep": "manager_id", "customer": "customer_id", "product": "product_id"}.get(dimension, "id"))
        if dimension == "product" and filters.get("manager_id"):
            return row.key in self._product_ids_for_manager(str(filters["manager_id"]))
        if expected is None:
            return self._filter_items([row], filters) != []
        expected_values = {str(expected)} if not isinstance(expected, list) else {str(value) for value in expected}
        if dimension == "sales_rep":
            matches = [item for item in self.store.list_canonical_sales_reps()
                       if str(item.id) in expected_values or item.sales_manager_id in expected_values or item.sales_manager_code in expected_values]
            return any(row.key in {item.sales_manager_id, item.sales_manager_code} for item in matches)
        return row.key in expected_values

    def _sort_items(self, items: list, sort: str, allowed: tuple[str, ...]) -> list:
        key = sort if sort in allowed else allowed[0]
        return sorted(items, key=lambda item: self._metric_value(getattr(item, key, None)), reverse=True)

    def _domain_result(self, domain: str, query: AnalyticsQuery, data, data_quality, extra: dict | None = None) -> dict:
        result = {
            "available": True,
            "domain": domain,
            "source": "AI Business OS canonical/analytics services",
            "organization": {
                "organization_ids": [str(item) for item in query.organization_ids],
                "resolved_organization_id": str(query.organization_id) if query.organization_id else None,
            },
            "period": self._period_payload(query),
            "generated_at": datetime.now(UTC).isoformat(),
            "data": [item.model_dump(mode="json") for item in data] if isinstance(data, list) else data,
            "limitations": [],
        }
        if data_quality is not None:
            result["data_quality"] = data_quality.model_dump(mode="json")
        if extra:
            result.update(extra)
        return result

    def _unavailable(self, domain: str, query: AnalyticsQuery, reason: str, missing_dimension: str | None = None) -> dict:
        result = {
            "available": False,
            "domain": domain,
            "source": "AI Business OS canonical/analytics services",
            "organization": {"organization_ids": [str(item) for item in query.organization_ids]},
            "period": self._period_payload(query),
            "generated_at": datetime.now(UTC).isoformat(),
            "reason": reason,
            "limitations": [reason],
        }
        if missing_dimension:
            result["missing_dimension"] = missing_dimension
        return result

    @staticmethod
    def _comparison_period(period: str | None) -> str:
        normalized = str(period or "").strip().lower().replace(" ", "_")
        return {
            "current_week": "last_week", "this_week": "last_week", "7d": "30d",
            "current_month": "previous_month", "this_month": "previous_month",
            "today": "yesterday",
        }.get(normalized, "last_7_days")

    def get_business_summary(
        self,
        *,
        organization_id: UUID | None = None,
        period: str | None = None,
    ) -> dict:
        query = self._build_query(organization_id=organization_id, period=period)
        summary = BusinessAnalyticsEngine(self.store).build_summary(query)
        business = summary.business
        return {
            "organization_ids": [str(item) for item in query.organization_ids],
            "resolved_organization_id": str(query.organization_id) if query.organization_id else None,
            "period": self._period_payload(query),
            "metrics": {
                "revenue": business.revenue.model_dump(mode="json"),
                "orders": business.orders.model_dump(mode="json"),
                "average_order": business.average_order.model_dump(mode="json"),
                "sold_units": business.sold_units.model_dump(mode="json"),
                "returns": business.returns.model_dump(mode="json"),
                "customers": business.customers.model_dump(mode="json"),
                "products": business.unique_products.model_dump(mode="json"),
                "visits": business.visits.model_dump(mode="json"),
            },
            "data_quality": summary.data_quality.model_dump(mode="json"),
        }

    def get_sales_summary(
        self,
        *,
        organization_id: UUID | None = None,
        period: str | None = None,
    ) -> dict:
        query = self._build_query(organization_id=organization_id, period=period)
        report = BusinessAnalyticsEngine(self.store).build_sales(query)
        return report.model_dump(mode="json")

    def get_top_products(
        self,
        *,
        organization_id: UUID | None = None,
        period: str | None = None,
        limit: int = 10,
    ) -> dict:
        query = self._build_query(organization_id=organization_id, period=period)
        report = BusinessAnalyticsEngine(self.store).build_products(query)
        safe_limit = max(1, min(int(limit), 50))
        return {
            "organization_ids": [str(item) for item in query.organization_ids],
            "resolved_organization_id": str(query.organization_id) if query.organization_id else None,
            "period": self._period_payload(query),
            "limit": safe_limit,
            "items": [item.model_dump(mode="json") for item in report.top[:safe_limit]],
            "data_quality": report.data_quality.model_dump(mode="json"),
        }

    def get_organizations(self) -> dict:
        items = [
            {
                "organization_id": str(row.organization_id),
                "name": row.name,
                "company_id": row.company_id,
                "filial_id": row.filial_id,
                "filial_code": row.filial_code,
                "project_code": row.project_code,
                "is_active": row.is_active,
                "sort_order": row.sort_order,
                "data_quality_status": row.data_quality_status.value,
                "last_synced_at": row.last_synced_at.isoformat() if row.last_synced_at else None,
            }
            for row in self.store.list_canonical_organizations()
        ]
        return {"count": len(items), "items": items}

    def get_business_alerts(
        self,
        *,
        organization_id: UUID | None = None,
        period: str | None = None,
    ) -> dict:
        query = self._build_query(organization_id=organization_id, period=period)
        overview = build_dashboard_overview(
            self.store,
            organization_ids=query.organization_ids or None,
            period=self._dashboard_period(query),
        )
        signals = [signal.model_dump(mode="json") for signal in overview.signals]
        action_center = [signal.model_dump(mode="json") for signal in overview.action_center]
        items = self._dedupe_alerts(signals + action_center)
        return {
            "organization_ids": [str(item) for item in query.organization_ids],
            "resolved_organization_id": str(query.organization_id) if query.organization_id else None,
            "period": self._period_payload(query),
            "signals": signals,
            "action_center": action_center,
            "items": items,
            "ai_insights": overview.ai_insights,
        }

    def _build_query(
        self,
        *,
        organization_id: UUID | None,
        period: str | None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> AnalyticsQuery:
        context_service = OrganizationContextService(self.store)
        organization_ids = context_service.resolve_organization_ids(organization_id=organization_id) or []
        resolved_organization_id = organization_id
        if resolved_organization_id is None and len(organization_ids) == 1:
            resolved_organization_id = organization_ids[0]

        context = context_service.get_context()
        preset, resolved_from, resolved_to = self._resolve_period(period, context)
        if date_from is not None or date_to is not None:
            preset = AnalyticsPeriodPreset.CUSTOM
            resolved_from = date_from
            resolved_to = date_to
        return AnalyticsQuery(
            organization_id=resolved_organization_id,
            organization_ids=organization_ids,
            date_from=resolved_from,
            date_to=resolved_to,
            period=preset,
            comparison_mode=AnalyticsComparisonMode.PREVIOUS_PERIOD,
        )

    def _resolve_period(
        self,
        period: str | None,
        context: AnalyticsContextState,
    ) -> tuple[AnalyticsPeriodPreset, date | None, date | None]:
        if period is None or not str(period).strip():
            return (
                context.period_context.preset,
                context.period_context.date_from,
                context.period_context.date_to,
            )

        normalized = str(period).strip().lower().replace(" ", "_")
        aliases = {
            "last_7_days": AnalyticsPeriodPreset.LAST_7_DAYS,
            "last_30_days": AnalyticsPeriodPreset.LAST_30_DAYS,
            "last_12_months": AnalyticsPeriodPreset.ALL,
            "all": AnalyticsPeriodPreset.ALL,
            "today": AnalyticsPeriodPreset.TODAY,
            "yesterday": AnalyticsPeriodPreset.YESTERDAY,
            "current_month": AnalyticsPeriodPreset.CURRENT_MONTH,
            "this_month": AnalyticsPeriodPreset.CURRENT_MONTH,
            "previous_month": AnalyticsPeriodPreset.PREVIOUS_MONTH,
            "last_month": AnalyticsPeriodPreset.PREVIOUS_MONTH,
            "custom": AnalyticsPeriodPreset.CUSTOM,
            "7d": AnalyticsPeriodPreset.LAST_7_DAYS,
            "30d": AnalyticsPeriodPreset.LAST_30_DAYS,
            "12m": AnalyticsPeriodPreset.ALL,
        }
        if normalized in {"this_week", "current_week", "текущая_неделя", "эта_неделя"}:
            return AnalyticsPeriodPreset.LAST_7_DAYS, None, None
        if normalized in {"last_week", "previous_week", "прошлая_неделя"}:
            start, end = self._week_dates(-1)
            return AnalyticsPeriodPreset.CUSTOM, start, end
        preset = aliases.get(normalized)
        if preset is None:
            try:
                preset = AnalyticsPeriodPreset(normalized)
            except ValueError:
                preset = context.period_context.preset

        if preset != AnalyticsPeriodPreset.CUSTOM:
            return preset, None, None

        return preset, context.period_context.date_from, context.period_context.date_to

    def _dashboard_period(self, query: AnalyticsQuery):
        from app.core.data_layer.dashboard import DashboardPeriod

        mapping = {
            AnalyticsPeriodPreset.ALL: DashboardPeriod.ALL,
            AnalyticsPeriodPreset.LAST_30_DAYS: DashboardPeriod.LAST_30_DAYS,
            AnalyticsPeriodPreset.CURRENT_MONTH: DashboardPeriod.LAST_30_DAYS,
            AnalyticsPeriodPreset.PREVIOUS_MONTH: DashboardPeriod.LAST_30_DAYS,
            AnalyticsPeriodPreset.LAST_7_DAYS: DashboardPeriod.LAST_30_DAYS,
            AnalyticsPeriodPreset.TODAY: DashboardPeriod.LAST_30_DAYS,
            AnalyticsPeriodPreset.YESTERDAY: DashboardPeriod.LAST_30_DAYS,
            AnalyticsPeriodPreset.CUSTOM: DashboardPeriod.LAST_30_DAYS,
        }
        return mapping.get(query.period, DashboardPeriod.LAST_30_DAYS)

    def _period_payload(self, query: AnalyticsQuery) -> dict:
        return {
            "preset": query.period.value,
            "date_from": query.date_from.isoformat() if query.date_from else None,
            "date_to": query.date_to.isoformat() if query.date_to else None,
        }

    def _dedupe_alerts(self, items: list[dict]) -> list[dict]:
        deduped: list[dict] = []
        seen: set[tuple[str | None, str | None]] = set()
        for item in items:
            key = (item.get("title"), item.get("note"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped[:12]

    @staticmethod
    def _week_dates(offset: int, now: datetime | None = None) -> tuple[date, date]:
        current = resolve_business_period("this_week", now)
        start = current.start + timedelta(days=offset * 7)
        return start.date(), start.date() + timedelta(days=6)

    @staticmethod
    def _infer_group_by(text: str) -> str | None:
        patterns = (
            (("продав", "менеджер", "сотрудник", "sales rep", "manager", "employee"), "sales_rep"),
            (("филиал", "filial", "branch"), "filial"),
            (("категор", "category"), "category"),
            (("товар", "продукт", "product"), "product"),
            (("клиент", "покупател", "customer", "client"), "customer"),
            (("по дням", "ежеднев", "day", "date"), "date"),
            (("по недел", "weekly", "week"), "week"),
            (("по месяц", "ежемесяч", "monthly", "month"), "month"),
            (("организац", "organization", "org"), "organization"),
        )
        for words, dimension in patterns:
            if any(word in text for word in words):
                return dimension
        return None

    @staticmethod
    def _plan_data_tools(text: str, group_by: str | None) -> list[str]:
        plan: list[str] = []
        if any(word in text for word in ("продаж", "выруч", "заказ", "продано", "sales", "revenue")):
            plan.append("aggregate_sales")
        if any(word in text for word in ("склад", "остат", "stock", "inventory", "warehouse")):
            plan.append("query_inventory")
        if any(word in text for word in ("товар", "продукт", "product", "категор")):
            plan.append("query_products")
        if any(word in text for word in ("клиент", "покупател", "customer", "client")):
            plan.append("query_customers")
        if any(word in text for word in ("возврат", "return")):
            plan.append("query_returns")
        if any(word in text for word in ("визит", "посещен", "visit")):
            plan.append("query_visits")
        if any(word in text for word in ("финанс", "оплат", "cash", "bank")):
            plan.append("query_finance")
        if any(word in text for word in ("сравни", "динамик", "изменил", "упал", "вырос")):
            plan.append("compare_periods")
        if any(word in text for word in ("аномал", "странност", "необыч")):
            plan.append("detect_anomalies")
        if group_by and "aggregate_sales" not in plan:
            plan.append("aggregate_sales")
        return list(dict.fromkeys(plan))

    @staticmethod
    def _infer_period(text: str) -> str | None:
        if any(value in text for value in ("на этой неделе", "за эту неделю", "this week", "current week")):
            return "current_week"
        if any(value in text for value in ("на прошлой неделе", "за прошлую неделю", "last week")):
            return "last_week"
        if any(value in text for value in ("сегодня", "today")):
            return "today"
        if any(value in text for value in ("вчера", "yesterday")):
            return "yesterday"
        if any(value in text for value in ("в этом месяце", "за этот месяц", "this month")):
            return "current_month"
        if any(value in text for value in ("в прошлом месяце", "за прошлый месяц", "last month")):
            return "previous_month"
        return None

    @staticmethod
    def _normalize_dimension(value: str) -> str:
        aliases = {
            "manager": "sales_rep", "seller": "sales_rep", "employee": "sales_rep",
            "sales_rep": "sales_rep", "sales-rep": "sales_rep", "customer": "customer",
            "client": "customer", "org": "organization", "day": "date",
            "week": "week", "month": "month",
        }
        return aliases.get(str(value).strip().lower(), str(value).strip().lower())

    @staticmethod
    def _normalize_metrics(metrics: list[str] | None) -> list[str]:
        aliases = {
            "sales": "revenue", "sales_amount": "revenue", "order_count": "orders",
            "quantity": "sold_units", "average_check": "average_order",
        }
        allowed = {"revenue", "orders", "sold_units", "average_order", "returns"}
        requested = [aliases.get(str(item).lower(), str(item).lower()) for item in (metrics or ["revenue", "orders"])]
        return list(dict.fromkeys(item for item in requested if item in allowed)) or ["revenue"]

    def _report_rows_for_dimension(self, report, dimension: str):
        if dimension == "sales_rep":
            return report.by_sales_rep
        if dimension == "organization":
            return report.by_organization
        if dimension == "product":
            return report.by_product
        if dimension == "category":
            return report.by_category
        if dimension == "customer":
            return report.by_customer
        if dimension == "date":
            return report.by_date
        if dimension in {"week", "month"}:
            return self._calendar_rows(report.by_date, dimension)
        if dimension == "filial":
            return self._filial_rows(report.by_organization)
        return None

    def _filial_rows(self, organization_rows):
        organizations = {str(item.organization_id): item for item in self.store.list_canonical_organizations()}
        grouped: dict[str, list] = {}
        for row in organization_rows:
            organization = organizations.get(row.key)
            if organization is None or not organization.filial_id:
                continue
            grouped.setdefault(organization.filial_id, []).append(row)
        if not grouped and organization_rows:
            return None
        result = []
        for filial_id, rows in grouped.items():
            first = next((item for item in organizations.values() if item.filial_id == filial_id), None)
            result.append(self._merge_dimension_rows("filial", filial_id, first.filial_code or filial_id if first else filial_id, rows))
        return result

    def _calendar_rows(self, date_rows, dimension: str):
        grouped: dict[str, list] = {}
        for row in date_rows:
            try:
                current = date.fromisoformat(row.key)
            except ValueError:
                continue
            if dimension == "week":
                year, week, _ = current.isocalendar()
                key = f"{year}-W{week:02d}"
            else:
                key = current.strftime("%Y-%m")
            grouped.setdefault(key, []).append(row)
        return [self._merge_dimension_rows(dimension, key, key, rows) for key, rows in sorted(grouped.items())]

    @staticmethod
    def _merge_dimension_rows(dimension: str, key: str, label: str, rows: list):
        merged = rows[0].model_copy(deep=True)
        merged.dimension, merged.key, merged.label = dimension, key, label
        for metric_name, metric in merged.metrics.items():
            values = [row.metrics[metric_name].value for row in rows if metric_name in row.metrics and row.metrics[metric_name].value is not None]
            metric.value = sum(values, metric.value.__class__(0) if metric.value is not None else 0) if values else None
        return merged

    def _serialize_aggregation_row(self, row, dimension: str, requested: list[str]) -> dict | None:
        label = row.label
        if dimension == "sales_rep":
            rep = next((item for item in self.store.list_canonical_sales_reps() if item.sales_manager_id == row.key or item.sales_manager_code == row.key), None)
            label = rep.sales_manager_name if rep and rep.sales_manager_name else label
        elif dimension == "customer":
            customer = next((item for item in self.store.list_canonical_customers() if item.person_id == row.key or item.code == row.key), None)
            label = customer.name if customer else label
        elif dimension == "product":
            product = next((item for item in self.store.list_canonical_products() if item.product_id == row.key or item.code == row.key), None)
            label = product.name if product else label
        elif dimension == "category":
            category = next((item for item in self.store.list_canonical_product_categories() if item.group_id == row.key or item.code == row.key), None)
            label = category.name if category else label
        values = {}
        for metric in requested:
            source = row.metrics.get(metric)
            value = source.value if source else None
            if metric == "average_order":
                revenue = row.metrics.get("revenue")
                orders = row.metrics.get("orders")
                value = revenue.value / orders.value if revenue and orders and revenue.value is not None and orders.value else None
            if value is not None:
                values[metric] = value
        result = {"entity_id": row.key, "entity_name": label, "metrics": values, **values}
        if dimension == "sales_rep":
            result.update({"manager_id": row.key, "manager_name": label})
        return result

    @staticmethod
    def _numeric_sort_value(value: object) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0
