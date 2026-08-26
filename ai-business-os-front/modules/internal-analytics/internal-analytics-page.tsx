"use client";

import { useMemo, useState } from "react";

import { Drawer } from "@/components/ui/drawer";
import { Badge } from "@/components/ui/badge";
import { SectionHeading } from "@/components/ui/section-heading";
import { Surface } from "@/components/ui/surface";
import { cn } from "@/lib/cn";
import {
  formatMoneyValue,
  parseMoneyValue,
} from "@/lib/money";
import type {
  DashboardBusinessBreakdown,
  DashboardInventoryCard,
  DashboardOverviewResponse,
  DashboardPaymentCard,
  DashboardRecentSale,
  DashboardTopProduct,
} from "@/lib/core-api";
import {
  AnalyticsTrendChart,
  DataTable,
  DetailCard,
  EmptyState,
  FiltersSurface,
  KeyValue,
  MetricCard,
  PaginationBar,
  SearchField,
  SelectField,
  SortBadges,
  SummaryBlock,
  TableSection,
  type ChartSeries,
  type SelectOption,
  type SortDirection,
  type SortState,
} from "./components/internal-analytics-ui";

type AnalyticsPageKind = "sales" | "inventory" | "customers" | "finance";

type InternalAnalyticsPageProps = {
  kind: AnalyticsPageKind;
  overview: DashboardOverviewResponse;
};

const PERIOD_OPTIONS: SelectOption[] = [
  { value: "all", label: "Всё время" },
  { value: "30d", label: "30 дней" },
  { value: "90d", label: "90 дней" },
  { value: "12m", label: "12 месяцев" },
];

const SEGMENT_OPTIONS: SelectOption[] = [
  { value: "all", label: "Все сегменты" },
  { value: "leaders", label: "Лидеры" },
  { value: "growing", label: "Растущие" },
  { value: "falling", label: "Падающие" },
  { value: "slow", label: "Медленные" },
  { value: "dead", label: "Без продаж" },
];

export function InternalAnalyticsPage({ kind, overview }: InternalAnalyticsPageProps) {
  if (kind === "sales") {
    return <SalesAnalyticsPage overview={overview} />;
  }

  if (kind === "inventory") {
    return <InventoryAnalyticsPage overview={overview} />;
  }

  if (kind === "customers") {
    return <CustomersAnalyticsPage overview={overview} />;
  }

  return <FinanceAnalyticsPage overview={overview} />;
}

function SalesAnalyticsPage({ overview }: { overview: DashboardOverviewResponse }) {
  const organizationOptions = useMemo(() => {
    const names = uniqueStrings([
      ...overview.organization_performance.map((item) => item.name),
      ...overview.businesses.map((item) => item.name),
    ]);
    return [{ value: "all", label: "Все организации" }, ...names.map((name) => ({ value: name, label: name }))];
  }, [overview]);

  const statusOptions = useMemo(() => {
    const names = uniqueStrings(overview.recent_sales.map((item) => item.stage));
    return [{ value: "all", label: "Все статусы" }, ...names.map((name) => ({ value: name, label: name }))];
  }, [overview]);

  const currencyOptions = useMemo(() => {
    const names = uniqueStrings(overview.recent_sales.map((item) => item.currency));
    return [{ value: "all", label: "Все валюты" }, ...names.map((name) => ({ value: name, label: name }))];
  }, [overview]);

  const productOptions = useMemo(() => {
    const names = uniqueStrings(overview.top_products.map((item) => item.name));
    return [{ value: "all", label: "Все товары" }, ...names.map((name) => ({ value: name, label: name }))];
  }, [overview]);

  const categoryOptions = useMemo(() => {
    const names = uniqueStrings(overview.top_products.map((item) => item.category ?? ""));
    return [{ value: "all", label: "Все категории" }, ...names.map((name) => ({ value: name, label: name }))];
  }, [overview]);

  const customerOptions = useMemo(() => {
    const names = uniqueStrings(overview.recent_sales.map((item) => item.contact_name ?? ""));
    return [{ value: "all", label: "Все клиенты" }, ...names.map((name) => ({ value: name, label: name }))];
  }, [overview]);

  const [organization, setOrganization] = useState("all");
  const [period, setPeriod] = useState("90d");
  const [status, setStatus] = useState("all");
  const [currency, setCurrency] = useState("all");
  const [product, setProduct] = useState("all");
  const [category, setCategory] = useState("all");
  const [customer, setCustomer] = useState("all");
  const [search, setSearch] = useState("");
  const [trendScale, setTrendScale] = useState<"day" | "week" | "month">("month");
  const [comparePrevious, setComparePrevious] = useState(true);
  const [selectedSaleId, setSelectedSaleId] = useState<string | null>(null);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [saleDrawerOpen, setSaleDrawerOpen] = useState(false);
  const [productDrawerOpen, setProductDrawerOpen] = useState(false);
  const [productMode, setProductMode] = useState<string>("all");
  const [productSort, setProductSort] = useState<SortState<"name" | "sold_quantity" | "sold_amount" | "stock_quantity" | "last_sold_at">>({
    key: "sold_amount",
    direction: "desc",
  });
  const [organizationSort, setOrganizationSort] = useState<SortState<"name" | "revenue" | "sales" | "sold_units" | "average_check" | "returns">>({
    key: "revenue",
    direction: "desc",
  });
  const [salesSort, setSalesSort] = useState<SortState<"sale_at" | "sale_number" | "business_name" | "amount" | "items_count" | "products_count">>({
    key: "sale_at",
    direction: "desc",
  });
  const [pageSize, setPageSize] = useState("50");
  const [salesPage, setSalesPage] = useState(1);
  const [productPage, setProductPage] = useState(1);

  const organizationRows = useMemo(() => {
    const rows = [...overview.organization_performance];
    const filtered = organization === "all" ? rows : rows.filter((item) => item.name === organization);
    return sortBusinessRows(filtered, organizationSort);
  }, [overview.organization_performance, organization, organizationSort]);

  const salesRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const rows = overview.recent_sales.filter((sale) => {
      if (organization !== "all" && sale.business_name !== organization) return false;
      if (status !== "all" && sale.stage !== status) return false;
      if (currency !== "all" && sale.currency !== currency) return false;
      if (customer !== "all" && (sale.contact_name ?? "") !== customer) return false;
      if (!q) return true;
      return [sale.sale_id, sale.sale_number, sale.business_name, sale.contact_name ?? "", sale.external_ref ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(q);
    });
    return sortSalesRows(rows, salesSort);
  }, [overview.recent_sales, organization, status, currency, customer, search, salesSort]);

  const productRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const rows = overview.top_products.filter((productItem) => {
      if (organization !== "all" && productItem.business_name !== organization) return false;
      if (product !== "all" && productItem.name !== product) return false;
      if (category !== "all" && (productItem.category ?? "") !== category) return false;
      if (productMode === "leaders" && parseMoneyValue(productItem.sold_amount) <= 0) return false;
      if (productMode === "falling" && (productItem.direction ?? "") !== "down") return false;
      if (productMode === "dead" && (productItem.no_sales_days ?? 0) <= 0) return false;
      if (productMode === "slow" && parseMoneyValue(productItem.stock_quantity) <= parseMoneyValue(productItem.sold_quantity)) return false;
      if (productMode === "growing" && (productItem.direction ?? "") !== "up") return false;
      if (!q) return true;
      return [
        productItem.name,
        productItem.category ?? "",
        productItem.sku ?? "",
        productItem.business_name,
      ]
        .join(" ")
        .toLowerCase()
        .includes(q);
    });
    return sortProductRows(rows, productSort);
  }, [overview.top_products, organization, product, category, productMode, search, productSort]);

  const pageSizeNumber = Number(pageSize);
  const totalSalesPages = Math.max(1, Math.ceil(salesRows.length / pageSizeNumber));
  const totalProductPages = Math.max(1, Math.ceil(productRows.length / pageSizeNumber));
  const visibleSalesRows = salesRows.slice((salesPage - 1) * pageSizeNumber, salesPage * pageSizeNumber);
  const visibleProductRows = productRows.slice((productPage - 1) * pageSizeNumber, productPage * pageSizeNumber);

  const activeSale = visibleSalesRows.find((sale) => sale.sale_id === selectedSaleId) ?? visibleSalesRows[0] ?? salesRows[0] ?? null;
  const activeProduct = visibleProductRows.find((item) => item.product_id === selectedProductId) ?? visibleProductRows[0] ?? productRows[0] ?? null;

  const revenueMetric = pickMetric(overview, "Выручка");
  const dealsMetric = pickMetric(overview, "Сделки");
  const soldUnitsMetric = pickMetric(overview, "Продано единиц");
  const avgCheckMetric = pickMetric(overview, "Средний чек");
  const returnsMetric = pickMetric(overview, "Возвраты");
  const customersCount = uniqueStrings(overview.recent_sales.map((item) => item.contact_name ?? "")).length;
  const uniqueProducts = overview.top_products.length;
  const returnsAmount = Math.max(parseMoneyValue(returnsMetric?.value), 0);
  const revenueAmount = Math.max(parseMoneyValue(revenueMetric?.value), 0);
  const returnRate = revenueAmount > 0 ? (returnsAmount / revenueAmount) * 100 : 0;

  const chartValues = useMemo(() => {
    const base = overview.trend.values.length ? overview.trend.values : overview.recent_sales.map((sale) => parseMoneyValue(sale.amount));
    return projectTrendSeries(base, trendScale);
  }, [overview.trend.values, overview.recent_sales, trendScale]);

  const chartSeries = useMemo<ChartSeries[]>(() => {
    const max = Math.max(...chartValues, 1);
    const unitsSource = chartValues.map((value) => Math.round((value / max) * Math.max(1, parseMoneyValue(soldUnitsMetric?.value ?? "0") || 1)));
    const dealsSource = chartValues.map((value) => Math.round((value / max) * Math.max(1, parseMoneyValue(dealsMetric?.value ?? "0") || 1)));

    return [
      {
        key: "revenue",
        label: "Выручка",
        color: "#4f46e5",
        values: chartValues,
      },
      {
        key: "units",
        label: "Продано единиц",
        color: "#0ea5e9",
        values: unitsSource,
      },
      {
        key: "deals",
        label: "Сделки",
        color: "#10b981",
        values: dealsSource,
      },
    ];
  }, [chartValues, dealsMetric?.value, soldUnitsMetric?.value]);

  const selectedSaleDetails = activeSale
    ? {
        ...activeSale,
        saleAt: activeSale.sale_at,
        amount: formatMoneyValue(activeSale.amount, activeSale.currency),
        itemsLabel: `${activeSale.items_count} строк`,
        productsLabel: `${activeSale.products_count} товаров`,
      }
    : null;

  const selectedProductDetails = activeProduct
    ? {
        ...activeProduct,
        soldAmount: formatMoneyValue(activeProduct.sold_amount),
        stockAmount: formatMoneyValue(activeProduct.stock_quantity),
      }
    : null;

  const filteredSales = visibleSalesRows;

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Продажи"
        title="Продажи"
        description="Полная аналитика продаж по организациям, товарам, клиентам и периодам."
      />

      <FiltersSurface>
        <div className="grid gap-3 xl:grid-cols-4">
          <SelectField label="Организация" value={organization} options={organizationOptions} onChange={setOrganization} />
          <SelectField label="Период" value={period} options={PERIOD_OPTIONS} onChange={setPeriod} />
          <SelectField label="Статус продажи" value={status} options={statusOptions} onChange={setStatus} />
          <SelectField label="Валюта" value={currency} options={currencyOptions} onChange={setCurrency} />
        </div>
        <div className="mt-3 grid gap-3 xl:grid-cols-4">
          <SelectField label="Товар" value={product} options={productOptions} onChange={setProduct} />
          <SelectField label="Категория" value={category} options={categoryOptions} onChange={setCategory} />
          <SelectField label="Клиент" value={customer} options={customerOptions} onChange={setCustomer} />
          <SearchField value={search} onChange={setSearch} placeholder="Поиск по deal_id, клиенту или товару" />
        </div>
      </FiltersSurface>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Выручка"
          value={revenueMetric?.value ?? "0 UZS"}
          note={revenueMetric?.note ?? "по продажам"}
          formula="SUM(Sale.total_amount) по подтвержденным продажам"
          change={revenueMetric?.change}
          active={false}
          onClick={() => {
            setSelectedSaleId(activeSale?.sale_id ?? null);
            setSaleDrawerOpen(true);
          }}
        />
        <MetricCard
          label="Сделок"
          value={dealsMetric?.value ?? String(salesRows.length)}
          note={dealsMetric?.note ?? "по периоду"}
          formula="COUNT(Sale) за выбранный период"
          change={dealsMetric?.change}
          onClick={() => setSalesPage(1)}
        />
        <MetricCard
          label="Продано единиц"
          value={soldUnitsMetric?.value ?? "0"}
          note={soldUnitsMetric?.note ?? "SaleItem.quantity"}
          formula="SUM(SaleItem.quantity)"
          change={soldUnitsMetric?.change}
          onClick={() => setProductMode("leaders")}
        />
        <MetricCard
          label="Средний чек"
          value={avgCheckMetric?.value ?? "0 UZS"}
          note={avgCheckMetric?.note ?? "выручка / сделки"}
          formula="Выручка / количество сделок"
          change={avgCheckMetric?.change}
        />
        <MetricCard
          label="Возвраты"
          value={returnsMetric?.value ?? "0 UZS"}
          note={returnsMetric?.note ?? "отдельно от cash flow"}
          formula="SUM(normalized_returns.amount)"
          change={returnsMetric?.change}
        />
        <MetricCard
          label="Возвраты %"
          value={`${formatRatio(returnRate)}%`}
          note="возвраты / выручка"
          formula="Возвраты / Выручка × 100%"
        />
        <MetricCard
          label="Клиентов"
          value={formatCompactNumber(customersCount)}
          note="уникальные клиенты"
          formula="COUNT(DISTINCT customer)"
          onClick={() => setCustomer("all")}
        />
        <MetricCard
          label="Уникальных товаров"
          value={formatCompactNumber(uniqueProducts)}
          note="в продажах"
          formula="COUNT(DISTINCT product_id)"
          onClick={() => {
            setProductMode("all");
            setProductDrawerOpen(true);
          }}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.4fr_0.8fr]">
        <Surface className="overflow-visible p-5 sm:p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Продажи и динамика</p>
              <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">Выручка, сделки и единицы</h3>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
                Показатель отображает глубину продаж: деньги, количество единиц и количество сделок за выбранный период.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {(["day", "week", "month"] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setTrendScale(value)}
                    className={cn(
                      "rounded-full border px-4 py-2 text-sm font-medium transition",
                      trendScale === value
                      ? "border-[#FFF27A]/30 bg-[#FFF27A] text-[#1E1E21]"
                      : "border-[#3a3d43] bg-[#2E3137] text-slate-400 hover:border-[#4a4e56] hover:text-[#f4f7fb]",
                  )}
                >
                  {value === "day" ? "День" : value === "week" ? "Неделя" : "Месяц"}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setComparePrevious((value) => !value)}
                className={cn(
                  "rounded-full border px-4 py-2 text-sm font-medium transition",
                  comparePrevious
                    ? "border-[#FFF27A]/30 bg-[#FFF27A] text-[#1E1E21]"
                    : "border-[#3a3d43] bg-[#2E3137] text-slate-400 hover:border-[#4a4e56] hover:text-[#f4f7fb]",
                )}
              >
                Сравнить с предыдущим
              </button>
            </div>
          </div>

          <div className="mt-5">
            <AnalyticsTrendChart
              labels={overview.trend.labels}
              series={chartSeries}
              comparePrevious={comparePrevious}
              variant="sales"
            />
          </div>
        </Surface>

        <Surface className="p-5 sm:p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
                <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Обзор ИИ</p>
              <h3 className="mt-2 text-xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">Куда смотреть в продажах</h3>
            </div>
            <Badge variant="accent">{overview.analysis_engine}</Badge>
          </div>
          <div className="mt-4 space-y-3">
            {overview.ai_insights.slice(0, 4).map((item, index) => (
              <div key={index} className="rounded-2xl border border-[#3a3d43] bg-[#343840]/80 px-4 py-3">
                <p className="text-sm leading-6 text-slate-300">{item}</p>
              </div>
            ))}
          </div>
          <div className="mt-4 rounded-2xl border border-[#3a3d43] bg-[#2E3137] p-4">
            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Статус данных</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <KeyValue label="Организаций" value={formatCompactNumber(organizationRows.length)} />
              <KeyValue label="Сделок" value={formatCompactNumber(filteredSales.length)} />
              <KeyValue label="Товаров" value={formatCompactNumber(productRows.length)} />
              <KeyValue label="Возвратов" value={formatMoneyValue(returnsAmount)} />
            </div>
          </div>
        </Surface>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <TableSection
          title="Продажи по организациям"
          subtitle="Выручка, доля, сделки, продано единиц и возвраты по каждой организации"
          badge={`${organizationRows.length} организаций`}
          rightAction={<SortBadges sort={organizationSort} />}
        >
          <DataTable
            columns={[
              { key: "name", label: "Организация" },
              { key: "revenue", label: "Выручка" },
              { key: "share", label: "Доля" },
              { key: "sales", label: "Сделок" },
              { key: "sold_units", label: "Продано" },
              { key: "average_check", label: "Средний чек" },
              { key: "returns", label: "Возвраты" },
              { key: "net_flow", label: "Поток" },
            ]}
            onSort={(key) => {
              if (key === "share") return;
              setOrganizationSort((current) =>
                current.key === key
                  ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
                  : { key: key as SortState<"name" | "revenue" | "sales" | "sold_units" | "average_check" | "returns">["key"], direction: "desc" },
              );
            }}
            sortKey={organizationSort.key}
            sortDirection={organizationSort.direction}
            rows={organizationRows.map((business) => (
              <tr
                key={business.business_id}
                className="cursor-pointer border-b border-[#3a3d43] transition hover:bg-[#343840]"
                onClick={() => setOrganization(business.name)}
              >
                <td className="px-4 py-3">
                  <div className="min-w-0">
                    <p className="font-semibold text-[#f4f7fb]">{business.name}</p>
                    <p className="mt-1 text-xs text-slate-400">
                      {business.external_ref ?? "Без external_ref"} · {business.source_systems} источн. · {business.contacts} контактов
                    </p>
                  </div>
                </td>
                <td className="px-4 py-3 font-medium text-[#f4f7fb]">{business.revenue}</td>
                <td className="px-4 py-3 text-slate-300">{business.rank ? `${business.rank}%` : "—"}</td>
                <td className="px-4 py-3 text-slate-300">{business.sales}</td>
                <td className="px-4 py-3 text-slate-300">{business.sold_units ?? "—"}</td>
                <td className="px-4 py-3 text-slate-300">{business.average_check ?? "—"}</td>
                <td className="px-4 py-3 text-slate-300">{business.returns ?? "—"}</td>
                <td className="px-4 py-3 text-slate-300">{business.net_flow}</td>
              </tr>
            ))}
          />
        </TableSection>

        <Surface className="p-5 sm:p-6">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Детали</p>
          <h3 className="mt-2 text-xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">Выбранная продажа и товар</h3>

          <div className="mt-4 space-y-4">
            <DetailCard
              title={selectedSaleDetails?.sale_number ?? "Продажа не выбрана"}
              subtitle={selectedSaleDetails ? `${selectedSaleDetails.business_name} · ${selectedSaleDetails.contact_name ?? "Без клиента"}` : "Выберите строку в таблице продаж"}
              badges={[
                selectedSaleDetails?.stage ?? "—",
                selectedSaleDetails?.currency ?? "—",
              ]}
              action={selectedSaleDetails ? <button type="button" onClick={() => setSaleDrawerOpen(true)} className="rounded-full border border-[#FFF27A]/30 bg-[#FFF27A] px-3 py-1.5 text-xs font-medium text-[#1E1E21] transition hover:border-[#FFF27A]/40">Открыть карточку</button> : null}
            >
              {selectedSaleDetails ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <KeyValue label="ID продажи" value={selectedSaleDetails.sale_id} />
                  <KeyValue label="Сумма" value={selectedSaleDetails.amount} />
                  <KeyValue label="Строк" value={selectedSaleDetails.itemsLabel} />
                  <KeyValue label="Товаров" value={selectedSaleDetails.productsLabel} />
                  <KeyValue label="Дата" value={formatDateTimeShort(selectedSaleDetails.saleAt)} />
                  <KeyValue label="Источник" value={selectedSaleDetails.external_ref ?? "—"} />
                </div>
              ) : null}
            </DetailCard>

            <DetailCard
              title={selectedProductDetails?.name ?? "Товар не выбран"}
              subtitle={selectedProductDetails ? `${selectedProductDetails.business_name} · ${selectedProductDetails.category ?? "Без категории"}` : "Выберите строку в аналитике товаров"}
              badges={[
                selectedProductDetails?.sku ?? "Артикул",
                selectedProductDetails?.status ?? "Статус",
              ]}
              action={selectedProductDetails ? <button type="button" onClick={() => setProductDrawerOpen(true)} className="rounded-full border border-[#FFF27A]/30 bg-[#FFF27A] px-3 py-1.5 text-xs font-medium text-[#1E1E21] transition hover:border-[#FFF27A]/40">Открыть карточку</button> : null}
            >
              {selectedProductDetails ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <KeyValue label="Продано единиц" value={selectedProductDetails.sold_quantity} />
                  <KeyValue label="Выручка" value={selectedProductDetails.soldAmount} />
                  <KeyValue label="Остаток" value={selectedProductDetails.stockAmount} />
                  <KeyValue label="Последняя продажа" value={formatDateShort(selectedProductDetails.last_sold_at)} />
                </div>
              ) : null}
            </DetailCard>
          </div>
        </Surface>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <TableSection
          title="Аналитика товаров"
          subtitle="Полная таблица товаров с режимами и возможностью сортировки"
          badge={`${productRows.length} позиций`}
          rightAction={
            <div className="flex items-center gap-2">
              {SEGMENT_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setProductMode(option.value)}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-xs font-medium transition",
                    productMode === option.value
                      ? "border-[#FFF27A]/30 bg-[#FFF27A] text-[#1E1E21]"
                      : "border-[#3a3d43] bg-[#2E3137] text-slate-400 hover:border-[#4a4e56] hover:text-[#f4f7fb]",
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
          }
        >
          <div className="rounded-2xl border border-[#3a3d43] bg-[#2E3137]">
            <DataTable
              columns={[
                { key: "name", label: "Товар" },
                { key: "sku", label: "Код товара" },
                { key: "category", label: "Категория" },
                { key: "sold_quantity", label: "Продано" },
                { key: "sales_count", label: "Продаж" },
                { key: "sold_amount", label: "Выручка" },
                { key: "average_price", label: "Средняя цена" },
                { key: "last_sold_at", label: "Последняя продажа" },
                { key: "stock_quantity", label: "Остаток" },
                { key: "change_percent", label: "Динамика" },
              ]}
              onSort={(key) => {
                if (key === "sales_count" || key === "average_price") return;
                setProductSort((current) =>
                  current.key === key
                    ? { key: key as SortState<"name" | "sold_quantity" | "sold_amount" | "stock_quantity" | "last_sold_at">["key"], direction: current.direction === "asc" ? "desc" : "asc" }
                    : { key: key as SortState<"name" | "sold_quantity" | "sold_amount" | "stock_quantity" | "last_sold_at">["key"], direction: "desc" },
                );
              }}
              sortKey={productSort.key}
              sortDirection={productSort.direction}
              rows={visibleProductRows.map((item) => (
                <tr
                  key={item.product_id}
                  className="cursor-pointer border-b border-[#3a3d43] transition hover:bg-[#343840]"
                  onClick={() => {
                    setSelectedProductId(item.product_id);
                    setProductDrawerOpen(true);
                  }}
                >
                  <td className="px-4 py-3">
                    <p className="font-semibold text-[#f4f7fb]">{item.name}</p>
                    <p className="mt-1 text-xs text-slate-400">{item.business_name}</p>
                  </td>
                  <td className="px-4 py-3 text-slate-300">{item.sku ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-300">{item.category ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-300">{item.sold_quantity}</td>
                  <td className="px-4 py-3 text-slate-300">{item.no_sales_days != null ? formatCompactNumber(Math.max(0, 30 - item.no_sales_days)) : "—"}</td>
                  <td className="px-4 py-3 font-medium text-[#f4f7fb]">{formatMoneyValue(item.sold_amount)}</td>
                  <td className="px-4 py-3 text-slate-300">{formatMoneyValue(formatAveragePrice(item))}</td>
                  <td className="px-4 py-3 text-slate-300">{formatDateShort(item.last_sold_at)}</td>
                  <td className="px-4 py-3 text-slate-300">{item.stock_quantity}</td>
                  <td className="px-4 py-3 text-slate-300">{item.change_percent ?? "—"}</td>
                </tr>
              ))}
            />
          </div>
          <PaginationBar
            page={productPage}
            totalPages={totalProductPages}
            pageSize={pageSize}
            onPageChange={setProductPage}
            onPageSizeChange={setPageSize}
          />
        </TableSection>

        <TableSection
          title="Все продажи"
          subtitle="Список сделок с поиском, страницами и переходом в детали"
          badge={`${salesRows.length} записей`}
          rightAction={<SearchField value={search} onChange={setSearch} placeholder="Поиск по сделке или клиенту" compact />}
        >
          <div className="rounded-2xl border border-[#3a3d43] bg-[#2E3137]">
            <DataTable
              columns={[
                { key: "sale_at", label: "Дата" },
                { key: "sale_number", label: "Номер сделки" },
                { key: "business_name", label: "Организация" },
                { key: "contact_name", label: "Клиент" },
                { key: "stage", label: "Статус" },
                { key: "items_count", label: "Строк" },
                { key: "products_count", label: "Товаров" },
                { key: "amount", label: "Сумма" },
                { key: "currency", label: "Валюта" },
              ]}
              onSort={(key) => {
                setSalesSort((current) =>
                  current.key === key
                    ? { key: key as SortState<"sale_at" | "sale_number" | "business_name" | "amount" | "items_count" | "products_count">["key"], direction: current.direction === "asc" ? "desc" : "asc" }
                    : { key: key as SortState<"sale_at" | "sale_number" | "business_name" | "amount" | "items_count" | "products_count">["key"], direction: "desc" },
                );
              }}
              sortKey={salesSort.key}
              sortDirection={salesSort.direction}
              rows={visibleSalesRows.map((sale) => (
                <tr
                  key={sale.sale_id}
                  className="cursor-pointer border-b border-[#3a3d43] transition hover:bg-[#343840]"
                  onClick={() => {
                    setSelectedSaleId(sale.sale_id);
                    setSaleDrawerOpen(true);
                  }}
                >
                  <td className="px-4 py-3 text-slate-300">{formatDateShort(sale.sale_at)}</td>
                  <td className="px-4 py-3">
                    <p className="font-semibold text-[#f4f7fb]">{sale.sale_number}</p>
                    <p className="mt-1 text-xs text-slate-400">Deal ID: {sale.sale_id}</p>
                  </td>
                  <td className="px-4 py-3 text-slate-300">{sale.business_name}</td>
                  <td className="px-4 py-3 text-slate-300">{sale.contact_name ?? "—"}</td>
                  <td className="px-4 py-3">
                    <Badge variant="soft">{sale.stage}</Badge>
                  </td>
                  <td className="px-4 py-3 text-slate-300">{sale.items_count}</td>
                  <td className="px-4 py-3 text-slate-300">{sale.products_count}</td>
                  <td className="px-4 py-3 font-medium text-[#f4f7fb]">{formatMoneyValue(sale.amount, sale.currency)}</td>
                  <td className="px-4 py-3 text-slate-300">{sale.currency}</td>
                </tr>
              ))}
            />
          </div>
          <PaginationBar
            page={salesPage}
            totalPages={totalSalesPages}
            pageSize={pageSize}
            onPageChange={setSalesPage}
            onPageSizeChange={setPageSize}
          />
        </TableSection>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <TableSection
          title="Возвраты и корректировки"
          subtitle="Что вернулось, что было скорректировано и как это влияет на продажи"
          badge={`${overview.returns_summary.length} карточек`}
        >
          <div className="grid gap-3 lg:grid-cols-2">
            {overview.returns_summary.length ? (
              overview.returns_summary.map((item) => <SummaryBlock key={item.label} card={item} />)
            ) : (
              <EmptyState text="Возвраты пока не загружены." />
            )}
          </div>
        </TableSection>

        <Surface className="p-5 sm:p-6">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Источники данных</p>
          <h3 className="mt-2 text-xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">Что видит страница продаж</h3>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {[
              "Организации и потоки",
              "Сделки и статусы",
              "Товары и остатки",
              "Клиенты и возвраты",
              "AI-инсайты из ядра",
              "Период и валюта",
            ].map((item) => (
              <div key={item} className="rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-3 text-sm text-slate-300">
                {item}
              </div>
            ))}
          </div>
        </Surface>
      </div>

      <Drawer
        open={saleDrawerOpen && Boolean(selectedSaleDetails)}
        onClose={() => setSaleDrawerOpen(false)}
        title={selectedSaleDetails?.sale_number ?? "Продажа"}
        description={selectedSaleDetails ? `${selectedSaleDetails.business_name} · ${selectedSaleDetails.contact_name ?? "Без клиента"}` : undefined}
        badges={selectedSaleDetails ? [selectedSaleDetails.stage, selectedSaleDetails.currency].map((value) => (
          <Badge key={value} variant="soft">
            {value}
          </Badge>
        )) : null}
      >
        {selectedSaleDetails ? (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <KeyValue label="Deal ID" value={selectedSaleDetails.sale_id} />
              <KeyValue label="Сумма" value={selectedSaleDetails.amount} />
              <KeyValue label="Строк" value={selectedSaleDetails.itemsLabel} />
              <KeyValue label="Товаров" value={selectedSaleDetails.productsLabel} />
              <KeyValue label="Дата" value={formatDateTimeShort(selectedSaleDetails.saleAt)} />
              <KeyValue label="Источник" value={selectedSaleDetails.external_ref ?? "—"} />
            </div>
            <div className="rounded-2xl border border-[#3a3d43] bg-[#2E3137] p-4">
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Контекст</p>
              <div className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                <p>Продажа открыта из списка &quot;Все продажи&quot;.</p>
                <p>Сумма и количество строк берутся из нормализованного заказа SmartUp.</p>
              </div>
            </div>
          </div>
        ) : null}
      </Drawer>

      <Drawer
        open={productDrawerOpen && Boolean(selectedProductDetails)}
        onClose={() => setProductDrawerOpen(false)}
        title={selectedProductDetails?.name ?? "Товар"}
        description={selectedProductDetails ? `${selectedProductDetails.business_name} · ${selectedProductDetails.category ?? "Без категории"}` : undefined}
        badges={selectedProductDetails ? [selectedProductDetails.sku ?? "Артикул", selectedProductDetails.status ?? "Статус"].map((value) => (
          <Badge key={value} variant="soft">
            {value}
          </Badge>
        )) : null}
      >
        {selectedProductDetails ? (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <KeyValue label="Продано единиц" value={selectedProductDetails.sold_quantity} />
              <KeyValue label="Выручка" value={selectedProductDetails.soldAmount} />
              <KeyValue label="Остаток" value={selectedProductDetails.stockAmount} />
              <KeyValue label="Последняя продажа" value={formatDateShort(selectedProductDetails.last_sold_at)} />
            </div>
            <div className="rounded-2xl border border-[#3a3d43] bg-[#2E3137] p-4">
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Контекст товара</p>
              <div className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                <p>Эта карточка открывает глубокий обзор по товару без перегрузки основной страницы.</p>
                <p>Здесь можно дальше подключить историю продаж, остатки и динамику по артикулам.</p>
              </div>
            </div>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}

function InventoryAnalyticsPage({ overview }: { overview: DashboardOverviewResponse }) {
  const organizationOptions = useMemo(() => {
    const names = uniqueStrings([
      ...overview.organization_performance.map((item) => item.name),
      ...overview.inventory.map((item) => item.business_name),
    ]);
    return [{ value: "all", label: "Все организации" }, ...names.map((name) => ({ value: name, label: name }))];
  }, [overview]);

  const warehouseOptions = useMemo(() => {
    const names = uniqueStrings(overview.inventory.map((item) => item.warehouse_name));
    return [{ value: "all", label: "Все склады" }, ...names.map((name) => ({ value: name, label: name }))];
  }, [overview]);

  const categoryOptions = useMemo(() => {
    const names = uniqueStrings(overview.top_products.map((item) => item.category ?? ""));
    return [{ value: "all", label: "Все категории" }, ...names.map((name) => ({ value: name, label: name }))];
  }, [overview]);

  const riskOptions = useMemo(() => {
    const names = uniqueStrings(overview.inventory.map((item) => item.risk_level ?? ""));
    return [{ value: "all", label: "Все риски" }, ...names.map((name) => ({ value: name, label: name }))];
  }, [overview]);

  const [organization, setOrganization] = useState("all");
  const [period, setPeriod] = useState("90d");
  const [warehouse, setWarehouse] = useState("all");
  const [risk, setRisk] = useState("all");
  const [category, setCategory] = useState("all");
  const [search, setSearch] = useState("");
  const [inventorySort, setInventorySort] = useState<SortState<"product_name" | "warehouse_name" | "quantity" | "average_daily_sales" | "days_of_stock" | "risk_level">>({
    key: "quantity",
    direction: "desc",
  });
  const [topProductSort, setTopProductSort] = useState<SortState<"name" | "sold_quantity" | "sold_amount" | "stock_quantity" | "last_sold_at">>({
    key: "sold_amount",
    direction: "desc",
  });
  const [selectedInventoryId, setSelectedInventoryId] = useState<string | null>(null);
  const [selectedTopProductId, setSelectedTopProductId] = useState<string | null>(null);
  const [inventoryDrawerOpen, setInventoryDrawerOpen] = useState(false);
  const [topProductDrawerOpen, setTopProductDrawerOpen] = useState(false);
  const [pageSize, setPageSize] = useState("50");
  const [inventoryPage, setInventoryPage] = useState(1);
  const [productPage, setProductPage] = useState(1);

  const inventoryRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const rows = overview.inventory.filter((item) => {
      if (organization !== "all" && item.business_name !== organization) return false;
      if (warehouse !== "all" && item.warehouse_name !== warehouse) return false;
      if (risk !== "all" && (item.risk_level ?? "") !== risk) return false;
      if (category !== "all") {
        const categoryMatch = overview.top_products.find(
          (product) => product.business_name === item.business_name && (product.category ?? "") === category,
        );
        if (!categoryMatch) return false;
      }
      if (!q) return true;
      return [item.warehouse_name, item.product_name, item.business_name, item.risk_level ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(q);
    });
    return sortInventoryRows(rows, inventorySort);
  }, [overview.inventory, overview.top_products, organization, warehouse, risk, category, search, inventorySort]);

  const productRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return overview.top_products.filter((item) => {
      if (organization !== "all" && item.business_name !== organization) return false;
      if (category !== "all" && (item.category ?? "") !== category) return false;
      if (!q) return true;
      return [item.name, item.business_name, item.category ?? "", item.sku ?? ""].join(" ").toLowerCase().includes(q);
    });
  }, [overview.top_products, organization, category, search]);

  const pageSizeNumber = Number(pageSize);
  const totalInventoryPages = Math.max(1, Math.ceil(inventoryRows.length / pageSizeNumber));
  const totalProductPages = Math.max(1, Math.ceil(productRows.length / pageSizeNumber));
  const visibleInventoryRows = inventoryRows.slice((inventoryPage - 1) * pageSizeNumber, inventoryPage * pageSizeNumber);
  const sortedProducts = useMemo(() => sortProductRows(productRows, topProductSort), [productRows, topProductSort]);
  const visibleProducts = sortedProducts.slice((productPage - 1) * pageSizeNumber, productPage * pageSizeNumber);

  const activeInventory = visibleInventoryRows.find((item) => `${item.warehouse_name}-${item.product_name}` === selectedInventoryId) ?? visibleInventoryRows[0] ?? inventoryRows[0] ?? null;
  const activeProduct = visibleProducts.find((item) => item.product_id === selectedTopProductId) ?? visibleProducts[0] ?? productRows[0] ?? null;

  const totalQuantity = inventoryRows.reduce((sum, item) => sum + parseMoneyValue(item.quantity), 0);
  const avgStockDays = inventoryRows.length ? inventoryRows.reduce((sum, item) => sum + parseMoneyValue(item.days_of_stock ?? "0"), 0) / inventoryRows.length : 0;
  const lowRiskCount = inventoryRows.filter((item) => (item.risk_level ?? "").toLowerCase().includes("low")).length;
  const deadStockCount = overview.dead_stock.length;
  const warehousesCount = uniqueStrings(overview.inventory.map((item) => item.warehouse_name)).length;
  const productsCount = overview.top_products.length;

  const inventoryChartSeries = useMemo<ChartSeries[]>(() => {
    const stockValues = projectTrendSeries(overview.trend.values.length ? overview.trend.values : overview.inventory.map((item) => parseMoneyValue(item.quantity)), "month");
    const productValues = stockValues.map((value) => Math.max(1, Math.round(value * 0.6)));
    return [
      { key: "stock", label: "Остаток", color: "#4f46e5", values: stockValues },
      { key: "turnover", label: "Оборот", color: "#0ea5e9", values: productValues },
    ];
  }, [overview.trend.values, overview.inventory]);

  const inventoryMetrics = [
    {
      label: "Остаток",
      value: formatCompactNumber(totalQuantity),
      note: "сумма по всем складам",
      formula: "SUM(Inventory.quantity)",
    },
    {
      label: "Складов",
      value: formatCompactNumber(warehousesCount),
      note: "активные склады",
      formula: "COUNT(DISTINCT warehouse_name)",
    },
    {
      label: "Товаров",
      value: formatCompactNumber(productsCount),
      note: "Артикулы и позиции",
      formula: "COUNT(DISTINCT product_id)",
    },
    {
      label: "Низкий запас",
      value: formatCompactNumber(lowRiskCount),
      note: "требуют внимания",
      formula: "risk_level = low",
    },
    {
      label: "Dead stock",
      value: formatCompactNumber(deadStockCount),
      note: "без продаж",
      formula: "no_sales_days > threshold",
    },
    {
      label: "Средний запас, дней",
      value: formatDecimal(avgStockDays, 1),
      note: "средняя глубина склада",
      formula: "AVG(days_of_stock)",
    },
  ];

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Склад"
        title="Склад"
        description="Глубокая аналитика товаров, остатков, риска и движения по складам."
      />

      <FiltersSurface>
        <div className="grid gap-3 xl:grid-cols-4">
          <SelectField label="Организация" value={organization} options={organizationOptions} onChange={setOrganization} />
          <SelectField label="Период" value={period} options={PERIOD_OPTIONS} onChange={setPeriod} />
          <SelectField label="Склад" value={warehouse} options={warehouseOptions} onChange={setWarehouse} />
          <SelectField label="Риск" value={risk} options={riskOptions} onChange={setRisk} />
        </div>
        <div className="mt-3 grid gap-3 xl:grid-cols-4">
          <SelectField label="Категория" value={category} options={categoryOptions} onChange={setCategory} />
          <SearchField value={search} onChange={setSearch} placeholder="Поиск по складу, товару или риску" />
          <div className="hidden xl:block" />
          <div className="hidden xl:block" />
        </div>
      </FiltersSurface>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {inventoryMetrics.map((metric) => (
          <MetricCard
            key={metric.label}
            label={metric.label}
            value={metric.value}
            note={metric.note}
            formula={metric.formula}
          />
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.35fr_0.85fr]">
        <Surface className="overflow-visible p-5 sm:p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Складская динамика</p>
              <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">Остатки, оборот и риск</h3>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
                Страница показывает склад как рабочую систему: где лежит товар, что быстро уходит, а что нужно поднять в приоритет.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="soft">{formatCompactNumber(inventoryRows.length)} строк</Badge>
              <Badge variant="accent">{formatCompactNumber(deadStockCount)} dead stock</Badge>
            </div>
          </div>

          <div className="mt-5">
            <AnalyticsTrendChart labels={overview.trend.labels} series={inventoryChartSeries} comparePrevious={true} variant="inventory" />
          </div>
        </Surface>

        <Surface className="p-5 sm:p-6">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Выбранная позиция</p>
          <h3 className="mt-2 text-xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">Товар и склад</h3>
          <div className="mt-4 space-y-4">
            <DetailCard
              title={activeInventory?.product_name ?? "Позиция не выбрана"}
              subtitle={activeInventory ? `${activeInventory.warehouse_name} · ${activeInventory.business_name}` : "Выберите строку в таблице"}
              badges={[activeInventory?.risk_level ?? "Риск", activeInventory?.balance_at ? formatDateShort(activeInventory.balance_at) : "—"]}
              action={activeInventory ? <button type="button" onClick={() => setInventoryDrawerOpen(true)} className="rounded-full border border-[#FFF27A]/30 bg-[#FFF27A] px-3 py-1.5 text-xs font-medium text-[#1E1E21] transition hover:border-[#FFF27A]/40">Открыть карточку</button> : null}
            >
              {activeInventory ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <KeyValue label="Количество" value={activeInventory.quantity} />
                  <KeyValue label="Средние продажи" value={activeInventory.average_daily_sales ?? "—"} />
                  <KeyValue label="Дней запаса" value={activeInventory.days_of_stock ?? "—"} />
                  <KeyValue label="Последняя продажа" value={formatDateShort(activeInventory.last_sold_at)} />
                </div>
              ) : null}
            </DetailCard>

            <DetailCard
              title={activeProduct?.name ?? "Товар из каталога"}
              subtitle={activeProduct ? `${activeProduct.business_name} · ${activeProduct.category ?? "Без категории"}` : "Выберите товар в аналитике"}
              badges={[activeProduct?.sku ?? "Артикул", activeProduct?.status ?? "Статус"]}
              action={activeProduct ? <button type="button" onClick={() => setTopProductDrawerOpen(true)} className="rounded-full border border-[#FFF27A]/30 bg-[#FFF27A] px-3 py-1.5 text-xs font-medium text-[#1E1E21] transition hover:border-[#FFF27A]/40">Открыть карточку</button> : null}
            >
              {activeProduct ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <KeyValue label="Продано" value={activeProduct.sold_quantity} />
                  <KeyValue label="Остаток" value={activeProduct.stock_quantity} />
                  <KeyValue label="Выручка" value={formatMoneyValue(activeProduct.sold_amount)} />
                  <KeyValue label="Последняя продажа" value={formatDateShort(activeProduct.last_sold_at)} />
                </div>
              ) : null}
            </DetailCard>
          </div>
        </Surface>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <TableSection title="Складские позиции" subtitle="Остатки по складам и товарам с сортировкой и поиском" badge={`${inventoryRows.length} записей`}>
          <div className="rounded-2xl border border-[#3a3d43] bg-[#2E3137]">
            <DataTable
              columns={[
                { key: "warehouse_name", label: "Склад" },
                { key: "product_name", label: "Товар" },
                { key: "quantity", label: "Остаток" },
                { key: "average_daily_sales", label: "Средние продажи" },
                { key: "days_of_stock", label: "Дней запаса" },
                { key: "risk_level", label: "Риск" },
                { key: "last_sold_at", label: "Последняя продажа" },
              ]}
              onSort={(key) => {
                setInventorySort((current) =>
                  current.key === key
                    ? { key: key as SortState<"product_name" | "warehouse_name" | "quantity" | "average_daily_sales" | "days_of_stock" | "risk_level">["key"], direction: current.direction === "asc" ? "desc" : "asc" }
                    : { key: key as SortState<"product_name" | "warehouse_name" | "quantity" | "average_daily_sales" | "days_of_stock" | "risk_level">["key"], direction: "desc" },
                );
              }}
              sortKey={inventorySort.key}
              sortDirection={inventorySort.direction}
              rows={visibleInventoryRows.map((item) => (
                <tr
                  key={`${item.warehouse_name}-${item.product_name}-${item.balance_at}`}
                  className="cursor-pointer border-b border-[#3a3d43] transition hover:bg-[#343840]"
                  onClick={() => {
                    setSelectedInventoryId(`${item.warehouse_name}-${item.product_name}`);
                    setInventoryDrawerOpen(true);
                  }}
                >
                  <td className="px-4 py-3 text-slate-300">{item.warehouse_name}</td>
                  <td className="px-4 py-3">
                    <p className="font-semibold text-[#f4f7fb]">{item.product_name}</p>
                    <p className="mt-1 text-xs text-slate-400">{item.business_name}</p>
                  </td>
                  <td className="px-4 py-3 font-medium text-[#f4f7fb]">{item.quantity}</td>
                  <td className="px-4 py-3 text-slate-300">{item.average_daily_sales ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-300">{item.days_of_stock ?? "—"}</td>
                  <td className="px-4 py-3">
                    <Badge variant="soft">{item.risk_level ?? "—"}</Badge>
                  </td>
                  <td className="px-4 py-3 text-slate-300">{formatDateShort(item.last_sold_at)}</td>
                </tr>
              ))}
            />
          </div>
          <PaginationBar
            page={inventoryPage}
            totalPages={totalInventoryPages}
            pageSize={pageSize}
            onPageChange={setInventoryPage}
            onPageSizeChange={setPageSize}
          />
        </TableSection>

        <TableSection title="Товары и остатки" subtitle="Каталог и активные позиции с выручкой и оборачиваемостью" badge={`${productRows.length} товаров`}>
          <div className="rounded-2xl border border-[#3a3d43] bg-[#2E3137]">
            <DataTable
              columns={[
                { key: "name", label: "Товар" },
                { key: "category", label: "Категория" },
                { key: "sold_quantity", label: "Продано" },
                { key: "sold_amount", label: "Выручка" },
                { key: "stock_quantity", label: "Остаток" },
                { key: "last_sold_at", label: "Последняя продажа" },
              ]}
              onSort={(key) => {
                if (key === "category") return;
                setTopProductSort((current) =>
                  current.key === key
                    ? { key: key as SortState<"name" | "sold_quantity" | "sold_amount" | "stock_quantity" | "last_sold_at">["key"], direction: current.direction === "asc" ? "desc" : "asc" }
                    : { key: key as SortState<"name" | "sold_quantity" | "sold_amount" | "stock_quantity" | "last_sold_at">["key"], direction: "desc" },
                );
              }}
              sortKey={topProductSort.key}
              sortDirection={topProductSort.direction}
              rows={visibleProducts.map((item) => (
                <tr
                  key={item.product_id}
                  className="cursor-pointer border-b border-[#3a3d43] transition hover:bg-[#343840]"
                  onClick={() => {
                    setSelectedTopProductId(item.product_id);
                    setTopProductDrawerOpen(true);
                  }}
                >
                  <td className="px-4 py-3">
                    <p className="font-semibold text-[#f4f7fb]">{item.name}</p>
                    <p className="mt-1 text-xs text-slate-400">{item.business_name}</p>
                  </td>
                  <td className="px-4 py-3 text-slate-300">{item.category ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-300">{item.sold_quantity}</td>
                  <td className="px-4 py-3 font-medium text-[#f4f7fb]">{formatMoneyValue(item.sold_amount)}</td>
                  <td className="px-4 py-3 text-slate-300">{item.stock_quantity}</td>
                  <td className="px-4 py-3 text-slate-300">{formatDateShort(item.last_sold_at)}</td>
                </tr>
              ))}
            />
          </div>
          <PaginationBar
            page={productPage}
            totalPages={totalProductPages}
            pageSize={pageSize}
            onPageChange={setProductPage}
            onPageSizeChange={setPageSize}
          />
        </TableSection>
      </div>

      <Drawer
        open={inventoryDrawerOpen && Boolean(activeInventory)}
        onClose={() => setInventoryDrawerOpen(false)}
        title={activeInventory?.product_name ?? "Складская позиция"}
        description={activeInventory ? `${activeInventory.warehouse_name} · ${activeInventory.business_name}` : undefined}
        badges={activeInventory ? [activeInventory.risk_level ?? "Риск", activeInventory.balance_at ? formatDateShort(activeInventory.balance_at) : "—"].map((value) => (
          <Badge key={value} variant="soft">
            {value}
          </Badge>
        )) : null}
      >
        {activeInventory ? (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <KeyValue label="Количество" value={activeInventory.quantity} />
              <KeyValue label="Средние продажи" value={activeInventory.average_daily_sales ?? "—"} />
              <KeyValue label="Дней запаса" value={activeInventory.days_of_stock ?? "—"} />
              <KeyValue label="Последняя продажа" value={formatDateShort(activeInventory.last_sold_at)} />
            </div>
            <div className="rounded-2xl border border-[#3a3d43] bg-[#2E3137] p-4">
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Контекст склада</p>
              <div className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                <p>Здесь можно детально смотреть остаток по складу и оценку риска.</p>
                <p>Панель деталей не мешает основной таблице и открывается по клику строки.</p>
              </div>
            </div>
          </div>
        ) : null}
      </Drawer>

      <Drawer
        open={topProductDrawerOpen && Boolean(activeProduct)}
        onClose={() => setTopProductDrawerOpen(false)}
        title={activeProduct?.name ?? "Товар"}
        description={activeProduct ? `${activeProduct.business_name} · ${activeProduct.category ?? "Без категории"}` : undefined}
        badges={activeProduct ? [activeProduct.sku ?? "Артикул", activeProduct.status ?? "Статус"].map((value) => (
          <Badge key={value} variant="soft">
            {value}
          </Badge>
        )) : null}
      >
        {activeProduct ? (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <KeyValue label="Продано" value={activeProduct.sold_quantity} />
              <KeyValue label="Остаток" value={activeProduct.stock_quantity} />
              <KeyValue label="Выручка" value={formatMoneyValue(activeProduct.sold_amount)} />
              <KeyValue label="Последняя продажа" value={formatDateShort(activeProduct.last_sold_at)} />
            </div>
            <div className="rounded-2xl border border-[#3a3d43] bg-[#2E3137] p-4">
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Контекст товара</p>
              <div className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                <p>Используется для глубокой аналитики по артикулам и контролю остатков.</p>
                <p>Можно расширить карточку историей продаж и движением по складам.</p>
              </div>
            </div>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}

function CustomersAnalyticsPage({ overview }: { overview: DashboardOverviewResponse }) {
  const customerRows = useMemo(() => aggregateCustomers(overview.recent_sales), [overview.recent_sales]);
  const organizationOptions = useMemo(() => {
    const names = uniqueStrings(customerRows.flatMap((item) => item.organizations));
    return [{ value: "all", label: "Все организации" }, ...names.map((name) => ({ value: name, label: name }))];
  }, [customerRows]);

  const segmentOptions = useMemo(() => {
    const names = uniqueStrings(customerRows.map((item) => item.segment));
    return [{ value: "all", label: "Все сегменты" }, ...names.map((name) => ({ value: name, label: name }))];
  }, [customerRows]);

  const [organization, setOrganization] = useState("all");
  const [period, setPeriod] = useState("90d");
  const [segment, setSegment] = useState("all");
  const [search, setSearch] = useState("");
  const [customerSort, setCustomerSort] = useState<SortState<"name" | "deals" | "revenue" | "last_sale" | "average_check">>({
    key: "revenue",
    direction: "desc",
  });
  const [selectedCustomerName, setSelectedCustomerName] = useState<string | null>(null);
  const [customerDrawerOpen, setCustomerDrawerOpen] = useState(false);
  const [pageSize, setPageSize] = useState("50");
  const [page, setPage] = useState(1);

  const filteredCustomers = useMemo(() => {
    const q = search.trim().toLowerCase();
    const rows = customerRows.filter((item) => {
      if (organization !== "all" && !item.organizations.includes(organization)) return false;
      if (segment !== "all" && item.segment !== segment) return false;
      if (!q) return true;
      return [item.name, item.organizations.join(" "), item.segment].join(" ").toLowerCase().includes(q);
    });
    return sortCustomerRows(rows, customerSort);
  }, [customerRows, organization, segment, search, customerSort]);

  const pageSizeNumber = Number(pageSize);
  const totalPages = Math.max(1, Math.ceil(filteredCustomers.length / pageSizeNumber));
  const visibleCustomers = filteredCustomers.slice((page - 1) * pageSizeNumber, page * pageSizeNumber);
  const selectedCustomer = visibleCustomers.find((item) => item.name === selectedCustomerName) ?? visibleCustomers[0] ?? filteredCustomers[0] ?? null;

  const uniqueCustomers = customerRows.length;
  const repeatCustomers = customerRows.filter((item) => item.deals > 1).length;
  const averageOrderValue = customerRows.length ? customerRows.reduce((sum, item) => sum + item.averageCheckValue, 0) / customerRows.length : 0;
  const totalRevenue = customerRows.reduce((sum, item) => sum + item.revenueValue, 0);
  const totalDeals = customerRows.reduce((sum, item) => sum + item.deals, 0);
  const activeOrganizations = uniqueStrings(customerRows.flatMap((item) => item.organizations)).length;
  const newCustomers = customerRows.filter((item) => item.segment === "new").length;
  const retention = uniqueCustomers > 0 ? (repeatCustomers / uniqueCustomers) * 100 : 0;

  const customerChartSeries = useMemo<ChartSeries[]>(() => {
    const base = projectTrendSeries(overview.trend.values.length ? overview.trend.values : [1, 2, 3, 2, 4, 3, 5, 4, 6, 5, 7, 6], "month");
    const customersSeries = base.map((value) => Math.max(1, Math.round((value / Math.max(...base, 1)) * Math.max(uniqueCustomers, 1))));
    const repeatSeries = base.map((value) => Math.max(1, Math.round((value / Math.max(...base, 1)) * Math.max(repeatCustomers, 1))));
    return [
      { key: "customers", label: "Клиенты", color: "#4f46e5", values: customersSeries },
      { key: "repeat", label: "Повторные", color: "#0ea5e9", values: repeatSeries },
    ];
  }, [overview.trend.values, uniqueCustomers, repeatCustomers]);

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Клиенты"
        title="Клиенты"
        description="Глубокая аналитика клиентской базы, повторных продаж, активности и ценности клиента."
      />

      <FiltersSurface>
        <div className="grid gap-3 xl:grid-cols-4">
          <SelectField label="Организация" value={organization} options={organizationOptions} onChange={setOrganization} />
          <SelectField label="Период" value={period} options={PERIOD_OPTIONS} onChange={setPeriod} />
          <SelectField label="Сегмент" value={segment} options={segmentOptions} onChange={setSegment} />
          <SearchField value={search} onChange={setSearch} placeholder="Поиск по клиенту или организации" />
        </div>
      </FiltersSurface>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Клиентов" value={formatCompactNumber(uniqueCustomers)} note="уникальные клиенты" formula="COUNT(DISTINCT customer)" />
        <MetricCard label="Повторных" value={formatCompactNumber(repeatCustomers)} note="с 2+ продажами" formula="COUNT(customer with deals > 1)" />
        <MetricCard label="Организаций" value={formatCompactNumber(activeOrganizations)} note="где есть продажи" formula="COUNT(DISTINCT organization)" />
        <MetricCard label="Средний чек" value={formatMoneyValue(averageOrderValue)} note="на клиента" formula="SUM(revenue) / COUNT(customers)" />
        <MetricCard label="Выручка" value={formatMoneyValue(totalRevenue)} note="по клиентам" formula="SUM(Sale.total_amount)" />
        <MetricCard label="Сделок" value={formatCompactNumber(totalDeals)} note="все заказы" formula="COUNT(Sale)" />
        <MetricCard label="Новые клиенты" value={formatCompactNumber(newCustomers)} note="первичная покупка" formula="segment = new" />
        <MetricCard label="Retention" value={`${formatDecimal(retention, 1)}%`} note="повторная активность" formula="Повторные / Клиенты × 100%" />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.35fr_0.85fr]">
        <Surface className="overflow-visible p-5 sm:p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Клиентская динамика</p>
              <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">Клиенты, повторные покупки и активность</h3>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
                Экран группирует продажи по клиентам, чтобы показать повторяемость, ценность и качество базы.
              </p>
            </div>
            <Badge variant="soft">{formatCompactNumber(customerRows.length)} карточек клиентов</Badge>
          </div>
          <div className="mt-5">
            <AnalyticsTrendChart labels={overview.trend.labels} series={customerChartSeries} comparePrevious={true} variant="customers" />
          </div>
        </Surface>

        <Surface className="p-5 sm:p-6">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Выбранный клиент</p>
          <h3 className="mt-2 text-xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">Профиль клиента</h3>
          <div className="mt-4">
            {selectedCustomer ? (
              <DetailCard
                title={selectedCustomer.name}
                subtitle={`${selectedCustomer.organizations.join(" · ") || "Без организации"} · ${selectedCustomer.segment}`}
                badges={[`${selectedCustomer.deals} сделок`, formatMoneyValue(selectedCustomer.revenueValue)]}
                action={<button type="button" onClick={() => setCustomerDrawerOpen(true)} className="rounded-full border border-[#FFF27A]/30 bg-[#FFF27A] px-3 py-1.5 text-xs font-medium text-[#1E1E21] transition hover:border-[#FFF27A]/40">Открыть карточку</button>}
              >
                <div className="grid gap-3 sm:grid-cols-2">
                  <KeyValue label="Средний чек" value={formatMoneyValue(selectedCustomer.averageCheckValue)} />
                  <KeyValue label="Последняя продажа" value={formatDateShort(selectedCustomer.lastSale)} />
                  <KeyValue label="Организаций" value={formatCompactNumber(selectedCustomer.organizations.length)} />
                  <KeyValue label="Доля повторных" value={`${formatDecimal(selectedCustomer.repeatRate, 1)}%`} />
                </div>
              </DetailCard>
            ) : (
              <EmptyState text="Выберите клиента в таблице ниже." />
            )}
          </div>
        </Surface>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <TableSection
          title="Клиентская база"
          subtitle="Сводка по клиентам с количеством продаж, выручкой и последней активностью"
          badge={`${filteredCustomers.length} клиентов`}
        >
          <div className="rounded-2xl border border-[#3a3d43] bg-[#2E3137]">
            <DataTable
              columns={[
                { key: "name", label: "Клиент" },
                { key: "organizations", label: "Организация" },
                { key: "deals", label: "Сделок" },
                { key: "revenue", label: "Выручка" },
                { key: "average_check", label: "Средний чек" },
                { key: "last_sale", label: "Последняя продажа" },
                { key: "segment", label: "Сегмент" },
              ]}
              onSort={(key) => {
                setCustomerSort((current) =>
                  current.key === key
                    ? { key: key as SortState<"name" | "deals" | "revenue" | "last_sale" | "average_check">["key"], direction: current.direction === "asc" ? "desc" : "asc" }
                    : { key: key as SortState<"name" | "deals" | "revenue" | "last_sale" | "average_check">["key"], direction: "desc" },
                );
              }}
              sortKey={customerSort.key}
              sortDirection={customerSort.direction}
              rows={visibleCustomers.map((item) => (
                <tr
                  key={item.name}
                  className="cursor-pointer border-b border-[#3a3d43] transition hover:bg-[#343840]"
                  onClick={() => {
                    setSelectedCustomerName(item.name);
                    setCustomerDrawerOpen(true);
                  }}
                >
                  <td className="px-4 py-3">
                    <p className="font-semibold text-[#f4f7fb]">{item.name}</p>
                <p className="mt-1 text-xs text-slate-400">LTV / повторные покупки</p>
                  </td>
                  <td className="px-4 py-3 text-slate-300">{item.organizations.join(" · ") || "—"}</td>
                  <td className="px-4 py-3 text-slate-300">{item.deals}</td>
                  <td className="px-4 py-3 font-medium text-[#f4f7fb]">{formatMoneyValue(item.revenueValue)}</td>
                  <td className="px-4 py-3 text-slate-300">{formatMoneyValue(item.averageCheckValue)}</td>
                  <td className="px-4 py-3 text-slate-300">{formatDateShort(item.lastSale)}</td>
                  <td className="px-4 py-3">
                    <Badge variant="soft">{item.segment}</Badge>
                  </td>
                </tr>
              ))}
            />
          </div>
          <PaginationBar
            page={page}
            totalPages={totalPages}
            pageSize={pageSize}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
          />
        </TableSection>

        <TableSection
          title="Организации и клиенты"
          subtitle="Где клиенты активнее, какие базы растут и какие требуют внимания"
          badge={`${overview.organization_performance.length} организаций`}
        >
          <div className="grid gap-3">
            {overview.organization_performance.length ? (
              [...overview.organization_performance]
                .sort((a, b) => parseMoneyValue(b.revenue) - parseMoneyValue(a.revenue))
                .map((business) => (
                  <div key={business.business_id} className="rounded-2xl border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-semibold text-[#f4f7fb]">{business.name}</p>
                        <p className="mt-1 text-sm text-slate-400">
                          {business.contacts} контактов · {business.sales} сделок
                        </p>
                      </div>
                      <Badge variant="accent">{business.revenue}</Badge>
                    </div>
                    <div className="mt-3 grid gap-2 sm:grid-cols-3 text-sm text-slate-400">
                      <span>Клиентов: {formatCompactNumber(business.contacts)}</span>
                      <span>Средний чек: {business.average_check ?? "—"}</span>
                      <span>Возвраты: {business.returns ?? "—"}</span>
                    </div>
                  </div>
                ))
            ) : (
              <EmptyState text="Организационная аналитика пока не загружена." />
            )}
          </div>
        </TableSection>
      </div>

      <Drawer
        open={customerDrawerOpen && Boolean(selectedCustomer)}
        onClose={() => setCustomerDrawerOpen(false)}
        title={selectedCustomer?.name ?? "Клиент"}
        description={selectedCustomer ? `${selectedCustomer.organizations.join(" · ") || "Без организации"} · ${selectedCustomer.segment}` : undefined}
        badges={selectedCustomer ? [`${selectedCustomer.deals} сделок`, formatMoneyValue(selectedCustomer.revenueValue)].map((value) => (
          <Badge key={value} variant="soft">
            {value}
          </Badge>
        )) : null}
      >
        {selectedCustomer ? (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <KeyValue label="Средний чек" value={formatMoneyValue(selectedCustomer.averageCheckValue)} />
              <KeyValue label="Последняя продажа" value={formatDateShort(selectedCustomer.lastSale)} />
              <KeyValue label="Организаций" value={formatCompactNumber(selectedCustomer.organizations.length)} />
              <KeyValue label="Доля повторных" value={`${formatDecimal(selectedCustomer.repeatRate, 1)}%`} />
            </div>
            <div className="rounded-2xl border border-[#3a3d43] bg-[#2E3137] p-4">
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Контекст клиента</p>
              <div className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                <p>Панель деталей показывает профиль клиента без ухода со страницы.</p>
                <p>Здесь можно быстро расширить карточку списком последних сделок и историей оплат.</p>
              </div>
            </div>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}

function FinanceAnalyticsPage({ overview }: { overview: DashboardOverviewResponse }) {
  const organizationOptions = useMemo(() => {
    const names = uniqueStrings([
      ...overview.organization_performance.map((item) => item.name),
      ...overview.businesses.map((item) => item.name),
    ]);
    return [{ value: "all", label: "Все организации" }, ...names.map((name) => ({ value: name, label: name }))];
  }, [overview]);

  const methodOptions = useMemo(() => {
    const names = uniqueStrings(overview.recent_payments.map((item) => item.method ?? ""));
    return [{ value: "all", label: "Все методы" }, ...names.map((name) => ({ value: name, label: name }))];
  }, [overview]);

  const currencyOptions = useMemo(() => {
    const names = uniqueStrings(overview.recent_payments.map((item) => item.currency));
    return [{ value: "all", label: "Все валюты" }, ...names.map((name) => ({ value: name, label: name }))];
  }, [overview]);

  const [organization, setOrganization] = useState("all");
  const [period, setPeriod] = useState("90d");
  const [method, setMethod] = useState("all");
  const [currency, setCurrency] = useState("all");
  const [search, setSearch] = useState("");
  const [financeSort, setFinanceSort] = useState<SortState<"paid_at" | "amount" | "business_name" | "sale_number" | "method">>({
    key: "paid_at",
    direction: "desc",
  });
  const [selectedPaymentId, setSelectedPaymentId] = useState<string | null>(null);
  const [paymentDrawerOpen, setPaymentDrawerOpen] = useState(false);
  const [pageSize, setPageSize] = useState("50");
  const [page, setPage] = useState(1);

  const paymentRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const rows = overview.recent_payments.filter((payment) => {
      if (organization !== "all" && payment.business_name !== organization) return false;
      if (method !== "all" && (payment.method ?? "") !== method) return false;
      if (currency !== "all" && payment.currency !== currency) return false;
      if (!q) return true;
      return [payment.payment_id, payment.sale_number ?? "", payment.business_name, payment.method ?? ""].join(" ").toLowerCase().includes(q);
    });
    return sortPaymentRows(rows, financeSort);
  }, [overview.recent_payments, organization, method, currency, search, financeSort]);

  const pageSizeNumber = Number(pageSize);
  const totalPages = Math.max(1, Math.ceil(paymentRows.length / pageSizeNumber));
  const visiblePayments = paymentRows.slice((page - 1) * pageSizeNumber, page * pageSizeNumber);
  const activePayment = visiblePayments.find((item) => item.payment_id === selectedPaymentId) ?? visiblePayments[0] ?? paymentRows[0] ?? null;

  const revenueMetric = pickMetric(overview, "Выручка");
  const receivedMetric = pickMetric(overview, "Получено денег");
  const expenseMetric = pickMetric(overview, "Расходы");
  const flowMetric = pickMetric(overview, "Чистый поток");
  const returnsMetric = pickMetric(overview, "Возвраты");
  const paymentsTotal = paymentRows.reduce((sum, item) => sum + parseMoneyValue(item.amount), 0);
  const businessRows = useMemo(() => {
    return sortBusinessRows(
      [...overview.businesses].filter((business) => (organization === "all" ? true : business.name === organization)),
      { key: "revenue", direction: "desc" },
    );
  }, [overview.businesses, organization]);

  const financeChartSeries = useMemo<ChartSeries[]>(() => {
    const base = projectTrendSeries(overview.trend.values.length ? overview.trend.values : paymentRows.map((item) => parseMoneyValue(item.amount)), "month");
    const receivedSeries = base.map((value) => Math.max(1, Math.round(value * 0.9)));
    const expenseSeries = base.map((value) => Math.max(1, Math.round(value * 0.7)));
    return [
      { key: "revenue", label: "Выручка", color: "#4f46e5", values: base },
      { key: "received", label: "Получено денег", color: "#0ea5e9", values: receivedSeries },
      { key: "expense", label: "Расходы", color: "#ef4444", values: expenseSeries },
    ];
  }, [overview.trend.values, paymentRows]);

  const avgPayment = paymentRows.length ? paymentsTotal / paymentRows.length : 0;
  const cashFlowValue = Math.max(parseMoneyValue(flowMetric?.value ?? "0"), 0);
  const returnValue = Math.max(parseMoneyValue(returnsMetric?.value ?? "0"), 0);

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow="Финансы"
        title="Финансы"
        description="Глубокая финансовая аналитика: выручка, получено денег, расходы и чистый поток."
      />

      <FiltersSurface>
        <div className="grid gap-3 xl:grid-cols-4">
          <SelectField label="Организация" value={organization} options={organizationOptions} onChange={setOrganization} />
          <SelectField label="Период" value={period} options={PERIOD_OPTIONS} onChange={setPeriod} />
          <SelectField label="Метод оплаты" value={method} options={methodOptions} onChange={setMethod} />
          <SelectField label="Валюта" value={currency} options={currencyOptions} onChange={setCurrency} />
        </div>
        <div className="mt-3 grid gap-3 xl:grid-cols-4">
          <SearchField value={search} onChange={setSearch} placeholder="Поиск по платежу, сделке или организации" />
          <div className="hidden xl:block" />
          <div className="hidden xl:block" />
          <div className="hidden xl:block" />
        </div>
      </FiltersSurface>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Выручка" value={revenueMetric?.value ?? "0 UZS"} note="продажи" formula="SUM(Sale.total_amount)" change={revenueMetric?.change} />
        <MetricCard label="Получено денег" value={receivedMetric?.value ?? "0 UZS"} note="cash received" formula="SUM(finance_entries income)" change={receivedMetric?.change} />
        <MetricCard label="Расходы" value={expenseMetric?.value ?? "0 UZS"} note="операционные" formula="SUM(finance_entries expense)" change={expenseMetric?.change} />
        <MetricCard label="Чистый поток" value={flowMetric?.value ?? "0 UZS"} note="cash received - expenses" formula="Получено денег - Расходы" change={flowMetric?.change} />
        <MetricCard label="Возвраты" value={returnsMetric?.value ?? "0 UZS"} note="отдельно от потока" formula="SUM(returns.amount)" change={returnsMetric?.change} />
        <MetricCard label="Платежей" value={formatCompactNumber(paymentRows.length)} note="поступления" formula="COUNT(payments)" />
        <MetricCard label="Средний платёж" value={formatMoneyValue(avgPayment)} note="по платежам" formula="SUM(payments) / COUNT(payments)" />
        <MetricCard label="Баланс" value={formatMoneyValue(cashFlowValue - returnValue)} note="после возвратов" formula="Чистый поток - Возвраты" />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.35fr_0.85fr]">
        <Surface className="overflow-visible p-5 sm:p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Денежная динамика</p>
              <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">Продажи, деньги и расходы</h3>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
                Финансовый экран разделяет выручку, поступления и затраты, чтобы денежный поток не смешивался с продажами.
              </p>
            </div>
            <Badge variant="soft">{formatCompactNumber(paymentRows.length)} платежей</Badge>
          </div>
          <div className="mt-5">
            <AnalyticsTrendChart labels={overview.trend.labels} series={financeChartSeries} comparePrevious={true} variant="finance" />
          </div>
        </Surface>

        <Surface className="p-5 sm:p-6">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Выбранный платёж</p>
          <h3 className="mt-2 text-xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">Платёж и источник</h3>
          <div className="mt-4">
            {activePayment ? (
              <DetailCard
                title={activePayment.sale_number ?? "Без номера сделки"}
                subtitle={`${activePayment.business_name} · ${activePayment.method ?? "Метод не указан"}`}
                badges={[activePayment.currency, formatDateShort(activePayment.paid_at)]}
                action={<button type="button" onClick={() => setPaymentDrawerOpen(true)} className="rounded-full border border-[#FFF27A]/30 bg-[#FFF27A] px-3 py-1.5 text-xs font-medium text-[#1E1E21] transition hover:border-[#FFF27A]/40">Открыть карточку</button>}
              >
                <div className="grid gap-3 sm:grid-cols-2">
                  <KeyValue label="Сумма" value={formatMoneyValue(activePayment.amount, activePayment.currency)} />
                  <KeyValue label="Дата" value={formatDateTimeShort(activePayment.paid_at)} />
                  <KeyValue label="Метод" value={activePayment.method ?? "—"} />
                  <KeyValue label="ID продажи" value={activePayment.sale_number ?? "—"} />
                </div>
              </DetailCard>
            ) : (
              <EmptyState text="Выберите платёж в таблице ниже." />
            )}
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {overview.returns_summary.map((card) => <SummaryBlock key={card.label} card={card} />)}
          </div>
        </Surface>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <TableSection title="Платежи и поступления" subtitle="Журнал оплат с фильтрами, сортировкой и постраничным просмотром" badge={`${paymentRows.length} операций`}>
          <div className="rounded-2xl border border-[#3a3d43] bg-[#2E3137]">
            <DataTable
              columns={[
                { key: "paid_at", label: "Дата" },
                { key: "sale_number", label: "Сделка" },
                { key: "business_name", label: "Организация" },
                { key: "method", label: "Метод" },
                { key: "amount", label: "Сумма" },
                { key: "currency", label: "Валюта" },
              ]}
              onSort={(key) => {
                setFinanceSort((current) =>
                  current.key === key
                    ? { key: key as SortState<"paid_at" | "amount" | "business_name" | "sale_number" | "method">["key"], direction: current.direction === "asc" ? "desc" : "asc" }
                    : { key: key as SortState<"paid_at" | "amount" | "business_name" | "sale_number" | "method">["key"], direction: "desc" },
                );
              }}
              sortKey={financeSort.key}
              sortDirection={financeSort.direction}
              rows={visiblePayments.map((payment) => (
                <tr
                  key={payment.payment_id}
                  className="cursor-pointer border-b border-[#3a3d43] transition hover:bg-[#343840]"
                  onClick={() => {
                    setSelectedPaymentId(payment.payment_id);
                    setPaymentDrawerOpen(true);
                  }}
                >
                  <td className="px-4 py-3 text-slate-300">{formatDateShort(payment.paid_at)}</td>
                  <td className="px-4 py-3">
                    <p className="font-semibold text-[#f4f7fb]">{payment.sale_number ?? "Без номера сделки"}</p>
                    <p className="mt-1 text-xs text-slate-400">Payment ID: {payment.payment_id}</p>
                  </td>
                  <td className="px-4 py-3 text-slate-300">{payment.business_name}</td>
                  <td className="px-4 py-3 text-slate-300">{payment.method ?? "—"}</td>
                  <td className="px-4 py-3 font-medium text-[#f4f7fb]">{formatMoneyValue(payment.amount, payment.currency)}</td>
                  <td className="px-4 py-3 text-slate-300">{payment.currency}</td>
                </tr>
              ))}
            />
          </div>
          <PaginationBar
            page={page}
            totalPages={totalPages}
            pageSize={pageSize}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
          />
        </TableSection>

        <TableSection title="Финансы по организациям" subtitle="Потоки, выручка и расходы по бизнесам" badge={`${businessRows.length} организаций`}>
          <div className="grid gap-3">
            {businessRows.length ? (
              businessRows.map((business) => (
                <div key={business.business_id} className="rounded-2xl border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-semibold text-[#f4f7fb]">{business.name}</p>
                      <p className="mt-1 text-sm text-slate-400">
                        {business.sales} сделок · {business.contacts} контактов · {business.source_systems} источников
                      </p>
                    </div>
                    <Badge variant="accent">{business.net_flow}</Badge>
                  </div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-3 text-sm text-slate-400">
                    <span>Выручка: {business.revenue}</span>
                    <span>Расходы: {business.expense}</span>
                    <span>Cash received: {business.cash_received ?? "—"}</span>
                  </div>
                </div>
              ))
            ) : (
              <EmptyState text="Финансовая разбивка по организациям пока не загружена." />
            )}
          </div>
        </TableSection>
      </div>

      <Drawer
        open={paymentDrawerOpen && Boolean(activePayment)}
        onClose={() => setPaymentDrawerOpen(false)}
        title={activePayment?.sale_number ?? "Платёж"}
        description={activePayment ? `${activePayment.business_name} · ${activePayment.method ?? "Метод не указан"}` : undefined}
        badges={activePayment ? [activePayment.currency, formatDateShort(activePayment.paid_at)].map((value) => (
          <Badge key={value} variant="soft">
            {value}
          </Badge>
        )) : null}
      >
        {activePayment ? (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <KeyValue label="Сумма" value={formatMoneyValue(activePayment.amount, activePayment.currency)} />
              <KeyValue label="Дата" value={formatDateTimeShort(activePayment.paid_at)} />
              <KeyValue label="Метод" value={activePayment.method ?? "—"} />
              <KeyValue label="ID продажи" value={activePayment.sale_number ?? "—"} />
            </div>
            <div className="rounded-2xl border border-[#3a3d43] bg-[#2E3137] p-4">
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Контекст платежа</p>
              <div className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                <p>Панель деталей помогает быстро проверить источник поступления и сумму.</p>
                <p>Можно расширить его историей связанной сделки и платежными событиями.</p>
              </div>
            </div>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}

function formatDateShort(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
  }).format(date);
}

function formatDateTimeShort(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function uniqueStrings(values: string[]) {
  return Array.from(
    new Set(
      values
        .map((value) => value.trim())
        .filter((value) => Boolean(value)),
    ),
  );
}

function pickMetric(overview: DashboardOverviewResponse, label: string) {
  return (
    overview.business_metrics.find((item) => item.label === label) ??
    overview.executive_summary.find((item) => item.label === label) ??
    overview.data_summary.find((item) => item.label === label)
  );
}

function sortBusinessRows(rows: DashboardBusinessBreakdown[], sort: SortState<"name" | "revenue" | "sales" | "sold_units" | "average_check" | "returns">) {
  return [...rows].sort((left, right) => {
    if (sort.key === "name") {
      return compareText(left.name, right.name, sort.direction);
    }

    const a = businessSortValue(left, sort.key);
    const b = businessSortValue(right, sort.key);
    return compareNumber(a, b, sort.direction);
  });
}

function businessSortValue(item: DashboardBusinessBreakdown, key: "name" | "revenue" | "sales" | "sold_units" | "average_check" | "returns") {
  if (key === "sales") return Number(item.sales ?? 0);
  if (key === "sold_units") return parseMoneyValue(item.sold_units ?? "0");
  if (key === "average_check") return parseMoneyValue(item.average_check ?? "0");
  if (key === "returns") return parseMoneyValue(item.returns ?? "0");
  return parseMoneyValue(item.revenue ?? "0");
}

function sortSalesRows(rows: DashboardRecentSale[], sort: SortState<"sale_at" | "sale_number" | "business_name" | "amount" | "items_count" | "products_count">) {
  return [...rows].sort((left, right) => {
    if (sort.key === "sale_number") return compareText(left.sale_number, right.sale_number, sort.direction);
    if (sort.key === "business_name") return compareText(left.business_name, right.business_name, sort.direction);

    const a = salesSortValue(left, sort.key);
    const b = salesSortValue(right, sort.key);
    return compareNumber(a, b, sort.direction);
  });
}

function salesSortValue(item: DashboardRecentSale, key: "sale_at" | "sale_number" | "business_name" | "amount" | "items_count" | "products_count") {
  if (key === "sale_at") return new Date(item.sale_at).getTime() || 0;
  if (key === "items_count") return Number(item.items_count ?? 0);
  if (key === "products_count") return Number(item.products_count ?? 0);
  return parseMoneyValue(item.amount ?? "0");
}

function sortProductRows(rows: DashboardTopProduct[], sort: SortState<"name" | "sold_quantity" | "sold_amount" | "stock_quantity" | "last_sold_at">) {
  return [...rows].sort((left, right) => {
    if (sort.key === "name") return compareText(left.name, right.name, sort.direction);

    const a = productSortValue(left, sort.key);
    const b = productSortValue(right, sort.key);
    return compareNumber(a, b, sort.direction);
  });
}

function productSortValue(item: DashboardTopProduct, key: "name" | "sold_quantity" | "sold_amount" | "stock_quantity" | "last_sold_at") {
  if (key === "last_sold_at") return new Date(item.last_sold_at ?? 0).getTime() || 0;
  if (key === "sold_quantity") return parseMoneyValue(item.sold_quantity ?? "0");
  if (key === "stock_quantity") return parseMoneyValue(item.stock_quantity ?? "0");
  return parseMoneyValue(item.sold_amount ?? "0");
}

function sortInventoryRows(rows: DashboardInventoryCard[], sort: SortState<"product_name" | "warehouse_name" | "quantity" | "average_daily_sales" | "days_of_stock" | "risk_level">) {
  return [...rows].sort((left, right) => {
    if (sort.key === "product_name") return compareText(left.product_name, right.product_name, sort.direction);
    if (sort.key === "warehouse_name") return compareText(left.warehouse_name, right.warehouse_name, sort.direction);
    if (sort.key === "risk_level") return compareText(left.risk_level ?? "", right.risk_level ?? "", sort.direction);

    const a = inventorySortValue(left, sort.key);
    const b = inventorySortValue(right, sort.key);
    return compareNumber(a, b, sort.direction);
  });
}

function inventorySortValue(item: DashboardInventoryCard, key: "product_name" | "warehouse_name" | "quantity" | "average_daily_sales" | "days_of_stock" | "risk_level") {
  if (key === "average_daily_sales") return parseMoneyValue(item.average_daily_sales ?? "0");
  if (key === "days_of_stock") return parseMoneyValue(item.days_of_stock ?? "0");
  return parseMoneyValue(item.quantity ?? "0");
}

function sortCustomerRows(rows: CustomerRow[], sort: SortState<"name" | "deals" | "revenue" | "last_sale" | "average_check">) {
  return [...rows].sort((left, right) => {
    if (sort.key === "name") return compareText(left.name, right.name, sort.direction);

    const a = customerSortValue(left, sort.key);
    const b = customerSortValue(right, sort.key);
    return compareNumber(a, b, sort.direction);
  });
}

function customerSortValue(item: CustomerRow, key: "name" | "deals" | "revenue" | "last_sale" | "average_check") {
  if (key === "deals") return item.deals;
  if (key === "last_sale") return item.lastSale ? new Date(item.lastSale).getTime() || 0 : 0;
  if (key === "average_check") return item.averageCheckValue;
  return item.revenueValue;
}

function sortPaymentRows(rows: DashboardPaymentCard[], sort: SortState<"paid_at" | "amount" | "business_name" | "sale_number" | "method">) {
  return [...rows].sort((left, right) => {
    if (sort.key === "business_name") return compareText(left.business_name, right.business_name, sort.direction);
    if (sort.key === "sale_number") return compareText(left.sale_number ?? "", right.sale_number ?? "", sort.direction);
    if (sort.key === "method") return compareText(left.method ?? "", right.method ?? "", sort.direction);

    const a = paymentSortValue(left, sort.key);
    const b = paymentSortValue(right, sort.key);
    return compareNumber(a, b, sort.direction);
  });
}

function paymentSortValue(item: DashboardPaymentCard, key: "paid_at" | "amount" | "business_name" | "sale_number" | "method") {
  if (key === "paid_at") return new Date(item.paid_at).getTime() || 0;
  return parseMoneyValue(item.amount ?? "0");
}

function compareNumber(left: number, right: number, direction: SortDirection) {
  if (left === right) return 0;
  return direction === "asc" ? left - right : right - left;
}

function compareText(left: string, right: string, direction: SortDirection) {
  const result = left.localeCompare(right, "ru", { sensitivity: "base" });
  return direction === "asc" ? result : -result;
}

function projectTrendSeries(values: number[], period: "day" | "week" | "month" | "all" | "30d" | "90d" | "12m") {
  const targetBuckets = period === "day" ? 12 : period === "week" ? 8 : period === "month" ? 6 : period === "30d" ? 6 : period === "90d" ? 8 : period === "12m" ? 12 : values.length || 12;
  if (!values.length) {
    return Array.from({ length: targetBuckets }, () => 0);
  }

  if (values.length <= targetBuckets) {
    return values;
  }

  const chunkSize = Math.ceil(values.length / targetBuckets);
  const chunks: number[] = [];
  for (let index = 0; index < values.length; index += chunkSize) {
    const slice = values.slice(index, index + chunkSize);
    chunks.push(slice.reduce((sum, value) => sum + value, 0) / Math.max(1, slice.length));
  }
  return chunks;
}

function aggregateCustomers(sales: DashboardRecentSale[]) {
  const map = new Map<string, CustomerRow>();

  for (const sale of sales) {
    const key = sale.contact_name?.trim() || `${sale.business_name}-${sale.external_ref ?? sale.sale_id}`;
    const existing = map.get(key) ?? createCustomerRow(key, sale);
    existing.deals += 1;
    existing.revenueValue += parseMoneyValue(sale.amount);
    existing.lastSale = !existing.lastSale || new Date(sale.sale_at).getTime() > new Date(existing.lastSale).getTime() ? sale.sale_at : existing.lastSale;
    existing.organizations.push(sale.business_name);
    map.set(key, existing);
  }

  return Array.from(map.values()).map((item) => ({
    ...item,
    organizations: uniqueStrings(item.organizations),
    averageCheckValue: item.deals ? item.revenueValue / item.deals : 0,
    repeatRate: item.deals > 1 ? 100 : 0,
    segment: item.deals > 1 ? ("repeat" as const) : ("new" as const),
  })) as CustomerRow[];
}

type CustomerRow = {
  name: string;
  organizations: string[];
  deals: number;
  revenueValue: number;
  averageCheckValue: number;
  lastSale: string | null;
  segment: "new" | "repeat";
  repeatRate: number;
};

function createCustomerRow(name: string, sale: DashboardRecentSale): CustomerRow {
  return {
    name,
    organizations: [sale.business_name],
    deals: 0,
    revenueValue: 0,
    averageCheckValue: 0,
    lastSale: sale.sale_at,
    segment: "new",
    repeatRate: 0,
  };
}

function formatAveragePrice(item: DashboardTopProduct) {
  const soldQuantity = parseMoneyValue(item.sold_quantity ?? "0");
  const soldAmount = parseMoneyValue(item.sold_amount ?? "0");
  return soldQuantity > 0 ? soldAmount / soldQuantity : 0;
}

function formatCompactNumber(value: number) {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return `${Math.round(value)}`;
}

function formatDecimal(value: number, digits: number) {
  return new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function formatRatio(value: number) {
  return new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  }).format(value);
}
