// Decisions and counts for the render tests, over the fixture run (spec #105). Fictional
// demo personas, as the demo issuer seeds them.
import type { Decision, DecisionCounts } from "@/api/client";

export const RUN_ID = "20261113T090000Z-f1a2b3";

const ISSUER = "http://127.0.0.1:9000";
export const AYU = { subject: "demo-0001", issuer: ISSUER, name: "Ayu Kartika Sari" };
export const BIMA = { subject: "demo-0002", issuer: ISSUER, name: "Bima Arya Nugraha" };

export function decision(over: Partial<Decision>): Decision {
  return {
    id: 1,
    decision: "accepted",
    coverage: null,
    reason: null,
    run_id: RUN_ID,
    content_hash: "h",
    at: "2026-11-16T09:30:00Z",
    ...AYU,
    ...over,
  };
}

const none = {
  total: 0,
  undecided: 0,
  accepted: 0,
  edited: 0,
  rejected: 0,
  changed: 0,
  decided_not_proposed: 0,
};

export const counts: DecisionCounts = {
  run_id: RUN_ID,
  coverage: { ...none, total: 3, undecided: 1, edited: 1, changed: 1, decided_not_proposed: 2 },
  check: { ...none, total: 2, accepted: 1, rejected: 1 },
  ai: { ...none, total: 1, undecided: 1 },
  draft: none,
  test_step: { ...none, total: 2, undecided: 1, accepted: 1 },
};
