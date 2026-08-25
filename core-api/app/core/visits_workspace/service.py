"""Canonical Visits / Field Sales workspace service."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from math import ceil
from typing import TypeVar
from uuid import UUID

from app.core.analytics.engine import BusinessAnalyticsEngine
from app.core.analytics.models import (
    AnalyticsDataStatus,
    AnalyticsMetricValue,
    AnalyticsQuery,
)
from app.core.data_layer.canonical_v2 import (
    CanonicalCustomer,
    CanonicalDataQualityStatus,
    CanonicalMediaAsset,
    CanonicalOrganization,
    CanonicalSalesRep,
    CanonicalVisit,
    CanonicalVisitComment,
    CanonicalVisitEquipment,
    CanonicalVisitQuizAnswer,
    CanonicalVisitStock,
    CanonicalWorkingZone,
)
from app.core.data_layer.contracts import CoreDataStore
from app.core.visits_workspace.models import (
    VisitsWorkspaceCapabilityItem,
    VisitsWorkspaceCapabilityStatus,
    VisitsWorkspaceDetail,
    VisitsWorkspaceFilterOption,
    VisitsWorkspaceFiltersMetadata,
    VisitsWorkspaceNestedCommentRow,
    VisitsWorkspaceNestedEquipmentRow,
    VisitsWorkspaceNestedMediaRow,
    VisitsWorkspaceNestedQuizRow,
    VisitsWorkspaceNestedStockRow,
    VisitsWorkspacePagination,
    VisitsWorkspaceProvenance,
    VisitsWorkspaceQuery,
    VisitsWorkspaceRelatedCustomer,
    VisitsWorkspaceRelatedSalesRep,
    VisitsWorkspaceRelatedWorkingZone,
    VisitsWorkspaceResponse,
    VisitsWorkspaceRows,
    VisitsWorkspaceSalesRepRow,
    VisitsWorkspaceSortBy,
    VisitsWorkspaceSortOrder,
    VisitsWorkspaceSummary,
    VisitsWorkspaceTab,
    VisitsWorkspaceTabStatus,
    VisitsWorkspaceVisitRow,
    VisitsWorkspaceWorkingZoneRow,
)

T = TypeVar("T")


@dataclass(slots=True)
class _ScopedVisitsData:
    organizations: list[CanonicalOrganization]
    organizations_by_id: dict[UUID, CanonicalOrganization]
    customers_by_id: dict[UUID, CanonicalCustomer]
    sales_reps_by_id: dict[UUID, CanonicalSalesRep]
    working_zones_by_id: dict[UUID, CanonicalWorkingZone]
    visits: list[CanonicalVisit]
    visit_stocks: list[CanonicalVisitStock]
    quiz_answers: list[CanonicalVisitQuizAnswer]
    equipments: list[CanonicalVisitEquipment]
    comments: list[CanonicalVisitComment]
    media_assets: list[CanonicalMediaAsset]


class VisitsWorkspaceService:
    """Build Visits / Field Sales business workspace payloads from Canonical V2."""

    def __init__(self, store: CoreDataStore) -> None:
        self._store = store
        self._analytics = BusinessAnalyticsEngine(store)

    def list_workspace(
        self,
        analytics_query: AnalyticsQuery,
        workspace_query: VisitsWorkspaceQuery,
    ) -> VisitsWorkspaceResponse:
        summary_payload = self._analytics.build_summary(analytics_query)
        visits_report = self._analytics.build_visits(analytics_query)
        scoped = self._load_scoped_data(analytics_query)
        period = visits_report.period
        visits = self._filter_by_period(scoped.visits, period.current_start, period.current_end)

        filter_metadata = self._build_filter_metadata(visits, scoped)
        visits = self._apply_workspace_filters(visits, workspace_query, scoped)

        visit_rows = self._sort_visit_rows(
            self._build_visit_rows(visits, scoped),
            workspace_query.sort_by,
            workspace_query.sort_order,
        )
        sales_rep_rows = self._sort_sales_rep_rows(self._build_sales_rep_rows(visits, scoped))
        working_zone_rows = self._sort_working_zone_rows(
            self._build_working_zone_rows(visits, scoped)
        )
        capability_rows = self._build_capability_rows(visits, scoped)
        tabs = self._build_tab_statuses(
            visit_rows,
            sales_rep_rows,
            working_zone_rows,
            capability_rows,
        )

        active_rows_count = self._row_count_for_tab(
            workspace_query.tab,
            visit_rows,
            sales_rep_rows,
            working_zone_rows,
            capability_rows,
        )
        pagination = self._paginate(
            active_rows_count,
            workspace_query.page,
            workspace_query.page_size,
        )
        rows = VisitsWorkspaceRows(
            visits=self._slice_rows(visit_rows, pagination),
            sales_reps=self._slice_rows(sales_rep_rows, pagination),
            working_zones=self._slice_rows(working_zone_rows, pagination),
            capabilities=self._slice_rows(capability_rows, pagination),
        )

        return VisitsWorkspaceResponse(
            period=period,
            active_tab=workspace_query.tab,
            summary=self._build_summary(summary_payload.business.visits, visits, scoped),
            filters=filter_metadata,
            tabs=tabs,
            rows=rows,
            pagination=pagination,
            data_quality=visits_report.data_quality,
        )

    def get_detail(
        self,
        visit_id: UUID,
        analytics_query: AnalyticsQuery,
    ) -> VisitsWorkspaceDetail | None:
        scoped = self._load_scoped_data(analytics_query)
        visit = next((item for item in scoped.visits if item.id == visit_id), None)
        if visit is None:
            return None

        row = self._build_visit_row(visit, scoped)
        visit_stocks = sorted(
            [
                VisitsWorkspaceNestedStockRow(
                    line_number=item.line_number,
                    product_id=item.product_id,
                    product_external_id=item.product_external_id,
                    product_code=item.product_code,
                    product_name=item.product_name,
                    quantity=item.quantity,
                    expiry_date=item.expiry_date,
                    card_code=item.card_code,
                    serial_number=item.serial_number,
                    inventory_kind=item.inventory_kind,
                    unavailable_reason=item.unavailable_reason,
                    data_quality_status=item.data_quality_status,
                )
                for item in scoped.visit_stocks
                if item.visit_id == visit.id
            ],
            key=lambda item: item.line_number,
        )
        quiz_answers = sorted(
            [
                VisitsWorkspaceNestedQuizRow(
                    line_number=item.line_number,
                    quiz_external_id=item.quiz_external_id,
                    quiz_name=item.quiz_name,
                    question_external_id=item.question_external_id,
                    question_text=item.question_text,
                    answer_value=item.answer_value,
                    answer_type=item.answer_type,
                    photo_sha=item.photo_sha,
                    data_quality_status=item.data_quality_status,
                )
                for item in scoped.quiz_answers
                if item.visit_id == visit.id
            ],
            key=lambda item: item.line_number,
        )
        equipments = sorted(
            [
                VisitsWorkspaceNestedEquipmentRow(
                    line_number=item.line_number,
                    equipment_external_id=item.equipment_external_id,
                    equipment_code=item.equipment_code,
                    equipment_name=item.equipment_name,
                    serial_number=item.serial_number,
                    status_code=item.status_code,
                    note=item.note,
                    data_quality_status=item.data_quality_status,
                )
                for item in scoped.equipments
                if item.visit_id == visit.id
            ],
            key=lambda item: item.line_number,
        )
        comments = sorted(
            [
                VisitsWorkspaceNestedCommentRow(
                    line_number=item.line_number,
                    comment_text=item.comment_text,
                    comment_type=item.comment_type,
                    created_by_external_id=item.created_by_external_id,
                    created_at_source=item.created_at_source,
                    data_quality_status=item.data_quality_status,
                )
                for item in scoped.comments
                if item.visit_id == visit.id
            ],
            key=lambda item: item.created_at_source or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        media_assets = sorted(
            [
                VisitsWorkspaceNestedMediaRow(
                    media_id=item.media_id,
                    media_type=item.media_type,
                    source_sha=item.source_sha,
                    source_reference=item.source_reference,
                    download_status=item.download_status,
                    local_path=item.local_path,
                    mime_type=item.mime_type,
                    data_quality_status=item.data_quality_status,
                )
                for item in scoped.media_assets
                if item.visit_id == visit.id
            ],
            key=lambda item: item.media_id or "",
        )

        limitations: list[str] = []
        duration = visit.duration_seconds or visit.derived_duration_seconds
        if duration is None:
            limitations.append("Длительность не зафиксирована в текущих данных.")
        limitations.append("Детерминированная связь визит → заказ/продажа пока не подтверждена.")
        if not visit_stocks:
            limitations.append("Остатки в торговой точке не загружены в текущий canonical dataset.")
        if not quiz_answers:
            limitations.append("Анкеты визита не загружены в текущий canonical dataset.")
        if not equipments:
            limitations.append("Оборудование визита не загружено в текущий canonical dataset.")
        if not comments:
            limitations.append(
                "Структурированные комментарии визита не загружены "
                "в текущий canonical dataset."
            )
        if not media_assets:
            limitations.append("Фотоотчёты не загружены в текущий canonical dataset.")

        return VisitsWorkspaceDetail(
            visit_id=visit.id,
            row=row,
            customer=VisitsWorkspaceRelatedCustomer(
                customer_id=visit.customer_id,
                customer_external_id=visit.customer_external_id,
                customer_code=visit.customer_code,
                customer_name=visit.customer_name,
                detail_href=(
                    f"/customers?customer={visit.customer_external_id}"
                    if visit.customer_external_id
                    else None
                ),
            ),
            sales_rep=VisitsWorkspaceRelatedSalesRep(
                sales_rep_id=visit.sales_rep_id,
                sales_rep_external_id=visit.sales_rep_external_id,
                sales_rep_code=visit.sales_rep_code,
                sales_rep_name=self._sales_rep_name(
                    visit.sales_rep_id,
                    scoped.sales_reps_by_id,
                    visit.sales_rep_name or visit.sales_rep_external_id,
                ),
            ),
            working_zone=VisitsWorkspaceRelatedWorkingZone(
                working_zone_id=visit.working_zone_id,
                working_zone_external_id=visit.working_zone_external_id,
                working_zone_code=visit.working_zone_code,
                working_zone_name=self._working_zone_name(
                    visit.working_zone_id,
                    scoped.working_zones_by_id,
                    visit.working_zone_name or visit.working_zone_external_id,
                ),
            ),
            visit_stocks=visit_stocks,
            quiz_answers=quiz_answers,
            equipments=equipments,
            comments=comments,
            media_assets=media_assets,
            related_sales_status=AnalyticsDataStatus.NOT_AVAILABLE,
            provenance=VisitsWorkspaceProvenance(
                source_endpoint=visit.source_endpoint,
                source_external_id=visit.source_external_id,
                source_raw_record_id=visit.source_raw_record_id,
                request_filial_id=visit.request_filial_id,
                response_filial_id=visit.response_filial_id,
                request_company_id=visit.request_company_id,
                request_project_code=visit.request_project_code,
                data_quality_status=visit.data_quality_status,
            ),
            limitations=limitations,
        )

    def _load_scoped_data(self, analytics_query: AnalyticsQuery) -> _ScopedVisitsData:
        organization_ids = analytics_query.organization_ids
        if analytics_query.organization_id is not None:
            organization_ids = [analytics_query.organization_id]

        organizations = list(self._store.list_canonical_organizations())
        if organization_ids:
            allowed = set(organization_ids)
            organizations = [item for item in organizations if item.organization_id in allowed]

        customers = self._list_scoped(self._store.list_canonical_customers, organization_ids)
        sales_reps = self._list_scoped(
            self._store.list_canonical_sales_reps,
            organization_ids,
        )
        working_zones = self._list_scoped(
            self._store.list_canonical_working_zones,
            organization_ids,
        )
        visits = self._list_scoped(self._store.list_canonical_visits, organization_ids)
        visit_stocks = self._list_scoped(self._store.list_canonical_visit_stocks, organization_ids)
        quiz_answers = self._list_scoped(
            self._store.list_canonical_visit_quiz_answers,
            organization_ids,
        )
        equipments = self._list_scoped(
            self._store.list_canonical_visit_equipments,
            organization_ids,
        )
        comments = self._list_scoped(self._store.list_canonical_visit_comments, organization_ids)
        media_assets = self._list_scoped(self._store.list_canonical_media_assets, organization_ids)

        return _ScopedVisitsData(
            organizations=organizations,
            organizations_by_id={item.organization_id: item for item in organizations},
            customers_by_id={item.id: item for item in customers},
            sales_reps_by_id={item.id: item for item in sales_reps},
            working_zones_by_id={item.id: item for item in working_zones},
            visits=visits,
            visit_stocks=visit_stocks,
            quiz_answers=quiz_answers,
            equipments=equipments,
            comments=comments,
            media_assets=media_assets,
        )

    def _build_summary(
        self,
        visits_metric: AnalyticsMetricValue,
        visits: list[CanonicalVisit],
        scoped: _ScopedVisitsData,
    ) -> VisitsWorkspaceSummary:
        durations = [
            Decimal(item.duration_seconds or item.derived_duration_seconds or 0)
            for item in visits
            if (item.duration_seconds or item.derived_duration_seconds) is not None
        ]
        average_duration = (
            sum(durations, Decimal("0")) / Decimal(len(durations))
            if durations
            else None
        )
        unique_customer_count = len(
            {item.customer_id for item in visits if item.customer_id is not None}
        )
        unique_rep_count = len(
            {item.sales_rep_id for item in visits if item.sales_rep_id is not None}
        )
        unique_zone_count = len(
            {item.working_zone_id for item in visits if item.working_zone_id is not None}
        )
        planned_count = len([item for item in visits if item.is_planned is True])

        return VisitsWorkspaceSummary(
            visits=visits_metric,
            unique_customers=self._metric_from_decimal(
                Decimal(unique_customer_count),
                "count",
                None,
                unique_customer_count,
                (
                    AnalyticsDataStatus.AVAILABLE
                    if unique_customer_count
                    else AnalyticsDataStatus.NO_DATA
                ),
                note="Уникальные клиенты, по которым зафиксированы визиты.",
            ),
            sales_reps=self._metric_from_decimal(
                Decimal(unique_rep_count),
                "count",
                None,
                unique_rep_count,
                AnalyticsDataStatus.AVAILABLE if unique_rep_count else AnalyticsDataStatus.NO_DATA,
                note="Торговые представители с визитами в выбранном срезе.",
            ),
            working_zones=self._metric_from_decimal(
                Decimal(unique_zone_count),
                "count",
                None,
                unique_zone_count,
                AnalyticsDataStatus.AVAILABLE if unique_zone_count else AnalyticsDataStatus.NO_DATA,
                note="Рабочие зоны, где зафиксированы визиты.",
            ),
            planned_visits=self._metric_from_decimal(
                Decimal(planned_count),
                "count",
                None,
                planned_count,
                AnalyticsDataStatus.AVAILABLE if planned_count else AnalyticsDataStatus.NO_DATA,
                note="Плановые визиты, если признак присутствует в источнике.",
            ),
            completed_visits=self._metric_from_decimal(
                Decimal(
                    len(
                        [
                            item
                            for item in visits
                            if item.normalized_status in {"completed", "approved"}
                        ]
                    )
                ),
                "count",
                None,
                len(visits),
                AnalyticsDataStatus.NO_DATA,
                note="Подтверждённый completed status в текущем наборе visits не найден.",
            ),
            average_duration=self._metric_from_decimal(
                average_duration,
                "seconds",
                None,
                len(durations),
                (
                    AnalyticsDataStatus.AVAILABLE
                    if average_duration is not None
                    else AnalyticsDataStatus.NO_DATA
                ),
                note=(
                    "Средняя длительность по визитам с фактическим временем."
                    if average_duration is not None
                    else "Длительность не зафиксирована в текущих данных."
                ),
            ),
            visit_conversion=AnalyticsMetricValue(
                value=None,
                unit="percent",
                status=AnalyticsDataStatus.NOT_AVAILABLE,
                data_status=AnalyticsDataStatus.NOT_AVAILABLE,
                record_count=0,
                note=(
                    "Конверсия визита не рассчитывается без "
                    "детерминированной связи визит → продажа."
                ),
            ),
        )

    def _build_filter_metadata(
        self,
        visits: list[CanonicalVisit],
        scoped: _ScopedVisitsData,
    ) -> VisitsWorkspaceFiltersMetadata:
        organization_counter = Counter()
        customer_counter = Counter()
        sales_rep_counter = Counter()
        working_zone_counter = Counter()
        status_counter = Counter()
        planned_counter = Counter()
        quality_counter = Counter()

        for visit in visits:
            organization_counter[str(visit.organization_id)] += 1
            if visit.customer_external_id and visit.customer_name:
                customer_counter[f"{visit.customer_external_id}::{visit.customer_name}"] += 1
            sales_rep_name = self._sales_rep_name(
                visit.sales_rep_id,
                scoped.sales_reps_by_id,
                visit.sales_rep_name or visit.sales_rep_external_id,
            )
            if sales_rep_name:
                sales_rep_counter[sales_rep_name] += 1
            zone_name = self._working_zone_name(
                visit.working_zone_id,
                scoped.working_zones_by_id,
                visit.working_zone_name or visit.working_zone_external_id,
            )
            if zone_name:
                working_zone_counter[zone_name] += 1
            status_counter[visit.display_status or visit.normalized_status] += 1
            if visit.is_planned is True:
                planned_counter["planned"] += 1
            elif visit.is_planned is False:
                planned_counter["unplanned"] += 1
            else:
                planned_counter["unknown"] += 1
            quality_counter[visit.data_quality_status.value] += 1

        return VisitsWorkspaceFiltersMetadata(
            organizations=[
                VisitsWorkspaceFilterOption(
                    value=str(item.organization_id),
                    label=item.name,
                    count=organization_counter.get(str(item.organization_id), 0),
                )
                for item in scoped.organizations
                if organization_counter.get(str(item.organization_id), 0) > 0
            ],
            customers=[
                VisitsWorkspaceFilterOption(
                    value=value.split("::", 1)[0],
                    label=value.split("::", 1)[1],
                    count=count,
                )
                for value, count in sorted(customer_counter.items(), key=lambda item: item[0])
            ],
            sales_reps=self._optionize_counter(sales_rep_counter),
            working_zones=self._optionize_counter(working_zone_counter),
            statuses=self._optionize_counter(status_counter),
            planned=[
                VisitsWorkspaceFilterOption(
                    value="planned",
                    label="Плановые",
                    count=planned_counter.get("planned", 0),
                ),
                VisitsWorkspaceFilterOption(
                    value="unplanned",
                    label="Вне плана",
                    count=planned_counter.get("unplanned", 0),
                ),
                VisitsWorkspaceFilterOption(
                    value="unknown",
                    label="План не указан",
                    count=planned_counter.get("unknown", 0),
                ),
            ],
            data_quality=self._optionize_counter(quality_counter),
        )

    def _apply_workspace_filters(
        self,
        visits: list[CanonicalVisit],
        workspace_query: VisitsWorkspaceQuery,
        scoped: _ScopedVisitsData,
    ) -> list[CanonicalVisit]:
        rows = visits
        if workspace_query.search:
            needle = workspace_query.search.casefold()
            rows = [
                item
                for item in rows
                if needle in (item.visit_id or "").casefold()
                or needle in (item.source_external_id or "").casefold()
                or needle in (item.customer_name or "").casefold()
                or needle in (
                    self._sales_rep_name(
                        item.sales_rep_id,
                        scoped.sales_reps_by_id,
                        item.sales_rep_name or item.sales_rep_external_id,
                    )
                    or ""
                ).casefold()
                or needle in (
                    self._working_zone_name(
                        item.working_zone_id,
                        scoped.working_zones_by_id,
                        item.working_zone_name or item.working_zone_external_id,
                    )
                    or ""
                ).casefold()
            ]
        if workspace_query.customer:
            allowed = set(workspace_query.customer)
            rows = [item for item in rows if item.customer_external_id in allowed]
        if workspace_query.sales_rep:
            allowed = set(workspace_query.sales_rep)
            rows = [
                item
                for item in rows
                if self._sales_rep_name(
                    item.sales_rep_id,
                    scoped.sales_reps_by_id,
                    item.sales_rep_name or item.sales_rep_external_id,
                )
                in allowed
            ]
        if workspace_query.working_zone:
            allowed = set(workspace_query.working_zone)
            rows = [
                item
                for item in rows
                if self._working_zone_name(
                    item.working_zone_id,
                    scoped.working_zones_by_id,
                    item.working_zone_name or item.working_zone_external_id,
                )
                in allowed
            ]
        if workspace_query.status:
            allowed = set(workspace_query.status)
            rows = [
                item
                for item in rows
                if (item.display_status or item.normalized_status) in allowed
            ]
        if workspace_query.planned:
            allowed = set(workspace_query.planned)
            filtered: list[CanonicalVisit] = []
            for item in rows:
                key = "unknown"
                if item.is_planned is True:
                    key = "planned"
                elif item.is_planned is False:
                    key = "unplanned"
                if key in allowed:
                    filtered.append(item)
            rows = filtered
        if workspace_query.data_quality:
            allowed_quality = set(workspace_query.data_quality)
            rows = [item for item in rows if item.data_quality_status in allowed_quality]
        return rows

    def _build_visit_rows(
        self,
        visits: list[CanonicalVisit],
        scoped: _ScopedVisitsData,
    ) -> list[VisitsWorkspaceVisitRow]:
        return [self._build_visit_row(item, scoped) for item in visits]

    def _build_visit_row(
        self,
        visit: CanonicalVisit,
        scoped: _ScopedVisitsData,
    ) -> VisitsWorkspaceVisitRow:
        has_comments = any(item.visit_id == visit.id for item in scoped.comments)
        has_media = any(item.visit_id == visit.id for item in scoped.media_assets)
        has_visit_stock = any(item.visit_id == visit.id for item in scoped.visit_stocks)
        has_quiz_answers = any(item.visit_id == visit.id for item in scoped.quiz_answers)
        has_equipment = any(item.visit_id == visit.id for item in scoped.equipments)
        return VisitsWorkspaceVisitRow(
            visit_id=visit.id,
            source_visit_id=visit.visit_id,
            source_external_id=visit.source_external_id,
            business_date=visit.visited_at or visit.visit_date,
            organization_id=visit.organization_id,
            organization_name=self._organization_name(
                visit.organization_id,
                scoped.organizations_by_id,
            ),
            customer_id=visit.customer_id,
            customer_external_id=visit.customer_external_id,
            customer_code=visit.customer_code,
            customer_name=visit.customer_name,
            sales_rep_id=visit.sales_rep_id,
            sales_rep_name=self._sales_rep_name(
                visit.sales_rep_id,
                scoped.sales_reps_by_id,
                visit.sales_rep_name or visit.sales_rep_external_id,
            ),
            working_zone_id=visit.working_zone_id,
            working_zone_name=self._working_zone_name(
                visit.working_zone_id,
                scoped.working_zones_by_id,
                visit.working_zone_name or visit.working_zone_external_id,
            ),
            source_status_code=visit.source_status_code,
            normalized_status=visit.normalized_status,
            display_status=visit.display_status,
            is_planned=visit.is_planned,
            start_time=visit.visit_start_time,
            end_time=visit.visit_end_time,
            duration_seconds=visit.duration_seconds or visit.derived_duration_seconds,
            has_comments=has_comments,
            has_media=has_media,
            has_visit_stock=has_visit_stock,
            has_quiz_answers=has_quiz_answers,
            has_equipment=has_equipment,
            data_quality_status=visit.data_quality_status,
            data_status=self._analytics_status_from_quality(visit.data_quality_status),
        )

    def _build_sales_rep_rows(
        self,
        visits: list[CanonicalVisit],
        scoped: _ScopedVisitsData,
    ) -> list[VisitsWorkspaceSalesRepRow]:
        visits_by_rep: dict[UUID, list[CanonicalVisit]] = defaultdict(list)
        for visit in visits:
            if visit.sales_rep_id is not None:
                visits_by_rep[visit.sales_rep_id].append(visit)

        rows: list[VisitsWorkspaceSalesRepRow] = []
        for rep_id, rep_visits in visits_by_rep.items():
            rep = scoped.sales_reps_by_id.get(rep_id)
            rep_name = self._sales_rep_name(rep_id, scoped.sales_reps_by_id, None)
            if rep is None or rep_name is None:
                continue
            unique_customers = len(
                {item.customer_id for item in rep_visits if item.customer_id is not None}
            )
            unique_zones = len(
                {item.working_zone_id for item in rep_visits if item.working_zone_id is not None}
            )
            planned = len([item for item in rep_visits if item.is_planned is True])
            completed = len(
                [
                    item
                    for item in rep_visits
                    if item.normalized_status in {"completed", "approved"}
                ]
            )
            organization_ids = sorted({item.organization_id for item in rep_visits}, key=str)
            rows.append(
                VisitsWorkspaceSalesRepRow(
                    sales_rep_id=rep.id,
                    sales_rep_key=rep.source_external_id,
                    sales_rep_name=rep_name,
                    organization_ids=organization_ids,
                    organization_names=[
                        self._organization_name(item, scoped.organizations_by_id)
                        for item in organization_ids
                    ],
                    visits=self._metric_from_decimal(
                        Decimal(len(rep_visits)),
                        "count",
                        None,
                        len(rep_visits),
                        self._status_from_quality_rows(rep_visits),
                        note="Количество визитов торгового представителя.",
                    ),
                    unique_customers=self._metric_from_decimal(
                        Decimal(unique_customers),
                        "count",
                        None,
                        unique_customers,
                        (
                            AnalyticsDataStatus.AVAILABLE
                            if unique_customers
                            else AnalyticsDataStatus.NO_DATA
                        ),
                        note="Уникальные клиенты, посещённые представителем.",
                    ),
                    working_zones=self._metric_from_decimal(
                        Decimal(unique_zones),
                        "count",
                        None,
                        unique_zones,
                        (
                            AnalyticsDataStatus.AVAILABLE
                            if unique_zones
                            else AnalyticsDataStatus.NO_DATA
                        ),
                        note="Рабочие зоны с визитами представителя.",
                    ),
                    completed_visits=self._metric_from_decimal(
                        Decimal(completed),
                        "count",
                        None,
                        completed,
                        (
                            AnalyticsDataStatus.NO_DATA
                            if completed == 0
                            else AnalyticsDataStatus.AVAILABLE
                        ),
                        note="Completed/approved mapping не подтверждён в текущем visits dataset.",
                    ),
                    planned_visits=self._metric_from_decimal(
                        Decimal(planned),
                        "count",
                        None,
                        planned,
                        AnalyticsDataStatus.AVAILABLE if planned else AnalyticsDataStatus.NO_DATA,
                        note="Плановые визиты представителя, если признак пришёл из источника.",
                    ),
                    visit_conversion=AnalyticsMetricValue(
                        value=None,
                        unit="percent",
                        status=AnalyticsDataStatus.NOT_AVAILABLE,
                        data_status=AnalyticsDataStatus.NOT_AVAILABLE,
                        record_count=0,
                        note="Конверсия визитов не рассчитывается без связи визит → продажа.",
                    ),
                    data_status=self._status_from_quality_rows(rep_visits),
                )
            )
        return rows

    def _build_working_zone_rows(
        self,
        visits: list[CanonicalVisit],
        scoped: _ScopedVisitsData,
    ) -> list[VisitsWorkspaceWorkingZoneRow]:
        visits_by_zone: dict[UUID, list[CanonicalVisit]] = defaultdict(list)
        for visit in visits:
            if visit.working_zone_id is not None:
                visits_by_zone[visit.working_zone_id].append(visit)

        rows: list[VisitsWorkspaceWorkingZoneRow] = []
        for zone_id, zone_visits in visits_by_zone.items():
            zone = scoped.working_zones_by_id.get(zone_id)
            zone_name = self._working_zone_name(zone_id, scoped.working_zones_by_id, None)
            if zone is None or zone_name is None:
                continue
            unique_customers = len(
                {item.customer_id for item in zone_visits if item.customer_id is not None}
            )
            unique_reps = len(
                {item.sales_rep_id for item in zone_visits if item.sales_rep_id is not None}
            )
            organization_ids = sorted({item.organization_id for item in zone_visits}, key=str)
            rows.append(
                VisitsWorkspaceWorkingZoneRow(
                    working_zone_id=zone.id,
                    working_zone_key=zone.source_external_id,
                    working_zone_name=zone_name,
                    organization_ids=organization_ids,
                    organization_names=[
                        self._organization_name(item, scoped.organizations_by_id)
                        for item in organization_ids
                    ],
                    visits=self._metric_from_decimal(
                        Decimal(len(zone_visits)),
                        "count",
                        None,
                        len(zone_visits),
                        self._status_from_quality_rows(zone_visits),
                        note="Количество визитов в рабочей зоне.",
                    ),
                    unique_customers=self._metric_from_decimal(
                        Decimal(unique_customers),
                        "count",
                        None,
                        unique_customers,
                        (
                            AnalyticsDataStatus.AVAILABLE
                            if unique_customers
                            else AnalyticsDataStatus.NO_DATA
                        ),
                        note="Уникальные клиенты в зоне.",
                    ),
                    sales_reps=self._metric_from_decimal(
                        Decimal(unique_reps),
                        "count",
                        None,
                        unique_reps,
                        (
                            AnalyticsDataStatus.AVAILABLE
                            if unique_reps
                            else AnalyticsDataStatus.NO_DATA
                        ),
                        note="Торговые представители, работавшие в зоне.",
                    ),
                    data_status=self._status_from_quality_rows(zone_visits),
                )
            )
        return rows

    def _build_capability_rows(
        self,
        visits: list[CanonicalVisit],
        scoped: _ScopedVisitsData,
    ) -> list[VisitsWorkspaceCapabilityItem]:
        duration_count = len(
            [
                item
                for item in visits
                if (item.duration_seconds or item.derived_duration_seconds) is not None
            ]
        )
        return [
            VisitsWorkspaceCapabilityItem(
                key="visits",
                label="Визиты",
                status=VisitsWorkspaceCapabilityStatus.AVAILABLE,
                message="Канонические визиты загружены и доступны для анализа.",
                count=len(visits),
            ),
            VisitsWorkspaceCapabilityItem(
                key="customers",
                label="Клиенты",
                status=VisitsWorkspaceCapabilityStatus.AVAILABLE,
                message="Связь визит → клиент подтверждена.",
                count=len({item.customer_id for item in visits if item.customer_id is not None}),
            ),
            VisitsWorkspaceCapabilityItem(
                key="sales_reps",
                label="Торговые представители",
                status=VisitsWorkspaceCapabilityStatus.AVAILABLE,
                message="Связь визит → торговый представитель подтверждена.",
                count=len({item.sales_rep_id for item in visits if item.sales_rep_id is not None}),
            ),
            VisitsWorkspaceCapabilityItem(
                key="working_zones",
                label="Рабочие зоны",
                status=VisitsWorkspaceCapabilityStatus.AVAILABLE,
                message="Связь визит → рабочая зона подтверждена.",
                count=len(
                    {
                        item.working_zone_id
                        for item in visits
                        if item.working_zone_id is not None
                    }
                ),
            ),
            VisitsWorkspaceCapabilityItem(
                key="duration",
                label="Длительность",
                status=(
                    VisitsWorkspaceCapabilityStatus.AVAILABLE
                    if duration_count
                    else VisitsWorkspaceCapabilityStatus.NO_DATA
                ),
                message=(
                    "Время визита присутствует в части строк."
                    if duration_count
                    else "Длительность не зафиксирована в текущих данных."
                ),
                count=duration_count,
            ),
            VisitsWorkspaceCapabilityItem(
                key="visit_to_sale",
                label="Связь визит → продажа",
                status=VisitsWorkspaceCapabilityStatus.NOT_AVAILABLE,
                message="Детерминированная связь визита с заказом/продажей пока не подтверждена.",
                count=None,
            ),
            VisitsWorkspaceCapabilityItem(
                key="visit_stocks",
                label="Остатки в точке",
                status=(
                    VisitsWorkspaceCapabilityStatus.AVAILABLE
                    if scoped.visit_stocks
                    else VisitsWorkspaceCapabilityStatus.NO_DATA_IN_CURRENT_RAW
                ),
                message=(
                    "Остатки в торговой точке доступны."
                    if scoped.visit_stocks
                    else "Остатки в торговой точке не загружены в текущий canonical dataset."
                ),
                count=len(scoped.visit_stocks),
            ),
            VisitsWorkspaceCapabilityItem(
                key="quizzes",
                label="Анкеты",
                status=(
                    VisitsWorkspaceCapabilityStatus.AVAILABLE
                    if scoped.quiz_answers
                    else VisitsWorkspaceCapabilityStatus.NO_DATA_IN_CURRENT_RAW
                ),
                message=(
                    "Ответы на анкеты доступны."
                    if scoped.quiz_answers
                    else "Анкеты визита не загружены в текущий canonical dataset."
                ),
                count=len(scoped.quiz_answers),
            ),
            VisitsWorkspaceCapabilityItem(
                key="equipment",
                label="Оборудование",
                status=(
                    VisitsWorkspaceCapabilityStatus.AVAILABLE
                    if scoped.equipments
                    else VisitsWorkspaceCapabilityStatus.NO_DATA_IN_CURRENT_RAW
                ),
                message=(
                    "Оборудование визита доступно."
                    if scoped.equipments
                    else "Оборудование визита не загружено в текущий canonical dataset."
                ),
                count=len(scoped.equipments),
            ),
            VisitsWorkspaceCapabilityItem(
                key="comments",
                label="Комментарии",
                status=(
                    VisitsWorkspaceCapabilityStatus.AVAILABLE
                    if scoped.comments
                    else VisitsWorkspaceCapabilityStatus.NO_DATA_IN_CURRENT_RAW
                ),
                message=(
                    "Структурированные комментарии визитов доступны."
                    if scoped.comments
                    else (
                        "Структурированные комментарии визита не загружены "
                        "в текущий canonical dataset."
                    )
                ),
                count=len(scoped.comments),
            ),
            VisitsWorkspaceCapabilityItem(
                key="media",
                label="Фотоотчёты",
                status=(
                    VisitsWorkspaceCapabilityStatus.AVAILABLE
                    if scoped.media_assets
                    else VisitsWorkspaceCapabilityStatus.NO_DATA_IN_CURRENT_RAW
                ),
                message=(
                    "Фотоотчёты/медиа доступны."
                    if scoped.media_assets
                    else "Фотоотчёты не загружены в текущий canonical dataset."
                ),
                count=len(scoped.media_assets),
            ),
        ]

    def _build_tab_statuses(
        self,
        visit_rows: list[VisitsWorkspaceVisitRow],
        sales_rep_rows: list[VisitsWorkspaceSalesRepRow],
        working_zone_rows: list[VisitsWorkspaceWorkingZoneRow],
        capability_rows: list[VisitsWorkspaceCapabilityItem],
    ) -> list[VisitsWorkspaceTabStatus]:
        return [
            VisitsWorkspaceTabStatus(
                tab=VisitsWorkspaceTab.VISITS,
                label="Визиты",
                count=len(visit_rows),
                status=(
                    VisitsWorkspaceCapabilityStatus.AVAILABLE
                    if visit_rows
                    else VisitsWorkspaceCapabilityStatus.NO_DATA
                ),
            ),
            VisitsWorkspaceTabStatus(
                tab=VisitsWorkspaceTab.SALES_REPS,
                label="Торговые представители",
                count=len(sales_rep_rows),
                status=(
                    VisitsWorkspaceCapabilityStatus.AVAILABLE
                    if sales_rep_rows
                    else VisitsWorkspaceCapabilityStatus.NO_DATA
                ),
            ),
            VisitsWorkspaceTabStatus(
                tab=VisitsWorkspaceTab.WORKING_ZONES,
                label="Рабочие зоны",
                count=len(working_zone_rows),
                status=(
                    VisitsWorkspaceCapabilityStatus.AVAILABLE
                    if working_zone_rows
                    else VisitsWorkspaceCapabilityStatus.NO_DATA
                ),
            ),
            VisitsWorkspaceTabStatus(
                tab=VisitsWorkspaceTab.CAPABILITIES,
                label="Покрытие данных",
                count=len(capability_rows),
                status=VisitsWorkspaceCapabilityStatus.AVAILABLE,
            ),
        ]

    def _sort_visit_rows(
        self,
        rows: list[VisitsWorkspaceVisitRow],
        sort_by: VisitsWorkspaceSortBy,
        sort_order: VisitsWorkspaceSortOrder,
    ) -> list[VisitsWorkspaceVisitRow]:
        reverse = sort_order is VisitsWorkspaceSortOrder.DESC
        key_map = {
            VisitsWorkspaceSortBy.DATE: lambda row: (
                row.business_date or datetime.min.replace(tzinfo=UTC)
            ),
            VisitsWorkspaceSortBy.CUSTOMER: lambda row: row.customer_name or "",
            VisitsWorkspaceSortBy.SALES_REP: lambda row: row.sales_rep_name or "",
            VisitsWorkspaceSortBy.WORKING_ZONE: lambda row: row.working_zone_name or "",
            VisitsWorkspaceSortBy.STATUS: lambda row: row.display_status or row.normalized_status,
            VisitsWorkspaceSortBy.ORGANIZATION: lambda row: row.organization_name,
        }
        return sorted(rows, key=key_map[sort_by], reverse=reverse)

    def _sort_sales_rep_rows(
        self,
        rows: list[VisitsWorkspaceSalesRepRow],
    ) -> list[VisitsWorkspaceSalesRepRow]:
        return sorted(
            rows,
            key=lambda row: (
                row.visits.value or Decimal("0"),
                row.sales_rep_name,
            ),
            reverse=True,
        )

    def _sort_working_zone_rows(
        self,
        rows: list[VisitsWorkspaceWorkingZoneRow],
    ) -> list[VisitsWorkspaceWorkingZoneRow]:
        return sorted(
            rows,
            key=lambda row: (
                row.visits.value or Decimal("0"),
                row.working_zone_name,
            ),
            reverse=True,
        )

    def _row_count_for_tab(
        self,
        tab: VisitsWorkspaceTab,
        visit_rows: list[VisitsWorkspaceVisitRow],
        sales_rep_rows: list[VisitsWorkspaceSalesRepRow],
        working_zone_rows: list[VisitsWorkspaceWorkingZoneRow],
        capability_rows: list[VisitsWorkspaceCapabilityItem],
    ) -> int:
        if tab is VisitsWorkspaceTab.SALES_REPS:
            return len(sales_rep_rows)
        if tab is VisitsWorkspaceTab.WORKING_ZONES:
            return len(working_zone_rows)
        if tab is VisitsWorkspaceTab.CAPABILITIES:
            return len(capability_rows)
        return len(visit_rows)

    def _slice_rows(self, rows: list[T], pagination: VisitsWorkspacePagination) -> list[T]:
        start = pagination.page_size * (pagination.page - 1)
        end = start + pagination.page_size
        return rows[start:end]

    def _paginate(
        self,
        total_items: int,
        page: int,
        page_size: int,
    ) -> VisitsWorkspacePagination:
        total_pages = max(1, ceil(total_items / page_size)) if total_items else 1
        current_page = min(page, total_pages)
        return VisitsWorkspacePagination(
            page=current_page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        )

    def _filter_by_period(
        self,
        visits: list[CanonicalVisit],
        start: datetime | None,
        end: datetime | None,
    ) -> list[CanonicalVisit]:
        if start is None or end is None:
            return visits
        return [
            item
            for item in visits
            if self._within_period(item.visited_at or item.visit_date, start, end)
        ]

    def _within_period(
        self,
        value: datetime | None,
        start: datetime,
        end: datetime,
    ) -> bool:
        if value is None:
            return False
        return start <= value <= end

    def _organization_name(
        self,
        organization_id: UUID,
        organizations_by_id: dict[UUID, CanonicalOrganization],
    ) -> str:
        organization = organizations_by_id.get(organization_id)
        return organization.name if organization is not None else "Организация не определена"

    def _sales_rep_name(
        self,
        sales_rep_id: UUID | None,
        sales_reps_by_id: dict[UUID, CanonicalSalesRep],
        fallback: str | None,
    ) -> str | None:
        if sales_rep_id is not None and sales_rep_id in sales_reps_by_id:
            rep = sales_reps_by_id[sales_rep_id]
            return rep.sales_manager_name or rep.sales_manager_code or rep.source_external_id
        return fallback

    def _working_zone_name(
        self,
        working_zone_id: UUID | None,
        working_zones_by_id: dict[UUID, CanonicalWorkingZone],
        fallback: str | None,
    ) -> str | None:
        if working_zone_id is not None and working_zone_id in working_zones_by_id:
            zone = working_zones_by_id[working_zone_id]
            return zone.room_name or zone.room_code or zone.source_external_id
        return fallback

    def _analytics_status_from_quality(
        self,
        quality: CanonicalDataQualityStatus,
    ) -> AnalyticsDataStatus:
        if quality is CanonicalDataQualityStatus.VERIFIED:
            return AnalyticsDataStatus.AVAILABLE
        if quality is CanonicalDataQualityStatus.PARTIAL:
            return AnalyticsDataStatus.PARTIAL
        if quality is CanonicalDataQualityStatus.UNRESOLVED:
            return AnalyticsDataStatus.UNRESOLVED
        return AnalyticsDataStatus.NO_VERIFIED_DATA

    def _metric_from_decimal(
        self,
        value: Decimal | None,
        unit: str,
        currency: str | None,
        record_count: int,
        status: AnalyticsDataStatus,
        *,
        note: str,
    ) -> AnalyticsMetricValue:
        return AnalyticsMetricValue(
            value=value,
            unit=unit,
            status=status,
            data_status=status,
            currency=currency,
            record_count=record_count,
            note=note,
        )

    def _status_from_quality_rows(
        self,
        rows: list[CanonicalVisit],
    ) -> AnalyticsDataStatus:
        if not rows:
            return AnalyticsDataStatus.NO_DATA
        statuses = {self._analytics_status_from_quality(row.data_quality_status) for row in rows}
        if AnalyticsDataStatus.NO_VERIFIED_DATA in statuses:
            return AnalyticsDataStatus.NO_VERIFIED_DATA
        if AnalyticsDataStatus.UNRESOLVED in statuses:
            return AnalyticsDataStatus.UNRESOLVED
        if AnalyticsDataStatus.PARTIAL in statuses:
            return AnalyticsDataStatus.PARTIAL
        return AnalyticsDataStatus.AVAILABLE

    def _list_scoped(
        self,
        reader: Callable[..., list[T] | tuple[T, ...] | object],
        organization_ids: list[UUID],
    ) -> list[T]:
        if not organization_ids:
            return list(reader())  # type: ignore[arg-type]
        aggregated: list[T] = []
        for organization_id in organization_ids:
            aggregated.extend(list(reader(organization_id=organization_id)))  # type: ignore[arg-type]
        return aggregated

    def _optionize_counter(self, counter: Counter[str]) -> list[VisitsWorkspaceFilterOption]:
        return [
            VisitsWorkspaceFilterOption(value=value, label=value, count=count)
            for value, count in sorted(counter.items(), key=lambda item: item[0])
        ]
