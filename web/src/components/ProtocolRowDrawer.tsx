"use client";

import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, ExternalLink, ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useActionState, useState } from "react";

import type { ProtocolRowView, Stage } from "@/api/client";
import type { ProtocolFormActionState } from "@/protocol/actions";
import type { ProtocolControls } from "./AssembledProtocolView";
import type { DecisionView } from "./Decisions";
import { DraftLabels, DraftRowSections } from "./DraftProtocolPanels";
import { FindingDecisionPanel } from "./FindingDecisionPanel";
import { formatValue } from "./MatrixTable";
import { EditDraftForm, Versions, WriteForm } from "./TestStepForms";
import { DirtyGuardBanner } from "./ui/DirtyGuardBanner";
import { Drawer } from "./ui/Drawer";
import { FIELD_BASE_CLASS } from "./ui/FormControls";
import { PdfCitationButton } from "./ui/PdfCitationModal";
import { CoverageStatusBadge, StageBadge } from "./ui/StatusBadge";
import { SubmitButton } from "./ui/SubmitButton";

function RowAttributesForm({
  row,
  protocolId,
  updateAction,
}: {
  row: ProtocolRowView;
  protocolId: number;
  updateAction: (
    prevState: ProtocolFormActionState,
    formData: FormData,
  ) => Promise<ProtocolFormActionState>;
}) {
  const t = useTranslations("protocol");
  const [stage, setStage] = useState<Stage | "">(row.stage ?? "");
  const [witnessRequired, setWitnessRequired] = useState(row.witness_required);
  const [state, formAction] = useActionState(updateAction, { ok: false });

  return (
    <form
      action={formAction}
      className="space-y-3 rounded-lg border border-border bg-surface p-3.5"
    >
      <input type="hidden" name="protocol_id" value={protocolId} />
      <input type="hidden" name="requirement" value={row.requirement} />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="m-0 text-xs font-bold tracking-wide text-ink-muted uppercase">
          {t("attributes.title")}
        </h3>
        <div className="flex items-center gap-1.5">
          <StageBadge stage={row.stage} />
          {row.witness_required && (
            <span className="inline-flex items-center gap-1 rounded-full border border-info-edge bg-info-soft px-2 py-0.5 text-[11px] font-semibold text-info">
              <ShieldCheck className="h-3 w-3 shrink-0" aria-hidden="true" />
              <span>{t("attributes.witnessBadge")}</span>
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="block space-y-1 text-xs font-medium text-ink">
          <span>{t("attributes.stageLabel")}</span>
          <select
            name="stage"
            value={stage}
            onChange={(e) => setStage(e.target.value as Stage | "")}
            className={`w-full text-xs ${FIELD_BASE_CLASS}`}
          >
            <option value="">{t("attributes.stageUnsplit")}</option>
            <option value="IQ">{t("attributes.stageIQ")}</option>
            <option value="OQ">{t("attributes.stageOQ")}</option>
          </select>
        </label>

        <label className="flex cursor-pointer items-center gap-2 self-end rounded-md border border-border bg-sunken px-3 py-2 text-xs font-medium text-ink">
          <input
            type="checkbox"
            name="witness_required"
            checked={witnessRequired}
            onChange={(e) => setWitnessRequired(e.target.checked)}
            className="h-4 w-4 rounded border-border-strong accent-accent"
          />
          <span>{t("attributes.witnessLabel")}</span>
        </label>
      </div>

      {state.error && (
        <p role="alert" className="m-0 text-xs text-fail">
          {t(`errors.${state.error}`)}
        </p>
      )}
      {state.ok && state.submittedAt && (
        <p className="m-0 flex items-center gap-1 text-xs text-pass">
          <CheckCircle2 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>{t("attributes.saved")}</span>
        </p>
      )}

      <div className="flex justify-end">
        <SubmitButton variant="soft">{t("attributes.save")}</SubmitButton>
      </div>
    </form>
  );
}

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
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onPrev}
            disabled={rowIndex <= 0}
            aria-label={t("drawer.prev")}
            className="inline-flex h-7 cursor-pointer items-center gap-1 rounded border border-border bg-surface px-2 text-xs font-medium text-ink hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-45"
          >
            <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">{t("drawer.prev")}</span>
          </button>
          <span className="px-1.5 text-xs font-medium text-ink-muted tabular-nums">
            {t("drawer.position", { current: rowIndex + 1, total: totalRows })}
          </span>
          <button
            type="button"
            onClick={onNext}
            disabled={rowIndex < 0 || rowIndex >= totalRows - 1}
            aria-label={t("drawer.next")}
            className="inline-flex h-7 cursor-pointer items-center gap-1 rounded border border-border bg-surface px-2 text-xs font-medium text-ink hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-45"
          >
            <span className="hidden sm:inline">{t("drawer.next")}</span>
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        {dirtyPrompt && (
          <DirtyGuardBanner
            message={t("drawer.dirtyWarning")}
            discardLabel={t("drawer.discardChanges")}
            keepLabel={t("drawer.keepEditing")}
            onDiscard={onDiscardAndProceed}
            onKeep={onCancelProceed}
          />
        )}

        <section className="space-y-2 rounded-lg border border-border bg-sunken p-3.5">
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
                  href={`/runs/${encodeURIComponent(runId)}?selected=${encodeURIComponent(row.requirement)}`}
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
                  className="flex flex-wrap items-center justify-between gap-2 rounded border border-border bg-sunken px-2.5 py-1.5 text-xs text-ink"
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

        {controls !== null && controls.updateAttributesInline && row.kind === "test_step" && (
          <RowAttributesForm
            key={`attrs-${row.requirement}-${row.stage ?? "none"}-${row.witness_required}`}
            row={row}
            protocolId={protocolId}
            updateAction={controls.updateAttributesInline}
          />
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

        {row.step_source && (
          <div className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            <span>
              {t("draftFlow.row.source")}: {t(`draftFlow.row.sources.${row.step_source}`)}
            </span>
            {row.step_source === "draft" && <DraftLabels t={t} />}
          </div>
        )}

        <DraftRowSections
          t={t}
          row={row}
          runId={runId}
          protocolId={protocolId}
          decisions={decisions}
          controls={controls}
          onDirtyChange={onDirtyChange}
        />

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
                  className="space-y-3 rounded-lg border border-border bg-sunken p-3.5"
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
                      proposalId={d.proposal.id}
                      start={d.draft}
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
