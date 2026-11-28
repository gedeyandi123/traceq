import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import type { RunRoundsView } from "@/api/client";
import type { Session } from "@/auth/session";

import messages from "../../messages/id.json";
import {
  RoundsWorkbench,
  type CloseRoundAction,
  type ExportReportAction,
} from "./RoundsWorkbench";

const deciderSession: Session = {
  name: "Ayu Kartika Sari",
  subject: "demo-0001",
  issuer: "http://127.0.0.1:9000",
  mayDecide: true,
  mayApprove: false,
  mayExecute: true,
  mayWitness: false,
};

const approverSession: Session = {
  name: "Dewi Anggraini Lestari",
  subject: "demo-0003",
  issuer: "http://127.0.0.1:9000",
  mayDecide: false,
  mayApprove: true,
  mayExecute: false,
  mayWitness: false,
};

const readOnlySession: Session = {
  name: "Citra Maharani Putri",
  subject: "demo-0004",
  issuer: "http://127.0.0.1:9000",
  mayDecide: false,
  mayApprove: false,
  mayExecute: false,
  mayWitness: false,
};

const sampleRounds: RunRoundsView = {
  equipment: "TP-201",
  current_round_id: 2,
  rounds: [
    {
      id: 1,
      equipment: "TP-201",
      round_number: 1,
      run_id: "r1",
      previous_round_id: null,
      at: "2026-11-20T08:00:00Z",
      status: "returned_for_revision",
      documents: [
        {
          id: 10,
          equipment: "TP-201",
          doc_id: "URS-TP201",
          rev: 0,
          doc_type: "URS",
          source: "site",
          sha256: "aaaa1111bbbb2222cccc3333dddd4444",
          first_seen_run_id: "r1",
          at: "2026-11-20T08:00:00Z",
        },
        {
          id: 11,
          equipment: "TP-201",
          doc_id: "FAT-TP201",
          rev: 0,
          doc_type: "FAT",
          source: "vendor",
          sha256: "11112222333344445555666677778888",
          first_seen_run_id: "r1",
          at: "2026-11-20T08:00:00Z",
        },
      ],
      events: [
        {
          id: 1,
          round_id: 1,
          event: "opened",
          reason: null,
          at: "2026-11-20T08:00:00Z",
          subject: "demo-0001",
          issuer: "http://127.0.0.1:9000",
          name: "Ayu Kartika Sari",
        },
        {
          id: 2,
          round_id: 1,
          event: "returned_for_revision",
          reason: "Revisi sertifikat FAT diperlukan",
          at: "2026-11-20T09:00:00Z",
          subject: "demo-0001",
          issuer: "http://127.0.0.1:9000",
          name: "Ayu Kartika Sari",
        },
      ],
      exports: [
        {
          id: 100,
          round_id: 1,
          report_kind: "pre_review",
          at: "2026-11-20T08:30:00Z",
          subject: "demo-0001",
          issuer: "http://127.0.0.1:9000",
          name: "Ayu Kartika Sari",
          snapshot_hash: "snap1111222233334444",
          pdf_sha256: "pdfa1111222233334444",
          template_version: "1",
          typst_version: "0.13.0",
        },
      ],
    },
    {
      id: 2,
      equipment: "TP-201",
      round_number: 2,
      run_id: "r2",
      previous_round_id: 1,
      at: "2026-11-21T08:00:00Z",
      status: "open",
      documents: [
        {
          id: 10,
          equipment: "TP-201",
          doc_id: "URS-TP201",
          rev: 0,
          doc_type: "URS",
          source: "site",
          sha256: "aaaa1111bbbb2222cccc3333dddd4444",
          first_seen_run_id: "r1",
          at: "2026-11-20T08:00:00Z",
        },
        {
          id: 12,
          equipment: "TP-201",
          doc_id: "FAT-TP201",
          rev: 1,
          doc_type: "FAT",
          source: "vendor",
          sha256: "99998888777766665555444433332222",
          first_seen_run_id: "r2",
          at: "2026-11-21T08:00:00Z",
        },
        {
          id: 13,
          equipment: "TP-201",
          doc_id: "SAT-TP201",
          rev: 0,
          doc_type: "SAT",
          source: "vendor",
          sha256: "cccc4444dddd5555eeee6666ffff7777",
          first_seen_run_id: "r2",
          at: "2026-11-21T08:00:00Z",
        },
      ],
      events: [
        {
          id: 3,
          round_id: 2,
          event: "opened",
          reason: null,
          at: "2026-11-21T08:00:00Z",
          subject: "demo-0001",
          issuer: "http://127.0.0.1:9000",
          name: "Ayu Kartika Sari",
        },
      ],
      exports: [],
    },
  ],
  diff: {
    previous_round_number: 1,
    previous_run_id: "r1",
    documents_added: ["SAT-TP201"],
    documents_revised: ["FAT-TP201"],
    documents_unchanged: ["URS-TP201"],
    documents_removed: [],
    findings_resolved: 2,
    findings_persisted: 2,
    findings_persisted_changed: 1,
    findings_new: 1,
    decisions_carried_forward: 10,
    decisions_changed: 2,
    decisions_undecided: 3,
    findings: [
      {
        proposal_id: 1,
        kind: "draft",
        change: "persisted_changed",
        finding_type: "ac_deviates_from_urs",
        test_step: "OQ-03",
        requirement: "URS-TP201-003",
      },
      {
        proposal_id: 2,
        kind: "draft",
        change: "persisted",
        finding_type: "ac_deviates_from_urs",
        test_step: "OQ-24",
        requirement: "URS-TP201-024",
      },
    ],
  },
};

function renderWorkbench(
  session: Session | null = deciderSession,
  closeRoundAction: CloseRoundAction = vi.fn(async () => ({ ok: true, submittedAt: Date.now() })),
  exportReportAction: ExportReportAction = vi.fn(async () => ({ ok: true, submittedAt: Date.now() })),
) {
  const rendered = render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <RoundsWorkbench
        runId="r2"
        data={sampleRounds}
        session={session}
        closeRoundAction={closeRoundAction}
        exportReportAction={exportReportAction}
      />
    </NextIntlClientProvider>,
  );
  return { ...rendered, closeRoundAction, exportReportAction };
}

describe("RoundsWorkbench", () => {
  it("renders document versions with active/superseded status and cross-round diff badges", () => {
    renderWorkbench();

    expect(screen.getByText("Versi Dokumen Peralatan")).toBeDefined();
    expect(screen.getAllByText("FAT-TP201")).toHaveLength(2);
    expect(screen.getByText("Revisi baru")).toBeDefined();
    expect(screen.getByText("Baru di ronde ini")).toBeDefined();
    expect(screen.getByText("Tidak berubah")).toBeDefined();
    expect(screen.getByText("Digantikan")).toBeDefined();
    expect(screen.getAllByText("Aktif")).toHaveLength(3);
    expect(screen.getByText("999988887777")).toBeDefined();
  });

  it("renders review rounds & diff tab and enforces role gating for closing round", async () => {
    const user = userEvent.setup();
    renderWorkbench(deciderSession);

    await user.click(screen.getByRole("tab", { name: /Ronde Tinjauan & Diff/ }));
    expect(screen.getByText("Diff Lintas-Ronde (vs R1)")).toBeDefined();
    expect(screen.getByText("Revisi sertifikat FAT diperlukan")).toBeDefined();
    expect(screen.getByRole("button", { name: /Tutup ronde/ })).toBeDefined();
    // A persisted-but-changed finding is shown as that, and a plain persisted one is not listed.
    expect(screen.getAllByText("Bertahan, berubah")).toHaveLength(2);
    // The finding type is its Indonesian label, never the raw code.
    expect(
      screen.getByText("Kriteria penerimaan lebih longgar dari URS · OQ-03 · URS-TP201-003"),
    ).toBeDefined();
    expect(screen.queryByText(/ac_deviates_from_urs/)).toBeNull();
    // The figures here are dev-only and claim nothing about time saved or compliance.
    expect(screen.getByText(/Hanya data pengembangan/)).toBeDefined();
    expect(screen.queryByText(/OQ-24/)).toBeNull();
  });

  it("hides close round button for approver and read-only, while allowing approver to issue export", async () => {
    const user = userEvent.setup();
    const { unmount } = renderWorkbench(approverSession);

    await user.click(screen.getByRole("tab", { name: /Ronde Tinjauan & Diff/ }));
    expect(screen.queryByRole("button", { name: /Tutup ronde/ })).toBeNull();

    await user.click(screen.getByRole("tab", { name: /Ekspor Laporan/ }));
    expect(screen.getByRole("button", { name: /Terbitkan Laporan Pra-Tinjauan/ })).toBeDefined();
    expect(screen.getByRole("link", { name: /Unduh PDF/ }).getAttribute("href")).toBe(
      "/api/rounds/1/exports/100/pdf",
    );
    unmount();

    renderWorkbench(readOnlySession);
    await user.click(screen.getByRole("tab", { name: /Ekspor Laporan/ }));
    expect(screen.queryByRole("button", { name: /Terbitkan Laporan Pra-Tinjauan/ })).toBeNull();
    expect(screen.getByRole("link", { name: /Unduh PDF/ })).toBeDefined();
  });

  it("preserves typed reason on 422/409 error and triggers dirty-form guard on modal close", async () => {
    const user = userEvent.setup();
    const failingClose: CloseRoundAction = vi.fn(async (_prev, fd) => ({
      ok: false,
      error: "conflict" as const,
      outcome: "returned_for_revision" as const,
      reason: String(fd.get("reason") ?? ""),
    }));

    renderWorkbench(deciderSession, failingClose);

    await user.click(screen.getByRole("tab", { name: /Ronde Tinjauan & Diff/ }));
    await user.click(screen.getByRole("button", { name: /Tutup ronde/ }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Status tercatat, bukan Tanda Tangan Elektronik.")).toBeDefined();

    const textarea = within(dialog).getByLabelText(/Alasan perubahan/);
    fireEvent.change(textarea, { target: { value: "Dokumen SAT belum lengkap" } });
    await user.click(within(dialog).getByRole("button", { name: /Simpan penutupan ronde/ }));

    await waitFor(() => {
      expect(within(dialog).getByRole("alert").textContent).toContain("409");
    });
    expect((within(dialog).getByLabelText(/Alasan perubahan/) as HTMLTextAreaElement).value).toBe(
      "Dokumen SAT belum lengkap",
    );

    // Dirty guard triggers when cancelling with typed reason
    fireEvent.click(within(dialog).getByRole("button", { name: "Batal" }));
    expect(within(dialog).getByRole("alertdialog")).toBeDefined();

    fireEvent.click(within(dialog).getByRole("button", { name: /Buang & tutup/ }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
  });
});
