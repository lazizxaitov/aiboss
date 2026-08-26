"""Hermes backend tools backed by existing AI Business OS services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.core.analytics.engine import BusinessAnalyticsEngine
from app.core.analytics.models import AnalyticsComparisonMode, AnalyticsPeriodPreset, AnalyticsQuery
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.dashboard import build_dashboard_overview
from app.core.organization_context import AnalyticsContextState, OrganizationContextService


@dataclass(slots=True)
class HermesBusinessTools:
    """Execute Hermes business-data tools through canonical / analytics / workspace services."""

    store: CoreDataStore

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
    ) -> AnalyticsQuery:
        context_service = OrganizationContextService(self.store)
        organization_ids = context_service.resolve_organization_ids(organization_id=organization_id) or []
        resolved_organization_id = organization_id
        if resolved_organization_id is None and len(organization_ids) == 1:
            resolved_organization_id = organization_ids[0]

        context = context_service.get_context()
        preset, date_from, date_to = self._resolve_period(period, context)
        return AnalyticsQuery(
            organization_id=resolved_organization_id,
            organization_ids=organization_ids,
            date_from=date_from,
            date_to=date_to,
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

        normalized = str(period).strip().lower()
        aliases = {
            "last_7_days": AnalyticsPeriodPreset.LAST_7_DAYS,
            "last_30_days": AnalyticsPeriodPreset.LAST_30_DAYS,
            "last_12_months": AnalyticsPeriodPreset.ALL,
            "all": AnalyticsPeriodPreset.ALL,
            "today": AnalyticsPeriodPreset.TODAY,
            "yesterday": AnalyticsPeriodPreset.YESTERDAY,
            "current_month": AnalyticsPeriodPreset.CURRENT_MONTH,
            "previous_month": AnalyticsPeriodPreset.PREVIOUS_MONTH,
            "custom": AnalyticsPeriodPreset.CUSTOM,
            "7d": AnalyticsPeriodPreset.LAST_7_DAYS,
            "30d": AnalyticsPeriodPreset.LAST_30_DAYS,
            "12m": AnalyticsPeriodPreset.ALL,
        }
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
