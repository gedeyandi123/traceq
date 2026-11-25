"use client";

import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  History as HistoryIcon,
  Lock,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useActionState, useState } from "react";

import type {
  CompletionBlockers,
  ExecutionCopy,
  ExecutionEvent,
  ExecutionView,
} from "@/api/client";
import type { ExecutionActionState } from "@/execution/actions";
import { formatWhen } from "./formatWhen";
import { CopyHashButton } from "./ui/CopyHashButton";
import { Modal } from "./ui/Modal";
import { ExecutionStatusBadge } from "./ui/StatusBadge";
import { SubmitButton } from "./ui/SubmitButton";
import { Button } from "./ui/ui";

type T = ReturnType<typeof useTranslations<"execution">>;
type WhenT = ReturnType<typeof useTranslations<"decisions">>;

const INITIAL_STATE: ExecutionActionState = { ok: true };
const MAX_VISIBLE_BLOCKERS = 6;

const LIMIT_KEYS = [
  "evidenceText",
  "noWitness",
  "retestNoPermission",
  "noRounding",
  "typedCalibration",
  "liveOnly",
  "oneExecution",
  "combined",
  "notSignature",
] as const;

export function ExecutionStatusPanel({
  t,
  when,
  execution,
}: {
  t: T;
  when: WhenT;
  execution: ExecutionView;
}) {
  return (
    <section
      aria-labelledby="execution-status"
      className="space-y-3 rounded-lg border border-border bg-surface p-4 shadow-xs"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <h2 id="execution-status" className="m-0 text-base font-bold text-ink tabular-nums">
              {t("status", { id: execution.id })}
            </h2>
            <ExecutionStatusBadge status={execution.status} />
          </div>
          <p className="m-0 text-xs text-ink-muted tabular-nums">
            {t("protocolRef", {
              protocolId: execution.protocol_id,
              runId: execution.run_id,
              eventId: execution.submission_event_id,
            })}
          </p>
        </div>
      </div>

      <div className="space-y-2 border-t border-border pt-3">
        <h3 className="m-0 flex items-center gap-2 text-xs font-bold text-ink">
          <HistoryIcon className="h-3.5 w-3.5 text-ink-muted" aria-hidden="true" />
          <span>{t("history")}</span>
        </h3>
        <ol className="m-0 list-decimal space-y-1 pl-5 text-xs text-ink tabular-nums">
          {execution.events.map((e: ExecutionEvent) => (
            <li key={e.id}>
              {t(`events.${e.event}`, { name: e.name, when: formatWhen(when, e.at) })}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

export function CompletionChecklistPanel({
  t,
  executionId,
  blockers,
  completeAction,
  onSelectRow,
  onSelectDeviation,
}: {
  t: T;
  executionId: number;
  blockers: CompletionBlockers;
  completeAction:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  onSelectRow?: (requirement: string) => void;
  onSelectDeviation?: (deviationNumber: number) => void;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [showAllRows, setShowAllRows] = useState(false);
  const [state, formAction] = useActionState(async (prev: ExecutionActionState, fd: FormData) => {
    if (!completeAction) return prev;
    const res = await completeAction(prev, fd);
    if (res.ok) setConfirmOpen(false);
    return res;
  }, INITIAL_STATE);

  const reqs = blockers.rows_without_result.requirements;
  const visibleReqs = showAllRows ? reqs : reqs.slice(0, MAX_VISIBLE_BLOCKERS);
  const hiddenReqCount = reqs.length - visibleReqs.length;

  return (
    <section
      aria-labelledby="execution-completion-checklist"
      className="space-y-3 rounded-lg border border-border bg-surface p-4 shadow-xs"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-start gap-2">
          {blockers.blocked ? (
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-pass" aria-hidden="true" />
          )}
          <div>
            <h2 id="execution-completion-checklist" className="m-0 text-sm font-bold text-ink">
              {t("completion.title")}
            </h2>
            <p className="m-0 text-xs text-ink-muted">
              {blockers.blocked ? t("completion.blockedNote") : t("completion.ready")}
            </p>
          </div>
        </div>

        {completeAction !== null && (
          <>
            <Button
              type="button"
              variant="primary"
              disabled={blockers.blocked}
              onClick={() => setConfirmOpen(true)}
            >
              {t("completion.completeButton")}
            </Button>
            <Modal
              open={confirmOpen}
              onOpenChange={setConfirmOpen}
              size="sm"
              title={t("completion.completeButton")}
              description={t("completeModalDesc")}
            >
              <form action={formAction} className="space-y-3">
                <input type="hidden" name="execution_id" value={executionId} />
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setConfirmOpen(false)}
                    className="cursor-pointer rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-sunken"
                  >
                    {t("cancel")}
                  </button>
                  <SubmitButton variant="primary">{t("completion.completeButton")}</SubmitButton>
                </div>
              </form>
            </Modal>
          </>
        )}
      </div>

      {!state.ok && state.error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-fail-edge bg-fail-soft px-3 py-2 text-xs text-fail"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{state.detail ?? t(`errors.${state.error}`)}</span>
        </div>
      )}

      <ul className="m-0 list-none space-y-2 border-t border-border p-0 pt-3 text-xs">
        <li className="space-y-1">
          <div className="flex items-center gap-2 font-semibold text-ink tabular-nums">
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                blockers.rows_without_result.count > 0 ? "bg-warn" : "bg-pass"
              }`}
              aria-hidden="true"
            />
            <span>
              {t("completion.rowsWithoutResult", {
                count: blockers.rows_without_result.count,
              })}
            </span>
          </div>
          {blockers.rows_without_result.count === 0 ? (
            <p className="m-0 pl-4 text-ink-muted">{t("completion.rowsWithoutResultNone")}</p>
          ) : (
            <div className="flex flex-wrap items-center gap-1.5 pl-4">
              {visibleReqs.map((req) =>
                onSelectRow ? (
                  <button
                    key={req}
                    type="button"
                    onClick={() => onSelectRow(req)}
                    className="cursor-pointer rounded border border-warn-edge bg-warn-soft px-2 py-0.5 font-mono text-[11px] font-semibold text-warn tabular-nums hover:bg-warn-edge/30"
                  >
                    {req}
                  </button>
                ) : (
                  <span
                    key={req}
                    className="rounded border border-warn-edge bg-warn-soft px-2 py-0.5 font-mono text-[11px] font-semibold text-warn tabular-nums"
                  >
                    {req}
                  </span>
                ),
              )}
              {hiddenReqCount > 0 && (
                <button
                  type="button"
                  onClick={() => setShowAllRows(true)}
                  className="cursor-pointer rounded border border-border bg-sunken px-2 py-0.5 text-[11px] font-semibold text-ink-muted hover:text-ink tabular-nums"
                >
                  {t("moreBlockers", { count: hiddenReqCount })}
                </button>
              )}
            </div>
          )}
        </li>

        <li className="space-y-1">
          <div className="flex items-center gap-2 font-semibold text-ink tabular-nums">
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                blockers.open_deviations.count > 0 ? "bg-warn" : "bg-pass"
              }`}
              aria-hidden="true"
            />
            <span>
              {t("completion.openDeviations", {
                count: blockers.open_deviations.count,
              })}
            </span>
          </div>
          {blockers.open_deviations.count === 0 ? (
            <p className="m-0 pl-4 text-ink-muted">{t("completion.openDeviationsNone")}</p>
          ) : (
            <div className="flex flex-wrap gap-1.5 pl-4">
              {blockers.open_deviations.items.map((d) =>
                onSelectDeviation ? (
                  <button
                    key={d.deviation_number}
                    type="button"
                    onClick={() => onSelectDeviation(d.deviation_number)}
                    className="cursor-pointer rounded border border-warn-edge bg-warn-soft px-2 py-0.5 font-mono text-[11px] font-semibold text-warn tabular-nums hover:bg-warn-edge/30"
                  >
                    {t("completion.deviationItem", {
                      number: d.deviation_number,
                      status: t(`completion.deviationStatuses.${d.status}`),
                    })}
                  </button>
                ) : (
                  <span
                    key={d.deviation_number}
                    className="rounded border border-warn-edge bg-warn-soft px-2 py-0.5 font-mono text-[11px] font-semibold text-warn tabular-nums"
                  >
                    {t("completion.deviationItem", {
                      number: d.deviation_number,
                      status: t(`completion.deviationStatuses.${d.status}`),
                    })}
                  </span>
                ),
              )}
            </div>
          )}
        </li>

        <li className="space-y-1">
          <div className="flex items-center gap-2 font-semibold text-ink tabular-nums">
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                blockers.unconfirmed_witness_rows.count > 0 ? "bg-warn" : "bg-pass"
              }`}
              aria-hidden="true"
            />
            <span>
              {t("completion.unconfirmedWitness", {
                count: blockers.unconfirmed_witness_rows.count,
              })}
            </span>
          </div>
          {blockers.unconfirmed_witness_rows.count === 0 ? (
            <p className="m-0 pl-4 text-ink-muted">{t("completion.unconfirmedWitnessNone")}</p>
          ) : (
            <div className="flex flex-wrap items-center gap-1.5 pl-4">
              {blockers.unconfirmed_witness_rows.requirements.map((req) =>
                onSelectRow ? (
                  <button
                    key={req}
                    type="button"
                    onClick={() => onSelectRow(req)}
                    className="cursor-pointer rounded border border-warn-edge bg-warn-soft px-2 py-0.5 font-mono text-[11px] font-semibold text-warn tabular-nums hover:bg-warn-edge/30"
                  >
                    {req}
                  </button>
                ) : (
                  <span
                    key={req}
                    className="rounded border border-warn-edge bg-warn-soft px-2 py-0.5 font-mono text-[11px] font-semibold text-warn tabular-nums"
                  >
                    {req}
                  </span>
                ),
              )}
            </div>
          )}
        </li>
      </ul>
    </section>
  );
}

export function ExecutionFrozenCopyPanel({
  t,
  when,
  frozenCopy,
  copyHash,
}: {
  t: T;
  when: WhenT;
  frozenCopy: ExecutionCopy;
  copyHash: string;
}) {
  const ui = useTranslations("ui");
  return (
    <section
      aria-labelledby="execution-frozen-copy"
      className="space-y-2.5 rounded-lg border border-pass-edge bg-pass-soft p-4 text-xs text-ink"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Lock className="h-4 w-4 shrink-0 text-pass" aria-hidden="true" />
          <h2 id="execution-frozen-copy" className="m-0 text-sm font-bold text-ink">
            {t("completion.frozenTitle")}
          </h2>
        </div>
        <span className="text-ink-muted tabular-nums">
          {t("completion.frozenSummary", {
            rows: frozenCopy.rows.length,
            deviations: frozenCopy.deviations.length,
          })}
        </span>
      </div>
      <p className="m-0 text-ink tabular-nums">
        {t("completion.frozenBy", {
          name: frozenCopy.completer.name,
          when: formatWhen(when, frozenCopy.completed_at),
        })}
      </p>
      <div className="space-y-1 rounded border border-border bg-surface px-3 py-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-[11px] font-semibold text-ink-muted">
            {t("completion.frozenHashLabel")}
          </div>
          <CopyHashButton value={copyHash} copyLabel={ui("copyHash")} copiedLabel={ui("copied")} />
        </div>
        <code className="block font-mono text-xs break-all text-ink tabular-nums">{copyHash}</code>
      </div>
    </section>
  );
}

export function ExecutionLimits({ t }: { t: T }) {
  return (
    <details className="rounded-lg border border-border bg-surface px-4 py-2.5 text-xs">
      <summary className="font-semibold text-ink-muted hover:text-ink">
        <h2 className="m-0 inline text-xs font-semibold">{t("limitsTitle")}</h2>
      </summary>
      <ul className="mt-2 mb-0 list-disc space-y-1 pl-5 text-ink-muted">
        {LIMIT_KEYS.map((key) => (
          <li key={key}>{t(`limits.${key}`)}</li>
        ))}
      </ul>
    </details>
  );
}
