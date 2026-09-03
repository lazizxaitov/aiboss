import { NextResponse, type NextRequest } from "next/server";

type VerifyResult = { valid: boolean; backendAvailable: boolean };

// Every page navigation (and every background RSC refetch a "force-dynamic"
// page or a <Link> prefetch triggers) used to make middleware do a fresh
// network round-trip to the FastAPI backend just to re-verify the exact same
// session token — the backend log showed the same token being re-verified
// dozens of times back-to-back, which is wasted backend load and made
// navigation feel slow (every transition waited on that round trip). The
// token is a signed value the backend can only ever answer the same way for
// within a short window, so a brief in-memory cache here removes almost all
// of that redundant traffic without weakening the check: a revoked/changed
// session is still re-verified for real within CACHE_TTL_MS of the change.
const CACHE_TTL_MS = 5_000;
const verifyCache = new Map<string, { result: VerifyResult; expiresAt: number }>();

async function verifyOwnerSession(token: string | undefined): Promise<VerifyResult> {
  if (!token) return { valid: false, backendAvailable: true };

  const cached = verifyCache.get(token);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.result;
  }

  const result = await (async (): Promise<VerifyResult> => {
    try {
      const baseUrl = process.env.CORE_API_URL ?? process.env.NEXT_PUBLIC_CORE_API_URL ?? "http://127.0.0.1:8000";
      const decodedToken = decodeURIComponent(token);
      const response = await fetch(`${baseUrl}/api/v1/auth/verify?token=${encodeURIComponent(decodedToken)}`, {
        cache: "no-store",
        signal: AbortSignal.timeout(1500),
      });
      if (!response.ok) return { valid: false, backendAvailable: true };
      const payload = await response.json() as { valid?: boolean };
      return { valid: payload.valid === true, backendAvailable: true };
    } catch {
      return { valid: false, backendAvailable: false };
    }
  })();

  // Don't cache a "backend unreachable" result — that should keep retrying
  // on the very next request instead of pinning a stale verdict for 5s.
  if (result.backendAvailable) {
    verifyCache.set(token, { result, expiresAt: Date.now() + CACHE_TTL_MS });
    // Keep this from growing forever across many different tokens/logins.
    if (verifyCache.size > 50) {
      const oldestKey = verifyCache.keys().next().value;
      if (oldestKey !== undefined) verifyCache.delete(oldestKey);
    }
  }

  return result;
}

const PUBLIC_PAGE_PREFIXES = ["/telegram-app", "/m/pair"];
const PUBLIC_PAGE_EXACT = ["/m/manifest.webmanifest"];

export async function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname;
  // API requests are authenticated by FastAPI and must reach the same-origin
  // rewrite untouched. Page middleware must not redirect login or API calls.
  if (pathname.startsWith("/api/v1/")) {
    return NextResponse.next();
  }
  // These pages authenticate themselves instead of relying on an existing
  // session cookie — that's the whole point of scanning a QR code on a
  // device that has never logged in before (Telegram Mini App initData +
  // pairing token, or the mobile pairing token + owner password). The
  // mobile manifest is a static resource the OS/browser fetches directly,
  // same reasoning as the desktop manifest.webmanifest exclusion below.
  if (
    PUBLIC_PAGE_EXACT.includes(pathname) ||
    PUBLIC_PAGE_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))
  ) {
    return NextResponse.next();
  }
  const isLoginPage = pathname === "/login";
  const cookieHeader = request.headers.get("cookie") ?? "";
  const sessionCookie = cookieHeader
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith("aibos_owner_session="))
    ?.slice("aibos_owner_session=".length);
  const session = await verifyOwnerSession(sessionCookie);

  // A restarting backend is not a logout. Let the client startup gate wait for
  // health readiness instead of redirecting a valid desktop session to login.
  if (!session.valid && !session.backendAvailable && !isLoginPage) {
    return NextResponse.next();
  }
  if (!session.valid && !isLoginPage) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (session.valid && isLoginPage) {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|login_background\\.png|main%20icon\\.png|manifest\\.webmanifest|sw\\.js|pwa-icon\\.svg).*)"],
};
