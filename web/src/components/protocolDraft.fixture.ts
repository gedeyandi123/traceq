// A Protocol Draft as the API serves it, for the render tests of the draft screen (spec #196,
// ticket #210). Hand-written, not taken from the Review Package: three Test Steps (one
// looser than the URS, one not compared, one within the URS) and a traceability row whose
// Test Step is not printed; the vendor documents a comparator may come from; and a Test Step
// whose reading the citation check dropped, for the tests that add it.
import type { Cite, DraftFindingView, DraftTestStep, Proposal, ProtocolDraftView } from "@/api/client";

import { RUN_ID } from "./decisions.fixture";

const DRAFT = { doc: "OQ-TP201", rev: 0 };
const URS = { doc: "URS-TP201", rev: 1 };

function cite(doc: { doc: string; rev: number }, page: number, quote: string): Cite {
  return { ...doc, page, quote };
}

const noiseLimit = { type: "range", min: null, max: 60, unit: "dB(A)", min_exclusive: false, max_exclusive: false } as const;

export const deviates: DraftFindingView["finding"] = {
  type: "ac_deviates_from_urs",
  layer: "rule",
  test_step: "OQ-03",
  row: null,
  requirement: "URS-TP201-020",
  detail: "AC accepts up to 65 dB(A); the URS rejects above 60 dB(A)",
  ac: { ...noiseLimit, max: 65 },
  urs_limit: noiseLimit,
  citations: [
    cite(DRAFT, 2, "OQ-03 Kebisingan maks. 65 dB(A)"),
    cite(URS, 2, "Kebisingan maksimal 60 dB(A)."),
  ],
};

/** A finding of a type no practitioner has reviewed (spec #375): the API carries its label. */
export const outsideCapability: DraftFindingView["finding"] = {
  type: "ac_outside_documented_capability",
  layer: "rule",
  test_step: "OQ-03",
  row: null,
  requirement: "URS-TP201-020",
  detail: "OQ-03 requires at least 105 kN, above the maximum 100 kN the Datasheet DS-TP201 states",
  ac: { ...noiseLimit, min: 105, max: null, unit: "kN" },
  urs_limit: null,
  capability: { type: "number", value: 100, unit: "kN" },
  label: "not reviewed by a practitioner",
  citations: [cite(DRAFT, 2, "OQ-03 minimal 105 kN"), cite({ doc: "DS-TP201", rev: 0 }, 1, "Maximum main compression force 100 kN")],
};

/** A unit error (spec #375, S2b): the URS number in a unit off by a power of ten; the label comes from the API. */
export const unitError: DraftFindingView["finding"] = {
  type: "unit_error",
  layer: "rule",
  test_step: "OQ-03",
  row: null,
  requirement: "URS-TP201-020",
  detail: "OQ-03 prints at most 18 cm where URS-TP201-020 says at most 18 mm: the number is the URS number and the unit is off by a factor of 10.",
  ac: { ...noiseLimit, max: 18, unit: "cm" },
  urs_limit: { ...noiseLimit, max: 18, unit: "mm" },
  label: "not reviewed by a practitioner",
  citations: [cite(DRAFT, 2, "OQ-03 maks. 18 cm"), cite(URS, 2, "Tinggi maksimal 18 mm.")],
};

export const notTested: DraftFindingView["finding"] = {
  type: "requirement_not_tested",
  layer: "rule",
  test_step: null,
  row: "URS-TP201-031",
  requirement: "URS-TP201-031",
  detail: "the traceability table lists OQ-21 for URS-TP201-031; no such Test Step is printed",
  ac: null,
  urs_limit: null,
  citations: [cite(DRAFT, 8, "URS-TP201-031 OQ-21")],
};

/** A Test Step the draft prints whose reading the citation check dropped (story 7). */
export const notReadStep: DraftTestStep = {
  id: "OQ-02A",
  requirements: [],
  acceptance: null,
  not_read: "quote check",
  traced: [],
  compared: false,
  not_compared: null,
};

export function proposal(over: Partial<Proposal>): Proposal {
  return {
    id: 40,
    kind: "draft",
    requirement: null,
    position: 0,
    content_hash: "d0",
    state: "undecided",
    decisions: [],
    previous: null,
    previous_class: null,
    ...over,
  };
}

export function draftView(findings: DraftFindingView[]): ProtocolDraftView {
  return {
    run_id: RUN_ID,
    imported: findings.some((f) => f.proposal !== null),
    package: "TP-201-OQ-draft",
    document: { doc_id: "OQ-TP201", rev: 0, sha256: "ab".repeat(32) },
    test_steps: [
      {
        id: "OQ-01",
        requirements: ["URS-TP201-001"],
        acceptance: {
          printed: "minimal 100 kN",
          value: { type: "range", min: 100, max: null, unit: "kN", min_exclusive: false, max_exclusive: false },
          citation: cite(DRAFT, 1, "OQ-01 Gaya kompresi minimal 100 kN"),
        },
        traced: [
          {
            requirement: "URS-TP201-001",
            urs_limit: { type: "range", min: 100, max: null, unit: "kN", min_exclusive: false, max_exclusive: false },
            citation: cite(URS, 1, "Gaya kompresi minimal 100 kN."),
            not_parsed: null,
            compared: true,
            deviates: false,
            not_compared: null,
            comparators: [
              {
                doc: "FAT-TP201-M",
                rev: 0,
                kind: "FAT",
                facts: [
                  {
                    name: "FAT-M-02",
                    printed: "102 kN",
                    citation: cite({ doc: "FAT-TP201-M", rev: 0 }, 1, "FAT-M-02 Gaya kompresi 102 kN Lulus"),
                  },
                ],
              },
            ],
          },
        ],
        compared: true,
        not_compared: null,
      },
      {
        id: "OQ-02",
        requirements: ["URS-TP201-005"],
        acceptance: {
          printed: "20–60 rpm",
          value: { type: "range", min: 20, max: 60, unit: "rpm", min_exclusive: false, max_exclusive: false },
          citation: cite(DRAFT, 1, "OQ-02 Kecepatan putar 20–60 rpm"),
        },
        traced: [
          {
            requirement: "URS-TP201-005",
            urs_limit: { type: "range", min: 20, max: 60, unit: "rpm", min_exclusive: false, max_exclusive: false },
            citation: cite(URS, 1, "Kecepatan putar 20–60 rpm."),
            not_parsed: null,
            compared: false,
            deviates: false,
            not_compared: "two-sided URS range",
            comparators: [],
          },
        ],
        compared: false,
        not_compared: "two-sided URS range",
      },
      {
        id: "OQ-03",
        requirements: ["URS-TP201-020"],
        acceptance: {
          printed: "maks. 65 dB(A)",
          value: { ...noiseLimit, max: 65 },
          citation: cite(DRAFT, 2, "OQ-03 Kebisingan maks. 65 dB(A)"),
        },
        traced: [
          {
            requirement: "URS-TP201-020",
            urs_limit: noiseLimit,
            citation: cite(URS, 2, "Kebisingan maksimal 60 dB(A)."),
            not_parsed: null,
            compared: true,
            deviates: true,
            not_compared: null,
            comparators: [],
          },
        ],
        compared: true,
        not_compared: null,
      },
    ],
    trace_rows: [],
    findings,
    vendor_documents: [
      { doc: "DS-TP201", rev: 0, kind: "datasheet" },
      { doc: "FAT-TP201-M", rev: 0, kind: "FAT" },
      { doc: "SAT-TP201", rev: 0, kind: "SAT" },
    ],
  };
}
