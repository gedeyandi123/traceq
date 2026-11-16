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
        ]}
        action={() => {}}
      />
    </NextIntlClientProvider>,
  );

  expect(screen.getByText(/identitas demo/)).toBeDefined();
  expect(screen.getByRole("button", { name: "Masuk sebagai Ayu Kartika Sari" })).toBeDefined();
  expect(screen.getByRole("button", { name: "Masuk sebagai Citra Maharani Putri" })).toBeDefined();
  expect(screen.getByText("Dapat memutuskan")).toBeDefined();
  // Only the deciding role decides: another role reads, as no role does.
  expect(screen.getAllByText("Hanya membaca")).toHaveLength(2);
  expect(document.querySelector("input[type=password]")).toBeNull();
});
