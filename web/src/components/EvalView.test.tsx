// The eval screen over a fixture aggregate from the harness's eval API (spec #29, ticket #42).
import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { EvalSummary } from "@/api/client";
import messages from "../../messages/id.json";
import fixture from "../../../tests/fixtures/eval/summary.json";
import { EvalView } from "./EvalView";

test("renders every rate with k/n and its split, the gates and the cost", () => {
  render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <EvalView summary={fixture as EvalSummary} />
    </NextIntlClientProvider>,
  );

  const rows = screen.getAllByRole("row").slice(1);
  expect(rows).toHaveLength(fixture.rates.length);
  for (const row of rows) {
    expect(within(row).getByText("Pengembangan (TP-201)")).toBeDefined();
    expect(within(row).getByTestId("kn").textContent).toMatch(/^\d+\/\d+$/);
  }

  const extraction = within(screen.getByTestId("extraction_accuracy"));
  expect(extraction.getByText("Akurasi ekstraksi nilai")).toBeDefined();
  expect(extraction.getByText("31/38")).toBeDefined();
  expect(extraction.getByText("81,6%")).toBeDefined();

  const cer = within(screen.getByTestId("ocr_cer"));
  expect(cer.getByText("41/371")).toBeDefined();
  expect(cer.getByText("Lebih rendah lebih baik")).toBeDefined();
  expect(within(screen.getByTestId("fabrication_rate")).getByText("0/129")).toBeDefined();
  expect(within(screen.getByTestId("citation_groundedness")).getByText("84/91")).toBeDefined();
  expect(within(screen.getByTestId("defect_recall")).getByText("5/7")).toBeDefined();

  expect(screen.getByText("Gerbang fabrikasi: lulus")).toBeDefined();
  expect(screen.getByText(/0,0012 USD/)).toBeDefined();
});

test("a rate over nothing shows a dash, not zero", () => {
  const empty = {
    ...(fixture as EvalSummary),
    split: "held_out",
    equipment: "TP-202",
    rates: [{ metric: "ocr_cer", k: 0, n: 0, rate: null, better: "lower" }],
  } satisfies EvalSummary;
  render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <EvalView summary={empty} />
    </NextIntlClientProvider>,
  );
  const cer = within(screen.getByTestId("ocr_cer"));
  expect(cer.getByText("0/0")).toBeDefined();
  expect(cer.getByText("–")).toBeDefined();
  expect(cer.getByText("Held-out (TP-202)")).toBeDefined();
});
