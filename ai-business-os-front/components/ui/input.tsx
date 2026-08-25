import type { InputHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

type InputProps = InputHTMLAttributes<HTMLInputElement>;

export function Input({ className, ...props }: InputProps) {
  return (
    <input
      className={cn(
        "h-11 w-full rounded-2xl border border-[#3a3d43] bg-[#2E3137] px-4 text-sm text-[#f4f7fb] outline-none transition placeholder:text-slate-400 focus:border-[#6a6f79] focus:ring-4 focus:ring-white/10",
        className,
      )}
      {...props}
    />
  );
}
