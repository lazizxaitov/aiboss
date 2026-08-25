"use client";

import { createContext, useContext, type ReactNode } from "react";

type DashboardThemeValue = {
  dark: boolean;
};

const DashboardThemeContext = createContext<DashboardThemeValue>({ dark: false });

export function DashboardThemeProvider({
  dark,
  children,
}: Readonly<{
  dark: boolean;
  children: ReactNode;
}>) {
  return <DashboardThemeContext.Provider value={{ dark }}>{children}</DashboardThemeContext.Provider>;
}

export function useDashboardTheme() {
  return useContext(DashboardThemeContext);
}
