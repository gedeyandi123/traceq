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
          witness_required: false,
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
    completion_blockers: {
      blocked: true,
      rows_without_result: { count: 1, requirements: ["URS-TP201-002"] },
      open_deviations: { count: 0, items: [] },
      unconfirmed_witness_rows: { count: 0, requirements: [] },
    },
    frozen_copy: null,
    copy_hash: null,
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

test("renders started Execution with status, history, frozen rows in order, and known limits", async () => {
  const user = userEvent.setup();
  renderExecution(executionFixture(), approved, false);

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

  await user.click(screen.getByRole("tab", { name: /Riwayat & salinan/ }));
  expect(screen.getByRole("heading", { name: "Status eksekusi 12" })).toBeDefined();
  expect(screen.getByText("Sedang berjalan")).toBeDefined();
  expect(screen.getByText(/Dimulai oleh Ayu Kartika Sari/)).toBeDefined();
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
        witness_required: false,
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
        witness_required: false,
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
  await user.click(within(oneOfDialog).getByRole("button", { name: "Buang perubahan" }));

  // Present row: has Ada / Tidak ada and "Tidak dapat dilaksanakan" option
  const presentRow = within(screen.getByTestId("exec-row-URS-TP201-030"));
  await user.click(presentRow.getByRole("button", { name: "Catat hasil" }));
  const presentDialog = await screen.findByRole("dialog");
  expect(within(presentDialog).getByLabelText("Ada (Present)")).toBeDefined();
  expect(within(presentDialog).getByLabelText("Tidak ada (Absent)")).toBeDefined();
  await user.click(within(presentDialog).getByLabelText("Tidak dapat dilaksanakan"));
  expect(within(presentDialog).getByLabelText("Alasan tidak dapat dilaksanakan")).toBeDefined();
});

test("displays recorded attempt verdict, performer, UTC timestamp, and Deviations list", async () => {
  const user = userEvent.setup();
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
            witness_confirmations: [],
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
          witness_confirmations: [],
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
      investigations: [],
      closure_note: null,
    },
  ];

  renderExecution(ex, approved, true);

  const row = within(screen.getByTestId("exec-row-URS-TP201-002"));
  expect(row.getByText("Gagal")).toBeDefined();
  expect(row.getByText("99 rpm")).toBeDefined();
  expect(row.queryByRole("button", { name: "Catat hasil" })).toBeNull();

  await user.click(row.getByRole("button", { name: "URS-TP201-002" }));
  const rowDialog = await screen.findByRole("dialog", { name: "URS-TP201-002" });
  expect(within(rowDialog).getByText(/Dicatat oleh Ayu Kartika Sari/)).toBeDefined();
  await user.click(within(rowDialog).getByRole("button", { name: "Tutup panel" }));

  await user.click(screen.getByRole("tab", { name: /Deviasi/ }));
  expect(screen.getByRole("heading", { name: "Deviasi (1)" })).toBeDefined();
  expect(screen.getByText("#1")).toBeDefined();
  expect(screen.getByText("Terbuka")).toBeDefined();
  expect(screen.getByText("Belum ditetapkan")).toBeDefined();
  expect(screen.getByText(/failed Acceptance Criterion/)).toBeDefined();
});

test("executor sees manual deviation button and can open investigation form; approver sees close/return on submitted; reader sees none", async () => {
  const user = userEvent.setup();
  const ex = executionFixture();
  ex.deviations = [
    {
      id: 10,
      at: "2026-11-24T10:15:00Z",
      deviation_number: 1,
      requirement: null,
      attempt_id: null,
      cause: "manual",
      status: "open",
      deviation_class: "minor",
      description: "Gangguan udara tekan.",
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
      investigations: [
        {
          id: 1,
          at: "2026-11-24T10:20:00Z",
          version: 1,
          investigation: "Kompresor berhenti sesaat.",
          deviation_class: "minor",
          capa: "Periksa katup.",
          reason_for_change: null,
          subject: "demo-0001",
          issuer: "http://127.0.0.1:9000",
          name: "Ayu Kartika Sari",
        },
      ],
      closure_note: null,
    },
    {
      id: 11,
      at: "2026-11-24T10:25:00Z",
      deviation_number: 2,
      requirement: "URS-TP201-002",
      attempt_id: 1,
      cause: "failed",
      status: "submitted",
      deviation_class: "major",
      description: "Kecepatan di luar rentang.",
      subject: "demo-0001",
      issuer: "http://127.0.0.1:9000",
      name: "Ayu Kartika Sari",
      events: [
        {
          id: 2,
          at: "2026-11-24T10:25:00Z",
          event: "opened",
          status: "open",
          reason: null,
          subject: "demo-0001",
          issuer: "http://127.0.0.1:9000",
          name: "Ayu Kartika Sari",
        },
        {
          id: 3,
          at: "2026-11-24T10:30:00Z",
          event: "submitted",
          status: "submitted",
          reason: null,
          subject: "demo-0001",
          issuer: "http://127.0.0.1:9000",
          name: "Ayu Kartika Sari",
        },
      ],
      investigations: [
        {
          id: 2,
          at: "2026-11-24T10:28:00Z",
          version: 1,
          investigation: "Sensor terlepas.",
          deviation_class: "major",
          capa: null,
          reason_for_change: null,
          subject: "demo-0001",
          issuer: "http://127.0.0.1:9000",
          name: "Ayu Kartika Sari",
        },
      ],
      closure_note: null,
    },
  ];

  const noop = async () => ({ ok: true });

  // Executor view
  const { unmount } = render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <ExecutionViewPanel
        execution={ex}
        protocol={approved}
        runId={RUN_ID}
        startAction={noop}
        recordAction={noop}
        openDeviationAction={noop}
        investigateAction={noop}
        submitDeviationAction={noop}
      />
    </NextIntlClientProvider>,
  );

  await user.click(screen.getByRole("tab", { name: /Deviasi/ }));
  expect(screen.getByRole("button", { name: "Buka deviasi manual" })).toBeDefined();
  await user.click(screen.getByRole("button", { name: "#1" }));
  expect((await screen.findAllByText("Kompresor berhenti sesaat.")).length).toBeGreaterThanOrEqual(
    1,
  );
  expect(screen.getByLabelText("Alasan perubahan (wajib untuk versi 2+)")).toBeDefined();
  expect(screen.getByRole("button", { name: "Ajukan deviasi" })).toBeDefined();
  unmount();

  // Approver view on Submitted deviation
  const { unmount: unmountApprover } = render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <ExecutionViewPanel
        execution={ex}
        protocol={approved}
        runId={RUN_ID}
        startAction={null}
        closeDeviationAction={noop}
        returnDeviationAction={noop}
      />
    </NextIntlClientProvider>,
  );

  await user.click(screen.getByRole("tab", { name: /Deviasi/ }));
  expect(screen.queryByRole("button", { name: "Buka deviasi manual" })).toBeNull();
  await user.click(screen.getByRole("button", { name: "#2" }));
  expect(await screen.findByText("Sensor terlepas.")).toBeDefined();
  expect(screen.getByRole("button", { name: "Tutup deviasi" })).toBeDefined();
  expect(screen.getByRole("button", { name: "Kembalikan ke Terbuka" })).toBeDefined();
  expect(
    screen.getByText("Penutupan deviasi adalah status tercatat, bukan Tanda Tangan Elektronik."),
  ).toBeDefined();
  unmountApprover();

  // Reader view
  render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <ExecutionViewPanel execution={ex} protocol={approved} runId={RUN_ID} startAction={null} />
    </NextIntlClientProvider>,
  );
  await user.click(screen.getByRole("tab", { name: /Deviasi/ }));
  expect(screen.queryByRole("button", { name: "Buka deviasi manual" })).toBeNull();
  await user.click(screen.getByRole("button", { name: "#2" }));
  expect(await screen.findByText("Sensor terlepas.")).toBeDefined();
  expect(screen.queryByRole("button", { name: "Tutup deviasi" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Simpan investigasi" })).toBeNull();
});

test("displays Witness status and restricts Konfirmasi sebagai Saksi by role and performer", async () => {
  const user = userEvent.setup();
  const ex = executionFixture();
  const baseVersion = {
    id: 1,
    at: "2026-11-24T10:05:00Z",
    version: 1,
    outcome_kind: "value" as const,
    not_performable_reason: null,
    value: { type: "number" as const, value: 40 },
    observation: null,
    instruments: [{ identifier: "TACH-07", calibration_due_date: "2027-05-01" }],
    no_calibrated_instrument_reason: null,
    evidence: [],
    verdict: "pass" as const,
    version_hash: "c".repeat(64),
    reason_for_change: null,
    subject: "demo-0001",
    issuer: "http://127.0.0.1:9000",
    name: "Ayu Kartika Sari",
    witness_confirmations: [],
  };
  ex.rows[0] = {
    ...ex.rows[0]!,
    attempts: [
      {
        id: 10,
        at: "2026-11-24T10:05:00Z",
        attempt_number: 1,
        requirement: "URS-TP201-002",
        subject: "demo-0001",
        issuer: "http://127.0.0.1:9000",
        name: "Ayu Kartika Sari",
        versions: [baseVersion],
        latest: baseVersion,
      },
    ],
  };

  const noop = async () => ({ ok: true });

  // 1. Witness (Eko) sees unconfirmed status + confirm button
  const { unmount: unmountEko } = render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <ExecutionViewPanel
        execution={ex}
        protocol={approved}
        runId={RUN_ID}
        currentUser={{ subject: "demo-0005", issuer: "http://127.0.0.1:9000" }}
        startAction={null}
        witnessAction={noop}
      />
    </NextIntlClientProvider>,
  );
  await user.click(
    within(screen.getByTestId("exec-row-URS-TP201-002")).getByRole("button", {
      name: "URS-TP201-002",
    }),
  );
  expect(
    await screen.findByText("Belum dikonfirmasi Saksi (tidak ada langkah uji yang mewajibkan Saksi)."),
  ).toBeDefined();
  expect(screen.getByRole("button", { name: "Konfirmasi sebagai Saksi" })).toBeDefined();
  unmountEko();

  // 2. Non-witness (Ayu / Citra / Dewi) sees no confirm button
  const { unmount: unmountNonWitness } = render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <ExecutionViewPanel
        execution={ex}
        protocol={approved}
        runId={RUN_ID}
        currentUser={{ subject: "demo-0001", issuer: "http://127.0.0.1:9000" }}
        startAction={null}
        witnessAction={null}
      />
    </NextIntlClientProvider>,
  );
  await user.click(
    within(screen.getByTestId("exec-row-URS-TP201-002")).getByRole("button", {
      name: "URS-TP201-002",
    }),
  );
  await screen.findByRole("dialog", { name: "URS-TP201-002" });
  expect(screen.queryByRole("button", { name: "Konfirmasi sebagai Saksi" })).toBeNull();
  unmountNonWitness();

  // 3. Performer holding witness role cannot confirm their own Result
  const { unmount: unmountPerformer } = render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <ExecutionViewPanel
        execution={ex}
        protocol={approved}
        runId={RUN_ID}
        currentUser={{ subject: "demo-0001", issuer: "http://127.0.0.1:9000" }}
        startAction={null}
        witnessAction={noop}
      />
    </NextIntlClientProvider>,
  );
  await user.click(
    within(screen.getByTestId("exec-row-URS-TP201-002")).getByRole("button", {
      name: "URS-TP201-002",
    }),
  );
  await screen.findByRole("dialog", { name: "URS-TP201-002" });
  expect(screen.queryByRole("button", { name: "Konfirmasi sebagai Saksi" })).toBeNull();
  expect(screen.getByText("Pelaksana hasil ini tidak dapat menjadi Saksi.")).toBeDefined();
  unmountPerformer();

  // 4. Confirmed + voided badges and ADR 0007 note render when confirmations exist
  const confirmedVersion = {
    ...baseVersion,
    witness_confirmations: [
      {
        id: 1,
        at: "2026-11-24T10:10:00Z",
        version_id: 1,
        version_hash: "c".repeat(64),
        subject: "demo-0005",
        issuer: "http://127.0.0.1:9000",
        name: "Eko Prasetyo Wijaya",
        voided: true,
        note: "a recorded status, not an Electronic Signature (ADR 0007 phase 2)",
      },
    ],
  };
  ex.rows[0] = {
    ...ex.rows[0]!,
    attempts: [
      {
        ...ex.rows[0]!.attempts[0]!,
        versions: [confirmedVersion],
        latest: confirmedVersion,
      },
    ],
  };
  render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <ExecutionViewPanel
        execution={ex}
        protocol={approved}
        runId={RUN_ID}
        currentUser={{ subject: "demo-0005", issuer: "http://127.0.0.1:9000" }}
        startAction={null}
        witnessAction={noop}
      />
    </NextIntlClientProvider>,
  );
  await user.click(
    within(screen.getByTestId("exec-row-URS-TP201-002")).getByRole("button", {
      name: "URS-TP201-002",
    }),
  );
  expect(await screen.findByText("Dibatalkan oleh versi baru")).toBeDefined();
  expect(screen.getByText(/Disaksikan oleh Eko Prasetyo Wijaya/)).toBeDefined();
  expect(
    screen.getAllByText("Status tercatat, bukan Tanda Tangan Elektronik (ADR 0007 fase 2).").length,
  ).toBeGreaterThanOrEqual(1);
  expect(screen.getByText("Anda sudah mengonfirmasi versi ini.")).toBeDefined();
  expect(screen.queryByRole("button", { name: "Konfirmasi sebagai Saksi" })).toBeNull();
});

test("completion checklist shows blockers, enables complete button only for executor when unblocked, and shows frozen copy when completed", () => {
  const noop = async () => ({ ok: true });
  const blockedEx = executionFixture();
  blockedEx.completion_blockers = {
    blocked: true,
    rows_without_result: { count: 1, requirements: ["URS-TP201-002"] },
    open_deviations: { count: 1, items: [{ deviation_number: 1, status: "open" }] },
    unconfirmed_witness_rows: { count: 0, requirements: [] },
  };

  // 1. Executor sees checklist + disabled Complete button when blocked
  const { unmount: unmountBlocked } = render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <ExecutionViewPanel
        execution={blockedEx}
        protocol={approved}
        runId={RUN_ID}
        startAction={null}
        completeAction={noop}
      />
    </NextIntlClientProvider>,
  );
  expect(screen.getByText("Daftar periksa penyelesaian eksekusi")).toBeDefined();
  expect(screen.getByText("Baris langkah uji tanpa hasil (1)")).toBeDefined();
  expect(screen.getByText("Deviasi belum ditutup (1)")).toBeDefined();
  expect(screen.getByText("#1 (Terbuka)")).toBeDefined();
  const blockedBtn = screen.getByRole("button", { name: "Selesaikan eksekusi" }) as HTMLButtonElement;
  expect(blockedBtn.disabled).toBe(true);
  unmountBlocked();

  // 2. Non-executor (completeAction = null) does not see Complete button
  const readyEx = executionFixture();
  readyEx.completion_blockers = {
    blocked: false,
    rows_without_result: { count: 0, requirements: [] },
    open_deviations: { count: 0, items: [] },
    unconfirmed_witness_rows: { count: 0, requirements: [] },
  };
  const { unmount: unmountReader } = render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <ExecutionViewPanel
        execution={readyEx}
        protocol={approved}
        runId={RUN_ID}
        startAction={null}
        completeAction={null}
      />
    </NextIntlClientProvider>,
  );
  expect(screen.queryByRole("button", { name: "Selesaikan eksekusi" })).toBeNull();
  unmountReader();

  // 3. Executor sees enabled Complete button when unblocked
  const { unmount: unmountReady } = render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <ExecutionViewPanel
        execution={readyEx}
        protocol={approved}
        runId={RUN_ID}
        startAction={null}
        completeAction={noop}
      />
    </NextIntlClientProvider>,
  );
  const readyBtn = screen.getByRole("button", { name: "Selesaikan eksekusi" }) as HTMLButtonElement;
  expect(readyBtn.disabled).toBe(false);
  unmountReady();

  // 4. Completed Execution shows frozen copy + hash and hides all write controls
  const completedEx = executionFixture();
  const copyHash = "f".repeat(64);
  completedEx.status = "completed";
  completedEx.completion_blockers = {
    blocked: false,
    rows_without_result: { count: 0, requirements: [] },
    open_deviations: { count: 0, items: [] },
    unconfirmed_witness_rows: { count: 0, requirements: [] },
  };
  completedEx.copy_hash = copyHash;
  completedEx.frozen_copy = {
    execution_id: completedEx.id,
    protocol_id: completedEx.protocol_id,
    equipment: completedEx.equipment,
    run_id: completedEx.run_id,
    submission_event_id: completedEx.submission_event_id,
    submission_hash: completedEx.submission_hash,
    completed_event_id: 2,
    completed_at: "2026-11-24T12:00:00Z",
    completer: {
      subject: "demo-0001",
      issuer: "http://127.0.0.1:9000",
      name: "Ayu Kartika Sari",
    },
    rows: [],
    deviations: [],
  };
  render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <ExecutionViewPanel
        execution={completedEx}
        protocol={approved}
        runId={RUN_ID}
        startAction={null}
        recordAction={noop}
        openDeviationAction={noop}
        witnessAction={noop}
        completeAction={noop}
      />
    </NextIntlClientProvider>,
  );
  expect(screen.getByText("Salinan beku eksekusi")).toBeDefined();
  expect(screen.getByText(copyHash)).toBeDefined();
  expect(screen.queryByRole("button", { name: "Selesaikan eksekusi" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Catat hasil" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Buka deviasi manual" })).toBeNull();
});

test("shows all attempts and versions in order, Koreksi only for attempt Performer, and Uji ulang when failed with Open Deviation", async () => {
  const user = userEvent.setup();
  const noop = async () => ({ ok: true });
  const ex = executionFixture();
  const stepRow = ex.rows[0]!;
  stepRow.attempts = [
    {
      id: 10,
      at: "2026-11-24T10:05:00Z",
      attempt_number: 1,
      requirement: "URS-TP201-002",
      subject: "demo-0001",
      issuer: "http://127.0.0.1:9000",
      name: "Ayu Kartika Sari",
      versions: [
        {
          id: 101,
          at: "2026-11-24T10:05:00Z",
          version: 1,
          outcome_kind: "value",
          not_performable_reason: null,
          value: { type: "number", value: 15 },
          observation: null,
          instruments: [{ identifier: "TACH-07", calibration_due_date: "2026-12-31" }],
          no_calibrated_instrument_reason: null,
          evidence: [],
          verdict: "fail",
          version_hash: "b".repeat(64),
          reason_for_change: null,
          subject: "demo-0001",
          issuer: "http://127.0.0.1:9000",
          name: "Ayu Kartika Sari",
          witness_confirmations: [],
        },
        {
          id: 102,
          at: "2026-11-24T10:08:00Z",
          version: 2,
          outcome_kind: "value",
          not_performable_reason: null,
          value: { type: "number", value: 18 },
          observation: null,
          instruments: [{ identifier: "TACH-07", calibration_due_date: "2026-12-31" }],
          no_calibrated_instrument_reason: null,
          evidence: [],
          verdict: "fail",
          version_hash: "c".repeat(64),
          reason_for_change: "Koreksi pembacaan awal",
          subject: "demo-0001",
          issuer: "http://127.0.0.1:9000",
          name: "Ayu Kartika Sari",
          witness_confirmations: [],
        },
      ],
      latest: {
        id: 102,
        at: "2026-11-24T10:08:00Z",
        version: 2,
        outcome_kind: "value",
        not_performable_reason: null,
        value: { type: "number", value: 18 },
        observation: null,
        instruments: [{ identifier: "TACH-07", calibration_due_date: "2026-12-31" }],
        no_calibrated_instrument_reason: null,
        evidence: [],
        verdict: "fail",
        version_hash: "c".repeat(64),
        reason_for_change: "Koreksi pembacaan awal",
        subject: "demo-0001",
        issuer: "http://127.0.0.1:9000",
        name: "Ayu Kartika Sari",
        witness_confirmations: [],
      },
    },
  ];
  ex.deviations = [
    {
      id: 50,
      at: "2026-11-24T10:05:00Z",
      deviation_number: 1,
      requirement: "URS-TP201-002",
      attempt_id: 10,
      cause: "failed",
      status: "open",
      deviation_class: null,
      description: "Gagal rentang kecepatan",
      subject: "demo-0001",
      issuer: "http://127.0.0.1:9000",
      name: "Ayu Kartika Sari",
      events: [],
      investigations: [],
      closure_note: null,
    },
  ];

  // Signed in as Ayu (attempt's Performer): sees Koreksi and Uji ulang
  const { unmount } = render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <ExecutionViewPanel
        execution={ex}
        protocol={approved}
        runId={RUN_ID}
        currentUser={{ subject: "demo-0001", issuer: "http://127.0.0.1:9000" }}
        startAction={noop}
        recordAction={noop}
        correctAction={noop}
        retestAction={noop}
      />
    </NextIntlClientProvider>,
  );

  await user.click(
    within(screen.getByTestId("exec-row-URS-TP201-002")).getByRole("button", {
      name: "URS-TP201-002",
    }),
  );
  const rowDialog = await screen.findByRole("dialog", { name: "URS-TP201-002" });
  expect(within(rowDialog).getByText("Percobaan #1")).toBeDefined();
  expect(within(rowDialog).getByText("v1")).toBeDefined();
  expect(within(rowDialog).getByText("v2")).toBeDefined();
  expect(within(rowDialog).getByText("Hasil saat ini")).toBeDefined();
  expect(within(rowDialog).getByText("Koreksi pembacaan awal")).toBeDefined();
  expect(within(rowDialog).getByRole("button", { name: "Koreksi" })).toBeDefined();
  expect(within(rowDialog).getByRole("button", { name: "Uji ulang" })).toBeDefined();

  // Opening Koreksi drawer shows Reason for Change field
  await user.click(within(rowDialog).getByRole("button", { name: "Koreksi" }));
  expect(screen.getByLabelText("Alasan perubahan")).toBeDefined();
  await user.keyboard("{Escape}");

  // Opening Uji ulang drawer shows Open Deviation select & reason field
  await user.click(within(rowDialog).getByRole("button", { name: "Uji ulang" }));
  expect(screen.getByLabelText("Deviasi terbuka terkait")).toBeDefined();
  expect(screen.getByLabelText("Alasan uji ulang")).toBeDefined();
  unmount();

  // Signed in as Bima (different Performer): does NOT see Koreksi, still sees Uji ulang
  render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <ExecutionViewPanel
        execution={ex}
        protocol={approved}
        runId={RUN_ID}
        currentUser={{ subject: "demo-0002", issuer: "http://127.0.0.1:9000" }}
        startAction={noop}
        recordAction={noop}
        correctAction={noop}
        retestAction={noop}
      />
    </NextIntlClientProvider>,
  );
  await user.click(
    within(screen.getByTestId("exec-row-URS-TP201-002")).getByRole("button", {
      name: "URS-TP201-002",
    }),
  );
  const rowBimaDialog = await screen.findByRole("dialog", { name: "URS-TP201-002" });
  expect(within(rowBimaDialog).queryByRole("button", { name: "Koreksi" })).toBeNull();
  expect(within(rowBimaDialog).getByRole("button", { name: "Uji ulang" })).toBeDefined();
});

test("displays stage/witness_required badges and unconfirmed_witness_rows blocker", () => {
  const ex = executionFixture();
  const row0 = ex.rows[0]!;
  if (row0.test_step) {
    row0.test_step.stage = "OQ";
    row0.test_step.witness_required = true;
  }
  ex.completion_blockers.unconfirmed_witness_rows = {
    count: 1,
    requirements: ["URS-TP201-002"],
  };

  renderExecution(ex, approved, true);

  expect(screen.getByText("Baris wajib Saksi yang belum dikonfirmasi (1)")).toBeDefined();
  const rowEl = screen.getByTestId("exec-row-URS-TP201-002");
  expect(within(rowEl).getByText("OQ")).toBeDefined();
  expect(within(rowEl).getByText("Wajib Saksi")).toBeDefined();
});
