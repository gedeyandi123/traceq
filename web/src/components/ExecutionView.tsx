"use client";

import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  History as HistoryIcon,
  Lock,
  PlayCircle,
  ShieldCheck,
} from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useActionState, useState } from "react";

import type {
  AttemptVersionView,
  CompletionBlockers,
  DeviationView,
  ExecutionCopy,
  ExecutionRowView,
  ExecutionView,
  ProtocolView,
} from "@/api/client";
import type { ExecutionActionState } from "@/execution/actions";
import { DeviationDetailDrawer } from "./DeviationDetailDrawer";
import { ExecutionResultDrawer } from "./ExecutionResultDrawer";
import { formatWhen } from "./formatWhen";
import { formatValue } from "./MatrixTable";
import { ManualDeviationDrawer } from "./ManualDeviationDrawer";
import { PdfCitationButton } from "./ui/PdfCitationModal";
import {
  DeviationStatusBadge,
  ExecutionStatusBadge,
  VerdictBadge,
} from "./ui/StatusBadge";
import { SubmitButton } from "./ui/SubmitButton";
import { Button, EmptyState } from "./ui/ui";

type T = ReturnType<typeof useTranslations<"execution">>;
type MatrixT = ReturnType<typeof useTranslations<"matrix">>;
type WhenT = ReturnType<typeof useTranslations<"decisions">>;

const INITIAL_STATE: ExecutionActionState = { ok: true };

const LIMITS = [
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

function Limits({ t }: { t: T }) {
  return (
    <aside
      aria-labelledby="execution-limits"
      className="space-y-2 rounded-lg border border-border bg-sunken px-4 py-3 text-xs text-ink-muted"
    >
      <h2 id="execution-limits" className="m-0 text-xs font-bold tracking-wide text-ink uppercase">
        {t("limitsTitle")}
      </h2>
      <ul className="m-0 list-disc space-y-1 pl-4">
        {LIMITS.map((k) => (
          <li key={k}>{t(`limits.${k}`)}</li>
        ))}
      </ul>
    </aside>
  );
}

function formatAttemptValue(t: T, row: ExecutionRowView, latest: AttemptVersionView): string {
  if (latest.outcome_kind === "not_performable") {
    return t("notPerformableDisplay", { reason: latest.not_performable_reason ?? "" });
  }
  const v = latest.value;
  if (!v) return "—";
  if (v.type === "number") {
    const ac = row.test_step?.acceptance;
    const unit = ac && (ac.type === "number" || ac.type === "range") ? ` ${ac.unit}` : "";
    return `${v.value}${unit}`;
  }
  if (v.type === "one_of") {
    return v.not_one_of ? `${t("oneOfNotListed")}: ${v.value}` : v.value;
  }
  return v.value ? t("presentTrue") : t("presentFalse");
}

function WitnessConfirmForm({
  t,
  executionId,
  requirement,
  attemptNumber,
  versionNumber,
  versionHash,
  witnessAction,
}: {
  t: T;
  executionId: number;
  requirement: string;
  attemptNumber: number;
  versionNumber: number;
  versionHash: string;
  witnessAction: (
    prevState: ExecutionActionState,
    formData: FormData,
  ) => Promise<ExecutionActionState>;
}) {
  const [state, formAction] = useActionState(witnessAction, INITIAL_STATE);
  return (
    <form action={formAction} className="space-y-1.5 pt-1">
      <input type="hidden" name="execution_id" value={executionId} />
      <input type="hidden" name="requirement" value={requirement} />
      <input type="hidden" name="attempt_number" value={attemptNumber} />
      <input type="hidden" name="version_number" value={versionNumber} />
      <input type="hidden" name="version_hash" value={versionHash} />
      {!state.ok && state.error && (
        <div
          role="alert"
          className="flex items-start gap-1.5 rounded border border-fail-edge bg-fail-soft px-2 py-1 text-[11px] text-fail"
        >
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>{state.detail ?? t(`errors.${state.error}`)}</span>
        </div>
      )}
      <SubmitButton variant="soft">
        <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
        <span>{t("witnessConfirmButton")}</span>
      </SubmitButton>
    </form>
  );
}

function ExecutionRow({
  t,
  m,
  when,
  row,
  runId,
  executionId,
  executionInProgress,
  currentUser,
  canRecord,
  witnessAction,
  onRecord,
}: {
  t: T;
  m: MatrixT;
  when: WhenT;
  row: ExecutionRowView;
  runId: string;
  executionId: number;
  executionInProgress: boolean;
  currentUser: { subject: string; issuer: string } | null;
  canRecord: boolean;
  witnessAction:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  onRecord: () => void;
}) {
  const step = row.test_step;
  const latestAttempt = row.attempts[row.attempts.length - 1];
  const latest = latestAttempt?.latest;
  const confirmations = latest?.witness_confirmations ?? [];
  const isPerformer =
    latest !== undefined &&
    currentUser !== null &&
    currentUser.subject === latest.subject &&
    currentUser.issuer === latest.issuer;
  const alreadyConfirmed =
    currentUser !== null &&
    confirmations.some(
      (w) => w.subject === currentUser.subject && w.issuer === currentUser.issuer,
    );

  return (
    <tr data-testid={`exec-row-${row.requirement}`} className="border-b border-border last:border-b-0">
      <th scope="row" className="max-w-[260px] px-3 py-2.5 text-left align-top font-normal">
        <div className="font-mono text-xs font-semibold text-ink tabular-nums">{row.requirement}</div>
        <div className="mt-0.5 text-xs text-ink-muted">{row.text}</div>
        <div className="mt-1">
          <PdfCitationButton runId={runId} cite={row.source} compact />
        </div>
      </th>

      <td className="px-3 py-2.5 align-top whitespace-nowrap">
        <span className="inline-flex rounded border border-border bg-sunken px-2 py-0.5 text-[11px] font-semibold text-ink">
          {t(`kinds.${row.kind}`)}
        </span>
      </td>

      <td className="max-w-[400px] px-3 py-2.5 align-top">
        {row.kind === "vendor_reference" ? (
          <div className="space-y-1.5">
            <ul className="m-0 list-disc space-y-0.5 pl-4 text-xs text-ink tabular-nums">
              {row.evidence.map((e) => (
                <li key={`${e.doc}/${e.rev}/${e.step}`}>
                  {t("evidenceStep", { doc: e.doc, rev: e.rev, step: e.step })}
                </li>
              ))}
            </ul>
            <p className="m-0 text-[11px] text-ink-muted">{t("vendorNoControls")}</p>
          </div>
        ) : (
          step && (
            <dl className="m-0 space-y-1 text-xs">
              <div>
                <dt className="inline font-semibold text-ink-muted">{t("description")}: </dt>
                <dd className="m-0 inline text-ink">{step.description}</dd>
              </div>
              <div>
                <dt className="inline font-semibold text-ink-muted">{t("method")}: </dt>
                <dd className="m-0 inline text-ink">{step.method}</dd>
              </div>
              <div>
                <dt className="inline font-semibold text-ink-muted">{t("instrument")}: </dt>
                <dd className="m-0 inline text-ink">{step.instrument ?? t("noInstrument")}</dd>
              </div>
            </dl>
          )
        )}
      </td>

      <td className="px-3 py-2.5 align-top text-xs font-medium text-ink tabular-nums">
        {step ? formatValue(m, step.acceptance) : "—"}
      </td>

      <td className="min-w-[220px] px-3 py-2.5 align-top text-xs">
        {row.kind === "vendor_reference" ? (
          <span className="text-ink-muted">—</span>
        ) : latest ? (
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <VerdictBadge verdict={latest.verdict} />
              <span className="font-semibold text-ink tabular-nums">
                {formatAttemptValue(t, row, latest)}
              </span>
            </div>
            {latest.instruments.length > 0 && (
              <ul className="m-0 list-disc space-y-0.5 pl-4 text-[11px] text-ink-muted tabular-nums">
                {latest.instruments.map((inst) => (
                  <li key={`${inst.identifier}-${inst.calibration_due_date}`}>
                    {inst.identifier} ({inst.calibration_due_date})
                  </li>
                ))}
              </ul>
            )}
            {latest.no_calibrated_instrument_reason && (
              <p className="m-0 text-[11px] text-warn">
                {t("noCalibratedDisplay", { reason: latest.no_calibrated_instrument_reason })}
              </p>
            )}
            {latest.evidence.length > 0 && (
              <div className="text-[11px] text-ink-muted">
                {t("evidenceTitle")}: {latest.evidence.join(", ")}
              </div>
            )}
            {latest.observation && (
              <p className="m-0 text-[11px] text-ink-muted">{latest.observation}</p>
            )}
            <div className="text-[11px] text-ink-muted tabular-nums">
              {t("recordedBy", { name: latest.name, when: formatWhen(when, latest.at) })}
            </div>

            <div className="space-y-1 border-t border-border pt-1.5">
              {confirmations.length > 0 ? (
                <ul className="m-0 list-none space-y-1 p-0">
                  {confirmations.map((w) => (
                    <li key={w.id} className="space-y-0.5 text-[11px]">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span
                          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                            w.voided
                              ? "border-warn-edge bg-warn-soft text-warn"
                              : "border-pass-edge bg-pass-soft text-pass"
                          }`}
                        >
                          <ShieldCheck className="h-3 w-3 shrink-0" aria-hidden="true" />
                          <span>
                            {w.voided ? t("witnessVoidedBadge") : t("witnessConfirmedBadge")}
                          </span>
                        </span>
                        <span className="text-ink tabular-nums">
                          {t("witnessedBy", { name: w.name, when: formatWhen(when, w.at) })}
                        </span>
                      </div>
                      <div className="text-[10px] text-ink-muted">{t("witnessNotSignatureNote")}</div>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="text-[11px] text-ink-muted">{t("witnessNotConfirmed")}</div>
              )}

              {witnessAction !== null && executionInProgress && latestAttempt && (
                <>
                  {isPerformer ? (
                    <p className="m-0 text-[11px] text-ink-muted">{t("witnessPerformerRefused")}</p>
                  ) : alreadyConfirmed ? (
                    <p className="m-0 text-[11px] text-ink-muted">{t("witnessAlreadyConfirmed")}</p>
                  ) : (
                    <WitnessConfirmForm
                      t={t}
                      executionId={executionId}
                      requirement={row.requirement}
                      attemptNumber={latestAttempt.attempt_number}
                      versionNumber={latest.version}
                      versionHash={latest.version_hash}
                      witnessAction={witnessAction}
                    />
                  )}
                </>
              )}
            </div>
          </div>
        ) : canRecord ? (
          <Button type="button" variant="soft" onClick={onRecord}>
            {t("recordResult")}
          </Button>
        ) : (
          <span className="text-ink-muted">—</span>
        )}
      </td>
    </tr>
  );
}

function DeviationsSection({
  t,
  deviations,
  canOpenManual,
  onOpenManual,
  onSelectDeviation,
}: {
  t: T;
  deviations: DeviationView[];
  canOpenManual: boolean;
  onOpenManual: () => void;
  onSelectDeviation: (id: number) => void;
}) {
  return (
    <section aria-labelledby="execution-deviations" className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="execution-deviations" className="m-0 text-sm font-bold text-ink tabular-nums">
          {t("deviationsTitle", { count: deviations.length })}
        </h2>
        {canOpenManual && (
          <Button type="button" variant="soft" onClick={onOpenManual}>
            {t("openManualDeviation")}
          </Button>
        )}
      </div>
      {deviations.length === 0 ? (
        <p className="m-0 rounded-lg border border-border bg-surface px-4 py-3 text-xs text-ink-muted">
          {t("deviationsEmpty")}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-surface shadow-xs">
          <table className="w-full border-collapse text-left text-xs">
            <thead className="border-b border-border bg-sunken text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
              <tr>
                <th scope="col" className="px-3 py-2">
                  {t("deviationColNumber")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("deviationColStatus")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("deviationColClass")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("deviationColStep")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("deviationColDescription")}
                </th>
              </tr>
            </thead>
            <tbody>
              {deviations.map((d) => (
                <tr key={d.id} className="border-b border-border last:border-b-0">
                  <th scope="row" className="px-3 py-2.5 text-left font-mono font-semibold text-ink tabular-nums">
                    <button
                      type="button"
                      onClick={() => onSelectDeviation(d.id)}
                      className="cursor-pointer rounded border-0 bg-transparent p-0 font-mono text-xs font-semibold text-accent underline hover:text-accent-hover"
                    >
                      #{d.deviation_number}
                    </button>
                  </th>
                  <td className="px-3 py-2.5">
                    <DeviationStatusBadge status={d.status} />
                  </td>
                  <td className="px-3 py-2.5 text-ink-muted">
                    {d.deviation_class
                      ? t(`deviationClasses.${d.deviation_class}`)
                      : t("deviationClassUnset")}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-ink tabular-nums">
                    {d.requirement ?? "—"}
                  </td>
                  <td className="px-3 py-2.5 text-ink">{d.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function CompletionChecklistPanel({
  t,
  executionId,
  blockers,
  completeAction,
}: {
  t: T;
  executionId: number;
  blockers: CompletionBlockers;
  completeAction:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
}) {
  const [state, formAction] = useActionState(
    completeAction ?? (async () => INITIAL_STATE),
    INITIAL_STATE,
  );

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
          <form action={formAction}>
            <input type="hidden" name="execution_id" value={executionId} />
            <SubmitButton variant="primary" disabled={blockers.blocked}>
              {t("completion.completeButton")}
            </SubmitButton>
          </form>
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
            <div className="flex flex-wrap gap-1.5 pl-4">
              {blockers.rows_without_result.requirements.map((req) => (
                <span
                  key={req}
                  className="rounded border border-warn-edge bg-warn-soft px-2 py-0.5 font-mono text-[11px] font-semibold text-warn tabular-nums"
                >
                  {req}
                </span>
              ))}
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
              {blockers.open_deviations.items.map((d) => (
                <span
                  key={d.deviation_number}
                  className="rounded border border-warn-edge bg-warn-soft px-2 py-0.5 font-mono text-[11px] font-semibold text-warn tabular-nums"
                >
                  {t("completion.deviationItem", {
                    number: d.deviation_number,
                    status: t(`completion.deviationStatuses.${d.status}`),
                  })}
                </span>
              ))}
            </div>
          )}
        </li>
      </ul>
    </section>
  );
}

function ExecutionFrozenCopyPanel({
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
        <div className="text-[11px] font-semibold text-ink-muted">
          {t("completion.frozenHashLabel")}
        </div>
        <code className="block font-mono text-xs break-all text-ink tabular-nums">{copyHash}</code>
      </div>
    </section>
  );
}

export function ExecutionViewPanel({
  execution,
  protocol,
  runId,
  currentUser = null,
  startAction,
  recordAction = null,
  witnessAction = null,
  openDeviationAction = null,
  investigateAction = null,
  submitDeviationAction = null,
  closeDeviationAction = null,
  returnDeviationAction = null,
  completeAction = null,
}: {
  execution: ExecutionView | null;
  protocol: ProtocolView | null;
  runId: string;
  currentUser?: { subject: string; issuer: string } | null;
  startAction:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  recordAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  witnessAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  openDeviationAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  investigateAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  submitDeviationAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  closeDeviationAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  returnDeviationAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  completeAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
}) {
  const t = useTranslations("execution");
  const m = useTranslations("matrix");
  const when: WhenT = useTranslations("decisions");

  const [activeRequirement, setActiveRequirement] = useState<string | null>(null);
  const [manualDevOpen, setManualDevOpen] = useState(false);
  const [activeDeviationId, setActiveDeviationId] = useState<number | null>(null);
  const [state, formAction] = useActionState(
    startAction ?? (async () => INITIAL_STATE),
    INITIAL_STATE,
  );

  const protocolHref = `/runs/${encodeURIComponent(runId)}/protocol`;
  const activeRow =
    execution && activeRequirement
      ? (execution.rows.find((r) => r.requirement === activeRequirement) ?? null)
      : null;
  const activeDeviation =
    execution && activeDeviationId !== null
      ? (execution.deviations.find((d) => d.id === activeDeviationId) ?? null)
      : null;

  return (
    <div className="space-y-4">
      {!state.ok && state.error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-fail-edge bg-fail-soft px-3.5 py-2.5 text-xs text-fail"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{t(`errors.${state.error}`)}</span>
        </div>
      )}

      {execution === null ? (
        protocol === null || protocol.status !== "approved" ? (
          <EmptyState title={t("noApprovedProtocol")}>
            <p className="m-0 mb-3 text-xs text-ink-muted">{t("noApprovedProtocolBody")}</p>
            <Link
              href={protocolHref}
              className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent no-underline hover:bg-accent-hover"
            >
              <span>{t("toProtocol")}</span>
              <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
            </Link>
          </EmptyState>
        ) : (
          <EmptyState title={t("notStarted")}>
            <p className="m-0 mb-3 text-xs text-ink-muted">
              {t("notStartedBody", { protocolId: protocol.id })}
            </p>
            {startAction !== null ? (
              <form action={formAction}>
                <input type="hidden" name="protocol_id" value={protocol.id} />
                <SubmitButton variant="primary">
                  <PlayCircle className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{t("start")}</span>
                </SubmitButton>
              </form>
            ) : (
              <p className="m-0 text-xs text-ink-muted">{t("notStartedReadOnly")}</p>
            )}
          </EmptyState>
        )
      ) : (
        <>
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
                {execution.events.map((e) => (
                  <li key={e.id}>
                    {t(`events.${e.event}`, { name: e.name, when: formatWhen(when, e.at) })}
                  </li>
                ))}
              </ol>
            </div>
          </section>

          {execution.status === "in_progress" ? (
            <CompletionChecklistPanel
              t={t}
              executionId={execution.id}
              blockers={execution.completion_blockers}
              completeAction={completeAction}
            />
          ) : (
            execution.frozen_copy &&
            execution.copy_hash && (
              <ExecutionFrozenCopyPanel
                t={t}
                when={when}
                frozenCopy={execution.frozen_copy}
                copyHash={execution.copy_hash}
              />
            )
          )}

          <section aria-labelledby="execution-rows" className="space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 id="execution-rows" className="m-0 text-sm font-bold text-ink tabular-nums">
                {t("rows", { count: execution.rows.length })}
              </h2>
              <span className="text-xs text-ink-muted">{t("rowsNote")}</span>
            </div>
            <p className="m-0 text-xs text-ink-muted">{t("utcNote")}</p>

            <div className="overflow-x-auto rounded-lg border border-border bg-surface shadow-xs">
              <table className="w-full border-collapse text-left text-xs">
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
                <tbody>
                  {execution.rows.map((r) => (
                    <ExecutionRow
                      key={r.requirement}
                      t={t}
                      m={m}
                      when={when}
                      row={r}
                      runId={runId}
                      executionId={execution.id}
                      executionInProgress={execution.status === "in_progress"}
                      currentUser={currentUser}
                      canRecord={
                        execution.status === "in_progress" &&
                        r.kind === "test_step" &&
                        r.attempts.length === 0 &&
                        recordAction !== null
                      }
                      witnessAction={witnessAction}
                      onRecord={() => setActiveRequirement(r.requirement)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <DeviationsSection
            t={t}
            deviations={execution.deviations}
            canOpenManual={execution.status === "in_progress" && openDeviationAction !== null}
            onOpenManual={() => setManualDevOpen(true)}
            onSelectDeviation={(id) => setActiveDeviationId(id)}
          />

          {activeRow && recordAction && (
            <ExecutionResultDrawer
              key={activeRow.requirement}
              executionId={execution.id}
              row={activeRow}
              open={true}
              onOpenChange={(open) => {
                if (!open) setActiveRequirement(null);
              }}
              recordAction={recordAction}
            />
          )}

          {manualDevOpen && openDeviationAction && (
            <ManualDeviationDrawer
              executionId={execution.id}
              rows={execution.rows}
              open={true}
              onOpenChange={setManualDevOpen}
              openAction={openDeviationAction}
            />
          )}

          {activeDeviation && (
            <DeviationDetailDrawer
              key={activeDeviation.id}
              executionId={execution.id}
              executionInProgress={execution.status === "in_progress"}
              deviation={activeDeviation}
              open={true}
              onOpenChange={(open) => {
                if (!open) setActiveDeviationId(null);
              }}
              investigateAction={investigateAction}
              submitAction={submitDeviationAction}
              closeAction={closeDeviationAction}
              returnAction={returnDeviationAction}
            />
          )}
        </>
      )}

      <Limits t={t} />
    </div>
  );
}
