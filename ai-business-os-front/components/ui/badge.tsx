"use client";

import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type BadgeVariant = "neutral" | "accent" | "soft" | "dark";

const badgeStyles: Record<BadgeVariant, string> = {
  neutral: "border-[#3a3d43] bg-[#2E3137] text-[#f4f7fb]",
  accent: "border-[#FFF27A]/30 bg-[#FFF27A] text-[#1E1E21]",
  soft: "border-[#3a3d43] bg-[#343840] text-slate-200",
  dark: "border-[#3a3d43] bg-[#343840] text-[#f4f7fb]",
};

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  variant?: BadgeVariant;
};

export function Badge({
  className,
  variant = "neutral",
  ...props
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium tracking-[0.01em]",
        badgeStyles[variant],
        className,
      )}
      {...props}
    />
  );
}
