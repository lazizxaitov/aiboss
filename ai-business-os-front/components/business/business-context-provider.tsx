"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import {
  getCachedSmartUpOrganizations,
  getOrganizationContext,
  getSmartUpOrganizations,
  type AnalyticsComparisonMode,
  type AnalyticsContextState,
  type AnalyticsPeriodPreset,
  type OrganizationContextMode,
  type SmartUpOrganization,
  updateOrganizationContext,
} from "@/lib/core-api";

export type BusinessContextOrganizationMode = "ALL" | "SINGLE" | "MULTIPLE";

export type BusinessContextPeriod = {
  preset: AnalyticsPeriodPreset;
  dateFrom: string | null;
  dateTo: string | null;
};

export type BusinessContextState = {
  organizationMode: BusinessContextOrganizationMode;
  selectedOrganizationIds: string[];
  period: BusinessContextPeriod;
};

export type BusinessContextOrganizationOption = {
  id: string;
  name: string;
};

type BusinessContextValue = {
  state: BusinessContextState;
  availableOrganizations: BusinessContextOrganizationOption[];
  loading: boolean;
  hydrated: boolean;
  comparisonMode: AnalyticsComparisonMode;
  setOrganizationSelection: (organizationIds: string[]) => void;
  setPeriodPreset: (preset: AnalyticsPeriodPreset) => void;
  setCustomPeriod: (dateFrom: string, dateTo: string) => void;
  resetToAll: () => void;
};

const DEFAULT_STATE: BusinessContextState = {
  organizationMode: "ALL",
  selectedOrganizationIds: [],
  period: {
    preset: "30d",
    dateFrom: null,
    dateTo: null,
  },
};

const BusinessContext = createContext<BusinessContextValue | null>(null);

function mapMode(mode: BusinessContextOrganizationMode): OrganizationContextMode {
  return mode === "ALL" ? "all" : mode === "SINGLE" ? "single" : "multiple";
}

function mapPersistedContext(context: AnalyticsContextState): BusinessContextState {
  const ids = context.organization_context.organization_ids ?? [];
  const mode =
    context.organization_context.mode === "single"
      ? "SINGLE"
      : context.organization_context.mode === "multiple"
        ? "MULTIPLE"
        : "ALL";

  return {
    organizationMode: mode,
    selectedOrganizationIds: ids,
    period: {
      preset: context.period_context.preset,
      dateFrom: context.period_context.date_from,
      dateTo: context.period_context.date_to,
    },
  };
}

function normalizeState(state: BusinessContextState): BusinessContextState {
  const ids = Array.from(new Set(state.selectedOrganizationIds));
  if (ids.length === 0) {
    return { ...state, organizationMode: "ALL", selectedOrganizationIds: [] };
  }
  if (ids.length === 1) {
    return { ...state, organizationMode: "SINGLE", selectedOrganizationIds: ids };
  }
  return { ...state, organizationMode: "MULTIPLE", selectedOrganizationIds: ids };
}

function parseUrlState(params: URLSearchParams): BusinessContextState | null {
  const org = params.get("org");
  const period = params.get("period") as AnalyticsPeriodPreset | null;
  const from = params.get("from");
  const to = params.get("to");

  const hasContext =
    org !== null ||
    period !== null ||
    from !== null ||
    to !== null;

  if (!hasContext) return null;

  let selectedOrganizationIds: string[] = [];
  let organizationMode: BusinessContextOrganizationMode = "ALL";

  if (org && org !== "all") {
    selectedOrganizationIds = org
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    organizationMode =
      selectedOrganizationIds.length > 1 ? "MULTIPLE" : selectedOrganizationIds.length === 1 ? "SINGLE" : "ALL";
  }

  const preset = period ?? ((from || to) ? "custom" : DEFAULT_STATE.period.preset);
  return normalizeState({
    organizationMode,
    selectedOrganizationIds,
    period: {
      preset,
      dateFrom: from,
      dateTo: to,
    },
  });
}

function toSearchParams(state: BusinessContextState) {
  const params = new URLSearchParams();

  if (state.organizationMode === "ALL" || state.selectedOrganizationIds.length === 0) {
    params.set("org", "all");
  } else {
    params.set("org", state.selectedOrganizationIds.join(","));
  }

  params.set("period", state.period.preset);

  if (state.period.preset === "custom") {
    if (state.period.dateFrom) params.set("from", state.period.dateFrom);
    if (state.period.dateTo) params.set("to", state.period.dateTo);
  }

  return params;
}

export function BusinessContextProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [state, setState] = useState<BusinessContextState>(DEFAULT_STATE);
  const [availableOrganizations, setAvailableOrganizations] = useState<BusinessContextOrganizationOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [hydrated, setHydrated] = useState(false);
  const initialised = useRef(false);
  const lastSyncedState = useRef<string>("");

  useEffect(() => {
    let active = true;
    const cachedOrganizations = getCachedSmartUpOrganizations();
    if (cachedOrganizations && cachedOrganizations.length > 0) {
      setAvailableOrganizations(
        cachedOrganizations
          .map((item: SmartUpOrganization) => ({
            id: item.id,
            name: item.name,
          }))
          .sort((left, right) => left.name.localeCompare(right.name, "ru")),
      );
      return () => {
        active = false;
      };
    }

    void getSmartUpOrganizations()
      .then((items) => {
        if (!active || items.length === 0) return;
        setAvailableOrganizations(
          items
            .map((item) => ({
              id: item.id,
              name: item.name,
            }))
            .sort((left, right) => left.name.localeCompare(right.name, "ru")),
        );
      })
      .catch(() => {
        if (!active) return;
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (initialised.current) return;

    let active = true;

    async function bootstrap() {
      try {
        const fromUrl = parseUrlState(new URLSearchParams(searchParams.toString()));
        if (fromUrl) {
          if (!active) return;
          setState(fromUrl);
          lastSyncedState.current = JSON.stringify(fromUrl);
          setHydrated(true);
          setLoading(false);
          initialised.current = true;
          return;
        }

        const persisted = await getOrganizationContext();
        if (!active) return;
        const mapped = normalizeState(mapPersistedContext(persisted));
        setState(mapped);
        lastSyncedState.current = JSON.stringify(mapped);
      } catch {
        if (!active) return;
        setState(DEFAULT_STATE);
        lastSyncedState.current = JSON.stringify(DEFAULT_STATE);
      } finally {
        if (active) {
          setHydrated(true);
          setLoading(false);
          initialised.current = true;
        }
      }
    }

    void bootstrap();

    return () => {
      active = false;
    };
  }, [searchParams]);

  useEffect(() => {
    if (!hydrated) return;

    const normalized = normalizeState(state);
    const params = toSearchParams(normalized);
    const nextUrl = params.toString() ? `${pathname}?${params.toString()}` : pathname;
    router.replace(nextUrl, { scroll: false });

    const serialized = JSON.stringify(normalized);
    if (serialized === lastSyncedState.current) return;
    lastSyncedState.current = serialized;

    void updateOrganizationContext({
      organization_context: {
        mode: mapMode(normalized.organizationMode),
        organization_ids: normalized.selectedOrganizationIds,
      },
      period_context: {
        preset: normalized.period.preset,
        date_from: normalized.period.dateFrom,
        date_to: normalized.period.dateTo,
      },
    }).catch(() => undefined);
  }, [hydrated, pathname, router, state]);

  const value = useMemo<BusinessContextValue>(() => ({
    state,
    availableOrganizations,
    loading,
    hydrated,
    comparisonMode: "previous_period",
    setOrganizationSelection: (organizationIds) => {
      setState((current) =>
        normalizeState({
          ...current,
          selectedOrganizationIds: organizationIds,
          organizationMode:
            organizationIds.length > 1
              ? "MULTIPLE"
              : organizationIds.length === 1
                ? "SINGLE"
                : "ALL",
        }),
      );
    },
    setPeriodPreset: (preset) => {
      setState((current) => ({
        ...current,
        period: {
          preset,
          dateFrom: preset === "custom" ? current.period.dateFrom : null,
          dateTo: preset === "custom" ? current.period.dateTo : null,
        },
      }));
    },
    setCustomPeriod: (dateFrom, dateTo) => {
      setState((current) => ({
        ...current,
        period: {
          preset: "custom",
          dateFrom,
          dateTo,
        },
      }));
    },
    resetToAll: () => {
      setState(DEFAULT_STATE);
    },
  }), [availableOrganizations, hydrated, loading, state]);

  return <BusinessContext.Provider value={value}>{children}</BusinessContext.Provider>;
}

export function useBusinessContext() {
  const context = useContext(BusinessContext);
  if (context === null) {
    throw new Error("useBusinessContext must be used inside BusinessContextProvider");
  }
  return context;
}

export function useSelectedOrganizationNames() {
  const { state, availableOrganizations } = useBusinessContext();

  return useMemo(() => {
    if (state.organizationMode === "ALL") return ["Все организации"];
    const selected = new Set(state.selectedOrganizationIds);
    return availableOrganizations
      .filter((item) => selected.has(item.id))
      .map((item) => item.name);
  }, [availableOrganizations, state.organizationMode, state.selectedOrganizationIds]);
}
