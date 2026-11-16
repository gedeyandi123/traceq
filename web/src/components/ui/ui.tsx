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

/** A Coverage class as a label with a shape, so the class never rests on colour alone.
 * ``help`` is the class's meaning, shown on hover. */
export function CoverageBadge({ cls, label, help }: { cls: CoverageKey; label: string; help?: string }) {
  return (
    <span className={`${s.badge} ${s[`cov_${cls}`]}`} title={help}>
      <span aria-hidden="true" className={s.shape}>
        {SHAPES[cls]}
      </span>
      {label}
    </span>
  );
}

/** A note block: info for read-only, alert for an error. */
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

/** A summary card: a small title, then content. Every screen's overview uses it. */
export function Panel({ title, children, aside }: { title?: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <div className={s.panel}>
      {(title || aside) && (
        <div className={s.panelHead}>
          {title && <h2 className={s.panelTitle}>{title}</h2>}
          {aside}
        </div>
      )}
      {children}
    </div>
  );
}

/** A row of counts, each optionally linking to the section it counts. */
export function StatList({
  items,
}: {
  items: readonly { n: number; label: ReactNode; href?: string; tone?: "attention" }[];
}) {
  return (
    <ul className={s.stats}>
      {items.map((it, i) => {
        const body = (
          <>
            <span className={`${s.statN} ${it.tone === "attention" && it.n > 0 ? s.attention : ""}`}>{it.n}</span>
            <span className={s.statLabel}>{it.label}</span>
          </>
        );
        return (
          <li key={i}>
            {it.href ? (
              <a href={it.href} className={s.stat}>
                {body}
              </a>
            ) : (
              <span className={s.stat}>{body}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** The heading of a section of a screen: title, count, one line of what it is. The id makes
 * it the section's accessible name and an anchor target. */
export function SectionHead({ id, title, count, note }: { id: string; title: string; count?: number; note?: string }) {
  return (
    <div className={s.sectionHead}>
      <div className={s.sectionTitle}>
        <h2 id={id}>{title}</h2>
        {count !== undefined && <span className={s.count}>{count}</span>}
      </div>
      {note && <p className={s.note}>{note}</p>}
    </div>
  );
}

/** A progress bar of decided proposals. */
export function Progress({ done, total, label }: { done: number; total: number; label: string }) {
  const pct = total === 0 ? 0 : Math.round((done / total) * 100);
  return (
    <div className={s.progress}>
      <div className={s.progressText}>
        <span className={s.progressN}>
          {done}/{total}
        </span>
        <span>{label}</span>
      </div>
      <span className={s.progressTrack} aria-hidden="true">
        <span className={s.progressFill} style={{ width: `${pct}%` }} />
      </span>
    </div>
  );
}
