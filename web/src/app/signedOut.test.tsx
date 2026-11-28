import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../messages/id.json";

const { session, get } = vi.hoisted(() => ({
  session: vi.fn<() => Promise<unknown>>(),
  get: vi.fn(),
}));

vi.mock("@/auth/session", () => ({
  currentSession: session,
  bearerHeaders: vi.fn(async () => ({})),
}));
vi.mock("@/api/client", () => ({ api: { GET: get } }));
vi.mock("@/auth/actions", () => ({ signOutAction: vi.fn() }));
vi.mock("next-intl/server", () => ({
  getTranslations: async (ns: string) => (key: string) =>
    (messages as unknown as Record<string, Record<string, string>>)[ns]?.[key] ?? `${ns}.${key}`,
  getMessages: async () => messages,
}));
vi.mock("@/i18n/request", () => ({ LOCALE: "id" }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

import RunsPage from "./(home)/page";
import RunWorkspaceLayout from "./(run)/runs/[runId]/layout";

describe("signed out", () => {
  beforeEach(() => {
    session.mockResolvedValue(null);
    get.mockReset();
  });

  it("a run screen shows the sign-in prompt, not a not-found, and loads nothing", async () => {
    const ui = await RunWorkspaceLayout({
      params: Promise.resolve({ runId: "run-1" }),
      children: <p>run content</p>,
    });
    render(ui);
    expect(screen.getByText(messages.runs.signedOutTitle)).toBeTruthy();
    expect(screen.queryByText("run content")).toBeNull();
    const link = screen.getByRole("link", { name: messages.signin.link });
    expect(link.getAttribute("href")).toBe("/signin?next=%2Fruns%2Frun-1");
    expect(get).not.toHaveBeenCalled();
  });

  it("the home list asks to sign in instead of saying the API is down", async () => {
    render(await RunsPage());
    expect(screen.getByText(messages.runs.signedOutTitle)).toBeTruthy();
    expect(screen.queryByText(messages.runs.unavailableTitle)).toBeNull();
    expect(get).not.toHaveBeenCalled();
  });
});
