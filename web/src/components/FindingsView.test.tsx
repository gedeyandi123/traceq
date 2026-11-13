// The Pre-review screen over the fixture run folder the API contract tests use (spec #29).
import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { Findings } from "@/api/client";
import messages from "../../messages/id.json";
import fixture from "../../../tests/fixtures/run/runs/20261113T090000Z-f1a2b3/findings.json";
import { FindingsView } from "./FindingsView";

const RUN_ID = "20261113T090000Z-f1a2b3";

test("renders Check Findings, AI Findings and missing documents apart, each cited", () => {
  render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <FindingsView findings={fixture as Findings} runId={RUN_ID} />
    </NextIntlClientProvider>,
  );

  const check = within(screen.getByRole("region", { name: "Temuan pemeriksaan (aturan)" }));
  expect(check.getByText("Di luar batas namun ditandai Lulus")).toBeDefined();
  expect(check.getByText("Protokol vendor belum disetujui")).toBeDefined();
  const limit = check.getByRole("link", { name: "FAT-TP201-M rev 0, hlm. 1" });
  expect(limit.getAttribute("href")).toBe(`/api/runs/${RUN_ID}/documents/FAT-TP201-M/0#page=1`);
  expect(limit.getAttribute("title")).toBe("FAT-M-04 Noise level <= 50 dB(A) 52 dB(A) Pass");
  expect(check.getByRole("link", { name: "SOP-VAL-002 rev 0, hlm. 1" })).toBeDefined();
  expect(check.queryByText("Menunggu tinjauan")).toBeNull();

  const ai = within(screen.getByRole("region", { name: "Temuan AI (saran)" }));
  expect(ai.getByText("Data tidak konsisten")).toBeDefined();
  expect(ai.getByText("Menunggu tinjauan")).toBeDefined();
  expect(ai.getByText(/claude-haiku-5-5/)).toBeDefined();
  expect(ai.getByRole("link", { name: "DS-TP201 rev 0, hlm. 1" })).toBeDefined();
  expect(ai.queryByText("Di luar batas namun ditandai Lulus")).toBeNull();

  const missing = within(screen.getByRole("region", { name: "Dokumen yang tidak ada" }));
  expect(missing.getByText("IQ-TP201")).toBeDefined();
  expect(missing.getByText("OQ-TP201")).toBeDefined();
  const cited = missing.getAllByRole("link", { name: "VMP-001 rev 0, hlm. 2" });
  expect(cited.map((a) => a.getAttribute("title"))).toEqual([
    "IQ-TP201 Protokol IQ IQ",
    "OQ-TP201 Protokol OQ OQ",
  ]);
});
