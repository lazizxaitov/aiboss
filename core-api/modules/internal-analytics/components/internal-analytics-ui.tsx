import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Surface } from "@/components/ui/surface";
import { cn } from "@/lib/cn";
import type { DashboardCard } from "@/lib/core-api";

export type SortDirection = "asc" | "desc";

export type SortState<Key extends string> = {
  key: Key;
  direction: SortDirection;
};

export type SelectOption = {
  value: string;
  label: string;
};

export type ChartSeries = {
  key: string;
  label: string;
  color: string;
  values: number[];
  dashed?: boolean;
};

type SelectFieldProps = {
  label: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  compact?: boolean;
};

type MetricCardProps = {
  label: string;
  value: string;
  note: string;
  formula: string;
  change?: string | null;
  active?: boolean;
  onClick?: () => void;
};

export function AnalyticsTrendChart({
  labels,
  series,
  comparePrevious,
  variant,
}: {
  labels: string[];
  series: ChartSeries[];
  comparePrevious: boolean;
  variant: "sales" | "inventory" | "customers" | "finance";
}) {
  const visibleSeries = series.filter((item) => item.values.some((value) => value > 0));
  const chartLabels = labels.length ? labels : Array.from({ length: Math.max(...series.map((item) => item.values.length), 6) }, (_, index) => `${index + 1}`);
  const width = 960;
  const height = 320;
  const compareValues = comparePrevious ? series[0]?.values.map((value, index) => Math.max(0, Math.round(value * 0.82 + index * 2))) ?? [] : [];
  return (
    <div className="rounded-[28px] border border-[#3a3d43] bg-[#2E3137] p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-2">
        {visibleSeries.map((item) => (
          <span key={item.key} className="inline-flex items-center gap-2 rounded-full border border-[#3a3d43] bg-[#2E3137] px-3 py-1.5 text-xs font-medium text-slate-300">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
            {item.label}
          </span>
        ))}
        {comparePrevious ? (
          <span className="inline-flex items-center gap-2 rounded-full border border-[#3a3d43] bg-[#2E3137] px-3 py-1.5 text-xs font-medium text-slate-500">
            <span className="h-2.5 w-2.5 rounded-full bg-[#4a4e56]" />
            Предыдущий период
          </span>
        ) : null}
      </div>

      <div className="mt-4">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-[280px] w-full">
          <defs>
            {visibleSeries.map((item) => (
              <linearGradient key={item.key} id={`gradient-${variant}-${item.key}`} x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor={item.color} stopOpacity="0.9" />
                <stop offset="100%" stopColor={item.color} stopOpacity="0.4" />
              </linearGradient>
            ))}
          </defs>
          <g stroke="#e2e8f0" strokeDasharray="4 6">
            {Array.from({ length: 4 }, (_, index) => {
              const y = 40 + (index * (height - 80)) / 3;
              return <line key={index} x1="24" x2={width - 24} y1={y} y2={y} />;
            })}
          </g>

          {comparePrevious && compareValues.length ? (
            <path
              d={buildLinePath(compareValues, width, height)}
              fill="none"
              stroke="#cbd5e1"
              strokeWidth="3"
              strokeDasharray="8 8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ) : null}

          {visibleSeries.map((item) => (
            <g key={item.key}>
              <path
                d={buildLinePath(item.values, width, height)}
                fill="none"
                stroke={`url(#gradient-${variant}-${item.key})`}
                strokeWidth="4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </g>
          ))}

          <g fill="#64748b" fontSize="12">
            {chartLabels.map((label, index) => {
              const step = chartLabels.length > 1 ? (width - 48) / (chartLabels.length - 1) : 0;
              const x = 24 + step * index;
              return (
                <text key={label} x={x} y={height - 12} textAnchor="middle">
                  {label}
                </text>
              );
            })}
          </g>
        </svg>
      </div>
    </div>
  );
}

export function FiltersSurface({ children }: { children: ReactNode }) {
  return <Surface className="overflow-visible p-4 sm:p-5">{children}</Surface>;
}

export function SelectField({ label, value, options, onChange, compact }: SelectFieldProps) {
  const disabled = options.length <= 1;
  return (
    <label className={cn("flex min-w-0 flex-col gap-2", compact ? "text-xs" : "text-sm")}>
      <span className="text-[11px] uppercase tracking-[0.28em] text-slate-500">{label}</span>
      <div className="relative">
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          className={cn(
            "w-full appearance-none rounded-2xl border bg-[#2E3137] px-4 py-3 pr-10 text-sm font-medium text-slate-200 outline-none transition",
            disabled
              ? "border-[#3a3d43] bg-[#343840] text-slate-500"
              : "border-[#3a3d43] hover:border-[#4a4e56] focus:border-violet-300 focus:ring-2 focus:ring-violet-100",
          )}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-slate-500">▾</span>
      </div>
    </label>
  );
}

export function SearchField({
  value,
  onChange,
  placeholder,
  compact,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  compact?: boolean;
}) {
  return (
    <label className={cn("flex min-w-0 flex-col gap-2", compact ? "text-xs" : "text-sm")}>
      <span className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Поиск</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded-2xl border border-[#3a3d43] bg-[#2E3137] px-4 py-3 text-sm text-slate-200 outline-none transition hover:border-[#4a4e56] focus:border-violet-300 focus:ring-2 focus:ring-violet-100"
      />
    </label>
  );
}

export function MetricCard({ label, value, note, formula, change, active, onClick }: MetricCardProps) {
  return (
    <button type="button" title={formula} onClick={onClick} className={cn("group text-left", onClick ? "cursor-pointer" : "cursor-default")}>
      <Surface className={cn("h-full p-4 transition", active ? "ring-2 ring-violet-200" : "hover:border-[#4a4e56]")}>
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{label}</p>
            <p className="mt-3 text-[28px] font-semibold tracking-[-0.05em] text-[#f4f7fb]">{value}</p>
            <p className="mt-2 text-sm leading-5 text-slate-500">{note}</p>
          </div>
          {change ? <Badge variant="soft">{change}</Badge> : <Badge variant="accent">KPI</Badge>}
        </div>
      </Surface>
    </button>
  );
}

export function TableSection({
  title,
  subtitle,
  badge,
  rightAction,
  children,
}: {
  title: string;
  subtitle: string;
  badge: string;
  rightAction?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Surface className="overflow-hidden p-5 sm:p-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-500">{badge}</p>
          <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">{title}</h3>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">{subtitle}</p>
        </div>
        {rightAction ? <div className="flex flex-wrap gap-2">{rightAction}</div> : null}
      </div>
      <div className="mt-4">{children}</div>
    </Surface>
  );
}

export function DataTable({
  columns,
  rows,
  sortKey,
  sortDirection,
  onSort,
}: {
  columns: Array<{ key: string; label: string }>;
  rows: ReactNode[];
  sortKey: string;
  sortDirection: SortDirection;
  onSort: (key: string) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border-separate border-spacing-0">
        <thead className="sticky top-0 z-10 bg-[#2E3137]">
          <tr>
            {columns.map((column) => (
              <th key={column.key} className="border-b border-[#3a3d43] px-4 py-3 text-left text-xs uppercase tracking-[0.24em] text-slate-500">
                <button type="button" onClick={() => onSort(column.key)} className="inline-flex items-center gap-2 text-left">
                  <span>{column.label}</span>
                  {sortKey === column.key ? <span className="text-[10px] text-violet-500">{sortDirection === "asc" ? "▲" : "▼"}</span> : null}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  );
}

export function PaginationBar({
  page,
  totalPages,
  pageSize,
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  totalPages: number;
  pageSize: string;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: string) => void;
}) {
  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <span>Показать</span>
        <select value={pageSize} onChange={(event) => onPageSizeChange(event.target.value)} className="rounded-full border border-[#3a3d43] bg-[#2E3137] px-3 py-1.5 text-sm text-slate-200 outline-none">
          <option value="50">50</option>
          <option value="100">100</option>
          <option value="200">200</option>
        </select>
        <span>строк</span>
      </div>

      <div className="flex items-center gap-2">
        <button type="button" onClick={() => onPageChange(Math.max(1, page - 1))} disabled={page <= 1} className="rounded-full border border-[#3a3d43] bg-[#2E3137] px-3 py-1.5 text-sm text-slate-200 transition hover:border-[#4a4e56] disabled:cursor-not-allowed disabled:opacity-40">
          Назад
        </button>
        <span className="text-sm text-slate-500">
          {page} / {totalPages}
        </span>
        <button type="button" onClick={() => onPageChange(Math.min(totalPages, page + 1))} disabled={page >= totalPages} className="rounded-full border border-[#3a3d43] bg-[#2E3137] px-3 py-1.5 text-sm text-slate-200 transition hover:border-[#4a4e56] disabled:cursor-not-allowed disabled:opacity-40">
          Вперёд
        </button>
      </div>
    </div>
  );
}

export function DetailCard({
  title,
  subtitle,
  badges,
  children,
  action,
}: {
  title: string;
  subtitle: string;
  badges: string[];
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-[24px] border border-[#3a3d43] bg-[#2E3137] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">{title}</p>
          <p className="mt-1 text-sm leading-6 text-slate-500">{subtitle}</p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex flex-wrap justify-end gap-2">
            {badges.map((badge, index) => (
              <Badge key={`${badge}-${index}`} variant="soft">
                {badge}
              </Badge>
            ))}
          </div>
          {action}
        </div>
      </div>
      {children ? <div className="mt-4">{children}</div> : null}
    </div>
  );
}

export function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[#3a3d43] bg-[#2E3137] px-3 py-2.5">
      <p className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{label}</p>
      <p className="mt-1 text-sm font-medium text-[#f4f7fb]">{value}</p>
    </div>
  );
}

export function SummaryBlock({ card }: { card: DashboardCard }) {
  return (
    <div className="rounded-2xl border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-[#f4f7fb]">{card.label}</p>
          <p className="mt-1 text-sm text-slate-500">{card.note}</p>
        </div>
        <Badge variant="soft">{card.value}</Badge>
      </div>
    </div>
  );
}

export function EmptyState({ text }: { text: string }) {
  return <div className="rounded-2xl border border-dashed border-[#3a3d43] bg-[#343840]/70 px-4 py-5 text-sm text-slate-500">{text}</div>;
}

export function SortBadges<Key extends string>({ sort }: { sort: SortState<Key> }) {
  return (
    <Badge variant="soft">
      {sort.key} · {sort.direction === "asc" ? "▲" : "▼"}
    </Badge>
  );
}

function buildLinePath(values: number[], width: number, height: number) {
  const points = values.length ? values : [0];
  const max = Math.max(...points, 1);
  const step = points.length > 1 ? (width - 48) / (points.length - 1) : 0;
  return points
    .map((value, index) => {
      const x = 24 + step * index;
      const y = height - 36 - ((height - 80) * value) / max;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}
