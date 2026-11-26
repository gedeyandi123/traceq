// The Protocol page (spec #247, ADR 0012, ADR 0014): Sticky Submission Readiness Bar,
// Radix Tabs, Opsi A compact table + 640px Slide-Over Drawer, Confirmation Modals,
// FrozenCopy + ApprovalForms (Dewi), MissedNumbers, and ADR 0012 Limits.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";

import type { ProtocolView } from "@/api/client";
import messages from "../../messages/id.json";
import {
  type ApprovalControls,
  AssembledProtocolView,
  type ProtocolControls,
  type ProtocolError,
} from "./AssembledProtocolView";
import type { DecisionView } from "./Decisions";
import { decision, RUN_ID } from "./decisions.fixture";
import { openBlockingModal, openDialogCount } from "./modal.fixture";
import { approved, protocolView, ready, returned, rows, submitted, withdrawn } from "./protocol.fixture";
import { RunShellProvider } from "./RunShellContext";

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
      <RunShellProvider>
        <AssembledProtocolView
          protocol={protocol}
          runId={RUN_ID}
          decisions={decisions}
          controls={decisions.access.mode === "decide" ? controls : null}
          signingAuth={SIGNING_AUTH}
          error={error}
        />
      </RunShellProvider>
    </NextIntlClientProvider>,
  );
}

const SIGNING_AUTH = {
  oidcMode: false,
  reauthAuthTime: null,
  signer: { name: "Dewi Lestari", username: "dewi" },
};

function row(requirement: string) {
  return within(screen.getByTestId(requirement));
}

async function openRowDrawer(user: ReturnType<typeof userEvent.setup>, requirement: string) {
  await user.click(row(requirement).getByRole("button", { name: requirement }));
  return within(await screen.findByRole("dialog"));
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

test("a Protocol in Draft status shows its status, history tab and one row per requirement", async () => {
  const user = userEvent.setup();
  renderPage(protocolView());
  expect(screen.getByRole("heading", { name: "Status protokol 7" })).toBeDefined();
  expect(screen.getByText("Draft")).toBeDefined();
  expect(
    screen.getByText("5 baris: 2 masih memblokir, 1 referensi vendor, 3 baris langkah uji"),
  ).toBeDefined();

  const tableRows = within(screen.getByRole("region", { name: "Baris protokol" }))
    .getAllByRole("row")
    .slice(1);
  expect(tableRows.map((r) => r.getAttribute("data-testid"))).toEqual([
    "URS-TP201-001",
    "URS-TP201-002",
    "URS-TP201-010",
    "URS-TP201-026",
    "URS-TP201-030",
  ]);

  await user.click(screen.getByRole("tab", { name: "Riwayat & Salinan" }));
  expect(
    await screen.findByText("Dimulai oleh Ayu Kartika Sari, 19/11/2026 09.00 UTC"),
  ).toBeDefined();
});

test("Coverage changed since it was decided blocks, with a link to the matrix", () => {
  renderPage(protocolView());
  const r = row("URS-TP201-001");
  expect(r.getByText("Berubah sejak diputuskan")).toBeDefined();
  expect(r.getByText("Belum dapat ditentukan")).toBeDefined();
  expect(r.getByText(/Memblokir: cakupan belum diputuskan/)).toBeDefined();
  expect(r.getByRole("link", { name: "Putuskan di matriks" }).getAttribute("href")).toBe(
    `/runs/${RUN_ID}?selected=URS-TP201-001`,
  );
});

test("a Test Step row shows its accepted draft; a Vendor Reference names its Evidence in table and drawer", async () => {
  const user = userEvent.setup();
  renderPage(protocolView());
  const step = row("URS-TP201-002");
  expect(step.getByText("Sebagian")).toBeDefined();
  expect(step.getByText("Langkah uji")).toBeDefined();
  expect(step.getByText(/Langkah uji rancangan yang diterima/)).toBeDefined();
  expect(step.getByText("20–70 rpm")).toBeDefined();
  expect(step.queryByText(/Memblokir/)).toBeNull();

  const vendor = row("URS-TP201-010");
  expect(vendor.getByText("Dicakup vendor")).toBeDefined();
  expect(vendor.getByText("Referensi vendor")).toBeDefined();
  expect(vendor.getByText("FAT-TP201-M rev 0, langkah FAT-M-02")).toBeDefined();

  const drawer = await openRowDrawer(user, "URS-TP201-010");
  expect(drawer.getByText(/Tidak perlu diputuskan/)).toBeDefined();
});

test("a Test Step row without a Test Step blocks; a draft without AC says it is set by a human in the drawer", async () => {
  const user = userEvent.setup();
  renderPage(protocolView());
  const r = row("URS-TP201-030");
  expect(r.getByText(/Memblokir: belum ada langkah uji/)).toBeDefined();

  const drawer = await openRowDrawer(user, "URS-TP201-030");
  expect(drawer.getByText(/Ditetapkan oleh manusia: tidak ada kriteria penerimaan di sumber/)).toBeDefined();
  expect(drawer.getByText("Instrumen: tidak disebut")).toBeDefined();
});

test("the deciding role gets decision controls in the drawer and the withdraw confirmation modal", async () => {
  const user = userEvent.setup();
  renderPage(protocolView(), decider);

  const withdrawTrigger = screen.getByRole("button", { name: "Tarik protokol" });
  await user.click(withdrawTrigger);
  const modal = within(await screen.findByRole("dialog", { name: "Tarik protokol?" }));
  expect(modal.getByRole("textbox", { name: "Alasan penarikan" })).toBeDefined();
  expect(modal.getByRole("button", { name: "Tarik protokol" })).toBeDefined();
  await user.click(modal.getByRole("button", { name: "Batal" }));

  const d030 = await openRowDrawer(user, "URS-TP201-030");
  expect(d030.getByRole("button", { name: "Terima" })).toBeDefined();
  await user.click(d030.getByRole("button", { name: "Sebelumnya" }));
  await user.click(await screen.findByRole("button", { name: "Tutup panel" }));

  const d002 = await openRowDrawer(user, "URS-TP201-002");
  expect(d002.getByRole("button", { name: "Putuskan ulang" })).toBeDefined();
});

test("a written Test Step is the row's Test Step, with every version who and when in the drawer", async () => {
  const user = userEvent.setup();
  renderPage(protocolView());
  const drawer = await openRowDrawer(user, "URS-TP201-026");
  expect(drawer.getByText("Langkah uji tertulis, versi 2")).toBeDefined();
  expect(drawer.getByText("Verifikasi tombol darurat menghentikan turret.")).toBeDefined();
  expect(drawer.getByText("Riwayat versi (2)")).toBeDefined();
  expect(drawer.getByText("Versi 1 oleh Ayu Kartika Sari, 19/11/2026 09.10 UTC")).toBeDefined();
  expect(drawer.getByText("Versi 2 oleh Bima Arya Nugraha, 19/11/2026 09.20 UTC")).toBeDefined();
  expect(drawer.getByText(/^Verifikasi tombol darurat\. · .* · tidak disebut · Harus ada$/)).toBeDefined();
  expect(
    drawer.getByText(/^Verifikasi tombol darurat menghentikan turret\. · .* · Stopwatch · ≤ 2 s$/),
  ).toBeDefined();
});

test("the deciding role gets the write form with the four AC shapes, prefilled in the drawer", async () => {
  const user = userEvent.setup();
  renderPage(protocolView(), decider);

  const vendorDrawer = await openRowDrawer(user, "URS-TP201-010");
  const form = within(vendorDrawer.getByRole("form", { name: "Tulis langkah uji" }));
  expect((form.getByRole("textbox", { name: "Deskripsi" }) as HTMLTextAreaElement).value).toBe(
    "Verifikasi URS-TP201-010 di lokasi.",
  );
  const shape = form.getByRole("combobox", { name: "Bentuk" }) as HTMLSelectElement;
  expect(shape.value).toBe("range");
  expect([...shape.options].map((o) => o.value)).toEqual(["", "range", "number", "one_of", "present"]);
  expect((form.getByRole("textbox", { name: "Batas bawah" }) as HTMLInputElement).value).toBe("20");
  expect((form.getByRole("textbox", { name: "Satuan" }) as HTMLInputElement).value).toBe("rpm");
  expect(vendorDrawer.getByText("Diisi dari langkah uji rancangan.")).toBeDefined();
  expect(form.queryByRole("textbox", { name: "Alasan perubahan" })).toBeNull();
  await user.click(vendorDrawer.getByRole("button", { name: "Tutup panel" }));

  const writtenDrawer = await openRowDrawer(user, "URS-TP201-026");
  expect(writtenDrawer.getByRole("form", { name: "Ubah langkah uji tertulis" })).toBeDefined();
  expect(writtenDrawer.getByRole("button", { name: "Hapus langkah uji tertulis" })).toBeDefined();
  await user.click(writtenDrawer.getByRole("button", { name: "Tutup panel" }));

  const withdrawnDrawer = await openRowDrawer(user, "URS-TP201-030");
  expect(withdrawnDrawer.getByText(/Diisi dari versi terakhir di protokol yang ditarik/)).toBeDefined();
  const f = within(withdrawnDrawer.getByRole("form", { name: "Tulis langkah uji" }));
  expect((f.getByRole("combobox", { name: "Bentuk" }) as HTMLSelectElement).value).toBe("number");
  expect((f.getByRole("textbox", { name: "Nilai" }) as HTMLInputElement).value).toBe("4.5");
});

test("a row whose draft is accepted says to reject it before writing; undecided rows have no form", async () => {
  const user = userEvent.setup();
  renderPage(protocolView(), decider);

  const d002 = await openRowDrawer(user, "URS-TP201-002");
  expect(d002.getByText(/Tolak atau putuskan ulang dulu sebelum menulis/)).toBeDefined();
  expect(d002.queryByRole("form", { name: "Tulis langkah uji" })).toBeNull();
  await user.click(d002.getByRole("button", { name: "Tutup panel" }));

  const d001 = await openRowDrawer(user, "URS-TP201-001");
  expect(d001.queryByRole("form", { name: "Tulis langkah uji" })).toBeNull();
});

test("a draft without AC is edited with a Reason for Change and the AC set there", async () => {
  const user = userEvent.setup();
  renderPage(protocolView(), decider);

  const d030 = await openRowDrawer(user, "URS-TP201-030");
  expect(d030.getByText("Sunting rancangan dan tetapkan kriteria penerimaan")).toBeDefined();
  const form = within(d030.getByRole("form", { name: "Sunting rancangan" }));
  expect((form.getByRole("textbox", { name: "Deskripsi" }) as HTMLTextAreaElement).value).toBe(
    "Verifikasi URS-TP201-030 di lokasi.",
  );
  expect((form.getByRole("combobox", { name: "Bentuk" }) as HTMLSelectElement).value).toBe("");
  expect(form.getByRole("textbox", { name: "Alasan perubahan" })).toBeDefined();
  expect(form.getByRole("button", { name: "Simpan suntingan" })).toBeDefined();
  await user.click(d030.getByRole("button", { name: "Tutup panel" }));

  const d010 = await openRowDrawer(user, "URS-TP201-010");
  const vendor = within(d010.getByRole("form", { name: "Sunting rancangan" }));
  expect((vendor.getByRole("combobox", { name: "Bentuk" }) as HTMLSelectElement).value).toBe("range");
});

test("a draft edited shows as edited in the drawer, not as a class", async () => {
  const user = userEvent.setup();
  const last = rows[4];
  const d = last?.drafts[0];
  if (!last || !d) throw new Error("the fixture has a fifth row with a draft");
  const made = decision({ decision: "edited", reason: "AC dari URS" });
  const edited = protocolView({
    rows: [{ ...last, drafts: [{ ...d, proposal: { ...d.proposal, state: "decided", decisions: [made] } }] }],
  });
  renderPage(edited);
  const drawer = await openRowDrawer(user, "URS-TP201-030");
  expect(drawer.getByText("Disunting oleh Ayu Kartika Sari, 16/11/2026 09.30 UTC")).toBeDefined();
});

test("a reader sees the rows and no controls at all", () => {
  renderPage(protocolView(), reader);
  expect(screen.getAllByRole("row").length).toBeGreaterThan(1);
  expect(screen.queryByRole("button", { name: /Tarik protokol/ })).toBeNull();
  expect(screen.queryByRole("button", { name: /Ajukan protokol/ })).toBeNull();
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
  expect(screen.queryByRole("button", { name: /Tarik|Ajukan|Setujui|Kembalikan/ })).toBeNull();
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
  expect(
    copy.getByText(/URS-TP201-004 \(URS-TP201 rev 0\): persyaratan yang tidak diuji protokol ini/),
  ).toBeDefined();
  const history = within(copy.getByRole("list", { name: "Riwayat jawaban (2)" }));
  expect(history.getByText("Versi 1 oleh Bima Arya Nugraha, 19/11/2026 09.07 UTC")).toBeDefined();
  expect(history.getByText("Versi 2 oleh Ayu Kartika Sari, 19/11/2026 09.09 UTC")).toBeDefined();
  expect(history.getByText("Bukan persyaratan · Nomor judul bagian.")).toBeDefined();
});

test("a reader sees the frozen copy too", () => {
  renderPage(submitted, reader);
  expect(screen.getByTestId("copy-hash").textContent).toBe("a".repeat(64));
  expect(screen.queryByRole("button", { name: /Tarik|Ajukan|Setujui|Kembalikan/ })).toBeNull();
});

test("the checklist lists every check with its count and links to the rows; submit is disabled while blocked", () => {
  renderPage(protocolView(), decider);
  const list = within(screen.getByRole("region", { name: /Yang memblokir pengajuan/ }));
  expect(list.getByTestId("check-coverage_undecided").textContent).toBe(
    "Cakupan belum diputuskan atas isi run ini: 1: URS-TP201-001",
  );
  expect(list.getByTestId("check-draft_undecided").textContent).toBe(
    "Langkah uji rancangan belum diputuskan: 0",
  );
  expect(list.getByRole("link", { name: "URS-TP201-030" }).getAttribute("href")).toBe(
    "#row-URS-TP201-030",
  );
  expect(list.getByRole("link", { name: "URS-TP201-004" }).getAttribute("href")).toBe(
    "#protocol-missed",
  );
  expect(document.getElementById("row-URS-TP201-030")).not.toBeNull();
  const submit = list.getByRole("button", { name: "Ajukan protokol" });
  expect((submit as HTMLButtonElement).disabled).toBe(true);
});

test("when nothing blocks the deciding role may submit; a reader may not", () => {
  const { unmount } = renderPage(protocolView({ checklist: ready }), decider);
  const list = within(screen.getByRole("region", { name: /Yang memblokir pengajuan/ }));
  expect(list.getByText("Tidak ada yang memblokir: protokol dapat diajukan.")).toBeDefined();
  expect((list.getByRole("button", { name: "Ajukan protokol" }) as HTMLButtonElement).disabled).toBe(
    false,
  );
  unmount();
  renderPage(protocolView({ checklist: ready }), reader);
  expect(screen.queryByRole("button", { name: "Ajukan protokol" })).toBeNull();
});

test("the submit dialog posts the draft hash of the page the Preparer reads", async () => {
  const user = userEvent.setup();
  const hash = "c".repeat(64);
  renderPage(protocolView({ checklist: ready, draft_hash: hash }), decider);
  await user.click(screen.getByRole("button", { name: "Ajukan protokol" }));
  const dialog = within(await screen.findByRole("dialog", { name: "Ajukan protokol untuk persetujuan?" }));
  const form = dialog.getByRole("button", { name: "Ajukan protokol" }).closest("form") as HTMLFormElement;
  expect(dialog.getByTestId("signature-signer").textContent).toBe("Dewi Lestari(dewi)");
  expect((form.elements.namedItem("expected_draft_hash") as HTMLInputElement).value).toBe(hash);
  expect((form.elements.namedItem("protocol_id") as HTMLInputElement).value).toBe("7");
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

async function openMissedTab(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("tab", { name: /Nomor Terlewat & URS/ }));
  return within(await screen.findByRole("region", { name: /Nomor persyaratan tercetak yang terlewat/ }));
}

test("missed numbers are listed per URS with their page; unanswered ones block", async () => {
  const user = userEvent.setup();
  renderPage(protocolView());
  const section = await openMissedTab(user);
  expect(section.getByText("Memblokir: 1 nomor belum dijawab")).toBeDefined();
  const open = missed("URS-TP201/0/URS-TP201-004");
  expect(open.getByText("URS-TP201-004")).toBeDefined();
  expect(open.getByRole("button", { name: /hlm\. 2/ })).toBeDefined();
  expect(open.getByText("Memblokir: belum dijawab")).toBeDefined();
  const annex = within(section.getByRole("region", { name: "URS-TP201-ANNEX rev 1" }));
  expect(annex.getByText(/Tidak berlaku/)).toBeDefined();
  expect(annex.queryByRole("listitem")).toBeNull();
});

test("an answered number shows the answer in force and every answer, who and when", async () => {
  const user = userEvent.setup();
  renderPage(protocolView());
  await openMissedTab(user);
  const r = missed("URS-TP201/0/URS-TP201-003");
  expect(r.queryByText(/Memblokir/)).toBeNull();
  expect(r.getByText("Bukan persyaratan")).toBeDefined();
  await user.click(r.getByRole("button", { name: "Riwayat jawaban (2)" }));
  expect(await r.findByText("Versi 1 oleh Ayu Kartika Sari, 19/11/2026 09.30 UTC")).toBeDefined();
  expect(r.getByText("Versi 2 oleh Bima Arya Nugraha, 19/11/2026 09.40 UTC")).toBeDefined();
  expect(r.getByText("Persyaratan yang tidak diuji protokol ini · Diuji di IQ.")).toBeDefined();
});

test("the deciding role answers a number with one of two kinds and a justification", async () => {
  const user = userEvent.setup();
  renderPage(protocolView(), decider);
  await openMissedTab(user);

  const form = within(
    missed("URS-TP201/0/URS-TP201-004").getByRole("form", { name: "Jawab URS-TP201-004" }),
  );
  const kind = form.getByRole("combobox", { name: "Jawaban" }) as HTMLSelectElement;
  expect([...kind.options].map((o) => o.value)).toEqual(["", "not_a_requirement", "not_tested_here"]);
  expect(form.getByRole("textbox", { name: "Justifikasi" })).toBeDefined();
  expect(form.getByRole("button", { name: "Simpan jawaban" })).toBeDefined();

  const item003 = missed("URS-TP201/0/URS-TP201-003");
  await user.click(item003.getByRole("button", { name: "Ubah jawaban URS-TP201-003" }));
  const change = within(await item003.findByRole("form", { name: "Ubah jawaban URS-TP201-003" }));
  expect((change.getByRole("combobox", { name: "Jawaban" }) as HTMLSelectElement).value).toBe(
    "not_a_requirement",
  );
});

test("a reader sees the missed numbers but no answer form", async () => {
  const user = userEvent.setup();
  renderPage(protocolView(), reader);
  const section = await openMissedTab(user);
  expect(section.getByText("URS-TP201-004")).toBeDefined();
  expect(screen.queryByRole("form", { name: /Jawab/ })).toBeNull();
});

test("unquoted text is shown per URS and never blocks", async () => {
  const user = userEvent.setup();
  renderPage(protocolView());
  await openMissedTab(user);
  const section = within(screen.getByRole("region", { name: /Teks URS yang tidak dikutip/ }));
  const toggle = section.getByRole("button", { name: "URS-TP201 rev 0: tampilkan teks (1)" });
  await user.click(toggle);
  expect(await section.findByText(/Nomor dokumen URS-TP201/)).toBeDefined();
  expect(section.getByText(/tidak memblokir/)).toBeDefined();
  expect(section.queryByText(/^Memblokir/)).toBeNull();
});

test("a run without a completeness check says so and has nothing to answer", async () => {
  const user = userEvent.setup();
  renderPage(protocolView({ urs: null }), decider);
  await openMissedTab(user);
  expect(screen.getByText(/Pemeriksaan kelengkapan tidak dijalankan/)).toBeDefined();
  expect(screen.queryByRole("region", { name: /Teks URS yang tidak dikutip/ })).toBeNull();
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
      <RunShellProvider>
        <AssembledProtocolView
          protocol={protocol}
          runId={RUN_ID}
          decisions={reader}
          controls={null}
          approval={approvalControls}
          signingAuth={SIGNING_AUTH}
        />
      </RunShellProvider>
    </NextIntlClientProvider>,
  );
}

test("the approving role approves the submission shown, bound to its event id and hash, or returns it via confirmation modal", async () => {
  const user = userEvent.setup();
  renderForApprover(submitted);
  expect(screen.getByText(/bukan Tanda Tangan Elektronik \(ADR 0007 fase 2\)/)).toBeDefined();
  await user.click(screen.getByRole("button", { name: "Setujui protokol" }));
  const approveModal = within(await screen.findByRole("dialog", { name: "Setujui protokol" }));
  const form = approveModal.getByRole("button", { name: "Setujui protokol" }).closest("form") as HTMLFormElement;
  expect(approveModal.getByTestId("signature-signer").textContent).toBe("Dewi Lestari(dewi)");
  expect((form.elements.namedItem("submission_event_id") as HTMLInputElement).value).toBe("12");
  expect((form.elements.namedItem("hash") as HTMLInputElement).value).toBe("a".repeat(64));
  await user.click(approveModal.getByRole("button", { name: "Batal" }));

  await user.click(screen.getByRole("button", { name: "Kembalikan ke Draft" }));
  const modal = within(await screen.findByRole("dialog", { name: "Kembalikan protokol ke Draft?" }));
  const reason = modal.getByRole("textbox", { name: "Alasan pengembalian" }) as HTMLTextAreaElement;
  expect(reason.required).toBe(true);
  expect(modal.getByRole("button", { name: "Kembalikan ke Draft" })).toBeDefined();
});

test("the deciding role and a reader get no approve or return control", () => {
  const { unmount } = renderPage(submitted, decider);
  expect(screen.queryByRole("button", { name: "Setujui protokol" })).toBeNull();
  unmount();
  renderPage(submitted, reader);
  expect(screen.queryByRole("button", { name: "Kembalikan ke Draft" })).toBeNull();
});

test("an approved Protocol shows the approval as a recorded status and no controls", async () => {
  const user = userEvent.setup();
  renderForApprover(approved);
  expect(screen.getByText("Disetujui")).toBeDefined();
  expect(screen.getByText(/Disetujui: status yang dicatat .* bukan Tanda Tangan Elektronik/)).toBeDefined();
  expect(screen.getByTestId("copy-hash").textContent).toBe("a".repeat(64));
  expect(screen.queryByRole("button", { name: /Setujui|Kembalikan/ })).toBeNull();

  await user.click(screen.getByRole("tab", { name: "Riwayat & Salinan" }));
  expect(
    await screen.findByText("Disetujui oleh Dewi Anggraini Lestari, 19/11/2026 11.00 UTC"),
  ).toBeDefined();
});

test("a returned Protocol reads live again and lists its earlier copy with the reason", async () => {
  const user = userEvent.setup();
  renderForApprover(returned);
  expect(screen.getByText("Draft")).toBeDefined();
  expect(screen.getByRole("region", { name: "Baris protokol" })).toBeDefined();
  expect(screen.queryByRole("button", { name: "Setujui protokol" })).toBeNull();

  await user.click(screen.getByRole("tab", { name: "Riwayat & Salinan" }));
  const earlier = within(await screen.findByTestId("earlier-12"));
  expect(earlier.getByText("a".repeat(64))).toBeDefined();
  expect(
    earlier.getByText("Dikembalikan ke Draft oleh Dewi Anggraini Lestari, 19/11/2026 11.00 UTC"),
  ).toBeDefined();
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

test("protocol useActionState forms preserve typed inputs when inline action returns error (422/409)", async () => {
  const user = userEvent.setup();
  const base = protocolView();
  const baseRows = base.rows ?? [];
  const rowNeedWrite = baseRows.find((r) => r.requirement === "URS-TP201-002")!;
  const view: ProtocolView = {
    ...base,
    rows: [
      { ...rowNeedWrite, kind: "test_step", test_step: null },
      ...baseRows.filter((r) => r.requirement !== "URS-TP201-002"),
    ],
  };

  const c: ProtocolControls = {
    ...controls,
    writeInline: vi.fn(async () => ({ ok: false as const, error: "refused" as const })),
    editInline: vi.fn(async () => ({ ok: false as const, error: "refused" as const })),
    answerInline: vi.fn(async () => ({ ok: false as const, error: "refused" as const })),
  };

  render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <RunShellProvider>
        <AssembledProtocolView protocol={view} runId={RUN_ID} decisions={decider} controls={c} />
      </RunShellProvider>
    </NextIntlClientProvider>,
  );

  // 1. WriteForm preserves description on 422/409
  await user.click(screen.getByRole("button", { name: "URS-TP201-002" }));
  const writeDialog = await screen.findByRole("dialog");
  const writeForm = within(within(writeDialog).getByRole("form", { name: "Tulis langkah uji" }));
  const descInput = writeForm.getByLabelText("Deskripsi");
  await user.clear(descInput);
  await user.type(descInput, "Langkah uji baru yang belum tersimpan");
  const methodInput = writeForm.getByLabelText("Metode");
  await user.clear(methodInput);
  await user.type(methodInput, "Inspeksi visual");
  const acShape = writeForm.getByLabelText("Bentuk");
  await user.selectOptions(acShape, "present");
  await user.click(writeForm.getByRole("button", { name: "Simpan versi" }));

  expect(await within(writeDialog).findByRole("alert")).toBeDefined();
  expect((writeForm.getByLabelText("Deskripsi") as HTMLTextAreaElement).value).toBe(
    "Langkah uji baru yang belum tersimpan",
  );

  // 2. EditDraftForm preserves Reason for Change on 422/409 (also present on URS-TP201-002)
  const reasonInput = within(writeDialog).getByLabelText("Alasan perubahan");
  await user.type(reasonInput, "Alasan koreksi yang harus tetap ada");
  await user.click(within(writeDialog).getByRole("button", { name: "Simpan suntingan" }));

  await waitFor(() => {
    expect(within(writeDialog).getAllByRole("alert")).toHaveLength(2);
  });
  expect((within(writeDialog).getByLabelText("Alasan perubahan") as HTMLTextAreaElement).value).toBe(
    "Alasan koreksi yang harus tetap ada",
  );

  // 3. MissedNumbers AnswerForm preserves justification on 422/409
  await user.click(within(writeDialog).getByRole("button", { name: "Tutup panel" }));
  const discardBtn = within(writeDialog).queryByRole("button", { name: /Buang/i });
  if (discardBtn) await user.click(discardBtn);
  await user.click(await screen.findByRole("tab", { name: /Nomor terlewat/i }));
  const missedCard = within(await screen.findByTestId("URS-TP201/0/URS-TP201-004"));
  await user.selectOptions(missedCard.getByLabelText("Jawaban"), "not_a_requirement");
  await user.type(missedCard.getByLabelText("Justifikasi"), "Justifikasi nomor terlewat tetap terjaga");
  await user.click(missedCard.getByRole("button", { name: "Simpan jawaban" }));

  expect(await missedCard.findByRole("alert")).toBeDefined();
  expect((missedCard.getByLabelText("Justifikasi") as HTMLTextAreaElement).value).toBe(
    "Justifikasi nomor terlewat tetap terjaga",
  );
});

test("ProtocolRowDrawer shows stage and witness_required controls when updateAttributesInline is provided", async () => {
  const user = userEvent.setup();
  const updateAttributesInline = vi.fn(async () => ({ ok: true, submittedAt: Date.now() }));
  render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <RunShellProvider>
        <AssembledProtocolView
          protocol={protocolView()}
          runId={RUN_ID}
          decisions={decider}
          controls={{ ...controls, updateAttributesInline }}
        />
      </RunShellProvider>
    </NextIntlClientProvider>,
  );

  const dialog = await openRowDrawer(user, "URS-TP201-002");
  const stageSelect = dialog.getByLabelText("Tahap Kualifikasi") as HTMLSelectElement;
  await user.selectOptions(stageSelect, "IQ");
  const witnessCheckbox = dialog.getByLabelText("Wajib konfirmasi Saksi") as HTMLInputElement;
  await user.click(witnessCheckbox);
  await user.click(dialog.getByRole("button", { name: "Simpan atribut" }));

  await waitFor(() => {
    expect(updateAttributesInline).toHaveBeenCalledTimes(1);
  });
});

// --- A failed signing must tell the signer (issue #348) -----------------------------------

function pageFor(
  protocol: ProtocolView,
  props: { decisions: DecisionView; error?: ProtocolError; asApprover?: boolean },
) {
  return (
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <RunShellProvider>
        <AssembledProtocolView
          protocol={protocol}
          runId={RUN_ID}
          decisions={props.decisions}
          controls={props.decisions.access.mode === "decide" ? controls : null}
          approval={props.asApprover ? approvalControls : null}
          signingAuth={SIGNING_AUTH}
          error={props.error}
        />
      </RunShellProvider>
    </NextIntlClientProvider>
  );
}

test("a stale-draft conflict closes the submit dialog and moves focus to the page alert", async () => {
  const user = userEvent.setup();
  const protocol = protocolView({ checklist: ready });
  const { rerender } = render(pageFor(protocol, { decisions: decider }));
  await user.click(screen.getByRole("button", { name: "Ajukan protokol" }));
  await screen.findByRole("dialog", { name: "Ajukan protokol untuk persetujuan?" });

  rerender(pageFor(protocol, { decisions: decider, error: "conflict" }));

  expect(screen.queryByRole("dialog")).toBeNull();
  const alert = screen.getByRole("alert");
  expect(alert.textContent).toContain("muat ulang dan periksa lagi");
  await waitFor(() => expect(document.activeElement).toBe(alert));
});

test("reopening the dialog while the conflict is unresolved shows it inside the dialog", async () => {
  const user = userEvent.setup();
  const protocol = protocolView({ checklist: ready });
  const { rerender } = render(pageFor(protocol, { decisions: decider }));
  await user.click(screen.getByRole("button", { name: "Ajukan protokol" }));
  await screen.findByRole("dialog");
  rerender(pageFor(protocol, { decisions: decider, error: "conflict" }));
  await user.click(screen.getByRole("button", { name: "Ajukan protokol" }));
  const dialog = within(await screen.findByRole("dialog"));
  expect(dialog.getByRole("alert").textContent).toContain("muat ulang dan periksa lagi");
});

test("a failed approval closes the approve dialog and shows the alert", async () => {
  const user = userEvent.setup();
  const { rerender } = render(pageFor(submitted, { decisions: reader, asApprover: true }));
  await user.click(screen.getByRole("button", { name: "Setujui protokol" }));
  await screen.findByRole("dialog", { name: "Setujui protokol" });
  rerender(pageFor(submitted, { decisions: reader, asApprover: true, error: "forbidden" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByRole("alert").textContent).toContain("tidak memiliki peran");
});

test("a reauth_required error keeps the dialog open and shows it inside", async () => {
  const user = userEvent.setup();
  const protocol = protocolView({ checklist: ready });
  const { rerender } = render(pageFor(protocol, { decisions: decider }));
  await user.click(screen.getByRole("button", { name: "Ajukan protokol" }));
  await screen.findByRole("dialog");
  rerender(pageFor(protocol, { decisions: decider, error: "reauth_required" }));
  const dialog = within(screen.getByRole("dialog"));
  expect(dialog.getByRole("alert").textContent).toContain("Autentikasi ulang diperlukan");
});

test("J/K shortcuts do nothing while a modal dialog is open (#349)", () => {
  renderPage(protocolView());
  const button = openBlockingModal();
  fireEvent.keyDown(button, { key: "j" });
  fireEvent.keyDown(button, { key: "k" });
  expect(openDialogCount()).toBe(1);
  expect(document.activeElement).toBe(button);
});
