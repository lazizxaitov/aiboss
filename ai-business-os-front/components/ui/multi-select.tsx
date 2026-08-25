"use client";

import { useMemo } from "react";

import { Dropdown } from "@/components/ui/dropdown";
import { FilterChip } from "@/components/ui/filter-chip";
import { cn } from "@/lib/cn";

type MultiSelectOption = {
  value: string;
  label: string;
  count?: number;
};

type MultiSelectProps = {
  label: string;
  value: string[];
  options: MultiSelectOption[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  className?: string;
  panelClassName?: string;
};

function labelForSelection(label: string, selected: MultiSelectOption[]) {
  if (selected.length === 0) return label;
  if (selected.length === 1) return selected[0]?.label ?? label;
  return `${selected[0]?.label ?? label} + ещё ${selected.length - 1}`;
}

export function MultiSelect({
  label,
  value,
  options,
  onChange,
  placeholder = "Все",
  className,
  panelClassName,
}: MultiSelectProps) {
  const selected = useMemo(
    () => options.filter((option) => value.includes(option.value)),
    [options, value],
  );

  const toggle = (item: string) => {
    if (value.includes(item)) {
      onChange(value.filter((current) => current !== item));
      return;
    }
    onChange([...value, item]);
  };

  return (
    <Dropdown
      className={className}
      panelClassName={cn("w-[min(340px,calc(100vw-1rem))] p-1.5", panelClassName)}
      align="left"
      trigger={
        <FilterChip active={value.length > 0} count={value.length || undefined} className="w-full justify-between px-3 py-2">
          <span className="flex min-w-0 flex-col items-start text-left">
            <span className="text-[10px] uppercase tracking-[0.24em] text-slate-400">{label}</span>
            <span className={cn("truncate", selected.length > 0 ? "text-[#f4f7fb]" : "text-slate-400")}>
              {selected.length > 0 ? labelForSelection(placeholder, selected) : placeholder}
            </span>
          </span>
        </FilterChip>
      }
    >
      {() => (
        <div className="p-1">
          <div className="max-h-[280px] overflow-y-auto">
            <div className="space-y-1">
              {options.length ? options.map((option) => {
                const checked = value.includes(option.value);
                return (
                  <button
                    key={option.value}
                    type="button"
                    className={cn(
                      "flex w-full items-center justify-between gap-3 rounded-2xl px-2.5 py-2 text-left text-sm transition",
                      checked
                        ? "bg-[#3a3f48] text-[#f4f7fb] ring-1 ring-inset ring-[#5a6270]"
                        : "text-slate-300 hover:bg-[#343840] hover:text-[#f4f7fb]",
                    )}
                    onClick={() => toggle(option.value)}
                  >
                    <span className="min-w-0 truncate">{option.label}</span>
                    <span className="flex items-center gap-2">
                      {typeof option.count === "number" ? (
                        <span className="rounded-full bg-[#343840] px-2 py-0.5 text-[11px] text-slate-300">
                          {option.count}
                        </span>
                      ) : null}
                      <span
                        className={cn(
                          "flex h-4.5 w-4.5 items-center justify-center rounded-full border text-[11px]",
                          checked
                            ? "border-[#5a6270] bg-[#3a3f48] text-[#f4f7fb]"
                            : "border-[#4a4e56] text-transparent",
                        )}
                      >
                        ✓
                      </span>
                    </span>
                  </button>
                );
              }) : (
                <div className="px-3 py-4 text-sm text-slate-400">Нет вариантов</div>
              )}
            </div>
          </div>
        </div>
      )}
    </Dropdown>
  );
}
