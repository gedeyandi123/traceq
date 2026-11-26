import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { vi } from "vitest";

import type { RunSummary } from "@/api/client";

import messages from "../../messages/id.json";
import { RunSidebar } from "./RunSidebar";
import { TooltipProvider } from "./ui/Tooltip";

vi.mock("next/navigation", () => ({
  useSelectedLayoutSegment: () => null,
  usePathname: () => "/runs/r7",
}));

const run: RunSummary = {
  run_id: "r7",
  created: "2026-11-10T08:05:00Z",
  equipment: "TP-201",
  model: "claude-opus-5-5",
  mode: "replay",
  pipeline_version: "1",
};

function renderSidebar(collapsed: boolean, badges = { matrix: 5, findings: 0 }) {
  render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <TooltipProvider>
        <RunSidebar
          run={run}
          badges={badges}
          collapsed={collapsed}
          autoCollapsedForDrawer={false}
          onToggleCollapse={() => {}}
          mobileOpen={false}
          onMobileOpenChange={() => {}}
        />
      </TooltipProvider>
    </NextIntlClientProvider>,
  );
  return within(screen.getByRole("navigation", { name: "Layar run" }));
}

test("collapsed links keep an accessible name: the label, plus the count when there is one", () => {
  const nav = renderSidebar(true);

  // The visible text is gone when collapsed: the name must come from aria-label.
  const matrix = nav.getByRole("link", { name: "Matriks & triase (5 belum diputuskan)" });
  expect(matrix.getAttribute("href")).toBe("/runs/r7");
  expect(matrix.getAttribute("aria-label")).toBe("Matriks & triase (5 belum diputuskan)");

  const report = nav.getByRole("link", { name: "Laporan Kualifikasi" });
  expect(report.getAttribute("aria-label")).toBe("Laporan Kualifikasi");
  // Every link of the collapsed nav is named.
  for (const link of nav.getAllByRole("link")) {
    expect((link.getAttribute("aria-label") ?? "").length).toBeGreaterThan(0);
  }
});

test("expanded links are named by their visible text, with no redundant aria-label", () => {
  const nav = renderSidebar(false);
  const report = nav.getByRole("link", { name: /Laporan Kualifikasi/ });
  expect(report.getAttribute("aria-label")).toBeNull();
});
