"use client";

import { useEffect } from "react";

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.closest(
      'input, textarea, select, [contenteditable], [contenteditable="true"], [role="listbox"], [role="menu"], [role="combobox"]',
    ) !== null
  );
}

// A modal (Modal, PdfCitationModal, signature dialogs, alert dialogs) is open. The row Drawer is
// also a Radix dialog but carries `data-tq-drawer`: it is the surface J/K navigates, so it does
// not count. Row shortcuts must do nothing while this is true (#349).
export function isModalOpen(): boolean {
  return (
    document.querySelector(
      '[role="dialog"][data-state="open"]:not([data-tq-drawer]), [role="alertdialog"][data-state="open"]',
    ) !== null
  );
}

// Shared guard for the window-level J/K row shortcuts.
export function shouldIgnoreRowShortcut(e: KeyboardEvent): boolean {
  if (e.ctrlKey || e.metaKey || e.altKey) return true;
  if (e.key !== "j" && e.key !== "J" && e.key !== "k" && e.key !== "K") return true;
  return isTypingTarget(e.target) || isModalOpen();
}

export function useTriageKeyboardNav<T extends string>({
  items,
  selectedId,
  onSelect,
  enabled = true,
}: {
  items: readonly T[];
  selectedId: T | null;
  onSelect: (id: T) => void;
  enabled?: boolean;
}) {
  useEffect(() => {
    if (!enabled || items.length === 0) return;
    const handleKey = (e: KeyboardEvent) => {
      if (shouldIgnoreRowShortcut(e)) return;
      e.preventDefault();
      const idx = selectedId !== null ? items.indexOf(selectedId) : -1;
      const forward = e.key === "j" || e.key === "J";
      const nextIdx = forward
        ? idx < 0
          ? 0
          : Math.min(items.length - 1, idx + 1)
        : idx < 0
          ? items.length - 1
          : Math.max(0, idx - 1);
      const nextId = items[nextIdx];
      if (nextId !== undefined) onSelect(nextId);
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [enabled, items, onSelect, selectedId]);
}
