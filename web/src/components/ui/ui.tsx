import type { ButtonHTMLAttributes, ReactNode, TableHTMLAttributes } from "react";

import type { CoverageClass } from "@/api/client";

import { AlertCircleIcon, AlertTriangleIcon, CheckCircleIcon, ChevronRightIcon, InfoIcon } from "./icons";
import t from "./table.module.css";
import s from "./ui.module.css";

// The shared primitives of every screen (spec #135, ADR 0011, ui-contract.md). Server Components
// only: none holds state, so none needs client JavaScript.

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

/** The four button variants: `primary` for the one main action of a screen, `soft` for an
 * action that repeats on every row, `quiet` for a secondary action, `danger` for destructive
 * or withdrawal actions. */
export function Button({
  variant,
  className,
  ...props
}: { variant: "primary" | "soft" | "quiet" | "danger" } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button {...props} className={`${s.button} ${s[variant]} ${className ?? ""}`.trim()} />;
}

/** Semantic tone for StatusBadge and Alert. */
export type SemanticTone = "neutral" | "info" | "pass" | "warn" | "fail";

/** A compact semantic status pill for protocol, decision, or execution states. */
export function StatusBadge({
  tone,
  children,
  className,
}: {
  tone: SemanticTone;
  children: ReactNode;
  className?: string;
}) {
  return <span className={`${s.statusBadge} ${s[`tone_${tone}`]} ${className ?? ""}`.trim()}>{children}</span>;
}

const ALERT_ICONS = {
  info: InfoIcon,
  warn: AlertTriangleIcon,
  fail: AlertCircleIcon,
  pass: CheckCircleIcon,
} as const;

/** A structured callout banner with a leading icon and semantic accent border. */
export function Alert({
  tone,
  role,
  title,
  children,
  className,
}: {
  tone: Exclude<SemanticTone, "neutral">;
  role?: "alert" | "status";
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  const Icon = ALERT_ICONS[tone];
  return (
    <div role={role} className={`${s.alert} ${s[`alert_${tone}`]} ${className ?? ""}`.trim()}>
      <Icon className={s.alertIcon} />
      <div className={s.alertBody}>
        {title !== undefined && <div className={s.alertTitle}>{title}</div>}
        <div>{children}</div>
      </div>
    </div>
  );
}

/** Accessible progress bar for decision or execution completion. */
export function ProgressBar({
  value,
  max,
  label,
  className,
}: {
  value: number;
  max: number;
  label: string;
  className?: string;
}) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-label={label}
      className={`${s.progressTrack} ${className ?? ""}`.trim()}
    >
      <div className={s.progressFill} style={{ width: `${pct}%` }} />
    </div>
  );
}

/** Native `<details>`/`<summary>` wrapper styled with tokens; text stays in the DOM. */
export function Disclosure({
  summary,
  defaultOpen,
  children,
  className,
}: {
  summary: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <details open={defaultOpen} className={`${s.disclosure} ${className ?? ""}`.trim()}>
      <summary className={s.disclosureSummary}>{summary}</summary>
      <div className={s.disclosureBody}>{children}</div>
    </details>
  );
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

/** A screen's summary in a panel: one count per section, each a link to the section's anchor.
 * The findings and left-out screens share it. */
export function SummaryLinks({
  title,
  items,
}: {
  title: string;
  items: readonly { n: number; label: string; href: string }[];
}) {
  return (
    <Panel title={title}>
      <ul className={s.summaryLinks} aria-label={title}>
        {items.map((item) => (
          <li key={item.href}>
            <a href={item.href} className={item.n === 0 ? s.zero : undefined}>
              <span className={s.summaryCount}>{item.n}</span> {item.label}
            </a>
          </li>
        ))}
      </ul>
    </Panel>
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

/** Guided handoff bar linking to the next workflow screens. */
export function HandoffBar({
  label,
  links,
}: {
  label: string;
  links: readonly { href: string; text: string }[];
}) {
  return (
    <nav aria-label={label} className={s.handoff}>
      <span className={s.handoffLabel}>{label}</span>
      <div className={s.handoffLinks}>
        {links.map((item) => (
          <a key={item.href} href={item.href} className={s.handoffLink}>
            <span>{item.text}</span>
            <ChevronRightIcon />
          </a>
        ))}
      </div>
    </nav>
  );
}
