"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

type ButtonVariant = "primary" | "secondary" | "ghost" | "soft" | "danger";
type ButtonSize = "sm" | "md" | "lg";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  leadingIcon?: ReactNode;
  trailingIcon?: ReactNode;
};

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: "border border-[#FFF27A]/30 bg-[#FFF27A] text-[#1E1E21] shadow-[0_10px_24px_rgba(0,0,0,0.22)] hover:border-[#FFF27A]/40 hover:bg-[#fff6a6]",
  secondary: "border border-[#3a3d43] bg-[#2E3137] text-[#f4f7fb] hover:border-[#4a4e56] hover:text-white",
  ghost: "text-slate-300 hover:bg-[#2E3137]/5 hover:text-white",
  soft: "border border-[#5d4d1f] bg-[#3f3721] text-[#ffe781] hover:border-[#7a6524] hover:bg-[#4a4127]",
  danger: "border border-rose-500/30 bg-rose-500/10 text-rose-200 hover:border-rose-400/50 hover:bg-rose-500/20",
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "h-9 px-3 text-sm",
  md: "h-11 px-4 text-sm",
  lg: "h-12 px-5 text-[15px]",
};

export function Button({
  className,
  variant = "primary",
  size = "md",
  leadingIcon,
  trailingIcon,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-full font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        VARIANT_CLASSES[variant],
        SIZE_CLASSES[size],
        className,
      )}
      {...props}
    >
      {leadingIcon ? <span className="shrink-0">{leadingIcon}</span> : null}
      <span className="truncate">{children}</span>
      {trailingIcon ? <span className="shrink-0">{trailingIcon}</span> : null}
    </button>
  );
}
