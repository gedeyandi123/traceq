// The left-out screen's summary panel: one count per section, each a jump link (#158).
import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { Completeness, DroppedClaim } from "@/api/client";
import messages from "../../messages/id.json";
import completeness from "../../../tests/fixtures/run/runs/20261113T090000Z-f1a2b3/completeness.json";
import run from "../../../tests/fixtures/run/runs/20261113T090000Z-f1a2b3/run.json";
import { LeftOutView } from "./LeftOutView";

const humanAc: DroppedClaim = {
  claim: "acceptance",
  id: "URS-TP201-007",
  reason: "to be set by a human: no source cited",
};
const dropped = [...(run.dropped as DroppedClaim[]), humanAc];

function summaryLinks(c: Completeness | null) {
  render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <LeftOutView dropped={dropped} completeness={c} />
    </NextIntlClientProvider>,
  );
  const summary = within(screen.getByRole("list", { name: "Ringkasan" }));
  return summary.getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")]);
}

test("the summary counts each section of the fixture run and links to it", () => {
  expect(summaryLinks(completeness as Completeness)).toEqual([
    ["2 Klaim yang dibuang pemeriksaan kutipan", "#dropped-claims"],
    ["1 Kriteria penerimaan yang diserahkan ke manusia", "#human-ac"],
    ["1 Teks URS tidak dikutip", "#completeness"],
  ]);
});

test("the unquoted count is absent when no completeness check ran", () => {
  expect(summaryLinks(null)).toEqual([
    ["2 Klaim yang dibuang pemeriksaan kutipan", "#dropped-claims"],
    ["1 Kriteria penerimaan yang diserahkan ke manusia", "#human-ac"],
  ]);
});
