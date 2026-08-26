import type { Metadata, Viewport } from "next";
import { PwaClient } from "@/components/pwa/pwa-client";
import { Montserrat } from "next/font/google";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import "./globals.css";

const montserrat = Montserrat({
  variable: "--font-montserrat",
  subsets: ["latin", "cyrillic"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "AI БОС — панель управления",
  description: "Единый интерфейс бизнес-данных, аналитики и управления.",
  applicationName: "AI Business OS",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "AI BOS", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#1E1E21",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru" className={`${montserrat.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-[#1E1E21] text-[#f4f7fb]"><PwaClient />{children}</body>
    </html>
  );
}
