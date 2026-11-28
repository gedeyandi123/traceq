import { NextResponse } from "next/server";

import { API_URL } from "@/api/url";
import { bearerHeaders } from "@/auth/session";

const POSITIVE_INT = /^[1-9]\d*$/;

/** Auth-forwarding poll of one upload job: the bearer token is attached here. */
export async function GET(
  _request: Request,
  context: { params: Promise<{ jobId: string }> },
): Promise<Response> {
  const { jobId } = await context.params;
  if (!POSITIVE_INT.test(jobId)) {
    return NextResponse.json({ detail: "Invalid jobId" }, { status: 400 });
  }
  let upstream: Response;
  try {
    upstream = await fetch(`${API_URL}/uploads/${jobId}`, {
      method: "GET",
      headers: await bearerHeaders(),
      cache: "no-store",
    });
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
