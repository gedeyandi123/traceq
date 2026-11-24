import { useTranslations } from "next-intl";
import Link from "next/link";

import type { RunSummary } from "@/api/client";

import { formatWhen } from "./formatWhen";
import { ModeBadge } from "./ui/ui";

import s from "./RunHeader.module.css";

/** The screens of a run; ``draft`` only for a Review Package run. ``protocol``: the Protocol
 * assembled in TraceQ from the run, never the site's Protocol Draft. */
export type RunTab = "matrix" | "findings" | "draft" | "protocol" | "leftOut" | "eval";

const PATHS: Record<RunTab, string> = {
  matrix: "",
  findings: "/findings",
  draft: "/draft",
  protocol: "/protocol",
  leftOut: "/left-out",
  eval: "/eval",
};

const PRIMARY_TABS: readonly RunTab[] = ["matrix", "findings", "draft", "protocol"];
const AUDIT_TABS: readonly RunTab[] = ["leftOut", "eval"];

/** The header every run screen shares: a breadcrumb back to all runs, the run's Equipment and
 * facts (with the Protocol Draft under review, for a Review Package run), one tab per screen of the run (the current one marked with `aria-current`), and one
 * line on what the screen is for. A component the pages render, not a layout: the pages
 * already fetch the run, and a layout cannot see `searchParams`. */
export function RunHeader({
  run,
  current,
  intro,
  badges,
}: {
  run: RunSummary;
  current: RunTab;
  intro: string;
  badges?: Partial<Record<RunTab, number>>;
}) {
  const t = useTranslations("runHeader");
  const runs = useTranslations("runs");
  const when = useTranslations("decisions");
  const base = `/runs/${encodeURIComponent(run.run_id)}`;
  const pkg = run.review_package;
  // The Protocol Draft tab links the Equipment screens to the draft under review.
  const primary = PRIMARY_TABS.filter((tab) => tab !== "draft" || pkg);
  const renderTab = (tab: RunTab, extraClass?: string) => {
    const count = badges?.[tab];
    return (
      <Link
        key={tab}
        href={`${base}${PATHS[tab]}`}
        className={extraClass ? `${s.tab} ${extraClass}` : s.tab}
        aria-current={tab === current ? "page" : undefined}
      >
        {t(tab)}
        {count !== undefined && count > 0 && <span className={s.tabBadge}>{count}</span>}
      </Link>
    );
  };
  return (
    <header className={s.header}>
      <nav aria-label={t("breadcrumb")} className={s.crumbs}>
        <Link href="/">{t("back")}</Link>
        <span aria-hidden="true">/</span>
        <span>{run.equipment}</span>
      </nav>
      <div className={s.titleRow}>
        <h1 className={s.title}>{run.equipment}</h1>
        <ModeBadge>{runs(run.mode)}</ModeBadge>
      </div>
      <dl className={s.meta}>
        <div>
          <dt>{t("run")}</dt>
          <dd>{run.run_id}</dd>
        </div>
        <div>
          <dt>{runs("model")}</dt>
          <dd>{run.model}</dd>
        </div>
        <div>
          <dt>{runs("created")}</dt>
          <dd>{formatWhen(when, run.created)}</dd>
        </div>
        {pkg && (
          <div>
            <dt>{t("draft")}</dt>
            <dd>{`${pkg.doc_id} rev ${pkg.rev} (${pkg.package} ${pkg.version})`}</dd>
          </div>
        )}
      </dl>
      <nav aria-label={t("tabs")} className={s.tabs}>
        {primary.map((tab) => renderTab(tab))}
        <span className={s.tabDivider} aria-hidden="true" />
        {AUDIT_TABS.map((tab) => renderTab(tab, s.tabAudit))}
      </nav>
      <p className={s.intro}>{intro}</p>
    </header>
  );
}
