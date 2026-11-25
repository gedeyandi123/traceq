import { cache } from "react";

import {
  api,
  type DecisionCounts,
  type ExecutionView,
  type ProtocolView,
  type RunRoundsView,
  type RunSummary,
} from "@/api/client";
import { bearerHeaders, currentSession } from "@/auth/session";

/** Deduplicated per-request fetch for a single RunSummary (ADR 0014). */
export const fetchRun = cache(async (runId: string): Promise<RunSummary | null> => {
  try {
    const { data } = await api.GET("/runs/{run_id}", {
      params: { path: { run_id: runId } },
    });
    return data ?? null;
  } catch {
    return null;
  }
});

/** Deduplicated per-request fetch for DecisionCounts (ADR 0014). */
export const fetchDecisionCounts = cache(async (runId: string): Promise<DecisionCounts | null> => {
  const session = await currentSession();
  if (session === null) return null;
  try {
    const { data } = await api.GET("/runs/{run_id}/decision-counts", {
      params: { path: { run_id: runId } },
      headers: await bearerHeaders(),
    });
    return data ?? null;
  } catch {
    return null;
  }
});

export type ProtocolFetchResult =
  | { kind: "ok"; data: ProtocolView }
  | { kind: "not_found" }
  | { kind: "unavailable" };

/** Deduplicated per-request fetch for the Assembled Protocol (ADR 0014). */
export const fetchProtocol = cache(async (runId: string): Promise<ProtocolFetchResult> => {
  const session = await currentSession();
  if (session === null) return { kind: "unavailable" };
  try {
    const res = await api.GET("/runs/{run_id}/protocol", {
      params: { path: { run_id: runId } },
      headers: await bearerHeaders(),
    });
    if (res.data) return { kind: "ok", data: res.data };
    if (res.response.status === 404) return { kind: "not_found" };
    return { kind: "unavailable" };
  } catch {
    return { kind: "unavailable" };
  }
});

export type ExecutionFetchResult =
  | { kind: "ok"; data: ExecutionView }
  | { kind: "not_found" }
  | { kind: "unavailable" };

/** Deduplicated per-request fetch for Protocol Execution (ADR 0013, ADR 0014). */
export const fetchExecution = cache(async (runId: string): Promise<ExecutionFetchResult> => {
  const session = await currentSession();
  if (session === null) return { kind: "unavailable" };
  try {
    const res = await api.GET("/runs/{run_id}/execution", {
      params: { path: { run_id: runId } },
      headers: await bearerHeaders(),
    });
    if (res.data) return { kind: "ok", data: res.data };
    if (res.response.status === 404) return { kind: "not_found" };
    return { kind: "unavailable" };
  } catch {
    return { kind: "unavailable" };
  }
});

export type RoundsFetchResult =
  | { kind: "ok"; data: RunRoundsView }
  | { kind: "not_found" }
  | { kind: "unavailable" };

/** Deduplicated per-request fetch for Review Rounds & Document Versions (Step 6). */
export const fetchRounds = cache(async (runId: string): Promise<RoundsFetchResult> => {
  const session = await currentSession();
  if (session === null) return { kind: "unavailable" };
  try {
    const res = await api.GET("/runs/{run_id}/rounds", {
      params: { path: { run_id: runId } },
      headers: await bearerHeaders(),
    });
    if (res.data) return { kind: "ok", data: res.data };
    if (res.response.status === 404) return { kind: "not_found" };
    return { kind: "unavailable" };
  } catch {
    return { kind: "unavailable" };
  }
});
