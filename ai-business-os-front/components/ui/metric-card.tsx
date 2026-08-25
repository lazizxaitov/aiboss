import type { CSSProperties, ReactNode } from "react";

import { Surface } from "@/components/ui/surface";
import { cn } from "@/lib/cn";

type MetricCardProps = {
  label: string;
  value: string;
  note?: string;
  detail?: string;
  tone?: "violet" | "emerald" | "rose" | "amber" | "sky" | "slate";
  icon?: ReactNode;
  className?: string;
  compact?: boolean;
};

const toneClasses: Record<NonNullable<MetricCardProps["tone"]>, { bar: string; icon: string; badge: string }> = {
  violet: {
    bar: "bg-gradient-to-r from-yellow-300 via-yellow-300 to-amber-400",
    icon: "bg-[#FFF27A] text-[#1E1E21] ring-yellow-200/20",
    badge: "bg-[#FFF27A] text-[#1E1E21]",
  },
  emerald: {
    bar: "bg-gradient-to-r from-emerald-400 via-emerald-500 to-teal-500",
    icon: "bg-[#32443d] text-[#f4f7fb] ring-emerald-200/20",
    badge: "bg-[#32443d] text-[#f4f7fb]",
  },
  rose: {
    bar: "bg-gradient-to-r from-rose-400 via-rose-500 to-orange-500",
    icon: "bg-[#4a3540] text-[#f4f7fb] ring-rose-200/20",
    badge: "bg-[#4a3540] text-[#f4f7fb]",
  },
  amber: {
    bar: "bg-gradient-to-r from-amber-400 via-amber-500 to-orange-500",
    icon: "bg-[#4b432d] text-[#f4f7fb] ring-amber-200/20",
    badge: "bg-[#4b432d] text-[#f4f7fb]",
  },
  sky: {
    bar: "bg-gradient-to-r from-sky-400 via-amber-300 to-cyan-500",
    icon: "bg-[#2f4050] text-[#f4f7fb] ring-sky-200/20",
    badge: "bg-[#2f4050] text-[#f4f7fb]",
  },
  slate: {
    bar: "bg-gradient-to-r from-slate-400 via-slate-500 to-slate-600",
    icon: "bg-[#343840] text-[#f4f7fb] ring-slate-200/20",
    badge: "bg-[#343840] text-[#f4f7fb]",
  },
};

export function MetricCard({
  label,
  value,
  note,
  detail,
  tone = "slate",
  icon,
  className,
  compact,
}: MetricCardProps) {
  const styles = toneClasses[tone];
  const compactStyle: CSSProperties | undefined = compact
    ? {
        minHeight: 0,
      }
    : undefined;

  return (
    <Surface className={cn("relative flex h-full flex-col overflow-hidden p-4 sm:p-5", className)} style={compactStyle}>
      <div className={cn("absolute inset-x-0 top-0 h-1", styles.bar)} />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">{label}</p>
          <p className="mt-3 text-[28px] font-semibold tracking-[-0.06em] text-[#f4f7fb] sm:text-[32px]">{value}</p>
        </div>
        {icon ? (
          <div className={cn("flex h-10 w-10 items-center justify-center rounded-2xl ring-1", styles.icon)}>
            {icon}
          </div>
        ) : null}
      </div>
      {note ? <p className="mt-3 text-sm leading-6 text-slate-300">{note}</p> : null}
      {detail ? <p className="mt-2 text-xs uppercase tracking-[0.22em] text-slate-400">{detail}</p> : null}
    </Surface>
  );
}
