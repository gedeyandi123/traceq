// The API's decision vocabulary as the web shows it. Display only: the API is the authority
// and checks the role and the class again on every call. `tests/test_web_vocabulary.py` keeps
// both equal to the Python ones.
import type { CoverageClass } from "@/api/client";

/** The role that may import a run and record Proposal Decisions (spec #105), as the API
 * names it. */
export const DECIDING_ROLE = "qualification-decider";

/** Every Coverage class, in display order. A record over the generated type, so a class added
 * to or removed from the API's schema fails the typecheck until it is listed here. */
const COVERAGE_CLASS_ORDER: Record<CoverageClass, number> = {
  covered_by_vendor: 0,
  partial: 1,
  site_only: 2,
  gap: 3,
  conflict: 4,
};

export const COVERAGE_CLASSES: readonly CoverageClass[] = (
  Object.keys(COVERAGE_CLASS_ORDER) as CoverageClass[]
).sort((a, b) => COVERAGE_CLASS_ORDER[a] - COVERAGE_CLASS_ORDER[b]);
