import { fireEvent, render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { vi } from "vitest";

import type { RunSummary } from "@/api/client";
import type { Session } from "@/auth/session";

import messages from "../../messages/id.json";
import { RunShell } from "./RunShell";
import { useRunShell } from "./RunShellContext";

let mockSegment: string | null = null;

vi.mock("next/navigation", () => ({
  useSelectedLayoutSegment: () => mockSegment,
  usePathname: () => "/runs/r7%20TP%2F201",
}));

const run: RunSummary = {
  run_id: "r7 TP/201",
  created: "2026-11-10T08:05:00Z",
  equipment: "TP-201",
  model: "claude-opus-5-5",
  mode: "replay",
  pipeline_version: "1",
};

const session: Session = {
  name: "Ayu Kartika Sari",
  mayDecide: true,
  mayApprove: false,
};

function renderShell(
  overrides: {
    run?: RunSummary;
    badges?: { matrix?: number; findings?: number; draft?: number };
    protocolStatus?: "draft" | "submitted" | "approved" | "withdrawn" | null;
    session?: Session | null;
  } = {},
) {
  const signOutAction = vi.fn(async () => {});
  render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <RunShell
        run={overrides.run ?? run}
        badges={overrides.badges}
        protocolStatus={overrides.protocolStatus}
        session={overrides.session === undefined ? session : overrides.session}
        signOutAction={signOutAction}
      >
        <div>Isi layar</div>
      </RunShell>
    </NextIntlClientProvider>,
  );
  return { signOutAction };
}

test("renders unnumbered workflow & audit links, omitting Draf protokol when review_package is absent", () => {
  mockSegment = null;
  renderShell({ badges: { matrix: 5, findings: 0 } });

  const nav = screen.getByRole("navigation", { name: "Layar run" });
  const links = within(nav).getAllByRole("link");
  expect(links.map((a) => a.getAttribute("href"))).toEqual([
    "/runs/r7%20TP%2F201",
    "/runs/r7%20TP%2F201/findings",
    "/runs/r7%20TP%2F201/protocol",
    "/runs/r7%20TP%2F201/left-out",
    "/runs/r7%20TP%2F201/eval",
  ]);
  expect(links[0]?.getAttribute("aria-current")).toBe("page");
  expect(within(nav).getByRole("link", { name: /Matriks & Triage/ }).textContent).toContain("5");
  expect(within(nav).getByText("Eksekusi & Deviasi")).toBeDefined();
  expect(within(nav).getByText("Tahap 5b")).toBeDefined();
});

test("includes Draf protokol and review_package metadata when review_package is present", () => {
  mockSegment = "draft";
  renderShell({
    run: {
      ...run,
      review_package: { package: "TP-201-OQ-draft", version: "0.1.0", doc_id: "OQ-TP201", rev: 0 },
    },
    badges: { draft: 3 },
  });

  const nav = screen.getByRole("navigation", { name: "Layar run" });
  const draftLink = within(nav).getByRole("link", { name: /Draf protokol/ });
  expect(draftLink.getAttribute("href")).toBe("/runs/r7%20TP%2F201/draft");
  expect(draftLink.getAttribute("aria-current")).toBe("page");
  expect(draftLink.textContent).toContain("3");
  expect(screen.getByText("OQ-TP201 rev 0 (TP-201-OQ-draft 0.1.0)")).toBeDefined();
});

test("context bar renders equipment, next-action CTA, and persona dropdown menu", async () => {
  mockSegment = null;
  renderShell();

  expect(screen.getByText("TP-201")).toBeDefined();
  expect(screen.getByRole("link", { name: /Lanjut ke Temuan pra-tinjauan/ }).getAttribute("href")).toBe(
    "/runs/r7%20TP%2F201/findings",
  );

  const personaBtn = screen.getByRole("button", { name: /Ayu Kartika Sari/ });
  expect(personaBtn).toBeDefined();
  fireEvent.pointerDown(personaBtn);
  fireEvent.click(personaBtn);

  expect(await screen.findByRole("menuitem", { name: /Ganti persona/ })).toBeDefined();
  expect(await screen.findByRole("menuitem", { name: /Keluar/ })).toBeDefined();
});

test("mobile navigation dialog opens on button click and closes on Escape", async () => {
  mockSegment = "findings";
  renderShell();

  const openBtn = screen.getByRole("button", { name: "Buka navigasi" });
  fireEvent.click(openBtn);

  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByRole("link", { name: /Temuan pra-tinjauan/ })).toBeDefined();

  fireEvent.keyDown(dialog, { key: "Escape" });
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("auto-collapses desktop sidebar to icon-rail (hiding section labels & brand text) when drawer opens below 1440px", () => {
  mockSegment = null;
  const origMatchMedia = window.matchMedia;
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));

  function DrawerTrigger() {
    const { setDrawerOpen } = useRunShell();
    return (
      <button type="button" onClick={() => setDrawerOpen(true)}>
        Buka drawer
      </button>
    );
  }

  try {
    const signOutAction = vi.fn(async () => {});
    render(
      <NextIntlClientProvider locale="id" messages={messages}>
        <RunShell run={run} session={session} signOutAction={signOutAction}>
          <DrawerTrigger />
        </RunShell>
      </NextIntlClientProvider>,
    );

    expect(screen.getByText("Alur kualifikasi")).toBeDefined();
    expect(screen.getByText("TraceQ")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Buka drawer" }));

    expect(screen.queryByText("Alur kualifikasi")).toBeNull();
    expect(screen.queryByText("TraceQ")).toBeNull();
  } finally {
    window.matchMedia = origMatchMedia;
  }
});
