// The findings screen's tab and filter counts over the fixture run.
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { Findings } from "@/api/client";
import messages from "../../messages/id.json";
import fixture from "../../../tests/fixtures/run/runs/20261113T090000Z-f1a2b3/findings.json";
import { RUN_ID } from "./decisions.fixture";
import { FindingsView } from "./FindingsView";

test("the tabs and filter chips count each section of the fixture run", () => {
  render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <FindingsView
        findings={fixture as Findings}
        runId={RUN_ID}
        decisions={{ access: { mode: "readOnly", why: "signedOut" } }}
      />
    </NextIntlClientProvider>,
  );

  expect(screen.getByRole("tab", { name: /Temuan pemeriksaan & AI\s*3/ })).toBeDefined();
  expect(screen.getByRole("tab", { name: /Dokumen yang tidak ada\s*2/ })).toBeDefined();
  expect(screen.getByRole("button", { name: /Semua\s*3/ })).toBeDefined();
  expect(screen.getByRole("button", { name: /Aturan\s*2/ })).toBeDefined();
  expect(screen.getByRole("button", { name: /AI\s*1/ })).toBeDefined();
});
