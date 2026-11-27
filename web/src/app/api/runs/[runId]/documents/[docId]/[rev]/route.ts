import { NextResponse } from "next/server";

import { API_URL } from "@/api/url";
import { bearerHeaders } from "@/auth/session";

const RUN_ID = /^[0-9A-Za-z][0-9A-Za-z_-]{0,63}$/;
const DOC_ID = /^[0-9A-Za-z][0-9A-Za-z._-]{0,127}$/;
const REV = /^\d{1,6}$/;

type Context = { params: Promise<{ runId: string; docId: string; rev: string }> };

/** Auth-forwarding proxy for a cited document: the run routes need a bearer token, which a
 * browser cannot attach to an iframe or a link, so the httpOnly cookie is turned into one
 * here. Validates the path parts, then streams the API's answer, keeping its private cache-control and ETag (304 on a match). */
async function forward(
  method: "GET" | "HEAD",
  context: Context,
  ifNoneMatch: string | null,
): Promise<Response> {
  const { runId, docId, rev } = await context.params;
  if (!RUN_ID.test(runId) || !DOC_ID.test(docId) || !REV.test(rev)) {
    return NextResponse.json({ detail: "Invalid run, document or revision" }, { status: 400 });
  }

  let upstream: Response;
  try {
    const reqHeaders: Record<string, string> = { ...(await bearerHeaders()) };
    if (ifNoneMatch) reqHeaders["if-none-match"] = ifNoneMatch;
    upstream = await fetch(
      `${API_URL}/runs/${encodeURIComponent(runId)}/documents/${encodeURIComponent(docId)}/${rev}`,
      { method, headers: reqHeaders, cache: "no-store" },
    );
  } catch {
    return NextResponse.json({ detail: "Upstream API unavailable" }, { status: 502 });
  }

  if (upstream.status === 304) {
    const notModified = new Headers();
    for (const name of ["etag", "cache-control"]) {
      const value = upstream.headers.get(name);
      if (value) notModified.set(name, value);
    }
    return new NextResponse(null, { status: 304, headers: notModified });
  }

  if (!upstream.ok) {
    const bodyText = method === "HEAD" ? "" : await upstream.text().catch(() => "");
    return new NextResponse(bodyText || null, {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "application/json",
        "cache-control": "no-store",
      },
    });
  }

  const headers = new Headers();
  for (const name of ["content-type", "content-disposition", "content-security-policy", "etag"]) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  // Passed through as the API sent it (it sends `private`); the fallback is for an upstream that sent none.
  headers.set("cache-control", upstream.headers.get("cache-control") ?? "private, no-store");
  return new NextResponse(method === "HEAD" ? null : upstream.body, { status: 200, headers });
}

export async function GET(request: Request, context: Context): Promise<Response> {
  return forward("GET", context, request.headers.get("if-none-match"));
}

export async function HEAD(request: Request, context: Context): Promise<Response> {
  return forward("HEAD", context, request.headers.get("if-none-match"));
}
