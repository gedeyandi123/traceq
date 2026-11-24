"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { api } from "@/api/client";
import { bearerHeaders } from "@/auth/session";
import type { ProtocolError } from "@/components/AssembledProtocolView";
import { stepFrom } from "@/protocol/form";

export type ProtocolFormActionState = {
  ok: boolean;
  error?: ProtocolError;
  submittedAt?: number;
};

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
  revalidatePath("/runs/[runId]", "layout");
  const page = `/runs/${encodeURIComponent(runId)}/protocol`;
  redirect(failed ? `${page}?protocolError=${failed}` : page);
}

function inlineResult(failed: ProtocolError | undefined): ProtocolFormActionState {
  revalidatePath("/runs/[runId]", "layout");
  return failed ? { ok: false, error: failed } : { ok: true, submittedAt: Date.now() };
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

/** Adds a version of a requirement's written Test Step from the write form, with no Reason
 * for Change, then returns to the page. A form that is not a complete Test Step in one of the
 * four Acceptance Criterion shapes is not sent. */
export async function writeTestStep(form: FormData): Promise<void> {
  const runId = field(form, "run_id") ?? "";
  const protocolId = Number(field(form, "protocol_id"));
  const requirement = field(form, "requirement") ?? "";
  const step = stepFrom(form);
  if (!Number.isInteger(protocolId) || requirement === "") back(runId, "failed");
  if (step === null) back(runId, "invalid");
  let failed: ProtocolError | undefined;
  try {
    const { response } = await api.POST("/protocols/{protocol_id}/test-steps/{requirement}", {
      params: { path: { protocol_id: protocolId, requirement } },
      headers: await bearerHeaders(),
      body: { test_step: step },
    });
    failed = error(response.status);
  } catch {
    failed = "failed";
  }
  back(runId, failed);
}

/** Removes a requirement's written Test Step (a version that takes it back), then returns. */
export async function removeTestStep(form: FormData): Promise<void> {
  const runId = field(form, "run_id") ?? "";
  const protocolId = Number(field(form, "protocol_id"));
  const requirement = field(form, "requirement") ?? "";
  if (!Number.isInteger(protocolId) || requirement === "") back(runId, "failed");
  let failed: ProtocolError | undefined;
  try {
    const { response } = await api.POST("/protocols/{protocol_id}/test-steps/{requirement}", {
      params: { path: { protocol_id: protocolId, requirement } },
      headers: await bearerHeaders(),
      body: { test_step: null },
    });
    failed = error(response.status);
  } catch {
    failed = "failed";
  }
  back(runId, failed);
}

/** Edits a drafted Test Step: the `edited` decision with its Reason for Change and the Test
 * Step it gives, in one request, then returns to the page. */
export async function editDraftedTestStep(form: FormData): Promise<void> {
  const runId = field(form, "run_id") ?? "";
  const protocolId = Number(field(form, "protocol_id"));
  const proposalId = Number(field(form, "proposal_id"));
  const step = stepFrom(form);
  if (!Number.isInteger(protocolId) || !Number.isInteger(proposalId)) back(runId, "failed");
  if (step === null) back(runId, "invalid");
  let failed: ProtocolError | undefined;
  try {
    const { response } = await api.POST("/protocols/{protocol_id}/drafts/{proposal_id}/edit", {
      params: { path: { protocol_id: protocolId, proposal_id: proposalId } },
      headers: await bearerHeaders(),
      body: { reason: field(form, "reason") ?? "", test_step: step },
    });
    failed = error(response.status);
  } catch {
    failed = "failed";
  }
  back(runId, failed);
}

/** Answers a printed requirement number the run missed (`not_a_requirement` or
 * `not_tested_here`, with a justification), then returns to the page. No Reason for Change:
 * a later answer replaces the earlier, which the API keeps. */
export async function answerMissedNumber(form: FormData): Promise<void> {
  const runId = field(form, "run_id") ?? "";
  const protocolId = Number(field(form, "protocol_id"));
  const rev = Number(field(form, "rev"));
  const doc = field(form, "doc") ?? "";
  const number = field(form, "number") ?? "";
  const kind = field(form, "kind");
  if (!Number.isInteger(protocolId) || !Number.isInteger(rev) || doc === "" || number === "") back(runId, "failed");
  if (kind !== "not_a_requirement" && kind !== "not_tested_here") back(runId, "invalid");
  let failed: ProtocolError | undefined;
  try {
    const { response } = await api.POST("/protocols/{protocol_id}/missed-numbers", {
      params: { path: { protocol_id: protocolId } },
      headers: await bearerHeaders(),
      body: { doc, rev, number, kind, justification: field(form, "justification") ?? "" },
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

/** Approves a Submitted Protocol, bound to the submission the Approver read (its event id and
 * hash, from hidden fields), then returns to the page. A recorded status, not an Electronic
 * Signature. The API refuses (409) a stale submission, the Preparer and any author. */
export async function approveProtocol(form: FormData): Promise<void> {
  const runId = field(form, "run_id") ?? "";
  const protocolId = Number(field(form, "protocol_id"));
  const eventId = Number(field(form, "submission_event_id"));
  const hash = field(form, "hash") ?? "";
  if (!Number.isInteger(protocolId) || !Number.isInteger(eventId) || hash === "") back(runId, "failed");
  let failed: ProtocolError | undefined;
  try {
    const { response } = await api.POST("/protocols/{protocol_id}/approve", {
      params: { path: { protocol_id: protocolId } },
      headers: await bearerHeaders(),
      body: { submission_event_id: eventId, hash },
    });
    failed = error(response.status);
  } catch {
    failed = "failed";
  }
  back(runId, failed);
}

/** Returns a Submitted Protocol to Draft with the reason given, then returns to the page. */
export async function returnProtocol(form: FormData): Promise<void> {
  const runId = field(form, "run_id") ?? "";
  const protocolId = Number(field(form, "protocol_id"));
  if (!Number.isInteger(protocolId)) back(runId, "failed");
  let failed: ProtocolError | undefined;
  try {
    const { response } = await api.POST("/protocols/{protocol_id}/return", {
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

/** Submits a Protocol in Draft status that nothing blocks, then returns to the page, which
 * shows the frozen copy and its hash. The API checks again what blocks and refuses (409). */
export async function submitProtocol(form: FormData): Promise<void> {
  const runId = field(form, "run_id") ?? "";
  const protocolId = Number(field(form, "protocol_id"));
  if (!Number.isInteger(protocolId)) back(runId, "failed");
  let failed: ProtocolError | undefined;
  try {
    const { response } = await api.POST("/protocols/{protocol_id}/submit", {
      params: { path: { protocol_id: protocolId } },
      headers: await bearerHeaders(),
    });
    failed = error(response.status);
  } catch {
    failed = "failed";
  }
  back(runId, failed);
}

/** Inline `useActionState` variant of `writeTestStep` for drawer forms. */
export async function writeTestStepInline(
  _prevState: ProtocolFormActionState,
  form: FormData,
): Promise<ProtocolFormActionState> {
  const protocolId = Number(field(form, "protocol_id"));
  const requirement = field(form, "requirement") ?? "";
  const step = stepFrom(form);
  if (!Number.isInteger(protocolId) || requirement === "") return { ok: false, error: "failed" };
  if (step === null) return { ok: false, error: "invalid" };
  let failed: ProtocolError | undefined;
  try {
    const { response } = await api.POST("/protocols/{protocol_id}/test-steps/{requirement}", {
      params: { path: { protocol_id: protocolId, requirement } },
      headers: await bearerHeaders(),
      body: { test_step: step },
    });
    failed = error(response.status);
  } catch {
    failed = "failed";
  }
  return inlineResult(failed);
}

/** Inline `useActionState` variant of `removeTestStep` for drawer forms. */
export async function removeTestStepInline(
  _prevState: ProtocolFormActionState,
  form: FormData,
): Promise<ProtocolFormActionState> {
  const protocolId = Number(field(form, "protocol_id"));
  const requirement = field(form, "requirement") ?? "";
  if (!Number.isInteger(protocolId) || requirement === "") return { ok: false, error: "failed" };
  let failed: ProtocolError | undefined;
  try {
    const { response } = await api.POST("/protocols/{protocol_id}/test-steps/{requirement}", {
      params: { path: { protocol_id: protocolId, requirement } },
      headers: await bearerHeaders(),
      body: { test_step: null },
    });
    failed = error(response.status);
  } catch {
    failed = "failed";
  }
  return inlineResult(failed);
}

/** Inline `useActionState` variant of `editDraftedTestStep` for drawer forms. */
export async function editDraftedTestStepInline(
  _prevState: ProtocolFormActionState,
  form: FormData,
): Promise<ProtocolFormActionState> {
  const protocolId = Number(field(form, "protocol_id"));
  const proposalId = Number(field(form, "proposal_id"));
  const step = stepFrom(form);
  if (!Number.isInteger(protocolId) || !Number.isInteger(proposalId)) return { ok: false, error: "failed" };
  if (step === null) return { ok: false, error: "invalid" };
  let failed: ProtocolError | undefined;
  try {
    const { response } = await api.POST("/protocols/{protocol_id}/drafts/{proposal_id}/edit", {
      params: { path: { protocol_id: protocolId, proposal_id: proposalId } },
      headers: await bearerHeaders(),
      body: { reason: field(form, "reason") ?? "", test_step: step },
    });
    failed = error(response.status);
  } catch {
    failed = "failed";
  }
  return inlineResult(failed);
}

/** Inline `useActionState` variant of `answerMissedNumber` for tab forms. */
export async function answerMissedNumberInline(
  _prevState: ProtocolFormActionState,
  form: FormData,
): Promise<ProtocolFormActionState> {
  const protocolId = Number(field(form, "protocol_id"));
  const rev = Number(field(form, "rev"));
  const doc = field(form, "doc") ?? "";
  const number = field(form, "number") ?? "";
  const kind = field(form, "kind");
  if (!Number.isInteger(protocolId) || !Number.isInteger(rev) || doc === "" || number === "") {
    return { ok: false, error: "failed" };
  }
  if (kind !== "not_a_requirement" && kind !== "not_tested_here") return { ok: false, error: "invalid" };
  let failed: ProtocolError | undefined;
  try {
    const { response } = await api.POST("/protocols/{protocol_id}/missed-numbers", {
      params: { path: { protocol_id: protocolId } },
      headers: await bearerHeaders(),
      body: { doc, rev, number, kind, justification: field(form, "justification") ?? "" },
    });
    failed = error(response.status);
  } catch {
    failed = "failed";
  }
  return inlineResult(failed);
}
