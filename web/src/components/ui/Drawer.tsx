"use client";

import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { Dialog } from "radix-ui";
import type { ReactNode } from "react";

export function Drawer({
  open,
  onOpenChange,
  title,
  description,
  headerExtra,
  footer,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  headerExtra?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}) {
  const t = useTranslations("ui");
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink/25 backdrop-blur-[1px]" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-full max-w-full flex-col border-l border-border bg-surface text-ink shadow-2xl outline-none md:w-[560px] xl:w-[640px]">
          <div className="flex shrink-0 items-start justify-between gap-3 border-b border-border bg-surface px-5 py-3.5">
            <div className="min-w-0 flex-1">
              <Dialog.Title className="m-0 text-base font-bold text-ink tabular-nums">
                {title}
              </Dialog.Title>
              {description ? (
                <Dialog.Description className="mt-0.5 mb-0 text-xs text-ink-muted">
                  {description}
                </Dialog.Description>
              ) : (
                <Dialog.Description className="sr-only">{title}</Dialog.Description>
              )}
              {headerExtra && <div className="mt-2">{headerExtra}</div>}
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                data-tw=""
                aria-label={t("closePanel")}
                className="inline-flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-md border border-border bg-surface text-ink-muted hover:bg-sunken hover:text-ink"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </Dialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
          {footer && (
            <div className="shrink-0 border-t border-border bg-canvas px-5 py-3">{footer}</div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
