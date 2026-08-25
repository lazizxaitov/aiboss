"use client";

import { useState } from "react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Surface } from "@/components/ui/surface";
import { cn } from "@/lib/cn";

type FilterBarProps = {
  title?: string;
  subtitle?: string;
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
  drawerTitle?: string;
  drawerDescription?: string;
  drawerLabel?: string;
};

export function FilterBar({
  title,
  subtitle,
  children,
  actions,
  className,
  drawerLabel = "Изменить",
}: FilterBarProps) {
  const [open, setOpen] = useState(false);
  const toggleLabel = open ? "Закрыть" : drawerLabel;

  return (
    <Surface className={cn("overflow-visible px-4 py-4 sm:px-5", className)}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="min-w-0">
            {title ? <p className="text-[10px] uppercase tracking-[0.3em] text-slate-400">{title}</p> : null}
            {subtitle ? <p className="mt-1.5 max-w-[54rem] text-sm leading-6 text-slate-400">{subtitle}</p> : null}
          </div>

          <div className="flex items-center gap-2 self-start xl:self-auto">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="h-9 rounded-full border-[#3a3d43] px-4 text-sm text-slate-100"
              onClick={() => setOpen((current) => !current)}
            >
              {toggleLabel}
            </Button>
          </div>
        </div>

        <div
          className={cn(
            "grid transition-[grid-template-rows,opacity,margin-top] duration-300 ease-out",
            open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
          )}
        >
          <div className={cn("min-h-0 overflow-hidden", open ? "mt-0" : "pointer-events-none")}>
            <div className="space-y-4">
              {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
              <div>{children}</div>
            </div>
          </div>
        </div>
      </div>
    </Surface>
  );
}
