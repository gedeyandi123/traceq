// The Pre-review screen over the fixture run folder the API contract tests use (spec #29), and
// with the Proposal Decisions of the run (spec #105).
import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { Findings } from "@/api/client";
import messages from "../../messages/id.json";
import fixture from "../../../tests/fixtures/run/runs/20261113T090000Z-f1a2b3/findings.json";
import type { DecisionView } from "./Decisions";
import { counts, decision, BIMA, RUN_ID } from "./decisions.fixture";
import { FindingsView } from "./FindingsView";

const action = async () => {};

function renderFindings(
  decisions: DecisionView = { access: { mode: "readOnly", why: "signedOut" } },
) {
  return render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <FindingsView findings={fixture as Findings} runId={RUN_ID} decisions={decisions} />
    </NextIntlClientProvider>,
  );
}

const proposals: DecisionView["proposals"] = [
  {
    id: 21,
    kind: "check",
    requirement: null,
    position: 0,
    content_hash: "c0",
    state: "decided",
    decisions: [decision({ id: 5 })],
    previous: null,
    previous_class: null,
  },
  {
    id: 22,
    kind: "check",
    requirement: null,
    position: 1,
    content_hash: "c1",
    state: "decided",
    decisions: [
      decision({ id: 6, decision: "rejected", reason: "Protokol disetujui di halaman 2", ...BIMA }),
    ],
    previous: null,
    previous_class: null,
  },
  {
    id: 23,
    kind: "ai",
    requirement: null,
    position: 0,
    content_hash: "a0",
    state: "undecided",
    decisions: [],
    previous: null,
    previous_class: null,
  },
];

test("renders Check Findings, AI Findings and missing documents apart, each cited", () => {
  renderFindings();

  const check = within(screen.getByRole("region", { name: "Temuan pemeriksaan (aturan)" }));
  expect(check.getByText("Di luar batas namun ditandai Lulus")).toBeDefined();
  expect(check.getByText("Protokol vendor belum disetujui")).toBeDefined();
  const limit = check.getByRole("link", { name: "FAT-TP201-M rev 0, hlm. 1" });
  expect(limit.getAttribute("href")).toBe(`/api/runs/${RUN_ID}/documents/FAT-TP201-M/0#page=1`);
  expect(limit.getAttribute("title")).toBe("FAT-M-04 Noise level <= 50 dB(A) 52 dB(A) Pass");
  expect(check.getByRole("link", { name: "SOP-VAL-002 rev 0, hlm. 1" })).toBeDefined();
  expect(check.queryByText("Menunggu tinjauan")).toBeNull();

  const ai = within(screen.getByRole("region", { name: "Temuan AI (saran)" }));
  expect(ai.getByText("Data tidak konsisten")).toBeDefined();
  expect(ai.getByText("Menunggu tinjauan")).toBeDefined();
  expect(ai.getByText(/claude-haiku-5-5/)).toBeDefined();
  expect(ai.getByRole("link", { name: "DS-TP201 rev 0, hlm. 1" })).toBeDefined();
  expect(ai.queryByText("Di luar batas namun ditandai Lulus")).toBeNull();

  const missing = within(screen.getByRole("region", { name: "Dokumen yang tidak ada" }));
  expect(missing.getByText("IQ-TP201")).toBeDefined();
  expect(missing.getByText("OQ-TP201")).toBeDefined();
  const cited = missing.getAllByRole("link", { name: "VMP-001 rev 0, hlm. 2" });
  expect(cited.map((a) => a.getAttribute("title"))).toEqual([
    "IQ-TP201 Protokol IQ IQ",
    "OQ-TP201 Protokol OQ OQ",
  ]);
});

test("an imported run shows each finding's decision state in place of pending, and the counts", () => {
  renderFindings({ proposals, counts, access: { mode: "decide", action } });

  const check = within(screen.getByRole("region", { name: "Temuan pemeriksaan (aturan)" }));
  const [limit, protocol] = check.getAllByRole("row").slice(1);
  const first = within(limit!);
  expect(first.getByText("Sudah diputuskan")).toBeDefined();
  expect(first.getByText("Diterima oleh Ayu Kartika Sari, 16/11/2026 09.30 UTC")).toBeDefined();
  const second = within(protocol!);
  expect(second.getByText("Ditolak oleh Bima Arya Nugraha, 16/11/2026 09.30 UTC")).toBeDefined();
  expect(second.getByText("Protokol disetujui di halaman 2")).toBeDefined();

  const ai = within(screen.getByRole("region", { name: "Temuan AI (saran)" }));
  expect(ai.queryByText("Menunggu tinjauan")).toBeNull();
  expect(ai.getByText("Belum diputuskan")).toBeDefined();
  // Accepting a first decision needs no reason; rejecting always does.
  const accept = ai.getByRole("button", { name: "Terima" }).closest("form")!;
  expect(within(accept).queryByRole("textbox")).toBeNull();
  const reject = ai.getByRole("button", { name: "Tolak" }).closest("form")!;
  expect(within(reject).getByRole("textbox").hasAttribute("required")).toBe(true);
  expect(screen.queryByRole("button", { name: /semua|setuju/i })).toBeNull();

  const tally = within(screen.getByRole("table", { name: "Jumlah keputusan" }));
  const row = (name: RegExp) =>
    within(tally.getByRole("row", { name })).getAllByRole("cell").map((c) => c.textContent);
  expect(row(/Temuan pemeriksaan/)).toEqual(["2", "0", "1", "0", "1", "0", "0"]);
  expect(row(/Temuan AI/)).toEqual(["1", "1", "0", "0", "0", "0", "0"]);
});

test("a run that is not imported shows read-only with pending and what deciding needs", () => {
  renderFindings({ access: { mode: "readOnly", why: "notImported" } });

  expect(screen.getByText(/Hanya membaca: run ini belum diimpor/)).toBeDefined();
  const ai = within(screen.getByRole("region", { name: "Temuan AI (saran)" }));
  expect(ai.getByText("Menunggu tinjauan")).toBeDefined();
  expect(screen.queryByRole("button")).toBeNull();
});
