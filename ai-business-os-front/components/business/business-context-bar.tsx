"use client";

import { Badge } from "@/components/ui/badge";
import { FilterBar } from "@/components/ui/filter-bar";
import { useBusinessContext, useSelectedOrganizationNames } from "@/components/business/business-context-provider";
import type { AnalyticsPeriodPreset } from "@/lib/core-api";
import { cn } from "@/lib/cn";

const PERIOD_OPTIONS: Array<{ value: AnalyticsPeriodPreset; label: string }> = [
  { value: "today", label: "Сегодня" },
  { value: "7d", label: "7 дней" },
  { value: "30d", label: "30 дней" },
  { value: "current_month", label: "Этот месяц" },
  { value: "previous_month", label: "Прошлый месяц" },
  { value: "all", label: "Весь период" },
  { value: "custom", label: "Произвольный" },
];

function buildSelectionLabel(names: string[]) {
  if (names.length <= 1) return names[0] ?? "Все организации";
  if (names.length === 2) return `${names[0]} + ${names[1]}`;
  return `${names[0]} + ещё ${names.length - 1}`;
}

export function BusinessContextBar() {
  const {
    state,
    availableOrganizations,
    loading,
    setOrganizationSelection,
    setPeriodPreset,
    setCustomPeriod,
  } = useBusinessContext();
  const selectedNames = useSelectedOrganizationNames();

  const organizationLabel = buildSelectionLabel(selectedNames);
  const periodLabel =
    PERIOD_OPTIONS.find((item) => item.value === state.period.preset)?.label ?? "30 дней";
  const selectedOrganizationIds = state.selectedOrganizationIds;
  const selectedOrganizationSet = new Set(selectedOrganizationIds);
  const dateFrom = state.period.dateFrom ?? "";
  const dateTo = state.period.dateTo ?? "";

  return (
    <FilterBar
      title="Глобальный контекст"
      subtitle="Организация и период сохраняются между всеми разделами."
      drawerTitle="Глобальный контекст"
      drawerDescription="Настройте организацию, период и сравнение для всех рабочих разделов."
      drawerLabel="Изменить"
      actions={
        <>
          <Badge variant="soft" className="px-2.5 py-0.5 text-[11px]">
            {state.organizationMode === "ALL"
              ? "Все организации"
              : state.organizationMode === "SINGLE"
                ? "Одна организация"
                : "Несколько организаций"}
          </Badge>
          <Badge variant="soft" className="px-2.5 py-0.5 text-[11px]">
            Период: {periodLabel}
          </Badge>
        </>
      }
    >
      <div className="space-y-3">
        <div className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-3 py-2.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant="soft" className="px-2.5 py-0.5 text-[11px]">
              {organizationLabel}
            </Badge>
            <Badge variant="soft" className="px-2.5 py-0.5 text-[11px]">
              Период: {periodLabel}
            </Badge>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            {loading ? "Загрузка доступных организаций..." : "Выбранный контекст влияет на все рабочие разделы."}
          </p>
        </div>

        <div className="grid gap-3 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <section className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-3 py-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[10px] uppercase tracking-[0.28em] text-slate-400">Организации</p>
                <p className="mt-1 text-sm text-slate-400">Выберите одну или несколько организаций.</p>
              </div>
              <Badge variant="soft" className="shrink-0 px-2.5 py-0.5 text-[11px]">
                {selectedOrganizationIds.length > 0 ? selectedOrganizationIds.length : "Все"}
              </Badge>
            </div>

            <div className="mt-3 max-h-[15.5rem] overflow-y-auto pr-1">
              <div className="grid gap-2 sm:grid-cols-2">
                <button
                  type="button"
                  onClick={() => setOrganizationSelection([])}
                  className={cn(
                    "flex h-11 items-center justify-between rounded-2xl border px-3 text-left text-sm transition",
                    selectedOrganizationIds.length === 0
                      ? "border-[#FFF27A]/40 bg-[#FFF27A] text-[#1E1E21]"
                      : "border-[#3a3d43] bg-[#343840] text-slate-300 hover:border-[#4a4e56] hover:text-white",
                  )}
                >
                  <span className="min-w-0 truncate">Все организации</span>
                  <span className={cn(
                    "ml-3 inline-flex h-6 min-w-6 items-center justify-center rounded-full px-1 text-[11px] font-semibold",
                    selectedOrganizationIds.length === 0 ? "bg-[#1E1E21]/10 text-[#1E1E21]" : "bg-[#2E3137] text-slate-300",
                  )}>
                    ∞
                  </span>
                </button>

                {availableOrganizations.map((option) => {
                  const checked = selectedOrganizationSet.has(option.id);
                  return (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => {
                        if (checked) {
                          setOrganizationSelection(selectedOrganizationIds.filter((current) => current !== option.id));
                          return;
                        }
                        setOrganizationSelection([...selectedOrganizationIds, option.id]);
                      }}
                      className={cn(
                        "flex h-11 items-center justify-between rounded-2xl border px-3 text-left text-sm transition",
                        checked
                          ? "border-[#FFF27A]/40 bg-[#FFF27A] text-[#1E1E21]"
                          : "border-[#3a3d43] bg-[#343840] text-slate-300 hover:border-[#4a4e56] hover:text-white",
                      )}
                    >
                      <span className="min-w-0 truncate">{option.name}</span>
                      <span
                        className={cn(
                          "ml-3 inline-flex h-6 min-w-6 items-center justify-center rounded-full px-1 text-[11px] font-semibold",
                          checked ? "bg-[#1E1E21]/10 text-[#1E1E21]" : "bg-[#2E3137] text-slate-300",
                        )}
                      >
                        {checked ? "✓" : "•"}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          </section>

          <section className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-3 py-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[10px] uppercase tracking-[0.28em] text-slate-400">Период</p>
                <p className="mt-1 text-sm text-slate-400">Стандартные периоды и ручной диапазон дат.</p>
              </div>
              <Badge variant="soft" className="shrink-0 px-2.5 py-0.5 text-[11px]">
                {periodLabel}
              </Badge>
            </div>

            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {PERIOD_OPTIONS.map((option) => {
                const isActive = state.period.preset === option.value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setPeriodPreset(option.value)}
                    className={cn(
                      "flex h-11 items-center justify-between rounded-2xl border px-3 text-left text-sm transition",
                      isActive
                        ? "border-[#FFF27A]/40 bg-[#FFF27A] text-[#1E1E21]"
                        : "border-[#3a3d43] bg-[#343840] text-slate-300 hover:border-[#4a4e56] hover:text-white",
                    )}
                  >
                    <span className="min-w-0 truncate">{option.label}</span>
                    <span
                      className={cn(
                        "ml-3 inline-flex h-6 min-w-6 items-center justify-center rounded-full px-1 text-[11px] font-semibold",
                        isActive ? "bg-[#1E1E21]/10 text-[#1E1E21]" : "bg-[#2E3137] text-slate-300",
                      )}
                    >
                      {isActive ? "✓" : "•"}
                    </span>
                  </button>
                );
              })}
            </div>

            {state.period.preset === "custom" ? (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <label className="space-y-1.5 text-xs text-slate-400">
                  <span>Дата начала</span>
                  <input
                    type="date"
                    value={dateFrom}
                    onChange={(event) =>
                      setCustomPeriod(event.target.value, dateTo || event.target.value)
                    }
                    className="h-11 w-full rounded-2xl border border-[#3a3d43] bg-[#343840] px-3 text-sm text-[#f4f7fb] outline-none transition focus:border-[#6a6f79]"
                  />
                </label>
                <label className="space-y-1.5 text-xs text-slate-400">
                  <span>Дата конца</span>
                  <input
                    type="date"
                    value={dateTo}
                    onChange={(event) =>
                      setCustomPeriod(dateFrom || event.target.value, event.target.value)
                    }
                    className="h-11 w-full rounded-2xl border border-[#3a3d43] bg-[#343840] px-3 text-sm text-[#f4f7fb] outline-none transition focus:border-[#6a6f79]"
                  />
                </label>
              </div>
            ) : (
              <p className="mt-3 text-sm leading-6 text-slate-400">
                Для ручного диапазона выберите пункт «Произвольный период».
              </p>
            )}
          </section>
        </div>
      </div>
    </FilterBar>
  );
}
