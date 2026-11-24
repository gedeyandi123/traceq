// The findings screen's labels: a missing document's type as a label with the raw value as
// fallback, and AI Finding timestamps formatted like decision timestamps.
import { fireEvent, render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { Findings } from "@/api/client";
import messages from "../../messages/id.json";
import fixture from "../../../tests/fixtures/run/runs/20261113T090000Z-f1a2b3/findings.json";
import { RUN_ID } from "./decisions.fixture";
import { FindingsView } from "./FindingsView";

function renderFindings(findings: Findings) {
  return render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <FindingsView
        findings={findings}
        runId={RUN_ID}
        decisions={{ access: { mode: "readOnly", why: "signedOut" } }}
      />
    </NextIntlClientProvider>,
  );
}

test("a missing document's type shows as its label, and as the raw value when no label exists", () => {
  const base = fixture as Findings;
  const [iq] = base.missing_documents;
  renderFindings({
    ...base,
    missing_documents: [iq!, { ...iq!, doc_id: "XX-TP201", type: "pump_manual" }],
  });

  const missingTab = screen.getByRole("tab", { name: /Dokumen yang tidak ada/ });
  fireEvent.mouseDown(missingTab);
  fireEvent.click(missingTab);

  const missing = within(screen.getByRole("region", { name: "Dokumen yang tidak ada" }));
  const [first, second] = missing.getAllByRole("row").slice(1);
  expect(within(first!).getByText("Protokol IQ")).toBeDefined();
  expect(within(first!).queryByText("iq_protocol")).toBeNull();
  expect(within(second!).getByText("pump_manual")).toBeDefined();
});

test("an AI Finding's timestamp reads like a decision's", () => {
  renderFindings(fixture as Findings);

  const ai = within(screen.getByRole("region", { name: "Temuan AI (saran)" }));
  fireEvent.click(ai.getByRole("button", { name: /Data tidak konsisten/ }));

  const detail = within(screen.getByRole("region", { name: "Rincian" }));
  expect(detail.getByText(/13\/11\/2026 09\.00 UTC/)).toBeDefined();
  expect(detail.queryByText(/2026-11-13T09:00:00/)).toBeNull();
});
