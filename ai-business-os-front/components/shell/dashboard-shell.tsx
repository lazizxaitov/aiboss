"use client";

import { Suspense, type ReactNode } from "react";

import { BusinessContextProvider } from "@/components/business/business-context-provider";
import { BusinessRefreshProvider } from "@/components/business/business-refresh-provider";
import { AppSidebar } from "@/components/shell/app-sidebar";
import { AppTopbar } from "@/components/shell/app-topbar";
import { SessionLockGuard } from "@/components/auth/session-lock-guard";
import { MobileInstallPrompt } from "@/components/pwa/mobile-install-prompt";
import { MobileBottomNav } from "@/components/shell/mobile-bottom-nav";
import { DashboardAssistantPanel } from "@/components/dashboard/dashboard-grid";
import { BackendStartupGate } from "@/components/startup/backend-startup-gate";
import { SleepModeOverlay } from "@/components/shell/sleep-mode-overlay";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

export function DashboardShell({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  const pathname = usePathname();
  const [sleepMode, setSleepMode] = useState(false);
  useEffect(() => {
    const open = () => setSleepMode(true);
    window.addEventListener("aibos-enter-sleep-mode", open);
    return () => window.removeEventListener("aibos-enter-sleep-mode", open);
  }, []);
  return (
    <Suspense fallback={null}>
      <BackendStartupGate>
      <SessionLockGuard>
      <BusinessRefreshProvider>
        <BusinessContextProvider>
          <div className="min-h-screen overflow-x-clip bg-[#1E1E21] p-4 pb-24 text-[#f4f7fb] lg:pb-4">
            {/* Previously capped at max-w-[1920px], then max-w-[2600px], to
                stop the dashboard grid from spreading widgets too far apart
                on ultra-wide monitors — but any fixed cap letterboxes the
                whole shell (topbar, sidebar, grid) on a bigger screen (a 4K
                TV is 3840px wide), which is exactly the "doesn't fill my
                screen" complaint. The actual "spread out" problem is now
                fixed at the grid level instead of by capping width: extra
                xl/xxl breakpoints add more columns on wide screens, and
                launcher/composer.js's row-fill grows widgets to close any
                left-over row width. So the shell itself goes back to filling
                the full viewport width on any monitor, TV included. */}
            <div className="mx-auto flex min-h-[calc(100vh-2rem)] w-full flex-col gap-4">
              <AppTopbar />
              <div className="flex min-h-0 min-w-0 flex-1 items-stretch gap-4">
                <AppSidebar />
                <main className="min-h-0 min-w-0 flex-1">{children}</main>
              </div>
            </div>
          </div>
          <MobileBottomNav />
          <MobileInstallPrompt />
          {pathname !== "/" ? <DashboardAssistantPanel floating /> : null}
        </BusinessContextProvider>
      </BusinessRefreshProvider>
      </SessionLockGuard>
      </BackendStartupGate>
      {sleepMode ? <SleepModeOverlay onClose={() => setSleepMode(false)} /> : null}
    </Suspense>
  );
}
