"use server";

import { revalidatePath } from "next/cache";

import { api, type InstrumentInput } from "@/api/client";
import { bearerHeaders } from "@/auth/session";

export type ExecutionError =
  | "conflict"
  | "forbidden"
  | "unauthorized"
  | "notFound"
  | "unprocessable"
  | "failed";

export type ExecutionActionState = {
  ok: boolean;
  error?: ExecutionError;
  detail?: string;
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
  if (status === 422) return "unprocessable";
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

type RecordAttemptBody = {
  outcome_kind: "value" | "not_performable";
  not_performable_reason?: string | null;
  value?:
    | { type: "number"; value: number }
    | { type: "one_of"; value: string; not_one_of: boolean }
    | { type: "present"; value: boolean }
    | null;
  observation?: string | null;
  instruments: InstrumentInput[];
  no_calibrated_instrument_reason?: string | null;
  evidence: string[];
};

/** Records the first attempt on a Test Step row of an Execution (ADR 0013, spec #270, #272). */
export async function recordAttempt(
  _prevState: ExecutionActionState,
  form: FormData,
): Promise<ExecutionActionState> {
  const executionId = Number(field(form, "execution_id"));
  const requirement = field(form, "requirement");
  const outcomeKind = field(form, "outcome_kind");
  if (!Number.isInteger(executionId) || !requirement || !outcomeKind) {
    return { ok: false, error: "unprocessable" };
  }

  let body: RecordAttemptBody;
  if (outcomeKind === "not_performable") {
    body = {
      outcome_kind: "not_performable",
      not_performable_reason: field(form, "not_performable_reason") ?? "",
      instruments: [],
      evidence: [],
    };
  } else {
    const acType = field(form, "acceptance_type");
    if (acType === "range" || acType === "number") {
      const raw = field(form, "numeric_value");
      const num = raw !== undefined ? Number(raw) : Number.NaN;
      if (!Number.isFinite(num)) {
        return { ok: false, error: "unprocessable" };
      }
      body = {
        outcome_kind: "value",
        value: { type: "number", value: num },
        instruments: [],
        evidence: [],
      };
    } else if (acType === "one_of") {
      const choice = field(form, "one_of_choice");
      if (choice === "__not_one_of__") {
        body = {
          outcome_kind: "value",
          value: {
            type: "one_of",
            value: field(form, "one_of_observed") ?? "",
            not_one_of: true,
          },
          instruments: [],
          evidence: [],
        };
      } else {
        body = {
          outcome_kind: "value",
          value: { type: "one_of", value: choice ?? "", not_one_of: false },
          instruments: [],
          evidence: [],
        };
      }
    } else if (acType === "present") {
      const presentChoice = field(form, "present_value");
      if (presentChoice !== "true" && presentChoice !== "false") {
        return { ok: false, error: "unprocessable" };
      }
      body = {
        outcome_kind: "value",
        value: { type: "present", value: presentChoice === "true" },
        instruments: [],
        evidence: [],
      };
    } else {
      return { ok: false, error: "unprocessable" };
    }
  }

  const observation = field(form, "observation");
  if (observation !== undefined) {
    body.observation = observation;
  }

  const instrumentMode = field(form, "instrument_mode");
  if (instrumentMode === "calibrated") {
    const ids = form.getAll("instrument_id").map((v) => (typeof v === "string" ? v.trim() : ""));
    const dates = form
      .getAll("instrument_due")
      .map((v) => (typeof v === "string" ? v.trim() : ""));
    body.instruments = ids
      .map((identifier, i) => ({ identifier, calibration_due_date: dates[i] ?? "" }))
      .filter((inst) => inst.identifier !== "" || inst.calibration_due_date !== "");
  } else if (instrumentMode === "none") {
    body.no_calibrated_instrument_reason = field(form, "no_calibrated_instrument_reason") ?? "";
  }

  const evidence = form
    .getAll("evidence_ref")
    .map((v) => (typeof v === "string" ? v.trim() : ""))
    .filter((v) => v !== "");
  if (evidence.length > 0) {
    body.evidence = evidence;
  }

  let failed: ExecutionError | undefined;
  let detail: string | undefined;
  try {
    const { response, error } = await api.POST(
      "/executions/{execution_id}/rows/{requirement}/attempts",
      {
        params: { path: { execution_id: executionId, requirement } },
        body,
        headers: await bearerHeaders(),
      },
    );
    failed = errorFromStatus(response.status);
    if (failed && error && typeof error === "object" && "detail" in error) {
      const d = (error as { detail?: unknown }).detail;
      if (typeof d === "string") detail = d;
    }
  } catch {
    failed = "failed";
  }
  revalidatePath("/runs/[runId]", "layout");
  return failed
    ? { ok: false, error: failed, detail }
    : { ok: true, submittedAt: Date.now() };
}

async function postExecutionMutation(
  call: () => Promise<{ response: Response; error?: unknown }>,
): Promise<ExecutionActionState> {
  let failed: ExecutionError | undefined;
  let detail: string | undefined;
  try {
    const { response, error } = await call();
    failed = errorFromStatus(response.status);
    if (failed && error && typeof error === "object" && "detail" in error) {
      const d = (error as { detail?: unknown }).detail;
      if (typeof d === "string") detail = d;
    }
  } catch {
    failed = "failed";
  }
  revalidatePath("/runs/[runId]", "layout");
  return failed
    ? { ok: false, error: failed, detail }
    : { ok: true, submittedAt: Date.now() };
}

/** Opens a manual Deviation linked to a Test Step row or to the Execution (spec #273). */
export async function openManualDeviation(
  _prevState: ExecutionActionState,
  form: FormData,
): Promise<ExecutionActionState> {
  const executionId = Number(field(form, "execution_id"));
  const description = field(form, "description");
  const requirement = field(form, "requirement") ?? null;
  if (!Number.isInteger(executionId) || !description) {
    return { ok: false, error: "unprocessable" };
  }
  const headers = await bearerHeaders();
  return postExecutionMutation(() =>
    api.POST("/executions/{execution_id}/deviations", {
      params: { path: { execution_id: executionId } },
      body: { requirement, description },
      headers,
    }),
  );
}

/** Records an immutable Investigation version on an Open Deviation (spec #273). */
export async function addDeviationInvestigation(
  _prevState: ExecutionActionState,
  form: FormData,
): Promise<ExecutionActionState> {
  const executionId = Number(field(form, "execution_id"));
  const deviationId = Number(field(form, "deviation_id"));
  const investigation = field(form, "investigation");
  const deviationClass = field(form, "deviation_class");
  if (
    !Number.isInteger(executionId) ||
    !Number.isInteger(deviationId) ||
    !investigation ||
    (deviationClass !== "minor" && deviationClass !== "major" && deviationClass !== "critical")
  ) {
    return { ok: false, error: "unprocessable" };
  }
  const capa = field(form, "capa") ?? null;
  const reasonForChange = field(form, "reason_for_change") ?? null;
  const headers = await bearerHeaders();
  return postExecutionMutation(() =>
    api.POST("/executions/{execution_id}/deviations/{deviation_id}/investigations", {
      params: { path: { execution_id: executionId, deviation_id: deviationId } },
      body: {
        investigation,
        deviation_class: deviationClass,
        capa,
        reason_for_change: reasonForChange,
      },
      headers,
    }),
  );
}

/** Submits an Open Deviation once an Investigation with a class is recorded (spec #273). */
export async function submitDeviation(
  _prevState: ExecutionActionState,
  form: FormData,
): Promise<ExecutionActionState> {
  const executionId = Number(field(form, "execution_id"));
  const deviationId = Number(field(form, "deviation_id"));
  if (!Number.isInteger(executionId) || !Number.isInteger(deviationId)) {
    return { ok: false, error: "unprocessable" };
  }
  const headers = await bearerHeaders();
  return postExecutionMutation(() =>
    api.POST("/executions/{execution_id}/deviations/{deviation_id}/submit", {
      params: { path: { execution_id: executionId, deviation_id: deviationId } },
      headers,
    }),
  );
}

/** Closes a Submitted Deviation (a recorded status, not an Electronic Signature) (spec #273). */
export async function closeDeviation(
  _prevState: ExecutionActionState,
  form: FormData,
): Promise<ExecutionActionState> {
  const executionId = Number(field(form, "execution_id"));
  const deviationId = Number(field(form, "deviation_id"));
  if (!Number.isInteger(executionId) || !Number.isInteger(deviationId)) {
    return { ok: false, error: "unprocessable" };
  }
  const headers = await bearerHeaders();
  return postExecutionMutation(() =>
    api.POST("/executions/{execution_id}/deviations/{deviation_id}/close", {
      params: { path: { execution_id: executionId, deviation_id: deviationId } },
      headers,
    }),
  );
}

/** Returns a Submitted Deviation to Open with a required reason (spec #273). */
export async function returnDeviation(
  _prevState: ExecutionActionState,
  form: FormData,
): Promise<ExecutionActionState> {
  const executionId = Number(field(form, "execution_id"));
  const deviationId = Number(field(form, "deviation_id"));
  const reason = field(form, "reason");
  if (!Number.isInteger(executionId) || !Number.isInteger(deviationId) || !reason) {
    return { ok: false, error: "unprocessable" };
  }
  const headers = await bearerHeaders();
  return postExecutionMutation(() =>
    api.POST("/executions/{execution_id}/deviations/{deviation_id}/return", {
      params: { path: { execution_id: executionId, deviation_id: deviationId } },
      body: { reason },
      headers,
    }),
  );
}

/** Records a Witness confirmation bound to the latest version's hash (ADR 0013, spec #274). */
export async function confirmWitness(
  _prevState: ExecutionActionState,
  form: FormData,
): Promise<ExecutionActionState> {
  const executionId = Number(field(form, "execution_id"));
  const requirement = field(form, "requirement");
  const attemptNumber = Number(field(form, "attempt_number"));
  const versionNumber = Number(field(form, "version_number"));
  const versionHash = field(form, "version_hash");
  if (
    !Number.isInteger(executionId) ||
    !requirement ||
    !Number.isInteger(attemptNumber) ||
    !Number.isInteger(versionNumber) ||
    !versionHash
  ) {
    return { ok: false, error: "unprocessable" };
  }
  const headers = await bearerHeaders();
  return postExecutionMutation(() =>
    api.POST("/executions/{execution_id}/rows/{requirement}/attempts/{attempt_number}/witness", {
      params: {
        path: {
          execution_id: executionId,
          requirement,
          attempt_number: attemptNumber,
        },
      },
      body: { version_number: versionNumber, version_hash: versionHash },
      headers,
    }),
  );
}
