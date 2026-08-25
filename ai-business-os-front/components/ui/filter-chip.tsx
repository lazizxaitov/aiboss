"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

type FilterChipProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  active?: boolean;
  count?: number;
  leadingIcon?: ReactNode;
};

export function FilterChip({
  active,
  count,
  leadingIcon,
  className,
  children,
  ...props
}: FilterChipProps) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-2 text-sm font-medium transition",
        active
          ? "border-[#5a6270] bg-[#3a3f48] text-[#f4f7fb]"
          : "border-[#3a3d43] bg-[#2E3137] text-slate-300 hover:border-[#4a4e56] hover:text-white",
        className,
      )}
      {...props}
    >
      {leadingIcon ? <span className="shrink-0">{leadingIcon}</span> : null}
      <span className="truncate">{children}</span>
      {typeof count === "number" ? (
        <span
          className={cn(
            "inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-semibold",
            active ? "bg-[#4a515c] text-[#f4f7fb]" : "bg-[#2E3137]/10 text-slate-300",
          )}
        >
          {count}
        </span>
      ) : null}
    </button>
  );
}
