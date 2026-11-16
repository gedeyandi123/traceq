import { useTranslations } from "next-intl";
import Link from "next/link";

import type { RunSummary } from "@/api/client";

import s from "./RunHeader.module.css";

export type RunTab = "matrix" | "findings" | "leftOut" | "eval";

const created = new Intl.DateTimeFormat("id-ID", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
});

/** The header every run screen shares: where the viewer is (all runs / equipment), the run's
 * facts, and one tab per screen of the run. Same links as before; the current screen is
 * marked with aria-current, and one line says what the screen is for. */
export function RunHeader({ run, current, intro }: { run: RunSummary; current: RunTab; intro: string }) {
  const t = useTranslations("matrix");
  const tr = useTranslations("runs");
  const base = `/runs/${encodeURIComponent(run.run_id)}`;
  const tabs: { key: RunTab; href: string; label: string }[] = [
    { key: "matrix", href: base, label: t("title") },
    { key: "findings", href: `${base}/findings`, label: t("toFindings") },
    { key: "leftOut", href: `${base}/left-out`, label: t("toLeftOut") },
    { key: "eval", href: `${base}/eval`, label: t("toEval") },
  ];
  return (
    <div className={s.header}>
      <nav aria-label="Breadcrumb" className={s.crumbs}>
        <Link href="/">{t("back")}</Link>
        <span aria-hidden="true">/</span>
        <span>{run.equipment}</span>
      </nav>
      <div className={s.titleRow}>
        <h1 className={s.title}>{run.equipment}</h1>
        <span className={s.mode}>{tr(run.mode)}</span>
      </div>
      <dl className={s.meta}>
        <div>
          <dt>Run</dt>
          <dd className="num">{run.run_id}</dd>
        </div>
        <div>
          <dt>{tr("model")}</dt>
          <dd>{run.model}</dd>
        </div>
        <div>
          <dt>{tr("created")}</dt>
          <dd className="num">{created.format(new Date(run.created))} UTC</dd>
        </div>
      </dl>
      <nav className={s.tabs} aria-label={run.equipment}>
        {tabs.map((tab) => (
          <Link
            key={tab.key}
            href={tab.href}
            className={s.tab}
            aria-current={tab.key === current ? "page" : undefined}
          >
            {tab.label}
          </Link>
        ))}
      </nav>
      <p className={s.intro}>{intro}</p>
    </div>
  );
}
