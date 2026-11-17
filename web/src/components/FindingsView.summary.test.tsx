// The findings screen's summary panel: one count per section, each a jump link (#158).
import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { Findings } from "@/api/client";
import messages from "../../messages/id.json";
import fixture from "../../../tests/fixtures/run/runs/20261113T090000Z-f1a2b3/findings.json";
import { RUN_ID } from "./decisions.fixture";
import { FindingsView } from "./FindingsView";

test("the summary counts each section of the fixture run and links to it", () => {
  render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <FindingsView
        findings={fixture as Findings}
        runId={RUN_ID}
        decisions={{ access: { mode: "readOnly", why: "signedOut" } }}
      />
    </NextIntlClientProvider>,
  );

  const summary = within(screen.getByRole("list", { name: "Ringkasan temuan" }));
  const links = summary.getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")]);
  expect(links).toEqual([
    ["2 Temuan pemeriksaan (aturan)", "#check-findings"],
    ["1 Temuan AI (saran)", "#ai-findings"],
    ["2 Dokumen yang tidak ada", "#missing-documents"],
  ]);
});
