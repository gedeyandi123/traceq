"use server";

import { redirect } from "next/navigation";

import { api } from "@/api/client";
import { bearerHeaders } from "@/auth/session";
import type { ProtocolError } from "@/components/AssembledProtocolView";

function field(form: FormData, name: string): string | undefined {
  const v = form.get(name);
  return typeof v === "string" && v.trim() !== "" ? v.trim() : undefined;
}

function error(status: number): ProtocolError | undefined {
  if (status === 409) return "conflict";
  if (status === 422) return "refused";
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  return status >= 200 && status < 300 ? undefined : "failed";
}

function back(runId: string, failed: ProtocolError | undefined): never {
  const page = `/runs/${encodeURIComponent(runId)}/protocol`;
  redirect(failed ? `${page}?protocolError=${failed}` : page);
}

/** Starts the Protocol of the run's Equipment from the run, with the viewer's token, then
 * returns to the Protocol page. The API checks the role and refuses a second open Protocol;
 * a refusal comes back as the `protocolError` query parameter. */
export async function startProtocol(form: FormData): Promise<void> {
  const runId = field(form, "run_id") ?? "";
  let failed: ProtocolError | undefined;
  try {
    const { response } = await api.POST("/runs/{run_id}/protocol", {
      params: { path: { run_id: runId } },
      headers: await bearerHeaders(),
    });
    failed = error(response.status);
  } catch {
    failed = "failed";
  }
  back(runId, failed);
}

/** Withdraws a Protocol in Draft status with the reason given, then returns to the page. */
export async function withdrawProtocol(form: FormData): Promise<void> {
  const runId = field(form, "run_id") ?? "";
  const protocolId = Number(field(form, "protocol_id"));
  if (!Number.isInteger(protocolId)) back(runId, "failed");
  let failed: ProtocolError | undefined;
  try {
    const { response } = await api.POST("/protocols/{protocol_id}/withdraw", {
      params: { path: { protocol_id: protocolId } },
      headers: await bearerHeaders(),
      body: { reason: field(form, "reason") ?? "" },
    });
    failed = error(response.status);
  } catch {
    failed = "failed";
  }
  back(runId, failed);
}
