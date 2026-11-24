// The Pre-review screen (Opsi B Grouped Split-Pane): Check Findings (deterministic rules),
// AI Findings (advisory-only), Missing Documents tab, 1-click triage filters, PdfCitationModal
// (including .xlsx fallback), and useActionState decision workspace with dirty-form guard.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { vi } from "vitest";

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

afterEach(() => {
  vi.restoreAllMocks();
});

test("renders Check Findings and AI Findings in grouped split-pane, and Missing Documents in its tab", () => {
  renderFindings();

  const check = within(screen.getByRole("region", { name: "Temuan pemeriksaan (aturan)" }));
  expect(check.getByRole("button", { name: /Di luar batas namun ditandai Lulus/ })).toBeDefined();
  expect(check.getByRole("button", { name: /Protokol vendor belum disetujui/ })).toBeDefined();

  const ai = within(screen.getByRole("region", { name: "Temuan AI (saran)" }));
  expect(ai.getByRole("button", { name: /Data tidak konsisten/ })).toBeDefined();
  expect(ai.getByText("Menunggu tinjauan")).toBeDefined();
  expect(ai.getByText(/claude-haiku-5-5/)).toBeDefined();

  // First item is selected in the right inspection workspace by default
  const detail = within(screen.getByRole("region", { name: "Rincian" }));
  expect(detail.getByRole("heading", { name: "Di luar batas namun ditandai Lulus" })).toBeDefined();
  const limitBtn = detail.getByRole("button", { name: "FAT-TP201-M rev 0, hlm. 1" });
  expect(limitBtn.getAttribute("title")).toBe("FAT-M-04 Noise level <= 50 dB(A) 52 dB(A) Pass");

  // Second check finding has SOP-VAL-002 rule citation
  fireEvent.click(check.getByRole("button", { name: /Protokol vendor belum disetujui/ }));
  expect(detail.getByRole("button", { name: "SOP-VAL-002 rev 0, hlm. 1" })).toBeDefined();

  // Clicking the AI finding switches the right workspace to advisory AI metadata
  fireEvent.click(ai.getByRole("button", { name: /Data tidak konsisten/ }));
  expect(detail.getByRole("heading", { name: "Data tidak konsisten" })).toBeDefined();
  expect(detail.getByText(/claude-haiku-5-5/)).toBeDefined();
  expect(detail.getByRole("button", { name: "DS-TP201 rev 0, hlm. 1" })).toBeDefined();

  // Missing documents live in their own read-only tab
  const missingTab = screen.getByRole("tab", { name: /Dokumen yang tidak ada/ });
  fireEvent.mouseDown(missingTab);
  fireEvent.click(missingTab);
  const missing = within(screen.getByRole("region", { name: "Dokumen yang tidak ada" }));
  expect(missing.getByText("IQ-TP201")).toBeDefined();
  expect(missing.getByText("OQ-TP201")).toBeDefined();
  const cited = missing.getAllByRole("button", { name: "VMP-001 rev 0, hlm. 2" });
  expect(cited.map((b) => b.getAttribute("title"))).toEqual([
    "IQ-TP201 Protokol IQ IQ",
    "OQ-TP201 Protokol OQ OQ",
  ]);
  expect(missing.queryByRole("button", { name: /Terima|Tolak/ })).toBeNull();
});

test("1-click triage filters narrow the master list between Semua, Belum diputuskan, Aturan, and AI", () => {
  renderFindings({ proposals, counts, access: { mode: "decide", action } });

  expect(screen.getByRole("region", { name: "Temuan pemeriksaan (aturan)" })).toBeDefined();
  expect(screen.getByRole("region", { name: "Temuan AI (saran)" })).toBeDefined();

  fireEvent.click(screen.getByRole("button", { name: /^Belum diputuskan\s*\d+$/ }));
  const checkUndecided = within(screen.getByRole("region", { name: "Temuan pemeriksaan (aturan)" }));
  expect(checkUndecided.queryByRole("button", { name: /Di luar batas/ })).toBeNull();
  const aiUndecided = within(screen.getByRole("region", { name: "Temuan AI (saran)" }));
  expect(aiUndecided.getByRole("button", { name: /Data tidak konsisten/ })).toBeDefined();

  fireEvent.click(screen.getByRole("button", { name: /^Aturan\s*\d+$/ }));
  expect(screen.getByRole("region", { name: "Temuan pemeriksaan (aturan)" })).toBeDefined();
  expect(screen.queryByRole("region", { name: "Temuan AI (saran)" })).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: /^AI\s*\d+$/ }));
  expect(screen.queryByRole("region", { name: "Temuan pemeriksaan (aturan)" })).toBeNull();
  expect(screen.getByRole("region", { name: "Temuan AI (saran)" })).toBeDefined();
});

test("an imported run shows each finding's decision state, inline decision forms, and counts", () => {
  renderFindings({ proposals, counts, access: { mode: "decide", action } });

  const check = within(screen.getByRole("region", { name: "Temuan pemeriksaan (aturan)" }));
  fireEvent.click(check.getByRole("button", { name: /Di luar batas namun ditandai Lulus/ }));

  const detail = within(screen.getByRole("region", { name: "Rincian" }));
  expect(detail.getByText("Sudah diputuskan")).toBeDefined();
  expect(detail.getByText("Diterima oleh Ayu Kartika Sari, 16/11/2026 09.30 UTC")).toBeDefined();

  fireEvent.click(check.getByRole("button", { name: /Protokol vendor belum disetujui/ }));
  expect(detail.getByText("Ditolak oleh Bima Arya Nugraha, 16/11/2026 09.30 UTC")).toBeDefined();
  expect(detail.getByText("Protokol disetujui di halaman 2")).toBeDefined();

  const ai = within(screen.getByRole("region", { name: "Temuan AI (saran)" }));
  fireEvent.click(ai.getByRole("button", { name: /Data tidak konsisten/ }));
  expect(detail.queryByText("Menunggu tinjauan")).toBeNull();
  expect(detail.getByText("Belum diputuskan")).toBeDefined();

  // Accepting a first decision needs no reason; rejecting always does.
  const accept = detail.getByRole("button", { name: "Terima" }).closest("form")!;
  expect(within(accept).queryByRole("textbox")).toBeNull();
  fireEvent.click(detail.getByRole("button", { name: "Tolak…" }));
  const reject = detail.getByRole("button", { name: "Tolak" }).closest("form")!;
  expect(within(reject).getByRole("textbox").hasAttribute("required")).toBe(true);

  // Counts accordion
  fireEvent.click(screen.getByRole("button", { name: "Jumlah keputusan" }));
  const tally = within(screen.getByRole("table", { name: "Jumlah keputusan" }));
  const row = (name: RegExp) =>
    within(tally.getByRole("row", { name })).getAllByRole("cell").map((c) => c.textContent);
  expect(row(/Temuan pemeriksaan/)).toEqual(["2", "0", "1", "0", "1", "0", "0"]);
  expect(row(/Temuan AI/)).toEqual(["1", "1", "0", "0", "0", "0", "0"]);
});

test("useActionState preserves typed Reason for Change on 422/409 and dirty-form guard blocks switching", async () => {
  const inlineAction = vi.fn().mockResolvedValue({
    ok: false,
    error: "refused",
    values: { decision: "rejected", reason: "Alasan saya" },
  });
  renderFindings({ proposals, counts, access: { mode: "decide", action, inlineAction } });

  const ai = within(screen.getByRole("region", { name: "Temuan AI (saran)" }));
  fireEvent.click(ai.getByRole("button", { name: /Data tidak konsisten/ }));

  const detail = within(screen.getByRole("region", { name: "Rincian" }));
  fireEvent.click(detail.getByRole("button", { name: "Tolak…" }));
  const reasonBox = detail.getByRole("textbox", { name: "Alasan perubahan" }) as HTMLTextAreaElement;
  fireEvent.change(reasonBox, { target: { value: "Alasan saya" } });
  fireEvent.submit(reasonBox.closest("form")!);

  await waitFor(() => {
    expect(detail.getByRole("alert")).toBeDefined();
  });
  expect((detail.getByRole("textbox", { name: "Alasan perubahan" }) as HTMLTextAreaElement).value).toBe(
    "Alasan saya",
  );

  // Dirty-form guard when switching items
  const check = within(screen.getByRole("region", { name: "Temuan pemeriksaan (aturan)" }));
  fireEvent.click(check.getByRole("button", { name: /Di luar batas/ }));
  expect(
    detail.getByRole("alertdialog", {
      name: "Anda memiliki perubahan yang belum disimpan. Buang perubahan?",
    }),
  ).toBeDefined();
});

test("PdfCitationModal opens .xlsx fallback card for RA-TP201", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(null, {
      status: 200,
      headers: {
        "content-type":
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      },
    }),
  );
  const base = fixture as Findings;
  const withXlsx: Findings = {
    ...base,
    check_findings: [
      {
        ...base.check_findings[0]!,
        citations: [{ doc: "RA-TP201", rev: 0, page: 1, quote: "Risiko kompresi" }],
      },
    ],
  };
  render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <FindingsView
        findings={withXlsx}
        runId={RUN_ID}
        decisions={{ access: { mode: "readOnly", why: "signedOut" } }}
      />
    </NextIntlClientProvider>,
  );

  const detail = within(screen.getByRole("region", { name: "Rincian" }));
  fireEvent.click(detail.getByRole("button", { name: "RA-TP201 rev 0, hlm. 1" }));
  const dialog = await screen.findByRole("dialog", { name: /RA-TP201 rev 0, hlm\. 1/ });
  await waitFor(() => {
    expect(within(dialog).getByRole("link", { name: "Buka / Unduh dokumen" })).toBeDefined();
  });
});

test("a run that is not imported shows read-only with pending and what deciding needs", () => {
  renderFindings({ access: { mode: "readOnly", why: "notImported" } });

  expect(screen.getByText(/Hanya membaca: run ini belum diimpor/)).toBeDefined();
  const ai = within(screen.getByRole("region", { name: "Temuan AI (saran)" }));
  expect(ai.getByText("Menunggu tinjauan")).toBeDefined();
  expect(screen.queryByRole("button", { name: /Terima|Tolak/ })).toBeNull();
});
