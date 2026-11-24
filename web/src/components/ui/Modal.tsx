"use client";

import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { Dialog } from "radix-ui";
import type { ReactNode } from "react";

export function Modal({
  open,
  onOpenChange,
  title,
  description,
  size = "sm",
  headerActions,
  footer,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  size?: "sm" | "wide";
  headerActions?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}) {
  const t = useTranslations("ui");
  const sizeClass =
    size === "wide"
      ? "h-[85vh] w-[94vw] max-w-[1400px] md:w-[85vw]"
      : "max-h-[85vh] w-[92vw] max-w-md";

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink/40 backdrop-blur-[1px]" />
        <Dialog.Content
          className={`fixed top-1/2 left-1/2 z-50 flex -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg border border-border bg-surface text-ink shadow-2xl outline-none ${sizeClass}`}
        >
          <div className="flex shrink-0 items-start justify-between gap-3 rounded-t-lg border-b border-border bg-surface px-5 py-3.5">
            <div className="min-w-0 flex-1">
              <Dialog.Title className="m-0 text-sm font-bold text-ink">{title}</Dialog.Title>
              {description ? (
                <Dialog.Description className="mt-1 mb-0 text-xs leading-relaxed text-ink-muted">
                  {description}
                </Dialog.Description>
              ) : (
                <Dialog.Description className="sr-only">{title}</Dialog.Description>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {headerActions}
              <Dialog.Close asChild>
                <button
                  type="button"
                  data-tw=""
                  aria-label={t("closeDialog")}
                  className="inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-md border border-border bg-surface text-ink-muted hover:bg-sunken hover:text-ink"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </Dialog.Close>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-5">{children}</div>
          {footer && (
            <div className="flex shrink-0 items-center justify-end gap-2 rounded-b-lg border-t border-border bg-canvas px-5 py-3">
              {footer}
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
