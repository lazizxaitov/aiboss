"use client";

import type { InputHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

type SearchInputProps = InputHTMLAttributes<HTMLInputElement> & {
  compact?: boolean;
};

export function SearchInput({ className, compact, ...props }: SearchInputProps) {
  return (
    <label
      className={cn(
        "flex w-full items-center gap-2 rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 text-sm text-slate-400 shadow-[0_8px_24px_rgba(0,0,0,0.12)] transition focus-within:border-[#6a6f79] focus-within:ring-4 focus-within:ring-white/10",
        compact ? "h-10 px-3" : "h-12",
        className,
      )}
    >
      <span className="text-sm leading-none">⌕</span>
      <input
        type="search"
        className={cn(
          "w-full border-0 bg-transparent text-sm font-medium outline-none",
          "text-[#f4f7fb] placeholder:text-slate-400",
        )}
        {...props}
      />
    </label>
  );
}
