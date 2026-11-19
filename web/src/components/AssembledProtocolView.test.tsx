// The Protocol page (spec #247, ticket #249): status and history, one row per requirement of
// each kind with what blocks, drafted Test Steps with the decision controls of slice 1, the
// start and withdraw controls by role and status, and the known limits.
import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import messages from "../../messages/id.json";
import { AssembledProtocolView, type ProtocolControls, type ProtocolError } from "./AssembledProtocolView";
import type { DecisionView } from "./Decisions";
import { RUN_ID } from "./decisions.fixture";
import { protocolView, withdrawn } from "./protocol.fixture";
import type { ProtocolView } from "@/api/client";

const action = async () => {};
const controls: ProtocolControls = { start: action, withdraw: action };
const decider: DecisionView = { access: { mode: "decide", action } };
const reader: DecisionView = { access: { mode: "readOnly", why: "noRole" } };

function renderPage(
  protocol: ProtocolView | null,
  decisions: DecisionView = reader,
  error?: ProtocolError,
) {
  return render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <AssembledProtocolView
        protocol={protocol}
        runId={RUN_ID}
        decisions={decisions}
        controls={decisions.access.mode === "decide" ? controls : null}
        error={error}
      />
    </NextIntlClientProvider>,
  );
}

function row(requirement: string) {
  return within(screen.getByTestId(requirement));
}

test("without a Protocol, a person with the deciding role can start one; a reader cannot", () => {
  const { unmount } = renderPage(null, decider);
  expect(screen.getByText("Belum ada protokol yang dimulai dari run ini")).toBeDefined();
  expect(screen.getByRole("button", { name: "Mulai protokol dari run ini" })).toBeDefined();
  unmount();
  renderPage(null, reader);
  expect(screen.queryByRole("button")).toBeNull();
  expect(screen.getByText(/tidak memiliki peran pengambil keputusan/)).toBeDefined();
});

test("a Protocol in Draft status shows its status, history and one row per requirement", () => {
  renderPage(protocolView());
  expect(screen.getByRole("heading", { name: "Status protokol 7" })).toBeDefined();
  expect(screen.getByText("Draft (sedang disusun)")).toBeDefined();
  expect(screen.getByText("Dimulai oleh Ayu Kartika Sari, 19/11/2026 09.00 UTC")).toBeDefined();
  expect(screen.getByText("4 baris: 2 masih memblokir, 1 referensi vendor, 2 baris langkah uji")).toBeDefined();
  const rows = within(screen.getByRole("region", { name: "Baris protokol" })).getAllByRole("row").slice(1);
  expect(rows.map((r) => r.getAttribute("data-testid"))).toEqual([
    "URS-TP201-001",
    "URS-TP201-002",
    "URS-TP201-010",
    "URS-TP201-030",
  ]);
});

test("Coverage changed since it was decided blocks, with a link to the matrix", () => {
  renderPage(protocolView());
  const r = row("URS-TP201-001");
  expect(r.getByText("Berubah sejak diputuskan")).toBeDefined();
  expect(r.getByText("Belum dapat ditentukan")).toBeDefined();
  expect(r.getByText(/Memblokir: cakupan belum diputuskan/)).toBeDefined();
  expect(r.getByRole("link", { name: "Putuskan di matriks" }).getAttribute("href")).toBe(
    `/runs/${RUN_ID}#URS-TP201-001`,
  );
});

test("a Test Step row shows its accepted draft; a Vendor Reference names its Evidence", () => {
  renderPage(protocolView());
  const step = row("URS-TP201-002");
  expect(step.getByText("Sebagian")).toBeDefined();
  expect(step.getByText("Langkah uji")).toBeDefined();
  expect(step.getByText("Langkah uji rancangan yang diterima")).toBeDefined();
  expect(step.getAllByText("20–70 rpm").length).toBeGreaterThan(0);
  expect(step.queryByText(/Memblokir/)).toBeNull();

  const vendor = row("URS-TP201-010");
  expect(vendor.getByText("Dicakup vendor")).toBeDefined();
  expect(vendor.getByText("Referensi vendor")).toBeDefined();
  expect(vendor.getByText("FAT-TP201-M rev 0, langkah FAT-M-02")).toBeDefined();
  expect(vendor.getByText(/Tidak perlu diputuskan/)).toBeDefined();
});

test("a Test Step row without a Test Step blocks; a draft without AC says it is set by a human", () => {
  renderPage(protocolView());
  const r = row("URS-TP201-030");
  expect(r.getByText(/Memblokir: belum ada langkah uji/)).toBeDefined();
  expect(r.getByText(/Ditetapkan oleh manusia: tidak ada kriteria penerimaan di sumber/)).toBeDefined();
  expect(r.getByText("Instrumen: tidak disebut")).toBeDefined();
});

test("the deciding role gets the decision controls on drafts and the withdraw form", () => {
  renderPage(protocolView(), decider);
  expect(row("URS-TP201-030").getByRole("button", { name: "Terima" })).toBeDefined();
  expect(row("URS-TP201-002").getByText("Putuskan ulang")).toBeDefined();
  expect(screen.getByRole("button", { name: "Tarik protokol" })).toBeDefined();
  expect(screen.getByRole("textbox", { name: "Alasan penarikan" })).toBeDefined();
  expect(screen.queryByRole("button", { name: /Mulai protokol/ })).toBeNull();
});

test("a reader sees the rows and no controls at all", () => {
  renderPage(protocolView(), reader);
  expect(screen.getAllByRole("row").length).toBeGreaterThan(1);
  expect(screen.queryByRole("button")).toBeNull();
  expect(screen.queryByRole("textbox")).toBeNull();
});

test("a withdrawn Protocol shows its reason and lets the deciding role start a new one", () => {
  const { unmount } = renderPage(withdrawn, decider);
  expect(screen.getByText("Ditarik")).toBeDefined();
  expect(screen.getByText("Ditarik oleh Bima Arya Nugraha, 19/11/2026 09.00 UTC")).toBeDefined();
  expect(screen.getByText("run yang lebih baru")).toBeDefined();
  expect(screen.queryByRole("region", { name: "Baris protokol" })).toBeNull();
  expect(screen.getByRole("button", { name: "Mulai protokol baru dari run ini" })).toBeDefined();
  expect(screen.queryByRole("button", { name: "Tarik protokol" })).toBeNull();
  unmount();
  renderPage(withdrawn, reader);
  expect(screen.queryByRole("button")).toBeNull();
});

test("a submitted Protocol shows no live rows and cannot be withdrawn", () => {
  renderPage(protocolView({ status: "submitted", rows: null }), decider);
  expect(screen.getByText("Diajukan")).toBeDefined();
  expect(screen.getByText("Baris hanya dihitung selama protokol berstatus Draft.")).toBeDefined();
  expect(screen.queryByRole("button")).toBeNull();
});

test("the known limits are always shown", () => {
  renderPage(null);
  const limits = within(screen.getByRole("complementary", { name: "Batas yang diketahui" }));
  expect(limits.getAllByRole("listitem").map((li) => li.textContent)).toEqual([
    "Satu langkah uji per persyaratan.",
    "IQ dan OQ digabung dalam satu protokol.",
    "Tidak ada protokol cetak atau ekspor.",
    "Persetujuan adalah status yang dicatat, bukan Tanda Tangan Elektronik.",
    "Belum ada versi baru setelah protokol disetujui (langkah 6).",
  ]);
});

test("a refused start is reported", () => {
  renderPage(null, decider, "conflict");
  expect(screen.getByRole("alert").textContent).toMatch(/protokol lain untuk peralatan ini masih terbuka/);
});
