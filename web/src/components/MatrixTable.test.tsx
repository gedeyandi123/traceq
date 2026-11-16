// The matrix screen over the fixture run folder the API contract tests use (spec #29), and
// with the Proposal Decisions of the run (spec #105).
import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { Matrix } from "@/api/client";
import messages from "../../messages/id.json";
import fixture from "../../../tests/fixtures/run/runs/20261113T090000Z-f1a2b3/matrix.json";
import type { DecisionView } from "./Decisions";
import { counts, decision, BIMA, RUN_ID } from "./decisions.fixture";
import { MatrixTable } from "./MatrixTable";

const action = async () => {};

function renderMatrix(decisions: DecisionView = { access: { mode: "readOnly", why: "signedOut" } }) {
  return render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <MatrixTable matrix={fixture as Matrix} runId={RUN_ID} decisions={decisions} />
    </NextIntlClientProvider>,
  );
}

const proposals: DecisionView["proposals"] = [
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

test("renders each requirement with its Coverage class, reason and cited Evidence", () => {
  renderMatrix();

  expect(screen.getByRole("columnheader", { name: "Cakupan" })).toBeDefined();
  const speed = within(screen.getByTestId("URS-TP201-002"));
  expect(speed.getByText("Sebagian")).toBeDefined();
  expect(speed.getByText(/FAT-M-02: result does not meet the URS/)).toBeDefined();
  expect(speed.getByText("20–70 rpm")).toBeDefined();
  expect(speed.getByText(/Terbaca ganda \(1\.500 \/ 1,5\): minta konfirmasi/)).toBeDefined();

  const step = speed.getByRole("link", { name: "FAT-TP201-M rev 0, hlm. 1" });
  expect(step.getAttribute("href")).toBe(
    `/api/runs/${RUN_ID}/documents/FAT-TP201-M/0#page=1`,
  );
  expect(step.getAttribute("title")).toBe("FAT-M-02 Turret speed range 20-60 rpm 20-60 rpm Pass");
  expect(speed.getByRole("link", { name: "DS-TP201 rev 0, hlm. 1" })).toBeDefined();

  const power = within(screen.getByTestId("URS-TP201-026"));
  expect(power.getByText("Hanya di lokasi")).toBeDefined();
  expect(power.getByText("Tidak ada bukti vendor")).toBeDefined();

  const unassessed = within(screen.getByTestId("URS-TP201-030"));
  expect(unassessed.getByText("Belum dinilai")).toBeDefined();
  expect(unassessed.getByText("Tidak ada nilai terverifikasi")).toBeDefined();

  expect(screen.getByText("Dokumen vendor yang tidak terbaca")).toBeDefined();
  expect(screen.getByText("SAT-TP201 rev 0 (scan)")).toBeDefined();
});

test("an imported run shows each row's decision state, its decisions and the counts", () => {
  renderMatrix({ proposals, counts, access: { mode: "decide", action } });

  expect(screen.queryByText(/Hanya membaca/)).toBeNull();
  const decided = within(screen.getByTestId("URS-TP201-002"));
  expect(decided.getByText("Sudah diputuskan")).toBeDefined();
  expect(
    decided.getByText("Diubah ke Celah oleh Ayu Kartika Sari, 16/11/2026 10.15 UTC"),
  ).toBeDefined();
  expect(decided.getByText("Rentang FAT tidak mencakup 70 rpm")).toBeDefined();
  expect(decided.getByText("Diterima oleh Bima Arya Nugraha, 16/11/2026 09.30 UTC")).toBeDefined();
  // Replacing a decision on the same content needs a Reason for Change.
  const accept = decided.getByRole("button", { name: "Terima" }).closest("form")!;
  expect(within(accept).getByRole("textbox").hasAttribute("required")).toBe(true);
  expect(decided.queryByRole("button", { name: /setuju/i })).toBeNull();

  const changed = within(screen.getByTestId("URS-TP201-026"));
  expect(changed.getByText("Berubah sejak diputuskan: belum diputuskan lagi")).toBeDefined();
  expect(
    changed.getByText(
      "Keputusan sebelumnya, atas isi lain: Diterima oleh Bima Arya Nugraha, 16/11/2026 09.30 UTC",
    ),
  ).toBeDefined();
  const acceptChanged = changed.getByRole("button", { name: "Terima" }).closest("form")!;
  expect(within(acceptChanged).queryByRole("textbox")).toBeNull();
  const edit = changed.getByRole("button", { name: "Ubah kelas" }).closest("form")!;
  expect(within(edit).getByRole("textbox").hasAttribute("required")).toBe(true);
  expect(within(edit).getByRole("combobox").hasAttribute("required")).toBe(true);
  expect(within(edit).getByRole("option", { name: "Celah" })).toBeDefined();

  // No class proposed: it can only be changed, not accepted.
  const undecided = within(screen.getByTestId("URS-TP201-030"));
  expect(undecided.getByText("Belum diputuskan")).toBeDefined();
  expect(undecided.queryByRole("button", { name: "Terima" })).toBeNull();
  expect(undecided.getByRole("button", { name: "Ubah kelas" })).toBeDefined();

  const tally = within(screen.getByRole("table", { name: "Jumlah keputusan" }));
  const row = within(tally.getByRole("row", { name: /Baris cakupan/ }));
  expect(row.getAllByRole("cell").map((c) => c.textContent)).toEqual([
    "3", "1", "0", "1", "0", "1", "2",
  ]);
});

test("a viewer without the deciding role reads the decisions and cannot decide", () => {
  renderMatrix({ proposals, counts, access: { mode: "readOnly", why: "noRole" } });

  expect(
    screen.getByText(/Hanya membaca: identitas ini tidak memiliki peran pengambil keputusan/),
  ).toBeDefined();
  expect(within(screen.getByTestId("URS-TP201-002")).getByText("Sudah diputuskan")).toBeDefined();
  expect(screen.queryByRole("button", { name: "Terima" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Ubah kelas" })).toBeNull();
});

test("a viewer who is not signed in sees the run read-only with what deciding needs", () => {
  renderMatrix({ access: { mode: "readOnly", why: "signedOut" } });

  expect(
    screen.getByText(/Hanya membaca: masuk sebagai orang dengan peran pengambil keputusan/),
  ).toBeDefined();
  expect(screen.queryByText("Belum diputuskan")).toBeNull();
  expect(screen.queryByRole("button")).toBeNull();
  expect(screen.queryByRole("table", { name: "Jumlah keputusan" })).toBeNull();
});
