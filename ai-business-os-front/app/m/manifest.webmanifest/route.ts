// A dedicated manifest for the mobile PWA experience under /m, served as a
// plain route handler (rather than the app/manifest.ts convention) so it
// keeps its own name/icon/start_url independent from the main desktop
// manifest at the site root. Linked from app/m/layout.tsx's metadata.
export async function GET() {
  const manifest = {
    name: "AI BOS Mobile",
    short_name: "AI BOS",
    description: "Мобильная версия AI Business OS.",
    start_url: "/m",
    scope: "/m",
    display: "standalone",
    orientation: "portrait",
    background_color: "#1E1E21",
    theme_color: "#1E1E21",
    lang: "ru",
    // Reuses the desktop app icon for now — swap this src for a dedicated
    // mobile icon file under /public whenever one is provided.
    icons: [{ src: "/main%20icon.png", sizes: "4272x4144", type: "image/png", purpose: "any" }],
  };
  return new Response(JSON.stringify(manifest), {
    headers: { "Content-Type": "application/manifest+json" },
  });
}
