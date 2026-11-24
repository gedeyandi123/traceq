"use client";

import { Tabs as RadixTabs } from "radix-ui";
import type { ComponentPropsWithoutRef } from "react";

export const Tabs = RadixTabs.Root;

export function TabsList({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof RadixTabs.List>) {
  return (
    <RadixTabs.List
      className={`inline-flex max-w-full items-center gap-1 overflow-x-auto border-b border-border bg-transparent ${className ?? ""}`.trim()}
      {...props}
    />
  );
}

export function TabsTrigger({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof RadixTabs.Trigger>) {
  return (
    <RadixTabs.Trigger
      className={`inline-flex shrink-0 cursor-pointer items-center gap-1.5 border-b-2 border-transparent px-3 py-2 text-xs font-semibold whitespace-nowrap text-ink-muted transition-colors hover:text-ink data-[state=active]:border-accent data-[state=active]:text-accent ${className ?? ""}`.trim()}
      {...props}
    />
  );
}

export function TabsContent({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof RadixTabs.Content>) {
  return (
    <RadixTabs.Content
      className={`pt-4 outline-none ${className ?? ""}`.trim()}
      {...props}
    />
  );
}
