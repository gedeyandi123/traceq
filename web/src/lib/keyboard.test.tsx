import { fireEvent, render } from "@testing-library/react";
import { vi } from "vitest";

import { openBlockingModal } from "@/components/modal.fixture";
import { useTriageKeyboardNav } from "./keyboard";

function Nav({ onSelect }: { onSelect: (id: string) => void }) {
  useTriageKeyboardNav({ items: ["a", "b"], selectedId: null, onSelect });
  return <button type="button">row</button>;
}

test("triage J/K navigates without a modal and does nothing while a modal dialog is open (#349)", () => {
  const onSelect = vi.fn();
  render(<Nav onSelect={onSelect} />);
  fireEvent.keyDown(window, { key: "j" });
  expect(onSelect).toHaveBeenCalledWith("a");
  onSelect.mockClear();
  const button = openBlockingModal();
  fireEvent.keyDown(button, { key: "j" });
  expect(onSelect).not.toHaveBeenCalled();
});
