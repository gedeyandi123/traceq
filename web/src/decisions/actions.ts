"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { api } from "@/api/client";
import { bearerHeaders } from "@/auth/session";
import type { DecisionError } from "@/components/Decisions";
import { buildDecisionRedirect } from "@/decisions/redirect";
import { COVERAGE_CLASSES } from "@/decisions/vocabulary";

const DECISIONS = ["accepted", "rejected", "edited"] as const;

/** The path of each screen a decision form can be on, after the run's own; the matrix is "". */
const SCREENS: Partial<Record<string, string>> = {
  findings: "/findings",
  draft: "/draft",
  protocol: "/protocol",
};

function field(form: FormData, name: string): string | undefined {
  const v = form.get(name);
  return typeof v === "string" && v.trim() !== "" ? v.trim() : undefined;
}

/** Records one Proposal Decision through the API with the viewer's token, then returns to
 * the screen the form was on. The API decides whether it is allowed and whether a Reason for
 * Change is needed; a refusal comes back as the `error` query parameter. */
export async function decide(form: FormData): Promise<void> {
  const runId = field(form, "run_id") ?? "";
  const screen = SCREENS[field(form, "screen") ?? ""] ?? "";
  const back = `/runs/${encodeURIComponent(runId)}${screen}`;
  const returnQuery = field(form, "return_query");
  const anchor = field(form, "anchor");
  const decision = DECISIONS.find((d) => d === field(form, "decision"));
  const proposalId = Number(field(form, "proposal_id"));
  if (decision === undefined || !Number.isInteger(proposalId)) {
    redirect(buildDecisionRedirect(back, { error: "failed", returnQuery, anchor }));
  }
  let error: DecisionError | undefined;
  try {
    const { response } = await api.POST("/runs/{run_id}/proposals/{proposal_id}/decisions", {
      params: { path: { run_id: runId, proposal_id: proposalId } },
      headers: await bearerHeaders(),
      body: {
        decision,
        coverage: COVERAGE_CLASSES.find((c) => c === field(form, "coverage")) ?? null,
        reason: field(form, "reason") ?? null,
      },
    });
    if (response.status === 422) error = "refused";
    else if (response.status === 409) error = "conflict";
    else if (response.status === 401) error = "unauthorized";
    else if (response.status === 403) error = "forbidden";
    else if (!response.ok) error = "failed";
  } catch {
    error = "failed";
  }
  revalidatePath("/runs/[runId]", "layout");
  redirect(buildDecisionRedirect(back, { error, returnQuery, anchor }));
}
