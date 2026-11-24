import { AlertTriangle, FileWarning, UserCheck } from "lucide-react";
import { useTranslations } from "next-intl";

import type { Completeness, DroppedClaim } from "@/api/client";

import { cell, DataTable, EmptyState, SectionHeading } from "./ui/ui";

/** The reason the drafting step gives for an Acceptance Criterion it leaves empty. */
const HUMAN_REASON = "to be set by a human";

function isHumanAc(d: DroppedClaim): boolean {
  return d.claim === "acceptance" && d.reason.startsWith(HUMAN_REASON);
}

function groupByKind(dropped: readonly DroppedClaim[]): [string, DroppedClaim[]][] {
  const groups = new Map<string, DroppedClaim[]>();
  for (const d of dropped) groups.set(d.claim, [...(groups.get(d.claim) ?? []), d]);
  return [...groups];
}

function DroppedTable({ items }: { items: readonly DroppedClaim[] }) {
  const t = useTranslations("leftOut");
  return (
    <DataTable>
      <thead>
        <tr>
          <th>{t("kind")}</th>
          <th>{t("subject")}</th>
          <th>{t("reason")}</th>
        </tr>
      </thead>
      <tbody>
        {items.map((d, i) => (
          <tr key={`${d.claim}/${d.id}/${i}`}>
            <td className="font-medium text-ink">{d.claim}</td>
            <td className={`${cell.id} text-ink`}>{d.id}</td>
            <td className="text-ink-muted">{d.reason}</td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}

/** What the system left out of a run: claims the citation check dropped (by kind, with the
 * Acceptance Criteria left to a human apart) and the URS completeness check, after a 3-KPI
 * summary that links to each. A dropped claim shows kind, subject and reason only, never its
 * content. `completeness` is null for a run folder written before the check existed. */
export function LeftOutView({
  dropped,
  completeness,
}: {
  dropped: readonly DroppedClaim[];
  completeness: Completeness | null;
}) {
  const t = useTranslations("leftOut");
  const human = dropped.filter(isHumanAc);
  const groups = groupByKind(dropped.filter((d) => !isHumanAc(d)));
  const droppedCount = groups.reduce((n, [, items]) => n + items.length, 0);
  const unquoted = (completeness?.urs ?? []).reduce((n, u) => n + u.unquoted.length, 0);

  const summaryItems = [
    {
      n: droppedCount,
      label: t("dropped"),
      href: "#dropped-claims",
      icon: AlertTriangle,
      tone: droppedCount > 0 ? "border-warn-edge bg-warn-soft/50 text-warn" : "border-border bg-sunken text-ink-muted",
    },
    {
      n: human.length,
      label: t("humanAc"),
      href: "#human-ac",
      icon: UserCheck,
      tone: human.length > 0 ? "border-info-edge bg-info-soft/50 text-info" : "border-border bg-sunken text-ink-muted",
    },
    ...(completeness === null
      ? []
      : [
          {
            n: unquoted,
            label: t("unquotedTotal"),
            href: "#completeness",
            icon: FileWarning,
            tone: unquoted > 0 ? "border-warn-edge bg-warn-soft/50 text-warn" : "border-border bg-sunken text-ink-muted",
          },
        ]),
  ];

  return (
    <div className="flex flex-col gap-6">
      <section
        aria-labelledby="leftout-summary"
        className="rounded-lg border border-border bg-surface p-4 shadow-xs"
      >
        <h2 id="leftout-summary" className="m-0 mb-3 text-xs font-semibold tracking-wider text-ink-muted uppercase">
          {t("summaryTitle")}
        </h2>
        <ul className="m-0 grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-3" aria-label={t("summaryTitle")}>
          {summaryItems.map((item) => {
            const Icon = item.icon;
            return (
              <li key={item.href}>
                <a
                  href={item.href}
                  className={`flex h-full flex-col justify-between gap-2 rounded-lg border border-border bg-surface p-3.5 no-underline transition-colors hover:border-border-strong hover:bg-sunken/40 ${item.n === 0 ? "opacity-65" : ""}`.trim()}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className={`inline-flex h-7 w-7 items-center justify-center rounded-md border ${item.tone}`}>
                      <Icon className="h-4 w-4" aria-hidden="true" />
                    </span>
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-2xl font-bold tracking-tight text-ink tabular-nums">{item.n}</span>{" "}
                    <span className="text-xs font-medium text-ink-muted">{item.label}</span>
                  </div>
                </a>
              </li>
            );
          })}
        </ul>
      </section>

      <section aria-labelledby="dropped-claims" className="space-y-4">
        <SectionHeading id="dropped-claims" title={t("dropped")} count={droppedCount} note={t("droppedNote")} />
        {groups.length === 0 ? (
          <EmptyState title={t("none")} />
        ) : (
          groups.map(([kind, items]) => (
            <section key={kind} aria-label={t("group", { kind })} className="space-y-2">
              <h3 className="m-0 text-sm font-semibold text-ink">{t("group", { kind })}</h3>
              <DroppedTable items={items} />
            </section>
          ))
        )}
      </section>

      <section aria-labelledby="human-ac" className="space-y-3">
        <SectionHeading id="human-ac" title={t("humanAc")} count={human.length} note={t("humanAcNote")} />
        {human.length === 0 ? <EmptyState title={t("none")} /> : <DroppedTable items={human} />}
      </section>

      <section aria-labelledby="completeness" className="space-y-4">
        <SectionHeading id="completeness" title={t("completeness")} />
        {completeness === null ? (
          <EmptyState title={t("notRun")} />
        ) : (
          completeness.urs.map((u) => (
            <section
              key={`${u.doc}/${u.rev}`}
              aria-label={`${u.doc} rev ${u.rev}`}
              className="space-y-3 rounded-lg border border-border bg-surface p-4 shadow-xs"
            >
              <h3 className="m-0 text-sm font-semibold text-ink tabular-nums">{`${u.doc} rev ${u.rev}`}</h3>
              {u.numbers === "not_applicable" ? (
                <p className="m-0 text-xs text-ink-muted">{t("numbersNotApplicable")}</p>
              ) : (
                <div className="space-y-2">
                  <p className="m-0 text-sm text-ink tabular-nums">
                    {t("numbersFound", { found: u.found, missed: u.missed.length })}
                  </p>
                  {u.missed.length > 0 && (
                    <ul className="m-0 space-y-1 pl-5 text-xs text-ink-muted tabular-nums">
                      {u.missed.map((m) => (
                        <li key={`${m.number}/${m.page}`}>
                          {t("missedNumber", { number: m.number, page: m.page })}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              <div className="space-y-2 border-t border-border pt-3">
                <h4 className="m-0 text-xs font-semibold text-ink">{t("unquoted")}</h4>
                {u.unquoted.length === 0 ? (
                  <p className="m-0 text-xs text-ink-muted">{t("none")}</p>
                ) : (
                  <details className="rounded-md border border-border bg-sunken/40">
                    <summary className="px-3 py-2 text-xs font-semibold text-accent">
                      {t("showUnquoted", { count: u.unquoted.length })}
                    </summary>
                    <ul className="m-0 flex list-none flex-col gap-2.5 px-3 pt-1 pb-3">
                      {u.unquoted.map((x) => (
                        <li key={`${x.page}/${x.text}`} className="rounded border border-border bg-surface p-3">
                          <span className="mb-1.5 inline-block text-xs font-semibold text-ink-muted tabular-nums">
                            {t("page", { page: x.page })}
                          </span>
                          <pre className="m-0 font-sans text-xs leading-relaxed whitespace-pre-wrap text-ink">
                            {x.text}
                          </pre>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            </section>
          ))
        )}
      </section>
    </div>
  );
}
