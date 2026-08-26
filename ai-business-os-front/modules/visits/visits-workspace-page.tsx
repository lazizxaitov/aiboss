"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  useBusinessContext,
  useSelectedOrganizationNames,
} from "@/components/business/business-context-provider";
import { useBusinessRefresh } from "@/components/business/business-refresh-provider";
import { Badge } from "@/components/ui/badge";
import { FilterBar } from "@/components/ui/filter-bar";
import { Drawer } from "@/components/ui/drawer";
import { MultiSelect } from "@/components/ui/multi-select";
import { SearchInput } from "@/components/ui/search-input";
import { Select } from "@/components/ui/select";
import { Surface } from "@/components/ui/surface";
import { cn } from "@/lib/cn";
import {
  getVisitsWorkspace,
  getVisitsWorkspaceDetail,
  type AnalyticsDataStatus,
  type VisitsWorkspaceCapabilityItem,
  type VisitsWorkspaceDetail,
  type VisitsWorkspaceFilters,
  type VisitsWorkspaceSalesRepRow,
  type VisitsWorkspaceSortBy,
  type VisitsWorkspaceSortOrder,
  type VisitsWorkspaceTab,
  type VisitsWorkspaceVisitRow,
  type VisitsWorkspaceWorkingZoneRow,
} from "@/lib/core-api";
import { VISITS_TABS } from "@/lib/workspace-view-config";

const TAB_LABELS: Record<VisitsWorkspaceTab, string> = Object.fromEntries(
  VISITS_TABS.map(({ tab, label }) => [tab, label]),
) as Record<VisitsWorkspaceTab, string>;

const PAGE_SIZE = 25;

const SUMMARY_REGISTRY = [
  { key: "visits", label: "Визитов" },
  { key: "unique_customers", label: "Уникальных клиентов" },
  { key: "sales_reps", label: "Торговых представителей" },
  { key: "working_zones", label: "Рабочих зон" },
  { key: "planned_visits", label: "Плановых визитов" },
  { key: "completed_visits", label: "Подтверждённые визиты" },
  { key: "average_duration", label: "Средняя длительность" },
  { key: "visit_conversion", label: "Конверсия визита" },
] as const;

const SORT_OPTIONS: Array<{ value: VisitsWorkspaceSortBy; label: string }> = [
  { value: "date", label: "Дата" },
  { value: "customer", label: "Клиент" },
  { value: "sales_rep", label: "Торговый представитель" },
  { value: "working_zone", label: "Рабочая зона" },
  { value: "status", label: "Статус" },
  { value: "organization", label: "Организация" },
];

type QueryState = {
  tab: VisitsWorkspaceTab;
  search: string;
  customer: string[];
  salesRep: string[];
  workingZone: string[];
  status: string[];
  planned: string[];
  dataQuality: Array<"verified" | "partial" | "unresolved" | "unsafe">;
  sortBy: VisitsWorkspaceSortBy;
  sortOrder: VisitsWorkspaceSortOrder;
  page: number;
};

type DetailState = VisitsWorkspaceVisitRow | null;

function buildWorkspaceFilters(
  businessState: ReturnType<typeof useBusinessContext>["state"],
  query: QueryState,
): VisitsWorkspaceFilters {
  return {
    organizationIds: businessState.selectedOrganizationIds,
    period: businessState.period.preset,
    dateFrom: businessState.period.dateFrom,
    dateTo: businessState.period.dateTo,
    tab: query.tab,
    search: query.search || null,
    customer: query.customer,
    salesRep: query.salesRep,
    workingZone: query.workingZone,
    status: query.status,
    planned: query.planned,
    dataQuality: query.dataQuality,
    sortBy: query.sortBy,
    sortOrder: query.sortOrder,
    page: query.page,
    pageSize: PAGE_SIZE,
  };
}

function formatDateTime(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatMetricValue(
  value: string | number | null | undefined,
  unit: string,
  status?: AnalyticsDataStatus,
) {
  if (status === "NOT_AVAILABLE") return "Недоступно";
  if (status === "NO_DATA" && value == null) return "Нет данных";
  if (value == null) return "—";
  if (unit === "seconds") {
    const seconds = Number(value);
    if (!Number.isFinite(seconds)) return "—";
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;
    if (minutes <= 0) return `${remainder} сек`;
    return remainder > 0 ? `${minutes} мин ${remainder} сек` : `${minutes} мин`;
  }
  if (unit === "percent") return `${value}%`;
  return String(value);
}

function statusLabel(status: AnalyticsDataStatus) {
  switch (status) {
    case "AVAILABLE":
      return "Подтверждено";
    case "PARTIAL":
      return "Частично";
    case "NO_DATA":
      return "Нет данных";
    case "NO_VERIFIED_DATA":
      return "Нет подтверждённых данных";
    case "UNRESOLVED":
      return "Неразрешено";
    case "NOT_AVAILABLE":
      return "Недоступно";
    default:
      return status;
  }
}

function qualityVariant(status: "verified" | "partial" | "unresolved" | "unsafe") {
  if (status === "verified") return "accent" as const;
  if (status === "partial") return "soft" as const;
  if (status === "unresolved") return "neutral" as const;
  return "dark" as const;
}

function qualityStatusLabel(status: "verified" | "partial" | "unresolved" | "unsafe") {
  switch (status) {
    case "verified":
      return "Подтверждено";
    case "partial":
      return "Частично";
    case "unresolved":
      return "Есть неразрешённые связи";
    case "unsafe":
      return "Использовать с осторожностью";
    default:
      return status;
  }
}

function capabilityVariant(status: string) {
  if (status === "AVAILABLE") return "accent" as const;
  if (status === "PARTIAL") return "soft" as const;
  if (status === "NO_DATA" || status === "NO_DATA_IN_CURRENT_RAW") return "neutral" as const;
  return "dark" as const;
}

function plannedLabel(value: boolean | null) {
  if (value === true) return "Плановый";
  if (value === false) return "Вне плана";
  return "Не указан";
}

function renderVisitsTable(
  rows: VisitsWorkspaceVisitRow[],
  onSelect: (row: VisitsWorkspaceVisitRow) => void,
) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-[#3a3d43] text-xs uppercase tracking-[0.22em] text-slate-400">
          <tr>
            <th className="px-5 py-4 font-medium">Визит</th>
            <th className="px-5 py-4 font-medium">Дата</th>
            <th className="px-5 py-4 font-medium">Организация</th>
            <th className="px-5 py-4 font-medium">Клиент</th>
            <th className="px-5 py-4 font-medium">Представитель</th>
            <th className="px-5 py-4 font-medium">Зона</th>
            <th className="px-5 py-4 font-medium">Статус</th>
            <th className="px-5 py-4 font-medium">План</th>
            <th className="px-5 py-4 font-medium">Начало</th>
            <th className="px-5 py-4 font-medium">Конец</th>
            <th className="px-5 py-4 font-medium">Длительность</th>
            <th className="px-5 py-4 font-medium">Покрытие</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.visit_id}
              className="cursor-pointer border-b border-[#3a3d43] transition hover:bg-[#343840] last:border-b-0"
              onClick={() => onSelect(row)}
            >
              <td className="px-5 py-4">
                <div className="font-medium text-[#f4f7fb]">
                  {row.source_visit_id || row.source_external_id}
                </div>
                <div className="mt-1 text-xs text-slate-400">
                  {[
                    row.has_comments ? "коммент." : null,
                    row.has_media ? "фото" : null,
                    row.has_visit_stock ? "остатки" : null,
                    row.has_quiz_answers ? "анкета" : null,
                    row.has_equipment ? "оборуд." : null,
                  ]
                    .filter(Boolean)
                    .join(" · ") || "только header"}
                </div>
              </td>
              <td className="px-5 py-4 text-slate-200">{formatDateTime(row.business_date)}</td>
              <td className="px-5 py-4 text-slate-200">{row.organization_name}</td>
              <td className="px-5 py-4">
                <div className="font-medium text-[#f4f7fb]">{row.customer_name ?? "—"}</div>
                <div className="mt-1 text-xs text-slate-400">{row.customer_code ?? row.customer_external_id ?? "—"}</div>
              </td>
              <td className="px-5 py-4 text-slate-200">{row.sales_rep_name ?? "—"}</td>
              <td className="px-5 py-4 text-slate-200">{row.working_zone_name ?? "—"}</td>
              <td className="px-5 py-4">
                <div className="font-medium text-[#f4f7fb]">{row.display_status}</div>
                <div className="mt-1 text-xs text-slate-400">{row.normalized_status}</div>
              </td>
              <td className="px-5 py-4 text-slate-200">{plannedLabel(row.is_planned)}</td>
              <td className="px-5 py-4 text-slate-200">{formatDateTime(row.start_time)}</td>
              <td className="px-5 py-4 text-slate-200">{formatDateTime(row.end_time)}</td>
              <td className="px-5 py-4 text-slate-200">
                {row.duration_seconds == null ? "Не зафиксирована" : formatMetricValue(row.duration_seconds, "seconds")}
              </td>
              <td className="px-5 py-4">
                <Badge variant={qualityVariant(row.data_quality_status)}>
                  {qualityStatusLabel(row.data_quality_status)}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderSalesRepsTable(rows: VisitsWorkspaceSalesRepRow[]) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-[#3a3d43] text-xs uppercase tracking-[0.22em] text-slate-400">
          <tr>
            <th className="px-5 py-4 font-medium">Представитель</th>
            <th className="px-5 py-4 font-medium">Организации</th>
            <th className="px-5 py-4 font-medium">Визиты</th>
            <th className="px-5 py-4 font-medium">Клиенты</th>
            <th className="px-5 py-4 font-medium">Зоны</th>
            <th className="px-5 py-4 font-medium">Плановые</th>
            <th className="px-5 py-4 font-medium">Конверсия</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.sales_rep_id} className="border-b border-[#3a3d43] last:border-b-0">
              <td className="px-5 py-4">
                <div className="font-medium text-[#f4f7fb]">{row.sales_rep_name}</div>
                <div className="mt-1 text-xs text-slate-400">{row.sales_rep_key}</div>
              </td>
              <td className="px-5 py-4 text-slate-200">{row.organization_names.join(", ") || "—"}</td>
              <td className="px-5 py-4 text-slate-200">{formatMetricValue(row.visits.value, row.visits.unit, row.visits.data_status)}</td>
              <td className="px-5 py-4 text-slate-200">{formatMetricValue(row.unique_customers.value, row.unique_customers.unit, row.unique_customers.data_status)}</td>
              <td className="px-5 py-4 text-slate-200">{formatMetricValue(row.working_zones.value, row.working_zones.unit, row.working_zones.data_status)}</td>
              <td className="px-5 py-4 text-slate-200">{formatMetricValue(row.planned_visits.value, row.planned_visits.unit, row.planned_visits.data_status)}</td>
              <td className="px-5 py-4 text-slate-200">{formatMetricValue(row.visit_conversion.value, row.visit_conversion.unit, row.visit_conversion.data_status)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderWorkingZonesTable(rows: VisitsWorkspaceWorkingZoneRow[]) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-[#3a3d43] text-xs uppercase tracking-[0.22em] text-slate-400">
          <tr>
            <th className="px-5 py-4 font-medium">Рабочая зона</th>
            <th className="px-5 py-4 font-medium">Организации</th>
            <th className="px-5 py-4 font-medium">Визиты</th>
            <th className="px-5 py-4 font-medium">Клиенты</th>
            <th className="px-5 py-4 font-medium">Представители</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.working_zone_id} className="border-b border-[#3a3d43] last:border-b-0">
              <td className="px-5 py-4">
                <div className="font-medium text-[#f4f7fb]">{row.working_zone_name}</div>
                <div className="mt-1 text-xs text-slate-400">{row.working_zone_key}</div>
              </td>
              <td className="px-5 py-4 text-slate-200">{row.organization_names.join(", ") || "—"}</td>
              <td className="px-5 py-4 text-slate-200">{formatMetricValue(row.visits.value, row.visits.unit, row.visits.data_status)}</td>
              <td className="px-5 py-4 text-slate-200">{formatMetricValue(row.unique_customers.value, row.unique_customers.unit, row.unique_customers.data_status)}</td>
              <td className="px-5 py-4 text-slate-200">{formatMetricValue(row.sales_reps.value, row.sales_reps.unit, row.sales_reps.data_status)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderCapabilities(rows: VisitsWorkspaceCapabilityItem[]) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {rows.map((row) => (
        <Surface key={row.key} className="p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">{row.label}</p>
              <p className="mt-2 text-sm leading-6 text-slate-400">{row.message}</p>
            </div>
            <Badge variant={capabilityVariant(row.status)}>{row.status}</Badge>
          </div>
          {typeof row.count === "number" ? (
            <p className="mt-4 text-sm text-slate-300">Записей: {row.count}</p>
          ) : null}
        </Surface>
      ))}
    </div>
  );
}

export function VisitsWorkspacePage() {
  const business = useBusinessContext();
  const { subscribe } = useBusinessRefresh();
  const selectedNames = useSelectedOrganizationNames();
  const [query, setQuery] = useState<QueryState>({
    tab: "visits",
    search: "",
    customer: [],
    salesRep: [],
    workingZone: [],
    status: [],
    planned: [],
    dataQuality: [],
    sortBy: "date",
    sortOrder: "desc",
    page: 1,
  });
  const [data, setData] = useState<Awaited<ReturnType<typeof getVisitsWorkspace>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedRow, setSelectedRow] = useState<DetailState>(null);
  const [detail, setDetail] = useState<VisitsWorkspaceDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  const filters = useMemo(
    () => buildWorkspaceFilters(business.state, query),
    [business.state, query],
  );

  const updateQuery = (updater: (current: QueryState) => QueryState) => {
    setRefreshing(true);
    setError(null);
    setQuery(updater);
  };

  const handleSelectRow = (row: VisitsWorkspaceVisitRow) => {
    setDetail(null);
    setDetailError(null);
    setSelectedRow(row);
  };

  useEffect(() => subscribe(() => setRefreshToken((current) => current + 1)), [subscribe]);

  useEffect(() => {
    let active = true;
    void getVisitsWorkspace(filters)
      .then((response) => {
        if (!active) return;
        setData(response);
      })
      .catch((reason) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "Не удалось загрузить визиты.");
        setData(null);
      })
      .finally(() => {
        if (active) setRefreshing(false);
      });
    return () => {
      active = false;
    };
  }, [filters, refreshToken]);

  useEffect(() => {
    if (!selectedRow) return;
    let active = true;
    void getVisitsWorkspaceDetail(selectedRow.visit_id, filters)
      .then((response) => {
        if (!active) return;
        setDetail(response);
      })
      .catch((reason) => {
        if (!active) return;
        setDetailError(reason instanceof Error ? reason.message : "Не удалось загрузить Visit 360.");
        setDetail(null);
      })
    return () => {
      active = false;
    };
  }, [selectedRow, filters, refreshToken]);

  const summaryCards = useMemo(() => {
    if (!data) return [];
    return SUMMARY_REGISTRY.map((item) => ({
      ...item,
      metric: data.summary[item.key],
    }));
  }, [data]);

  const emptyMessage = useMemo(() => {
    if (!data) return null;
    if (query.tab === "capabilities") return null;
    const count = data.pagination.total_items;
    if (count > 0) return null;
    if (selectedNames.length === 1) {
      return `В выбранном контексте для ${selectedNames[0]} визиты не найдены.`;
    }
    return "В выбранном контексте визиты не найдены.";
  }, [data, query.tab, selectedNames]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <Surface className="px-6 py-5">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
          <div className="max-w-3xl">
            <p className="text-[11px] uppercase tracking-[0.32em] text-slate-400">
              Полевые продажи
            </p>
            <h1 className="mt-3 text-[34px] font-semibold tracking-[-0.06em] text-[#f4f7fb]">Визиты</h1>
            <p className="mt-3 text-sm leading-6 text-slate-400">
              Канонические визиты, торговые представители и рабочие зоны по выбранным организациям.
              Конверсия визита отключена, пока нет детерминированной связи визит → продажа.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:w-[440px]">
            {summaryCards.slice(0, 4).map((card) => (
              <div
                key={card.key}
                className="rounded-[22px] border border-[#3a3d43] bg-[#2E3137] px-4 py-4"
              >
                <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">{card.label}</p>
                <p className="mt-3 text-2xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">
                  {formatMetricValue(card.metric.value, card.metric.unit, card.metric.data_status)}
                </p>
                <p className="mt-2 text-xs text-slate-400">
                  {card.metric.note ?? statusLabel(card.metric.data_status)}
                </p>
              </div>
            ))}
          </div>
        </div>
      </Surface>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Surface className="px-6 py-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Контекст</p>
              <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                {selectedNames.length === 0 ? "Все организации" : selectedNames.join(", ")}
              </h2>
              <p className="mt-2 text-sm text-slate-400">
                {data?.period.label ?? "Загрузка периода..."}
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              {VISITS_TABS.map((view) => {
                const tab = data?.tabs.find((item) => item.tab === view.tab);
                return (
                <button
                  key={view.tab}
                  type="button"
                  onClick={() =>
                    updateQuery((current) => ({
                      ...current,
                      tab: view.tab,
                      page: 1,
                    }))
                  }
                  className={cn(
                    "inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition",
                    query.tab === view.tab
                      ? "border-slate-900 bg-slate-900 text-white"
                      : "border-[#3a3d43] bg-[#2E3137] text-slate-300 hover:border-[#4a4e56] hover:text-[#f4f7fb]",
                  )}
                >
                  <span>{view.label}</span>
                  <span className="text-xs opacity-80">{tab?.count ?? 0}</span>
                </button>
                );
              })}
            </div>
          </div>
        </Surface>

        <Surface className="px-6 py-5">
          <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Статус</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {(data?.data_quality.items ?? []).map((item) => (
              <Badge key={`${item.metric_key}-${statusLabel(item.data_status)}`} variant="soft">
                {item.metric_key}: {statusLabel(item.data_status)}
              </Badge>
            ))}
          </div>
          <div className="mt-4 space-y-2 text-sm text-slate-400">
            {(data?.data_quality.notes ?? []).map((note) => (
              <p key={note}>{note}</p>
            ))}
          </div>
        </Surface>
      </div>

      <FilterBar title="Фильтры" subtitle="Поиск, сортировка и поля визитов.">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <SearchInput
              value={query.search}
              onChange={(event) =>
                updateQuery((current) => ({ ...current, search: event.target.value, page: 1 }))
              }
              placeholder="ID визита, клиент, представитель, зона"
            />
            <Select
              label="Сортировка"
              value={query.sortBy}
              options={SORT_OPTIONS}
              onChange={(value) =>
                updateQuery((current) => ({
                  ...current,
                  sortBy: value as VisitsWorkspaceSortBy,
                  page: 1,
                }))
              }
            />
            <Select
              label="Порядок"
              value={query.sortOrder}
              options={[
                { value: "desc", label: "Сначала новые" },
                { value: "asc", label: "Сначала старые" },
              ]}
              onChange={(value) =>
                updateQuery((current) => ({
                  ...current,
                  sortOrder: value as VisitsWorkspaceSortOrder,
                  page: 1,
                }))
              }
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <MultiSelect
              label="Клиенты"
              value={query.customer}
              options={data?.filters.customers ?? []}
              onChange={(value) => updateQuery((current) => ({ ...current, customer: value, page: 1 }))}
            />
            <MultiSelect
              label="Торговые представители"
              value={query.salesRep}
              options={data?.filters.sales_reps ?? []}
              onChange={(value) => updateQuery((current) => ({ ...current, salesRep: value, page: 1 }))}
            />
            <MultiSelect
              label="Рабочие зоны"
              value={query.workingZone}
              options={data?.filters.working_zones ?? []}
              onChange={(value) => updateQuery((current) => ({ ...current, workingZone: value, page: 1 }))}
            />
            <MultiSelect
              label="Статус"
              value={query.status}
              options={data?.filters.statuses ?? []}
              onChange={(value) => updateQuery((current) => ({ ...current, status: value, page: 1 }))}
            />
            <MultiSelect
              label="План"
              value={query.planned}
              options={data?.filters.planned ?? []}
              onChange={(value) => updateQuery((current) => ({ ...current, planned: value, page: 1 }))}
            />
            <MultiSelect
              label="Качество"
              value={query.dataQuality}
              options={data?.filters.data_quality ?? []}
              onChange={(value) =>
                updateQuery((current) => ({
                  ...current,
                  dataQuality: value as QueryState["dataQuality"],
                  page: 1,
                }))
              }
            />
          </div>
        </div>
      </FilterBar>

      <Surface className="min-h-0 flex-1 overflow-hidden">
        <div className="flex items-center justify-between border-b border-[#3a3d43] px-6 py-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.26em] text-slate-400">
              {TAB_LABELS[query.tab]}
            </p>
            <p className="mt-2 text-sm text-slate-400">
              {data ? `${data.pagination.total_items} строк в текущем контексте` : "Загрузка..."}
            </p>
          </div>
          <Badge variant="soft">
            {refreshing || (!data && !error)
              ? "Обновление..."
              : error
                ? "Ошибка"
                : statusLabel(data?.data_quality.overall_status ?? "NO_DATA")}
          </Badge>
        </div>

        <div className="min-h-0 overflow-auto">
          {error ? (
            <div className="px-6 py-6 text-sm text-rose-600">{error}</div>
          ) : !data && !error ? (
            <div className="px-6 py-6 text-sm text-slate-400">Загрузка страницы...</div>
          ) : emptyMessage ? (
            <div className="px-6 py-6 text-sm text-slate-400">{emptyMessage}</div>
          ) : query.tab === "visits" ? (
            renderVisitsTable(data?.rows.visits ?? [], handleSelectRow)
          ) : query.tab === "sales_reps" ? (
            renderSalesRepsTable(data?.rows.sales_reps ?? [])
          ) : query.tab === "working_zones" ? (
            renderWorkingZonesTable(data?.rows.working_zones ?? [])
          ) : (
            <div className="px-6 py-6">{renderCapabilities(data?.rows.capabilities ?? [])}</div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-[#3a3d43] px-6 py-4 text-sm text-slate-400">
          <div>
            Страница {data?.pagination.page ?? 1} из {data?.pagination.total_pages ?? 1}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={(data?.pagination.page ?? 1) <= 1}
              onClick={() =>
                updateQuery((current) => ({
                  ...current,
                  page: Math.max(1, current.page - 1),
                }))
              }
              className="rounded-full border border-[#3a3d43] px-4 py-2 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Назад
            </button>
            <button
              type="button"
              disabled={(data?.pagination.page ?? 1) >= (data?.pagination.total_pages ?? 1)}
              onClick={() =>
                updateQuery((current) => ({
                  ...current,
                  page: current.page + 1,
                }))
              }
              className="rounded-full border border-[#3a3d43] px-4 py-2 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Дальше
            </button>
          </div>
        </div>
      </Surface>

      <Drawer
        open={selectedRow !== null}
        onClose={() => {
          setSelectedRow(null);
          setDetail(null);
          setDetailError(null);
        }}
        title={detail?.row.source_visit_id || detail?.row.source_external_id || "Визит"}
        description={
          detail?.row.business_date
            ? `${detail.row.organization_name} · ${formatDateTime(detail.row.business_date)}`
            : detail?.row.organization_name
        }
        badges={
          detail ? (
            <>
              <Badge variant={qualityVariant(detail.row.data_quality_status)}>
                {qualityStatusLabel(detail.row.data_quality_status)}
              </Badge>
              <Badge variant="soft">{detail.row.display_status}</Badge>
              <Badge variant="soft">{plannedLabel(detail.row.is_planned)}</Badge>
            </>
          ) : null
        }
      >
        {selectedRow !== null && detail === null && detailError === null ? (
          <p className="text-sm text-slate-400">Загрузка Visit 360...</p>
        ) : detailError ? (
          <p className="text-sm text-rose-600">{detailError}</p>
        ) : detail ? (
          <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2">
              <Surface className="p-5">
                <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Клиент</p>
                <p className="mt-3 text-lg font-semibold tracking-[-0.03em] text-[#f4f7fb]">
                  {detail.customer.customer_name ?? "Не определён"}
                </p>
                <p className="mt-2 text-sm text-slate-400">
                  {detail.customer.customer_code ?? detail.customer.customer_external_id ?? "—"}
                </p>
                {detail.customer.detail_href ? (
                  <Link href={detail.customer.detail_href} className="mt-4 inline-flex text-sm font-medium text-[#FFF27A] hover:text-[#f4f7fb]">
                    Открыть карточку клиента
                  </Link>
                ) : null}
              </Surface>

              <Surface className="p-5">
                <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Полевой контекст</p>
                <div className="mt-3 space-y-3 text-sm text-slate-300">
                  <p><span className="font-medium text-[#f4f7fb]">Торговый представитель:</span> {detail.sales_rep.sales_rep_name ?? "Не определён"}</p>
                  <p><span className="font-medium text-[#f4f7fb]">Рабочая зона:</span> {detail.working_zone.working_zone_name ?? "Не определена"}</p>
                  <p><span className="font-medium text-[#f4f7fb]">Длительность:</span> {detail.row.duration_seconds == null ? "Длительность не зафиксирована в текущих данных" : formatMetricValue(detail.row.duration_seconds, "seconds")}</p>
                </div>
              </Surface>
            </div>

            <Surface className="p-5">
              <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Ограничения источника</p>
              <div className="mt-4 space-y-2 text-sm leading-6 text-slate-300">
                {detail.limitations.map((item) => (
                  <p key={item}>{item}</p>
                ))}
              </div>
            </Surface>

            <Surface className="p-5">
              <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Вложенные данные</p>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <div className="rounded-[20px] border border-[#3a3d43] p-4">
                  <p className="font-medium text-[#f4f7fb]">Остатки в точке</p>
                  <p className="mt-2 text-sm text-slate-400">{detail.visit_stocks.length > 0 ? `${detail.visit_stocks.length} строк` : "Не загружены"}</p>
                </div>
                <div className="rounded-[20px] border border-[#3a3d43] p-4">
                  <p className="font-medium text-[#f4f7fb]">Анкеты</p>
                  <p className="mt-2 text-sm text-slate-400">{detail.quiz_answers.length > 0 ? `${detail.quiz_answers.length} ответов` : "Не загружены"}</p>
                </div>
                <div className="rounded-[20px] border border-[#3a3d43] p-4">
                  <p className="font-medium text-[#f4f7fb]">Оборудование</p>
                  <p className="mt-2 text-sm text-slate-400">{detail.equipments.length > 0 ? `${detail.equipments.length} записей` : "Не загружено"}</p>
                </div>
                <div className="rounded-[20px] border border-[#3a3d43] p-4">
                  <p className="font-medium text-[#f4f7fb]">Фото и медиа</p>
                  <p className="mt-2 text-sm text-slate-400">{detail.media_assets.length > 0 ? `${detail.media_assets.length} файлов` : "Не загружены"}</p>
                </div>
              </div>
            </Surface>

            <Surface className="p-5">
              <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Provenance</p>
              <div className="mt-4 grid gap-3 md:grid-cols-2 text-sm text-slate-300">
                <p><span className="font-medium text-[#f4f7fb]">Источник:</span> {detail.provenance.source_endpoint}</p>
                <p><span className="font-medium text-[#f4f7fb]">Внешний ID:</span> {detail.provenance.source_external_id}</p>
                <p><span className="font-medium text-[#f4f7fb]">Запись-источник:</span> {detail.provenance.source_raw_record_id ?? "—"}</p>
                <p><span className="font-medium text-[#f4f7fb]">Филиал запроса:</span> {detail.provenance.request_filial_id ?? "—"}</p>
                <p><span className="font-medium text-[#f4f7fb]">Филиал ответа:</span> {detail.provenance.response_filial_id ?? "—"}</p>
                <p><span className="font-medium text-[#f4f7fb]">Проект:</span> {detail.provenance.request_project_code ?? "—"}</p>
              </div>
            </Surface>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
