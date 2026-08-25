import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type BadgeVariant = "soft" | "accent" | "success" | "warning" | "danger";

const variantClasses: Record<BadgeVariant, string> = {
  soft: "border-[#3a3d43] bg-[#343840] text-slate-300",
  accent: "border-violet-400/40 bg-violet-500/15 text-violet-200",
  success: "border-emerald-400/40 bg-emerald-500/15 text-emerald-200",
  warning: "border-amber-400/40 bg-amber-500/15 text-amber-200",
  danger: "border-rose-400/40 bg-rose-500/15 text-rose-200",
};

type BadgeProps = {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
};

export function Badge({ children, variant = "soft", className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium leading-none",
        variantClasses[variant],
        className,
      )}
    >
      {children}
    </span>
  );
}
