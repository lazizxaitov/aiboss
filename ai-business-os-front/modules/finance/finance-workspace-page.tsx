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
  getFinanceWorkspace,
  type AnalyticsDataStatus,
  type FinanceWorkspaceAccountRow,
  type FinanceWorkspaceCoverageItem,
  type FinanceWorkspaceDirection,
  type FinanceWorkspaceFilters,
  type FinanceWorkspaceOperationRow,
  type FinanceWorkspaceOverviewRow,
  type FinanceWorkspacePaymentRow,
  type FinanceWorkspaceResponse,
  type FinanceWorkspaceReturnRow,
  type FinanceWorkspaceSortBy,
  type FinanceWorkspaceSortOrder,
  type FinanceWorkspaceView,
} from "@/lib/core-api";
import { formatMoneyValue, normalizeCurrencyLabel } from "@/lib/money";
import { FINANCE_VIEWS } from "@/lib/workspace-view-config";

const PAGE_SIZE = 25;

const SUMMARY_REGISTRY = [
  { key: "payments_received", label: "Получено денег" },
  { key: "verified_cash_in", label: "Подтверждённый приток" },
  { key: "verified_cash_out", label: "Подтверждённый отток" },
  { key: "net_cash_flow", label: "Чистый поток" },
  { key: "customer_return_value", label: "Возвраты клиентам" },
  { key: "financial_operations_count", label: "Финансовых операций" },
] as const;

const SORT_OPTIONS: Array<{ value: FinanceWorkspaceSortBy; label: string }> = [
  { value: "date", label: "Дата" },
  { value: "amount", label: "Сумма" },
  { value: "organization", label: "Организация" },
  { value: "operation_type", label: "Тип операции" },
  { value: "direction", label: "Направление" },
  { value: "customer", label: "Клиент" },
  { value: "account", label: "Счёт" },
];

type RowSelection =
  | { kind: "overview"; row: FinanceWorkspaceOverviewRow }
  | { kind: "payment"; row: FinanceWorkspacePaymentRow }
  | { kind: "operation"; row: FinanceWorkspaceOperationRow }
  | { kind: "return"; row: FinanceWorkspaceReturnRow }
  | { kind: "account"; row: FinanceWorkspaceAccountRow }
  | null;

type QueryState = {
  view: FinanceWorkspaceView;
  search: string;
  direction: FinanceWorkspaceDirection[];
  operationType: string[];
  paymentType: string[];
  counterparty: string[];
  account: string[];
  currency: string[];
  dataQuality: Array<"verified" | "partial" | "unresolved" | "unsafe">;
  amountMin: string;
  amountMax: string;
  sortBy: FinanceWorkspaceSortBy;
  sortOrder: FinanceWorkspaceSortOrder;
  page: number;
};

function buildWorkspaceFilters(
  businessState: ReturnType<typeof useBusinessContext>["state"],
  query: QueryState,
): FinanceWorkspaceFilters {
  return {
    organizationIds: businessState.selectedOrganizationIds,
    period: businessState.period.preset,
    dateFrom: businessState.period.dateFrom,
    dateTo: businessState.period.dateTo,
    view: query.view,
    search: query.search || null,
    direction: query.direction,
    operationType: query.operationType,
    paymentType: query.paymentType,
    counterparty: query.counterparty,
    account: query.account,
    currency: query.currency,
    dataQuality: query.dataQuality,
    amountMin: query.amountMin ? query.amountMin : null,
    amountMax: query.amountMax ? query.amountMax : null,
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

function coverageVariant(status: FinanceWorkspaceCoverageItem["status"]) {
  if (status === "AVAILABLE") return "accent" as const;
  if (status === "PARTIAL") return "soft" as const;
  if (status === "NO_DATA" || status === "NO_VERIFIED_DATA") return "neutral" as const;
  return "dark" as const;
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

function directionLabel(direction: FinanceWorkspaceDirection) {
  switch (direction) {
    case "INFLOW":
      return "Приток";
    case "OUTFLOW":
      return "Отток";
    case "TRANSFER":
      return "Перенос";
    default:
      return "Неизвестно";
  }
}

function metricTone(status: AnalyticsDataStatus) {
  return status === "AVAILABLE" || status === "PARTIAL"
    ? "text-[#f4f7fb]"
    : "text-slate-400";
}

function formatMetricValue(
  value: string | number | null | undefined,
  currency?: string | null,
  status?: AnalyticsDataStatus,
) {
  if (status === "NOT_AVAILABLE") return "Недоступно";
  if (status === "NO_DATA") return "Нет данных";
  if (status === "NO_VERIFIED_DATA" && value == null) return "Нет подтверждённых данных";
  if (status === "NO_VERIFIED_DATA") return "Нет подтверждённых данных";
  if (value == null) return "—";
  return formatMoneyValue(value, currency);
}

function buildActiveRows(data: FinanceWorkspaceResponse) {
  switch (data.active_view) {
    case "overview":
      return data.rows.overview;
    case "payments":
      return data.rows.payments;
    case "cash_operations":
      return data.rows.cash_operations;
    case "bank_operations":
      return data.rows.bank_operations;
    case "financial_operations":
      return data.rows.financial_operations;
    case "returns":
      return data.rows.returns;
    case "accounts":
      return data.rows.accounts;
    default:
      return [];
  }
}

function renderOverviewTable(
  rows: FinanceWorkspaceOverviewRow[],
  onSelect: (row: FinanceWorkspaceOverviewRow) => void,
) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-[#3a3d43] text-xs uppercase tracking-[0.22em] text-slate-400">
          <tr>
            <th className="px-5 py-4 font-medium">Организация</th>
            <th className="px-5 py-4 font-medium">Платежи</th>
            <th className="px-5 py-4 font-medium">Приток</th>
            <th className="px-5 py-4 font-medium">Отток</th>
            <th className="px-5 py-4 font-medium">Возвраты</th>
            <th className="px-5 py-4 font-medium">Операции</th>
            <th className="px-5 py-4 font-medium">Документы</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.organization_id}
              className="cursor-pointer border-b border-[#3a3d43] transition hover:bg-[#343840] last:border-b-0"
              onClick={() => onSelect(row)}
            >
              <td className="px-5 py-4">
                <div className="font-medium text-[#f4f7fb]">{row.organization_name}</div>
                <div className="mt-1 text-xs text-slate-400">{statusLabel(row.data_status)}</div>
              </td>
              <td className="px-5 py-4 text-slate-200">{formatMoneyValue(row.payments_received, "UZS")}</td>
              <td className="px-5 py-4 text-slate-200">{formatMoneyValue(row.verified_cash_in, "UZS")}</td>
              <td className="px-5 py-4 text-slate-200">
                {row.data_status === "NO_VERIFIED_DATA" && row.verified_cash_out == null
                  ? "Нет подтверждённых данных"
                  : formatMoneyValue(row.verified_cash_out, "UZS")}
              </td>
              <td className="px-5 py-4 text-slate-200">{formatMoneyValue(row.customer_return_value, "UZS")}</td>
              <td className="px-5 py-4 text-slate-200">{row.financial_operations_count}</td>
              <td className="px-5 py-4 text-slate-400">
                {row.payments_count} платежей · {row.returns_count} возвратов · {row.purchases_count} закупок ·{" "}
                {row.writeoffs_count} списаний
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderPaymentsTable(
  rows: FinanceWorkspacePaymentRow[],
  onSelect: (row: FinanceWorkspacePaymentRow) => void,
) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-[#3a3d43] text-xs uppercase tracking-[0.22em] text-slate-400">
          <tr>
            <th className="px-5 py-4 font-medium">Платёж</th>
            <th className="px-5 py-4 font-medium">Организация</th>
            <th className="px-5 py-4 font-medium">Клиент</th>
            <th className="px-5 py-4 font-medium">Тип</th>
            <th className="px-5 py-4 font-medium">Сумма</th>
            <th className="px-5 py-4 font-medium">Связь с заказом</th>
            <th className="px-5 py-4 font-medium">Качество</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.payment_id}
              className="cursor-pointer border-b border-[#3a3d43] transition hover:bg-[#343840] last:border-b-0"
              onClick={() => onSelect(row)}
            >
              <td className="px-5 py-4">
                <div className="font-medium text-[#f4f7fb]">{row.payment_number ?? row.source_external_id}</div>
                <div className="mt-1 text-xs text-slate-400">{formatDateTime(row.paid_at)}</div>
              </td>
              <td className="px-5 py-4 text-slate-200">{row.organization_name}</td>
              <td className="px-5 py-4 text-slate-200">{row.customer_name ?? "—"}</td>
              <td className="px-5 py-4 text-slate-200">{row.payment_type ?? "—"}</td>
              <td className="px-5 py-4 font-medium text-[#f4f7fb]">
                {formatMoneyValue(row.amount, normalizeCurrencyLabel(row.currency_code))}
              </td>
              <td className="px-5 py-4 text-slate-400">
                <div>{row.allocation_status}</div>
                <div className="mt-1 text-xs">
                  {row.linked_order_number ?? row.linked_order_external_id ?? row.linked_sale_external_id ?? "—"}
                </div>
              </td>
              <td className="px-5 py-4">
                <Badge variant={qualityVariant(row.data_quality_status)}>{qualityStatusLabel(row.data_quality_status)}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderOperationsTable(
  rows: FinanceWorkspaceOperationRow[],
  onSelect: (row: FinanceWorkspaceOperationRow) => void,
) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-[#3a3d43] text-xs uppercase tracking-[0.22em] text-slate-400">
          <tr>
            <th className="px-5 py-4 font-medium">Операция</th>
            <th className="px-5 py-4 font-medium">Источник</th>
            <th className="px-5 py-4 font-medium">Организация</th>
            <th className="px-5 py-4 font-medium">Направление</th>
            <th className="px-5 py-4 font-medium">Контрагент</th>
            <th className="px-5 py-4 font-medium">Счёт</th>
            <th className="px-5 py-4 font-medium">Сумма</th>
            <th className="px-5 py-4 font-medium">Качество</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.operation_id}
              className="cursor-pointer border-b border-[#3a3d43] transition hover:bg-[#343840] last:border-b-0"
              onClick={() => onSelect(row)}
            >
              <td className="px-5 py-4">
                <div className="font-medium text-[#f4f7fb]">{row.operation_number ?? row.source_external_id}</div>
                <div className="mt-1 text-xs text-slate-400">{formatDateTime(row.operation_at)}</div>
              </td>
              <td className="px-5 py-4 text-slate-200">
                <div>{row.source_label}</div>
                <div className="mt-1 text-xs text-slate-400">{row.operation_type ?? "—"}</div>
              </td>
              <td className="px-5 py-4 text-slate-200">{row.organization_name}</td>
              <td className="px-5 py-4">
                <Badge variant={row.direction === "OUTFLOW" ? "soft" : "accent"}>
                  {directionLabel(row.direction)}
                </Badge>
              </td>
              <td className="px-5 py-4 text-slate-200">{row.counterparty_name ?? "—"}</td>
              <td className="px-5 py-4 text-slate-200">{row.account_label ?? "—"}</td>
              <td className="px-5 py-4 font-medium text-[#f4f7fb]">
                {formatMoneyValue(row.amount, normalizeCurrencyLabel(row.currency_code))}
              </td>
              <td className="px-5 py-4">
                <div className="flex flex-wrap gap-2">
                  <Badge variant={qualityVariant(row.data_quality_status)}>{qualityStatusLabel(row.data_quality_status)}</Badge>
                  {row.overlaps_customer_payment ? <Badge variant="soft">Пересечение с платежом</Badge> : null}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderReturnsTable(
  rows: FinanceWorkspaceReturnRow[],
  onSelect: (row: FinanceWorkspaceReturnRow) => void,
) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-[#3a3d43] text-xs uppercase tracking-[0.22em] text-slate-400">
          <tr>
            <th className="px-5 py-4 font-medium">Возврат</th>
            <th className="px-5 py-4 font-medium">Организация</th>
            <th className="px-5 py-4 font-medium">Клиент</th>
            <th className="px-5 py-4 font-medium">Сумма</th>
            <th className="px-5 py-4 font-medium">Количество</th>
            <th className="px-5 py-4 font-medium">Статус возврата денег</th>
            <th className="px-5 py-4 font-medium">Качество</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.customer_return_id}
              className="cursor-pointer border-b border-[#3a3d43] transition hover:bg-[#343840] last:border-b-0"
              onClick={() => onSelect(row)}
            >
              <td className="px-5 py-4">
                <div className="font-medium text-[#f4f7fb]">{row.return_number ?? row.source_external_id}</div>
                <div className="mt-1 text-xs text-slate-400">{formatDateTime(row.return_at)}</div>
              </td>
              <td className="px-5 py-4 text-slate-200">{row.organization_name}</td>
              <td className="px-5 py-4 text-slate-200">{row.customer_name ?? "—"}</td>
              <td className="px-5 py-4 font-medium text-[#f4f7fb]">
                {formatMoneyValue(row.value, normalizeCurrencyLabel(row.currency_code))}
              </td>
              <td className="px-5 py-4 text-slate-200">{row.returned_units ?? "—"}</td>
              <td className="px-5 py-4 text-slate-400">{row.cash_refund_status}</td>
              <td className="px-5 py-4">
                <Badge variant={qualityVariant(row.data_quality_status)}>{qualityStatusLabel(row.data_quality_status)}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderAccountsTable(
  rows: FinanceWorkspaceAccountRow[],
  onSelect: (row: FinanceWorkspaceAccountRow) => void,
) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-[#3a3d43] text-xs uppercase tracking-[0.22em] text-slate-400">
          <tr>
            <th className="px-5 py-4 font-medium">Счёт</th>
            <th className="px-5 py-4 font-medium">Организация</th>
            <th className="px-5 py-4 font-medium">Тип</th>
            <th className="px-5 py-4 font-medium">Банк / касса</th>
            <th className="px-5 py-4 font-medium">Валюта</th>
            <th className="px-5 py-4 font-medium">Качество</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.account_id}
              className="cursor-pointer border-b border-[#3a3d43] transition hover:bg-[#343840] last:border-b-0"
              onClick={() => onSelect(row)}
            >
              <td className="px-5 py-4">
                <div className="font-medium text-[#f4f7fb]">{row.account_name ?? row.account_code}</div>
                <div className="mt-1 text-xs text-slate-400">{row.account_code}</div>
              </td>
              <td className="px-5 py-4 text-slate-200">{row.organization_name}</td>
              <td className="px-5 py-4 text-slate-200">{row.account_type ?? "—"}</td>
              <td className="px-5 py-4 text-slate-200">
                {row.bank_name ?? row.bank_account_code ?? row.cashbox_code ?? "—"}
              </td>
              <td className="px-5 py-4 text-slate-200">{normalizeCurrencyLabel(row.currency_code) ?? "—"}</td>
              <td className="px-5 py-4">
                <Badge variant={qualityVariant(row.data_quality_status)}>{qualityStatusLabel(row.data_quality_status)}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function emptyStateMessage(
  rows: unknown[],
  selectedNames: string[],
  view: FinanceWorkspaceView,
) {
  if (rows.length > 0) return null;
  const scope = selectedNames.join(", ") || "выбранном контексте";
  switch (view) {
    case "payments":
      return `Нет платежей в ${scope}.`;
    case "returns":
      return `Нет возвратов в ${scope}.`;
    case "accounts":
      return `Нет финансовых счетов в ${scope}.`;
    default:
      return `Нет записей в ${scope}.`;
  }
}

function renderDrawerContent(selection: RowSelection) {
  if (!selection) return null;

  if (selection.kind === "overview") {
    const row = selection.row;
    return (
      <div className="space-y-4">
        <Surface className="p-4">
          <h3 className="text-lg font-semibold text-[#f4f7fb]">{row.organization_name}</h3>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Получено денег</p>
              <p className="mt-2 text-lg font-semibold text-[#f4f7fb]">{formatMoneyValue(row.payments_received, "UZS")}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Подтверждённый приток</p>
              <p className="mt-2 text-lg font-semibold text-[#f4f7fb]">{formatMoneyValue(row.verified_cash_in, "UZS")}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Подтверждённый отток</p>
              <p className="mt-2 text-lg font-semibold text-[#f4f7fb]">{formatMoneyValue(row.verified_cash_out, "UZS")}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Возвраты</p>
              <p className="mt-2 text-lg font-semibold text-[#f4f7fb]">{formatMoneyValue(row.customer_return_value, "UZS")}</p>
            </div>
          </div>
        </Surface>
      </div>
    );
  }

  const provenance = selection.row.provenance;

  return (
    <div className="space-y-4">
      {selection.kind === "payment" ? (
        <Surface className="p-4">
          <div className="flex flex-wrap gap-2">
            {selection.row.customer_id ? (
              <Link
                href="/customers"
                className="inline-flex items-center rounded-full border border-[#FFF27A]/30 bg-[#FFF27A] px-4 py-2 text-sm font-medium text-[#1E1E21] transition hover:border-[#FFF27A]/40"
              >
                Открыть карточку клиента
              </Link>
            ) : null}
            {selection.row.linked_order_id || selection.row.linked_sale_id ? (
              <Link
                href="/sales"
                className="inline-flex items-center rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-[#4a4e56] hover:text-[#f4f7fb]"
              >
                Открыть продажи и заказы
              </Link>
            ) : null}
          </div>
        </Surface>
      ) : null}
      <Surface className="overflow-hidden">
        <div className="divide-y divide-slate-100">
          {[
            ["Источник данных", provenance.source_endpoint],
            ["Внешний ID", provenance.source_external_id],
            ["Запись-источник", provenance.source_raw_record_id ?? "—"],
            ["Филиал запроса", provenance.request_filial_id ?? "—"],
            ["Филиал ответа", provenance.response_filial_id ?? "—"],
            ["Компания", provenance.request_company_id ?? "—"],
            ["Проект", provenance.request_project_code ?? "—"],
          ].map(([label, value]) => (
            <div key={label} className="flex items-start justify-between gap-4 px-4 py-3 text-sm">
              <span className="text-slate-400">{label}</span>
              <span className="max-w-[60%] break-all text-right text-[#f4f7fb]">{value}</span>
            </div>
          ))}
        </div>
      </Surface>
    </div>
  );
}

export function FinanceWorkspacePage() {
  const business = useBusinessContext();
  const { subscribe } = useBusinessRefresh();
  const selectedNames = useSelectedOrganizationNames();

  const [query, setQuery] = useState<QueryState>({
    view: "overview",
    search: "",
    direction: [],
    operationType: [],
    paymentType: [],
    counterparty: [],
    account: [],
    currency: [],
    dataQuality: [],
    amountMin: "",
    amountMax: "",
    sortBy: "date",
    sortOrder: "desc",
    page: 1,
  });
  const [data, setData] = useState<FinanceWorkspaceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<RowSelection>(null);
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

    void getFinanceWorkspace(filters)
      .then((response) => {
        if (!active) return;
        setData(response);
      })
      .catch((reason) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "Не удалось загрузить финансы.");
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

  const summaryTiles = useMemo(() => {
    if (!data) return [];
    return SUMMARY_REGISTRY.map(({ key, label }) => ({
      key,
      label,
      metric: data.summary[key],
    }));
  }, [data]);

  const activeRows = useMemo(() => (data ? buildActiveRows(data) : []), [data]);

  return (
    <section className="space-y-5">
      <div className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Финансы и денежный поток</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">Финансы</h1>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-400">
              Платежи, денежные операции, возвраты клиентам и финансовые счета.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="soft">{selectedNames.join(", ") || "Все организации"}</Badge>
            <Badge variant="soft">{data?.period.label ?? "Период загружается"}</Badge>
          </div>
        </div>
      </div>

      <Surface className="overflow-visible px-4 py-4 sm:px-5">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
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

      <FilterBar title="Фильтры" subtitle="Поиск, вкладка, суммы и финансовые признаки.">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <SearchInput
              value={query.search}
              onChange={(event) =>
                setQuery((current) => ({ ...current, search: event.target.value, page: 1 }))
              }
              placeholder="платёж, счёт, клиент, назначение"
            />
            <Select
              label="Вкладка"
              value={query.view}
              options={FINANCE_VIEWS.map(({ view, label }) => ({ value: view, label }))}
              onChange={(value) =>
                setQuery((current) => ({
                  ...current,
                  view: value as FinanceWorkspaceView,
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
                  sortBy: value as FinanceWorkspaceSortBy,
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
                setQuery((current) => ({
                  ...current,
                  sortOrder: value as FinanceWorkspaceSortOrder,
                }))
              }
            />
            <label className="flex flex-col gap-2">
              <span className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Сумма от</span>
              <input
                value={query.amountMin}
                onChange={(event) =>
                  setQuery((current) => ({ ...current, amountMin: event.target.value, page: 1 }))
                }
                placeholder="0"
                className="rounded-[20px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3 text-sm text-[#f4f7fb] outline-none transition focus:border-yellow-300"
              />
            </label>
            <label className="flex flex-col gap-2">
              <span className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Сумма до</span>
              <input
                value={query.amountMax}
                onChange={(event) =>
                  setQuery((current) => ({ ...current, amountMax: event.target.value, page: 1 }))
                }
                placeholder="без лимита"
                className="rounded-[20px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3 text-sm text-[#f4f7fb] outline-none transition focus:border-yellow-300"
              />
            </label>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <MultiSelect
              label="Направление"
              value={query.direction}
              options={data?.filters.directions ?? []}
              onChange={(next) =>
                setQuery((current) => ({
                  ...current,
                  direction: next as FinanceWorkspaceDirection[],
                  page: 1,
                }))
              }
            />
            <MultiSelect
              label="Тип платежа"
              value={query.paymentType}
              options={data?.filters.payment_types ?? []}
              onChange={(next) => setQuery((current) => ({ ...current, paymentType: next, page: 1 }))}
            />
            <MultiSelect
              label="Тип операции"
              value={query.operationType}
              options={data?.filters.operation_types ?? []}
              onChange={(next) => setQuery((current) => ({ ...current, operationType: next, page: 1 }))}
            />
            <MultiSelect
              label="Качество"
              value={query.dataQuality}
              options={data?.filters.data_quality ?? []}
              onChange={(next) =>
                setQuery((current) => ({
                  ...current,
                  dataQuality: next as QueryState["dataQuality"],
                  page: 1,
                }))
              }
            />
          </div>
        </div>
      </FilterBar>

      <Surface className="overflow-visible px-4 py-4 sm:px-5">
        <div className="flex flex-wrap gap-2">
          {FINANCE_VIEWS.map((view) => {
            const tab = data?.tabs.find((item) => item.view === view.view);
            return (
            <button
              key={view.view}
              type="button"
              onClick={() => setQuery((current) => ({ ...current, view: view.view, page: 1 }))}
              className={
                query.view === view.view
                  ? "inline-flex items-center gap-2 rounded-full border border-[#FFF27A]/30 bg-[#FFF27A] px-4 py-2 text-sm font-medium text-[#1E1E21]"
                  : "inline-flex items-center gap-2 rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-[#4a4e56] hover:text-[#f4f7fb]"
              }
            >
              <span>{view.label}</span>
              <Badge variant={coverageVariant(tab?.status ?? "NO_DATA")}>{tab?.count ?? 0}</Badge>
            </button>
            );
          })}
        </div>
      </Surface>

      <Surface className="overflow-visible px-4 py-4 sm:px-5">
        <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
          {(data?.coverage ?? []).map((item, index) => (
            <div key={`${item.key}-${index}`} className="rounded-[20px] border border-[#3a3d43] bg-[#343840] px-4 py-4">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-medium text-[#f4f7fb]">{item.label}</p>
                <Badge variant={coverageVariant(item.status)}>{item.status}</Badge>
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-400">{item.message}</p>
              {item.affected_domains.length > 0 ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {item.affected_domains.map((domain) => (
                    <Badge key={`${item.key}-${index}-${domain}`} variant="soft">
                      {domain}
                    </Badge>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </Surface>

      <Surface className="overflow-hidden">
        <div className="flex items-center justify-between gap-3 border-b border-[#3a3d43] px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-[#f4f7fb]">Операционный журнал</h2>
            <p className="mt-1 text-sm text-slate-400">
              {error
                ? error
                : emptyStateMessage(activeRows, selectedNames, query.view) ??
                  "Список строится из финансовых данных и учитывает текущий бизнес-контекст."}
            </p>
          </div>
          <Badge variant="soft">{data?.pagination.total_items ?? 0} записей</Badge>
        </div>

        {loading ? (
          <div className="px-5 py-10 text-sm text-slate-400">Загрузка финансовой страницы…</div>
        ) : error ? (
          <div className="px-5 py-10 text-sm text-rose-600">{error}</div>
        ) : query.view === "overview" ? (
          renderOverviewTable(data?.rows.overview ?? [], (row) => setSelection({ kind: "overview", row }))
        ) : query.view === "payments" ? (
          renderPaymentsTable(data?.rows.payments ?? [], (row) => setSelection({ kind: "payment", row }))
        ) : query.view === "returns" ? (
          renderReturnsTable(data?.rows.returns ?? [], (row) => setSelection({ kind: "return", row }))
        ) : query.view === "accounts" ? (
          renderAccountsTable(data?.rows.accounts ?? [], (row) => setSelection({ kind: "account", row }))
        ) : (
          renderOperationsTable(
            query.view === "cash_operations"
              ? data?.rows.cash_operations ?? []
              : query.view === "bank_operations"
                ? data?.rows.bank_operations ?? []
                : data?.rows.financial_operations ?? [],
            (row) => setSelection({ kind: "operation", row }),
          )
        )}

        {data ? (
          <div className="flex items-center justify-between gap-3 border-t border-[#3a3d43] px-5 py-4 text-sm text-slate-400">
            <span>
              Страница {data.pagination.page} из {Math.max(data.pagination.total_pages, 1)}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={data.pagination.page <= 1}
                className="rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 py-2 font-medium text-slate-300 transition hover:border-[#4a4e56] hover:text-[#f4f7fb] disabled:cursor-not-allowed disabled:opacity-40"
                onClick={() =>
                  setQuery((current) => ({
                    ...current,
                    page: Math.max(1, current.page - 1),
                  }))
                }
              >
                Назад
              </button>
              <button
                type="button"
                disabled={data.pagination.page >= data.pagination.total_pages}
                className="rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 py-2 font-medium text-slate-300 transition hover:border-[#4a4e56] hover:text-[#f4f7fb] disabled:cursor-not-allowed disabled:opacity-40"
                onClick={() =>
                  setQuery((current) => ({
                    ...current,
                    page: Math.min(data.pagination.total_pages, current.page + 1),
                  }))
                }
              >
                Вперёд
              </button>
            </div>
          </div>
        ) : null}
      </Surface>

      <Drawer
        open={Boolean(selection)}
        onClose={() => setSelection(null)}
        title={
          selection?.kind === "overview"
            ? selection.row.organization_name
            : selection?.kind === "payment"
              ? selection.row.payment_number ?? selection.row.source_external_id
              : selection?.kind === "operation"
                ? selection.row.operation_number ?? selection.row.source_external_id
                : selection?.kind === "return"
                  ? selection.row.return_number ?? selection.row.source_external_id
                  : selection?.kind === "account"
                    ? selection.row.account_name ?? selection.row.account_code
                    : "Подробности"
        }
        description="Источники данных и ключевые поля финансового раздела."
        badges={
          selection?.kind && selection.kind !== "overview" ? (
            <>
              <Badge variant="soft">
                {selection.kind === "payment"
                  ? "Платёж"
                  : selection.kind === "operation"
                    ? "Операция"
                    : selection.kind === "return"
                      ? "Возврат"
                      : "Счёт"}
              </Badge>
              <Badge variant={qualityVariant(selection.row.data_quality_status)}>
                {qualityStatusLabel(selection.row.data_quality_status)}
              </Badge>
            </>
          ) : undefined
        }
      >
        {renderDrawerContent(selection)}
      </Drawer>
    </section>
  );
}
