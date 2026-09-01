"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";

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
            <DashboardErrorBoundary fallback="Не удалось отобразить виджеты Dashboard.">
              <DashboardGrid />
            </DashboardErrorBoundary>
          </div>
          <DashboardErrorBoundary fallback="AI-панель временно недоступна.">
            <DashboardAssistantPanel />
          </DashboardErrorBoundary>
        </div>
      </section>
    </DashboardManifestProvider>
  );
}

class DashboardErrorBoundary extends Component<
  { children: ReactNode; fallback: string },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // Keep a malformed Dashboard payload from taking down the application shell.
  }

  render() {
    return this.state.hasError
      ? <p className="rounded-[28px] bg-[#2E3137] p-6 text-sm text-slate-300">{this.props.fallback}</p>
      : this.props.children;
  }
}
