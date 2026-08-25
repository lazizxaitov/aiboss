"use client";

import { useMemo } from "react";

import { Dropdown } from "@/components/ui/dropdown";
import { FilterChip } from "@/components/ui/filter-chip";
import { cn } from "@/lib/cn";

type SelectOption = {
  value: string;
  label: string;
  count?: number;
};

type SelectProps = {
  label?: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  panelClassName?: string;
};

export function Select({
  label,
  value,
  options,
  onChange,
  placeholder = "Выберите",
  className,
  panelClassName,
}: SelectProps) {
  const selected = useMemo(
    () => options.find((option) => option.value === value) ?? null,
    [options, value],
  );

  return (
    <Dropdown
      className={className}
      panelClassName={cn("w-[min(320px,calc(100vw-1rem))] p-1.5", panelClassName)}
      align="left"
      trigger={
        <FilterChip active={Boolean(value)} className="w-full justify-between px-3 py-2">
          <span className="flex min-w-0 flex-col items-start text-left">
            {label ? <span className="text-[10px] uppercase tracking-[0.24em] text-slate-400">{label}</span> : null}
            <span className={cn("truncate", selected ? "text-[#f4f7fb]" : "text-slate-400")}>
              {selected?.label ?? placeholder}
            </span>
          </span>
        </FilterChip>
      }
    >
      {(close) => (
        <div className="max-h-[280px] overflow-y-auto p-1">
          {options.length ? (
            options.map((option) => {
              const isActive = option.value === value;
              return (
                <button
                  key={option.value}
                  type="button"
                  className={cn(
                    "flex w-full items-center justify-between gap-3 rounded-2xl px-2.5 py-2 text-left text-sm transition",
                    isActive
                      ? "bg-[#3a3f48] text-[#f4f7fb] ring-1 ring-inset ring-[#5a6270]"
                      : "text-slate-300 hover:bg-[#343840] hover:text-[#f4f7fb]",
                  )}
                  onClick={() => {
                    onChange(option.value);
                    close();
                  }}
                >
                  <span className="min-w-0 truncate">{option.label}</span>
                  {typeof option.count === "number" ? (
                    <span className="rounded-full bg-[#343840] px-2 py-0.5 text-[11px] text-slate-300">
                      {option.count}
                    </span>
                  ) : null}
                </button>
              );
            })
          ) : (
            <div className="px-3 py-4 text-sm text-slate-400">Нет вариантов</div>
          )}
        </div>
      )}
    </Dropdown>
  );
}
