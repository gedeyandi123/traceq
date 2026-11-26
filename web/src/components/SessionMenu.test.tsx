import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { expect, test, vi } from "vitest";

import type { Session } from "@/auth/session";

import messages from "../../messages/id.json";
import { SessionMenu } from "./SessionMenu";

vi.mock("next/navigation", () => ({
  usePathname: () => "/runs/r1/protocol",
}));

const switchPersonaAction = vi.fn(async (_next: string) => {});
vi.mock("@/auth/actions", () => ({
  switchPersonaAction: (next: string) => switchPersonaAction(next),
}));

const session = {
  name: "Dewi",
  subject: "u-1",
  issuer: "http://kc/realms/traceq",
  username: "dewi",
  roles: [],
} as unknown as Session;

test("Ganti persona calls the server action with the current path", async () => {
  render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <SessionMenu session={session} signOutAction={async () => {}} />
    </NextIntlClientProvider>,
  );
  const trigger = screen.getByRole("button", { name: /Dewi/ });
  fireEvent.pointerDown(trigger);
  fireEvent.click(trigger);
  fireEvent.click(await screen.findByRole("menuitem", { name: /Ganti persona/ }));
  expect(switchPersonaAction).toHaveBeenCalledWith("/runs/r1/protocol");
});
