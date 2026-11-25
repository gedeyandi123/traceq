"use server";

import { revalidatePath } from "next/cache";

import { api, type CloseOutcome, type ReportExportView } from "@/api/client";
import { bearerHeaders } from "@/auth/session";

export type RoundsError = "conflict" | "forbidden" | "unauthorized" | "notFound" | "unprocessable" | "failed";

export type CloseRoundActionState = {
  ok: boolean;
  error?: RoundsError;
  outcome?: CloseOutcome;
  reason?: string;
  submittedAt?: number;
};

export type ExportReportActionState = {
  ok: boolean;
  error?: RoundsError;
  exportItem?: ReportExportView;
  submittedAt?: number;
};

function field(form: FormData, name: string): string | undefined {
  const v = form.get(name);
  return typeof v === "string" && v.trim() !== "" ? v.trim() : undefined;
}

function errorFromStatus(status: number): RoundsError | undefined {
  if (status === 409) return "conflict";
  if (status === 403) return "forbidden";
  if (status === 401) return "unauthorized";
  if (status === 404) return "notFound";
  if (status === 422) return "unprocessable";
  return status >= 200 && status < 300 ? undefined : "failed";
}

/** Closes a Review Round (`returned_for_revision` or `ready_for_protocol`), preserving
 * submitted form values on 422/409 so typed Reason for Change is never lost. */
export async function closeReviewRound(
  _prevState: CloseRoundActionState,
  form: FormData,
): Promise<CloseRoundActionState> {
  const runId = field(form, "run_id") ?? "";
  const roundId = Number(field(form, "round_id"));
  const rawOutcome = field(form, "outcome");
  const rawReason = form.get("reason");
  const reasonStr = typeof rawReason === "string" ? rawReason : "";
  const outcome: CloseOutcome =
    rawOutcome === "ready_for_protocol" ? "ready_for_protocol" : "returned_for_revision";

  if (!Number.isInteger(roundId) || roundId <= 0) {
    return { ok: false, error: "failed", outcome, reason: reasonStr };
  }
  if (outcome === "returned_for_revision" && reasonStr.trim() === "") {
    return { ok: false, error: "unprocessable", outcome, reason: reasonStr };
  }

  let failed: RoundsError | undefined;
  try {
    const { response } = await api.POST("/rounds/{round_id}/close", {
      params: { path: { round_id: roundId } },
      headers: await bearerHeaders(),
      body: {
        outcome,
        reason: reasonStr.trim() === "" ? null : reasonStr.trim(),
      },
    });
    failed = errorFromStatus(response.status);
  } catch {
    failed = "failed";
  }

  if (runId !== "") {
    revalidatePath(`/runs/${runId}`, "layout");
  }
  revalidatePath("/runs/[runId]", "layout");

  return failed
    ? { ok: false, error: failed, outcome, reason: reasonStr }
    : { ok: true, submittedAt: Date.now() };
}

/** Issues a Pre-review Report (PDF) export for the given Review Round. */
export async function exportPreReviewReport(
  _prevState: ExportReportActionState,
  form: FormData,
): Promise<ExportReportActionState> {
  const runId = field(form, "run_id") ?? "";
  const roundId = Number(field(form, "round_id"));

  if (!Number.isInteger(roundId) || roundId <= 0) {
    return { ok: false, error: "failed" };
  }

  let failed: RoundsError | undefined;
  let exportItem: ReportExportView | undefined;
  try {
    const { data, response } = await api.POST("/rounds/{round_id}/exports", {
      params: { path: { round_id: roundId } },
      headers: await bearerHeaders(),
    });
    failed = errorFromStatus(response.status);
    exportItem = data;
  } catch {
    failed = "failed";
  }

  if (runId !== "") {
    revalidatePath(`/runs/${runId}`, "layout");
  }
  revalidatePath("/runs/[runId]", "layout");

  return failed
    ? { ok: false, error: failed }
    : { ok: true, exportItem, submittedAt: Date.now() };
}
