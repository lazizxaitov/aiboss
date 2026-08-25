"use client";

import { Suspense, type ReactNode } from "react";

import { BusinessContextProvider } from "@/components/business/business-context-provider";
import { BusinessRefreshProvider } from "@/components/business/business-refresh-provider";
import { AppSidebar } from "@/components/shell/app-sidebar";
import { AppTopbar } from "@/components/shell/app-topbar";

export function DashboardShell({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <Suspense fallback={null}>
      <BusinessRefreshProvider>
        <BusinessContextProvider>
          <div className="min-h-screen bg-[#1E1E21] p-4 text-[#f4f7fb]">
            <div className="flex min-h-[calc(100vh-2rem)] w-full flex-col gap-4">
              <AppTopbar />
              <div className="flex min-h-0 min-w-0 flex-1 items-stretch gap-4">
                <AppSidebar />
                <main className="min-h-0 min-w-0 flex-1">{children}</main>
              </div>
            </div>
          </div>
        </BusinessContextProvider>
      </BusinessRefreshProvider>
    </Suspense>
  );
}
