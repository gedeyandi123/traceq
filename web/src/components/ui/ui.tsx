import type { ReactNode } from "react";

import type { CoverageClass } from "@/api/client";

import s from "./ui.module.css";

export type CoverageKey = CoverageClass | "none";

const SHAPES: Record<CoverageKey, string> = {
  covered_by_vendor: "●",
  partial: "◐",
  site_only: "○",
  gap: "▲",
  conflict: "◆",
  none: "–",
};

/** A Coverage class as a label with a shape, so the class never rests on colour alone. */
export function CoverageBadge({ cls, label }: { cls: CoverageKey; label: string }) {
  return (
    <span className={`${s.badge} ${s[`cov_${cls}`]}`}>
      <span aria-hidden="true" className={s.shape}>
        {SHAPES[cls]}
      </span>
      {label}
    </span>
  );
}

/** A note block: info for read-only, alert for an error, success and warning for gates. */
export function Callout({
  tone,
  children,
  role,
}: {
  tone: "info" | "alert" | "success" | "warning";
  children: ReactNode;
  role?: "alert" | "status";
}) {
  return (
    <div className={`${s.callout} ${s[tone]}`} role={role}>
      {children}
    </div>
  );
}

/** A panel that says there is nothing here, and why. */
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className={s.empty}>
      <p className={s.emptyTitle}>{title}</p>
      {children && <div className={s.emptyBody}>{children}</div>}
    </div>
  );
}

/** A section of a screen: heading, one line of context, a count, then content. */
export function Section({
  id,
  title,
  note,
  count,
  children,
  label,
}: {
  id?: string;
  title: string;
  note?: string;
  count?: number;
  children: ReactNode;
  label?: string;
}) {
  return (
    <section className={s.section} aria-labelledby={label ? undefined : id} aria-label={label}>
      <div className={s.sectionHead}>
        <h2 id={id}>{title}</h2>
        {count !== undefined && <span className={s.count}>{count}</span>}
      </div>
      {note && <p className={s.note}>{note}</p>}
      {children}
    </section>
  );
}
