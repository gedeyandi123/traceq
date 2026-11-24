// RequiredObservedUnit, GMP-safe fail > ambiguous precedence, Coverage summary, and changed-class badges.
import { fireEvent, render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { Matrix, Proposal } from "@/api/client";
import messages from "../../messages/id.json";
import fixture from "../../../tests/fixtures/run/runs/20261113T090000Z-f1a2b3/matrix.json";
import type { DecisionView } from "./Decisions";
import { counts, decision, BIMA, RUN_ID } from "./decisions.fixture";
import { MatrixTable } from "./MatrixTable";

const matrix = fixture as Matrix;

function renderMatrix(
  m: Matrix = matrix,
  decisions: DecisionView = { access: { mode: "readOnly", why: "signedOut" } },
) {
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

test("the Coverage summary counts the rows per class, riskiest first, and toggles legend", () => {
  renderMatrix();

  const summary = within(screen.getByRole("list", { name: "Ringkasan cakupan" }));
  const items = summary.getAllByRole("listitem").map((li) => li.textContent);
  expect(items).toEqual([
    "0Konflik",
    "0Celah",
    "1Sebagian",
    "1Hanya di lokasi",
    "0Dicakup vendor",
    "1Belum dinilai",
  ]);

  const legendBtn = screen.getByRole("button", { name: "Arti setiap kelas" });
  fireEvent.click(legendBtn);
  expect(screen.getByText("Tidak ada bukti sama sekali.")).toBeDefined();
});

test("RequiredObservedUnit deduplicates stage prefix and applies GMP-safe fail > ambiguous precedence", async () => {
  // In fixture URS-TP201-002: FAT-M-02 is pass, FAT-M-05 is ambiguous with result: null
  const first = renderMatrix();

  const speedRow = screen.getByRole("row", { name: /URS-TP201-002/ });
  expect(within(speedRow).getByText("FAT-M-02 · 20–60 rpm")).toBeDefined();
  expect(within(speedRow).getByText("FAT-M-05 · 1.500 / 1,5 ?")).toBeDefined();
  expect(within(speedRow).getByText("Desain · 20-70 rpm")).toBeDefined();
  expect(within(speedRow).getByText("Perlu konfirmasi nilai (ambigu)")).toBeDefined();

  // Open drawer: ambiguous warning renders when result !== "fail"
  fireEvent.click(screen.getByRole("button", { name: "URS-TP201-002" }));
  const dialog = await screen.findByRole("dialog", { name: "URS-TP201-002" });
  expect(within(dialog).getByText("Perlu konfirmasi nilai (ambigu)")).toBeDefined();

  first.unmount();

  // Now force result === "fail" on FAT-M-05: fail MUST override ambiguous!
  const failOverridesAmbiguous: Matrix = {
    ...matrix,
    requirements: matrix.requirements.map((r) =>
      r.id === "URS-TP201-002"
        ? {
            ...r,
            evidence: r.evidence.map((e) =>
              e.step === "FAT-M-05" ? { ...e, result: "fail" } : e,
            ),
          }
        : r,
    ),
  };
  renderMatrix(failOverridesAmbiguous);
  const secondSpeedRow = screen.getByRole("row", { name: /URS-TP201-002/ });
  expect(within(secondSpeedRow).queryByText("Perlu konfirmasi nilai (ambigu)")).toBeNull();
});

test("the value citation shows in Drawer only when it differs from the requirement citation", async () => {
  const differs: Matrix = {
    ...matrix,
    requirements: matrix.requirements.map((r) =>
      r.id === "URS-TP201-026" && r.value_citation
        ? { ...r, value_citation: { ...r.value_citation, quote: "380 V, 3 fasa" } }
        : r,
    ),
  };
  renderMatrix(differs);

  fireEvent.click(screen.getByRole("button", { name: "URS-TP201-002" }));
  const speedDialog = await screen.findByRole("dialog", { name: "URS-TP201-002" });
  expect(
    within(speedDialog).getAllByRole("button", { name: "URS-TP201 rev 0, hlm. 1" }),
  ).toHaveLength(1);

  fireEvent.click(within(speedDialog).getByRole("button", { name: "Berikutnya" }));
  const powerDialog = await screen.findByRole("dialog", { name: "URS-TP201-026" });
  expect(
    within(powerDialog)
      .getAllByRole("button", { name: "URS-TP201 rev 0, hlm. 2" })
      .map((b) => b.getAttribute("title")),
  ).toEqual(["Catu daya 380 V, 3 fasa, 50 Hz.", "380 V, 3 fasa"]);
});

test("a class a human changed shows as proposed -> decided; other rows show one class", () => {
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

  const edited = screen.getByRole("row", { name: /URS-TP201-002/ });
  expect(within(edited).getByText("Sebagian")).toBeDefined();
  expect(within(edited).getByText("Kelas setelah keputusan")).toBeDefined();
  expect(within(edited).getByText("Celah")).toBeDefined();

  for (const id of ["URS-TP201-026", "URS-TP201-030"]) {
    expect(
      within(screen.getByRole("row", { name: new RegExp(id) })).queryByText(
        "Kelas setelah keputusan",
      ),
    ).toBeNull();
  }
});

test("an accepted class shows no arrow", () => {
  const proposals = [
    coverage(11, "URS-TP201-002", { state: "decided", decisions: [decision({ id: 4, ...BIMA })] }),
  ];
  renderMatrix(matrix, { proposals, counts, access: { mode: "readOnly", why: "noRole" } });

  const row = screen.getByRole("row", { name: /URS-TP201-002/ });
  expect(within(row).getByText("Sebagian")).toBeDefined();
  expect(within(row).queryByText("Kelas setelah keputusan")).toBeNull();
});
