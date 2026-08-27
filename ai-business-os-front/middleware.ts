import { NextResponse, type NextRequest } from "next/server";

async function isValidOwnerSession(token: string | undefined) {
  if (!token) return false;
  try {
    const baseUrl = process.env.CORE_API_URL ?? process.env.NEXT_PUBLIC_CORE_API_URL ?? "http://127.0.0.1:8000";
    const decodedToken = decodeURIComponent(token);
    const response = await fetch(`${baseUrl}/api/v1/auth/verify?token=${encodeURIComponent(decodedToken)}`, { cache: "no-store" });
    if (!response.ok) return false;
    const payload = await response.json() as { valid?: boolean };
    return payload.valid === true;
  } catch {
    return false;
  }
}

export async function middleware(request: NextRequest) {
  const isLoginPage = request.nextUrl.pathname === "/login";
  const cookieHeader = request.headers.get("cookie") ?? "";
  const sessionCookie = cookieHeader
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith("aibos_owner_session="))
    ?.slice("aibos_owner_session=".length);
  const hasOwnerSession = await isValidOwnerSession(sessionCookie);

  if (!hasOwnerSession && !isLoginPage) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (hasOwnerSession && isLoginPage) {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|login_background\\.png|main%20icon\\.png|manifest\\.webmanifest|sw\\.js|pwa-icon\\.svg).*)"],
};
