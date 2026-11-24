import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { ExecutionView, ProtocolView } from "@/api/client";
import messages from "../../messages/id.json";
import { RUN_ID } from "./decisions.fixture";
import { ExecutionViewPanel } from "./ExecutionView";
import { approved, protocolView } from "./protocol.fixture";

const startAction = async () => ({ ok: true });

function executionFixture(): ExecutionView {
  return {
    id: 12,
    protocol_id: 7,
    equipment: "TP-201",
    run_id: RUN_ID,
    submission_event_id: 19,
    submission_hash: "a".repeat(64),
    status: "in_progress",
    events: [
      {
        id: 1,
        event: "started",
        status: "in_progress",
        subject: "demo-0001",
        issuer: "http://127.0.0.1:9000",
        name: "Ayu Kartika Sari",
        at: "2026-11-24T10:00:00Z",
      },
    ],
    rows: [
      {
        requirement: "URS-TP201-002",
        text: "Kecepatan turret dapat diatur 20–70 rpm.",
        source: { doc: "URS-TP201", rev: 0, page: 1, quote: "20–70 rpm" },
        kind: "test_step",
        evidence: [],
        test_step: {
          origin: "accepted_draft",
          description: "Verifikasi rentang kecepatan turret.",
          method: "Atur turret ke 20 dan 70 rpm.",
          instrument: "TACH-07",
          acceptance: { type: "range", min: 20, max: 70, unit: "rpm" },
        },
      },
      {
        requirement: "URS-TP201-010",
        text: "Material kontak produk adalah SS 316L.",
        source: { doc: "URS-TP201", rev: 0, page: 2, quote: "SS 316L" },
        kind: "vendor_reference",
        evidence: [
          {
            doc: "FAT-TP201",
            rev: 0,
            stage: "FAT",
            step: "FAT-M-02",
            test: "Uji material",
            acceptance: "SS 316L",
            observed: "SS 316L",
            observed_value: null,
            result: "pass",
            failure: null,
            citation: { doc: "FAT-TP201", rev: 0, page: 1, quote: "SS 316L" },
          },
        ],
        test_step: null,
      },
    ],
  };
}

function renderExecution(
  execution: ExecutionView | null,
  protocol: ProtocolView | null,
  canExecute: boolean,
) {
  return render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <ExecutionViewPanel
        execution={execution}
        protocol={protocol}
        runId={RUN_ID}
        startAction={canExecute ? startAction : null}
      />
    </NextIntlClientProvider>,
  );
}

test("without an Approved Protocol, shows link to Protocol page and no start button", () => {
  renderExecution(null, protocolView(), true);
  expect(screen.getByText("Belum ada protokol yang disetujui")).toBeDefined();
  expect(screen.queryByRole("button", { name: "Mulai eksekusi" })).toBeNull();
  expect(screen.getByRole("link", { name: "Buka Protokol IQ/OQ" }).getAttribute("href")).toBe(
    `/runs/${RUN_ID}/protocol`,
  );
  expect(screen.getByRole("heading", { name: "Batas yang diketahui" })).toBeDefined();
});

test("when Protocol is Approved and no Execution exists, executor sees start button; reader/approver sees none", () => {
  const { unmount } = renderExecution(null, approved, true);
  expect(screen.getByText("Belum ada eksekusi untuk protokol yang disetujui ini")).toBeDefined();
  expect(screen.getByRole("button", { name: "Mulai eksekusi" })).toBeDefined();
  unmount();

  renderExecution(null, approved, false);
  expect(screen.queryByRole("button", { name: "Mulai eksekusi" })).toBeNull();
  expect(screen.getByText(/tidak memiliki peran pelaksana/)).toBeDefined();
});

test("renders started Execution with status, history, frozen rows in order, and known limits", () => {
  renderExecution(executionFixture(), approved, false);

  expect(screen.getByRole("heading", { name: "Status eksekusi 12" })).toBeDefined();
  expect(screen.getByText("Sedang berjalan")).toBeDefined();
  expect(screen.getByText(/Dimulai oleh Ayu Kartika Sari/)).toBeDefined();

  const stepRow = within(screen.getByTestId("exec-row-URS-TP201-002"));
  expect(stepRow.getByText("Langkah uji")).toBeDefined();
  expect(stepRow.getByText("Verifikasi rentang kecepatan turret.")).toBeDefined();
  expect(stepRow.getByText("Atur turret ke 20 dan 70 rpm.")).toBeDefined();
  expect(stepRow.getByText("TACH-07")).toBeDefined();
  expect(stepRow.getByText("20–70 rpm")).toBeDefined();

  const vendorRow = within(screen.getByTestId("exec-row-URS-TP201-010"));
  expect(vendorRow.getByText("Referensi vendor")).toBeDefined();
  expect(vendorRow.getByText("FAT-TP201 rev 0, langkah FAT-M-02")).toBeDefined();
  expect(vendorRow.queryByRole("button", { name: /Mulai/ })).toBeNull();

  expect(screen.getByRole("heading", { name: "Batas yang diketahui" })).toBeDefined();
  expect(screen.getByText(/IQ dan OQ digabung dalam satu eksekusi/)).toBeDefined();
});
