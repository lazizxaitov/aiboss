"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { SessionLockGuard } from "@/components/auth/session-lock-guard";

// The desktop app auto-locks an idle session behind a PIN
// (components/shell/dashboard-shell.tsx via SessionLockGuard). The mobile
// PWA had no equivalent — its cookie is long-lived (30 days, set at
// /m/pair) and, until now, nothing ever locked it again. A lost or stolen
// phone with the PWA installed would stay fully signed in for a month with
// no re-check at all. Reusing SessionLockGuard here gives mobile the same
// protection, redirected back into /m instead of the desktop "/".
//
// /m/pair is the one page under /m that must stay reachable without an
// existing session — that's the whole point of scanning a QR code on a
// phone that has never logged in — so it's excluded here the same way
// middleware.ts excludes it from the cookie check.
export function MobileAuthGate({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/m/pair" || pathname.startsWith("/m/pair/")) {
    return <>{children}</>;
  }
  return <SessionLockGuard lockedRedirectTo="/m">{children}</SessionLockGuard>;
}
