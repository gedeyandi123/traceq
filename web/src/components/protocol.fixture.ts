// A Protocol assembled in TraceQ as the API serves it, for the render tests of the Protocol
// page (spec #247, tickets #249 to #252). Hand-written over the fixture run: five rows, one
// of each kind (Coverage changed, Vendor Reference, Test Step with its accepted draft, Test
// Step with a written Test Step in its second version, Test Step without one).
import type {
  ChecklistItem,
  Cite,
  ProtocolEvent,
  ProtocolRowView,
  ProtocolUrs,
  ProtocolView,
  RowDraft,
  SubmissionView,
} from "@/api/client";
import type { components } from "@/api/schema";

type WrittenVersionView = components["schemas"]["WrittenVersionView"];
type MissedDispositionView = components["schemas"]["MissedDispositionView"];

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
    written: [],
    prefill: null,
    blockers: [],
    witness_required: false,
    ...over,
  };
}

const accepted = draft("URS-TP201-002", 70, {}, true);

/** A Test Step a human wrote for URS-TP201-026, then changed: version 2 is in force. */
export const written: WrittenVersionView[] = [
  {
    id: 1,
    version: 1,
    removed: false,
    test_step: {
      description: "Verifikasi tombol darurat.",
      method: "Tekan tombol darurat saat turret berputar.",
      instrument: null,
      acceptance: { type: "present", value: null },
    },
    from_proposal_id: null,
    decision_id: null,
    at: "2026-11-19T09:10:00Z",
    ...AYU,
  },
  {
    id: 2,
    version: 2,
    removed: false,
    test_step: {
      description: "Verifikasi tombol darurat menghentikan turret.",
      method: "Tekan tombol darurat saat turret berputar, ukur waktu berhenti.",
      instrument: "Stopwatch",
      acceptance: { type: "range", min: null, max: 2, unit: "s" },
    },
    from_proposal_id: null,
    decision_id: null,
    at: "2026-11-19T09:20:00Z",
    ...BIMA,
  },
];

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
      version: null,
      description: accepted.draft.description,
      method: accepted.draft.method,
      instrument: accepted.draft.instrument,
      acceptance: accepted.draft.acceptance,
      acceptance_flag: null,
      witness_required: false,
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
    prefill: {
      origin: "draft",
      description: "Verifikasi URS-TP201-010 di lokasi.",
      method: "Atur turret ke 20 dan 70 rpm, baca takometer.",
      instrument: "TACH-07 Takometer digital",
      acceptance: { type: "range", min: 20, max: 70, unit: "rpm" },
    },
  }),
  row({
    requirement: "URS-TP201-026",
    decided_class: "site_only",
    test_step: {
      origin: "written",
      proposal_id: null,
      version: 2,
      description: "Verifikasi tombol darurat menghentikan turret.",
      method: "Tekan tombol darurat saat turret berputar, ukur waktu berhenti.",
      instrument: "Stopwatch",
      acceptance: { type: "range", min: null, max: 2, unit: "s" },
      acceptance_flag: null,
      witness_required: false,
    },
    written,
    prefill: {
      origin: "written",
      description: "Verifikasi tombol darurat menghentikan turret.",
      method: "Tekan tombol darurat saat turret berputar, ukur waktu berhenti.",
      instrument: "Stopwatch",
      acceptance: { type: "range", min: null, max: 2, unit: "s" },
    },
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
    prefill: {
      origin: "withdrawn",
      description: "Verifikasi URS-TP201-030 dari protokol yang ditarik.",
      method: "Ukur ketebalan tablet.",
      instrument: null,
      acceptance: { type: "number", value: 4.5, unit: "mm" },
    },
  }),
];

/** The run's URS completeness check as the Protocol serves it (ticket #251): URS-TP201 missed
 * two numbers, one answered twice (the second answer in force), one unanswered; an annex
 * checked `not_applicable` lists none. The TP-201 demo run misses none. */
const answers: MissedDispositionView[] = [
  { id: 1, version: 1, kind: "not_tested_here", justification: "Diuji di IQ.", at: "2026-11-19T09:30:00Z", ...AYU },
  {
    id: 2,
    version: 2,
    kind: "not_a_requirement",
    justification: "Nomor ini menandai judul bagian, bukan persyaratan.",
    at: "2026-11-19T09:40:00Z",
    ...BIMA,
  },
];

export const urs: ProtocolUrs[] = [
  {
    ...URS,
    numbers: "checked",
    missed: [
      { number: "URS-TP201-003", page: 1, blocking: false, disposition: answers[1] ?? null, dispositions: answers },
      { number: "URS-TP201-004", page: 2, blocking: true, disposition: null, dispositions: [] },
    ],
    unquoted: [{ page: 1, text: "Spesifikasi Kebutuhan Pengguna (SKP)\nNomor dokumen URS-TP201" }],
  },
  { doc: "URS-TP201-ANNEX", rev: 1, numbers: "not_applicable", missed: [], unquoted: [] },
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
    urs,
    checklist,
    draft_hash: null,
    submission: null,
    submissions: [],
    ...over,
  };
}

/** What blocks the Protocol above: one row's Coverage, one row without a Test Step, one
 * missed number without its disposition. */
export const checklist: ChecklistItem[] = [
  { check: "coverage_undecided", count: 1, requirements: ["URS-TP201-001"], numbers: [] },
  { check: "draft_undecided", count: 0, requirements: [], numbers: [] },
  { check: "no_test_step", count: 1, requirements: ["URS-TP201-030"], numbers: [] },
  { check: "acceptance_not_shaped", count: 0, requirements: [], numbers: [] },
  { check: "missed_undecided", count: 1, requirements: [], numbers: [{ ...URS, number: "URS-TP201-004" }] },
];

export const ready: ChecklistItem[] = checklist.map((c) => ({ ...c, count: 0, requirements: [], numbers: [] }));

/** A submission as the API serves it (ticket #252): two rows frozen with who decided them. */
export const submissionView: SubmissionView = {
  event_id: 12,
  hash: "a".repeat(64),
  outcome: null,
  at: "2026-11-19T10:00:00Z",
  frozen_copy: {
    protocol_id: 7,
    equipment: "TP-201",
    run_id: RUN_ID,
    preparer: AYU,
    rows: [
      {
        requirement: "URS-TP201-002",
        text: "Teks URS-TP201-002.",
        source: cite(1, "Teks URS-TP201-002."),
        coverage: {
          coverage_class: "partial",
          decision: { id: 1, decision: "accepted", coverage: null, reason: null, author: AYU, at: "2026-11-19T09:05:00Z" },
        },
        kind: "test_step",
        evidence: [],
        test_step: {
          origin: "accepted_draft",
          proposal_id: 70,
          version: null,
          decision: { id: 170, decision: "accepted", coverage: null, reason: null, author: AYU, at: "2026-11-19T09:06:00Z" },
          description: accepted.draft.description,
          method: accepted.draft.method,
          instrument: accepted.draft.instrument,
          acceptance: { type: "range", min: 20, max: 70, unit: "rpm" },
          witness_required: false,
        },
        drafts: [
          {
            proposal_id: 70,
            draft_id: "TS-URS-TP201-002",
            decision: { id: 170, decision: "accepted", coverage: null, reason: null, author: AYU, at: "2026-11-19T09:06:00Z" },
          },
        ],
        written: [],
        step_attributes: [],
      },
      {
        requirement: "URS-TP201-026",
        text: "Teks URS-TP201-026.",
        source: cite(1, "Teks URS-TP201-026."),
        coverage: {
          coverage_class: "site_only",
          decision: { id: 2, decision: "accepted", coverage: null, reason: null, author: BIMA, at: "2026-11-19T09:07:00Z" },
        },
        kind: "test_step",
        evidence: [],
        test_step: {
          origin: "written",
          proposal_id: null,
          version: 1,
          decision: null,
          description: "Verifikasi tombol darurat.",
          method: "Tekan tombol darurat saat turret berputar.",
          instrument: null,
          acceptance: { type: "present", value: null },
          witness_required: false,
        },
        drafts: [],
        written: [
          {
            version: 1,
            removed: false,
            test_step: {
              description: "Verifikasi tombol darurat.",
              method: "Tekan tombol darurat saat turret berputar.",
              instrument: null,
              acceptance: { type: "present", value: null },
            },
            from_proposal_id: null,
            decision_id: null,
            author: BIMA,
            at: "2026-11-19T09:08:00Z",
          },
        ],
        step_attributes: [],
      },
    ],
    urs: [
      {
        ...URS,
        numbers: "checked",
        missed: [
          {
            number: "URS-TP201-004",
            page: 2,
            disposition: {
              version: 2,
              kind: "not_tested_here",
              justification: "Diuji di IQ peralatan lain.",
              author: AYU,
              at: "2026-11-19T09:09:00Z",
            },
            dispositions: [
              {
                version: 1,
                kind: "not_a_requirement",
                justification: "Nomor judul bagian.",
                author: BIMA,
                at: "2026-11-19T09:07:00Z",
              },
              {
                version: 2,
                kind: "not_tested_here",
                justification: "Diuji di IQ peralatan lain.",
                author: AYU,
                at: "2026-11-19T09:09:00Z",
              },
            ],
          },
        ],
        unquoted: [],
      },
    ],
  },
};

export const submitted = protocolView({
  status: "submitted",
  rows: null,
  urs: null,
  checklist: null,
  submission: submissionView,
  submissions: [submissionView],
  events: [event({}), event({ id: 12, event: "submitted", status: "submitted", at: "2026-11-19T10:00:00Z" })],
});

export const withdrawn = protocolView({
  status: "withdrawn",
  rows: null,
  urs: null,
  events: [event({}), event({ id: 2, event: "withdrawn", status: "withdrawn", reason: "run yang lebih baru", ...BIMA })],
});

export const DEWI = { subject: "demo-0004", issuer: AYU.issuer, name: "Dewi Anggraini Lestari" };

/** Approved by the approving persona (ticket #253): the copy approved, and the approval. */
export const approvedEvent = event({ id: 13, event: "approved", status: "approved", at: "2026-11-19T11:00:00Z", ...DEWI });
export const approved = protocolView({
  status: "approved",
  rows: null,
  urs: null,
  checklist: null,
  submission: { ...submissionView, outcome: approvedEvent },
  submissions: [{ ...submissionView, outcome: approvedEvent }],
  events: [...submitted.events, approvedEvent],
});

/** Returned to Draft (ticket #253): live rows again, the returned copy listed with its reason. */
export const returnedEvent = event({
  id: 13,
  event: "returned",
  status: "draft",
  reason: "Takometer belum dikalibrasi.",
  at: "2026-11-19T11:00:00Z",
  ...DEWI,
});
export const returned = protocolView({
  submissions: [{ ...submissionView, outcome: returnedEvent }],
  events: [...submitted.events, returnedEvent],
});
