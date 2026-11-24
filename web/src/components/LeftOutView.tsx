"use client";

import { AlertTriangle, CheckCircle2, ChevronDown, FileWarning, UserCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";

import type { Completeness, DroppedClaim } from "@/api/client";
import { PdfCitationButton } from "./ui/PdfCitationModal";
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

function DroppedTable({
  items,
  runId,
}: {
  items: readonly DroppedClaim[];
  runId?: string;
}) {
  const t = useTranslations("leftOut");
  return (
    <DataTable>
      <thead>
        <tr>
          <th>{t("subject")}</th>
          <th>{t("reason")}</th>
        </tr>
      </thead>
      <tbody>
        {items.map((d, i) => {
          const isUrsId = runId && /^URS-/.test(d.id);
          return (
            <tr key={`${d.claim}/${d.id}/${i}`}>
              <td className={`${cell.id} text-ink`}>
                {isUrsId ? (
                  <Link
                    href={`/runs/${encodeURIComponent(runId)}?selected=${encodeURIComponent(d.id)}`}
                    className="font-mono text-accent no-underline hover:underline"
                  >
                    {d.id}
                  </Link>
                ) : (
                  d.id
                )}
              </td>
              <td className="text-ink-muted">{d.reason}</td>
            </tr>
          );
        })}
      </tbody>
    </DataTable>
  );
}

function UnquotedDisclosure({
  u,
  runId,
}: {
  u: Completeness["urs"][number];
  runId?: string;
}) {
  const t = useTranslations("leftOut");
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-md border border-border bg-sunken/40">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full cursor-pointer items-center justify-between gap-2 px-3 py-2 text-left text-xs font-semibold text-accent hover:bg-sunken/70"
      >
        <span>{t("showUnquoted", { count: u.unquoted.length })}</span>
        <ChevronDown
          className={`h-3.5 w-3.5 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>
      <ul
        className={`m-0 list-none flex-col gap-2.5 px-3 pt-1 pb-3 ${open ? "flex" : "hidden"}`}
      >
        {u.unquoted.map((x) => (
          <li key={`${x.page}/${x.text}`} className="rounded border border-border bg-surface p-3">
            <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-semibold text-ink-muted tabular-nums">
                {t("page", { page: x.page })}
              </span>
              {runId && (
                <PdfCitationButton
                  runId={runId}
                  cite={{ doc: u.doc, rev: u.rev, page: x.page, quote: x.text.slice(0, 120) }}
                  compact
                />
              )}
            </div>
            <pre className="m-0 font-sans text-xs leading-relaxed whitespace-pre-wrap text-ink">
              {x.text}
            </pre>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** What the system left out of a run: claims the citation check dropped (by kind, with the
 * Acceptance Criteria left to a human apart) and the URS completeness check, after a 3-KPI
 * summary that links to each. */
export function LeftOutView({
  dropped,
  completeness,
  runId,
}: {
  dropped: readonly DroppedClaim[];
  completeness: Completeness | null;
  runId?: string;
}) {
  const t = useTranslations("leftOut");
  const human = dropped.filter(isHumanAc);
  const groups = groupByKind(dropped.filter((d) => !isHumanAc(d)));
  const droppedCount = groups.reduce((n, [, items]) => n + items.length, 0);
  const unquoted = (completeness?.urs ?? []).reduce((n, u) => n + u.unquoted.length, 0);
  const claimLabel = (kind: string) => (t.has(`claimKinds.${kind}`) ? t(`claimKinds.${kind}`) : kind);

  const summaryItems = [
    {
      n: droppedCount,
      label: t("dropped"),
      href: "#dropped-claims",
      icon: AlertTriangle,
      tone:
        droppedCount > 0
          ? "border-warn-edge bg-warn-soft/50 text-warn"
          : "border-border bg-sunken text-ink-muted",
    },
    {
      n: human.length,
      label: t("humanAc"),
      href: "#human-ac",
      icon: UserCheck,
      tone:
        human.length > 0
          ? "border-info-edge bg-info-soft/50 text-info"
          : "border-border bg-sunken text-ink-muted",
    },
    ...(completeness === null
      ? []
      : [
          {
            n: unquoted,
            label: t("unquotedTotal"),
            href: "#completeness",
            icon: FileWarning,
            tone:
              unquoted > 0
                ? "border-warn-edge bg-warn-soft/50 text-warn"
                : "border-border bg-sunken text-ink-muted",
          },
        ]),
  ];

  return (
    <div className="flex flex-col gap-6">
      <section
        aria-labelledby="leftout-summary"
        className="rounded-lg border border-border bg-surface p-4 shadow-xs"
      >
        <h2
          id="leftout-summary"
          className="m-0 mb-3 text-xs font-semibold tracking-wider text-ink-muted uppercase"
        >
          {t("summaryTitle")}
        </h2>
        <ul
          className="m-0 grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-3"
          aria-label={t("summaryTitle")}
        >
          {summaryItems.map((item) => {
            const Icon = item.icon;
            return (
              <li key={item.href}>
                <a
                  href={item.href}
                  className={`flex h-full items-start justify-between gap-3 rounded-lg border border-border bg-surface p-3.5 no-underline transition-colors hover:border-border-strong hover:bg-sunken/40 ${item.n === 0 ? "opacity-65" : ""}`.trim()}
                >
                  <div className="flex flex-col gap-1">
                    <span className="text-2xl font-bold tracking-tight text-ink tabular-nums">
                      {item.n}
                    </span>{" "}
                    <span className="text-xs font-medium text-ink-muted">{item.label}</span>
                  </div>
                  <span
                    className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border ${item.tone}`}
                  >
                    <Icon className="h-4 w-4" aria-hidden="true" />
                  </span>
                </a>
              </li>
            );
          })}
        </ul>
      </section>

      <section aria-labelledby="dropped-claims" className="space-y-4">
        <SectionHeading
          id="dropped-claims"
          title={t("dropped")}
          count={droppedCount}
          note={t("droppedNote")}
        />
        {groups.length === 0 ? (
          <EmptyState title={t("none")} />
        ) : (
          groups.map(([kind, items]) => {
            const label = claimLabel(kind);
            return (
              <section key={kind} aria-label={t("group", { kind: label })} className="space-y-2">
                <h3 className="m-0 text-sm font-semibold text-ink">
                  {t("group", { kind: label })}
                </h3>
                <DroppedTable items={items} runId={runId} />
              </section>
            );
          })
        )}
      </section>

      <section aria-labelledby="human-ac" className="space-y-3">
        <SectionHeading
          id="human-ac"
          title={t("humanAc")}
          count={human.length}
          note={t("humanAcNote")}
        />
        {human.length === 0 ? (
          <EmptyState title={t("none")} />
        ) : (
          <DroppedTable items={human} runId={runId} />
        )}
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
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="m-0 text-sm font-semibold text-ink tabular-nums">
                  {`${u.doc} rev ${u.rev}`}
                </h3>
                {u.numbers !== "not_applicable" && u.missed.length === 0 && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-pass-edge bg-pass-soft px-2 py-0.5 text-[11px] font-semibold text-pass">
                    <CheckCircle2 className="h-3 w-3 shrink-0" aria-hidden="true" />
                    <span>{t("zeroMissed")}</span>
                  </span>
                )}
              </div>
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
                  <UnquotedDisclosure u={u} runId={runId} />
                )}
              </div>
            </section>
          ))
        )}
      </section>
    </div>
  );
}
