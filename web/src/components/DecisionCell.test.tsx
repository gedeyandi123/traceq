// The decision progress line and the folded decision forms (spec #135, ticket #139), over the
// fixture run folder and the decision fixtures.
import { fireEvent, render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { Findings, Matrix, Proposal } from "@/api/client";
import messages from "../../messages/id.json";
import findingsFixture from "../../../tests/fixtures/run/runs/20261113T090000Z-f1a2b3/findings.json";
import matrixFixture from "../../../tests/fixtures/run/runs/20261113T090000Z-f1a2b3/matrix.json";
import type { DecisionView } from "./Decisions";
import { counts, decision, BIMA, RUN_ID } from "./decisions.fixture";
import { FindingsView } from "./FindingsView";
import { MatrixTable } from "./MatrixTable";

const action = async () => {};

function coverage(id: number, requirement: string, over: Partial<Proposal>): Proposal {
  return {
    id,
    kind: "coverage",
    requirement,
    position: null,
    content_hash: `h${id}`,
    state: "undecided",
    decisions: [],
    previous: null,
    previous_class: null,
    ...over,
  };
}

const proposals: Proposal[] = [
  coverage(11, "URS-TP201-002", { state: "decided", decisions: [decision({ id: 2, ...BIMA })] }),
  coverage(12, "URS-TP201-026", {
    state: "changed",
    previous: decision({ id: 1, content_hash: "old", ...BIMA }),
  }),
  coverage(13, "URS-TP201-030", {}),
];

function renderMatrix(decisions: DecisionView) {
  return render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <MatrixTable matrix={matrixFixture as Matrix} runId={RUN_ID} decisions={decisions} />
    </NextIntlClientProvider>,
  );
}

function renderFindings(decisions: DecisionView) {
  return render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <FindingsView findings={findingsFixture as Findings} runId={RUN_ID} decisions={decisions} />
    </NextIntlClientProvider>,
  );
}

test("the matrix says how many Coverage rows are decided: accepted, edited or rejected", () => {
  // Coverage: 3 Proposals, 1 undecided, 1 edited, 1 changed.
  renderMatrix({ proposals, counts, access: { mode: "decide", action } });

  expect(screen.getByText("1/3 usulan sudah diputuskan")).toBeDefined();
});

test("the findings count Check Findings and AI Findings together", () => {
  // Check: 2 Proposals, both decided; AI: 1 undecided.
  renderFindings({ proposals: [], counts, access: { mode: "readOnly", why: "noRole" } });

  expect(screen.getByText("2/3 usulan sudah diputuskan")).toBeDefined();
});

test("no progress line when the API gave no counts", () => {
  renderMatrix({ access: { mode: "readOnly", why: "signedOut" } });

  expect(screen.queryByText(/usulan sudah diputuskan/)).toBeNull();
});

test("only a decided Proposal offers to decide again; a changed one is decided afresh", async () => {
  renderMatrix({ proposals, counts, access: { mode: "decide", action } });

  fireEvent.click(screen.getByRole("button", { name: "URS-TP201-002" }));
  let dialog = await screen.findByRole("dialog", { name: "URS-TP201-002" });
  expect(within(dialog).getByRole("button", { name: "Putuskan ulang" })).toBeDefined();

  fireEvent.click(within(dialog).getByRole("button", { name: "Berikutnya" }));
  dialog = await screen.findByRole("dialog", { name: "URS-TP201-026" });
  expect(within(dialog).queryByRole("button", { name: "Putuskan ulang" })).toBeNull();
  expect(within(dialog).getByRole("button", { name: "Terima" })).toBeDefined();

  fireEvent.click(within(dialog).getByRole("button", { name: "Berikutnya" }));
  dialog = await screen.findByRole("dialog", { name: "URS-TP201-030" });
  expect(within(dialog).queryByRole("button", { name: "Putuskan ulang" })).toBeNull();
});

test("a read-only viewer gets no fold to decide again", async () => {
  renderMatrix({ proposals, counts, access: { mode: "readOnly", why: "noRole" } });

  fireEvent.click(screen.getByRole("button", { name: "URS-TP201-002" }));
  const dialog = await screen.findByRole("dialog", { name: "URS-TP201-002" });
  expect(within(dialog).queryByRole("button", { name: "Putuskan ulang" })).toBeNull();
});
