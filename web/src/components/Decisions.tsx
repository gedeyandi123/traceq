import type { CoverageClass, DecisionCounts, Proposal } from "@/api/client";
import type { DecideActionState } from "@/decisions/actions";

/** Why a run shows read-only: not signed in, signed in without the deciding role, the run is
 * not imported, or the API refused the token or has no database. */
export type ReadOnlyReason = "signedOut" | "noRole" | "notImported" | "unavailable";

/** Why the API refused a decision, as the screen reports it. */
export type DecisionError = "refused" | "conflict" | "forbidden" | "unauthorized" | "failed";

export type DecisionAccess =
  | {
      mode: "decide";
      action: (formData: FormData) => void | Promise<void>;
      inlineAction?: (prevState: DecideActionState, formData: FormData) => Promise<DecideActionState>;
    }
  | { mode: "readOnly"; why: ReadOnlyReason };

/** What a screen knows about the decisions of its run. ``proposals`` and ``counts`` are absent
 * when the API could not give them (not signed in, run not imported). */
export type DecisionView = {
  proposals?: readonly Proposal[];
  counts?: DecisionCounts;
  access: DecisionAccess;
  error?: DecisionError;
};

/** The screen a decision form returns to. */
export type DecisionScreen = "matrix" | "findings" | "draft" | "protocol";

export type { CoverageClass };
