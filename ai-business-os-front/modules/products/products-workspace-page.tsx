"use client";

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
  getProductWorkspace,
  getProductWorkspaceDetail,
  type AnalyticsDataStatus,
  type ProductWorkspaceDetail,
  type ProductWorkspaceFilters,
  type ProductWorkspaceRow,
  type ProductWorkspaceSortBy,
  type ProductWorkspaceSortOrder,
  type ProductWorkspaceStockStatus,
} from "@/lib/core-api";
import { formatMoneyValue } from "@/lib/money";

const PAGE_SIZE = 25;

const SUMMARY_REGISTRY = [
  { key: "products", label: "Товаров" },
  { key: "products_sold", label: "Продавалось" },
  { key: "sold_units", label: "Продано единиц" },
  { key: "revenue", label: "Выручка" },
  { key: "average_selling_price", label: "Средняя цена" },
  { key: "current_stock", label: "Текущий остаток" },
  { key: "out_of_stock", label: "Нет в наличии" },
  { key: "low_stock", label: "Низкий остаток" },
  { key: "overstock", label: "Избыточный остаток" },
  { key: "return_quantity", label: "Возвращено ед." },
  { key: "return_value", label: "Сумма возвратов" },
] as const;

const SORT_OPTIONS: Array<{ value: ProductWorkspaceSortBy; label: string }> = [
  { value: "revenue", label: "Выручка" },
  { value: "sold_units", label: "Продано единиц" },
  { value: "orders", label: "Заказы" },
  { value: "customers", label: "Клиенты" },
  { value: "current_stock", label: "Текущий остаток" },
  { value: "last_sale", label: "Последняя продажа" },
  { value: "return_quantity", label: "Возвраты" },
  { value: "product_name", label: "Товар" },
] as const;

type QueryState = {
  search: string;
  categoryIds: string[];
  stockStatus: ProductWorkspaceStockStatus[];
  hasSales: "all" | "yes" | "no";
  hasReturns: "all" | "yes" | "no";
  dataQuality: Array<"verified" | "partial" | "unresolved" | "unsafe">;
  sortBy: ProductWorkspaceSortBy;
  sortOrder: ProductWorkspaceSortOrder;
  page: number;
};

function normalizeBooleanFilter(value: QueryState["hasSales" | "hasReturns"]) {
  if (value === "all") return null;
  return value === "yes";
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
      return "Подтверждено";
    case "PARTIAL":
      return "Частично";
    case "NO_DATA":
      return "Нет данных";
    case "NO_VERIFIED_DATA":
      return "Нет подтверждённых данных";
    case "UNRESOLVED":
      return "Есть неразрешённые связи";
    case "NOT_AVAILABLE":
      return "Недоступно";
    default:
      return status;
  }
}

function qualityBadgeVariant(status: ProductWorkspaceRow["data_quality_status"]) {
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

function stockBadgeVariant(status: ProductWorkspaceStockStatus | null) {
  if (status === "IN_STOCK") return "accent" as const;
  if (status === "LOW_STOCK") return "soft" as const;
  if (status === "OUT_OF_STOCK") return "dark" as const;
  return "neutral" as const;
}

function stockStatusLabel(status: ProductWorkspaceStockStatus | null) {
  switch (status) {
    case "IN_STOCK":
      return "В наличии";
    case "LOW_STOCK":
      return "Низкий остаток";
    case "OUT_OF_STOCK":
      return "Нет остатка";
    case "OVERSTOCK":
      return "Избыток";
    default:
      return "—";
  }
}

function metricValueTone(status: AnalyticsDataStatus) {
  if (status === "AVAILABLE") return "text-[#f4f7fb]";
  if (status === "PARTIAL") return "text-[#f4f7fb]";
  return "text-slate-400";
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
): ProductWorkspaceFilters {
  return {
    organizationIds: businessState.selectedOrganizationIds,
    period: businessState.period.preset,
    dateFrom: businessState.period.dateFrom,
    dateTo: businessState.period.dateTo,
    search: query.search || null,
    categoryIds: query.categoryIds,
    stockStatus: query.stockStatus,
    hasSales: normalizeBooleanFilter(query.hasSales),
    hasReturns: normalizeBooleanFilter(query.hasReturns),
    dataQuality: query.dataQuality,
    sortBy: query.sortBy,
    sortOrder: query.sortOrder,
    page: query.page,
    pageSize: PAGE_SIZE,
  };
}

export function ProductsWorkspacePage() {
  const business = useBusinessContext();
  const { subscribe } = useBusinessRefresh();
  const selectedNames = useSelectedOrganizationNames();
  const [query, setQuery] = useState<QueryState>({
    search: "",
    categoryIds: [],
    stockStatus: [],
    hasSales: "all",
    hasReturns: "all",
    dataQuality: [],
    sortBy: "revenue",
    sortOrder: "desc",
    page: 1,
  });
  const [data, setData] = useState<Awaited<ReturnType<typeof getProductWorkspace>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedRow, setSelectedRow] = useState<ProductWorkspaceRow | null>(null);
  const [detail, setDetail] = useState<ProductWorkspaceDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  const filters = useMemo(() => buildWorkspaceFilters(business.state, query), [business.state, query]);

  useEffect(() => subscribe(() => setRefreshToken((current) => current + 1)), [subscribe]);

  useEffect(() => {
    let active = true;
    void getProductWorkspace(filters)
      .then((response) => {
        if (!active) return;
        setData(response);
        setError(null);
      })
      .catch((reason) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "Не удалось загрузить товары.");
        setData(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [filters, refreshToken]);

  useEffect(() => {
    if (!selectedRow) return;
    let active = true;
    void getProductWorkspaceDetail(selectedRow.product_id, filters)
      .then((response) => {
        if (!active) return;
        setDetail(response);
        setDetailError(null);
      })
      .catch((reason) => {
        if (!active) return;
        setDetailError(reason instanceof Error ? reason.message : "Не удалось загрузить карточку товара.");
        setDetail(null);
      })
      .finally(() => {
        if (active) setDetailLoading(false);
      });
    return () => {
      active = false;
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
            <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Товары</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">Товары</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
              Единое окно по товарам, продажам, остаткам, возвратам и ценам.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
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

      <FilterBar title="Фильтры" subtitle="Поиск, продажи, возвраты, категории и статус остатка.">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <SearchInput
              value={query.search}
              onChange={(event) =>
                setQuery((current) => ({ ...current, search: event.target.value, page: 1 }))
              }
              placeholder="название, код, article, barcode"
            />
            <Select
              label="Продажи"
              value={query.hasSales}
              options={[
                { value: "all", label: "Все" },
                { value: "yes", label: "Только с продажами" },
                { value: "no", label: "Без продаж" },
              ]}
              onChange={(value) =>
                setQuery((current) => ({
                  ...current,
                  hasSales: value as QueryState["hasSales"],
                  page: 1,
                }))
              }
            />
            <Select
              label="Возвраты"
              value={query.hasReturns}
              options={[
                { value: "all", label: "Все" },
                { value: "yes", label: "Только с возвратами" },
                { value: "no", label: "Без возвратов" },
              ]}
              onChange={(value) =>
                setQuery((current) => ({
                  ...current,
                  hasReturns: value as QueryState["hasReturns"],
                  page: 1,
                }))
              }
            />
            <Select
              label="Сортировка"
              value={query.sortBy}
              options={SORT_OPTIONS}
              onChange={(value) =>
                setQuery((current) => ({
                  ...current,
                  sortBy: value as ProductWorkspaceSortBy,
                }))
              }
            />
            <Select
              label="Порядок"
              value={query.sortOrder}
              options={[
                { value: "desc", label: "Сначала больше" },
                { value: "asc", label: "Сначала меньше" },
              ]}
              onChange={(value) =>
                setQuery((current) => ({
                  ...current,
                  sortOrder: value as ProductWorkspaceSortOrder,
                }))
              }
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-2">
            <MultiSelect
              label="Категории"
              value={query.categoryIds}
              options={data?.filters.categories ?? []}
              onChange={(next) => setQuery((current) => ({ ...current, categoryIds: next, page: 1 }))}
            />
            <MultiSelect
              label="Статус остатка"
              value={query.stockStatus}
              options={data?.filters.stock_statuses ?? []}
              onChange={(next) =>
                setQuery((current) => ({
                  ...current,
                  stockStatus: next as ProductWorkspaceStockStatus[],
                  page: 1,
                }))
              }
            />
          </div>
        </div>
      </FilterBar>

      <Surface className="overflow-hidden">
        <div className="flex items-center justify-between gap-3 border-b border-[#3a3d43] px-5 py-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Товары</p>
            <h2 className="mt-1 text-xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
              Продажи, остатки и возвраты по товарам
            </h2>
          </div>
          <Badge variant="soft">{data?.pagination.total_items ?? 0} товаров</Badge>
        </div>

        {error ? (
          <div className="px-5 py-6 text-sm text-rose-600">{error}</div>
        ) : loading ? (
          <div className="px-5 py-6 text-sm text-slate-400">Загрузка товаров...</div>
        ) : !data || data.rows.length === 0 ? (
          <div className="px-5 py-6 text-sm text-slate-400">По выбранному контексту товары не найдены.</div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-[1520px] border-separate border-spacing-0 text-left text-sm">
                <thead className="sticky top-0 z-10 bg-[#2E3137]">
                  <tr className="text-[11px] uppercase tracking-[0.18em] text-slate-400">
                    {[
                      "Товар",
                      "Код",
                      "Категория",
                      "Организации",
                      "Продано",
                      "Выручка",
                      "Заказы",
                      "Клиенты",
                      "Средняя цена",
                      "Текущий остаток",
                      "Последняя продажа",
                      "Возвраты",
                      "Сумма возвратов",
                      "Stock status",
                      "Качество",
                    ].map((column) => (
                      <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr
                      key={row.product_id}
                      className="cursor-pointer transition hover:bg-[#343840]/80"
                      onClick={() => {
                        setSelectedRow(row);
                        setDetail(null);
                        setDetailLoading(true);
                      }}
                    >
                      <td className="border-b border-[#3a3d43] px-4 py-4 align-top">
                        <div className="space-y-1">
                          <p className="font-semibold text-[#f4f7fb]">{row.product_name}</p>
                          <p className="text-xs text-slate-400">
                            {[row.article_code, ...row.barcodes.slice(0, 2)].filter(Boolean).join(" · ") || "—"}
                          </p>
                        </div>
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {row.product_code ?? "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {row.category_name ?? "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {row.organization_names.join(", ") || "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 font-medium text-[#f4f7fb]">
                        {row.sold_units ?? "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 font-medium text-[#f4f7fb]">
                        {row.revenue ? formatMoneyValue(row.revenue, "UZS") : "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {row.orders_count ?? "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {row.customers_count ?? "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {row.average_selling_price ? formatMoneyValue(row.average_selling_price, "UZS") : "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {row.current_stock ?? "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {formatDateTime(row.last_sale)}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {row.return_quantity ?? "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4 text-slate-300">
                        {row.return_value ? formatMoneyValue(row.return_value, "UZS") : "—"}
                      </td>
                      <td className="border-b border-[#3a3d43] px-4 py-4">
                        <Badge variant={stockBadgeVariant(row.stock_status)}>
                          {stockStatusLabel(row.stock_status)}
                        </Badge>
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
                Показано {data.rows.length} из {data.pagination.total_items}
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={data.pagination.page <= 1}
                  onClick={() =>
                    setQuery((current) => ({ ...current, page: Math.max(1, current.page - 1) }))
                  }
                  className="rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 py-2 text-sm text-slate-300 transition hover:border-[#4a4e56] hover:text-[#f4f7fb] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Назад
                </button>
                <Badge variant="soft">
                  {data.pagination.page} / {data.pagination.total_pages}
                </Badge>
                <button
                  type="button"
                  disabled={data.pagination.page >= data.pagination.total_pages}
                  onClick={() => setQuery((current) => ({ ...current, page: current.page + 1 }))}
                  className="rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 py-2 text-sm text-slate-300 transition hover:border-[#4a4e56] hover:text-[#f4f7fb] disabled:cursor-not-allowed disabled:opacity-40"
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
        title={selectedRow?.product_name ?? "Карточка товара"}
        description={selectedRow ? `${selectedRow.product_code ?? "Без кода"} · ${selectedRow.category_name ?? "Без категории"}` : undefined}
        badges={
          selectedRow ? (
            <>
              <Badge variant={stockBadgeVariant(selectedRow.stock_status)}>
                {stockStatusLabel(selectedRow.stock_status)}
              </Badge>
              <Badge variant={qualityBadgeVariant(selectedRow.data_quality_status)}>
                {qualityStatusLabel(selectedRow.data_quality_status)}
              </Badge>
            </>
          ) : null
        }
        className="max-w-[min(48rem,100vw)]"
      >
        {detailError ? (
          <p className="text-sm text-rose-600">{detailError}</p>
        ) : detailLoading || !detail ? (
          <p className="text-sm text-slate-400">Загрузка карточки товара...</p>
        ) : (
          <div className="space-y-6">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {[
                { label: "Выручка", value: detail.overview.revenue.value, currency: detail.overview.revenue.currency },
                { label: "Продано единиц", value: detail.overview.sold_units.value, currency: null },
                { label: "Средняя цена", value: detail.overview.average_selling_price.value, currency: detail.overview.average_selling_price.currency },
                { label: "Текущий остаток", value: detail.overview.current_stock.value, currency: null },
              ].map((item) => (
                <div key={item.label} className="rounded-[20px] border border-[#3a3d43] bg-[#2E3137] px-4 py-4">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">{item.label}</p>
                  <p className="mt-3 text-xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                    {formatMetricValue(item.value, item.currency)}
                  </p>
                </div>
              ))}
            </div>

            {detail.ai_summary ? (
              <Surface className="px-5 py-4">
                <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Сводка AI</p>
                <p className="mt-2 text-sm leading-6 text-slate-200">{detail.ai_summary}</p>
              </Surface>
            ) : null}

            <div className="grid gap-4 xl:grid-cols-2">
              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-5 py-4">
                  <h3 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">Продажи</h3>
                </div>
                <div className="max-h-[320px] overflow-y-auto">
                  <table className="min-w-full text-left text-sm">
                    <thead className="bg-[#343840] text-slate-400">
                      <tr>
                        {["Дата", "Организация", "Сделка", "Клиент", "Количество", "Цена", "Сумма"].map((column) => (
                          <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">{column}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {detail.sales.map((item) => (
                        <tr key={item.sale_item_id} className="border-b border-[#3a3d43]">
                          <td className="px-4 py-3 text-slate-300">{formatDateTime(item.business_date)}</td>
                          <td className="px-4 py-3 text-[#f4f7fb]">{item.organization_name}</td>
                          <td className="px-4 py-3 font-medium text-[#f4f7fb]">{item.order_number ?? item.sale_number ?? item.deal_id ?? "—"}</td>
                          <td className="px-4 py-3 text-slate-300">{item.customer_name ?? "—"}</td>
                          <td className="px-4 py-3 text-slate-300">{item.sold_quantity ?? "—"}</td>
                          <td className="px-4 py-3 text-slate-300">{item.unit_price ? formatMoneyValue(item.unit_price, item.currency_code) : "—"}</td>
                          <td className="px-4 py-3 font-medium text-[#f4f7fb]">{item.amount ? formatMoneyValue(item.amount, item.currency_code) : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Surface>

              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-5 py-4">
                  <h3 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">По организациям</h3>
                </div>
                <div className="max-h-[320px] overflow-y-auto px-5 py-4">
                  <div className="space-y-3">
                    {detail.organizations.map((item) => (
                      <div key={item.organization_id} className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="font-medium text-[#f4f7fb]">{item.organization_name}</p>
                            <p className="mt-1 text-sm text-slate-400">
                              Выручка {item.revenue ? formatMoneyValue(item.revenue, "UZS") : "—"} · Продано {item.sold_units ?? "—"} · Остаток {item.current_stock ?? "—"}
                            </p>
                          </div>
                          <Badge variant={stockBadgeVariant(item.stock_status)}>
                            {stockStatusLabel(item.stock_status)}
                          </Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </Surface>

              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-5 py-4">
                  <h3 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">Клиенты</h3>
                </div>
                <div className="max-h-[320px] overflow-y-auto">
                  <table className="min-w-full text-left text-sm">
                    <thead className="bg-[#343840] text-slate-400">
                      <tr>
                        {["Клиент", "Организация", "Количество", "Выручка", "Заказы", "Последняя покупка"].map((column) => (
                          <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">{column}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {detail.customers.map((item) => (
                        <tr key={item.customer_id} className="border-b border-[#3a3d43]">
                          <td className="px-4 py-3 font-medium text-[#f4f7fb]">{item.customer_name}</td>
                          <td className="px-4 py-3 text-slate-300">{item.organization_name}</td>
                          <td className="px-4 py-3 text-slate-300">{item.sold_units ?? "—"}</td>
                          <td className="px-4 py-3 text-[#f4f7fb]">{item.revenue ? formatMoneyValue(item.revenue, "UZS") : "—"}</td>
                          <td className="px-4 py-3 text-slate-300">{item.orders_count ?? "—"}</td>
                          <td className="px-4 py-3 text-slate-300">{formatDateTime(item.last_purchase)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Surface>

              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-5 py-4">
                  <h3 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">Текущий склад</h3>
                </div>
                <div className="max-h-[320px] overflow-y-auto">
                  <table className="min-w-full text-left text-sm">
                    <thead className="bg-[#343840] text-slate-400">
                      <tr>
                        {["Организация", "Склад", "Кол-во", "Доступно", "Резерв", "Дата снимка"].map((column) => (
                          <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">{column}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {detail.inventory.map((item) => (
                        <tr key={item.inventory_balance_id} className="border-b border-[#3a3d43]">
                          <td className="px-4 py-3 text-[#f4f7fb]">{item.organization_name}</td>
                          <td className="px-4 py-3 text-slate-300">{item.warehouse_name ?? item.warehouse_code ?? "—"}</td>
                          <td className="px-4 py-3 text-slate-300">{item.quantity ?? "—"}</td>
                          <td className="px-4 py-3 text-slate-300">{item.available_quantity ?? "—"}</td>
                          <td className="px-4 py-3 text-slate-300">{item.reserved_quantity ?? "—"}</td>
                          <td className="px-4 py-3 text-slate-300">{formatDateOnly(item.snapshot_date)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Surface>
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-5 py-4">
                  <h3 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">Цены</h3>
                </div>
                <div className="max-h-[280px] overflow-y-auto">
                  <table className="min-w-full text-left text-sm">
                    <thead className="bg-[#343840] text-slate-400">
                      <tr>
                        {["Источник", "Организация", "Тип", "Цена", "Дата", "Комментарий"].map((column) => (
                          <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">{column}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {detail.prices.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="px-4 py-4 text-slate-400">
                            Нет подтверждённой прайс-лист цены. Показываются только наблюдаемые transaction sale prices, если они появятся.
                          </td>
                        </tr>
                      ) : (
                        detail.prices.map((item, index) => (
                          <tr key={`${item.source_type}-${item.organization_id}-${item.effective_date ?? index}`} className="border-b border-[#3a3d43]">
                            <td className="px-4 py-3 text-slate-300">{item.source_type}</td>
                            <td className="px-4 py-3 text-[#f4f7fb]">{item.organization_name}</td>
                            <td className="px-4 py-3 text-slate-300">{item.price_type_name ?? item.price_type_code ?? "—"}</td>
                            <td className="px-4 py-3 text-[#f4f7fb]">{item.price ? formatMoneyValue(item.price, item.currency_code) : "—"}</td>
                            <td className="px-4 py-3 text-slate-300">{formatDateTime(item.effective_date)}</td>
                            <td className="px-4 py-3 text-slate-300">{item.note ?? "—"}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </Surface>

              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-5 py-4">
                  <h3 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">Возвраты</h3>
                </div>
                <div className="max-h-[280px] overflow-y-auto">
                  <table className="min-w-full text-left text-sm">
                    <thead className="bg-[#343840] text-slate-400">
                      <tr>
                        {["Дата", "Организация", "Документ", "Клиент", "Количество", "Сумма"].map((column) => (
                          <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">{column}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {detail.returns.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="px-4 py-4 text-slate-400">Возвраты по товару не найдены.</td>
                        </tr>
                      ) : (
                        detail.returns.map((item) => (
                          <tr key={item.return_item_id} className="border-b border-[#3a3d43]">
                            <td className="px-4 py-3 text-slate-300">{formatDateTime(item.return_at)}</td>
                            <td className="px-4 py-3 text-[#f4f7fb]">{item.organization_name}</td>
                            <td className="px-4 py-3 font-medium text-[#f4f7fb]">{item.return_number ?? "Возврат"}</td>
                            <td className="px-4 py-3 text-slate-300">{item.customer_name ?? "—"}</td>
                            <td className="px-4 py-3 text-slate-300">{item.returned_quantity ?? "—"}</td>
                            <td className="px-4 py-3 text-[#f4f7fb]">{item.amount ? formatMoneyValue(item.amount, item.currency_code) : "—"}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </Surface>
            </div>

            <Surface className="overflow-hidden">
              <div className="border-b border-[#3a3d43] px-5 py-4">
                <h3 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">Timeline и ограничения</h3>
              </div>
              <div className="grid gap-4 px-5 py-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
                <div className="max-h-[340px] overflow-y-auto">
                  <div className="space-y-3">
                    {detail.timeline.map((item) => (
                      <div key={item.event_id} className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="font-medium text-[#f4f7fb]">{item.title}</p>
                            <p className="mt-1 text-sm text-slate-400">
                              {item.organization_name ?? "—"} · {formatDateTime(item.happened_at)}
                            </p>
                          </div>
                          <Badge variant="soft">{item.event_type}</Badge>
                        </div>
                        <p className="mt-3 text-sm text-slate-300">
                          {[item.description, item.quantity ? `Количество ${item.quantity}` : null, item.amount ? formatMoneyValue(item.amount, item.currency_code) : null]
                            .filter(Boolean)
                            .join(" · ") || "—"}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="space-y-4">
                  <div className="rounded-[20px] border border-[#3a3d43] bg-[#2E3137] px-4 py-4">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">Качество данных</p>
                    <p className="mt-3 text-sm leading-6 text-slate-200">
                      {qualityStatusLabel(detail.provenance.data_quality_status)}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-slate-400">
                      Источник: {detail.provenance.source_endpoint}
                    </p>
                    <p className="mt-1 text-sm leading-6 text-slate-400">
                      External ID: {detail.provenance.source_external_id}
                    </p>
                  </div>
                  <div className="rounded-[20px] border border-[#3a3d43] bg-[#2E3137] px-4 py-4">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">Ограничения</p>
                    <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                      {detail.limitations.length === 0 ? (
                        <li>Явных source limitations для текущего товара не найдено.</li>
                      ) : (
                        detail.limitations.map((item) => <li key={item}>• {item}</li>)
                      )}
                    </ul>
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
