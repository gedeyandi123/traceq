"use client";

import { AlertTriangle, ChevronRight } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";

import type { ProtocolRowView } from "@/api/client";
import { formatValue } from "./MatrixTable";
import { PdfCitationButton } from "./ui/PdfCitationModal";
import { CoverageStatusBadge, DecisionStateBadge } from "./ui/StatusBadge";

/** Opsi A compact 4-column table for Assembled Protocol rows in Draft status. */
export function ProtocolRowsTable({
  rows,
  runId,
  selectedRequirement,
  onSelect,
}: {
  rows: readonly ProtocolRowView[];
  runId: string;
  selectedRequirement: string | null;
  onSelect: (requirement: string) => void;
}) {
  const t = useTranslations("protocol");
  const m = useTranslations("matrix");

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface shadow-xs">
      <table className="w-full border-collapse text-left text-xs">
        <thead>
          <tr className="border-b border-border bg-sunken/70 text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
            <th scope="col" className="px-3 py-2">
              {t("requirement")}
            </th>
            <th scope="col" className="px-3 py-2">
              {t("coverage")}
            </th>
            <th scope="col" className="px-3 py-2">
              {t("content")}
            </th>
            <th scope="col" className="px-3 py-2">
              {t("drafts")}
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((r) => {
            const isSelected = selectedRequirement === r.requirement;
            const isBlocking = r.blockers.length > 0;
            const step = r.test_step;
            const changed = r.coverage.state === "changed";

            return (
              <tr
                key={r.requirement}
                id={`row-${r.requirement}`}
                data-testid={r.requirement}
                className={`group transition-colors ${
                  isSelected
                    ? "bg-accent-soft shadow-[inset_3px_0_0_var(--color-accent)]"
                    : isBlocking
                      ? "bg-fail-soft/20 hover:bg-fail-soft/35"
                      : "hover:bg-sunken/40"
                }`}
              >
                <th scope="row" className="max-w-[260px] px-3 py-2.5 align-top font-normal">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => onSelect(r.requirement)}
                      className="cursor-pointer font-mono text-xs font-semibold text-accent tabular-nums underline decoration-accent/40 underline-offset-2 hover:text-accent-hover hover:decoration-accent"
                    >
                      {r.requirement}
                    </button>
                    <PdfCitationButton runId={runId} cite={r.source} compact />
                  </div>
                  <div title={r.text} className="mt-1 line-clamp-2 text-xs text-ink-muted">
                    {r.text}
                  </div>
                </th>

                <td className="px-3 py-2.5 align-top whitespace-nowrap">
                  {r.decided_class ? (
                    <CoverageStatusBadge coverage={r.decided_class} size="xs" />
                  ) : (
                    <div className="space-y-1">
                      <span className="inline-flex items-center gap-1 rounded-full border border-fail-edge bg-fail-soft px-2 py-0.5 text-[11px] font-semibold text-fail">
                        <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
                        <span>{t(changed ? "coverageChanged" : "coverageUndecided")}</span>
                      </span>
                      <div>
                        <Link
                          href={`/runs/${encodeURIComponent(runId)}?selected=${encodeURIComponent(r.requirement)}`}
                          className="text-[11px] font-semibold text-accent hover:underline"
                        >
                          {t("toMatrix")}
                        </Link>
                      </div>
                    </div>
                  )}
                </td>

                <td className="max-w-[320px] px-3 py-2.5 align-top">
                  <div className="font-semibold text-ink">{t(`kinds.${r.kind}`)}</div>
                  {r.kind === "vendor_reference" && r.evidence.length > 0 && (
                    <div className="mt-0.5 text-[11px] text-ink-muted tabular-nums">
                      {r.evidence
                        .map((e) => t("evidenceStep", { doc: e.doc, rev: e.rev, step: e.step }))
                        .join(" · ")}
                    </div>
                  )}
                  {step && (
                    <div className="mt-0.5 space-y-0.5">
                      <div
                        title={`${step.origin === "written" ? t(step.proposal_id === null ? "writtenStep" : "editedStep", { version: step.version ?? 1 }) : t("fromDraft")} · ${step.acceptance ? formatValue(m, step.acceptance) : t("acToSet", { flag: step.acceptance_flag ?? "" })}`}
                        className="line-clamp-1 text-[11px] text-ink-muted"
                      >
                        {step.origin === "written"
                          ? t(step.proposal_id === null ? "writtenStep" : "editedStep", {
                              version: step.version ?? 1,
                            })
                          : t("fromDraft")}
                        {" · "}
                        <span className="font-medium text-ink tabular-nums">
                          {step.acceptance
                            ? formatValue(m, step.acceptance)
                            : t("acToSet", { flag: step.acceptance_flag ?? "" })}
                        </span>
                      </div>
                    </div>
                  )}
                  {r.blockers.map((b) => (
                    <div
                      key={b}
                      className="mt-1 inline-flex items-center gap-1 rounded border border-fail-edge bg-fail-soft px-1.5 py-0.5 text-[11px] font-medium text-fail"
                    >
                      <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
                      <span>{t(`blockers.${b}`)}</span>
                    </div>
                  ))}
                </td>

                <td className="px-3 py-2.5 align-top whitespace-nowrap">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-1">
                      {r.drafts.length === 0 ? (
                        <span className="text-[11px] text-ink-muted">{t("noDrafts")}</span>
                      ) : (
                        r.drafts.map((d) => (
                          <DecisionStateBadge key={d.proposal.id} state={d.proposal.state} />
                        ))
                      )}
                    </div>
                    <span
                      aria-hidden="true"
                      className="inline-flex items-center gap-0.5 text-[11px] font-medium text-accent opacity-0 transition-opacity group-hover:opacity-100"
                    >
                      <span>{t("drawer.inspect")}</span>
                      <ChevronRight className="h-3 w-3" aria-hidden="true" />
                    </span>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
