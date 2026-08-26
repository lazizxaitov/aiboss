import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "AI Business OS",
    short_name: "AI BOS",
    description: "Панель управления бизнесом, аналитика и AI Chat.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#1E1E21",
    theme_color: "#1E1E21",
    lang: "ru",
    icons: [{ src: "/pwa-icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
  };
}
