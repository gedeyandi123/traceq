// The 404 page of every route and of an unknown run (spec #135, ticket #140).
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import messages from "../../messages/id.json";
import { NotFoundView } from "./NotFoundView";

test("the 404 page names what happened and leads back to the run list", () => {
  render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <NotFoundView />
    </NextIntlClientProvider>,
  );

  expect(screen.getByRole("heading", { level: 1, name: "Halaman tidak ditemukan" })).toBeDefined();
  expect(screen.getByRole("link", { name: "Kembali ke daftar run" }).getAttribute("href")).toBe("/");
});
