"use client";

import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Sparkles,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useActionState, useState } from "react";

import type { CoverageClass, Decision, MatrixRow, Proposal } from "@/api/client";
import type { DecisionAccess, DecisionView } from "@/components/Decisions";
import { formatWhen } from "@/components/formatWhen";
import { RequiredObservedUnit } from "@/components/RequiredObservedUnit";
import { DirtyGuardBanner } from "@/components/ui/DirtyGuardBanner";
import { Drawer } from "@/components/ui/Drawer";
import { PdfCitationButton } from "@/components/ui/PdfCitationModal";
import {
  CoverageStatusBadge,
  DecisionStateBadge,
  type CoverageBadgeKey,
} from "@/components/ui/StatusBadge";
import type { DecideActionState } from "@/decisions/actions";
import { COVERAGE_CLASSES } from "@/decisions/vocabulary";

type DecisionsT = ReturnType<typeof useTranslations<"decisions">>;
type MatrixT = ReturnType<typeof useTranslations<"matrix">>;

function decisionSummary(td: DecisionsT, tm: MatrixT, d: Decision): string {
  const when = formatWhen(td, d.at);
  if (d.decision === "edited") {
    if (d.coverage === null) return td("made.editedStep", { name: d.name, when });
    return td("made.edited", {
      class: tm(`classes.${d.coverage ?? "none"}`),
      name: d.name,
      when,
    });
  }
  return td(`made.${d.decision}`, { name: d.name, when });
}

function DecisionEntry({ td, tm, d }: { td: DecisionsT; tm: MatrixT; d: Decision }) {
  return (
    <div className="space-y-1">
      <div className="text-xs font-medium text-ink">{decisionSummary(td, tm, d)}</div>
      {d.reason && <div className="text-xs text-ink-muted italic">{d.reason}</div>}
    </div>
  );
}

function wrapLegacyAction(
  action: (formData: FormData) => void | Promise<void>,
): (prevState: DecideActionState, formData: FormData) => Promise<DecideActionState> {
  return async (_prevState, formData) => {
    await action(formData);
    return { ok: true, submittedAt: Date.now() };
  };
}

function MatrixDecisionForm({
  proposal,
  row,
  runId,
  access,
  returnQuery,
  hasNext,
  onNext,
  onDirtyChange,
}: {
  proposal: Proposal;
  row: MatrixRow;
  runId: string;
  access: Extract<DecisionAccess, { mode: "decide" }>;
  returnQuery?: string;
  hasNext: boolean;
  onNext: () => void;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const td = useTranslations("decisions");
  const tm = useTranslations("matrix");

  const actionFn = access.inlineAction ?? wrapLegacyAction(access.action);
  const [reason, setReason] = useState("");
  const [coverage, setCoverage] = useState<string>("");
  const [redecideOpen, setRedecideOpen] = useState(false);
  const [redecideChoice, setRedecideChoice] = useState<"accepted" | "edited">("accepted");
  const [editOpen, setEditOpen] = useState(false);

  const [state, formAction, isPending] = useActionState(
    async (prev: DecideActionState, formData: FormData): Promise<DecideActionState> => {
      const next = await actionFn(prev, formData);
      if (next.ok) {
        setReason("");
        setCoverage("");
        setRedecideOpen(false);
        setEditOpen(false);
        onDirtyChange(false);
      } else if (next.values) {
        if (next.values.reason !== undefined) setReason(next.values.reason);
        if (next.values.coverage) setCoverage(next.values.coverage);
      }
      return next;
    },
    { ok: true },
  );

  const handleReasonChange = (val: string) => {
    setReason(val);
    onDirtyChange(val.trim() !== "" || coverage !== "");
  };

  const handleCoverageChange = (val: string) => {
    setCoverage(val);
    onDirtyChange(reason.trim() !== "" || val !== "");
  };

  const replacing = proposal.state === "decided";
  const proposed: CoverageClass | null | undefined = row.coverage;
  const canAccept = proposed != null;
  const effectiveChoice: "accepted" | "edited" = canAccept ? redecideChoice : "edited";

  const hiddenInputs = (decision: Decision["decision"]) => (
    <>
      <input type="hidden" name="run_id" value={runId} />
      <input type="hidden" name="proposal_id" value={proposal.id} />
      <input type="hidden" name="screen" value="matrix" />
      <input type="hidden" name="decision" value={decision} />
      {returnQuery && <input type="hidden" name="return_query" value={returnQuery} />}
      <input type="hidden" name="anchor" value={row.id} />
    </>
  );

  const acceptForm = canAccept ? (
    <form action={formAction} className="space-y-2">
      {hiddenInputs("accepted")}
      <button
        type="submit"
        disabled={isPending}
        className="inline-flex cursor-pointer items-center justify-center rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
      >
        {td("accept")}
      </button>
    </form>
  ) : null;

  const editForm = (
    <form action={formAction} className="space-y-2">
      {hiddenInputs("edited")}
      <select
        name="coverage"
        required
        value={coverage}
        onChange={(e) => handleCoverageChange(e.target.value)}
        aria-label={td("toClass")}
        className="w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-ink focus:border-accent focus:outline-none"
      >
        <option value="" disabled>
          {td("toClass")}
        </option>
        {COVERAGE_CLASSES.filter((c) => c !== proposed).map((c) => (
          <option key={c} value={c}>
            {tm(`classes.${c}`)}
          </option>
        ))}
      </select>
      <textarea
        name="reason"
        required
        rows={2}
        value={reason}
        onChange={(e) => handleReasonChange(e.target.value)}
        aria-label={td("reason")}
        placeholder={td("reason")}
        className="w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none"
      />
      <button
        type="submit"
        disabled={isPending}
        className="inline-flex cursor-pointer items-center justify-center rounded-md border border-border-strong bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-60"
      >
        {td("edit")}
      </button>
    </form>
  );

  return (
    <div className="space-y-3 pt-2">
      {!state.ok && state.error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-fail-edge bg-fail-soft px-3 py-2 text-xs text-fail"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{td(`errors.${state.error}`)}</span>
        </div>
      )}

      {state.ok && state.submittedAt && hasNext && (
        <div
          role="status"
          className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-pass-edge bg-pass-soft px-3 py-2 text-xs text-pass"
        >
          <span className="inline-flex items-center gap-1.5 font-medium">
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span>{tm("drawer.savedNext")}</span>
          </span>
          <button
            type="button"
            onClick={onNext}
            className="inline-flex cursor-pointer items-center gap-1 rounded border border-pass-edge bg-surface px-2 py-0.5 text-xs font-semibold text-pass hover:bg-sunken"
          >
            <span>{tm("drawer.next")}</span>
            <ArrowRight className="h-3 w-3" aria-hidden="true" />
          </button>
        </div>
      )}

      {replacing ? (
        <div className="space-y-2">
          <button
            type="button"
            aria-expanded={redecideOpen}
            onClick={() => setRedecideOpen((o) => !o)}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border-strong bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-sunken"
          >
            <span>{td("redecide")}</span>
            <ChevronDown
              className={`h-3.5 w-3.5 transition-transform ${redecideOpen ? "rotate-180" : ""}`}
              aria-hidden="true"
            />
          </button>
          {redecideOpen && (
            <form action={formAction} className="space-y-2.5 rounded-lg border border-border bg-sunken p-3">
              {hiddenInputs(effectiveChoice)}
              {canAccept && (
                <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={td("redecide")}>
                  <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1 text-xs font-medium text-ink">
                    <input
                      type="radio"
                      name="redecide_choice"
                      value="accepted"
                      checked={effectiveChoice === "accepted"}
                      onChange={() => setRedecideChoice("accepted")}
                    />
                    <span>{td("accept")}</span>
                  </label>
                  <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1 text-xs font-medium text-ink">
                    <input
                      type="radio"
                      name="redecide_choice"
                      value="edited"
                      checked={effectiveChoice === "edited"}
                      onChange={() => setRedecideChoice("edited")}
                    />
                    <span>{td("edit")}</span>
                  </label>
                </div>
              )}
              {effectiveChoice === "edited" && (
                <select
                  name="coverage"
                  required
                  value={coverage}
                  onChange={(e) => handleCoverageChange(e.target.value)}
                  aria-label={td("toClass")}
                  className="w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-ink focus:border-accent focus:outline-none"
                >
                  <option value="" disabled>
                    {td("toClass")}
                  </option>
                  {COVERAGE_CLASSES.filter((c) => c !== proposed).map((c) => (
                    <option key={c} value={c}>
                      {tm(`classes.${c}`)}
                    </option>
                  ))}
                </select>
              )}
              <textarea
                name="reason"
                required
                rows={2}
                value={reason}
                onChange={(e) => handleReasonChange(e.target.value)}
                aria-label={td("reason")}
                placeholder={td("reason")}
                className="w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none"
              />
              <button
                type="submit"
                disabled={isPending}
                className={`inline-flex cursor-pointer items-center justify-center rounded-md px-3 py-1.5 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-60 ${
                  effectiveChoice === "accepted"
                    ? "bg-accent text-on-accent hover:bg-accent-hover"
                    : "border border-border-strong bg-surface text-ink hover:bg-canvas"
                }`}
              >
                {effectiveChoice === "accepted" ? td("accept") : td("edit")}
              </button>
            </form>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            {acceptForm}
            {canAccept && (
              <button
                type="button"
                aria-expanded={editOpen}
                onClick={() => setEditOpen((o) => !o)}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border-strong bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-sunken"
              >
                <span>{td("edit")}…</span>
                <ChevronDown
                  className={`h-3.5 w-3.5 transition-transform ${editOpen ? "rotate-180" : ""}`}
                  aria-hidden="true"
                />
              </button>
            )}
          </div>
          {(editOpen || !canAccept) && (
            <div className="rounded-lg border border-border bg-sunken p-3">{editForm}</div>
          )}
        </div>
      )}
    </div>
  );
}

export function MatrixDrawer({
  row,
  proposal,
  runId,
  decisions,
  returnQuery,
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
  row: MatrixRow | null;
  proposal: Proposal | undefined;
  runId: string;
  decisions: DecisionView;
  returnQuery?: string;
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
  const tm = useTranslations("matrix");
  const td = useTranslations("decisions");

  if (!row) {
    return (
      <Drawer open={false} onOpenChange={() => {}} title="">
        {null}
      </Drawer>
    );
  }

  const proposed: CoverageBadgeKey = row.coverage ?? "none";
  const current = proposal?.state === "decided" ? proposal.decisions[0] : undefined;
  const decidedClass: CoverageBadgeKey | null =
    current?.decision === "edited" ? (current.coverage ?? "none") : null;
  const [latestDecision, ...earlierDecisions] = proposal?.decisions ?? [];

  return (
    <Drawer
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
      title={row.id}
      headerExtra={
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onPrev}
            disabled={rowIndex <= 0}
            aria-label={tm("drawer.prev")}
            className="inline-flex h-7 cursor-pointer items-center gap-1 rounded border border-border bg-surface px-2 text-xs font-medium text-ink hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-45"
          >
            <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">{tm("drawer.prev")}</span>
          </button>
          <span className="px-1.5 text-xs font-medium text-ink-muted tabular-nums">
            {tm("drawer.position", { current: rowIndex + 1, total: totalRows })}
          </span>
          <button
            type="button"
            onClick={onNext}
            disabled={rowIndex < 0 || rowIndex >= totalRows - 1}
            aria-label={tm("drawer.next")}
            className="inline-flex h-7 cursor-pointer items-center gap-1 rounded border border-border bg-surface px-2 text-xs font-medium text-ink hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-45"
          >
            <span className="hidden sm:inline">{tm("drawer.next")}</span>
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        {dirtyPrompt && (
          <DirtyGuardBanner
            message={tm("drawer.dirtyWarning")}
            discardLabel={tm("drawer.discardChanges")}
            keepLabel={tm("drawer.keepEditing")}
            onDiscard={onDiscardAndProceed}
            onKeep={onCancelProceed}
          />
        )}

        <div className="space-y-2 rounded-lg border border-border bg-sunken p-3">
          <p className="m-0 text-xs leading-relaxed text-ink">{row.text}</p>
          <div>
            <PdfCitationButton runId={runId} cite={row.source} compact />
          </div>
        </div>

        {/* Coverage & AI advisory rationale */}
        <section className="space-y-2 rounded-lg border border-border bg-sunken p-3.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <CoverageStatusBadge coverage={proposed} />
              {decidedClass != null && (
                <>
                  <span aria-hidden="true" className="text-xs font-bold text-ink-muted">
                    →
                  </span>
                  <span className="sr-only">{tm("decidedClass")}</span>
                  <CoverageStatusBadge coverage={decidedClass} />
                </>
              )}
            </div>
            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-ink-muted">
              <Sparkles className="h-3 w-3 text-accent" aria-hidden="true" />
              <span>{tm("advisoryNote")}</span>
            </span>
          </div>
          <p className="m-0 text-xs leading-relaxed text-ink">{row.reason}</p>
        </section>

        {/* Required vs Observed comparison */}
        <section aria-label={`${tm("disyaratkan")} / ${tm("teramati")}`}>
          <RequiredObservedUnit row={row} runId={runId} variant="detailed" />
        </section>

        {/* Decision section */}
        {proposal !== undefined && (
          <section className="space-y-3 rounded-lg border border-border bg-surface p-3.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="m-0 text-xs font-bold tracking-wide text-ink-muted uppercase">
                {td("column")}
              </h3>
              <DecisionStateBadge state={proposal.state} />
            </div>

            {latestDecision && (
              <div className="rounded-md border border-border bg-sunken p-2.5">
                <DecisionEntry td={td} tm={tm} d={latestDecision} />
              </div>
            )}

            {earlierDecisions.length > 0 && (
              <div className="space-y-1.5 border-t border-border pt-2.5">
                <div className="text-xs font-semibold text-ink-muted">{td("earlier")}</div>
                <ul className="m-0 list-none space-y-2 p-0">
                  {earlierDecisions.map((d) => (
                    <li
                      key={d.id}
                      className="rounded-md border border-border bg-sunken px-2.5 py-2"
                    >
                      <DecisionEntry td={td} tm={tm} d={d} />
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {proposal.previous && (
              <div className="space-y-1 rounded-md border border-warn-edge bg-warn-soft p-2.5 text-xs text-warn">
                <div>{td("previous", { summary: decisionSummary(td, tm, proposal.previous) })}</div>
                {proposal.previous_class && (
                  <div className="font-semibold">
                    {td("previousClass", { class: tm(`classes.${proposal.previous_class}`) })}
                  </div>
                )}
                {proposal.previous.reason && (
                  <div className="italic">{proposal.previous.reason}</div>
                )}
              </div>
            )}

            {decisions.access.mode === "decide" && (
              <MatrixDecisionForm
                key={`${row.id}-${proposal.id}-${proposal.state}-${proposal.decisions[0]?.id ?? 0}`}
                proposal={proposal}
                row={row}
                runId={runId}
                access={decisions.access}
                returnQuery={returnQuery}
                hasNext={rowIndex >= 0 && rowIndex < totalRows - 1}
                onNext={onNext}
                onDirtyChange={onDirtyChange}
              />
            )}
          </section>
        )}
      </div>
    </Drawer>
  );
}
