import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/id.json";
import { Drawer } from "./Drawer";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./DropdownMenu";
import { Modal } from "./Modal";
import { PdfCitationButton } from "./PdfCitationModal";
import {
  CoverageStatusBadge,
  DecisionStateBadge,
  ProtocolStatusBadge,
} from "./StatusBadge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./Tabs";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./Tooltip";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderWithIntl(ui: ReactNode) {
  return render(
    <NextIntlClientProvider locale="id" messages={messages}>
      {ui}
    </NextIntlClientProvider>,
  );
}

describe("Owned Radix UI primitives", () => {
  it("CoverageStatusBadge renders explicit Indonesian label for all 6 classes", () => {
    const { container } = renderWithIntl(
      <div>
        <CoverageStatusBadge coverage="covered_by_vendor" />
        <CoverageStatusBadge coverage="partial" />
        <CoverageStatusBadge coverage="site_only" />
        <CoverageStatusBadge coverage="gap" />
        <CoverageStatusBadge coverage="conflict" />
        <CoverageStatusBadge coverage="none" />
      </div>,
    );

    expect(screen.getByText("Dicakup vendor")).toBeTruthy();
    expect(screen.getByText("Sebagian")).toBeTruthy();
    expect(screen.getByText("Hanya di lokasi")).toBeTruthy();
    expect(screen.getByText("Celah")).toBeTruthy();
    expect(screen.getByText("Konflik")).toBeTruthy();
    expect(screen.getByText("Belum dinilai")).toBeTruthy();
    expect(container.querySelectorAll("svg").length).toBe(6);
  });

  it("DecisionStateBadge and ProtocolStatusBadge render Indonesian labels with icons", () => {
    const { container } = renderWithIntl(
      <div>
        <DecisionStateBadge state="undecided" />
        <DecisionStateBadge state="decided" />
        <DecisionStateBadge state="changed" />
        <DecisionStateBadge state="accepted" />
        <DecisionStateBadge state="edited" />
        <DecisionStateBadge state="rejected" />
        <ProtocolStatusBadge status="draft" />
        <ProtocolStatusBadge status="submitted" />
        <ProtocolStatusBadge status="approved" />
        <ProtocolStatusBadge status="withdrawn" />
      </div>,
    );

    expect(screen.getByText("Belum diputuskan")).toBeTruthy();
    expect(screen.getByText("Sudah diputuskan")).toBeTruthy();
    expect(screen.getByText("Isi berubah")).toBeTruthy();
    expect(screen.getByText("Diterima")).toBeTruthy();
    expect(screen.getByText("Diubah")).toBeTruthy();
    expect(screen.getByText("Ditolak")).toBeTruthy();
    expect(screen.getByText("Draft")).toBeTruthy();
    expect(screen.getByText("Diajukan")).toBeTruthy();
    expect(screen.getByText("Disetujui")).toBeTruthy();
    expect(screen.getByText("Ditarik")).toBeTruthy();
    expect(container.querySelectorAll("svg").length).toBe(10);
  });

  it("Drawer opens with accessible dialog title and closes on Escape", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    renderWithIntl(
      <Drawer open={true} onOpenChange={onOpenChange} title="URS-TP201-001">
        <p>Detail persyaratan</p>
      </Drawer>,
    );

    const dialog = await screen.findByRole("dialog", { name: "URS-TP201-001" });
    expect(dialog).toBeTruthy();

    await user.keyboard("{Escape}");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("Modal renders dialog and closes via close button", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    renderWithIntl(
      <Modal open={true} onOpenChange={onOpenChange} size="wide" title="Sitasi: SAT-TP201">
        <div>Isi modal</div>
      </Modal>,
    );

    expect(await screen.findByRole("dialog", { name: "Sitasi: SAT-TP201" })).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Tutup dialog" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("PdfCitationButton renders PDF iframe on HEAD 200 application/pdf", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, {
        status: 200,
        headers: { "content-type": "application/pdf" },
      }),
    );

    renderWithIntl(
      <PdfCitationButton
        runId="run-1"
        cite={{ doc: "SAT-TP201", rev: 0, page: 3, quote: "20.4 kN" }}
      />,
    );

    await user.click(screen.getByRole("button", { name: "SAT-TP201 rev 0, hlm. 3" }));
    const iframe = await screen.findByTitle("SAT-TP201 rev 0, hlm. 3");
    expect(iframe.getAttribute("src")).toContain("/api/runs/run-1/documents/SAT-TP201/0#page=3");
    expect(screen.getAllByText(/20.4 kN/).length).toBeGreaterThan(0);
  });

  it("PdfCitationButton renders fallback card on non-PDF", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(null, {
        status: 200,
        headers: {
          "content-type":
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
      }),
    );

    renderWithIntl(
      <PdfCitationButton
        runId="run-1"
        cite={{ doc: "DS-TP201", rev: 0, page: 1, quote: "Sheet 1" }}
      />,
    );

    await user.click(screen.getByRole("button", { name: "DS-TP201 rev 0, hlm. 1" }));
    expect(await screen.findByText("Unduh lembar kerja")).toBeTruthy();
    expect(screen.queryByTitle("DS-TP201 rev 0, hlm. 1")).toBeNull();
  });

  it("PdfCitationButton renders alert on 404", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(null, { status: 404 }));

    renderWithIntl(
      <PdfCitationButton
        runId="run-1"
        cite={{ doc: "MISSING-DOC", rev: 0, page: 1, quote: "" }}
      />,
    );

    await user.click(screen.getByRole("button", { name: "MISSING-DOC rev 0, hlm. 1" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
  });

  it("DropdownMenu opens on trigger click and invokes onSelect", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    renderWithIntl(
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button type="button" data-tw="">
            Menu Persona
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onSelect={onSelect}>Keluar</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>,
    );

    await user.click(screen.getByRole("button", { name: "Menu Persona" }));
    const item = await screen.findByRole("menuitem", { name: "Keluar" });
    await user.click(item);
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("Tabs switches active panel and updates aria-selected", async () => {
    const user = userEvent.setup();
    renderWithIntl(
      <Tabs defaultValue="rows">
        <TabsList>
          <TabsTrigger value="rows">Baris</TabsTrigger>
          <TabsTrigger value="frozen">Salinan beku</TabsTrigger>
        </TabsList>
        <TabsContent value="rows">Konten baris</TabsContent>
        <TabsContent value="frozen">Konten salinan beku</TabsContent>
      </Tabs>,
    );

    const frozenTab = screen.getByRole("tab", { name: "Salinan beku" });
    expect(frozenTab.getAttribute("aria-selected")).toBe("false");
    await user.click(frozenTab);
    expect(frozenTab.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("Konten salinan beku")).toBeTruthy();
  });

  it("Tooltip renders content on focus", async () => {
    const user = userEvent.setup();
    renderWithIntl(
      <TooltipProvider delayDuration={0}>
        <Tooltip>
          <TooltipTrigger asChild>
            <button type="button" data-tw="">
              Info
            </button>
          </TooltipTrigger>
          <TooltipContent>Penjelasan singkat</TooltipContent>
        </Tooltip>
      </TooltipProvider>,
    );

    await user.tab();
    expect(await screen.findByRole("tooltip")).toBeTruthy();
  });
});
