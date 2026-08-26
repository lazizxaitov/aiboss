"use client";

import { useEffect, useMemo, useState } from "react";

import { useBusinessContext, useSelectedOrganizationNames } from "@/components/business/business-context-provider";
import { useBusinessRefresh } from "@/components/business/business-refresh-provider";
import { Drawer } from "@/components/ui/drawer";
import { Badge } from "@/components/ui/badge";
import { SmartUpPageRefreshButton } from "@/components/smartup/page-refresh-button";
import { FilterBar } from "@/components/ui/filter-bar";
import { MultiSelect } from "@/components/ui/multi-select";
import { SearchInput } from "@/components/ui/search-input";
import { Select } from "@/components/ui/select";
import { Surface } from "@/components/ui/surface";
import {
  getSalesWorkspace,
  getSalesWorkspaceDetail,
  type AnalyticsDataStatus,
  type SalesWorkspaceDetail,
  type SalesWorkspaceFilters,
  type SalesWorkspaceRow,
  type SalesWorkspaceSortBy,
  type SalesWorkspaceSortOrder,
} from "@/lib/core-api";
import { cn } from "@/lib/cn";
import { formatMoneyValue, normalizeCurrencyLabel } from "@/lib/money";

const PAGE_SIZE = 25;

const SUMMARY_REGISTRY = [
  { key: "revenue", label: "Выручка" },
  { key: "orders", label: "Заказы" },
  { key: "realised_sales", label: "Реализованные продажи" },
  { key: "sold_units", label: "Продано единиц" },
  { key: "average_order", label: "Средний заказ" },
  { key: "unique_customers", label: "Клиенты" },
  { key: "payments_received", label: "Получено денег" },
  { key: "return_value", label: "Возвраты" },
] as const;

const SORT_OPTIONS: Array<{ value: SalesWorkspaceSortBy; label: string }> = [
  { value: "business_date", label: "Дата" },
  { value: "realised_amount", label: "Сумма реализации" },
  { value: "order_amount", label: "Сумма заказа" },
  { value: "sold_units", label: "Продано единиц" },
  { value: "customer", label: "Клиент" },
  { value: "organization", label: "Организация" },
  { value: "status", label: "Статус" },
];

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

function statusLabel(status: AnalyticsDataStatus) {
  switch (status) {
    case "AVAILABLE":
      return "Данные подтверждены";
    case "PARTIAL":
      return "Частичное покрытие";
    case "NO_VERIFIED_DATA":
      return "Нет подтверждённых данных";
    case "NO_DATA":
      return "Нет данных";
    case "UNRESOLVED":
      return "Есть неразрешённые связи";
    case "UNRESOLVED":
      return "Есть неразрешённые связи";
    default:
      return status;
  }
}

function qualityBadgeVariant(status: string) {
  if (status === "verified") return "accent" as const;
  if (status === "partial") return "soft" as const;
  if (status === "unresolved") return "neutral" as const;
  return "dark" as const;
}

function metricValueTone(status: AnalyticsDataStatus) {
  if (status === "AVAILABLE") return "text-[#f4f7fb]";
  if (status === "PARTIAL") return "text-[#f4f7fb]";
  return "text-slate-400";
}

function rowStatusTone(realised: boolean, status: string) {
  const normalized = status.toLowerCase();
  if (!realised) return "bg-[#3f3721] text-[#ffe781] border-[#5d4d1f]";
  if (normalized.includes("cancel")) return "bg-[#40272c] text-[#ffd3db] border-[#40272c]";
  if (normalized.includes("approved")) return "bg-[#244037] text-[#c7f4de] border-[#244037]";
  if (normalized.includes("new")) return "bg-[#343840] text-slate-300 border-[#3a3d43]";
  return "bg-[#343840] text-slate-200 border-[#3a3d43]";
}

function emptyStateMessage(
  rows: SalesWorkspaceRow[],
  selectedNames: string[],
  status: AnalyticsDataStatus,
) {
  if (rows.length > 0) return null;
  if (status === "NO_VERIFIED_DATA") {
    return selectedNames.length === 1 && selectedNames[0] === "Администрация"
      ? "Нет подтверждённых данных о реализованных продажах в текущем наборе данных."
      : "Нет подтверждённых продаж в выбранном срезе.";
  }
  return "По выбранному контексту данные не найдены.";
}

type QueryState = {
  search: string;
  status: string[];
  customer: string[];
  salesRep: string[];
  workingZone: string[];
  realised: "all" | "realised" | "not_realised";
  hasReturns: "all" | "yes" | "no";
  sortBy: SalesWorkspaceSortBy;
  sortOrder: SalesWorkspaceSortOrder;
  page: number;
};

function buildWorkspaceFilters(
  businessState: ReturnType<typeof useBusinessContext>["state"],
  query: QueryState,
): SalesWorkspaceFilters {
  return {
    organizationIds: businessState.selectedOrganizationIds,
    period: businessState.period.preset,
    dateFrom: businessState.period.dateFrom,
    dateTo: businessState.period.dateTo,
    search: query.search || null,
    status: query.status,
    customer: query.customer,
    salesRep: query.salesRep,
    workingZone: query.workingZone,
    realised:
      query.realised === "all" ? null : query.realised === "realised",
    hasReturns:
      query.hasReturns === "all" ? null : query.hasReturns === "yes",
    sortBy: query.sortBy,
    sortOrder: query.sortOrder,
    page: query.page,
    pageSize: PAGE_SIZE,
  };
}

export function SalesWorkspacePage() {
  const business = useBusinessContext();
  const { subscribe } = useBusinessRefresh();
  const selectedNames = useSelectedOrganizationNames();
  const [query, setQuery] = useState<QueryState>({
    search: "",
    status: [],
    customer: [],
    salesRep: [],
    workingZone: [],
    realised: "all",
    hasReturns: "all",
    sortBy: "business_date",
    sortOrder: "desc",
    page: 1,
  });
  const [data, setData] = useState<Awaited<ReturnType<typeof getSalesWorkspace>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedRow, setSelectedRow] = useState<SalesWorkspaceRow | null>(null);
  const [detail, setDetail] = useState<SalesWorkspaceDetail | null>(null);
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
    void getSalesWorkspace(filters)
      .then((response) => {
        if (!active) return;
        setData(response);
      })
      .catch((reason) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "Не удалось загрузить продажи.");
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
    void getSalesWorkspaceDetail(selectedRow.record_id, filters)
      .then((response) => {
        if (!active) return;
        setDetail(response);
      })
      .catch((reason) => {
        if (!active) return;
        setDetailError(reason instanceof Error ? reason.message : "Не удалось загрузить карточку заказа.");
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
    return SUMMARY_REGISTRY.map(({ key, label }) => {
      const metric = data.summary[key];
      return {
        key,
        label,
        metric,
      };
    });
  }, [data]);

  const emptyMessage = data
    ? emptyStateMessage(data.rows, selectedNames, data.summary.revenue.data_status)
    : null;

  return (
    <section className="space-y-5">
      <div className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Продажи</p>
            <h1 className="mt-2 text-[32px] font-semibold tracking-[-0.06em] text-[#f4f7fb]">
              Продажи и заказы
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
              Экран продаж по текущему бизнес-контексту: заказы, реализации, возвраты и платежи.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <SmartUpPageRefreshButton page="sales" onCompleted={() => setRefreshToken((value) => value + 1)} />
            <Badge variant="soft">{selectedNames.join(", ") || "Все организации"}</Badge>
            <Badge variant="soft">
              {data?.period.label ?? "Период загружается"}
            </Badge>
          </div>
        </div>
      </div>

      <div className="space-y-4">
        <Surface className="overflow-visible px-4 py-4 sm:px-5">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {summaryTiles.map(({ key, label, metric }) => (
              <div
                key={key}
                className="rounded-[22px] border border-[#3a3d43] bg-[#2E3137] px-4 py-4"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">{label}</p>
                  <Badge variant="soft">{statusLabel(metric.data_status)}</Badge>
                </div>
                <p className={cn("mt-4 text-3xl font-semibold tracking-[-0.05em]", metricValueTone(metric.data_status))}>
                  {metric.value == null ? "—" : formatMoneyValue(String(metric.value), metric.currency)}
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
          subtitle="Поиск, статусы и рабочие фильтры сохраняют бизнес-контекст."
          drawerLabel="Изменить фильтр"
          actions={
            <>
              <Badge variant="soft">{data?.pagination.total_items ?? 0} строк</Badge>
              <Badge variant="accent">{query.realised === "realised" ? "Реализованные" : "Все продажи"}</Badge>
            </>
          }
        >
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1.5fr)_repeat(4,minmax(180px,1fr))]">
            <SearchInput
              value={query.search}
              onChange={(event) =>
                setQuery((current) => ({
                    ...current,
                    search: event.target.value,
                    page: 1,
                  }))
                }
                placeholder="ID сделки, заказ, клиент, товар"
              />

              <Select
                label="Реализация"
                value={query.realised}
                options={[
                  { value: "all", label: "Все" },
                  { value: "realised", label: "Только реализованные" },
                  { value: "not_realised", label: "Без реализации" },
                ]}
                onChange={(value) =>
                  setQuery((current) => ({
                    ...current,
                    realised: value as QueryState["realised"],
                    page: 1,
                  }))
                }
                className="w-full min-w-0"
              />

              <Select
                label="Возвраты"
                value={query.hasReturns}
                options={[
                  { value: "all", label: "Все" },
                  { value: "yes", label: "Есть возвраты" },
                  { value: "no", label: "Без возвратов" },
                ]}
                onChange={(value) =>
                  setQuery((current) => ({
                    ...current,
                    hasReturns: value as QueryState["hasReturns"],
                    page: 1,
                  }))
                }
                className="w-full min-w-0"
              />

              <Select
                label="Сортировка"
                value={query.sortBy}
                options={SORT_OPTIONS}
                onChange={(value) =>
                  setQuery((current) => ({
                    ...current,
                    sortBy: value as SalesWorkspaceSortBy,
                  }))
                }
                className="w-full min-w-0"
              />

              <Select
                label="Порядок"
                value={query.sortOrder}
                options={[
                  { value: "desc", label: "Сначала новые" },
                  { value: "asc", label: "Сначала старые" },
                ]}
                onChange={(value) =>
                  setQuery((current) => ({
                    ...current,
                    sortOrder: value as SalesWorkspaceSortOrder,
                  }))
                }
                className="w-full min-w-0"
              />
            </div>

            <div className="grid gap-3 xl:grid-cols-4">
              <MultiSelect
                label="Статусы"
                value={query.status}
                options={data?.filters.statuses ?? []}
                onChange={(next) => setQuery((current) => ({ ...current, status: next, page: 1 }))}
                className="w-full min-w-0"
              />
              <MultiSelect
                label="Клиенты"
                value={query.customer}
                options={data?.filters.customers ?? []}
                onChange={(next) => setQuery((current) => ({ ...current, customer: next, page: 1 }))}
                className="w-full min-w-0"
              />
              <MultiSelect
                label="Менеджеры"
                value={query.salesRep}
                options={data?.filters.sales_reps ?? []}
                onChange={(next) => setQuery((current) => ({ ...current, salesRep: next, page: 1 }))}
                className="w-full min-w-0"
              />
              <MultiSelect
                label="Зоны"
                value={query.workingZone}
                options={data?.filters.working_zones ?? []}
                onChange={(next) => setQuery((current) => ({ ...current, workingZone: next, page: 1 }))}
                className="w-full min-w-0"
              />
            </div>
        </FilterBar>

        <Surface className="overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-[#3a3d43] px-5 py-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Таблица заказов</p>
              <h2 className="mt-1 text-xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                Заказы, реализации и подтверждённые строки
              </h2>
            </div>
            <Badge variant="soft">
              {data?.pagination.total_items ?? 0} строк
            </Badge>
          </div>

          {error ? (
            <div className="px-5 py-6 text-sm text-rose-600">{error}</div>
          ) : loading ? (
            <div className="px-5 py-6 text-sm text-slate-400">Загрузка продаж...</div>
          ) : emptyMessage ? (
            <div className="px-5 py-6 text-sm text-slate-400">{emptyMessage}</div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="min-w-[1560px] border-separate border-spacing-0 text-left text-sm">
                  <thead className="sticky top-0 z-10 bg-[#2E3137]">
                    <tr className="text-[11px] uppercase tracking-[0.18em] text-slate-400">
                      {[
                        "Заказ / deal",
                        "Дата",
                        "Организация",
                        "Клиент",
                        "Менеджер",
                        "Зона",
                        "Статус",
                        "Заказано",
                        "Продано",
                        "Возвращено",
                        "Сумма заказа",
                        "Сумма реализации",
                        "Платежи",
                        "Возвраты",
                        "Currency",
                        "Delivery",
                        "Modified",
                        "Качество",
                      ].map((column) => (
                        <th
                          key={column}
                          className="border-b border-[#3a3d43] px-4 py-3 font-medium"
                        >
                          {column}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data?.rows.map((row) => (
                      <tr
                        key={row.record_id}
                        className="cursor-pointer transition hover:bg-[#343840]/80"
                        onClick={() => {
                          setSelectedRow(row);
                          setDetail(null);
                        }}
                      >
                        <td className="border-b border-[#3a3d43] px-4 py-4 align-top">
                          <div className="space-y-1">
                            <p className="font-semibold text-[#f4f7fb]">
                              {row.order_number ?? row.sale_number ?? row.deal_id ?? "—"}
                            </p>
                            <div className="flex flex-wrap gap-2">
                              <Badge variant="soft">{row.row_kind === "order" ? "Заказ" : "Продажа"}</Badge>
                              <Badge variant={row.realised ? "accent" : "neutral"}>
                                {row.realised ? "Реализован" : "Без реализации"}
                              </Badge>
                            </div>
                          </div>
                        </td>
                        <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                          {formatDateTime(row.business_date)}
                        </td>
                        <td className="border-b border-[#3a3d43] px-4 py-4 text-[#f4f7fb]">
                          {row.organization_name}
                        </td>
                        <td className="border-b border-[#3a3d43] px-4 py-4">
                          <div className="space-y-1">
                            <p className="font-medium text-[#f4f7fb]">
                              {row.customer_name ?? "Не удалось определить клиента"}
                            </p>
                            <p className="text-xs text-slate-400">
                              {row.customer_code ?? row.customer_external_id ?? "—"}
                            </p>
                          </div>
                        </td>
                        <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                          {row.sales_rep_name ?? "—"}
                        </td>
                        <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                          {row.working_zone_name ?? "—"}
                        </td>
                        <td className="border-b border-[#3a3d43] px-4 py-4">
                          <span
                            className={cn(
                              "inline-flex rounded-full border px-3 py-1 text-xs font-medium",
                              rowStatusTone(row.realised, row.display_status),
                            )}
                          >
                            {row.display_status}
                          </span>
                        </td>
                        <td className="border-b border-[#3a3d43] px-4 py-4 text-[#f4f7fb]">
                          {row.ordered_units ?? "—"}
                        </td>
                        <td className="border-b border-[#3a3d43] px-4 py-4 text-[#f4f7fb]">
                          {row.sold_units ?? "—"}
                        </td>
                        <td className="border-b border-[#3a3d43] px-4 py-4 text-[#f4f7fb]">
                          {row.returned_units ?? "—"}
                        </td>
                        <td className="border-b border-[#3a3d43] px-4 py-4 font-medium text-[#f4f7fb]">
                          {row.order_amount ? formatMoneyValue(row.order_amount, row.currency_code) : "—"}
                        </td>
                        <td className="border-b border-[#3a3d43] px-4 py-4 font-medium text-[#f4f7fb]">
                          {row.realised_amount ? formatMoneyValue(row.realised_amount, row.currency_code) : "—"}
                        </td>
                        <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                          {row.linked_payment_amount
                            ? formatMoneyValue(row.linked_payment_amount, row.currency_code)
                            : "—"}
                        </td>
                        <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                          {row.return_value ? formatMoneyValue(row.return_value, row.currency_code) : "—"}
                        </td>
                        <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                          {normalizeCurrencyLabel(row.currency_code) ?? "—"}
                        </td>
                        <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                          {formatDateOnly(row.delivery_date)}
                        </td>
                        <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                          {formatDateTime(row.last_modified_at)}
                        </td>
                        <td className="border-b border-[#3a3d43] px-4 py-4">
                          <Badge variant={qualityBadgeVariant(row.data_quality_status)}>
                            {row.data_quality_status === "verified"
                              ? "Подтверждено"
                              : row.data_quality_status === "partial"
                                ? "Частично"
                                : row.data_quality_status === "unresolved"
                                  ? "Есть неразрешённые связи"
                                  : "Использовать с осторожностью"}
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
                      setQuery((current) => ({ ...current, page: Math.max(1, current.page - 1) }))
                    }
                    className="rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 py-2 text-sm text-slate-300 transition hover:border-[#4a4e56] hover:text-[#f4f7fb] disabled:cursor-not-allowed disabled:opacity-40"
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
                      setQuery((current) => ({ ...current, page: current.page + 1 }))
                    }
                    className="rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 py-2 text-sm text-slate-300 transition hover:border-[#4a4e56] hover:text-[#f4f7fb] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Далее
                  </button>
                </div>
              </div>
            </>
          )}
        </Surface>
      </div>

      <Drawer
        open={selectedRow !== null}
        onClose={() => {
          setSelectedRow(null);
          setDetail(null);
          setDetailError(null);
        }}
        title={selectedRow?.order_number ?? selectedRow?.sale_number ?? selectedRow?.deal_id ?? "Карточка заказа"}
        description={selectedRow ? `${selectedRow.organization_name} · ${selectedRow.customer_name ?? "Не удалось определить клиента"}` : undefined}
        badges={
          selectedRow ? (
            <>
              <Badge variant="soft">{selectedRow.row_kind === "order" ? "Заказ" : "Продажа"}</Badge>
              <Badge variant={selectedRow.realised ? "accent" : "neutral"}>
                {selectedRow.realised ? "Реализован" : "Без реализации"}
              </Badge>
              <Badge variant={qualityBadgeVariant(selectedRow.data_quality_status)}>
                {selectedRow.data_quality_status === "verified"
                  ? "Подтверждено"
                  : selectedRow.data_quality_status === "partial"
                    ? "Частично"
                    : selectedRow.data_quality_status === "unresolved"
                      ? "Есть неразрешённые связи"
                      : "Использовать с осторожностью"}
              </Badge>
            </>
          ) : null
        }
      >
        {detailError ? (
          <p className="text-sm text-rose-600">{detailError}</p>
        ) : detailLoading || !detail ? (
          <p className="text-sm text-slate-400">Загрузка карточки заказа...</p>
        ) : (
          <div className="space-y-6">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {[
                { label: "Сумма заказа", value: detail.row.order_amount ? formatMoneyValue(detail.row.order_amount, detail.row.currency_code) : "—" },
                { label: "Сумма реализации", value: detail.row.realised_amount ? formatMoneyValue(detail.row.realised_amount, detail.row.currency_code) : "—" },
                { label: "Payment received", value: detail.row.linked_payment_amount ? formatMoneyValue(detail.row.linked_payment_amount, detail.row.currency_code) : "—" },
                { label: "Return value", value: detail.row.return_value ? formatMoneyValue(detail.row.return_value, detail.row.currency_code) : "—" },
              ].map((item) => (
                <div key={item.label} className="rounded-[20px] border border-[#3a3d43] bg-[#2E3137] px-4 py-4">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">{item.label}</p>
                  <p className="mt-3 text-xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">{item.value}</p>
                </div>
              ))}
            </div>

            <Surface className="overflow-hidden">
              <div className="border-b border-[#3a3d43] px-5 py-4">
                <h3 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">Товарные строки</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-[980px] text-left text-sm">
                  <thead className="bg-[#343840] text-slate-400">
                    <tr>
                      {["Товар", "Код", "Заказано", "Продано", "Возвращено", "Цена за ед.", "Сумма", "НДС", "Маржа", "Склад", "Тип цены"].map((column) => (
                        <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">{column}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {detail.items.map((item) => (
                      <tr key={`${item.line_number}-${item.product_code ?? "line"}`} className="border-b border-[#3a3d43]">
                        <td className="px-4 py-3 font-medium text-[#f4f7fb]">{item.product_name ?? "Не удалось определить товар"}</td>
                        <td className="px-4 py-3 text-slate-300">{item.product_code ?? "—"}</td>
                        <td className="px-4 py-3 text-[#f4f7fb]">{item.ordered_quantity ?? "—"}</td>
                        <td className="px-4 py-3 text-[#f4f7fb]">{item.sold_quantity ?? "—"}</td>
                        <td className="px-4 py-3 text-[#f4f7fb]">{item.returned_quantity ?? "—"}</td>
                        <td className="px-4 py-3 text-slate-300">{item.unit_price ? formatMoneyValue(item.unit_price, item.currency_code) : "—"}</td>
                        <td className="px-4 py-3 text-[#f4f7fb]">{item.amount ? formatMoneyValue(item.amount, item.currency_code) : "—"}</td>
                        <td className="px-4 py-3 text-slate-300">{item.vat_amount ? formatMoneyValue(item.vat_amount, item.currency_code) : item.vat_percent ?? "—"}</td>
                        <td className="px-4 py-3 text-slate-300">{item.margin_amount ? formatMoneyValue(item.margin_amount, item.currency_code) : "—"}</td>
                        <td className="px-4 py-3 text-slate-300">{item.warehouse_name ?? item.warehouse_code ?? "—"}</td>
                        <td className="px-4 py-3 text-slate-300">{item.price_type_code ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Surface>

            <div className="grid gap-4 xl:grid-cols-2">
              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-5 py-4">
                  <h3 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">Связанные возвраты</h3>
                </div>
                <div className="max-h-[320px] overflow-y-auto px-5 py-4">
                  {detail.returns.length === 0 ? (
                    <p className="text-sm text-slate-400">Нет подтверждённой связи возвратов с этой записью.</p>
                  ) : (
                    <div className="space-y-3">
                      {detail.returns.map((item) => (
                        <div key={`${item.return_id}-${item.product_code ?? "return"}`} className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="font-medium text-[#f4f7fb]">{item.return_number ?? "Возврат"}</p>
                              <p className="mt-1 text-sm text-slate-400">{item.product_name ?? item.product_code ?? "Без строки товара"}</p>
                            </div>
                            <Badge variant={qualityBadgeVariant(item.data_quality_status)}>
                              {item.data_quality_status === "verified"
                                ? "Подтверждено"
                                : item.data_quality_status === "partial"
                                  ? "Частично"
                                  : item.data_quality_status === "unresolved"
                                    ? "Есть неразрешённые связи"
                                    : "Использовать с осторожностью"}
                            </Badge>
                          </div>
                          <div className="mt-3 flex flex-wrap gap-4 text-sm text-slate-300">
                            <span>Дата: {formatDateOnly(item.return_at)}</span>
                            <span>Кол-во: {item.returned_quantity ?? "—"}</span>
                            <span>Сумма: {item.amount ? formatMoneyValue(item.amount, item.currency_code) : "—"}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </Surface>

              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-5 py-4">
                  <h3 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">Детерминированные платежи</h3>
                </div>
                <div className="max-h-[320px] overflow-y-auto px-5 py-4">
                  {detail.payments.length === 0 ? (
                    <p className="text-sm text-slate-400">Точная аллокация платежей к этому заказу не подтверждена.</p>
                  ) : (
                    <div className="space-y-3">
                      {detail.payments.map((item) => (
                        <div key={item.payment_id} className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="font-medium text-[#f4f7fb]">{item.payment_number ?? "Платёж"}</p>
                              <p className="mt-1 text-sm text-slate-400">{item.normalized_payment_type ?? "Тип не определён"}</p>
                            </div>
                            <p className="font-semibold text-[#f4f7fb]">
                              {item.amount ? formatMoneyValue(item.amount, item.currency_code) : "—"}
                            </p>
                          </div>
                          <div className="mt-3 flex flex-wrap gap-4 text-sm text-slate-300">
                            <span>Дата: {formatDateOnly(item.paid_at)}</span>
                            <span>Связь: {item.allocation_type}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </Surface>
            </div>

            <Surface className="overflow-hidden">
              <div className="border-b border-[#3a3d43] px-5 py-4">
                <h3 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">Проверка данных</h3>
              </div>
              <div className="space-y-3 px-5 py-4">
                {detail.limitations.length === 0 ? (
                  <p className="text-sm text-slate-400">Ограничений не обнаружено.</p>
                ) : (
                  detail.limitations.map((item, index) => (
                    <div key={`${index}-${item}`} className="rounded-[18px] border border-[#3a3d43] bg-[#343840] px-4 py-3 text-sm text-slate-300">
                      {item}
                    </div>
                  ))
                )}
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">Точка подключения</p>
                    <p className="mt-2 break-all text-sm text-[#f4f7fb]">{detail.provenance.source_endpoint}</p>
                  </div>
                  <div className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">Внешний ID</p>
                    <p className="mt-2 break-all text-sm text-[#f4f7fb]">{detail.provenance.source_external_id}</p>
                  </div>
                  <div className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">Филиал запроса</p>
                    <p className="mt-2 text-sm text-[#f4f7fb]">{detail.provenance.request_filial_id ?? "—"}</p>
                  </div>
                  <div className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">Филиал ответа</p>
                    <p className="mt-2 text-sm text-[#f4f7fb]">{detail.provenance.response_filial_id ?? "—"}</p>
                  </div>
                </div>
              </div>
            </Surface>
          </div>
        )}
      </Drawer>
    </section>
  );
}
