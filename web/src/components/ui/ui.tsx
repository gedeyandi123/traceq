import type { ButtonHTMLAttributes, ReactNode, TableHTMLAttributes } from "react";

import type { CoverageClass } from "@/api/client";

import { AlertCircleIcon, AlertTriangleIcon, CheckCircleIcon, ChevronRightIcon, InfoIcon } from "./icons";

// Shared UI primitives (spec #135, ADR 0014). Server-safe: no client state.

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

const PILL_TONES: Record<CoverageKey, string> = {
  covered_by_vendor: "text-cov-covered-fg bg-cov-covered-bg border-cov-covered-edge",
  partial: "text-cov-partial-fg bg-cov-partial-bg border-cov-partial-edge",
  site_only: "text-cov-site-fg bg-cov-site-bg border-cov-site-edge",
  gap: "text-cov-gap-fg bg-cov-gap-bg border-cov-gap-edge",
  conflict: "text-cov-conflict-fg bg-cov-conflict-bg border-cov-conflict-edge",
  none: "text-cov-none-fg bg-cov-none-bg border-cov-none-edge",
};

/** A Coverage class as a pill: its label after a shape, so colour is never the only sign.
 * The shape is hidden from screen readers; `help` (the class's meaning) shows on hover. */
export function CoveragePill({ cls, label, help }: { cls: CoverageKey; label: string; help?: string }) {
  return (
    <span
      className={`inline-flex min-h-5.5 items-center gap-1.5 rounded-full border pr-2 pl-1.5 text-xs leading-tight font-semibold whitespace-nowrap align-middle ${PILL_TONES[cls]} ${help ? "cursor-help" : ""}`.trim()}
      title={help}
    >
      <span aria-hidden="true" className="text-[0.85em] leading-none">
        {SHAPES[cls]}
      </span>
      {label}
    </span>
  );
}

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
      data-tw=""
      className={`inline-flex min-h-7 cursor-pointer items-center justify-center gap-2 rounded border px-3 text-xs font-semibold whitespace-nowrap transition-colors disabled:cursor-not-allowed disabled:opacity-55 ${BUTTON_VARIANTS[variant]} ${className ?? ""}`.trim()}
    />
  );
}

/** Semantic tone for StatusBadge and Alert. */
export type SemanticTone = "neutral" | "info" | "pass" | "warn" | "fail";

const BADGE_TONES: Record<SemanticTone, string> = {
  neutral: "bg-sunken border-border-strong text-ink-muted",
  info: "bg-info-soft border-info/30 text-info",
  pass: "bg-pass-soft border-pass/30 text-pass",
  warn: "bg-warn-soft border-warn/30 text-warn",
  fail: "bg-fail-soft border-fail/30 text-fail",
};

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
  return (
    <span
      className={`inline-flex min-h-5.5 items-center rounded-full border px-2 text-xs leading-tight font-semibold whitespace-nowrap ${BADGE_TONES[tone]} ${className ?? ""}`.trim()}
    >
      {children}
    </span>
  );
}

const ALERT_ICONS = {
  info: InfoIcon,
  warn: AlertTriangleIcon,
  fail: AlertCircleIcon,
  pass: CheckCircleIcon,
} as const;

const ALERT_STYLES = {
  info: { box: "bg-info-soft border-info/25 border-l-info text-ink", icon: "text-info" },
  warn: { box: "bg-warn-soft border-warn/30 border-l-warn text-ink", icon: "text-warn" },
  fail: { box: "bg-fail-soft border-fail/30 border-l-fail text-fail", icon: "text-fail" },
  pass: { box: "bg-pass-soft border-pass/30 border-l-pass text-ink", icon: "text-pass" },
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
  const style = ALERT_STYLES[tone];
  return (
    <div
      role={role}
      className={`flex items-start gap-3 rounded-lg border border-l-[3px] px-4 py-3 text-sm ${style.box} ${className ?? ""}`.trim()}
    >
      <Icon className={`mt-0.5 shrink-0 ${style.icon}`} />
      <div className="min-w-0">
        {title !== undefined && <div className="mb-1 font-semibold">{title}</div>}
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
      className={`h-1.5 w-full overflow-hidden rounded-full bg-sunken ${className ?? ""}`.trim()}
    >
      <div className="h-full rounded-full bg-accent transition-[width] duration-150" style={{ width: `${pct}%` }} />
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
    <details open={defaultOpen} className={`rounded border border-border bg-surface ${className ?? ""}`.trim()}>
      <summary className="px-3 py-2 text-sm font-semibold text-accent">{summary}</summary>
      <div className="px-3 pb-3">{children}</div>
    </details>
  );
}

/** The one card of every screen's overview: a small title, then content. */
export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-lg border border-border bg-surface px-5 py-4 shadow-xs">
      <h2 className="m-0 text-xs font-semibold tracking-wider text-ink-muted uppercase">{title}</h2>
      {children}
    </section>
  );
}

/** A screen's summary in a panel: one count per section, each a link to the section's anchor. */
export function SummaryLinks({
  title,
  items,
}: {
  title: string;
  items: readonly { n: number; label: string; href: string }[];
}) {
  return (
    <Panel title={title}>
      <ul className="m-0 flex list-none flex-wrap gap-x-4 gap-y-2 p-0" aria-label={title}>
        {items.map((item) => (
          <li key={item.href}>
            <a
              href={item.href}
              className={`inline-flex items-baseline gap-2 text-sm text-accent no-underline hover:text-accent-hover hover:underline ${item.n === 0 ? "opacity-60" : ""}`.trim()}
            >
              <span className="min-w-5 text-right text-base font-bold tabular-nums">{item.n}</span> {item.label}
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
      {children !== undefined && <div className="mx-auto mt-2 max-w-[60ch] text-sm text-ink-muted">{children}</div>}
    </div>
  );
}

/** The one data-table style that the matrix, findings, left-out, eval and run list share.
 * The frame scrolls sideways on its own on a narrow screen, never the page. */
export function DataTable({ className, ...props }: TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="relative overflow-x-auto rounded-lg border border-border bg-surface shadow-xs">
      <table
        {...props}
        data-tw=""
        className={`w-full border-collapse text-left text-sm [&_tbody_tr:hover_td]:bg-sunken/40 [&_tbody_tr:last-child_td]:border-b-0 [&_tbody_tr:last-child_th]:border-b-0 [&_td]:border-b [&_td]:border-border [&_td]:px-3 [&_td]:py-2.5 [&_td]:align-top [&_th]:border-b [&_th]:border-border [&_th]:px-3 [&_th]:py-2.5 [&_th]:align-top [&_thead_th]:bg-sunken/70 [&_thead_th]:py-2 [&_thead_th]:text-xs [&_thead_th]:font-semibold [&_thead_th]:tracking-wide [&_thead_th]:whitespace-nowrap [&_thead_th]:text-ink-muted [&_thead_th]:uppercase ${className ?? ""}`.trim()}
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

/** Guided handoff bar linking to the next workflow screens. */
export function HandoffBar({
  label,
  links,
}: {
  label: string;
  links: readonly { href: string; text: string }[];
}) {
  return (
    <nav
      aria-label={label}
      className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface px-4 py-3"
    >
      <span className="text-xs font-semibold tracking-wider text-ink-muted uppercase">{label}</span>
      <div className="flex flex-wrap gap-3">
        {links.map((item) => (
          <a
            key={item.href}
            href={item.href}
            className="inline-flex items-center gap-1 text-sm font-semibold text-accent no-underline hover:text-accent-hover hover:underline"
          >
            <span>{item.text}</span>
            <ChevronRightIcon />
          </a>
        ))}
      </div>
    </nav>
  );
}
