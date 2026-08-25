"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  getBusinessRefreshController,
  type BusinessFreshnessSnapshot,
  type BusinessRefreshControllerOptions,
  type WorkspaceRefreshHandler,
} from "@/lib/business-refresh";

type BusinessRefreshContextValue = {
  snapshot: BusinessFreshnessSnapshot | null;
  refreshNow: () => Promise<void>;
};

const BusinessRefreshContext = createContext<BusinessRefreshContextValue | null>(null);

export type BusinessRefreshProviderProps = Omit<BusinessRefreshControllerOptions, "refresh" | "onStatusChange"> & {
  refresh: WorkspaceRefreshHandler;
  onStatusChange?: (snapshot: BusinessFreshnessSnapshot) => void;
  children: ReactNode;
};

export function BusinessRefreshProvider({
  children,
  refresh,
  onStatusChange,
  ...controllerOptions
}: BusinessRefreshProviderProps) {
  const [snapshot, setSnapshot] = useState<BusinessFreshnessSnapshot | null>(null);

  const controller = useMemo(
    () =>
      getBusinessRefreshController({
        ...controllerOptions,
        refresh,
      }),
    [
      controllerOptions.baseUrl,
      controllerOptions.hiddenIntervalMs,
      controllerOptions.staleAfterSeconds,
      controllerOptions.visibleIntervalMs,
      refresh,
    ],
  );

  useEffect(() => controller.subscribe(refresh), [controller, refresh]);

  useEffect(() => controller.subscribeStatus(setSnapshot), [controller]);

  useEffect(() => {
    if (snapshot) {
      onStatusChange?.(snapshot);
    }
  }, [onStatusChange, snapshot]);

  useEffect(() => {
    void controller.refreshNow();
  }, [controller]);

  const value = useMemo<BusinessRefreshContextValue>(
    () => ({
      snapshot,
      refreshNow: () => controller.refreshNow(),
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
