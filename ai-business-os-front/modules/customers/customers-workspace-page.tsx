"use client";

import { useEffect, useMemo, useState } from "react";

import {
  useBusinessContext,
  useSelectedOrganizationNames,
} from "@/components/business/business-context-provider";
import { useBusinessRefresh } from "@/components/business/business-refresh-provider";
import { Badge } from "@/components/ui/badge";
import { SmartUpPageRefreshButton } from "@/components/smartup/page-refresh-button";
import { FilterBar } from "@/components/ui/filter-bar";
import { Drawer } from "@/components/ui/drawer";
import { MultiSelect } from "@/components/ui/multi-select";
import { SearchInput } from "@/components/ui/search-input";
import { Select } from "@/components/ui/select";
import { Surface } from "@/components/ui/surface";
import { cn } from "@/lib/cn";
import {
  getCustomerWorkspace,
  getCustomerWorkspaceDetail,
  type AnalyticsDataStatus,
  type CustomerWorkspaceDetail,
  type CustomerWorkspaceFilters,
  type CustomerWorkspaceRow,
  type CustomerWorkspaceSortBy,
  type CustomerWorkspaceSortOrder,
} from "@/lib/core-api";
import { formatMoneyValue } from "@/lib/money";

const PAGE_SIZE = 25;

const SUMMARY_REGISTRY = [
  { key: "unique_customers", label: "Уникальные клиенты" },
  { key: "customers_with_sales", label: "Клиенты с продажами" },
  { key: "revenue", label: "Выручка по клиентам" },
  { key: "average_revenue_per_customer", label: "Средняя выручка" },
  { key: "payments_received", label: "Получено денег" },
  { key: "return_value", label: "Возвраты" },
  { key: "visits", label: "Визиты" },
  { key: "active_customers", label: "Активные" },
] as const;

const SORT_OPTIONS: Array<{ value: CustomerWorkspaceSortBy; label: string }> = [
  { value: "revenue", label: "Выручка" },
  { value: "orders", label: "Заказы" },
  { value: "sold_units", label: "Продано единиц" },
  { value: "average_order", label: "Средний заказ" },
  { value: "payments", label: "Платежи" },
  { value: "returns", label: "Возвраты" },
  { value: "visits", label: "Визиты" },
  { value: "last_purchase", label: "Последняя покупка" },
  { value: "customer_name", label: "Клиент" },
] as const;

type QueryState = {
  search: string;
  hasSales: "all" | "yes" | "no";
  hasPayments: "all" | "yes" | "no";
  hasReturns: "all" | "yes" | "no";
  hasVisits: "all" | "yes" | "no";
  customerType: string[];
  salesRep: string[];
  workingZone: string[];
  sortBy: CustomerWorkspaceSortBy;
  sortOrder: CustomerWorkspaceSortOrder;
  page: number;
};

function formatDateOnly(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
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

function statusLabel(status: AnalyticsDataStatus) {
  switch (status) {
    case "AVAILABLE":
      return "Подтверждено";
    case "PARTIAL":
      return "Частично";
    case "NO_DATA":
      return "Нет данных";
    case "NO_VERIFIED_DATA":
      return "Нет подтверждения";
    case "UNRESOLVED":
      return "Есть связи без resolution";
    case "NOT_AVAILABLE":
      return "Недоступно";
    default:
      return status;
  }
}

function qualityLabel(status: CustomerWorkspaceRow["data_quality_status"]) {
  switch (status) {
    case "verified":
      return "Профиль подтверждён";
    case "partial":
      return "Профиль заполнен частично";
    case "unresolved":
      return "Есть неразрешённые связи";
    default:
      return "Использовать с осторожностью";
  }
}

function qualityBadgeVariant(status: CustomerWorkspaceRow["data_quality_status"]) {
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

function metricValueTone(status: AnalyticsDataStatus) {
  if (status === "AVAILABLE") return "text-[#f4f7fb]";
  if (status === "PARTIAL") return "text-[#f4f7fb]";
  return "text-slate-400";
}

function normalizeBooleanFilter(value: QueryState["hasSales" | "hasPayments" | "hasReturns" | "hasVisits"]) {
  if (value === "all") return null;
  return value === "yes";
}

function formatMetricValue(
  value: string | number | null | undefined,
  currency?: string | null,
  status?: AnalyticsDataStatus,
) {
  if (status === "NOT_AVAILABLE") return "Недоступно";
  if (value == null) return "—";
  return formatMoneyValue(value, currency);
}

function buildWorkspaceFilters(
  businessState: ReturnType<typeof useBusinessContext>["state"],
  query: QueryState,
): CustomerWorkspaceFilters {
  return {
    organizationIds: businessState.selectedOrganizationIds,
    period: businessState.period.preset,
    dateFrom: businessState.period.dateFrom,
    dateTo: businessState.period.dateTo,
    search: query.search || null,
    hasSales: normalizeBooleanFilter(query.hasSales),
    hasPayments: normalizeBooleanFilter(query.hasPayments),
    hasReturns: normalizeBooleanFilter(query.hasReturns),
    hasVisits: normalizeBooleanFilter(query.hasVisits),
    customerType: query.customerType,
    salesRep: query.salesRep,
    workingZone: query.workingZone,
    sortBy: query.sortBy,
    sortOrder: query.sortOrder,
    page: query.page,
    pageSize: PAGE_SIZE,
  };
}

export function CustomersWorkspacePage() {
  const business = useBusinessContext();
  const { subscribe } = useBusinessRefresh();
  const selectedNames = useSelectedOrganizationNames();
  const [query, setQuery] = useState<QueryState>({
    search: "",
    hasSales: "all",
    hasPayments: "all",
    hasReturns: "all",
    hasVisits: "all",
    customerType: [],
    salesRep: [],
    workingZone: [],
    sortBy: "revenue",
    sortOrder: "desc",
    page: 1,
  });
  const [data, setData] = useState<Awaited<ReturnType<typeof getCustomerWorkspace>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedRow, setSelectedRow] = useState<CustomerWorkspaceRow | null>(null);
  const [detail, setDetail] = useState<CustomerWorkspaceDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  const filters = useMemo(
    () => buildWorkspaceFilters(business.state, query),
    [business.state, query],
  );

  useEffect(() => subscribe(() => setRefreshToken((current) => current + 1)), [subscribe]);

  useEffect(() => {
    let active = true;
    const loadingTimer = window.setTimeout(() => {
      if (!active) return;
      setLoading(true);
      setError(null);
    }, 0);
    void getCustomerWorkspace(filters)
      .then((response) => {
        if (!active) return;
        setData(response);
      })
      .catch((reason) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "Не удалось загрузить карточки клиентов.");
        setData(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      window.clearTimeout(loadingTimer);
    };
  }, [filters, refreshToken]);

  useEffect(() => {
    if (!selectedRow) return;
    let active = true;
    const loadingTimer = window.setTimeout(() => {
      if (!active) return;
      setDetailLoading(true);
      setDetailError(null);
    }, 0);
    void getCustomerWorkspaceDetail(selectedRow.customer_id, filters)
      .then((response) => {
        if (!active) return;
        setDetail(response);
      })
      .catch((reason) => {
        if (!active) return;
        setDetailError(
          reason instanceof Error ? reason.message : "Не удалось загрузить карточку клиента.",
        );
        setDetail(null);
      })
      .finally(() => {
        if (active) setDetailLoading(false);
      });

    return () => {
      active = false;
      window.clearTimeout(loadingTimer);
    };
  }, [selectedRow, filters, refreshToken]);

  const summaryTiles = useMemo(() => {
    if (!data) return [];
    return SUMMARY_REGISTRY.map(({ key, label }) => ({
      key,
      label,
      metric: data.summary[key],
    }));
  }, [data]);

  return (
    <section className="space-y-5">
      <div className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Клиенты / 360</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">Клиенты</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
              Единое окно по клиентам, продажам, платежам, возвратам и визитам.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <SmartUpPageRefreshButton page="customers" onCompleted={() => setRefreshToken((value) => value + 1)} />
            <Badge variant="soft">{selectedNames.join(", ") || "Все организации"}</Badge>
            <Badge variant="soft">{data?.period.label ?? "Период загружается"}</Badge>
          </div>
        </div>
      </div>

      <Surface className="overflow-visible px-4 py-4 sm:px-5">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {summaryTiles.map(({ key, label, metric }) => (
            <div key={key} className="rounded-[22px] border border-[#3a3d43] bg-[#2E3137] px-4 py-4">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">{label}</p>
                <Badge variant="soft">{statusLabel(metric.data_status)}</Badge>
              </div>
              <p
                className={cn(
                  "mt-4 text-3xl font-semibold tracking-[-0.05em]",
                  metricValueTone(metric.data_status),
                )}
              >
                {formatMetricValue(metric.value, metric.currency, metric.data_status)}
              </p>
              <p className="mt-2 min-h-[40px] text-sm leading-5 text-slate-400">
                {metric.note ?? "—"}
              </p>
            </div>
          ))}
        </div>
      </Surface>

      <FilterBar
        title="Фильтры"
        subtitle="Поиск, статус связи и дополнительные измерения по клиентам."
      >
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <SearchInput
              value={query.search}
              onChange={(event) =>
                setQuery((current) => ({
                  ...current,
                  search: event.target.value,
                  page: 1,
                }))
              }
              placeholder="имя клиента, код, телефон, ID источника"
            />
            {[
              ["Продажи", "hasSales"],
              ["Платежи", "hasPayments"],
              ["Возвраты", "hasReturns"],
              ["Визиты", "hasVisits"],
            ].map(([label, key]) => (
              <Select
                key={key}
                label={label}
                value={query[key as keyof Pick<QueryState, "hasSales" | "hasPayments" | "hasReturns" | "hasVisits">] as string}
                options={[
                  { value: "all", label: "Все" },
                  { value: "yes", label: "Есть" },
                  { value: "no", label: "Нет" },
                ]}
                onChange={(value) =>
                  setQuery((current) => ({
                    ...current,
                    [key]: value,
                    page: 1,
                  }))
                }
              />
            ))}
            <Select
              label="Сортировка"
              value={query.sortBy}
              options={SORT_OPTIONS}
              onChange={(value) =>
                setQuery((current) => ({
                  ...current,
                  sortBy: value as CustomerWorkspaceSortBy,
                }))
              }
            />
            <Select
              label="Порядок"
              value={query.sortOrder}
              options={[
                { value: "desc", label: "По убыванию" },
                { value: "asc", label: "По возрастанию" },
              ]}
              onChange={(value) =>
                setQuery((current) => ({
                  ...current,
                  sortOrder: value as CustomerWorkspaceSortOrder,
                }))
              }
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-2">
            <MultiSelect
              label="Тип клиента"
              value={query.customerType}
              options={data?.filters.customer_types ?? []}
              onChange={(next) =>
                setQuery((current) => ({ ...current, customerType: next, page: 1 }))
              }
            />
            <MultiSelect
              label="Менеджеры"
              value={query.salesRep}
              options={data?.filters.sales_reps ?? []}
              onChange={(next) =>
                setQuery((current) => ({ ...current, salesRep: next, page: 1 }))
              }
            />
            <MultiSelect
              label="Зоны"
              value={query.workingZone}
              options={data?.filters.working_zones ?? []}
              onChange={(next) =>
                setQuery((current) => ({ ...current, workingZone: next, page: 1 }))
              }
            />
          </div>
        </div>
      </FilterBar>

      <Surface className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#3a3d43] px-5 py-4">
          <div className="min-w-0">
            <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Клиенты</p>
            <h2 className="mt-1 text-xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
              Клиентская база и активность
            </h2>
          </div>
          <Badge variant="soft">{data?.pagination.total_items ?? 0} клиентов</Badge>
        </div>

        {error ? (
          <div className="px-5 py-6 text-sm text-rose-600">{error}</div>
        ) : loading ? (
          <div className="px-5 py-6 text-sm text-slate-400">Загрузка клиентов...</div>
        ) : data && data.rows.length === 0 ? (
          <div className="px-5 py-6 text-sm text-slate-400">
            В выбранном контексте клиенты не найдены.
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-[1720px] border-separate border-spacing-0 text-left text-sm">
                <thead className="sticky top-0 z-10 bg-[#2E3137]">
                  <tr className="text-[11px] uppercase tracking-[0.18em] text-slate-400">
                    {[
                      "Клиент",
                      "Источник / код",
                      "Организации",
                      "Тип",
                      "Заказы",
                      "Реализации",
                      "Выручка",
                      "Продано",
                      "Средний заказ",
                      "Платежи",
                      "Возвраты",
                      "Визиты",
                      "Первая покупка",
                      "Последняя покупка",
                      "Дней с покупки",
                      "Товаров",
                      "Качество",
                    ].map((column) => (
                      <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data?.rows.map((row) => (
                    <tr
                      key={row.customer_id}
                      className="cursor-pointer transition hover:bg-[#343840]/80"
                      onClick={() => {
                        setSelectedRow(row);
                        setDetail(null);
                      }}
                    >
                      <td className="border-b border-[#3a3d43] px-4 py-4 align-top">
                        <div className="space-y-1">
                          <p className="font-semibold text-[#f4f7fb]">{row.customer_name}</p>
                          <p className="text-xs text-slate-400">{qualityLabel(row.data_quality_status)}</p>
                        </div>
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {row.customer_code ?? row.customer_external_id}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-[#f4f7fb]">
                        <div className="max-w-[220px] space-y-1">
                          {row.organization_names.map((name) => (
                            <p key={`${row.customer_id}-${name}`}>{name}</p>
                          ))}
                        </div>
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {row.customer_type ?? "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-[#f4f7fb]">
                        {row.orders_count ?? "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-[#f4f7fb]">
                        {row.realised_sales_count ?? "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 font-medium text-[#f4f7fb]">
                        {row.revenue ? formatMoneyValue(row.revenue, "UZS") : "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-[#f4f7fb]">
                        {row.sold_units ?? "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-[#f4f7fb]">
                        {row.average_order_value ? formatMoneyValue(row.average_order_value, "UZS") : "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {row.payments_received ? formatMoneyValue(row.payments_received, "UZS") : "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {row.return_value ? formatMoneyValue(row.return_value, "UZS") : "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {row.visits_count ?? "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {formatDateOnly(row.first_purchase)}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {formatDateOnly(row.last_purchase)}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {row.days_since_last_purchase ?? "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {row.products_bought_count ?? "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4">
                        <Badge variant={qualityBadgeVariant(row.data_quality_status)}>
                          {qualityStatusLabel(row.data_quality_status)}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
              <p className="text-sm text-slate-400">
                Показано {data?.rows.length ?? 0} из {data?.pagination.total_items ?? 0}
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={!data || data.pagination.page <= 1}
                  onClick={() =>
                    setQuery((current) => ({
                      ...current,
                      page: Math.max(1, current.page - 1),
                    }))
                  }
                  className="rounded-full border border-[#3a3d43] px-4 py-2 text-sm text-slate-300 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Назад
                </button>
                <Badge variant="soft">
                  {data?.pagination.page ?? 1} / {data?.pagination.total_pages ?? 1}
                </Badge>
                <button
                  type="button"
                  disabled={!data || data.pagination.page >= data.pagination.total_pages}
                  onClick={() =>
                    setQuery((current) => ({
                      ...current,
                      page: current.page + 1,
                    }))
                  }
                  className="rounded-full border border-[#3a3d43] px-4 py-2 text-sm text-slate-300 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Далее
                </button>
              </div>
            </div>
          </>
        )}
      </Surface>

      <Drawer
        open={selectedRow !== null}
        onClose={() => {
          setSelectedRow(null);
          setDetail(null);
          setDetailError(null);
        }}
        title={selectedRow?.customer_name ?? "Карточка клиента"}
        description={
          selectedRow
            ? `${selectedRow.customer_code ?? selectedRow.customer_external_id} · ${selectedRow.organization_names.join(", ")}`
            : undefined
        }
        badges={
          selectedRow ? (
            <>
              <Badge variant={qualityBadgeVariant(selectedRow.data_quality_status)}>
                {qualityLabel(selectedRow.data_quality_status)}
              </Badge>
              <Badge variant="soft">{selectedRow.segment ?? "Сегмент не определён"}</Badge>
            </>
          ) : null
        }
      >
        {detailError ? (
          <div className="text-sm text-rose-600">{detailError}</div>
        ) : detailLoading || !detail ? (
          <div className="text-sm text-slate-400">Загрузка карточки клиента...</div>
        ) : (
          <div className="space-y-5">
            <Surface className="px-4 py-4">
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {SUMMARY_REGISTRY.slice(2, 8).map(({ key, label }) => {
                  const metric = detail.overview[key];
                  return (
                    <div key={key} className="rounded-[20px] border border-[#3a3d43] bg-[#2E3137] px-4 py-4">
                      <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">{label}</p>
                      <p
                        className={cn(
                          "mt-3 text-2xl font-semibold tracking-[-0.04em]",
                          metricValueTone(metric.data_status),
                        )}
                      >
                        {formatMetricValue(metric.value, metric.currency, metric.data_status)}
                      </p>
                      <p className="mt-2 text-sm leading-5 text-slate-400">{metric.note ?? "—"}</p>
                    </div>
                  );
                })}
              </div>
            </Surface>

            {detail.ai_summary ? (
              <Surface className="px-4 py-4">
                <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Сводка AI</p>
                <p className="mt-2 text-sm leading-6 text-slate-200">{detail.ai_summary}</p>
              </Surface>
            ) : null}

            <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-4 py-4">
                  <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Продажи и заказы</p>
                  <h3 className="mt-1 text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                    Продажи и заказы клиента
                  </h3>
                </div>
                <div className="max-h-[340px] overflow-auto">
                  <table className="min-w-full border-separate border-spacing-0 text-left text-sm">
                    <thead className="sticky top-0 bg-[#2E3137] text-[11px] uppercase tracking-[0.18em] text-slate-400">
                      <tr>
                        {["Дата", "Deal", "Организация", "Статус", "Заказ", "Реализация", "Единицы"].map(
                          (column) => (
                            <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">
                              {column}
                            </th>
                          ),
                        )}
                      </tr>
                    </thead>
                    <tbody>
                      {detail.sales.map((row) => (
                        <tr key={row.record_id}>
                          <td className="border-b border-[#3a3d43] px-4 py-3 text-slate-300">
                            {formatDateOnly(row.business_date)}
                          </td>
                          <td className="border-b border-[#3a3d43] px-4 py-3 font-medium text-[#f4f7fb]">
                            {row.order_number ?? row.sale_number ?? row.deal_id ?? "—"}
                          </td>
                          <td className="border-b border-[#3a3d43] px-4 py-3 text-slate-300">
                            {row.organization_name}
                          </td>
                          <td className="border-b border-[#3a3d43] px-4 py-3 text-slate-300">
                            {row.display_status}
                          </td>
                          <td className="border-b border-[#3a3d43] px-4 py-3 text-[#f4f7fb]">
                            {row.order_amount ? formatMoneyValue(row.order_amount, row.currency_code) : "—"}
                          </td>
                          <td className="border-b border-[#3a3d43] px-4 py-3 text-[#f4f7fb]">
                            {row.realised_amount
                              ? formatMoneyValue(row.realised_amount, row.currency_code)
                              : "—"}
                          </td>
                          <td className="border-b border-[#3a3d43] px-4 py-3 text-slate-300">
                            {row.sold_units ?? "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Surface>

              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-4 py-4">
                  <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Товары</p>
                  <h3 className="mt-1 text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                    Товары клиента
                  </h3>
                </div>
                <div className="max-h-[340px] overflow-auto">
                  <table className="min-w-full border-separate border-spacing-0 text-left text-sm">
                    <thead className="sticky top-0 bg-[#2E3137] text-[11px] uppercase tracking-[0.18em] text-slate-400">
                      <tr>
                        {["Товар", "Продано", "Выручка", "Заказы", "Возврат", "Последняя покупка"].map(
                          (column) => (
                            <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">
                              {column}
                            </th>
                          ),
                        )}
                      </tr>
                    </thead>
                    <tbody>
                      {detail.products.map((row) => (
                        <tr key={`${row.product_id ?? row.product_code ?? row.product_name}`}>
                          <td className="border-b border-[#3a3d43] px-4 py-3 font-medium text-[#f4f7fb]">
                            {row.product_name ?? row.product_code ?? "Товар не определён"}
                          </td>
                          <td className="border-b border-[#3a3d43] px-4 py-3 text-slate-300">
                            {row.sold_units ?? "—"}
                          </td>
                          <td className="border-b border-[#3a3d43] px-4 py-3 text-[#f4f7fb]">
                            {row.revenue ? formatMoneyValue(row.revenue, row.currency_code) : "—"}
                          </td>
                          <td className="border-b border-[#3a3d43] px-4 py-3 text-slate-300">
                            {row.orders_count ?? "—"}
                          </td>
                          <td className="border-b border-[#3a3d43] px-4 py-3 text-slate-300">
                            {row.return_quantity ?? "—"}
                          </td>
                          <td className="border-b border-[#3a3d43] px-4 py-3 text-slate-300">
                            {formatDateOnly(row.last_purchase)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Surface>
            </div>

            <div className="grid gap-5 xl:grid-cols-3">
              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-4 py-4">
                  <h3 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                    Платежи
                  </h3>
                </div>
                <div className="max-h-[320px] space-y-3 overflow-auto px-4 py-4">
                  {detail.payments.length ? (
                    detail.payments.map((row) => (
                      <div key={row.payment_id} className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="font-medium text-[#f4f7fb]">{row.payment_number ?? "Платёж"}</p>
                            <p className="mt-1 text-sm text-slate-400">
                              {row.organization_name} · {row.normalized_payment_type ?? "тип не определён"}
                            </p>
                          </div>
                          <p className="text-sm font-semibold text-[#f4f7fb]">
                            {row.amount ? formatMoneyValue(row.amount, row.currency_code) : "—"}
                          </p>
                        </div>
                        <p className="mt-2 text-xs text-slate-400">{formatDateTime(row.paid_at)}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-slate-400">Нет данных в выбранном контексте.</p>
                  )}
                </div>
              </Surface>

              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-4 py-4">
                  <h3 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                    Возвраты
                  </h3>
                </div>
                <div className="max-h-[320px] space-y-3 overflow-auto px-4 py-4">
                  {detail.returns.length ? (
                    detail.returns.map((row) => (
                      <div key={row.return_id} className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="font-medium text-[#f4f7fb]">{row.return_number ?? "Возврат"}</p>
                            <p className="mt-1 text-sm text-slate-400">{row.organization_name}</p>
                          </div>
                          <p className="text-sm font-semibold text-[#f4f7fb]">
                            {row.amount ? formatMoneyValue(row.amount, row.currency_code) : "—"}
                          </p>
                        </div>
                        <p className="mt-2 text-xs text-slate-400">
                          {row.products.join(", ") || "Продукты не определены"}
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-slate-400">Нет данных в выбранном контексте.</p>
                  )}
                </div>
              </Surface>

              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-4 py-4">
                  <h3 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                    Визиты
                  </h3>
                </div>
                <div className="max-h-[320px] space-y-3 overflow-auto px-4 py-4">
                  {detail.visits.length ? (
                    detail.visits.map((row) => (
                      <div key={row.visit_id} className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="font-medium text-[#f4f7fb]">{row.organization_name}</p>
                            <p className="mt-1 text-sm text-slate-400">
                              {row.sales_rep_name ?? "Менеджер не указан"} · {row.working_zone_name ?? "Зона не указана"}
                            </p>
                          </div>
                          <Badge variant="soft">{row.status}</Badge>
                        </div>
                        <p className="mt-2 text-xs text-slate-400">{formatDateTime(row.visit_date)}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-slate-400">Нет данных в выбранном контексте.</p>
                  )}
                </div>
              </Surface>
            </div>

            <Surface className="overflow-hidden">
              <div className="border-b border-[#3a3d43] px-4 py-4">
                <h3 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                  Хронология активности
                </h3>
              </div>
              <div className="max-h-[320px] space-y-3 overflow-auto px-4 py-4">
                {detail.timeline.map((event) => (
                  <div key={event.event_id} className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="font-medium text-[#f4f7fb]">{event.title}</p>
                        <p className="mt-1 text-sm text-slate-400">
                          {event.organization_name ?? "—"} · {event.description ?? event.event_type}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-semibold text-[#f4f7fb]">
                          {event.amount
                            ? formatMoneyValue(event.amount, event.currency_code)
                            : event.quantity ?? "—"}
                        </p>
                        <p className="mt-1 text-xs text-slate-400">{formatDateTime(event.happened_at)}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </Surface>

            {(detail.limitations.length > 0 || detail.provenance.reference_sources.length > 0) ? (
              <Surface className="px-4 py-4">
                <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Качество данных и источник</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Badge variant={qualityBadgeVariant(detail.provenance.data_quality_status)}>
                    {qualityStatusLabel(detail.provenance.data_quality_status)}
                  </Badge>
                  {detail.provenance.reference_sources.map((source) => (
                    <Badge key={source} variant="soft">
                      {source}
                    </Badge>
                  ))}
                </div>
                {detail.limitations.length ? (
                  <ul className="mt-4 space-y-2 text-sm leading-6 text-slate-300">
                    {detail.limitations.map((item) => (
                      <li key={item}>• {item}</li>
                    ))}
                  </ul>
                ) : null}
                <div className="mt-4 grid gap-3 text-sm text-slate-300 sm:grid-cols-2">
                  <div>
                    <p className="text-slate-400">ID клиента</p>
                    <p className="mt-1 font-medium text-[#f4f7fb]">
                      {detail.provenance.canonical_customer_id}
                    </p>
                  </div>
                  <div>
                    <p className="text-slate-400">Внешний ID</p>
                    <p className="mt-1 font-medium text-[#f4f7fb]">
                      {detail.provenance.source_external_id}
                    </p>
                  </div>
                </div>
              </Surface>
            ) : null}
          </div>
        )}
      </Drawer>
    </section>
  );
}
