// The matrix screen over the fixture run folder the API contract tests use (spec #29),
// Proposal Decisions (spec #105, K1-K5, K8-K10, K15), and Opsi A Drawer + shortcuts (#284).
import { fireEvent, render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { vi } from "vitest";

import type { Matrix } from "@/api/client";
import type { DecideActionState } from "@/decisions/actions";
import messages from "../../messages/id.json";
import fixture from "../../../tests/fixtures/run/runs/20261113T090000Z-f1a2b3/matrix.json";
import type { DecisionView } from "./Decisions";
import { counts, decision, BIMA, RUN_ID } from "./decisions.fixture";
import { openBlockingModal, openDialogCount } from "./modal.fixture";
import { MatrixTable } from "./MatrixTable";
import { RunShellProvider, useRunShell } from "./RunShellContext";

const action = async () => {};

function DrawerSpy() {
  const { drawerOpen } = useRunShell();
  return <output data-testid="drawer-open-state">{String(drawerOpen)}</output>;
}

function renderMatrix(
  decisions: DecisionView = { access: { mode: "readOnly", why: "signedOut" } },
  initialSelected: string | null = null,
) {
  return render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <RunShellProvider>
        <DrawerSpy />
        <MatrixTable
          matrix={fixture as Matrix}
          runId={RUN_ID}
          decisions={decisions}
          initialSelected={initialSelected}
        />
      </RunShellProvider>
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
    previous_class: null,
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
    previous_class: "covered_by_vendor",
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
    previous_class: null,
  },
];

beforeEach(() => {
  window.history.replaceState(null, "", `/runs/${RUN_ID}`);
});

test("renders 4-column Opsi A table with button triggers, Required vs Observed, and opens Drawer", async () => {
  renderMatrix();

  expect(screen.getByRole("columnheader", { name: "Persyaratan" })).toBeDefined();
  expect(screen.getByRole("columnheader", { name: /Disyaratkan \/ Teramati/ })).toBeDefined();
  expect(screen.getByRole("columnheader", { name: "Cakupan" })).toBeDefined();
  expect(screen.getByRole("columnheader", { name: "Keputusan" })).toBeDefined();

  const speedRow = screen.getByRole("row", { name: /URS-TP201-002/ });
  expect(within(speedRow).getByText("Sebagian")).toBeDefined();
  expect(within(speedRow).getByText("20–70 rpm")).toBeDefined();
  // Stage prefix deduplicated: FAT-M-02, never "FAT FAT-M-02"
  expect(within(speedRow).getByText(/FAT-M-02 · 20–60 rpm/)).toBeDefined();

  const powerRow = screen.getByRole("row", { name: /URS-TP201-026/ });
  expect(within(powerRow).getByText("Hanya di lokasi")).toBeDefined();
  expect(within(powerRow).getByText("Tidak ada bukti vendor")).toBeDefined();

  const unassessedRow = screen.getByRole("row", { name: /URS-TP201-030/ });
  expect(within(unassessedRow).getByText("Belum dinilai")).toBeDefined();
  expect(within(unassessedRow).getByText("Tidak ada nilai terverifikasi")).toBeDefined();

  // matrix.not_read panel preserved
  expect(screen.getByRole("heading", { name: "Dokumen vendor yang tidak terbaca" })).toBeDefined();
  expect(screen.getByText("SAT-TP201 rev 0 (scan)")).toBeDefined();

  // Clicking primary ID button opens Drawer and wires RunShellContext + URL
  expect(screen.getByTestId("drawer-open-state").textContent).toBe("false");
  fireEvent.click(screen.getByRole("button", { name: "URS-TP201-002" }));

  const dialog = await screen.findByRole("dialog", { name: "URS-TP201-002" });
  expect(screen.getByTestId("drawer-open-state").textContent).toBe("true");
  expect(window.location.search).toContain("selected=URS-TP201-002");

  expect(within(dialog).getByText(/FAT-M-02: result does not meet the URS/)).toBeDefined();
  expect(within(dialog).getByRole("button", { name: "FAT-TP201-M rev 0, hlm. 1" })).toBeDefined();
  expect(within(dialog).getByRole("button", { name: "DS-TP201 rev 0, hlm. 1" })).toBeDefined();
});

test("an imported run shows each row's decision state, prior decisions (K15), and decision forms in Drawer", async () => {
  renderMatrix({ proposals, counts, access: { mode: "decide", action } });

  expect(screen.queryByText(/Hanya membaca:/)).toBeNull();

  // Open URS-TP201-002 (decided, with prior decision by Bima for K15)
  fireEvent.click(screen.getByRole("button", { name: "URS-TP201-002" }));
  let dialog = await screen.findByRole("dialog", { name: "URS-TP201-002" });
  expect(within(dialog).getByText("Sudah diputuskan")).toBeDefined();
  expect(
    within(dialog).getByText("Diubah ke Celah oleh Ayu Kartika Sari, 16/11/2026 17.15 WIB"),
  ).toBeDefined();
  expect(within(dialog).getByText("Rentang FAT tidak mencakup 70 rpm")).toBeDefined();
  expect(within(dialog).getByText("Keputusan sebelumnya atas isi ini:")).toBeDefined();
  expect(
    within(dialog).getByText("Diterima oleh Bima Arya Nugraha, 16/11/2026 16.30 WIB"),
  ).toBeDefined();

  // Replacing a decision on the same content uses a single form + single Reason for Change (K8, K15)
  fireEvent.click(within(dialog).getByRole("button", { name: "Putuskan ulang" }));
  expect(within(dialog).getAllByRole("textbox", { name: "Alasan perubahan" })).toHaveLength(1);
  const acceptForm = within(dialog).getByRole("button", { name: "Terima" }).closest("form")!;
  expect(within(acceptForm).getByRole("textbox").hasAttribute("required")).toBe(true);
  expect(within(dialog).queryByRole("button", { name: /setuju/i })).toBeNull();

  // Navigate to next row (URS-TP201-026, changed)
  fireEvent.click(within(dialog).getByRole("button", { name: "Berikutnya" }));
  dialog = await screen.findByRole("dialog", { name: "URS-TP201-026" });
  expect(within(dialog).getByText("Isi berubah")).toBeDefined();
  expect(
    within(dialog).getByText(
      "Keputusan sebelumnya, atas isi lain: Diterima oleh Bima Arya Nugraha, 16/11/2026 16.30 WIB",
    ),
  ).toBeDefined();
  expect(within(dialog).getByText("sebelumnya: Dicakup vendor")).toBeDefined();

  const acceptChanged = within(dialog).getByRole("button", { name: "Terima" }).closest("form")!;
  expect(within(acceptChanged).queryByRole("textbox")).toBeNull();
  fireEvent.click(within(dialog).getByRole("button", { name: "Ubah kelas…" }));
  const editForm = within(dialog).getByRole("button", { name: "Ubah kelas" }).closest("form")!;
  expect(within(editForm).getByRole("textbox").hasAttribute("required")).toBe(true);
  expect(within(editForm).getByRole("combobox").hasAttribute("required")).toBe(true);
  expect(within(editForm).getByRole("option", { name: "Celah" })).toBeDefined();

  // Navigate to next row (URS-TP201-030, undecided, no proposed coverage -> only edit)
  fireEvent.click(within(dialog).getByRole("button", { name: "Berikutnya" }));
  dialog = await screen.findByRole("dialog", { name: "URS-TP201-030" });
  expect(within(dialog).getByText("Belum diputuskan")).toBeDefined();
  expect(within(dialog).queryByRole("button", { name: "Terima" })).toBeNull();
  expect(within(dialog).getByRole("button", { name: "Ubah kelas" })).toBeDefined();
  expect(within(dialog).queryByText(/^sebelumnya:/)).toBeNull();

  // Close drawer, then check decision counts table (toggleable)
  fireEvent.click(within(dialog).getByRole("button", { name: "Tutup panel" }));
  fireEvent.click(screen.getByRole("button", { name: "Jumlah keputusan" }));
  const tally = within(screen.getByRole("table", { name: "Jumlah keputusan" }));
  const row = within(tally.getByRole("row", { name: /Baris cakupan/ }));
  expect(row.getAllByRole("cell").map((c) => c.textContent)).toEqual([
    "3",
    "1",
    "0",
    "1",
    "0",
    "1",
    "2",
  ]);
});

test("the decision counts show the drafted Test Steps beside the Coverage rows", () => {
  renderMatrix({ proposals, counts, access: { mode: "decide", action } });

  expect(screen.getByText("1/3 usulan sudah diputuskan")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Jumlah keputusan" }));
  const tally = within(screen.getByRole("table", { name: "Jumlah keputusan" }));
  const row = within(tally.getByRole("row", { name: /Langkah uji rancangan TraceQ/ }));
  expect(row.getAllByRole("cell").map((c) => c.textContent)).toEqual([
    "2",
    "1",
    "1",
    "0",
    "0",
    "0",
    "0",
  ]);
});

test("a viewer without the deciding role reads the decisions and cannot decide", async () => {
  renderMatrix({ proposals, counts, access: { mode: "readOnly", why: "noRole" } });

  expect(
    screen.getByText(/Hanya membaca: identitas ini tidak memiliki peran pengambil keputusan/),
  ).toBeDefined();
  const row = screen.getByRole("row", { name: /URS-TP201-002/ });
  expect(within(row).getByText("Diubah")).toBeDefined();

  fireEvent.click(screen.getByRole("button", { name: "URS-TP201-002" }));
  const dialog = await screen.findByRole("dialog", { name: "URS-TP201-002" });
  expect(within(dialog).queryByRole("button", { name: "Terima" })).toBeNull();
  expect(within(dialog).queryByRole("button", { name: "Ubah kelas" })).toBeNull();
});

test("a viewer who is not signed in sees the run read-only with what deciding needs", () => {
  renderMatrix({ access: { mode: "readOnly", why: "signedOut" } });

  expect(
    screen.getByText(/Hanya membaca: masuk sebagai orang dengan peran pengambil keputusan/),
  ).toBeDefined();
  expect(screen.queryByText("Belum diputuskan")).toBeNull();
  const table = within(screen.getByRole("table"));
  expect(table.queryByRole("button", { name: "Terima" })).toBeNull();
  expect(table.queryByRole("button", { name: "Ubah kelas" })).toBeNull();
  expect(screen.queryByRole("table", { name: "Jumlah keputusan" })).toBeNull();
});

test("useActionState preserves typed Reason for Change on 422/409 error and dirty-form guard protects navigation", async () => {
  const inlineAction = vi.fn(
    async (_prev: DecideActionState, form: FormData): Promise<DecideActionState> => ({
      ok: false,
      error: "refused",
      values: {
        decision: "edited",
        coverage: "gap",
        reason: String(form.get("reason") ?? ""),
      },
    }),
  );

  renderMatrix(
    { proposals, counts, access: { mode: "decide", action, inlineAction } },
    "URS-TP201-026",
  );

  const dialog = await screen.findByRole("dialog", { name: "URS-TP201-026" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Ubah kelas…" }));

  const select = within(dialog).getByRole("combobox", { name: "Pilih kelas cakupan" });
  fireEvent.change(select, { target: { value: "gap" } });
  const textarea = within(dialog).getByRole("textbox", { name: "Alasan perubahan" }) as HTMLTextAreaElement;
  fireEvent.change(textarea, { target: { value: "Alasan yang diketik pengguna" } });

  fireEvent.click(within(dialog).getByRole("button", { name: "Ubah kelas" }));
  const alert = await within(dialog).findByRole("alert");
  expect(alert.textContent).toContain("Keputusan ditolak API");
  expect(textarea.value).toBe("Alasan yang diketik pengguna");

  // Dirty-form guard blocks switching until confirmed
  fireEvent.click(within(dialog).getByRole("button", { name: "Berikutnya" }));
  const dirtyAlert = await within(dialog).findByRole("alertdialog");
  expect(within(dirtyAlert).getByText(/Alasan perubahan yang diketik belum disimpan/)).toBeDefined();

  fireEvent.click(within(dirtyAlert).getByRole("button", { name: "Buang perubahan" }));
  await screen.findByRole("dialog", { name: "URS-TP201-030" });
});

test("J/K keyboard shortcuts navigate rows and are disabled inside inputs/combos or with modifiers", async () => {
  renderMatrix({ proposals, counts, access: { mode: "decide", action } });

  // J opens first row
  fireEvent.keyDown(window, { key: "j" });
  await screen.findByRole("dialog", { name: "URS-TP201-002" });

  // J with Ctrl modifier is ignored
  fireEvent.keyDown(window, { key: "j", ctrlKey: true });
  expect(screen.getByRole("dialog", { name: "URS-TP201-002" })).toBeDefined();

  // J moves to second row
  fireEvent.keyDown(window, { key: "j" });
  await screen.findByRole("dialog", { name: "URS-TP201-026" });

  // K moves back to first row
  fireEvent.keyDown(window, { key: "k" });
  const firstDialog = await screen.findByRole("dialog", { name: "URS-TP201-002" });

  // J inside select/textarea is ignored
  fireEvent.click(within(firstDialog).getByRole("button", { name: "Putuskan ulang" }));
  fireEvent.click(within(firstDialog).getByRole("radio", { name: "Ubah kelas" }));
  const coverageSelect = within(firstDialog).getByRole("combobox", {
    name: "Pilih kelas cakupan",
  });
  fireEvent.keyDown(coverageSelect, { key: "j" });
  expect(screen.getByRole("dialog", { name: "URS-TP201-002" })).toBeDefined();
});

test("J/K shortcuts do nothing while a modal dialog is open (#349)", () => {
  renderMatrix({ proposals, counts, access: { mode: "decide", action } });
  const button = openBlockingModal();
  fireEvent.keyDown(button, { key: "j" });
  fireEvent.keyDown(button, { key: "k" });
  expect(openDialogCount()).toBe(1);
  expect(document.activeElement).toBe(button);
});
