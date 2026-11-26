// The Protocol Draft screen (Opsi A Compact Ordered Table + Slide-Over Drawer): Test Steps
// in sequential draft order, 1-click triage filters, Drawer with Prev/Next + useActionState +
// dirty-form guard, RunShellContext wiring, whole-document findings below, and non-link draft
// citations (K22).
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { vi } from "vitest";

import messages from "../../messages/id.json";
import type { DecisionView } from "./Decisions";
import { counts, decision, RUN_ID } from "./decisions.fixture";
import { openBlockingModal, openDialogCount } from "./modal.fixture";
import {
  deviates,
  draftView,
  notReadStep,
  notTested,
  outsideCapability,
  proposal,
  unitError,
} from "./protocolDraft.fixture";
import { ProtocolDraftView } from "./ProtocolDraftView";
import { RunShellProvider, useRunShell } from "./RunShellContext";

const action = async () => {};
const readOnly: DecisionView = { access: { mode: "readOnly", why: "noRole" } };

function DrawerObserver() {
  const { drawerOpen } = useRunShell();
  return <div data-testid="shell-drawer-open">{drawerOpen ? "open" : "closed"}</div>;
}

function renderDraft(view = draftView([]), decisions: DecisionView = readOnly) {
  return render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <RunShellProvider>
        <DrawerObserver />
        <ProtocolDraftView draft={view} runId={RUN_ID} decisions={decisions} />
      </RunShellProvider>
    </NextIntlClientProvider>,
  );
}

const imported = draftView([
  { finding: deviates, proposal: proposal({ id: 40, position: 0 }) },
  {
    finding: notTested,
    proposal: proposal({ id: 41, position: 1, state: "decided", decisions: [decision({ id: 9 })] }),
  },
]);

function stepRows() {
  const steps = within(screen.getByRole("region", { name: "Langkah uji" }));
  return steps.getAllByRole("row").slice(1);
}

test("lists every Test Step in draft order with non-link draft citations and opens Drawer for full URS/comparators", async () => {
  renderDraft(imported);

  expect(screen.getByText("OQ-TP201 rev 0, paket tinjauan TP-201-OQ-draft")).toBeDefined();
  expect(screen.getByText(/dirancang TraceQ sendiri tidak ditampilkan/)).toBeDefined();
  const rows = stepRows();
  expect(
    rows.map((r) => within(within(r).getByRole("rowheader")).getByRole("button").textContent),
  ).toEqual(["OQ-01", "OQ-02", "OQ-03"]);

  const first = within(rows[0]!);
  expect(first.getByText("minimal 100 kN")).toBeDefined();
  expect(first.getByText("URS-TP201-001")).toBeDefined();
  expect(first.getByText("≥ 100 kN")).toBeDefined();
  // K22: draft citation is a tooltip span, never a link
  const ac = first.getByText("OQ-TP201 rev 0, hlm. 1");
  expect(ac.closest("a")).toBeNull();
  expect(ac.getAttribute("title")).toBe("OQ-01 Gaya kompresi minimal 100 kN");
  expect(first.getByText("Sesuai URS")).toBeDefined();
  expect(first.getByText("Tidak ada temuan")).toBeDefined();

  // Open OQ-01 in Drawer and verify URS + comparator citation buttons and RunShellContext wiring
  expect(screen.getByTestId("shell-drawer-open").textContent).toBe("closed");
  fireEvent.click(first.getByRole("button", { name: "OQ-01" }));
  expect(screen.getByTestId("shell-drawer-open").textContent).toBe("open");

  const dialog = await screen.findByRole("dialog", { name: "OQ-01" });
  const ursBtn = within(dialog).getByRole("button", { name: "URS-TP201 rev 1, hlm. 1" });
  expect(ursBtn.getAttribute("title")).toBe("Gaya kompresi minimal 100 kN.");
  expect(within(dialog).getByRole("button", { name: "FAT-TP201-M rev 0, hlm. 1" })).toBeDefined();
});

test("shows, per vendor document, the facts for the step's requirement or none", () => {
  renderDraft(imported);
  const [first, second] = stepRows();
  const docs = (row: HTMLElement) =>
    Array.from(row.querySelectorAll("[data-vendor-doc]")).map((li) => li.textContent);
  expect(docs(first!)).toEqual([
    "Datasheet DS-TP201: tidak ada",
    expect.stringMatching(/^FAT FAT-TP201-M: FAT-M-02: 102 kN/),
    "SAT SAT-TP201: tidak ada",
  ]);
  expect(docs(second!)).toEqual([
    "Datasheet DS-TP201: tidak ada",
    "FAT FAT-TP201-M: tidak ada",
    "SAT SAT-TP201: tidak ada",
  ]);
});

test("a Test Step whose reading was dropped is listed in draft order and filterable via Tidak terbaca", () => {
  const view = draftView([]);
  const [one, ...rest] = view.test_steps;
  renderDraft({ ...view, test_steps: [one!, notReadStep, ...rest] });

  const rows = stepRows();
  expect(
    rows.map((r) => within(within(r).getByRole("rowheader")).getByRole("button").textContent),
  ).toEqual(["OQ-01", "OQ-02A", "OQ-02", "OQ-03"]);
  const unread = within(rows[1]!);
  expect(
    unread.getByText("Tidak terbaca: bacaannya dibuang oleh pemeriksaan kutipan (quote check)"),
  ).toBeDefined();
  expect(unread.queryByText("Tidak ada temuan")).toBeNull();

  // 1-click triage filter chips
  expect(screen.getByRole("button", { name: /Semua\s*4/ })).toBeDefined();
  expect(screen.getByRole("button", { name: /Tidak terbaca\s*1/ })).toBeDefined();
  expect(screen.getByRole("button", { name: /Tidak dibandingkan\s*1/ })).toBeDefined();

  fireEvent.click(screen.getByRole("button", { name: /Tidak terbaca/ }));
  expect(stepRows().map((r) => within(r).getByRole("button").textContent)).toEqual(["OQ-02A"]);
});

test("a step that is not compared says so with the reason, and has no finding", () => {
  renderDraft(imported);
  const second = within(stepRows()[1]!);
  expect(second.getByText("Tidak dibandingkan: two-sided URS range")).toBeDefined();
  expect(second.queryByText("Menyimpang dari URS")).toBeNull();
});

test("a finding sits on its Test Step, and document-level findings sit below the steps", () => {
  renderDraft(imported);
  const third = within(stepRows()[2]!);
  expect(third.getByText("Menyimpang dari URS")).toBeDefined();
  expect(third.getByText("Kriteria penerimaan lebih longgar dari URS")).toBeDefined();
  expect(third.getByText("Belum diputuskan")).toBeDefined();

  const doc = within(screen.getByRole("region", { name: "Temuan tentang seluruh dokumen" }));
  expect(doc.getByText("Persyaratan tanpa langkah uji")).toBeDefined();
  expect(doc.getByText("URS-TP201-031")).toBeDefined();
  expect(doc.getByText(notTested.detail)).toBeDefined();
  expect(doc.getByText("Diterima oleh Ayu Kartika Sari, 16/11/2026 09.30 UTC")).toBeDefined();
  expect(doc.getByText("OQ-TP201 rev 0, hlm. 8").getAttribute("title")).toBe("URS-TP201-031 OQ-21");

  // Document order: the steps come before the findings about the whole document.
  const steps = screen.getByRole("region", { name: "Langkah uji" });
  const whole = screen.getByRole("region", { name: "Temuan tentang seluruh dokumen" });
  expect(steps.compareDocumentPosition(whole) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test("Drawer Prev/Next, useActionState accept/reject, and dirty-form guard work on draft findings", async () => {
  const inlineAction = vi.fn().mockResolvedValue({
    ok: false,
    error: "conflict",
    values: { decision: "rejected", reason: "Periksa ulang" },
  });
  renderDraft(imported, {
    counts: { ...counts, draft: { ...counts.draft, total: 2, undecided: 1, accepted: 1 } },
    access: { mode: "decide", action, inlineAction },
  });

  fireEvent.click(screen.getByRole("button", { name: "OQ-03" }));
  const dialog = await screen.findByRole("dialog", { name: "OQ-03" });
  expect(within(dialog).getByText(deviates.detail)).toBeDefined();

  const accept = within(dialog).getByRole("button", { name: "Terima" }).closest("form")!;
  expect(within(accept).queryByRole("textbox")).toBeNull();
  expect(accept.querySelector('input[name="screen"]')?.getAttribute("value")).toBe("draft");
  expect(accept.querySelector('input[name="proposal_id"]')?.getAttribute("value")).toBe("40");

  fireEvent.click(within(dialog).getByRole("button", { name: "Tolak…" }));
  const reasonBox = within(dialog).getByRole("textbox", {
    name: "Alasan perubahan",
  }) as HTMLTextAreaElement;
  expect(reasonBox.hasAttribute("required")).toBe(true);
  fireEvent.change(reasonBox, { target: { value: "Periksa ulang" } });
  fireEvent.submit(reasonBox.closest("form")!);

  await waitFor(() => {
    expect(within(dialog).getByRole("alert")).toBeDefined();
  });
  expect(
    (within(dialog).getByRole("textbox", { name: "Alasan perubahan" }) as HTMLTextAreaElement)
      .value,
  ).toBe("Periksa ulang");

  // Dirty-form guard blocks Prev navigation until discarded
  fireEvent.click(within(dialog).getByRole("button", { name: "Sebelumnya" }));
  expect(
    within(dialog).getByRole("alertdialog", {
      name: "Anda memiliki perubahan yang belum disimpan. Buang perubahan?",
    }),
  ).toBeDefined();
  fireEvent.click(within(dialog).getByRole("button", { name: "Buang perubahan" }));
  expect(await screen.findByRole("dialog", { name: "OQ-02" })).toBeDefined();

  // Close drawer so background regions/counts are visible again
  fireEvent.click(within(screen.getByRole("dialog", { name: "OQ-02" })).getByRole("button", { name: "Tutup panel" }));

  // Decision counts
  expect(screen.getByText("1/2 usulan sudah diputuskan")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Jumlah keputusan" }));
  const tally = within(screen.getByRole("table", { name: "Jumlah keputusan" }));
  expect(tally.getByRole("row", { name: /Temuan draf protokol/ })).toBeDefined();
  expect(tally.queryByRole("row", { name: /Baris cakupan/ })).toBeNull();
});

test("a reader sees the decisions and no decision control", () => {
  renderDraft(imported);
  expect(screen.getByText("Diterima oleh Ayu Kartika Sari, 16/11/2026 09.30 UTC")).toBeDefined();
  expect(screen.queryByRole("button", { name: /Terima|Tolak/ })).toBeNull();
  expect(screen.queryByText("Tolak…")).toBeNull();
  expect(screen.getByText(/Hanya membaca: identitas ini tidak memiliki peran/)).toBeDefined();
});

test("a run not imported shows the findings without decision state", async () => {
  renderDraft(draftView([{ finding: deviates, proposal: null }]), {
    access: { mode: "readOnly", why: "notImported" },
  });
  const doc = within(screen.getByRole("region", { name: "Temuan tentang seluruh dokumen" }));
  expect(doc.getByText("Tidak ada temuan tentang seluruh dokumen")).toBeDefined();

  fireEvent.click(screen.getByRole("button", { name: "OQ-03" }));
  const dialog = await screen.findByRole("dialog", { name: "OQ-03" });
  expect(within(dialog).getByText(deviates.detail)).toBeDefined();
  expect(within(dialog).queryByText("Belum diputuskan")).toBeNull();
});

test("J/K shortcuts do nothing while a modal dialog is open (#349)", () => {
  renderDraft(imported);
  const button = openBlockingModal();
  fireEvent.keyDown(button, { key: "j" });
  fireEvent.keyDown(button, { key: "k" });
  expect(openDialogCount()).toBe(1);
  expect(document.activeElement).toBe(button);
});

test("a finding of a type no practitioner has reviewed carries its label in the table and the Drawer", async () => {
  renderDraft(draftView([{ finding: outsideCapability, proposal: null }]), {
    access: { mode: "readOnly", why: "notImported" },
  });
  const row = within(stepRows()[2]!);
  expect(row.getByText("Kriteria penerimaan di luar kemampuan yang tercantum di datasheet")).toBeDefined();
  expect(row.getByText("Belum ditinjau praktisi")).toBeDefined();

  fireEvent.click(row.getByRole("button", { name: "OQ-03" }));
  const dialog = await screen.findByRole("dialog", { name: "OQ-03" });
  expect(within(dialog).getByText("Belum ditinjau praktisi")).toBeDefined();
  expect(within(dialog).getByText(outsideCapability.detail)).toBeDefined();
});

test("a unit error is named and labelled as not reviewed by a practitioner", () => {
  renderDraft(draftView([{ finding: unitError, proposal: null }]), {
    access: { mode: "readOnly", why: "notImported" },
  });
  const row = within(stepRows()[2]!);
  expect(row.getByText("Satuan kriteria penerimaan salah")).toBeDefined();
  expect(row.getByText("Belum ditinjau praktisi")).toBeDefined();
});

test("a finding of a reviewed type carries no such label", () => {
  renderDraft(draftView([{ finding: deviates, proposal: null }]), {
    access: { mode: "readOnly", why: "notImported" },
  });
  expect(screen.queryByText("Belum ditinjau praktisi")).toBeNull();
});
