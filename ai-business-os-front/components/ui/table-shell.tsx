import type { ReactNode } from "react";

import { Surface } from "@/components/ui/surface";
import { cn } from "@/lib/cn";

type TableShellProps = {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function TableShell({ title, subtitle, action, children, className }: TableShellProps) {
  return (
    <Surface className={cn("overflow-hidden", className)}>
      {(title || subtitle || action) ? (
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#3a3d43] px-5 py-4">
          <div>
            {title ? <h2 className="text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">{title}</h2> : null}
            {subtitle ? <p className="mt-1 text-sm leading-6 text-slate-400">{subtitle}</p> : null}
          </div>
          {action ? <div>{action}</div> : null}
        </div>
      ) : null}
      {children}
    </Surface>
  );
}
