// Test helper for the "shortcuts ignore an open modal" audit item (#349): mounts a real Modal
// next to the view under test, focuses its button, and counts the open dialogs in the document.
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import messages from "../../messages/id.json";
import { Modal } from "./ui/Modal";

export function openBlockingModal(): HTMLElement {
  render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <Modal
        open
        onOpenChange={() => {}}
        title="Tanda tangan"
        footer={<button type="button">Tanda tangani</button>}
      >
        isi
      </Modal>
    </NextIntlClientProvider>,
  );
  const button = screen.getByRole("button", { name: "Tanda tangani" });
  button.focus();
  return button;
}

export function openDialogCount(): number {
  return document.querySelectorAll('[role="dialog"][data-state="open"]').length;
}
