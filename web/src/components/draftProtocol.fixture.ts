// A Protocol started from the Protocol Draft, as the API serves it (spec #375, ticket S4b):
// pinned to revision 0 while the Equipment has revision 1, one draft step that stands for no
// requirement, a row with a candidate Test Step and two findings (one of a type no practitioner
// has reviewed), and the checks the draft adds. Hand-written over the fixture run.
import type {
  ChecklistItem,
  ProtocolRowView,
  ProtocolView,
  RowCandidate,
  RowFindingView,
  SubmissionView,
} from "@/api/client";

import { AYU, BIMA, decision, RUN_ID } from "./decisions.fixture";
import { checklist as oldChecklist, event, protocolView, rows, submissionView } from "./protocol.fixture";
import { deviates, outsideCapability, proposal } from "./protocolDraft.fixture";

export const DRAFT_DOC = { doc_id: "OQ-TP201", rev: 0, sha256: "ab".repeat(32) };

function candidate(over: Partial<RowCandidate> = {}): RowCandidate {
  return {
    step: {
      document: DRAFT_DOC,
      id: "OQ-02",
      requirements: ["URS-TP201-002"],
      mapped_to: ["URS-TP201-002"],
      description: "Atur turret ke 20 dan 70 rpm",
      method: "Baca takometer",
      instrument: "TACH-07",
      not_read: null,
    },
    proposal: proposal({ id: 201, kind: "draft_step", requirement: "URS-TP201-002" }),
    criterion: {
      document: DRAFT_DOC,
      id: "OQ-02/ac",
      mapped_to: ["URS-TP201-002"],
      printed: "20-70 rpm",
      value: { type: "range", min: 20, max: 70, unit: "rpm", min_exclusive: false, max_exclusive: false },
      citation: { doc: "OQ-TP201", rev: 0, page: 1, quote: "20-70 rpm" },
    },
    criterion_proposal: proposal({ id: 202, kind: "draft_criterion", requirement: "URS-TP201-002" }),
    mapping: null,
    ready: false,
    accepted: false,
    ...over,
  };
}

export function finding(id: number, over: Partial<RowFindingView> = {}, label?: boolean): RowFindingView {
  return {
    finding: label ? outsideCapability : deviates,
    proposal: proposal({ id, kind: "draft", requirement: "URS-TP201-002" }),
    reasons: [],
    ...over,
  };
}

export const fromDraftRows: ProtocolRowView[] = rows.map((r) =>
  r.requirement === "URS-TP201-002"
    ? {
        ...r,
        drafts: [],
        step_source: "draft" as const,
        candidates: [candidate()],
        findings: [finding(301), finding(302, {}, true)],
        blockers: ["finding_undecided" as const, "stage_missing" as const],
        test_step: null,
      }
    : r,
);

export const draftChecklist: ChecklistItem[] = [
  ...oldChecklist.map((c) => ({ ...c, count: 0, requirements: [], numbers: [], steps: [] })),
  { check: "finding_undecided", count: 1, requirements: ["URS-TP201-002"], numbers: [], steps: [] },
  { check: "finding_reason_missing", count: 0, requirements: [], numbers: [], steps: [] },
  { check: "stage_missing", count: 1, requirements: ["URS-TP201-002"], numbers: [], steps: [] },
  { check: "draft_step_unresolved", count: 1, requirements: [], numbers: [], steps: ["OQ-40"] },
];

export const draftSteps: NonNullable<ProtocolView["draft_steps"]> = [
  {
    step: { ...candidate().step, id: "OQ-02" },
    proposal: candidate().proposal,
    mappings: [],
    requirement: "URS-TP201-002",
    resolved: true,
  },
  {
    step: {
      document: DRAFT_DOC,
      id: "OQ-40",
      requirements: [],
      mapped_to: [],
      description: "Periksa fungsi interlock pintu",
      method: null,
      instrument: null,
      not_read: null,
    },
    proposal: proposal({ id: 240, kind: "draft_step", requirement: null }),
    mappings: [],
    requirement: null,
    resolved: false,
  },
];

/** Started from the draft, pinned to revision 0 while the Equipment has revision 1. */
export const fromDraft = protocolView({
  rows: fromDraftRows,
  checklist: draftChecklist,
  source: { doc: "OQ-TP201", rev: 0, sha256: DRAFT_DOC.sha256 },
  latest_draft_rev: 1,
  draft_steps: draftSteps,
});

/** The same, with nothing left to decide: it may be submitted. */
export const fromDraftReady = protocolView({
  rows: fromDraftRows,
  checklist: draftChecklist.map((c) => ({ ...c, count: 0, requirements: [], steps: [], numbers: [] })),
  draft_hash: "c".repeat(64),
  source: { doc: "OQ-TP201", rev: 0, sha256: DRAFT_DOC.sha256 },
  latest_draft_rev: 1,
  draft_steps: draftSteps.map((e) => ({ ...e, resolved: true })),
});

const accepted = (id: number, author = BIMA) =>
  decision({ id, decision: "accepted", reason: null, ...author, at: "2026-11-19T09:30:00Z" });

/** The frozen copy of a Protocol from the draft: version 2. */
export const submissionV2: SubmissionView = {
  ...submissionView,
  hash: "d".repeat(64),
  frozen_copy: {
    protocol_id: 7,
    equipment: "TP-201",
    run_id: RUN_ID,
    preparer: AYU,
    rows: [],
    urs: [],
    schema_version: 2,
    source: { doc: "OQ-TP201", rev: 0, sha256: DRAFT_DOC.sha256, run_id: RUN_ID },
    row_details: [
      { requirement: "URS-TP201-002", source: "draft", criterion_decision: null, candidates: [], findings: [301] },
    ],
    draft_steps: [
      {
        step: "OQ-40",
        proposal_id: 240,
        traced_to: [],
        not_read: null,
        requirement: "URS-TP201-030",
        mappings: [
          {
            version: 1,
            requirement: "URS-TP201-030",
            author: { subject: AYU.subject, issuer: AYU.issuer, name: AYU.name },
            at: "2026-11-19T09:20:00Z",
          },
        ],
        decisions: [],
        criterion_decisions: [],
      },
    ],
    findings: [
      {
        proposal_id: 301,
        type: "ac_deviates_from_urs",
        requirement: "URS-TP201-002",
        test_step: "OQ-02",
        row: "URS-TP201-002",
        detail: "AC accepts up to 70 rpm; the URS rejects above 60 rpm",
        label: null,
        decisions: [
          {
            id: 9,
            decision: "accepted",
            coverage: null,
            reason: null,
            author: { subject: BIMA.subject, issuer: BIMA.issuer, name: BIMA.name },
            at: "2026-11-19T09:30:00Z",
          },
        ],
        reasons: [
          {
            version: 1,
            reason: "Batas 70 rpm disetujui pemasok.",
            author: { subject: AYU.subject, issuer: AYU.issuer, name: AYU.name },
            at: "2026-11-19T09:40:00Z",
          },
        ],
      },
      {
        proposal_id: 302,
        type: "ac_outside_documented_capability",
        requirement: "URS-TP201-002",
        test_step: "OQ-02",
        row: null,
        detail: "OQ-02 requires 105 kN, above the maximum 100 kN",
        label: "not reviewed by a practitioner",
        decisions: [],
        reasons: [],
      },
    ],
  },
};

export const submittedFromDraft = protocolView({
  status: "submitted",
  rows: null,
  urs: null,
  checklist: null,
  submission: submissionV2,
  submissions: [submissionV2],
  source: { doc: "OQ-TP201", rev: 0, sha256: DRAFT_DOC.sha256 },
  latest_draft_rev: 0,
  events: [event({}), event({ id: 12, event: "submitted", status: "submitted", latest_draft_rev: 0 })],
});

export { accepted };
