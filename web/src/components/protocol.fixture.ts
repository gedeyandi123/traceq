// A Protocol assembled in TraceQ as the API serves it, for the render tests of the Protocol
// page (spec #247, ticket #249). Hand-written over the fixture run: four rows, one of each
// kind (Coverage changed, Vendor Reference, Test Step with its accepted draft, Test Step
// without one).
import type { Cite, ProtocolEvent, ProtocolRowView, ProtocolView, RowDraft } from "@/api/client";

import { AYU, BIMA, decision, RUN_ID } from "./decisions.fixture";
import { proposal } from "./protocolDraft.fixture";

const URS = { doc: "URS-TP201", rev: 0 };

function cite(page: number, quote: string): Cite {
  return { ...URS, page, quote };
}

function draft(requirement: string, id: number, over: Partial<RowDraft["draft"]> = {}, decided = false): RowDraft {
  return {
    draft: {
      id: `TS-${requirement}`,
      requirement,
      requirement_text: `The text of ${requirement}.`,
      coverage: "partial",
      saved_by_reuse: false,
      description: `Verifikasi ${requirement} di lokasi.`,
      method: "Atur turret ke 20 dan 70 rpm, baca takometer.",
      instrument: "TACH-07 Takometer digital",
      acceptance: { type: "range", min: 20, max: 70, unit: "rpm" },
      acceptance_citation: cite(1, "dapat diatur 20-70 rpm"),
      acceptance_flag: null,
      layer: "ai",
      source: { ...URS },
      model: "claude-haiku-5-5",
      prompt: "bbbb",
      created: "2026-11-13T09:00:00Z",
      reviewer_action: "pending",
      ...over,
    },
    proposal: proposal({
      id,
      kind: "test_step",
      requirement,
      position: null,
      state: decided ? "decided" : "undecided",
      decisions: decided ? [decision({ id: id + 100 })] : [],
    }),
  };
}

function row(over: Partial<ProtocolRowView> & { requirement: string }): ProtocolRowView {
  return {
    text: `Teks ${over.requirement}.`,
    source: cite(1, `Teks ${over.requirement}.`),
    coverage: proposal({ id: 1, kind: "coverage", requirement: over.requirement, position: null, state: "decided" }),
    decided_class: "partial",
    kind: "test_step",
    evidence: [],
    test_step: null,
    drafts: [],
    blockers: [],
    ...over,
  };
}

const accepted = draft("URS-TP201-002", 70, {}, true);

export const rows: ProtocolRowView[] = [
  row({
    requirement: "URS-TP201-001",
    coverage: proposal({ id: 2, kind: "coverage", requirement: "URS-TP201-001", position: null, state: "changed" }),
    decided_class: null,
    kind: "undecided",
    blockers: ["coverage_undecided"],
  }),
  row({
    requirement: "URS-TP201-002",
    test_step: {
      origin: "accepted_draft",
      proposal_id: 70,
      description: accepted.draft.description,
      method: accepted.draft.method,
      instrument: accepted.draft.instrument,
      acceptance: accepted.draft.acceptance,
      acceptance_flag: null,
    },
    drafts: [accepted],
  }),
  row({
    requirement: "URS-TP201-010",
    decided_class: "covered_by_vendor",
    kind: "vendor_reference",
    evidence: [
      {
        doc: "FAT-TP201-M",
        rev: 0,
        stage: "FAT",
        step: "FAT-M-02",
        test: "Kecepatan turret",
        acceptance: "20-70 rpm",
        observed: "20 dan 70 rpm",
        observed_value: null,
        result: "pass",
        failure: null,
        citation: { doc: "FAT-TP201-M", rev: 0, page: 1, quote: "FAT-M-02" },
      },
    ],
    drafts: [draft("URS-TP201-010", 71)],
  }),
  row({
    requirement: "URS-TP201-030",
    decided_class: "gap",
    blockers: ["no_test_step"],
    drafts: [
      draft("URS-TP201-030", 72, {
        acceptance: null,
        acceptance_citation: null,
        acceptance_flag: "tidak ada kriteria penerimaan di sumber",
        instrument: null,
      }),
    ],
  }),
];

export function event(over: Partial<ProtocolEvent>): ProtocolEvent {
  return { id: 1, event: "started", status: "draft", reason: null, at: "2026-11-19T09:00:00Z", ...AYU, ...over };
}

export function protocolView(over: Partial<ProtocolView> = {}): ProtocolView {
  return {
    id: 7,
    equipment: "TP-201",
    run_id: RUN_ID,
    status: "draft",
    events: [event({})],
    rows,
    ...over,
  };
}

export const withdrawn = protocolView({
  status: "withdrawn",
  rows: null,
  events: [event({}), event({ id: 2, event: "withdrawn", status: "withdrawn", reason: "run yang lebih baru", ...BIMA })],
});
