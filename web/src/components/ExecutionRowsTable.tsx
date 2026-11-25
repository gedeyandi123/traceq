"use client";

import { ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import type { ExecutionRowView } from "@/api/client";
import { formatAttemptValue } from "./ExecutionRowDrawer";
import { formatValue } from "./MatrixTable";
import { FilterBar, type FilterPillOption } from "./ui/FilterBar";
import { PdfCitationButton } from "./ui/PdfCitationModal";
import { StageBadge, VerdictBadge } from "./ui/StatusBadge";

export type ExecutionFilter =
  | "all"
  | "unrecorded"
  | "pass"
  | "fail"
  | "awaitingWitness"
  | "vendorRef";

function isAwaitingWitness(r: ExecutionRowView): boolean {
  if (r.kind !== "test_step" || r.attempts.length === 0) return false;
  const last = r.attempts[r.attempts.length - 1]?.latest;
  if (!last) return false;
  const activeConfirmations = (last.witness_confirmations ?? []).filter((w) => !w.voided);
  return activeConfirmations.length === 0;
}

function matchesFilter(r: ExecutionRowView, filter: ExecutionFilter): boolean {
  switch (filter) {
    case "all":
      return true;
    case "unrecorded":
      return r.kind === "test_step" && r.attempts.length === 0;
    case "pass":
      return r.attempts[r.attempts.length - 1]?.latest?.verdict === "pass";
    case "fail":
      return r.attempts[r.attempts.length - 1]?.latest?.verdict === "fail";
    case "awaitingWitness":
      return isAwaitingWitness(r);
    case "vendorRef":
      return r.kind === "vendor_reference";
  }
}

export function ExecutionRowsTable({
  rows,
  runId,
  selectedRequirement,
  onSelectRow,
  canRecordRow,
  onRecordRow,
}: {
  rows: readonly ExecutionRowView[];
  runId: string;
  selectedRequirement: string | null;
  onSelectRow: (requirement: string) => void;
  canRecordRow: (row: ExecutionRowView) => boolean;
  onRecordRow: (row: ExecutionRowView) => void;
}) {
  const t = useTranslations("execution");
  const m = useTranslations("matrix");
  const ui = useTranslations("ui");
  const [filter, setFilter] = useState<ExecutionFilter>("all");

  const filterOptions = useMemo<readonly FilterPillOption<ExecutionFilter>[]>(
    () => [
      { id: "all", label: t("filters.all"), count: rows.length },
      {
        id: "unrecorded",
        label: t("filters.unrecorded"),
        count: rows.filter((r) => matchesFilter(r, "unrecorded")).length,
      },
      {
        id: "pass",
        label: t("filters.pass"),
        count: rows.filter((r) => matchesFilter(r, "pass")).length,
      },
      {
        id: "fail",
        label: t("filters.fail"),
        count: rows.filter((r) => matchesFilter(r, "fail")).length,
      },
      {
        id: "awaitingWitness",
        label: t("filters.awaitingWitness"),
        count: rows.filter((r) => matchesFilter(r, "awaitingWitness")).length,
      },
      {
        id: "vendorRef",
        label: t("filters.vendorRef"),
        count: rows.filter((r) => matchesFilter(r, "vendorRef")).length,
      },
    ],
    [rows, t],
  );

  const filtered = useMemo(() => rows.filter((r) => matchesFilter(r, filter)), [rows, filter]);

  return (
    <section aria-labelledby="execution-rows" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="execution-rows" className="m-0 text-sm font-bold text-ink tabular-nums">
          {t("rows", { count: rows.length })}
        </h2>
        <span className="text-xs text-ink-muted">{t("rowsNote")}</span>
      </div>
      <p className="m-0 text-xs text-ink-muted">{t("utcNote")}</p>

      <FilterBar
        ariaLabel={t("tabs.rows")}
        options={filterOptions}
        activeId={filter}
        onSelect={setFilter}
      />

      {filtered.length === 0 ? (
        <div className="space-y-2 rounded-lg border border-border bg-surface p-6 text-center text-xs text-ink-muted">
          <p className="m-0">{t("filters.noMatches")}</p>
          {filter !== "all" && (
            <button
              type="button"
              onClick={() => setFilter("all")}
              className="cursor-pointer font-semibold text-accent hover:underline"
            >
              {ui("resetFilter")}
            </button>
          )}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-surface shadow-xs">
          <table className="w-full border-collapse text-left text-xs leading-5">
            <thead className="border-b border-border bg-sunken text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
              <tr>
                <th scope="col" className="px-3 py-2">
                  {t("colRequirement")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("colKind")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("colDetail")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("colAcceptance")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("colResult")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filtered.map((row) => {
                const isSelected = selectedRequirement === row.requirement;
                const step = row.test_step;
                const lastAttempt = row.attempts[row.attempts.length - 1];
                const latest = lastAttempt?.latest ?? null;
                const activeWitnessCount = (latest?.witness_confirmations ?? []).filter(
                  (w) => !w.voided,
                ).length;

                return (
                  <tr
                    key={row.requirement}
                    data-testid={`exec-row-${row.requirement}`}
                    className={`transition-colors ${
                      isSelected
                        ? "bg-accent-soft shadow-[inset_3px_0_0_var(--color-accent)]"
                        : "hover:bg-sunken/40"
                    }`}
                  >
                    <th scope="row" className="max-w-[240px] px-3 py-2.5 align-top font-normal">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => onSelectRow(row.requirement)}
                          aria-expanded={isSelected}
                          className="cursor-pointer font-mono text-xs font-semibold text-accent tabular-nums underline decoration-accent/40 underline-offset-2 hover:text-accent-hover hover:decoration-accent"
                        >
                          {row.requirement}
                        </button>
                        <PdfCitationButton runId={runId} cite={row.source} compact />
                      </div>
                      <div title={row.text} className="mt-1 line-clamp-2 text-xs text-ink-muted">
                        {row.text}
                      </div>
                    </th>

                    <td className="px-3 py-2.5 align-top whitespace-nowrap">
                      <div className="flex flex-col items-start gap-1">
                        <div className="font-semibold text-ink">{t(`kinds.${row.kind}`)}</div>
                        {row.kind === "test_step" && step && (
                          <div className="flex flex-wrap items-center gap-1">
                            <StageBadge stage={step.stage} />
                            {step.witness_required && (
                              <span className="inline-flex items-center gap-1 rounded-full border border-info-edge bg-info-soft px-2 py-0.5 text-[11px] font-semibold text-info">
                                <ShieldCheck className="h-3 w-3 shrink-0" aria-hidden="true" />
                                <span>{t("witnessRequiredBadge")}</span>
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    </td>

                    <td className="max-w-[280px] px-3 py-2.5 align-top">
                      {row.kind === "vendor_reference" ? (
                        <ul className="m-0 list-disc space-y-0.5 pl-4 text-[11px] text-ink-muted tabular-nums">
                          {row.evidence.map((e) => (
                            <li key={`${e.doc}/${e.rev}/${e.step}`}>
                              {t("evidenceStep", { doc: e.doc, rev: e.rev, step: e.step })}
                            </li>
                          ))}
                        </ul>
                      ) : step ? (
                        <div className="space-y-0.5">
                          <div title={step.description} className="line-clamp-2 font-medium text-ink">
                            {step.description}
                          </div>
                          <div title={step.method} className="line-clamp-1 text-[11px] text-ink-muted">
                            {step.method}
                          </div>
                          {step.instrument && (
                            <div className="text-[11px] font-medium text-ink-muted">
                              {step.instrument}
                            </div>
                          )}
                        </div>
                      ) : null}
                    </td>

                    <td className="px-3 py-2.5 align-top tabular-nums">
                      {row.kind === "vendor_reference" ? (
                        <span className="text-[11px] text-ink-muted">—</span>
                      ) : step ? (
                        <span className="font-medium text-ink">
                          {formatValue(m, step.acceptance)}
                        </span>
                      ) : null}
                    </td>

                    <td className="px-3 py-2.5 align-top">
                      {row.kind === "vendor_reference" ? (
                        <span className="text-[11px] text-ink-muted">{t("vendorNoControls")}</span>
                      ) : latest ? (
                        <div className="flex flex-wrap items-center gap-1.5">
                          <VerdictBadge verdict={latest.verdict} />
                          <span className="font-semibold text-ink tabular-nums">
                            {formatAttemptValue(t, row, latest)}
                          </span>
                          {activeWitnessCount > 0 && (
                            <span className="inline-flex items-center gap-1 rounded-full border border-pass-edge bg-pass-soft px-1.5 py-0.5 text-[10px] font-semibold text-pass">
                              <ShieldCheck className="h-3 w-3 shrink-0" aria-hidden="true" />
                              <span>{t("witnessConfirmedBadge")}</span>
                            </span>
                          )}
                          <button
                            type="button"
                            onClick={() => onSelectRow(row.requirement)}
                            className="cursor-pointer text-[11px] font-semibold text-accent hover:underline"
                          >
                            {t("inspectRow")} →
                          </button>
                        </div>
                      ) : canRecordRow(row) ? (
                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            onClick={() => onRecordRow(row)}
                            className="cursor-pointer rounded border border-accent/35 bg-accent-soft px-2.5 py-1 text-xs font-semibold text-accent hover:bg-accent hover:text-on-accent"
                          >
                            {t("recordResult")}
                          </button>
                        </div>
                      ) : (
                        <span className="text-ink-muted">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
