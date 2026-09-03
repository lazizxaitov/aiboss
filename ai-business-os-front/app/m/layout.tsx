import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { MobileComposerProvider } from "@/components/mobile/mobile-composer-context";

// Everything under /m (the mobile web-app experience, reached by scanning
// the QR code in Settings → "Мобильные устройства") gets its own manifest —
// a distinct name/icon so "Add to Home Screen" from here creates its own
// icon, separate from the main desktop AI Business OS PWA.
export const metadata: Metadata = {
  title: "AI BOS",
  manifest: "/m/manifest.webmanifest",
  appleWebApp: { capable: true, title: "AI BOS", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#1E1E21",
};

export default function MobileRootLayout({ children }: Readonly<{ children: ReactNode }>) {
  // overflow-x-hidden here is the safety net for the whole /m subtree: no
  // page nested under this layout can ever push the viewport into a
  // horizontal scrollbar, whatever its own content does.
  //
  // MobileComposerProvider lives here (not in the (shell) layout) because
  // /m/chat is a top-level route (its own layout tree), a sibling of the
  // (shell) route group rather than a child of it — the Action button
  // (rendered inside (shell)/layout.tsx) and /m/chat/page.tsx must share
  // ONE provider instance for the pending-draft handoff to work, and this
  // root layout is their nearest common ancestor.
  return (
    <div className="min-h-dvh w-full overflow-x-hidden bg-[#1E1E21] text-[#f4f7fb]">
      <MobileComposerProvider>{children}</MobileComposerProvider>
    </div>
  );
}
