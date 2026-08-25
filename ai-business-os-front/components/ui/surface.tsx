import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export function Surface({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "min-h-0 rounded-[28px] border border-[#3a3d43] bg-[#2E3137] shadow-[0_1px_2px_rgba(0,0,0,0.18),0_18px_60px_rgba(0,0,0,0.2)]",
        className,
      )}
      {...props}
    />
  );
}
