// Server side only: reads the token cookie.
import { api } from "@/api/client";
import { bearerHeaders, currentSession } from "@/auth/session";
import type { DecisionError, DecisionView } from "@/components/Decisions";
import { fetchDecisionCounts } from "@/runs/fetchers";

import { decide, decideInline } from "./actions";

const ERRORS: readonly DecisionError[] = ["refused", "conflict", "forbidden", "unauthorized", "failed"];

/** The error a decision form came back with, from the `error` query parameter. */
export function decisionError(raw: string | string[] | undefined): DecisionError | undefined {
  return ERRORS.find((e) => e === raw);
}

/** What a screen shows of the decisions of a run: its Proposals with their state and the
 * counts when the API gives them with the viewer's token, and whether the viewer may decide.
 * Read-only, with the reason, when the viewer is not signed in or lacks the deciding role,
 * the run is not imported, or the API refuses the token (no database, expired token). */
export async function loadDecisions(runId: string): Promise<DecisionView> {
  const session = await currentSession();
  if (session === null) return { access: { mode: "readOnly", why: "signedOut" } };
  const init = { params: { path: { run_id: runId } }, headers: await bearerHeaders() };
  try {
    const [proposals, counts] = await Promise.all([
      api.GET("/runs/{run_id}/proposals", init),
      fetchDecisionCounts(runId),
    ]);
    if (proposals.response.status === 404) {
      return { access: { mode: "readOnly", why: "notImported" } };
    }
    if (!proposals.data || !counts) {
      return { access: { mode: "readOnly", why: "unavailable" } };
    }
    return {
      proposals: proposals.data,
      counts,
      access: session.mayDecide
        ? { mode: "decide", action: decide, inlineAction: decideInline }
        : { mode: "readOnly", why: "noRole" },
    };
  } catch {
    return { access: { mode: "readOnly", why: "unavailable" } };
  }
}
