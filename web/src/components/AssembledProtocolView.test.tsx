// The Protocol page (spec #247, ticket #249): status and history, one row per requirement of
// each kind with what blocks, drafted Test Steps with the decision controls of slice 1, the
// start and withdraw controls by role and status, and the known limits; the submission
// checklist, the submit control and the frozen copy with its hash (ticket #252).
import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import messages from "../../messages/id.json";
import { type ApprovalControls, AssembledProtocolView, type ProtocolControls, type ProtocolError } from "./AssembledProtocolView";
import type { DecisionView } from "./Decisions";
import { decision, RUN_ID } from "./decisions.fixture";
import { approved, protocolView, ready, returned, rows, submitted, withdrawn } from "./protocol.fixture";
import type { ProtocolView } from "@/api/client";

const action = async () => {};
const controls: ProtocolControls = {
  start: action,
  withdraw: action,
  write: action,
  remove: action,
  edit: action,
  answer: action,
  submit: action,
};
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

test("a submitted Protocol shows its frozen copy and hash, no live rows, and cannot be withdrawn", () => {
  renderPage(submitted, decider);
  expect(screen.getByText("Diajukan")).toBeDefined();
  expect(screen.getByText("Baris hanya dihitung selama protokol berstatus Draft.")).toBeDefined();
  expect(screen.queryByRole("button")).toBeNull();
  expect(screen.queryByRole("region", { name: "Baris protokol" })).toBeNull();
  expect(screen.queryByRole("region", { name: "Yang memblokir pengajuan" })).toBeNull();
  const copy = within(screen.getByRole("region", { name: /Salinan beku yang diajukan/ }));
  expect(copy.getByTestId("copy-hash").textContent).toBe("a".repeat(64));
  expect(copy.getByText("Ayu Kartika Sari, diajukan 19/11/2026 10.00 UTC")).toBeDefined();
  const r002 = within(copy.getByTestId("copy-URS-TP201-002"));
  expect(r002.getByText("Langkah uji rancangan yang diterima")).toBeDefined();
  expect(r002.getAllByText("Diterima oleh Ayu Kartika Sari, 19/11/2026 09.06 UTC")).toHaveLength(1);
  expect(r002.getByText("Diterima oleh Ayu Kartika Sari, 19/11/2026 09.05 UTC")).toBeDefined();
  const r026 = within(copy.getByTestId("copy-URS-TP201-026"));
  expect(r026.getByText("Langkah uji tertulis, versi 1")).toBeDefined();
  expect(r026.getByText("Versi 1 oleh Bima Arya Nugraha, 19/11/2026 09.08 UTC")).toBeDefined();
  expect(copy.getByText(/URS-TP201-004 \(URS-TP201 rev 0\): persyaratan yang tidak diuji protokol ini/)).toBeDefined();
  // Every version of a disposition is frozen and shown, the replaced one too (ticket #263).
  const history = within(copy.getByRole("list", { name: "Riwayat jawaban (2)" }));
  expect(history.getByText("Versi 1 oleh Bima Arya Nugraha, 19/11/2026 09.07 UTC")).toBeDefined();
  expect(history.getByText("Versi 2 oleh Ayu Kartika Sari, 19/11/2026 09.09 UTC")).toBeDefined();
  expect(history.getByText("Bukan persyaratan · Nomor judul bagian.")).toBeDefined();
});

test("a reader sees the frozen copy too", () => {
  renderPage(submitted, reader);
  expect(screen.getByTestId("copy-hash").textContent).toBe("a".repeat(64));
  expect(screen.queryByRole("button")).toBeNull();
});

test("the checklist lists every check with its count and links to the rows; submit is disabled while blocked", () => {
  renderPage(protocolView(), decider);
  const list = within(screen.getByRole("region", { name: /Yang memblokir pengajuan/ }));
  expect(list.getByTestId("check-coverage_undecided").textContent).toBe(
    "Cakupan belum diputuskan atas isi run ini: 1: URS-TP201-001",
  );
  expect(list.getByTestId("check-draft_undecided").textContent).toBe("Langkah uji rancangan belum diputuskan: 0");
  expect(list.getByRole("link", { name: "URS-TP201-030" }).getAttribute("href")).toBe("#row-URS-TP201-030");
  expect(list.getByRole("link", { name: "URS-TP201-004" }).getAttribute("href")).toBe("#protocol-missed");
  expect(document.getElementById("row-URS-TP201-030")).not.toBeNull();
  const submit = list.getByRole("button", { name: "Ajukan protokol" });
  expect((submit as HTMLButtonElement).disabled).toBe(true);
});

test("when nothing blocks the deciding role may submit; a reader may not", () => {
  const { unmount } = renderPage(protocolView({ checklist: ready }), decider);
  const list = within(screen.getByRole("region", { name: /Yang memblokir pengajuan/ }));
  expect(list.getByText("Tidak ada yang memblokir: protokol dapat diajukan.")).toBeDefined();
  expect((list.getByRole("button", { name: "Ajukan protokol" }) as HTMLButtonElement).disabled).toBe(false);
  unmount();
  renderPage(protocolView({ checklist: ready }), reader);
  expect(screen.queryByRole("button", { name: "Ajukan protokol" })).toBeNull();
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

// --- Missed requirement numbers (ticket #251) ------------------------------------------

function missed(key: string) {
  return within(screen.getByTestId(key));
}

test("missed numbers are listed per URS with their page; unanswered ones block", () => {
  renderPage(protocolView());
  const section = within(screen.getByRole("region", { name: "Nomor persyaratan tercetak yang terlewat" }));
  expect(section.getByText("Memblokir: 1 nomor belum dijawab")).toBeDefined();
  const open = missed("URS-TP201/0/URS-TP201-004");
  expect(open.getByText("URS-TP201-004")).toBeDefined();
  expect(open.getByRole("link", { name: "hlm. 2" }).getAttribute("href")).toBe(
    `/api/runs/${RUN_ID}/documents/URS-TP201/0#page=2`,
  );
  expect(open.getByText("Memblokir: belum dijawab")).toBeDefined();
  const annex = within(section.getByRole("region", { name: "URS-TP201-ANNEX rev 1" }));
  expect(annex.getByText(/Tidak berlaku/)).toBeDefined();
  expect(annex.queryByRole("listitem")).toBeNull();
});

test("an answered number shows the answer in force and every answer, who and when", () => {
  renderPage(protocolView());
  const r = missed("URS-TP201/0/URS-TP201-003");
  expect(r.queryByText(/Memblokir/)).toBeNull();
  expect(r.getByText("Bukan persyaratan")).toBeDefined();
  expect(r.getByText("Riwayat jawaban (2)")).toBeDefined();
  expect(r.getByText("Versi 1 oleh Ayu Kartika Sari, 19/11/2026 09.30 UTC")).toBeDefined();
  expect(r.getByText("Versi 2 oleh Bima Arya Nugraha, 19/11/2026 09.40 UTC")).toBeDefined();
  expect(r.getByText("Persyaratan yang tidak diuji protokol ini · Diuji di IQ.")).toBeDefined();
});

test("the deciding role answers a number with one of two kinds and a justification", () => {
  renderPage(protocolView(), decider);
  const form = within(missed("URS-TP201/0/URS-TP201-004").getByRole("form", { name: "Jawab URS-TP201-004" }));
  const kind = form.getByRole("combobox", { name: "Jawaban" }) as HTMLSelectElement;
  expect([...kind.options].map((o) => o.value)).toEqual(["", "not_a_requirement", "not_tested_here"]);
  expect(form.getByRole("textbox", { name: "Justifikasi" })).toBeDefined();
  expect(form.getByRole("button", { name: "Simpan jawaban" })).toBeDefined();
  // A change starts from the answer in force.
  const change = within(
    missed("URS-TP201/0/URS-TP201-003").getByRole("form", { name: "Ubah jawaban URS-TP201-003" }),
  );
  expect((change.getByRole("combobox", { name: "Jawaban" }) as HTMLSelectElement).value).toBe("not_a_requirement");
});

test("a reader sees the missed numbers but no answer form", () => {
  renderPage(protocolView(), reader);
  const missed = within(screen.getByRole("region", { name: /Nomor persyaratan tercetak yang terlewat/ }));
  expect(missed.getByText("URS-TP201-004")).toBeDefined();
  expect(screen.queryByRole("form", { name: /Jawab/ })).toBeNull();
});

test("unquoted text is shown per URS and never blocks", () => {
  renderPage(protocolView());
  const section = within(screen.getByRole("region", { name: "Teks URS yang tidak dikutip" }));
  expect(section.getByText("URS-TP201 rev 0: tampilkan teks (1)")).toBeDefined();
  expect(section.getByText(/Nomor dokumen URS-TP201/)).toBeDefined();
  expect(section.getByText(/tidak memblokir/)).toBeDefined();
  expect(section.queryByText(/^Memblokir/)).toBeNull();
});

test("a run without a completeness check says so and has nothing to answer", () => {
  renderPage(protocolView({ urs: null }), decider);
  expect(screen.getByText(/Pemeriksaan kelengkapan tidak dijalankan/)).toBeDefined();
  expect(screen.queryByRole("region", { name: "Teks URS yang tidak dikutip" })).toBeNull();
});

test("a refused start is reported", () => {
  renderPage(null, decider, "conflict");
  expect(screen.getByRole("alert").textContent).toMatch(/protokol lain untuk peralatan ini masih terbuka/);
});

// --- Approving and returning (ticket #253) ------------------------------------------------

const approvalControls: ApprovalControls = { approve: action, return: action };

function renderForApprover(protocol: ProtocolView) {
  return render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <AssembledProtocolView
        protocol={protocol}
        runId={RUN_ID}
        decisions={reader}
        controls={null}
        approval={approvalControls}
      />
    </NextIntlClientProvider>,
  );
}

test("the approving role approves the submission shown, bound to its event id and hash, or returns it", () => {
  const { container } = renderForApprover(submitted);
  expect(screen.getByText(/bukan Tanda Tangan Elektronik \(ADR 0007 fase 2\)/)).toBeDefined();
  const approve = screen.getByRole("button", { name: "Setujui protokol" });
  const form = approve.closest("form") as HTMLFormElement;
  expect((form.elements.namedItem("submission_event_id") as HTMLInputElement).value).toBe("12");
  expect((form.elements.namedItem("hash") as HTMLInputElement).value).toBe("a".repeat(64));
  expect(screen.getByRole("textbox", { name: "Alasan pengembalian" })).toBeDefined();
  expect(screen.getByRole("button", { name: "Kembalikan ke Draft" })).toBeDefined();
  expect(container.querySelector("textarea[name=reason][required]")).not.toBeNull();
});

test("the deciding role and a reader get no approve or return control", () => {
  const { unmount } = renderPage(submitted, decider);
  expect(screen.queryByRole("button", { name: "Setujui protokol" })).toBeNull();
  unmount();
  renderPage(submitted, reader);
  expect(screen.queryByRole("button", { name: "Kembalikan ke Draft" })).toBeNull();
});

test("an approved Protocol shows the approval as a recorded status and no controls", () => {
  renderForApprover(approved);
  expect(screen.getByText("Disetujui")).toBeDefined();
  expect(screen.getByText("Disetujui oleh Dewi Anggraini Lestari, 19/11/2026 11.00 UTC")).toBeDefined();
  expect(screen.getByText(/Disetujui: status yang dicatat .* bukan Tanda Tangan Elektronik/)).toBeDefined();
  expect(screen.getByTestId("copy-hash").textContent).toBe("a".repeat(64));
  expect(screen.queryByRole("button")).toBeNull();
});

test("a returned Protocol reads live again and lists its earlier copy with the reason", () => {
  renderForApprover(returned);
  expect(screen.getByText("Draft (sedang disusun)")).toBeDefined();
  expect(screen.getByRole("region", { name: "Baris protokol" })).toBeDefined();
  expect(screen.queryByRole("button", { name: "Setujui protokol" })).toBeNull();
  const earlier = within(screen.getByTestId("earlier-12"));
  expect(earlier.getByText("a".repeat(64))).toBeDefined();
  expect(earlier.getByText("Dikembalikan ke Draft oleh Dewi Anggraini Lestari, 19/11/2026 11.00 UTC")).toBeDefined();
  expect(earlier.getByText("Takometer belum dikalibrasi.")).toBeDefined();
});

test("an Approver-only identity does not get the no-deciding-role banner; a reader still does", () => {
  const { unmount } = renderForApprover(protocolView());
  expect(screen.queryByText(/tidak memiliki peran pengambil keputusan/)).toBeNull();
  expect(screen.getByText(/dapat menyetujui atau mengembalikan/)).toBeDefined();
  unmount();
  renderPage(protocolView(), reader);
  expect(screen.getByText(/tidak memiliki peran pengambil keputusan/)).toBeDefined();
});
