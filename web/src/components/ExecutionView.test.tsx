import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";

import type { ExecutionView, ProtocolView } from "@/api/client";
import messages from "../../messages/id.json";
import { RUN_ID } from "./decisions.fixture";
import { ExecutionViewPanel } from "./ExecutionView";
import { approved, protocolView } from "./protocol.fixture";

const startAction = async () => ({ ok: true });
const recordAction = async () => ({ ok: true });

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
        attempts: [],
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
        attempts: [],
      },
    ],
    deviations: [],
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
        recordAction={canExecute ? recordAction : null}
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
  expect(screen.getByText(/zona waktu UTC/)).toBeDefined();
  expect(screen.queryByRole("button", { name: "Catat hasil" })).toBeNull();
});

test("executor sees Catat hasil button and opens Result form for range, one_of, present, and not_performable", async () => {
  const user = userEvent.setup();
  const ex = executionFixture();
  ex.rows.push(
    {
      requirement: "URS-TP201-020",
      text: "Mode operasi harus dipilih.",
      source: { doc: "URS-TP201", rev: 0, page: 3, quote: "Auto/Manual" },
      kind: "test_step",
      evidence: [],
      test_step: {
        origin: "written",
        description: "Periksa pilihan mode.",
        method: "Pilih mode pada HMI.",
        instrument: null,
        acceptance: { type: "one_of", allowed: ["Auto", "Manual"] },
      },
      attempts: [],
    },
    {
      requirement: "URS-TP201-030",
      text: "Pelindung keselamatan terpasang.",
      source: { doc: "URS-TP201", rev: 0, page: 4, quote: "Safety guard" },
      kind: "test_step",
      evidence: [],
      test_step: {
        origin: "written",
        description: "Periksa pelindung keselamatan.",
        method: "Inspeksi visual.",
        instrument: null,
        acceptance: { type: "present", value: null },
      },
      attempts: [],
    },
  );

  renderExecution(ex, approved, true);

  // Range row: has non-editable unit label and instruments section
  const rangeRow = within(screen.getByTestId("exec-row-URS-TP201-002"));
  await user.click(rangeRow.getByRole("button", { name: "Catat hasil" }));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByTestId("ac-unit-label").textContent).toBe("rpm");
  expect(within(dialog).getByText("Instrumen terkalibrasi")).toBeDefined();
  expect(within(dialog).getByLabelText("ID instrumen")).toBeDefined();
  await user.click(within(dialog).getByRole("button", { name: "Tutup panel" }));

  // OneOf row: has allowed choices + "Bukan salah satu dari ini" revealing observed text, no instruments
  const oneOfRow = within(screen.getByTestId("exec-row-URS-TP201-020"));
  await user.click(oneOfRow.getByRole("button", { name: "Catat hasil" }));
  const oneOfDialog = await screen.findByRole("dialog");
  expect(within(oneOfDialog).queryByText("Instrumen terkalibrasi")).toBeNull();
  await user.click(within(oneOfDialog).getByLabelText("Bukan salah satu dari ini"));
  expect(within(oneOfDialog).getByLabelText("Nilai yang teramati")).toBeDefined();
  await user.click(within(oneOfDialog).getByRole("button", { name: "Tutup panel" }));

  // Present row: has Ada / Tidak ada and "Tidak dapat dilaksanakan" option
  const presentRow = within(screen.getByTestId("exec-row-URS-TP201-030"));
  await user.click(presentRow.getByRole("button", { name: "Catat hasil" }));
  const presentDialog = await screen.findByRole("dialog");
  expect(within(presentDialog).getByLabelText("Ada (Present)")).toBeDefined();
  expect(within(presentDialog).getByLabelText("Tidak ada (Absent)")).toBeDefined();
  await user.click(within(presentDialog).getByLabelText("Tidak dapat dilaksanakan"));
  expect(within(presentDialog).getByLabelText("Alasan tidak dapat dilaksanakan")).toBeDefined();
});

test("displays recorded attempt verdict, performer, UTC timestamp, and Deviations list", () => {
  const ex = executionFixture();
  ex.rows[0] = {
    ...ex.rows[0]!,
    attempts: [
      {
        id: 1,
        at: "2026-11-24T10:15:00Z",
        attempt_number: 1,
        requirement: "URS-TP201-002",
        subject: "demo-0001",
        issuer: "http://127.0.0.1:9000",
        name: "Ayu Kartika Sari",
        versions: [
          {
            id: 1,
            at: "2026-11-24T10:15:00Z",
            version: 1,
            outcome_kind: "value",
            not_performable_reason: null,
            value: { type: "number", value: 99 },
            observation: "Melebihi batas atas",
            instruments: [{ identifier: "TACH-07", calibration_due_date: "2027-01-01" }],
            no_calibrated_instrument_reason: null,
            evidence: ["PRINT-01"],
            verdict: "fail",
            version_hash: "b".repeat(64),
            reason_for_change: null,
            subject: "demo-0001",
            issuer: "http://127.0.0.1:9000",
            name: "Ayu Kartika Sari",
          },
        ],
        latest: {
          id: 1,
          at: "2026-11-24T10:15:00Z",
          version: 1,
          outcome_kind: "value",
          not_performable_reason: null,
          value: { type: "number", value: 99 },
          observation: "Melebihi batas atas",
          instruments: [{ identifier: "TACH-07", calibration_due_date: "2027-01-01" }],
          no_calibrated_instrument_reason: null,
          evidence: ["PRINT-01"],
          verdict: "fail",
          version_hash: "b".repeat(64),
          reason_for_change: null,
          subject: "demo-0001",
          issuer: "http://127.0.0.1:9000",
          name: "Ayu Kartika Sari",
        },
      },
    ],
  };
  ex.deviations = [
    {
      id: 10,
      at: "2026-11-24T10:15:00Z",
      deviation_number: 1,
      requirement: "URS-TP201-002",
      attempt_id: 1,
      cause: "failed",
      status: "open",
      deviation_class: null,
      description: "Test Step URS-TP201-002 failed Acceptance Criterion (20–70 rpm) with Result: 99 rpm.",
      subject: "demo-0001",
      issuer: "http://127.0.0.1:9000",
      name: "Ayu Kartika Sari",
      events: [
        {
          id: 1,
          at: "2026-11-24T10:15:00Z",
          event: "opened",
          status: "open",
          reason: null,
          subject: "demo-0001",
          issuer: "http://127.0.0.1:9000",
          name: "Ayu Kartika Sari",
        },
      ],
    },
  ];

  renderExecution(ex, approved, true);

  const row = within(screen.getByTestId("exec-row-URS-TP201-002"));
  expect(row.getByText("Gagal")).toBeDefined();
  expect(row.getByText("99 rpm")).toBeDefined();
  expect(row.getByText(/Dicatat oleh Ayu Kartika Sari/)).toBeDefined();
  expect(row.queryByRole("button", { name: "Catat hasil" })).toBeNull();

  expect(screen.getByRole("heading", { name: "Deviasi (1)" })).toBeDefined();
  expect(screen.getByText("#1")).toBeDefined();
  expect(screen.getByText("Terbuka")).toBeDefined();
  expect(screen.getByText("Belum ditetapkan")).toBeDefined();
  expect(screen.getByText(/failed Acceptance Criterion/)).toBeDefined();
});
