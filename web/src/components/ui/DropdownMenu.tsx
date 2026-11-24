"use client";

import { DropdownMenu as RadixDropdownMenu } from "radix-ui";
import type { ComponentPropsWithoutRef } from "react";

export const DropdownMenu = RadixDropdownMenu.Root;
export const DropdownMenuTrigger = RadixDropdownMenu.Trigger;

export function DropdownMenuContent({
  className,
  sideOffset = 6,
  align = "end",
  ...props
}: ComponentPropsWithoutRef<typeof RadixDropdownMenu.Content>) {
  return (
    <RadixDropdownMenu.Portal>
      <RadixDropdownMenu.Content
        sideOffset={sideOffset}
        align={align}
        className={`z-50 min-w-[200px] rounded-md border border-border bg-surface p-1 text-ink shadow-lg outline-none ${className ?? ""}`.trim()}
        {...props}
      />
    </RadixDropdownMenu.Portal>
  );
}

export function DropdownMenuItem({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof RadixDropdownMenu.Item>) {
  return (
    <RadixDropdownMenu.Item
      className={`flex cursor-pointer items-center gap-2 rounded px-2.5 py-1.5 text-xs font-medium text-ink outline-none select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[highlighted]:bg-accent-soft data-[highlighted]:text-accent ${className ?? ""}`.trim()}
      {...props}
    />
  );
}

export function DropdownMenuLabel({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof RadixDropdownMenu.Label>) {
  return (
    <RadixDropdownMenu.Label
      className={`px-2.5 py-1.5 text-[11px] font-semibold text-ink-muted ${className ?? ""}`.trim()}
      {...props}
    />
  );
}

export function DropdownMenuSeparator({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof RadixDropdownMenu.Separator>) {
  return (
    <RadixDropdownMenu.Separator
      className={`my-1 h-px bg-border ${className ?? ""}`.trim()}
      {...props}
    />
  );
}
