import createClient from "openapi-fetch";

import type { components as evalComponents, paths as evalPaths } from "./eval-schema";
import type { components, paths } from "./schema";
import { API_URL, EVAL_URL } from "./url";

export type Matrix = components["schemas"]["Matrix"];
export type MatrixRow = components["schemas"]["MatrixRow"];
export type Cite = components["schemas"]["Cite"];
export type RunSummary = components["schemas"]["RunSummary"];
export type Findings = components["schemas"]["Findings"];
export type Value = NonNullable<MatrixRow["value"]>;
export type ObservedValue = NonNullable<components["schemas"]["EvidenceStep"]["observed_value"]>;

/** The typed client over the generated OpenAPI schema (ADR 0003). */
export const api = createClient<paths>({ baseUrl: API_URL, cache: "no-store" });

export type EvalSummary = evalComponents["schemas"]["EvalSummary"];
export type Rate = evalComponents["schemas"]["Rate"];

/** The harness's eval API: aggregates (k/n, split, cost) of scored runs, never items. */
export const evalApi = createClient<evalPaths>({ baseUrl: EVAL_URL, cache: "no-store" });

/** Where a citation opens: the document as the run read it, at the cited page. */
export function documentHref(runId: string, c: Cite): string {
  const doc = encodeURIComponent(c.doc);
  return `/api/runs/${encodeURIComponent(runId)}/documents/${doc}/${c.rev}#page=${c.page}`;
}
