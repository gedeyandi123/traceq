// The sign-in screen over the persona list (spec #105).
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import messages from "../../messages/id.json";
import { SignInView } from "./SignInView";

test("lists each demo persona as a demo identity, with no password field", () => {
  render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <SignInView
        personas={[
          { username: "ayu", name: "Ayu Kartika Sari", roles: ["qualification-decider"] },
          { username: "citra", name: "Citra Maharani Putri", roles: [] },
          { username: "budi", name: "Budi Santoso", roles: ["auditor"] },
          { username: "dewi", name: "Dewi Anggraini Lestari", roles: ["qualification-approver"] },
        ]}
        action={() => {}}
      />
    </NextIntlClientProvider>,
  );

  expect(screen.getByText(/identitas demo/)).toBeDefined();
  expect(screen.getByRole("button", { name: "Masuk sebagai Ayu Kartika Sari" })).toBeDefined();
  expect(screen.getByRole("button", { name: "Masuk sebagai Citra Maharani Putri" })).toBeDefined();
  expect(screen.getByText("Dapat memutuskan")).toBeDefined();
  expect(screen.getByRole("button", { name: "Masuk sebagai Dewi Anggraini Lestari" })).toBeDefined();
  expect(screen.getByText("Dapat menyetujui")).toBeDefined();
  // Only the deciding role decides: another role reads, as no role does.
  expect(screen.getAllByText("Hanya membaca")).toHaveLength(2);
  expect(document.querySelector("input[type=password]")).toBeNull();
});

test("preserves validated nextPath in hidden input and guards empty personas", () => {
  const { unmount } = render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <SignInView
        personas={[{ username: "ayu", name: "Ayu Kartika Sari", roles: ["qualification-decider"] }]}
        action={() => {}}
        nextPath="/runs/r1/protocol"
      />
    </NextIntlClientProvider>,
  );
  const nextInput = document.querySelector('input[name="next"]') as HTMLInputElement | null;
  expect(nextInput?.value).toBe("/runs/r1/protocol");
  unmount();

  render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <SignInView personas={[]} action={() => {}} />
    </NextIntlClientProvider>,
  );
  expect(screen.getByText("Belum ada persona demo yang tersedia.")).toBeDefined();
});
