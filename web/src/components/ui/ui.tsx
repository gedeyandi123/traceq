import type { ButtonHTMLAttributes, ReactNode, TableHTMLAttributes } from "react";

import type { CoverageClass } from "@/api/client";

// Shared UI primitives (spec #135, ADR 0014). Server-safe: no client state.

/** A Coverage class, or `none` when the system proposed no class. */
export type CoverageKey = CoverageClass | "none";

const BUTTON_VARIANTS = {
  primary: "bg-accent border-accent text-on-accent hover:bg-accent-hover hover:border-accent-hover",
  soft: "bg-accent-soft border-accent/35 text-accent hover:bg-accent hover:border-accent hover:text-on-accent",
  quiet: "bg-transparent border-transparent text-accent hover:bg-accent-soft",
  danger: "bg-fail-soft border-fail/35 text-fail hover:bg-fail hover:border-fail hover:text-on-accent",
} as const;

/** The four button variants: `primary` for the one main action of a screen, `soft` for an
 * action that repeats on every row, `quiet` for a secondary action, `danger` for destructive
 * or withdrawal actions. */
export function Button({
  variant,
  className,
  ...props
}: { variant: "primary" | "soft" | "quiet" | "danger" } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`inline-flex min-h-7 cursor-pointer items-center justify-center gap-2 rounded border px-3 text-xs font-semibold whitespace-nowrap transition-colors disabled:cursor-not-allowed disabled:opacity-55 ${BUTTON_VARIANTS[variant]} ${className ?? ""}`.trim()}
    />
  );
}

/** The heading of a section of a screen: title, an optional count, one line of what it is.
 * The id makes it an anchor and the name of the section it heads. */
export function SectionHeading({
  id,
  title,
  count,
  note,
}: {
  id: string;
  title: string;
  count?: number;
  note?: string;
}) {
  return (
    <div className="mb-3 flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <h2 id={id} className="m-0 scroll-mt-4 text-base font-semibold text-ink">
          {title}
        </h2>
        {count !== undefined && (
          <span className="inline-grid h-5 min-w-6 place-items-center rounded-full bg-sunken px-2 text-xs font-bold text-ink-muted tabular-nums">
            {count}
          </span>
        )}
      </div>
      {note !== undefined && <p className="m-0 max-w-[80ch] text-xs text-ink-muted">{note}</p>}
    </div>
  );
}

/** How a run was made (its translated mode), as a small badge; the run list and the run
 * header share it. */
export function ModeBadge({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full bg-accent-soft px-2 py-0.5 text-xs font-semibold whitespace-nowrap text-accent">
      {children}
    </span>
  );
}

/** A block that says there is nothing here, and why. Not an error. */
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-border-strong bg-surface p-5 text-center">
      <p className="m-0 font-semibold text-ink">{title}</p>
      {children !== undefined && (
        <div className="mx-auto mt-2 max-w-[60ch] text-sm text-ink-muted">{children}</div>
      )}
    </div>
  );
}

/** The one data-table style that left-out and eval share.
 * The frame scrolls sideways on its own on a narrow screen, never the page. */
export function DataTable({ className, ...props }: TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="relative overflow-x-auto rounded-lg border border-border bg-surface shadow-xs">
      <table
        {...props}
        className={`w-full border-collapse text-left text-sm [&_tbody_tr:hover_td]:bg-sunken/40 [&_tbody_tr:last-child_td]:border-b-0 [&_tbody_tr:last-child_th]:border-b-0 [&_td]:border-b [&_td]:border-border [&_td]:px-3 [&_td]:py-2.5 [&_td]:align-top [&_th]:border-b [&_th]:border-border [&_th]:px-3 [&_th]:py-2.5 [&_th]:align-top [&_thead_th]:bg-sunken/70 [&_thead_th]:py-2 [&_thead_th]:text-[11px] [&_thead_th]:font-semibold [&_thead_th]:tracking-wide [&_thead_th]:whitespace-nowrap [&_thead_th]:text-ink-muted [&_thead_th]:uppercase ${className ?? ""}`.trim()}
      />
    </div>
  );
}

/** Cell classes of the data table: `num` for figures (right-aligned, tabular), `id` for an
 * identifier that must not wrap. */
export const cell = {
  num: "text-right tabular-nums whitespace-nowrap",
  id: "font-semibold tabular-nums whitespace-nowrap",
} as const;
