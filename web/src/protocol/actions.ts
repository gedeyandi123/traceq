"use server";

import { redirect } from "next/navigation";

import { api } from "@/api/client";
import { bearerHeaders } from "@/auth/session";
import type { ProtocolError } from "@/components/AssembledProtocolView";
import { stepFrom } from "@/protocol/form";

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
