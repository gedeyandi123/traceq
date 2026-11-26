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
  size = "md",
  onCloseAutoFocus,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  headerExtra?: ReactNode;
  footer?: ReactNode;
  size?: "md" | "wide";
  onCloseAutoFocus?: (event: Event) => void;
  children: ReactNode;
}) {
  const t = useTranslations("ui");
  const widthClass = size === "wide" ? "md:w-[640px] xl:w-[760px]" : "md:w-[560px] xl:w-[640px]";
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="tq-fade-in fixed inset-0 z-50 bg-ink/25 backdrop-blur-[1px]" />
        <Dialog.Content
          onCloseAutoFocus={onCloseAutoFocus}
          data-tq-drawer=""
          className={`tq-slide-in-right fixed inset-y-0 right-0 z-50 flex w-full max-w-full flex-col border-l border-border bg-surface text-ink shadow-2xl outline-none ${widthClass}`}
        >
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border bg-surface px-4 py-2.5">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Dialog.Title className="m-0 text-sm font-bold text-ink tabular-nums">
                  {title}
                </Dialog.Title>
                {headerExtra && <div className="flex items-center gap-1.5">{headerExtra}</div>}
              </div>
              {description ? (
                <Dialog.Description
                  title={description}
                  className="mt-0.5 mb-0 truncate text-xs text-ink-muted"
                >
                  {description}
                </Dialog.Description>
              ) : (
                <Dialog.Description className="sr-only">{title}</Dialog.Description>
              )}
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                aria-label={t("closePanel")}
                className="inline-flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-md border border-border bg-surface text-ink-muted hover:bg-sunken hover:text-ink"
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
