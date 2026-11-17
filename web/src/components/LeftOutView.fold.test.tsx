// The left-out screen's folded unquoted URS text (spec #135, ticket #143).
import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { Completeness } from "@/api/client";
import messages from "../../messages/id.json";
import completeness from "../../../tests/fixtures/run/runs/20261113T090000Z-f1a2b3/completeness.json";
import { LeftOutView } from "./LeftOutView";

function show(c: Completeness) {
  render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <LeftOutView dropped={[]} completeness={c} />
    </NextIntlClientProvider>,
  );
}

test("the unquoted URS text sits behind a disclosure that carries its count", () => {
  show(completeness as Completeness);

  const check = within(screen.getByRole("region", { name: "Pemeriksaan kelengkapan URS" }));
  const toggle = check.getByText("Tampilkan teks (1)");
  expect(toggle.tagName).toBe("SUMMARY");
  const fold = toggle.closest("details");
  expect(fold).not.toBeNull();
  expect(fold?.open).toBe(false);
  expect(within(fold as HTMLElement).getByText(/Spesifikasi Kebutuhan Pengguna \(SKP\)/)).toBeDefined();
});

test("a URS with no unquoted text has nothing to open", () => {
  const all = completeness as Completeness;
  show({ urs: all.urs.map((u) => ({ ...u, unquoted: [] })) });

  const check = within(screen.getByRole("region", { name: "Pemeriksaan kelengkapan URS" }));
  expect(check.queryByText(/Tampilkan teks/)).toBeNull();
  expect(check.getByText("Tidak ada.")).toBeDefined();
});
