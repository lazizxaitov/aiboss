import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

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
  return <div className="min-h-dvh w-full overflow-x-hidden bg-[#1E1E21] text-[#f4f7fb]">{children}</div>;
}
