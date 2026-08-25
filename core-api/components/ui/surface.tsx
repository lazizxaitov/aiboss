import type { ComponentPropsWithoutRef, ReactNode } from "react";

import { cn } from "@/lib/cn";

type SurfaceProps = ComponentPropsWithoutRef<"div"> & {
  children?: ReactNode;
};

export function Surface({ className, children, ...props }: SurfaceProps) {
  return (
    <div
      className={cn(
        "rounded-[28px] border border-[#3a3d43] bg-[#2E3137] shadow-[0_1px_2px_rgba(0,0,0,0.18),0_18px_60px_rgba(0,0,0,0.2)]",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}
