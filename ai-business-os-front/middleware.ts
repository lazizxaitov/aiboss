import { NextResponse, type NextRequest } from "next/server";

async function verifyOwnerSession(token: string | undefined) {
  if (!token) return { valid: false, backendAvailable: true };
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
}

export async function middleware(request: NextRequest) {
  // API requests are authenticated by FastAPI and must reach the same-origin
  // rewrite untouched. Page middleware must not redirect login or API calls.
  if (request.nextUrl.pathname.startsWith("/api/v1/")) {
    return NextResponse.next();
  }
  const isLoginPage = request.nextUrl.pathname === "/login";
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
