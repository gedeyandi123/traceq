// The Protocol page (spec #247, ticket #249): status and history, one row per requirement of
// each kind with what blocks, drafted Test Steps with the decision controls of slice 1, the
// start and withdraw controls by role and status, and the known limits.
import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import messages from "../../messages/id.json";
import { AssembledProtocolView, type ProtocolControls, type ProtocolError } from "./AssembledProtocolView";
import type { DecisionView } from "./Decisions";
import { decision, RUN_ID } from "./decisions.fixture";
import { protocolView, rows, withdrawn } from "./protocol.fixture";
import type { ProtocolView } from "@/api/client";

const action = async () => {};
const controls: ProtocolControls = { start: action, withdraw: action, write: action, remove: action, edit: action };
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
  expect(screen.getByText("5 baris: 2 masih memblokir, 1 referensi vendor, 3 baris langkah uji")).toBeDefined();
  const rows = within(screen.getByRole("region", { name: "Baris protokol" })).getAllByRole("row").slice(1);
  expect(rows.map((r) => r.getAttribute("data-testid"))).toEqual([
    "URS-TP201-001",
    "URS-TP201-002",
    "URS-TP201-010",
    "URS-TP201-026",
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

test("a written Test Step is the row's Test Step, with every version who and when", () => {
  renderPage(protocolView());
  const r = row("URS-TP201-026");
  expect(r.getByText("Langkah uji tertulis, versi 2")).toBeDefined();
  expect(r.getByText("Verifikasi tombol darurat menghentikan turret.")).toBeDefined();
  expect(r.getByText("Riwayat versi (2)")).toBeDefined();
  expect(r.getByText("Versi 1 oleh Ayu Kartika Sari, 19/11/2026 09.10 UTC")).toBeDefined();
  expect(r.getByText("Versi 2 oleh Bima Arya Nugraha, 19/11/2026 09.20 UTC")).toBeDefined();
  // The old and the new content, each in full.
  expect(r.getByText(/^Verifikasi tombol darurat\. · .* · tidak disebut · Harus ada$/)).toBeDefined();
  expect(r.getByText(/^Verifikasi tombol darurat menghentikan turret\. · .* · Stopwatch · ≤ 2 s$/)).toBeDefined();
});

test("the deciding role gets the write form with the four AC shapes, prefilled", () => {
  renderPage(protocolView(), decider);
  const vendor = row("URS-TP201-010");
  const form = within(vendor.getByRole("form", { name: "Tulis langkah uji" }));
  expect((form.getByRole("textbox", { name: "Deskripsi" }) as HTMLTextAreaElement).value).toBe(
    "Verifikasi URS-TP201-010 di lokasi.",
  );
  const shape = form.getByRole("combobox", { name: "Bentuk" }) as HTMLSelectElement;
  expect(shape.value).toBe("range");
  expect([...shape.options].map((o) => o.value)).toEqual(["", "range", "number", "one_of", "present"]);
  expect((form.getByRole("textbox", { name: "Batas bawah" }) as HTMLInputElement).value).toBe("20");
  expect((form.getByRole("textbox", { name: "Satuan" }) as HTMLInputElement).value).toBe("rpm");
  expect(vendor.getByText("Diisi dari langkah uji rancangan.")).toBeDefined();
  // No Reason for Change for a written version.
  expect(form.queryByRole("textbox", { name: "Alasan perubahan" })).toBeNull();

  const written = row("URS-TP201-026");
  expect(written.getByRole("form", { name: "Ubah langkah uji tertulis" })).toBeDefined();
  expect(written.getByRole("button", { name: "Hapus langkah uji tertulis" })).toBeDefined();

  const withdrawnPrefill = row("URS-TP201-030");
  expect(withdrawnPrefill.getByText(/Diisi dari versi terakhir di protokol yang ditarik/)).toBeDefined();
  const f = within(withdrawnPrefill.getByRole("form", { name: "Tulis langkah uji" }));
  expect((f.getByRole("combobox", { name: "Bentuk" }) as HTMLSelectElement).value).toBe("number");
  expect((f.getByRole("textbox", { name: "Nilai" }) as HTMLInputElement).value).toBe("4.5");
});

test("a row whose draft is accepted says to reject it before writing; undecided rows have no form", () => {
  renderPage(protocolView(), decider);
  expect(row("URS-TP201-002").getByText(/Tolak atau putuskan ulang dulu sebelum menulis/)).toBeDefined();
  expect(row("URS-TP201-002").queryByRole("form", { name: "Tulis langkah uji" })).toBeNull();
  expect(row("URS-TP201-001").queryByRole("form", { name: "Tulis langkah uji" })).toBeNull();
});

test("a draft without AC is edited with a Reason for Change and the AC set there", () => {
  renderPage(protocolView(), decider);
  const r = row("URS-TP201-030");
  expect(r.getByText("Sunting rancangan dan tetapkan kriteria penerimaan")).toBeDefined();
  const form = within(r.getByRole("form", { name: "Sunting rancangan" }));
  expect((form.getByRole("textbox", { name: "Deskripsi" }) as HTMLTextAreaElement).value).toBe(
    "Verifikasi URS-TP201-030 di lokasi.",
  );
  expect((form.getByRole("combobox", { name: "Bentuk" }) as HTMLSelectElement).value).toBe("");
  expect(form.getByRole("textbox", { name: "Alasan perubahan" })).toBeDefined();
  expect(form.getByRole("button", { name: "Simpan suntingan" })).toBeDefined();
  // A drafted AC in one of the four shapes starts the edit form.
  const vendor = within(row("URS-TP201-010").getByRole("form", { name: "Sunting rancangan" }));
  expect((vendor.getByRole("combobox", { name: "Bentuk" }) as HTMLSelectElement).value).toBe("range");
});

test("a draft edited shows as edited, not as a class", () => {
  const last = rows[4];
  const d = last?.drafts[0];
  if (!last || !d) throw new Error("the fixture has a fifth row with a draft");
  const made = decision({ decision: "edited", reason: "AC dari URS" });
  const edited = protocolView({
    rows: [{ ...last, drafts: [{ ...d, proposal: { ...d.proposal, state: "decided", decisions: [made] } }] }],
  });
  renderPage(edited);
  expect(screen.getByText("Disunting oleh Ayu Kartika Sari, 16/11/2026 09.30 UTC")).toBeDefined();
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
