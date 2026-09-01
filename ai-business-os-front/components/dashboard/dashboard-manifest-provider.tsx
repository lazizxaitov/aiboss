"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { useBusinessContext } from "@/components/business/business-context-provider";
import { useBusinessRefresh } from "@/components/business/business-refresh-provider";
import {
  getDashboardManifest,
  type DashboardManifest,
  type DashboardManifestFilters,
} from "@/lib/core-api";

type DashboardManifestContextValue = {
  manifest: DashboardManifest | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  reload: () => Promise<void>;
};

const DashboardManifestContext = createContext<DashboardManifestContextValue | null>(null);
const DASHBOARD_MANIFEST_CACHE_PREFIX = "ai-business-os:dashboard-manifest:v1";

function getDashboardManifestCacheKey(filters: DashboardManifestFilters) {
  return `${DASHBOARD_MANIFEST_CACHE_PREFIX}:${JSON.stringify({
    organizationId: filters.organizationId ?? null,
    organizationIds: filters.organizationIds ?? [],
    dateFrom: filters.dateFrom ?? null,
    dateTo: filters.dateTo ?? null,
    period: filters.period ?? null,
    comparisonMode: filters.comparisonMode ?? null,
    language: filters.language ?? null,
    pinnedWidgetIds: filters.pinnedWidgetIds ?? [],
    hiddenWidgetIds: filters.hiddenWidgetIds ?? [],
    lockedPositionWidgetIds: filters.lockedPositionWidgetIds ?? [],
    lockedSizeWidgetIds: filters.lockedSizeWidgetIds ?? [],
  })}`;
}

function readCachedDashboardManifest(filters: DashboardManifestFilters): DashboardManifest | null {
  if (typeof window === "undefined") return null;

  try {
    const raw = window.sessionStorage.getItem(getDashboardManifestCacheKey(filters));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    return parsed as DashboardManifest;
  } catch {
    return null;
  }
}

function storeCachedDashboardManifest(filters: DashboardManifestFilters, manifest: DashboardManifest) {
  if (typeof window === "undefined") return;

  try {
    window.sessionStorage.setItem(getDashboardManifestCacheKey(filters), JSON.stringify(manifest));
  } catch {
    // Ignore cache write failures. The in-memory state still keeps the last manifest visible.
  }
}

function buildManifestFilters(
  state: ReturnType<typeof useBusinessContext>["state"],
): DashboardManifestFilters {
  return {
    organizationId:
      state.organizationMode === "SINGLE" && state.selectedOrganizationIds.length === 1
        ? state.selectedOrganizationIds[0]
        : null,
    organizationIds:
      state.organizationMode === "MULTIPLE" ? state.selectedOrganizationIds : undefined,
    period: state.period.preset,
    dateFrom: state.period.preset === "custom" ? state.period.dateFrom : null,
    dateTo: state.period.preset === "custom" ? state.period.dateTo : null,
    comparisonMode: "previous_period",
    language: "ru",
  };
}

export function DashboardManifestProvider({ children }: { children: ReactNode }) {
  const { state, hydrated } = useBusinessContext();
  const { subscribe } = useBusinessRefresh();
  const [manifest, setManifest] = useState<DashboardManifest | null>(() => readCachedDashboardManifest(buildManifestFilters(state)));
  const [loading, setLoading] = useState(() => readCachedDashboardManifest(buildManifestFilters(state)) === null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const filters = useMemo(() => buildManifestFilters(state), [state]);

  const load = useCallback(async (refresh = false) => {
    if (!hydrated) return;

    try {
      setError(null);
      if (refresh) {
        setRefreshing(true);
      } else {
        const cached = readCachedDashboardManifest(filters);
        setLoading(cached === null);
      }
      const next = await getDashboardManifest(filters);
      setManifest(next);
      storeCachedDashboardManifest(filters, next);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Не удалось загрузить manifest.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [filters, hydrated]);

  useEffect(() => {
    if (!hydrated) return;

    const cached = readCachedDashboardManifest(filters);
    if (cached) {
      setManifest(cached);
      setLoading(false);
    }
  }, [filters, hydrated]);

  useEffect(() => {
    let active = true;

    async function run() {
      if (!active) return;
      await load();
    }

    void run();

    return () => {
      active = false;
    };
  }, [load]);

  useEffect(() => subscribe(() => {
    void load(true);
  }), [load, subscribe]);

  const value = useMemo<DashboardManifestContextValue>(() => ({
    manifest,
    loading,
    refreshing,
    error,
    reload: async () => load(true),
  }), [error, load, loading, manifest, refreshing]);

  return (
    <DashboardManifestContext.Provider value={value}>
      {children}
    </DashboardManifestContext.Provider>
  );
}

export function useDashboardManifest() {
  const context = useContext(DashboardManifestContext);
  if (context === null) {
    throw new Error("useDashboardManifest must be used inside DashboardManifestProvider");
  }
  return context;
}

export function useOptionalDashboardManifest() {
  return useContext(DashboardManifestContext);
}
