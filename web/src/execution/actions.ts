"use server";

import { revalidatePath } from "next/cache";

import { api } from "@/api/client";
import { bearerHeaders } from "@/auth/session";

export type ExecutionError = "conflict" | "forbidden" | "unauthorized" | "notFound" | "failed";

export type ExecutionActionState = {
  ok: boolean;
  error?: ExecutionError;
  submittedAt?: number;
};

function field(form: FormData, name: string): string | undefined {
  const v = form.get(name);
  return typeof v === "string" && v.trim() !== "" ? v.trim() : undefined;
}

function errorFromStatus(status: number): ExecutionError | undefined {
  if (status === 409) return "conflict";
  if (status === 403) return "forbidden";
  if (status === 401) return "unauthorized";
  if (status === 404) return "notFound";
  return status >= 200 && status < 300 ? undefined : "failed";
}

/** Starts an Execution of an Approved Protocol (ADR 0013, spec #270, #271), then
 * revalidates the run layout so sidebar and page state stay fresh. */
export async function startExecution(
  _prevState: ExecutionActionState,
  form: FormData,
): Promise<ExecutionActionState> {
  const protocolId = Number(field(form, "protocol_id"));
  if (!Number.isInteger(protocolId)) {
    return { ok: false, error: "failed" };
  }
  let failed: ExecutionError | undefined;
  try {
    const { response } = await api.POST("/protocols/{protocol_id}/execution", {
      params: { path: { protocol_id: protocolId } },
      headers: await bearerHeaders(),
    });
    failed = errorFromStatus(response.status);
  } catch {
    failed = "failed";
  }
  revalidatePath("/runs/[runId]", "layout");
  return failed ? { ok: false, error: failed } : { ok: true, submittedAt: Date.now() };
}
