import { NextResponse } from "next/server";

import { API_URL } from "@/api/url";
import { bearerHeaders } from "@/auth/session";

const RUN_ID = /^[0-9A-Za-z][0-9A-Za-z_-]{0,63}$/;
const DOC_ID = /^[0-9A-Za-z][0-9A-Za-z._-]{0,127}$/;
const REV = /^\d{1,6}$/;

type Context = { params: Promise<{ runId: string; docId: string; rev: string }> };

/** Auth-forwarding proxy for a cited document: the run routes need a bearer token, which a
 * browser cannot attach to an iframe or a link, so the httpOnly cookie is turned into one
 * here. Validates the path parts, then streams the API's answer without a shared cache. */
async function forward(method: "GET" | "HEAD", context: Context): Promise<Response> {
  const { runId, docId, rev } = await context.params;
  if (!RUN_ID.test(runId) || !DOC_ID.test(docId) || !REV.test(rev)) {
    return NextResponse.json({ detail: "Invalid run, document or revision" }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(
      `${API_URL}/runs/${encodeURIComponent(runId)}/documents/${encodeURIComponent(docId)}/${rev}`,
      { method, headers: await bearerHeaders(), cache: "no-store" },
    );
  } catch {
    return NextResponse.json({ detail: "Upstream API unavailable" }, { status: 502 });
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
  headers.set("cache-control", "private, no-store");
  return new NextResponse(method === "HEAD" ? null : upstream.body, { status: 200, headers });
}

export async function GET(_request: Request, context: Context): Promise<Response> {
  return forward("GET", context);
}

export async function HEAD(_request: Request, context: Context): Promise<Response> {
  return forward("HEAD", context);
}
