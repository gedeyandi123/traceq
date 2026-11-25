"use client";

import { Tooltip as RadixTooltip } from "radix-ui";
import type { ComponentPropsWithoutRef } from "react";

export const TooltipProvider = RadixTooltip.Provider;
export const Tooltip = RadixTooltip.Root;
export const TooltipTrigger = RadixTooltip.Trigger;

export function TooltipContent({
  className,
  sideOffset = 6,
  ...props
}: ComponentPropsWithoutRef<typeof RadixTooltip.Content>) {
  return (
    <RadixTooltip.Portal>
      <RadixTooltip.Content
        sideOffset={sideOffset}
        className={`z-50 max-w-xs rounded-md border border-transparent bg-ink px-2.5 py-1.5 text-xs text-surface shadow-md ${className ?? ""}`.trim()}
        {...props}
      />
    </RadixTooltip.Portal>
  );
}
