import { useTranslations } from "next-intl";
import Link from "next/link";

import type { RunSummary } from "@/api/client";

import s from "./RunHeader.module.css";

/** The four screens of a run. */
export type RunTab = "matrix" | "findings" | "leftOut" | "eval";

const PATHS: Record<RunTab, string> = { matrix: "", findings: "/findings", leftOut: "/left-out", eval: "/eval" };
const TABS = Object.keys(PATHS) as RunTab[];

// The same format as the decision timestamps.
const date = new Intl.DateTimeFormat("id-ID", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" });
const time = new Intl.DateTimeFormat("id-ID", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });

/** The header every run screen shares: a breadcrumb back to all runs, the run's Equipment and
 * facts, one tab per screen of the run (the current one marked with `aria-current`), and one
 * line on what the screen is for. A component the pages render, not a layout: the pages
 * already fetch the run, and a layout cannot see `searchParams`. */
export function RunHeader({ run, current, intro }: { run: RunSummary; current: RunTab; intro: string }) {
  const t = useTranslations("runHeader");
  const runs = useTranslations("runs");
  const back = useTranslations("matrix");
  const when = useTranslations("decisions");
  const base = `/runs/${encodeURIComponent(run.run_id)}`;
  const created = new Date(run.created);
  return (
    <header className={s.header}>
      <nav aria-label={t("breadcrumb")} className={s.crumbs}>
        <Link href="/">{back("back")}</Link>
        <span aria-hidden="true">/</span>
        <span>{run.equipment}</span>
      </nav>
      <div className={s.titleRow}>
        <h1 className={s.title}>{run.equipment}</h1>
        <span className={s.mode}>{runs(run.mode)}</span>
      </div>
      <dl className={s.meta}>
        <div>
          <dt>{t("run")}</dt>
          <dd className={s.num}>{run.run_id}</dd>
        </div>
        <div>
          <dt>{runs("model")}</dt>
          <dd>{run.model}</dd>
        </div>
        <div>
          <dt>{runs("created")}</dt>
          <dd className={s.num}>{when("when", { date: date.format(created), time: time.format(created) })}</dd>
        </div>
      </dl>
      <nav aria-label={t("tabs")} className={s.tabs}>
        {TABS.map((tab) => (
          <Link
            key={tab}
            href={`${base}${PATHS[tab]}`}
            className={s.tab}
            aria-current={tab === current ? "page" : undefined}
          >
            {t(tab)}
          </Link>
        ))}
      </nav>
      <p className={s.intro}>{intro}</p>
    </header>
  );
}
