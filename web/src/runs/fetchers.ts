import { cache } from "react";

import {
  api,
  type DecisionCounts,
  type DraftUploads,
  type EquipmentSummary,
  type ExecutionView,
  type ProtocolView,
  type QualificationReportView,
  type RunRoundsView,
  type RunSummary,
} from "@/api/client";
import { bearerHeaders, currentSession } from "@/auth/session";

/** Deduplicated per-request fetch for a single RunSummary (ADR 0014). */
export const fetchRun = cache(async (runId: string): Promise<RunSummary | null> => {
  try {
    const { data } = await api.GET("/runs/{run_id}", {
      params: { path: { run_id: runId } },
      headers: await bearerHeaders(),
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

export type QualificationReportFetchResult =
  | { kind: "ok"; data: QualificationReportView }
  | { kind: "not_found" }
  | { kind: "unavailable" };

/** Deduplicated per-request fetch for Qualification Report preview & exports (Step 7). */
export const fetchQualificationReport = cache(
  async (runId: string): Promise<QualificationReportFetchResult> => {
    const session = await currentSession();
    if (session === null) return { kind: "unavailable" };
    try {
      const res = await api.GET("/runs/{run_id}/qualification-report", {
        params: { path: { run_id: runId } },
        headers: await bearerHeaders(),
      });
      if (res.data) return { kind: "ok", data: res.data };
      if (res.response.status === 404) return { kind: "not_found" };
      return { kind: "unavailable" };
    } catch {
      return { kind: "unavailable" };
    }
  },
);

export type DraftUploadsFetchResult =
  | { kind: "ok"; data: DraftUploads }
  | { kind: "unauthorized" }
  | { kind: "forbidden" }
  | { kind: "not_enabled" }
  | { kind: "unavailable" };

/** The uploaded drafts of an Equipment and the limits an upload must keep. */
export const fetchDraftUploads = cache(
  async (equipment: string): Promise<DraftUploadsFetchResult> => {
    const session = await currentSession();
    if (session === null) return { kind: "unauthorized" };
    try {
      const res = await api.GET("/equipment/{equipment}/drafts", {
        params: { path: { equipment } },
        headers: await bearerHeaders(),
      });
      if (res.data) return { kind: "ok", data: res.data };
      if (res.response.status === 401) return { kind: "unauthorized" };
      if (res.response.status === 403) return { kind: "forbidden" };
      if (res.response.status === 404) return { kind: "not_enabled" };
      return { kind: "unavailable" };
    } catch {
      return { kind: "unavailable" };
    }
  },
);

export type EquipmentListFetchResult =
  | { kind: "ok"; data: EquipmentSummary[] }
  | { kind: "unauthorized" }
  | { kind: "unavailable" };

/** Deduplicated per-request fetch for the Equipment Registry (`GET /equipment`, Step 7). */
export const fetchEquipmentList = cache(async (): Promise<EquipmentListFetchResult> => {
  const session = await currentSession();
  if (session === null) return { kind: "unauthorized" };
  try {
    const res = await api.GET("/equipment", {
      headers: await bearerHeaders(),
    });
    if (res.data) return { kind: "ok", data: res.data };
    if (res.response.status === 401) return { kind: "unauthorized" };
    return { kind: "unavailable" };
  } catch {
    return { kind: "unavailable" };
  }
});
