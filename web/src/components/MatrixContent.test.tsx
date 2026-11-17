// What the restyled matrix adds (spec #135, ticket #141): the Coverage summary, the values on
// the Evidence chips, the value citation only when it differs, and the changed-class arrow.
import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { Matrix, Proposal } from "@/api/client";
import messages from "../../messages/id.json";
import fixture from "../../../tests/fixtures/run/runs/20261113T090000Z-f1a2b3/matrix.json";
import type { DecisionView } from "./Decisions";
import { counts, decision, BIMA, RUN_ID } from "./decisions.fixture";
import { MatrixTable } from "./MatrixTable";

const matrix = fixture as Matrix;

function renderMatrix(m: Matrix = matrix, decisions: DecisionView = { access: { mode: "readOnly", why: "signedOut" } }) {
  return render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <MatrixTable matrix={m} runId={RUN_ID} decisions={decisions} />
    </NextIntlClientProvider>,
  );
}

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

test("the Coverage summary counts the rows per class, riskiest first", () => {
  renderMatrix();

  const summary = within(screen.getByRole("list", { name: "Ringkasan cakupan" }));
  // Shapes are hidden from screen readers; the text a person reads is the count and the label.
  const items = summary.getAllByRole("listitem").map((li) => li.textContent?.replace(/[●◐○▲◆–]/g, ""));
  expect(items).toEqual([
    "0Konflik",
    "0Celah",
    "1Sebagian",
    "1Hanya di lokasi",
    "0Dicakup vendor",
    "1Belum dinilai",
  ]);
  // The meaning of each class is one click away.
  expect(screen.getByText("Arti setiap kelas")).toBeDefined();
  expect(screen.getByText("Tidak ada bukti sama sekali.")).toBeDefined();
});

test("each Evidence chip carries its step and observed value, and the first design value", () => {
  renderMatrix();

  const speed = within(screen.getByTestId("URS-TP201-002"));
  expect(speed.getByText("FAT-M-02 · 20–60 rpm")).toBeDefined();
  // A reading that needs confirmation shows its readings and a question mark.
  expect(speed.getByText("FAT-M-05 · 1.500 / 1,5 ?")).toBeDefined();
  expect(speed.getByText("Desain · 20-70 rpm")).toBeDefined();
  // A chip is not a link: the only citation links are the requirement's and the full list's.
  expect(speed.getAllByRole("link").map((a) => a.textContent)).toEqual([
    "URS-TP201 rev 0, hlm. 1",
    "FAT-TP201-M rev 0, hlm. 1",
    "FAT-TP201-M rev 0, hlm. 2",
    "DS-TP201 rev 0, hlm. 1",
  ]);
});

test("the value citation shows only when it differs from the requirement citation", () => {
  const differs: Matrix = {
    ...matrix,
    requirements: matrix.requirements.map((r) =>
      r.id === "URS-TP201-026" && r.value_citation
        ? { ...r, value_citation: { ...r.value_citation, quote: "380 V, 3 fasa" } }
        : r,
    ),
  };
  renderMatrix(differs);

  // Equal to the requirement citation: one link, not two.
  const speed = within(screen.getByTestId("URS-TP201-002"));
  expect(speed.getAllByRole("link", { name: "URS-TP201 rev 0, hlm. 1" })).toHaveLength(1);
  // A different quote on the same page: both links, each with its own quote.
  const power = within(screen.getByTestId("URS-TP201-026"));
  expect(
    power.getAllByRole("link", { name: "URS-TP201 rev 0, hlm. 2" }).map((a) => a.getAttribute("title")),
  ).toEqual(["Catu daya 380 V, 3 fasa, 50 Hz.", "380 V, 3 fasa"]);
});

test("a class a human changed shows as proposed → decided; other rows show one class", () => {
  const proposals: Proposal[] = [
    coverage(11, "URS-TP201-002", {
      state: "decided",
      decisions: [
        decision({ id: 3, decision: "edited", coverage: "gap", reason: "Rentang FAT tidak mencakup 70 rpm" }),
        decision({ id: 2, ...BIMA }),
      ],
    }),
    coverage(12, "URS-TP201-026", {
      state: "changed",
      previous: decision({ id: 1, content_hash: "old", decision: "edited", coverage: "gap", ...BIMA }),
    }),
    coverage(13, "URS-TP201-030", {}),
  ];
  renderMatrix(matrix, { proposals, counts, access: { mode: "readOnly", why: "noRole" } });

  const edited = within(screen.getByTestId("URS-TP201-002"));
  expect(edited.getByText("Sebagian")).toBeDefined();
  expect(edited.getByText("Kelas setelah keputusan")).toBeDefined();
  expect(edited.getByText("Celah")).toBeDefined();

  for (const id of ["URS-TP201-026", "URS-TP201-030"]) {
    expect(within(screen.getByTestId(id)).queryByText("Kelas setelah keputusan")).toBeNull();
  }

});

test("an accepted class shows no arrow", () => {
  const proposals = [coverage(11, "URS-TP201-002", { state: "decided", decisions: [decision({ id: 4, ...BIMA })] })];
  renderMatrix(matrix, { proposals, counts, access: { mode: "readOnly", why: "noRole" } });

  const row = within(screen.getByTestId("URS-TP201-002"));
  expect(row.getByText("Sebagian")).toBeDefined();
  expect(row.queryByText("Kelas setelah keputusan")).toBeNull();
});
