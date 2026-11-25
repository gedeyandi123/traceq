import { NextResponse } from "next/server";

import { API_URL } from "@/api/url";
import { bearerHeaders } from "@/auth/session";

const POSITIVE_INT = /^[1-9]\d*$/;

/** Auth-forwarding PDF proxy for Pre-review Report exports.
 * Validates `roundId` and `exportId` as positive integers, attaches the httpOnly bearer
 * token, and streams the backend PDF response without caching. */
export async function GET(
  _request: Request,
  context: { params: Promise<{ roundId: string; exportId: string }> },
): Promise<Response> {
  const { roundId, exportId } = await context.params;
  if (!POSITIVE_INT.test(roundId) || !POSITIVE_INT.test(exportId)) {
    return NextResponse.json({ detail: "Invalid roundId or exportId" }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${API_URL}/rounds/${roundId}/exports/${exportId}/pdf`, {
      method: "GET",
      headers: await bearerHeaders(),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "Upstream API unavailable" }, { status: 502 });
  }

  if (!upstream.ok) {
    const bodyText = await upstream.text().catch(() => "");
    return new NextResponse(bodyText || null, {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "application/json",
        "cache-control": "no-store",
      },
    });
  }

  const headers = new Headers();
  headers.set("content-type", upstream.headers.get("content-type") ?? "application/pdf");
  const disposition = upstream.headers.get("content-disposition");
  if (disposition) {
    headers.set("content-disposition", disposition);
  }
  headers.set("cache-control", "no-store");

  return new NextResponse(upstream.body, {
    status: 200,
    headers,
  });
}
