import type { Proposal } from "@/api/client";
import type { DecisionError } from "@/components/Decisions";
import type { CoverageKey } from "@/components/ui/ui";
import { COVERAGE_CLASSES } from "@/decisions/vocabulary";

const VALID_COVERAGE = new Set<CoverageKey>([...COVERAGE_CLASSES, "none"]);
const VALID_STATUS = new Set<Proposal["state"]>(["undecided", "decided", "changed"]);
const ANCHOR_RE = /^[A-Za-z0-9._-]+$/;

/** Builds a safe redirect URL preserving whitelisted matrix filters, error state, and row anchor (#163). */
export function buildDecisionRedirect(
  back: string,
  opts: { error?: DecisionError; returnQuery?: string; anchor?: string },
): string {
  const params = new URLSearchParams();
  if (opts.returnQuery) {
    const raw = new URLSearchParams(opts.returnQuery);
    const cov = raw.get("coverage");
    if (cov && VALID_COVERAGE.has(cov as CoverageKey)) params.set("coverage", cov);
    const st = raw.get("status");
    if (st && VALID_STATUS.has(st as Proposal["state"])) params.set("status", st);
  }
  if (opts.error) params.set("error", opts.error);
  const qs = params.toString();
  const safeAnchor = opts.anchor && ANCHOR_RE.test(opts.anchor) ? `#${opts.anchor}` : "";
  return `${back}${qs ? `?${qs}` : ""}${safeAnchor}`;
}
