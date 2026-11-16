// The run header of the four run screens (spec #135, ticket #138).
import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { RunSummary } from "@/api/client";

import messages from "../../messages/id.json";
import { RunHeader, type RunTab } from "./RunHeader";

const run: RunSummary = {
  run_id: "r7 TP/201",
  created: "2026-11-10T08:05:00Z",
  equipment: "TP-201",
  model: "claude-opus-5-5",
  mode: "replay",
  pipeline_version: "1",
};
// The links the run screens carried before the header, run id URL-encoded.
const base = "/runs/r7%20TP%2F201";

function renderHeader(current: RunTab) {
  render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <RunHeader run={run} current={current} intro="Satu baris per persyaratan URS." />
    </NextIntlClientProvider>,
  );
}

test.each<[RunTab, string]>([
  ["matrix", "Matriks"],
  ["findings", "Temuan pra-tinjauan"],
  ["leftOut", "Yang tidak dimasukkan"],
  ["eval", "Hasil evaluasi"],
])("on the %s screen, four tabs link to the run's screens and only %s is current", (current, name) => {
  renderHeader(current);
  const tabs = within(screen.getByRole("navigation", { name: "Layar run" })).getAllByRole("link");
  expect(tabs.map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
    ["Matriks", base],
    ["Temuan pra-tinjauan", `${base}/findings`],
    ["Yang tidak dimasukkan", `${base}/left-out`],
    ["Hasil evaluasi", `${base}/eval`],
  ]);
  const marked = tabs.filter((a) => a.getAttribute("aria-current") !== null);
  expect(marked.map((a) => [a.textContent, a.getAttribute("aria-current")])).toEqual([[name, "page"]]);
});

test("the header leads back to all runs and names the run it shows", () => {
  renderHeader("matrix");
  const crumbs = screen.getByRole("navigation", { name: "Lokasi" });
  expect(within(crumbs).getByRole("link", { name: "Semua run" }).getAttribute("href")).toBe("/");
  expect(screen.getByRole("heading", { level: 1, name: "TP-201" })).toBeDefined();
  expect(screen.getByText("Putar ulang")).toBeDefined();
  expect(screen.getByText("r7 TP/201")).toBeDefined();
  expect(screen.getByText("claude-opus-5-5")).toBeDefined();
  expect(screen.getByText("10/11/2026 08.05 UTC")).toBeDefined();
  expect(screen.getByText("Satu baris per persyaratan URS.")).toBeDefined();
});
