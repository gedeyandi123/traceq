// PROTOTYPE (feat/ui-redesign-prototype, never merged): every decision state rendered by the
// real components over the fixture data the render tests use, so the decided, edited,
// rejected, changed and undecided looks can be checked without writing to any database.
// The forms post to a no-op action. Not served in production builds. The two JSON files are
// copies of tests/fixtures/run/runs/20261113T090000Z-f1a2b3 (Turbopack does not import
// from outside web/).
import { notFound } from "next/navigation";

import type { Findings, Matrix } from "@/api/client";
import type { DecisionView } from "@/components/Decisions";
import { FindingsView } from "@/components/FindingsView";
import { MatrixTable } from "@/components/MatrixTable";
import { BIMA, RUN_ID, counts, decision } from "@/components/decisions.fixture";
import { Callout } from "@/components/ui/ui";

import findingsFixture from "./findings.fixture.json";
import matrixFixture from "./matrix.fixture.json";

export const dynamic = "force-dynamic";

async function noop() {
  "use server";
}

const matrixProposals: DecisionView["proposals"] = [
  {
    id: 11,
    kind: "coverage",
    requirement: "URS-TP201-002",
    position: null,
    content_hash: "h",
    state: "decided",
    decisions: [
      decision({
        id: 3,
        decision: "edited",
        coverage: "gap",
        reason: "Rentang FAT tidak mencakup 70 rpm",
        at: "2026-11-16T10:15:00Z",
      }),
      decision({ id: 2, ...BIMA }),
    ],
    previous: null,
  },
  {
    id: 12,
    kind: "coverage",
    requirement: "URS-TP201-026",
    position: null,
    content_hash: "h2",
    state: "changed",
    decisions: [],
    previous: decision({ id: 1, content_hash: "old", run_id: "20261101T080000Z-aaaaaa", ...BIMA }),
  },
  {
    id: 13,
    kind: "coverage",
    requirement: "URS-TP201-030",
    position: null,
    content_hash: "h3",
    state: "undecided",
    decisions: [],
    previous: null,
  },
];

const findingProposals: DecisionView["proposals"] = [
  { id: 21, kind: "check", requirement: null, position: 0, content_hash: "c0", state: "decided", decisions: [decision({ id: 5 })], previous: null },
  {
    id: 22,
    kind: "check",
    requirement: null,
    position: 1,
    content_hash: "c1",
    state: "decided",
    decisions: [decision({ id: 6, decision: "rejected", reason: "Protokol disetujui di halaman 2", ...BIMA })],
    previous: null,
  },
  { id: 23, kind: "ai", requirement: null, position: 0, content_hash: "a0", state: "undecided", decisions: [], previous: null },
];

export default function StatesPreview() {
  if (process.env.NODE_ENV === "production") notFound();
  const access = { mode: "decide", action: noop } as const;
  return (
    <div className="stack">
      <Callout tone="warning">
        <p>
          PROTOTIPE: data contoh dari tes render (run {RUN_ID}), bukan data demo. Tombol tidak
          menyimpan apa pun.
        </p>
      </Callout>
      <MatrixTable
        matrix={matrixFixture as Matrix}
        runId={RUN_ID}
        decisions={{ proposals: matrixProposals, counts, access }}
      />
      <FindingsView
        findings={findingsFixture as Findings}
        runId={RUN_ID}
        decisions={{ proposals: findingProposals, counts, access }}
      />
    </div>
  );
}
