import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { vi } from "vitest";

import type { ExecutionView, QualificationReportView } from "@/api/client";
import type { Session } from "@/auth/session";
import messages from "../../messages/id.json";
import { QualificationReportWorkbench } from "./QualificationReportWorkbench";

function reportFixture(
  overrides: Partial<QualificationReportView> = {},
): QualificationReportView {
  return {
    execution_id: 12,
    protocol_id: 7,
    equipment: "TP-201",
    run_id: "r7 TP/201",
    execution_copy_hash: "b".repeat(64),
    completed_at: "2026-11-25T10:00:00Z",
    technical_conclusion: "qualified_with_deviations",
    counts: {
      iq_total: 1,
      iq_passed: 1,
      iq_failed: 0,
      oq_total: 2,
      oq_passed: 2,
      oq_failed: 0,
      unsplit_total: 0,
      unsplit_passed: 0,
      unsplit_failed: 0,
      vendor_reference_count: 1,
      total_rows: 4,
      total_deviations: 1,
    },
    approval_note:
      "Persetujuan Laporan Kualifikasi adalah status tercatat, bukan Tanda Tangan Elektronik (ADR 0007).",
    latest_export: {
      id: 9,
      revision_number: 1,
      technical_conclusion: "qualified_with_deviations",
      conclusion_note: "Catatan QA",
      next_requalification_date: "2027-11-25",
      approval_note: "bukan Tanda Tangan Elektronik",
      snapshot_hash: "c".repeat(64),
      pdf_sha256: "d".repeat(64),
      template_version: "1",
      typst_version: "0.13",
      subject: "demo-0002",
      issuer: "http://127.0.0.1:9000",
      name: "Dewi Lestari",
      at: "2026-11-25T11:00:00Z",
    },
    exports: [
      {
        id: 9,
        revision_number: 1,
        technical_conclusion: "qualified_with_deviations",
        conclusion_note: "Catatan QA",
        next_requalification_date: "2027-11-25",
        approval_note: "bukan Tanda Tangan Elektronik",
        snapshot_hash: "c".repeat(64),
        pdf_sha256: "d".repeat(64),
        template_version: "1",
        typst_version: "0.13",
        subject: "demo-0002",
        issuer: "http://127.0.0.1:9000",
        name: "Dewi Lestari",
        at: "2026-11-25T11:00:00Z",
      },
    ],
    ...overrides,
  };
}

function executionFixture(): ExecutionView {
  return {
    id: 12,
    protocol_id: 7,
    equipment: "TP-201",
    run_id: "r7 TP/201",
    submission_event_id: 19,
    submission_hash: "a".repeat(64),
    status: "completed",
    events: [],
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
          stage: "OQ",
          witness_required: true,
        },
        attempts: [
          {
            id: 1,
            at: "2026-11-25T08:00:00Z",
            attempt_number: 1,
            requirement: "URS-TP201-002",
            subject: "demo-0001",
            issuer: "http://127.0.0.1:9000",
            name: "Ayu",
            versions: [],
            latest: {
              id: 1,
              at: "2026-11-25T08:00:00Z",
              version: 1,
              outcome_kind: "value",
              not_performable_reason: null,
              value: { type: "number", value: 45 },
              observation: null,
              instruments: [],
              no_calibrated_instrument_reason: null,
              evidence: [],
              verdict: "pass",
              version_hash: "e".repeat(64),
              reason_for_change: null,
              subject: "demo-0001",
              issuer: "http://127.0.0.1:9000",
              name: "Ayu",
              witness_confirmations: [
                {
                  id: 1,
                  version_id: 1,
                  at: "2026-11-25T08:05:00Z",
                  subject: "demo-0003",
                  issuer: "http://127.0.0.1:9000",
                  name: "Citra",
                  version_hash: "e".repeat(64),
                  voided: false,
                  note: "Sesuai pembacaan takometer",
                },
              ],
            },
            retest_deviation_id: 4,
            retest_reason: "Uji ulang setelah kalibrasi",
          },
        ],
      },
    ],
    deviations: [
      {
        id: 4,
        deviation_number: 1,
        status: "closed",
        cause: "failed",
        attempt_id: 1,
        deviation_class: "minor",
        requirement: "URS-TP201-002",
        description: "Takometer belum terpasang ulang",
        subject: "demo-0001",
        issuer: "http://127.0.0.1:9000",
        name: "Ayu",
        at: "2026-11-25T07:50:00Z",
        events: [],
        investigations: [],
      },
    ],
    completion_blockers: {
      blocked: false,
      rows_without_result: { count: 0, requirements: [] },
      open_deviations: { count: 0, items: [] },
      unconfirmed_witness_rows: { count: 0, requirements: [] },
    },
    frozen_copy: null,
    copy_hash: "b".repeat(64),
  };
}

const approverSession: Session = {
  name: "Dewi Lestari",
  subject: "demo-0002",
  issuer: "http://127.0.0.1:9000",
  mayDecide: false,
  mayApprove: true,
  mayExecute: false,
  mayWitness: false,
};

const readerSession: Session = {
  name: "Citra",
  subject: "demo-0003",
  issuer: "http://127.0.0.1:9000",
  mayDecide: false,
  mayApprove: false,
  mayExecute: false,
  mayWitness: true,
};

test("renders conclusion, stage counts, ADR 0007 notice, retest lineage, exports, and approver form", () => {
  const approveAction = vi.fn(async () => ({ ok: true, submittedAt: Date.now() }));
  render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <QualificationReportWorkbench
        runId="r7 TP/201"
        report={reportFixture()}
        execution={executionFixture()}
        session={approverSession}
        approveAction={approveAction}
      />
    </NextIntlClientProvider>,
  );

  expect(screen.getAllByText("Memenuhi Syarat dengan Deviasi").length).toBeGreaterThan(0);
  expect(screen.getAllByText(/bukan Tanda Tangan Elektronik/).length).toBeGreaterThanOrEqual(1);
  expect(screen.getByText("1 lulus · 0 gagal")).toBeDefined();
  expect(screen.getByText("2 lulus · 0 gagal")).toBeDefined();
  expect(screen.getByText("Percobaan #1 (Deviasi #4)")).toBeDefined();
  expect(screen.getByText("#1")).toBeDefined();
  expect(screen.getByText("Rev 1")).toBeDefined();

  const downloadLink = screen.getByRole("link", { name: "Unduh PDF" });
  expect(downloadLink.getAttribute("href")).toBe(
    "/api/executions/12/qualification-reports/9/pdf",
  );

  expect(screen.getByLabelText("Tanggal rekualifikasi berikutnya (opsional)")).toBeDefined();
  const submitBtn = screen.getByRole("button", { name: "Terbitkan Laporan Kualifikasi (PDF)" });
  fireEvent.click(submitBtn);
});

test("hides approver form for non-approver and hides requalification date when not_qualified", () => {
  const approveAction = vi.fn(async () => ({ ok: true }));
  const { unmount } = render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <QualificationReportWorkbench
        runId="r7 TP/201"
        report={reportFixture({ exports: [], latest_export: null })}
        execution={null}
        session={readerSession}
        approveAction={approveAction}
      />
    </NextIntlClientProvider>,
  );

  expect(screen.queryByRole("button", { name: "Terbitkan Laporan Kualifikasi (PDF)" })).toBeNull();
  expect(
    screen.getByText("Hanya peran penyetuju (qualification-approver) yang dapat menerbitkan Laporan Kualifikasi."),
  ).toBeDefined();
  unmount();

  render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <QualificationReportWorkbench
        runId="r7 TP/201"
        report={reportFixture({ technical_conclusion: "not_qualified" })}
        execution={null}
        session={approverSession}
        approveAction={approveAction}
      />
    </NextIntlClientProvider>,
  );

  expect(screen.queryByLabelText("Tanggal rekualifikasi berikutnya (opsional)")).toBeNull();
  expect(
    screen.getByText(
      "Kesimpulan Tidak Memenuhi Syarat — tanggal rekualifikasi berikutnya tidak dapat dijadwalkan.",
    ),
  ).toBeDefined();
});

test("restores conclusion_note and next_requalification_date from sessionStorage and auto-opens ElectronicSignatureDialog on OIDC reauth return", () => {
  window.sessionStorage.setItem(
    "traceq:reauth:report:r7 TP/201",
    JSON.stringify({
      conclusion_note: "Catatan tersimpan sebelum reauth",
      next_requalification_date: "2027-12-01",
    }),
  );
  const authTime = Math.floor(Date.now() / 1000) - 5;

  render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <QualificationReportWorkbench
        runId="r7 TP/201"
        report={reportFixture()}
        execution={null}
        session={approverSession}
        signingAuth={{
          oidcMode: true,
          reauthAuthTime: authTime,
          signer: { name: "Citra Approver", username: "citra" },
        }}
        initialReauthTarget="qualification_report"
        approveAction={vi.fn(async () => ({ ok: true }))}
      />
    </NextIntlClientProvider>,
  );

  expect(
    (screen.getByLabelText(/Catatan kesimpulan/i) as HTMLTextAreaElement).value,
  ).toBe("Catatan tersimpan sebelum reauth");
  expect(
    (screen.getByLabelText("Tanggal rekualifikasi berikutnya (opsional)") as HTMLInputElement).value,
  ).toBe("2027-12-01");
  expect(screen.getByRole("dialog")).toBeDefined();
  expect(screen.getByText(/detik tersisa/i)).toBeDefined();
  expect(screen.getByTestId("signature-signer").textContent).toBe("Citra Approver(citra)");
});

test("pressing Enter in the requalification date field does not issue the report without the signature dialog", async () => {
  const approveAction = vi.fn(async () => ({ ok: true, submittedAt: Date.now() }));
  render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <QualificationReportWorkbench
        runId="r7 TP/201"
        report={reportFixture()}
        execution={null}
        session={approverSession}
        approveAction={approveAction}
      />
    </NextIntlClientProvider>,
  );

  const date = screen.getByLabelText("Tanggal rekualifikasi berikutnya (opsional)");
  expect(date.closest("form")).toBeNull();
  const user = userEvent.setup();
  await user.type(date, "2027-12-01{Enter}");

  expect(approveAction).not.toHaveBeenCalled();
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("the signature dialog's own form carries the report fields, the typed note and the date", async () => {
  const approveAction = vi.fn(async () => ({ ok: true, submittedAt: Date.now() }));
  render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <QualificationReportWorkbench
        runId="r7 TP/201"
        report={reportFixture()}
        execution={null}
        session={approverSession}
        approveAction={approveAction}
      />
    </NextIntlClientProvider>,
  );

  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/Catatan kesimpulan/i), "Catatan QA");
  fireEvent.change(screen.getByLabelText("Tanggal rekualifikasi berikutnya (opsional)"), {
    target: { value: "2027-12-01" },
  });
  await user.click(screen.getByRole("button", { name: "Terbitkan Laporan Kualifikasi (PDF)" }));

  const dialog = screen.getByRole("dialog");
  await user.click(
    within(dialog).getByRole("button", { name: "Terbitkan Laporan Kualifikasi (PDF)" }),
  );

  expect(approveAction).toHaveBeenCalledTimes(1);
  const fd = (approveAction.mock.calls[0] as unknown as [unknown, FormData])[1];
  expect(Object.fromEntries(fd.entries())).toEqual({
    run_id: "r7 TP/201",
    execution_id: "12",
    expected_revision_number: "2",
    expected_execution_copy_hash: "b".repeat(64),
    conclusion_note: "Catatan QA",
    next_requalification_date: "2027-12-01",
  });
});
