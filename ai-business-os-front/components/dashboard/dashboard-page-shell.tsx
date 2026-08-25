"use client";

import { BusinessContextBar } from "@/components/business/business-context-bar";
import { DashboardAssistantPanel, DashboardGrid } from "@/components/dashboard/dashboard-grid";
import { DashboardManifestProvider } from "@/components/dashboard/dashboard-manifest-provider";

export function DashboardPageShell() {
  return (
    <DashboardManifestProvider>
      <section className="w-full min-w-0">
        <div className="grid w-full min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_420px] xl:items-start">
          <div className="min-w-0 space-y-5">
            <BusinessContextBar />
            <DashboardGrid />
          </div>
          <DashboardAssistantPanel />
        </div>
      </section>
    </DashboardManifestProvider>
  );
}
