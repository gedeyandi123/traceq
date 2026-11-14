/** The read-only API (`traceq serve`), reached by the Next.js server. */
export const API_URL = process.env.TRACEQ_API_URL ?? "http://127.0.0.1:8000";

/** The harness's eval API (`python -m traceq_eval.screen serve`): aggregates of scored runs.
 * Separate from the system's API, which serves no score. */
export const EVAL_URL = process.env.TRACEQ_EVAL_URL ?? "http://127.0.0.1:8001";
