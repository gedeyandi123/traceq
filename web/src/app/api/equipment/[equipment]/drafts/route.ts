import { NextResponse } from "next/server";

import { API_URL } from "@/api/url";
import { bearerHeaders } from "@/auth/session";

const EQUIPMENT = /^[0-9A-Za-z][0-9A-Za-z_-]{0,63}$/;

/** Auth-forwarding upload proxy for a Protocol Draft PDF. The browser sends the PDF as the
 * body (no file name is forwarded); the bearer token is attached here and never reaches the
 * browser. The API checks role, scope, size, signature, page count and budget. */
export async function POST(
  request: Request,
  context: { params: Promise<{ equipment: string }> },
): Promise<Response> {
  const { equipment } = await context.params;
  if (!EQUIPMENT.test(equipment)) {
    return NextResponse.json({ detail: "Invalid equipment" }, { status: 400 });
  }
  if (!(request.headers.get("content-type") ?? "").toLowerCase().startsWith("application/pdf")) {
    return NextResponse.json({ detail: "Send the PDF as application/pdf" }, { status: 415 });
  }

  let upstream: Response;
  try {
    const init: RequestInit & { duplex: "half" } = {
      method: "POST",
      headers: { ...(await bearerHeaders()), "content-type": "application/pdf" },
      body: request.body,
      duplex: "half",
      cache: "no-store",
    };
    upstream = await fetch(`${API_URL}/equipment/${encodeURIComponent(equipment)}/drafts`, init);
  } catch {
    return NextResponse.json({ detail: "Upstream API unavailable" }, { status: 502 });
  }
  return new NextResponse(await upstream.text(), {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
    },
  });
}
