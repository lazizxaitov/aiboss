import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  icon: ReactNode;
  active?: boolean;
};

export function IconButton({ icon, active, className, ...props }: IconButtonProps) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex h-10 w-10 items-center justify-center rounded-full border transition",
        active
          ? "border-[#FFF27A]/35 bg-[#FFF27A] text-[#1E1E21] shadow-[0_10px_24px_rgba(0,0,0,0.22)]"
          : "border-[#3a3d43] bg-[#2E3137] text-slate-300 hover:border-[#4a4e56] hover:text-white",
        className,
      )}
      {...props}
    >
      {icon}
    </button>
  );
}
