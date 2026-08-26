"use client";

import { Suspense, type ReactNode } from "react";

import { BusinessContextProvider } from "@/components/business/business-context-provider";
import { BusinessRefreshProvider } from "@/components/business/business-refresh-provider";
import { AppSidebar } from "@/components/shell/app-sidebar";
import { AppTopbar } from "@/components/shell/app-topbar";
import { SessionLockGuard } from "@/components/auth/session-lock-guard";
import { MobileInstallPrompt } from "@/components/pwa/mobile-install-prompt";
import { MobileBottomNav } from "@/components/shell/mobile-bottom-nav";

export function DashboardShell({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <Suspense fallback={null}>
      <SessionLockGuard>
      <BusinessRefreshProvider>
        <BusinessContextProvider>
          <div className="min-h-screen overflow-x-clip bg-[#1E1E21] p-4 pb-24 text-[#f4f7fb] lg:pb-4">
            <div className="flex min-h-[calc(100vh-2rem)] w-full flex-col gap-4">
              <AppTopbar />
              <div className="flex min-h-0 min-w-0 flex-1 items-stretch gap-4">
                <AppSidebar />
                <main className="min-h-0 min-w-0 flex-1">{children}</main>
              </div>
            </div>
          </div>
          <MobileBottomNav />
          <MobileInstallPrompt />
        </BusinessContextProvider>
      </BusinessRefreshProvider>
      </SessionLockGuard>
    </Suspense>
  );
}
