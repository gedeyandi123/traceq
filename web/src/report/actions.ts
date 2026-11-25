"use server";

import { revalidatePath } from "next/cache";

import { api, type QualificationReportView } from "@/api/client";
import { isReauthRequiredResponse } from "@/auth/oidc";
import { consumeSignatureBearerHeaders } from "@/auth/session";

export type ReportError =
  | "conflict"
  | "forbidden"
  | "unauthorized"
  | "reauth_required"
  | "notFound"
  | "unprocessable"
  | "failed";

export type ApproveReportActionState = {
  ok: boolean;
  error?: ReportError;
  detail?: string;
  report?: QualificationReportView;
  conclusionNote?: string;
  nextRequalificationDate?: string;
  submittedAt?: number;
};

function field(form: FormData, name: string): string | undefined {
  const v = form.get(name);
  return typeof v === "string" && v.trim() !== "" ? v.trim() : undefined;
}

function errorFromStatus(status: number): ReportError | undefined {
  if (status === 409) return "conflict";
  if (status === 403) return "forbidden";
  if (status === 401) return "unauthorized";
  if (status === 404) return "notFound";
  if (status === 422) return "unprocessable";
  return status >= 200 && status < 300 ? undefined : "failed";
}

function extractDetail(error: unknown): string | undefined {
  if (error && typeof error === "object" && "detail" in error) {
    const d = (error as { detail?: unknown }).detail;
    if (typeof d === "string" && d.trim() !== "") return d;
  }
  return undefined;
}

/** Approves and exports an immutable Qualification Report (PDF) for a completed Execution
 * (Step 7, ADR 0007 SoD + recorded-status notice). Preserves typed form values on error. */
export async function approveQualificationReport(
  _prevState: ApproveReportActionState,
  form: FormData,
): Promise<ApproveReportActionState> {
  const runId = field(form, "run_id") ?? "";
  const executionId = Number(field(form, "execution_id"));
  const expectedRevisionNumber = Number(field(form, "expected_revision_number"));
  const expectedExecutionCopyHash = field(form, "expected_execution_copy_hash") ?? "";
  const rawNote = form.get("conclusion_note");
  const conclusionNote = typeof rawNote === "string" ? rawNote : "";
  const rawDate = form.get("next_requalification_date");
  const nextRequalificationDate = typeof rawDate === "string" ? rawDate.trim() : "";

  if (
    !Number.isInteger(executionId) ||
    executionId <= 0 ||
    !Number.isInteger(expectedRevisionNumber) ||
    expectedRevisionNumber <= 0 ||
    expectedExecutionCopyHash === ""
  ) {
    return {
      ok: false,
      error: "failed",
      conclusionNote,
      nextRequalificationDate,
    };
  }

  let failed: ReportError | undefined;
  let detail: string | undefined;
  let report: QualificationReportView | undefined;
  try {
    const { data, error, response } = await api.POST(
      "/executions/{execution_id}/qualification-reports",
      {
        params: { path: { execution_id: executionId } },
        headers: await consumeSignatureBearerHeaders(),
        body: {
          conclusion_note: conclusionNote.trim() === "" ? null : conclusionNote.trim(),
          next_requalification_date:
            nextRequalificationDate === "" ? null : nextRequalificationDate,
          expected_revision_number: expectedRevisionNumber,
          expected_execution_copy_hash: expectedExecutionCopyHash,
        },
      },
    );
    failed = isReauthRequiredResponse(response)
      ? "reauth_required"
      : errorFromStatus(response.status);
    detail = extractDetail(error);
    report = data;
  } catch {
    failed = "failed";
  }

  if (runId !== "") {
    revalidatePath(`/runs/${runId}`, "layout");
  }
  revalidatePath("/runs/[runId]", "layout");
  revalidatePath("/equipment");

  return failed
    ? {
        ok: false,
        error: failed,
        detail,
        conclusionNote,
        nextRequalificationDate,
      }
    : { ok: true, report, submittedAt: Date.now() };
}
