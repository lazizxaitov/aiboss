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
  const [manifest, setManifest] = useState<DashboardManifest | null>(null);
  const [loading, setLoading] = useState(true);
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
        setLoading(true);
      }
      const next = await getDashboardManifest(filters);
      setManifest(next);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Не удалось загрузить manifest.");
      setManifest(null);
    } finally {
      setLoading(false);
      setRefreshing(false);
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

  useEffect(() => subscribe(() => load(true)), [load, subscribe]);

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
