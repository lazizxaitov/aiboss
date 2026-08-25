"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  getBusinessRefreshController,
  type BusinessFreshnessSnapshot,
  type BusinessRefreshControllerOptions,
  type WorkspaceRefreshHandler,
} from "@/lib/business-refresh";
import { prefetchSmartUpOrganizations } from "@/lib/core-api";

type BusinessRefreshContextValue = {
  snapshot: BusinessFreshnessSnapshot | null;
  refreshNow: () => Promise<void>;
  subscribe: (refresh: WorkspaceRefreshHandler) => () => void;
};

const BusinessRefreshContext = createContext<BusinessRefreshContextValue | null>(null);

export type BusinessRefreshProviderProps = BusinessRefreshControllerOptions & {
  children: ReactNode;
};

export function BusinessRefreshProvider({
  children,
  visibleIntervalMs,
  hiddenIntervalMs,
  staleAfterSeconds,
}: BusinessRefreshProviderProps) {
  const [snapshot, setSnapshot] = useState<BusinessFreshnessSnapshot | null>(null);

  const controller = useMemo(
    () =>
      getBusinessRefreshController({
        visibleIntervalMs,
        hiddenIntervalMs,
        staleAfterSeconds,
      }),
    [hiddenIntervalMs, staleAfterSeconds, visibleIntervalMs],
  );

  useEffect(() => controller.subscribeStatus(setSnapshot), [controller]);

  useEffect(() => {
    void controller.refreshNow();
  }, [controller]);

  useEffect(() => {
    void prefetchSmartUpOrganizations();
  }, []);

  const value = useMemo<BusinessRefreshContextValue>(
    () => ({
      snapshot,
      refreshNow: () => controller.refreshNow(),
      subscribe: (refresh: WorkspaceRefreshHandler) => controller.subscribe(refresh),
    }),
    [controller, snapshot],
  );

  return <BusinessRefreshContext.Provider value={value}>{children}</BusinessRefreshContext.Provider>;
}

export function useBusinessRefresh() {
  const context = useContext(BusinessRefreshContext);
  if (!context) {
    throw new Error("useBusinessRefresh must be used within a BusinessRefreshProvider");
  }
  return context;
}
