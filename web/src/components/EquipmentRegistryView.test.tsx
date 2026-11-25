import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { EquipmentSummary } from "@/api/client";
import messages from "../../messages/id.json";
import { EquipmentRegistryView } from "./EquipmentRegistryView";

const items: EquipmentSummary[] = [
  {
    equipment: "TP-201",
    run_count: 2,
    latest_run: {
      run_id: "r7-tp201",
      created: "2026-11-10T08:05:00Z",
      equipment: "TP-201",
      model: "claude-opus-5-5",
      mode: "replay",
      pipeline_version: "1",
    },
    latest_round: {
      id: 2,
      round_number: 2,
      run_id: "r2-tp201",
      status: "ready_for_protocol",
      at: "2026-11-12T08:00:00Z",
    },
    latest_protocol: {
      id: 7,
      run_id: "r3-tp201",
      status: "approved",
      at: "2026-11-14T08:00:00Z",
    },
    latest_execution: {
      id: 12,
      protocol_id: 7,
      run_id: "r4-tp201",
      status: "completed",
      open_deviations: 1,
      at: "2026-11-16T08:00:00Z",
    },
    latest_qualification_report: {
      id: 9,
      execution_id: 12,
      run_id: "r5-tp201",
      revision_number: 1,
      technical_conclusion: "qualified_with_deviations",
      next_requalification_date: "2027-11-25",
      pdf_sha256: "a".repeat(64),
      at: "2026-11-17T08:00:00Z",
    },
  },
  {
    equipment: "AC-102",
    run_count: 1,
    latest_run: null,
    latest_round: null,
    latest_protocol: null,
    latest_execution: null,
    latest_qualification_report: null,
  },
];

test("renders Equipment Registry links using each nested summary run_id and requalification fallback", () => {
  render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <EquipmentRegistryView items={items} />
    </NextIntlClientProvider>,
  );

  expect(screen.getByRole("link", { name: /TP-201/ }).getAttribute("href")).toBe("/runs/r7-tp201");
  expect(screen.getByRole("link", { name: /R2 · Siap protokol/ }).getAttribute("href")).toBe(
    "/runs/r2-tp201/rounds",
  );
  expect(screen.getByRole("link", { name: /Disetujui/ }).getAttribute("href")).toBe(
    "/runs/r3-tp201/protocol",
  );
  expect(screen.getByRole("link", { name: /Selesai.*1 deviasi terbuka/ }).getAttribute("href")).toBe(
    "/runs/r4-tp201/execution",
  );
  expect(
    screen.getByRole("link", { name: /Memenuhi Syarat dengan Deviasi.*Rev 1/ }).getAttribute("href"),
  ).toBe("/runs/r5-tp201/report");

  expect(screen.getByText("2027-11-25")).toBeDefined();
  expect(screen.getByText("Belum dijadwalkan")).toBeDefined();
});
