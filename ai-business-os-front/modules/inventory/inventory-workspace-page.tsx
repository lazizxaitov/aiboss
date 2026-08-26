"use client";

import Link from "next/link";
import { startTransition, useEffect, useMemo, useState } from "react";

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
  getInventoryCurrentStockDetail,
  getInventoryWarehouseDetail,
  getInventoryWorkspace,
  type AnalyticsDataStatus,
  type InventoryWorkspaceCurrentStockDetail,
  type InventoryWorkspaceCurrentStockRow,
  type InventoryWorkspaceFilters,
  type InventoryWorkspaceResponse,
  type InventoryWorkspaceSortBy,
  type InventoryWorkspaceSortOrder,
  type InventoryWorkspaceStockStatus,
  type InventoryWorkspaceSupplierReturnRow,
  type InventoryWorkspaceView,
  type InventoryWorkspaceWarehouseDetail,
  type InventoryWorkspaceWarehouseRow,
} from "@/lib/core-api";
import { formatMoneyValue } from "@/lib/money";
import { INVENTORY_VIEWS } from "@/lib/workspace-view-config";

const PAGE_SIZE = 25;

type DetailState =
  | { kind: "current_stock"; row: InventoryWorkspaceCurrentStockRow }
  | { kind: "warehouse"; row: InventoryWorkspaceWarehouseRow }
  | null;

type QueryState = {
  view: InventoryWorkspaceView;
  search: string;
  warehouseId: string[];
  productId: string[];
  categoryId: string[];
  stockStatus: InventoryWorkspaceStockStatus[];
  hasStock: "all" | "yes" | "no";
  zeroStock: "all" | "yes" | "no";
  negativeStock: "all" | "yes" | "no";
  dataQuality: Array<"verified" | "partial" | "unresolved" | "unsafe">;
  sortBy: InventoryWorkspaceSortBy;
  sortOrder: InventoryWorkspaceSortOrder;
  page: number;
};

const VIEW_LABELS: Record<InventoryWorkspaceView, string> = {
  current_stock: "Текущий остаток",
  warehouses: "Склады",
  purchases: "Закупки",
  receipts: "Поступления",
  writeoffs: "Списания",
  movements: "Перемещения",
  stocktaking: "Инвентаризации",
  supplier_returns: "Возвраты поставщику",
};

const SORT_OPTIONS: Array<{ value: InventoryWorkspaceSortBy; label: string }> = [
  { value: "snapshot_date", label: "Дата снимка" },
  { value: "quantity", label: "Количество" },
  { value: "product_name", label: "Товар" },
  { value: "warehouse", label: "Склад" },
  { value: "organization", label: "Организация" },
  { value: "stock_status", label: "Статус остатка" },
  { value: "document_date", label: "Дата документа" },
  { value: "amount", label: "Сумма" },
];

const SUMMARY_REGISTRY = [
  { key: "current_stock_quantity", label: "Текущий остаток" },
  { key: "products_in_stock", label: "Товаров в наличии" },
  { key: "warehouses", label: "Складов" },
  { key: "zero_stock_products", label: "Нулевой остаток" },
  { key: "negative_stock_products", label: "Отрицательный остаток" },
  { key: "low_stock_signals", label: "Низкий остаток" },
  { key: "overstock_signals", label: "Избыточный остаток" },
  { key: "inventory_value", label: "Оценка остатка" },
] as const;

function normalizeTriState(value: QueryState["hasStock" | "zeroStock" | "negativeStock"]) {
  if (value === "all") return null;
  return value === "yes";
}

function buildWorkspaceFilters(
  businessState: ReturnType<typeof useBusinessContext>["state"],
  query: QueryState,
): InventoryWorkspaceFilters {
  return {
    organizationIds: businessState.selectedOrganizationIds,
    period: businessState.period.preset,
    dateFrom: businessState.period.dateFrom,
    dateTo: businessState.period.dateTo,
    view: query.view,
    search: query.search || null,
    warehouseId: query.warehouseId,
    productId: query.productId,
    categoryId: query.categoryId,
    stockStatus: query.stockStatus,
    hasStock: normalizeTriState(query.hasStock),
    zeroStock: normalizeTriState(query.zeroStock),
    negativeStock: normalizeTriState(query.negativeStock),
    dataQuality: query.dataQuality,
    sortBy: query.sortBy,
    sortOrder: query.sortOrder,
    page: query.page,
    pageSize: PAGE_SIZE,
  };
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

function metricTone(status: AnalyticsDataStatus) {
  return status === "AVAILABLE" || status === "PARTIAL"
    ? "text-[#f4f7fb]"
    : "text-slate-400";
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

function stockVariant(status: InventoryWorkspaceStockStatus) {
  if (status === "IN_STOCK") return "accent" as const;
  if (status === "LOW_STOCK") return "soft" as const;
  if (status === "OVERSTOCK") return "soft" as const;
  if (status === "OUT_OF_STOCK") return "dark" as const;
  return "neutral" as const;
}

function stockLabel(status: InventoryWorkspaceStockStatus) {
  switch (status) {
    case "IN_STOCK":
      return "В наличии";
    case "LOW_STOCK":
      return "Низкий остаток";
    case "OUT_OF_STOCK":
      return "Нет остатка";
    case "OVERSTOCK":
      return "Избыточный остаток";
    case "STOCKOUT_RISK":
      return "Риск дефицита";
    case "NEGATIVE_STOCK":
      return "Отрицательный остаток";
    default:
      return status;
  }
}

function capabilityVariant(status: string) {
  if (status === "AVAILABLE") return "accent" as const;
  if (status === "NO_DATA" || status === "NO_VERIFIED_DATA") return "neutral" as const;
  return "soft" as const;
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

function buildDocumentRows(data: InventoryWorkspaceResponse) {
  switch (data.active_view) {
    case "purchases":
      return data.rows.purchases;
    case "receipts":
      return data.rows.receipts;
    case "writeoffs":
      return data.rows.writeoffs;
    case "movements":
      return data.rows.movements;
    case "stocktaking":
      return data.rows.stocktaking;
    case "supplier_returns":
      return data.rows.supplier_returns;
    default:
      return [];
  }
}

function renderDocumentTable(data: InventoryWorkspaceResponse) {
  const rows = buildDocumentRows(data);

  if (rows.length === 0) {
    return <div className="px-5 py-6 text-sm text-slate-400">По выбранному контексту записи не найдены.</div>;
  }

  if (data.active_view === "purchases") {
    return (
      <div className="overflow-x-auto">
        <table className="min-w-[1280px] border-separate border-spacing-0 text-left text-sm">
          <thead className="sticky top-0 z-10 bg-[#2E3137]">
            <tr className="text-[11px] uppercase tracking-[0.18em] text-slate-400">
              {["Документ", "Дата", "Организация", "Склад", "Поставщик", "Количество", "Сумма", "Покрытие", "Качество"].map((column) => (
                <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.purchases.map((row) => (
              <tr key={row.purchase_id} className="border-b border-[#3a3d43]">
                <td className="px-4 py-4 font-medium text-[#f4f7fb]">{row.document_number ?? row.source_external_id}</td>
                <td className="px-4 py-4 text-slate-300">{formatDateOnly(row.document_date)}</td>
                <td className="px-4 py-4 text-[#f4f7fb]">{row.organization_name}</td>
                <td className="px-4 py-4 text-slate-300">{row.warehouse_name ?? row.warehouse_code ?? "—"}</td>
                <td className="px-4 py-4 text-slate-300">{row.supplier_code ?? row.supplier_external_id ?? "—"}</td>
                <td className="px-4 py-4 text-slate-300">{row.total_quantity ?? "—"}</td>
                <td className="px-4 py-4 font-medium text-[#f4f7fb]">{row.amount ? formatMoneyValue(row.amount, row.currency_code) : "—"}</td>
                <td className="px-4 py-4 text-slate-300">
                  Товар {row.product_linkage_coverage ?? "—"} · Склад {row.warehouse_linkage_coverage ?? "—"}
                </td>
                <td className="px-4 py-4">
                  <Badge variant={qualityVariant(row.data_quality_status)}>{qualityStatusLabel(row.data_quality_status)}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (data.active_view === "receipts") {
    return (
      <div className="overflow-x-auto">
        <table className="min-w-[1240px] border-separate border-spacing-0 text-left text-sm">
          <thead className="sticky top-0 z-10 bg-[#2E3137]">
            <tr className="text-[11px] uppercase tracking-[0.18em] text-slate-400">
              {["Документ", "Дата", "Организация", "Склад", "Поставщик", "Связь с закупкой", "Количество", "Сумма", "Качество"].map((column) => (
                <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.receipts.map((row) => (
              <tr key={row.receipt_id} className="border-b border-[#3a3d43]">
                <td className="px-4 py-4 font-medium text-[#f4f7fb]">{row.document_number ?? row.source_external_id}</td>
                <td className="px-4 py-4 text-slate-300">{formatDateOnly(row.document_date)}</td>
                <td className="px-4 py-4 text-[#f4f7fb]">{row.organization_name}</td>
                <td className="px-4 py-4 text-slate-300">{row.warehouse_name ?? row.warehouse_code ?? "—"}</td>
                <td className="px-4 py-4 text-slate-300">{row.supplier_code ?? row.supplier_external_id ?? "—"}</td>
                <td className="px-4 py-4 text-slate-300">{row.linked_purchase_external_id ?? "—"}</td>
                <td className="px-4 py-4 text-slate-300">{row.total_quantity ?? "—"}</td>
                <td className="px-4 py-4 font-medium text-[#f4f7fb]">{row.amount ? formatMoneyValue(row.amount, row.currency_code) : "—"}</td>
                <td className="px-4 py-4">
                  <Badge variant={qualityVariant(row.data_quality_status)}>{qualityStatusLabel(row.data_quality_status)}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (data.active_view === "writeoffs") {
    return (
      <div className="overflow-x-auto">
        <table className="min-w-[1120px] border-separate border-spacing-0 text-left text-sm">
          <thead className="sticky top-0 z-10 bg-[#2E3137]">
            <tr className="text-[11px] uppercase tracking-[0.18em] text-slate-400">
              {["Документ", "Дата", "Организация", "Склад", "Причина", "Количество", "Сумма", "Статус", "Качество"].map((column) => (
                <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.writeoffs.map((row) => (
              <tr key={row.writeoff_id} className="border-b border-[#3a3d43]">
                <td className="px-4 py-4 font-medium text-[#f4f7fb]">{row.document_number ?? row.source_external_id}</td>
                <td className="px-4 py-4 text-slate-300">{formatDateOnly(row.document_date)}</td>
                <td className="px-4 py-4 text-[#f4f7fb]">{row.organization_name}</td>
                <td className="px-4 py-4 text-slate-300">{row.warehouse_name ?? row.warehouse_code ?? "—"}</td>
                <td className="px-4 py-4 text-slate-300">{row.reason_code ?? "—"}</td>
                <td className="px-4 py-4 text-slate-300">{row.total_quantity ?? "—"}</td>
                <td className="px-4 py-4 font-medium text-[#f4f7fb]">{row.amount ? formatMoneyValue(row.amount, row.currency_code) : "—"}</td>
                <td className="px-4 py-4 text-slate-300">{row.status ?? "—"}</td>
                <td className="px-4 py-4">
                  <Badge variant={qualityVariant(row.data_quality_status)}>{qualityStatusLabel(row.data_quality_status)}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (data.active_view === "movements") {
    return (
      <div className="overflow-x-auto">
        <table className="min-w-[1360px] border-separate border-spacing-0 text-left text-sm">
          <thead className="sticky top-0 z-10 bg-[#2E3137]">
            <tr className="text-[11px] uppercase tracking-[0.18em] text-slate-400">
              {["Документ", "Дата", "Организация", "Источник", "Назначение", "Количество", "Сумма", "Тип", "Качество"].map((column) => (
                <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.movements.map((row) => (
              <tr key={row.movement_id} className="border-b border-[#3a3d43]">
                <td className="px-4 py-4 font-medium text-[#f4f7fb]">{row.document_number ?? row.source_external_id}</td>
                <td className="px-4 py-4 text-slate-300">{formatDateOnly(row.document_date)}</td>
                <td className="px-4 py-4 text-[#f4f7fb]">{row.organization_name}</td>
                <td className="px-4 py-4 text-slate-300">
                  {[row.source_organization_name, row.source_warehouse_name ?? row.source_warehouse_code].filter(Boolean).join(" · ") || "—"}
                </td>
                <td className="px-4 py-4 text-slate-300">
                  {[row.destination_organization_name, row.destination_warehouse_name ?? row.destination_warehouse_code].filter(Boolean).join(" · ") || "—"}
                </td>
                <td className="px-4 py-4 text-slate-300">{row.total_quantity ?? "—"}</td>
                <td className="px-4 py-4 font-medium text-[#f4f7fb]">{row.amount ? formatMoneyValue(row.amount, row.currency_code) : "—"}</td>
                <td className="px-4 py-4 text-slate-300">{row.movement_type}</td>
                <td className="px-4 py-4">
                  <Badge variant={qualityVariant(row.data_quality_status)}>{qualityStatusLabel(row.data_quality_status)}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (data.active_view === "stocktaking") {
    return (
      <div className="overflow-x-auto">
        <table className="min-w-[1000px] border-separate border-spacing-0 text-left text-sm">
          <thead className="sticky top-0 z-10 bg-[#2E3137]">
            <tr className="text-[11px] uppercase tracking-[0.18em] text-slate-400">
              {["Документ", "Дата", "Организация", "Склад", "Количество", "Качество"].map((column) => (
                <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.stocktaking.map((row) => (
              <tr key={row.stocktaking_id} className="border-b border-[#3a3d43]">
                <td className="px-4 py-4 font-medium text-[#f4f7fb]">{row.document_number ?? row.source_external_id}</td>
                <td className="px-4 py-4 text-slate-300">{formatDateOnly(row.document_date)}</td>
                <td className="px-4 py-4 text-[#f4f7fb]">{row.organization_name}</td>
                <td className="px-4 py-4 text-slate-300">{row.warehouse_name ?? row.warehouse_code ?? "—"}</td>
                <td className="px-4 py-4 text-slate-300">{row.total_quantity ?? "—"}</td>
                <td className="px-4 py-4">
                  <Badge variant={qualityVariant(row.data_quality_status)}>{qualityStatusLabel(row.data_quality_status)}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-[1180px] border-separate border-spacing-0 text-left text-sm">
        <thead className="sticky top-0 z-10 bg-[#2E3137]">
          <tr className="text-[11px] uppercase tracking-[0.18em] text-slate-400">
            {["Документ", "Дата", "Организация", "Склад", "Поставщик", "Причина", "Количество", "Сумма", "Качество"].map((column) => (
              <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.supplier_returns.map((row: InventoryWorkspaceSupplierReturnRow) => (
            <tr key={row.supplier_return_id} className="border-b border-[#3a3d43]">
              <td className="px-4 py-4 font-medium text-[#f4f7fb]">{row.document_number ?? row.source_external_id}</td>
              <td className="px-4 py-4 text-slate-300">{formatDateOnly(row.document_date)}</td>
              <td className="px-4 py-4 text-[#f4f7fb]">{row.organization_name}</td>
              <td className="px-4 py-4 text-slate-300">{row.warehouse_name ?? row.warehouse_code ?? "—"}</td>
              <td className="px-4 py-4 text-slate-300">{row.supplier_code ?? row.supplier_external_id ?? "—"}</td>
              <td className="px-4 py-4 text-slate-300">{row.reason_code ?? "—"}</td>
              <td className="px-4 py-4 text-slate-300">{row.total_quantity ?? "—"}</td>
              <td className="px-4 py-4 font-medium text-[#f4f7fb]">{row.amount ? formatMoneyValue(row.amount, row.currency_code) : "—"}</td>
              <td className="px-4 py-4">
                <Badge variant={qualityVariant(row.data_quality_status)}>{qualityStatusLabel(row.data_quality_status)}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function InventoryWorkspacePage() {
  const business = useBusinessContext();
  const { subscribe } = useBusinessRefresh();
  const selectedNames = useSelectedOrganizationNames();
  const [query, setQuery] = useState<QueryState>({
    view: "current_stock",
    search: "",
    warehouseId: [],
    productId: [],
    categoryId: [],
    stockStatus: [],
    hasStock: "all",
    zeroStock: "all",
    negativeStock: "all",
    dataQuality: [],
    sortBy: "snapshot_date",
    sortOrder: "desc",
    page: 1,
  });
  const [data, setData] = useState<InventoryWorkspaceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<DetailState>(null);
  const [stockDetail, setStockDetail] = useState<InventoryWorkspaceCurrentStockDetail | null>(null);
  const [warehouseDetail, setWarehouseDetail] = useState<InventoryWorkspaceWarehouseDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  const filters = useMemo(() => buildWorkspaceFilters(business.state, query), [business.state, query]);

  useEffect(() => subscribe(() => setRefreshToken((current) => current + 1)), [subscribe]);

  useEffect(() => {
    let active = true;
    startTransition(() => {
      setLoading(true);
    });
    void getInventoryWorkspace(filters)
      .then((response) => {
        if (!active) return;
        setData(response);
        setError(null);
      })
      .catch((reason) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "Не удалось загрузить раздел склада.");
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
    if (!selectedDetail) return;
    let active = true;
    startTransition(() => {
      setDetailLoading(true);
      setDetailError(null);
    });

    const detailRequest =
      selectedDetail.kind === "current_stock"
        ? getInventoryCurrentStockDetail(selectedDetail.row.inventory_balance_id, filters)
        : getInventoryWarehouseDetail(selectedDetail.row.warehouse_key, filters);

    void detailRequest
      .then((response) => {
        if (!active) return;
        if (selectedDetail.kind === "current_stock") {
          setStockDetail(response as InventoryWorkspaceCurrentStockDetail);
          setWarehouseDetail(null);
        } else {
          setWarehouseDetail(response as InventoryWorkspaceWarehouseDetail);
          setStockDetail(null);
        }
      })
      .catch((reason) => {
        if (!active) return;
        setDetailError(reason instanceof Error ? reason.message : "Не удалось загрузить детали.");
        setStockDetail(null);
        setWarehouseDetail(null);
      })
      .finally(() => {
        if (active) setDetailLoading(false);
      });

    return () => {
      active = false;
    };
  }, [selectedDetail, filters, refreshToken]);

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
            <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Inventory / Warehouse</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">Склад</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
              Канонический слой по остаткам, складам, закупкам, поступлениям, списаниям и движениям.
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
              <p className={cn("mt-4 text-3xl font-semibold tracking-[-0.05em]", metricTone(metric.data_status))}>
                {formatMetricValue(metric.value, metric.currency, metric.data_status)}
              </p>
              <p className="mt-2 min-h-[40px] text-sm leading-5 text-slate-400">{metric.note ?? "—"}</p>
            </div>
          ))}
        </div>
      </Surface>

      <Surface className="overflow-visible px-4 py-4 sm:px-5">
        <div className="flex flex-wrap gap-2">
          {INVENTORY_VIEWS.map((view) => {
            const tab = data?.tabs.find((item) => item.view === view.view);
            return (
            <button
              key={view.view}
              type="button"
              onClick={() => {
                setQuery((current) => ({
                  ...current,
                  view: view.view,
                  page: 1,
                  sortBy: view.view === "current_stock" || view.view === "warehouses" ? "snapshot_date" : "document_date",
                }));
              }}
              className={cn(
                "inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition",
                query.view === view.view
                  ? "border-slate-900 bg-slate-950 text-white"
                  : "border-[#3a3d43] bg-[#2E3137] text-slate-300 hover:border-[#4a4e56] hover:text-[#f4f7fb]",
              )}
            >
              <span>{view.label}</span>
              <Badge variant={query.view === view.view ? "dark" : capabilityVariant(tab?.status ?? "NO_DATA")}>
                {tab?.count ?? 0}
              </Badge>
            </button>
            );
          })}
        </div>
      </Surface>

      <FilterBar title="Фильтры" subtitle="Поиск, склад, категории, товары и статусы остатка.">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <SearchInput
              value={query.search}
              onChange={(event) => setQuery((current) => ({ ...current, search: event.target.value, page: 1 }))}
              placeholder="товар, код, склад, batch"
            />
            <Select
              label="Наличие"
              value={query.hasStock}
              options={[
                { value: "all", label: "Все" },
                { value: "yes", label: "Только с остатком" },
                { value: "no", label: "Без остатка" },
              ]}
              onChange={(value) =>
                setQuery((current) => ({ ...current, hasStock: value as QueryState["hasStock"], page: 1 }))
              }
            />
            <Select
              label="Нулевой остаток"
              value={query.zeroStock}
              options={[
                { value: "all", label: "Все" },
                { value: "yes", label: "Только нулевой" },
                { value: "no", label: "Исключить нулевой" },
              ]}
              onChange={(value) =>
                setQuery((current) => ({ ...current, zeroStock: value as QueryState["zeroStock"], page: 1 }))
              }
            />
            <Select
              label="Отрицательный остаток"
              value={query.negativeStock}
              options={[
                { value: "all", label: "Все" },
                { value: "yes", label: "Только отрицательный" },
                { value: "no", label: "Исключить отрицательный" },
              ]}
              onChange={(value) =>
                setQuery((current) => ({
                  ...current,
                  negativeStock: value as QueryState["negativeStock"],
                  page: 1,
                }))
              }
            />
            <Select
              label="Сортировка"
              value={query.sortBy}
              options={SORT_OPTIONS}
              onChange={(value) =>
                setQuery((current) => ({ ...current, sortBy: value as InventoryWorkspaceSortBy }))
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
                  sortOrder: value as InventoryWorkspaceSortOrder,
                }))
              }
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-2">
            <MultiSelect
              label="Склады"
              value={query.warehouseId}
              options={data?.filters.warehouses ?? []}
              onChange={(next) => setQuery((current) => ({ ...current, warehouseId: next, page: 1 }))}
            />
            <MultiSelect
              label="Статус остатка"
              value={query.stockStatus}
              options={data?.filters.stock_statuses ?? []}
              onChange={(next) =>
                setQuery((current) => ({
                  ...current,
                  stockStatus: next as InventoryWorkspaceStockStatus[],
                  page: 1,
                }))
              }
            />
            <MultiSelect
              label="Категории"
              value={query.categoryId}
              options={data?.filters.categories ?? []}
              onChange={(next) => setQuery((current) => ({ ...current, categoryId: next, page: 1 }))}
            />
            <MultiSelect
              label="Товары"
              value={query.productId}
              options={data?.filters.products ?? []}
              onChange={(next) => setQuery((current) => ({ ...current, productId: next, page: 1 }))}
            />
          </div>
        </div>
      </FilterBar>

      <Surface className="overflow-hidden">
        <div className="flex items-center justify-between gap-3 border-b border-[#3a3d43] px-5 py-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">{VIEW_LABELS[query.view]}</p>
            <h2 className="mt-1 text-xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
              {query.view === "current_stock"
                ? "Текущий остаток по товарам и складам"
                : query.view === "warehouses"
                  ? "Склады и состояние запасов"
                  : "Операционный список документов"}
            </h2>
          </div>
          <Badge variant="soft">{data?.pagination.total_items ?? 0} записей</Badge>
        </div>

        {error ? (
          <div className="px-5 py-6 text-sm text-rose-600">{error}</div>
        ) : loading ? (
          <div className="px-5 py-6 text-sm text-slate-400">Загрузка склада...</div>
        ) : !data ? (
          <div className="px-5 py-6 text-sm text-slate-400">Нет данных для выбранного контекста.</div>
        ) : query.view === "current_stock" ? (
          data.rows.current_stock.length === 0 ? (
            <div className="px-5 py-6 text-sm text-slate-400">Остатки не найдены.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-[1560px] border-separate border-spacing-0 text-left text-sm">
                <thead className="sticky top-0 z-10 bg-[#2E3137]">
                  <tr className="text-[11px] uppercase tracking-[0.18em] text-slate-400">
                    {["Товар", "Код", "Организация", "Склад", "Количество", "Доступно", "Резерв", "Оценка", "Снимок", "Скорость 30д", "Дней остатка", "Статус", "Качество"].map((column) => (
                      <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">{column}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.current_stock.map((row) => (
                    <tr
                      key={row.inventory_balance_id}
                      className="cursor-pointer border-b border-[#3a3d43] transition hover:bg-[#343840]/80"
                      onClick={() => {
                        setSelectedDetail({ kind: "current_stock", row });
                        setStockDetail(null);
                        setWarehouseDetail(null);
                      }}
                    >
                      <td className="px-4 py-4 align-top">
                        <div className="space-y-1">
                          <p className="font-semibold text-[#f4f7fb]">
                            {row.product_id ? (
                              <Link
                                href={`/products?entity_id=${encodeURIComponent(row.product_id)}`}
                                className="transition hover:text-[#f4f7fb]"
                                onClick={(event) => event.stopPropagation()}
                              >
                                {row.product_name}
                              </Link>
                            ) : (
                              row.product_name
                            )}
                          </p>
                          <p className="text-xs text-slate-400">
                            {[row.category_name, row.batch_number, row.inventory_kind].filter(Boolean).join(" · ") || "—"}
                          </p>
                        </div>
                      </td>
                      <td className="px-4 py-4 text-slate-300">{row.product_code ?? "—"}</td>
                      <td className="px-4 py-4 text-[#f4f7fb]">{row.organization_name}</td>
                      <td className="px-4 py-4 text-slate-300">{row.warehouse_name ?? row.warehouse_code ?? "—"}</td>
                      <td className="px-4 py-4 font-medium text-[#f4f7fb]">{row.quantity ?? "—"}</td>
                      <td className="px-4 py-4 text-slate-300">{row.available_quantity ?? "—"}</td>
                      <td className="px-4 py-4 text-slate-300">{row.reserved_quantity ?? "—"}</td>
                      <td className="px-4 py-4 text-slate-300">{row.valuation_amount ? formatMoneyValue(row.valuation_amount, row.currency_code) : "—"}</td>
                      <td className="px-4 py-4 text-slate-300">{formatDateOnly(row.snapshot_date)}</td>
                      <td className="px-4 py-4 text-slate-300">{row.sales_velocity_30d ?? "—"}</td>
                      <td className="px-4 py-4 text-slate-300">{row.days_of_stock ?? "—"}</td>
                      <td className="px-4 py-4">
                        <Badge variant={stockVariant(row.stock_status)}>{stockLabel(row.stock_status)}</Badge>
                      </td>
                      <td className="px-4 py-4">
                        <Badge variant={qualityVariant(row.data_quality_status)}>{qualityStatusLabel(row.data_quality_status)}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : query.view === "warehouses" ? (
          data.rows.warehouses.length === 0 ? (
            <div className="px-5 py-6 text-sm text-slate-400">Склады не найдены.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-[1300px] border-separate border-spacing-0 text-left text-sm">
                <thead className="sticky top-0 z-10 bg-[#2E3137]">
                  <tr className="text-[11px] uppercase tracking-[0.18em] text-slate-400">
                    {["Склад", "Организация", "Товаров", "Кол-во", "Последний снимок", "Низкий остаток", "Нет", "Избыток", "Минус", "Качество"].map((column) => (
                      <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">{column}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.warehouses.map((row) => (
                    <tr
                      key={row.warehouse_key}
                      className="cursor-pointer border-b border-[#3a3d43] transition hover:bg-[#343840]/80"
                      onClick={() => {
                        setSelectedDetail({ kind: "warehouse", row });
                        setStockDetail(null);
                        setWarehouseDetail(null);
                      }}
                    >
                      <td className="px-4 py-4 font-medium text-[#f4f7fb]">{row.warehouse_name ?? row.warehouse_code ?? "Без кода"}</td>
                      <td className="px-4 py-4 text-slate-300">{row.organization_name}</td>
                      <td className="px-4 py-4 text-slate-300">{row.products_count}</td>
                      <td className="px-4 py-4 font-medium text-[#f4f7fb]">{row.current_quantity ?? "—"}</td>
                      <td className="px-4 py-4 text-slate-300">{formatDateOnly(row.last_snapshot)}</td>
                      <td className="px-4 py-4 text-slate-300">{row.low_stock_count}</td>
                      <td className="px-4 py-4 text-slate-300">{row.out_of_stock_count}</td>
                      <td className="px-4 py-4 text-slate-300">{row.overstock_count}</td>
                      <td className="px-4 py-4 text-slate-300">{row.negative_stock_count}</td>
                      <td className="px-4 py-4">
                        <Badge variant={qualityVariant(row.data_quality_status)}>{qualityStatusLabel(row.data_quality_status)}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : (
          renderDocumentTable(data)
        )}

        {data ? (
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
            <p className="text-sm text-slate-400">
              Показано {data.pagination.total_items === 0 ? 0 : Math.min(data.rows[query.view].length, data.pagination.total_items)} из {data.pagination.total_items}
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={data.pagination.page <= 1}
                onClick={() => setQuery((current) => ({ ...current, page: Math.max(1, current.page - 1) }))}
                className="rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 py-2 text-sm text-slate-300 transition hover:border-[#4a4e56] hover:text-[#f4f7fb] disabled:cursor-not-allowed disabled:opacity-40"
              >
                Назад
              </button>
              <Badge variant="soft">{data.pagination.page} / {data.pagination.total_pages}</Badge>
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
        ) : null}
      </Surface>

      <Drawer
        open={selectedDetail !== null}
        onClose={() => {
          setSelectedDetail(null);
          setStockDetail(null);
          setWarehouseDetail(null);
          setDetailError(null);
        }}
        title={
          selectedDetail?.kind === "current_stock"
            ? selectedDetail.row.product_name
            : selectedDetail?.kind === "warehouse"
              ? selectedDetail.row.warehouse_name ?? selectedDetail.row.warehouse_code ?? "Склад"
              : "Детали"
        }
        description={
          selectedDetail?.kind === "current_stock"
            ? `${selectedDetail.row.organization_name} · ${selectedDetail.row.warehouse_name ?? selectedDetail.row.warehouse_code ?? "Без склада"}`
            : selectedDetail?.kind === "warehouse"
              ? selectedDetail.row.organization_name
              : undefined
        }
        badges={
          selectedDetail?.kind === "current_stock" ? (
            <>
              <Badge variant={stockVariant(selectedDetail.row.stock_status)}>{stockLabel(selectedDetail.row.stock_status)}</Badge>
              <Badge variant={qualityVariant(selectedDetail.row.data_quality_status)}>{qualityStatusLabel(selectedDetail.row.data_quality_status)}</Badge>
            </>
          ) : selectedDetail?.kind === "warehouse" ? (
            <Badge variant={qualityVariant(selectedDetail.row.data_quality_status)}>{qualityStatusLabel(selectedDetail.row.data_quality_status)}</Badge>
          ) : null
        }
        className="max-w-[min(48rem,100vw)]"
      >
        {detailError ? (
          <p className="text-sm text-rose-600">{detailError}</p>
        ) : detailLoading ? (
          <p className="text-sm text-slate-400">Загрузка деталей...</p>
        ) : selectedDetail?.kind === "current_stock" && stockDetail ? (
          <div className="space-y-5">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {[
                { label: "Текущее количество", value: stockDetail.row.quantity, currency: null },
                { label: "Доступно", value: stockDetail.row.available_quantity, currency: null },
                { label: "Резерв", value: stockDetail.row.reserved_quantity, currency: null },
                { label: "Оценка", value: stockDetail.row.valuation_amount, currency: stockDetail.row.currency_code },
              ].map((item) => (
                <div key={item.label} className="rounded-[20px] border border-[#3a3d43] bg-[#2E3137] px-4 py-4">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">{item.label}</p>
                  <p className="mt-3 text-xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                    {formatMetricValue(item.value, item.currency)}
                  </p>
                </div>
              ))}
            </div>

            <Surface className="overflow-hidden">
              <div className="border-b border-[#3a3d43] px-5 py-4">
                <h3 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">Последние снимки</h3>
              </div>
              <div className="max-h-[260px] overflow-y-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-[#343840] text-slate-400">
                    <tr>
                      {["Дата", "Количество", "Доступно", "Резерв", "Оценка"].map((column) => (
                        <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">{column}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {stockDetail.recent_snapshots.map((item) => (
                      <tr key={item.inventory_balance_id} className="border-b border-[#3a3d43]">
                        <td className="px-4 py-3 text-slate-300">{formatDateOnly(item.snapshot_date)}</td>
                        <td className="px-4 py-3 text-[#f4f7fb]">{item.quantity ?? "—"}</td>
                        <td className="px-4 py-3 text-slate-300">{item.available_quantity ?? "—"}</td>
                        <td className="px-4 py-3 text-slate-300">{item.reserved_quantity ?? "—"}</td>
                        <td className="px-4 py-3 text-slate-300">{item.valuation_amount ? formatMoneyValue(item.valuation_amount, item.currency_code) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Surface>

            <div className="grid gap-4 xl:grid-cols-3">
              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-5 py-4">
                  <h3 className="text-base font-semibold tracking-[-0.04em] text-[#f4f7fb]">Поступления</h3>
                </div>
                <div className="max-h-[240px] overflow-y-auto px-5 py-4 text-sm text-slate-300">
                  <div className="space-y-3">
                    {stockDetail.recent_receipts.length === 0 ? (
                      <p>Нет связанных поступлений.</p>
                    ) : (
                      stockDetail.recent_receipts.map((item) => (
                        <div key={item.receipt_id} className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                          <p className="font-medium text-[#f4f7fb]">{item.document_number ?? item.source_external_id}</p>
                          <p className="mt-1 text-sm text-slate-400">
                            {formatDateOnly(item.document_date)} · {item.total_quantity ?? "—"} · {item.amount ? formatMoneyValue(item.amount, item.currency_code) : "—"}
                          </p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </Surface>

              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-5 py-4">
                  <h3 className="text-base font-semibold tracking-[-0.04em] text-[#f4f7fb]">Списания</h3>
                </div>
                <div className="max-h-[240px] overflow-y-auto px-5 py-4 text-sm text-slate-300">
                  <div className="space-y-3">
                    {stockDetail.recent_writeoffs.length === 0 ? (
                      <p>Нет связанных списаний.</p>
                    ) : (
                      stockDetail.recent_writeoffs.map((item) => (
                        <div key={item.writeoff_id} className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                          <p className="font-medium text-[#f4f7fb]">{item.document_number ?? item.source_external_id}</p>
                          <p className="mt-1 text-sm text-slate-400">
                            {formatDateOnly(item.document_date)} · {item.total_quantity ?? "—"} · {item.amount ? formatMoneyValue(item.amount, item.currency_code) : "—"}
                          </p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </Surface>

              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-5 py-4">
                  <h3 className="text-base font-semibold tracking-[-0.04em] text-[#f4f7fb]">Перемещения</h3>
                </div>
                <div className="max-h-[240px] overflow-y-auto px-5 py-4 text-sm text-slate-300">
                  <div className="space-y-3">
                    {stockDetail.recent_movements.length === 0 ? (
                      <p>Нет связанных перемещений.</p>
                    ) : (
                      stockDetail.recent_movements.map((item) => (
                        <div key={item.movement_id} className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                          <p className="font-medium text-[#f4f7fb]">{item.document_number ?? item.source_external_id}</p>
                          <p className="mt-1 text-sm text-slate-400">
                            {formatDateOnly(item.document_date)} · {item.total_quantity ?? "—"} · {item.direction ?? item.movement_type}
                          </p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </Surface>
            </div>

            <Surface className="px-5 py-4">
              <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">Ограничения</p>
              <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                {stockDetail.limitations.length === 0 ? (
                  <li>Явных ограничений не обнаружено.</li>
                ) : (
                  stockDetail.limitations.map((item) => <li key={item}>• {item}</li>)
                )}
              </ul>
            </Surface>
          </div>
        ) : selectedDetail?.kind === "warehouse" && warehouseDetail ? (
          <div className="space-y-5">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {[
                { label: "Товаров", value: warehouseDetail.row.products_count, currency: null },
                { label: "Количество", value: warehouseDetail.row.current_quantity, currency: null },
                { label: "Низкий остаток", value: warehouseDetail.row.low_stock_count, currency: null },
                { label: "Нет в наличии", value: warehouseDetail.row.out_of_stock_count, currency: null },
              ].map((item) => (
                <div key={item.label} className="rounded-[20px] border border-[#3a3d43] bg-[#2E3137] px-4 py-4">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">{item.label}</p>
                  <p className="mt-3 text-xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                    {formatMetricValue(item.value, item.currency)}
                  </p>
                </div>
              ))}
            </div>

            <Surface className="overflow-hidden">
              <div className="border-b border-[#3a3d43] px-5 py-4">
                <h3 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">Текущий остаток по складу</h3>
              </div>
              <div className="max-h-[320px] overflow-y-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-[#343840] text-slate-400">
                    <tr>
                      {["Товар", "Количество", "Доступно", "Резерв", "Снимок", "Статус"].map((column) => (
                        <th key={column} className="border-b border-[#3a3d43] px-4 py-3 font-medium">{column}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {warehouseDetail.current_stock.map((item) => (
                      <tr key={item.inventory_balance_id} className="border-b border-[#3a3d43]">
                        <td className="px-4 py-3 font-medium text-[#f4f7fb]">{item.product_name}</td>
                        <td className="px-4 py-3 text-slate-300">{item.quantity ?? "—"}</td>
                        <td className="px-4 py-3 text-slate-300">{item.available_quantity ?? "—"}</td>
                        <td className="px-4 py-3 text-slate-300">{item.reserved_quantity ?? "—"}</td>
                        <td className="px-4 py-3 text-slate-300">{formatDateOnly(item.snapshot_date)}</td>
                        <td className="px-4 py-3">
                          <Badge variant={stockVariant(item.stock_status)}>{stockLabel(item.stock_status)}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Surface>

            <div className="grid gap-4 xl:grid-cols-2">
              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-5 py-4">
                  <h3 className="text-base font-semibold tracking-[-0.04em] text-[#f4f7fb]">Закупки и поступления</h3>
                </div>
                <div className="max-h-[280px] overflow-y-auto px-5 py-4">
                  <div className="space-y-3">
                    {[...warehouseDetail.purchases, ...warehouseDetail.receipts].length === 0 ? (
                      <p className="text-sm text-slate-400">Нет связанных документов.</p>
                    ) : (
                      [...warehouseDetail.purchases, ...warehouseDetail.receipts].map((item) => (
                        <div key={item.source_external_id} className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                          <p className="font-medium text-[#f4f7fb]">{item.document_number ?? item.source_external_id}</p>
                          <p className="mt-1 text-sm text-slate-400">
                            {formatDateOnly(item.document_date)} · {item.total_quantity ?? "—"} · {item.amount ? formatMoneyValue(item.amount, item.currency_code) : "—"}
                          </p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </Surface>

              <Surface className="overflow-hidden">
                <div className="border-b border-[#3a3d43] px-5 py-4">
                  <h3 className="text-base font-semibold tracking-[-0.04em] text-[#f4f7fb]">Списания и движения</h3>
                </div>
                <div className="max-h-[280px] overflow-y-auto px-5 py-4">
                  <div className="space-y-3">
                    {[...warehouseDetail.writeoffs, ...warehouseDetail.movements, ...warehouseDetail.stocktaking, ...warehouseDetail.supplier_returns].length === 0 ? (
                      <p className="text-sm text-slate-400">Нет связанных документов.</p>
                    ) : (
                      [...warehouseDetail.writeoffs, ...warehouseDetail.movements, ...warehouseDetail.stocktaking, ...warehouseDetail.supplier_returns].map((item) => (
                        <div key={item.source_external_id} className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                          <p className="font-medium text-[#f4f7fb]">{item.document_number ?? item.source_external_id}</p>
                          <p className="mt-1 text-sm text-slate-400">
                            {formatDateOnly(item.document_date)} · {"total_quantity" in item ? item.total_quantity ?? "—" : "—"} · {"amount" in item && item.amount ? formatMoneyValue(item.amount, item.currency_code) : "—"}
                          </p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </Surface>
            </div>

            <Surface className="px-5 py-4">
              <p className="text-[11px] uppercase tracking-[0.22em] text-slate-400">Ограничения</p>
              <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                {warehouseDetail.limitations.length === 0 ? (
                  <li>Явных ограничений не обнаружено.</li>
                ) : (
                  warehouseDetail.limitations.map((item) => <li key={item}>• {item}</li>)
                )}
              </ul>
            </Surface>
          </div>
        ) : (
          <p className="text-sm text-slate-400">Выберите строку для просмотра деталей.</p>
        )}
      </Drawer>
    </section>
  );
}
