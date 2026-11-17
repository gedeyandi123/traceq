import type { ButtonHTMLAttributes, ReactNode, TableHTMLAttributes } from "react";

import type { CoverageClass } from "@/api/client";

import t from "./table.module.css";
import s from "./ui.module.css";

// The shared primitives of every screen (spec #135, ADR 0011). Server Components only:
// none holds state, so none needs client JavaScript.

/** A Coverage class, or `none` when the system proposed no class. */
export type CoverageKey = CoverageClass | "none";

const SHAPES: Record<CoverageKey, string> = {
  covered_by_vendor: "●",
  partial: "◐",
  site_only: "○",
  gap: "▲",
  conflict: "◆",
  none: "–",
};

/** A Coverage class as a pill: its label after a shape, so colour is never the only sign.
 * The shape is hidden from screen readers; `help` (the class's meaning) shows on hover. */
export function CoveragePill({ cls, label, help }: { cls: CoverageKey; label: string; help?: string }) {
  return (
    <span className={`${s.pill} ${s[cls]}`} title={help}>
      <span aria-hidden="true" className={s.shape}>
        {SHAPES[cls]}
      </span>
      {label}
    </span>
  );
}

/** The three button variants: `primary` for the one main action of a screen, `soft` for an
 * action that repeats on every row, `quiet` for a secondary action. */
export function Button({
  variant,
  className,
  ...props
}: { variant: "primary" | "soft" | "quiet" } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button {...props} className={`${s.button} ${s[variant]} ${className ?? ""}`.trim()} />;
}

/** The one card of every screen's overview: a small title, then content. */
export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className={s.panel}>
      <h2 className={s.panelTitle}>{title}</h2>
      {children}
    </section>
  );
}

/** The heading of a section of a screen: title, an optional count, one line of what it is.
 * The id makes it an anchor and the name of the section it heads. */
export function SectionHeading({ id, title, count, note }: { id: string; title: string; count?: number; note?: string }) {
  return (
    <div className={s.section}>
      <div className={s.sectionTitle}>
        <h2 id={id}>{title}</h2>
        {count !== undefined && <span className={s.count}>{count}</span>}
      </div>
      {note !== undefined && <p className={s.note}>{note}</p>}
    </div>
  );
}

/** How a run was made (its translated mode), as a small badge; the run list and the run
 * header share it. */
export function ModeBadge({ children }: { children: ReactNode }) {
  return <span className={s.badge}>{children}</span>;
}

/** A block that says there is nothing here, and why. Not an error. */
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className={s.empty}>
      <p className={s.emptyTitle}>{title}</p>
      {children !== undefined && <div className={s.emptyBody}>{children}</div>}
    </div>
  );
}

/** The one data-table style that the matrix, findings, left-out, eval and run list share.
 * The frame scrolls sideways on its own on a narrow screen, never the page. */
export function DataTable({ className, ...props }: TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className={t.frame}>
      <table {...props} className={`${t.table} ${className ?? ""}`.trim()} />
    </div>
  );
}

/** Cell classes of the data table: `num` for figures (right-aligned, tabular), `id` for an
 * identifier that must not wrap. */
export const cell = { num: t.num, id: t.id } as const;
