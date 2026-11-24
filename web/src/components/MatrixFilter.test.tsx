import { fireEvent, render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { Matrix } from "@/api/client";

import messages from "../../messages/id.json";
import { decision, RUN_ID } from "./decisions.fixture";
import { MatrixTable } from "./MatrixTable";

const matrix: Matrix = {
  not_read: [],
  requirements: [
    {
      id: "URS-TP201-001",
      text: "Persyaratan satu",
      source: { doc: "URS-TP201", rev: 1, page: 1, quote: "satu" },
      value: null,
      value_citation: null,
      site_only: false,
      transport_sensitive: false,
      coverage: "gap",
      reason: "Belum diuji",
      evidence: [],
      design: [],
    },
    {
      id: "URS-TP201-002",
      text: "Persyaratan dua",
      source: { doc: "URS-TP201", rev: 1, page: 2, quote: "dua" },
      value: null,
      value_citation: null,
      site_only: false,
      transport_sensitive: false,
      coverage: "covered_by_vendor",
      reason: "Sudah diuji",
      evidence: [],
      design: [],
    },
  ],
};

test("filters matrix rows by coverage and decision status, supports 1-click pills, and preserves returnQuery/anchor", async () => {
  const action = async () => {};
  render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <MatrixTable
        matrix={matrix}
        runId={RUN_ID}
        filter={{ coverage: "gap", status: "undecided" }}
        decisions={{
          access: { mode: "decide", action },
          proposals: [
            {
              id: 1,
              kind: "coverage",
              requirement: "URS-TP201-001",
              position: null,
              content_hash: "h1",
              state: "undecided",
              decisions: [],
              previous: null,
              previous_class: null,
            },
            {
              id: 2,
              kind: "coverage",
              requirement: "URS-TP201-002",
              position: null,
              content_hash: "h2",
              state: "decided",
              decisions: [decision({ id: 9 })],
              previous: null,
              previous_class: null,
            },
          ],
        }}
      />
    </NextIntlClientProvider>,
  );

  expect(screen.getByText("Menampilkan 1 dari 2 persyaratan")).toBeDefined();
  const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
  expect(rows.map((r) => r.getAttribute("data-testid"))).toEqual(["URS-TP201-001"]);

  // Open drawer for URS-TP201-001 and verify return_query/anchor in form
  fireEvent.click(screen.getByRole("button", { name: "URS-TP201-001" }));
  const dialog = await screen.findByRole("dialog", { name: "URS-TP201-001" });
  const acceptForm = within(dialog).getByRole("button", { name: "Terima" }).closest("form")!;
  expect(acceptForm.querySelector('input[name="return_query"]')?.getAttribute("value")).toBe(
    "coverage=gap&status=undecided",
  );
  expect(acceptForm.querySelector('input[name="anchor"]')?.getAttribute("value")).toBe(
    "URS-TP201-001",
  );

  // Close drawer, then test 1-click "Semua" pill resets filter and syncs URL
  fireEvent.click(within(dialog).getByRole("button", { name: "Tutup panel" }));
  fireEvent.click(screen.getByRole("button", { name: /^Semua\s*2$/ }));
  expect(within(screen.getByRole("table")).getAllByRole("row").slice(1)).toHaveLength(2);
  expect(window.location.search).toBe("");

  // Click "Celah 1" blocker pill
  fireEvent.click(screen.getByRole("button", { name: /^Celah\s*1$/ }));
  expect(within(screen.getByRole("table")).getAllByRole("row").slice(1)).toHaveLength(1);
  expect(window.location.search).toBe("?coverage=gap");
});
