import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const backend = process.env.CORE_API_URL ?? "http://127.0.0.1:8000";
  const headers = new Headers();
  for (const name of ["authorization", "content-type", "accept", "x-request-id"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  try {
    const response = await fetch(`${backend}/api/v1/ai/chat`, {
      method: "POST",
      headers,
      body: await request.arrayBuffer(),
      signal: request.signal,
      cache: "no-store",
    });
    const responseHeaders = new Headers();
    for (const name of ["content-type", "cache-control", "x-accel-buffering", "vary"]) {
      const value = response.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      return new Response(null, { status: 499 });
    }
    return new Response(JSON.stringify({ detail: "AI chat transport is unavailable" }), {
      status: 502,
      headers: { "content-type": "application/json" },
    });
  }
}
