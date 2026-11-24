"use client";

import { AlertTriangle, ChevronLeft, ChevronRight, ExternalLink } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";

import type { ProtocolRowView } from "@/api/client";
import type { ProtocolControls } from "./AssembledProtocolView";
import type { DecisionView } from "./Decisions";
import { FindingDecisionPanel } from "./FindingDecisionPanel";
import { formatValue } from "./MatrixTable";
import { EditDraftForm, Versions, WriteForm } from "./TestStepForms";
import { Drawer } from "./ui/Drawer";
import { PdfCitationButton } from "./ui/PdfCitationModal";
import { CoverageStatusBadge } from "./ui/StatusBadge";

export function ProtocolRowDrawer({
  row,
  runId,
  protocolId,
  decisions,
  controls,
  open,
  rowIndex,
  totalRows,
  dirtyPrompt,
  onClose,
  onPrev,
  onNext,
  onDirtyChange,
  onDiscardAndProceed,
  onCancelProceed,
}: {
  row: ProtocolRowView | null;
  runId: string;
  protocolId: number;
  decisions: DecisionView;
  controls: ProtocolControls;
  open: boolean;
  rowIndex: number;
  totalRows: number;
  dirtyPrompt: boolean;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
  onDirtyChange: (dirty: boolean) => void;
  onDiscardAndProceed: () => void;
  onCancelProceed: () => void;
}) {
  const t = useTranslations("protocol");
  const m = useTranslations("matrix");

  if (!row) {
    return (
      <Drawer open={false} onOpenChange={() => {}} title="">
        {null}
      </Drawer>
    );
  }

  const step = row.test_step;
  const changed = row.coverage.state === "changed";

  return (
    <Drawer
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
      title={row.requirement}
      description={t(`kinds.${row.kind}`)}
      headerExtra={
        <div className="flex flex-wrap items-center justify-end gap-1">
          <button
            type="button"
            data-tw=""
            onClick={onPrev}
            disabled={rowIndex <= 0}
            aria-label={t("drawer.prev")}
            className="inline-flex h-7 cursor-pointer items-center gap-1 rounded border border-border bg-surface px-2 text-xs font-medium text-ink hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-45"
          >
            <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
            <span>{t("drawer.prev")}</span>
          </button>
          <span className="px-1.5 text-xs font-medium text-ink-muted tabular-nums">
            {t("drawer.position", { current: rowIndex + 1, total: totalRows })}
          </span>
          <button
            type="button"
            data-tw=""
            onClick={onNext}
            disabled={rowIndex < 0 || rowIndex >= totalRows - 1}
            aria-label={t("drawer.next")}
            className="inline-flex h-7 cursor-pointer items-center gap-1 rounded border border-border bg-surface px-2 text-xs font-medium text-ink hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-45"
          >
            <span>{t("drawer.next")}</span>
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
      }
    >
      <div className="space-y-5">
        {dirtyPrompt && (
          <div
            role="alert"
            className="space-y-2 rounded-lg border border-warn-edge bg-warn-soft p-3 text-xs text-warn"
          >
            <p className="m-0 font-semibold">{t("drawer.dirtyWarning")}</p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                data-tw=""
                onClick={onDiscardAndProceed}
                className="cursor-pointer rounded border border-warn-edge bg-surface px-2.5 py-1 text-xs font-semibold text-warn hover:bg-sunken"
              >
                {t("drawer.discardChanges")}
              </button>
              <button
                type="button"
                data-tw=""
                onClick={onCancelProceed}
                className="cursor-pointer rounded bg-accent px-2.5 py-1 text-xs font-semibold text-on-accent hover:bg-accent-hover"
              >
                {t("drawer.keepEditing")}
              </button>
            </div>
          </div>
        )}

        <section className="space-y-2 rounded-lg border border-border bg-canvas p-3.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            {row.decided_class ? (
              <CoverageStatusBadge coverage={row.decided_class} />
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1 rounded-full border border-fail-edge bg-fail-soft px-2.5 py-0.5 text-xs font-semibold text-fail">
                  <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  <span>{t(changed ? "coverageChanged" : "coverageUndecided")}</span>
                </span>
                <Link
                  href={`/runs/${encodeURIComponent(runId)}#${encodeURIComponent(row.requirement)}`}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-accent hover:underline"
                >
                  <span>{t("toMatrix")}</span>
                  <ExternalLink className="h-3 w-3" aria-hidden="true" />
                </Link>
              </div>
            )}
            <PdfCitationButton runId={runId} cite={row.source} compact />
          </div>
          <p className="m-0 text-sm leading-relaxed text-ink">{row.text}</p>
        </section>

        {row.blockers.length > 0 && (
          <div className="space-y-1.5">
            {row.blockers.map((b) => (
              <div
                key={b}
                className="flex items-start gap-2 rounded-md border border-fail-edge bg-fail-soft px-3 py-2 text-xs font-medium text-fail"
              >
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span>{t(`blockers.${b}`)}</span>
              </div>
            ))}
          </div>
        )}

        {row.kind === "vendor_reference" && (
          <section className="space-y-2 rounded-lg border border-border bg-surface p-3.5">
            <h3 className="m-0 text-xs font-bold tracking-wide text-ink-muted uppercase">
              {t("kinds.vendor_reference")}
            </h3>
            <p className="m-0 text-xs text-ink-muted">{t("vendorEvidence")}</p>
            <ul className="m-0 list-none space-y-1.5 p-0">
              {row.evidence.map((e) => (
                <li
                  key={`${e.doc}/${e.rev}/${e.step}`}
                  className="flex flex-wrap items-center justify-between gap-2 rounded border border-border bg-canvas px-2.5 py-1.5 text-xs text-ink"
                >
                  <span className="tabular-nums">
                    {t("evidenceStep", { doc: e.doc, rev: e.rev, step: e.step })}
                  </span>
                  <PdfCitationButton runId={runId} cite={e.citation} compact />
                </li>
              ))}
            </ul>
          </section>
        )}

        {step && (
          <section className="space-y-2.5 rounded-lg border border-border bg-surface p-3.5">
            <div className="text-xs font-bold text-ink">
              {step.origin === "written"
                ? t(step.proposal_id === null ? "writtenStep" : "editedStep", {
                    version: step.version ?? 1,
                  })
                : t("fromDraft")}
            </div>
            <dl className="m-0 grid grid-cols-1 gap-2 text-xs sm:grid-cols-[140px_1fr]">
              <dt className="font-semibold text-ink-muted">{t("description")}</dt>
              <dd className="m-0 text-ink">{step.description}</dd>
              <dt className="font-semibold text-ink-muted">{t("method")}</dt>
              <dd className="m-0 text-ink">{step.method}</dd>
              <dt className="font-semibold text-ink-muted">{t("instrument")}</dt>
              <dd className="m-0 text-ink">{step.instrument ?? t("noInstrument")}</dd>
              <dt className="font-semibold text-ink-muted">{t("ac")}</dt>
              <dd className="m-0 font-medium text-ink tabular-nums">
                {step.acceptance
                  ? formatValue(m, step.acceptance)
                  : t("acToSet", { flag: step.acceptance_flag ?? "" })}
              </dd>
            </dl>
          </section>
        )}

        {controls !== null && row.kind !== "undecided" && (
          <WriteForm
            key={row.requirement}
            t={t}
            row={row}
            runId={runId}
            protocolId={protocolId}
            write={controls.write}
            remove={controls.remove}
            writeInline={controls.writeInline}
            removeInline={controls.removeInline}
            onDirtyChange={onDirtyChange}
          />
        )}

        <Versions t={t} m={m} versions={row.written} />

        {row.drafts.length > 0 && (
          <section className="space-y-3">
            <h3 className="m-0 text-xs font-bold tracking-wide text-ink-muted uppercase">
              {t("drafts")}
            </h3>
            {row.drafts.map((d) => {
              const x = d.draft;
              return (
                <div
                  key={d.proposal.id}
                  className="space-y-3 rounded-lg border border-border bg-canvas p-3.5"
                >
                  <div className="space-y-1.5 text-xs">
                    <div className="font-medium text-ink">{x.description}</div>
                    <div className="text-ink-muted">
                      {t("method")}: {x.method}
                    </div>
                    <div className="text-ink-muted">
                      {t("instrument")}: {x.instrument ?? t("noInstrument")}
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5 text-ink">
                      <span>
                        {t("ac")}:{" "}
                        {x.acceptance
                          ? formatValue(m, x.acceptance)
                          : t("acToSet", { flag: x.acceptance_flag ?? "" })}
                      </span>
                      {x.acceptance_citation && (
                        <PdfCitationButton runId={runId} cite={x.acceptance_citation} compact />
                      )}
                    </div>
                    {row.kind === "vendor_reference" && (
                      <div className="text-ink-muted italic">{t("vendorDraftNote")}</div>
                    )}
                  </div>

                  <FindingDecisionPanel
                    proposal={d.proposal}
                    runId={runId}
                    screen="protocol"
                    access={decisions.access}
                    anchor={`row-${row.requirement}`}
                    onDirtyChange={onDirtyChange}
                  />

                  {controls !== null && row.test_step?.origin !== "written" && (
                    <EditDraftForm
                      t={t}
                      d={d}
                      runId={runId}
                      protocolId={protocolId}
                      edit={controls.edit}
                      editInline={controls.editInline}
                      onDirtyChange={onDirtyChange}
                    />
                  )}
                </div>
              );
            })}
          </section>
        )}
      </div>
    </Drawer>
  );
}
