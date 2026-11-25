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
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTypingTarget(e.target)) return;
      if (e.key !== "j" && e.key !== "J" && e.key !== "k" && e.key !== "K") return;
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
