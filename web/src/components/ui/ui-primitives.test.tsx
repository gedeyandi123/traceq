import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { DirtyGuardBanner } from "./DirtyGuardBanner";
import { FilterBar } from "./FilterBar";

describe("shared UI primitives", () => {
  it("renders DirtyGuardBanner as alertdialog and triggers discard/keep callbacks", () => {
    const onDiscard = vi.fn();
    const onKeep = vi.fn();
    render(
      <DirtyGuardBanner
        message="Perubahan belum disimpan."
        discardLabel="Buang perubahan"
        keepLabel="Tetap menyunting"
        onDiscard={onDiscard}
        onKeep={onKeep}
      />,
    );

    const dialog = screen.getByRole("alertdialog", { name: "Perubahan belum disimpan." });
    expect(dialog).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Buang perubahan" }));
    expect(onDiscard).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Tetap menyunting" }));
    expect(onKeep).toHaveBeenCalledTimes(1);
  });

  it("renders FilterBar pills with aria-pressed and invokes onSelect", () => {
    const onSelect = vi.fn();
    render(
      <FilterBar
        ariaLabel="Filter baris"
        options={[
          { id: "all", label: "Semua", count: 10 },
          { id: "blocking", label: "Memblokir", count: 2 },
        ]}
        activeId="all"
        onSelect={onSelect}
      />,
    );

    const allBtn = screen.getByRole("button", { name: /Semua/ });
    const blockBtn = screen.getByRole("button", { name: /Memblokir/ });
    expect(allBtn.getAttribute("aria-pressed")).toBe("true");
    expect(blockBtn.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(blockBtn);
    expect(onSelect).toHaveBeenCalledWith("blocking");
  });
});
