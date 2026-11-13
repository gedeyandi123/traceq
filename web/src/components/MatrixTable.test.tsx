// The matrix screen over the fixture run folder the API contract tests use (spec #29).
import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { Matrix } from "@/api/client";
import messages from "../../messages/id.json";
import fixture from "../../../tests/fixtures/run/runs/20261113T090000Z-f1a2b3/matrix.json";
import { MatrixTable } from "./MatrixTable";

const RUN_ID = "20261113T090000Z-f1a2b3";

function renderMatrix() {
  return render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <MatrixTable matrix={fixture as Matrix} runId={RUN_ID} />
    </NextIntlClientProvider>,
  );
}

test("renders each requirement with its Coverage class, reason and cited Evidence", () => {
  renderMatrix();

  expect(screen.getByRole("columnheader", { name: "Cakupan" })).toBeDefined();
  const speed = within(screen.getByTestId("URS-TP201-002"));
  expect(speed.getByText("Sebagian")).toBeDefined();
  expect(speed.getByText(/FAT-M-02: result does not meet the URS/)).toBeDefined();
  expect(speed.getByText("20–70 rpm")).toBeDefined();
  expect(speed.getByText(/Terbaca ganda \(1\.500 \/ 1,5\): minta konfirmasi/)).toBeDefined();

  const step = speed.getByRole("link", { name: "FAT-TP201-M rev 0, hlm. 1" });
  expect(step.getAttribute("href")).toBe(
    `/api/runs/${RUN_ID}/documents/FAT-TP201-M/0#page=1`,
  );
  expect(step.getAttribute("title")).toBe("FAT-M-02 Turret speed range 20-60 rpm 20-60 rpm Pass");
  expect(speed.getByRole("link", { name: "DS-TP201 rev 0, hlm. 1" })).toBeDefined();

  const power = within(screen.getByTestId("URS-TP201-026"));
  expect(power.getByText("Hanya di lokasi")).toBeDefined();
  expect(power.getByText("Tidak ada bukti vendor")).toBeDefined();

  const unassessed = within(screen.getByTestId("URS-TP201-030"));
  expect(unassessed.getByText("Belum dinilai")).toBeDefined();
  expect(unassessed.getByText("Tidak ada nilai terverifikasi")).toBeDefined();

  expect(screen.getByText("Dokumen vendor yang tidak terbaca")).toBeDefined();
  expect(screen.getByText("SAT-TP201 rev 0 (scan)")).toBeDefined();
});
