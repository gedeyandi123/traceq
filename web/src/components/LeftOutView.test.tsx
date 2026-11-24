// The "left out by the system" screen over the fixture run folder (spec #105).
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
const otherAc: DroppedClaim = { claim: "acceptance", id: "URS-TP201-009", reason: "bad answer" };
const dropped = [...(run.dropped as DroppedClaim[]), humanAc];

function show(c: Completeness | null, items: DroppedClaim[] = dropped) {
  render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <LeftOutView dropped={items} completeness={c} />
    </NextIntlClientProvider>,
  );
}

test("an acceptance claim dropped for another reason stays in its kind group", () => {
  show(null, [...dropped, otherAc]);

  const group = within(screen.getByRole("region", { name: "Jenis: Kriteria penerimaan" }));
  expect(group.getByText("URS-TP201-009")).toBeDefined();
  expect(group.queryByText("URS-TP201-007")).toBeNull();
  const human = within(screen.getByRole("region", { name: "Kriteria penerimaan yang diserahkan ke manusia" }));
  expect(human.getByText("URS-TP201-007")).toBeDefined();
  expect(human.queryByText("URS-TP201-009")).toBeNull();
});

test("groups dropped claims by kind, apart from Acceptance Criteria left to a human", () => {
  show(completeness as Completeness);

  const req = within(screen.getByRole("region", { name: "Jenis: Persyaratan" }));
  expect(req.getByText("URS-TP201 p2")).toBeDefined();
  expect(req.getByText("bad answer")).toBeDefined();
  const value = within(screen.getByRole("region", { name: "Jenis: Nilai" }));
  expect(value.getByText("quote not on page or value not in it")).toBeDefined();
  expect(screen.queryByRole("region", { name: "Jenis: Kriteria penerimaan" })).toBeNull();

  const human = within(screen.getByRole("region", { name: "Kriteria penerimaan yang diserahkan ke manusia" }));
  expect(human.getByText("URS-TP201-007")).toBeDefined();
});

test("shows missed printed numbers and unquoted URS text", () => {
  show(completeness as Completeness);

  const check = within(screen.getByRole("region", { name: "Pemeriksaan kelengkapan URS" }));
  expect(check.getByText("Nomor persyaratan tercetak: 3 ditemukan, 1 tidak menjadi persyaratan.")).toBeDefined();
  expect(check.getByText("URS-TP201-003 (hlm. 1) tidak menjadi persyaratan")).toBeDefined();
  expect(check.getByText(/Spesifikasi Kebutuhan Pengguna \(SKP\)/)).toBeDefined();
});

test("says the check did not run for a run without the completeness artefact", () => {
  show(null);

  const check = within(screen.getByRole("region", { name: "Pemeriksaan kelengkapan URS" }));
  expect(check.getByText(/tidak dijalankan/)).toBeDefined();
  expect(screen.getByText("URS-TP201 p2")).toBeDefined();
});
