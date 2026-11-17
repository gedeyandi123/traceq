// The eval screen's panels and its "not scored yet" state (spec #135, ticket #143).
import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { EvalSummary } from "@/api/client";
import messages from "../../messages/id.json";
import fixture from "../../../tests/fixtures/eval/summary.json";
import { EvalView } from "./EvalView";

function show(summary: EvalSummary | null) {
  render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <EvalView summary={summary} />
    </NextIntlClientProvider>,
  );
}

test("a run without scores reads as not scored yet, with no rates and no gate", () => {
  show(null);

  expect(screen.getByText("Belum ada hasil evaluasi")).toBeDefined();
  expect(screen.getByText(/Run ini belum dinilai/)).toBeDefined();
  expect(screen.queryAllByRole("row")).toHaveLength(0);
  expect(screen.queryByText(/Gerbang fabrikasi/)).toBeNull();
});

test("gates and cost sit in their own titled panel, outside the rates table", () => {
  show(fixture as EvalSummary);

  const panel = screen.getByRole("heading", { name: "Gerbang dan biaya" }).parentElement as HTMLElement;
  expect(within(panel).getByText("Gerbang fabrikasi: lulus")).toBeDefined();
  expect(within(panel).getByText(/0,0012 USD/)).toBeDefined();
  expect(within(screen.getByRole("table")).queryByText(/Gerbang fabrikasi/)).toBeNull();
});
