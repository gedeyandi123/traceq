"use client";

import { AlertCircle, ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { useActionState, useState } from "react";

import type {
  AttemptVersionView,
  AttemptView,
  DeviationView,
  ExecutionRowView,
} from "@/api/client";
import type { SigningAuthState } from "@/auth/session";
import type { ExecutionActionState } from "@/execution/actions";
import { ElectronicSignatureDialog } from "./ElectronicSignatureDialog";
import { formatWhen } from "./formatWhen";
import { formatValue } from "./MatrixTable";
import { SignatureBadge } from "./SignatureBadge";
import { Drawer } from "./ui/Drawer";
import { PdfCitationButton } from "./ui/PdfCitationModal";
import { VerdictBadge } from "./ui/StatusBadge";
import { Button } from "./ui/ui";

type T = ReturnType<typeof useTranslations<"execution">>;
type MatrixT = ReturnType<typeof useTranslations<"matrix">>;
type WhenT = ReturnType<typeof useTranslations<"decisions">>;

const INITIAL_STATE: ExecutionActionState = { ok: true };
const numberFormatter = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 3 });

export function formatAttemptValue(
  t: T,
  row: ExecutionRowView,
  latest: AttemptVersionView,
): string {
  if (latest.outcome_kind === "not_performable") {
    return t("notPerformableDisplay", { reason: latest.not_performable_reason ?? "" });
  }
  const v = latest.value;
  if (!v) return "—";
  if (v.type === "number") {
    const ac = row.test_step?.acceptance;
    const unit = ac && (ac.type === "number" || ac.type === "range") ? ` ${ac.unit}` : "";
    return `${numberFormatter.format(v.value)}${unit}`;
  }
  if (v.type === "one_of") {
    return v.not_one_of ? `${t("oneOfNotListed")}: ${v.value}` : v.value;
  }
  return v.value ? t("presentTrue") : t("presentFalse");
}

function WitnessConfirmForm({
  t,
  runId,
  executionId,
  requirement,
  attemptNumber,
  versionNumber,
  versionHash,
  signingAuth,
  initialReauthTarget,
  witnessAction,
}: {
  t: T;
  runId: string;
  executionId: number;
  requirement: string;
  attemptNumber: number;
  versionNumber: number;
  versionHash: string;
  signingAuth: SigningAuthState;
  initialReauthTarget: string | null;
  witnessAction: (
    prevState: ExecutionActionState,
    formData: FormData,
  ) => Promise<ExecutionActionState>;
}) {
  const targetKey = `witness_confirmation:${requirement}:${attemptNumber}:${versionNumber}`;
  const [dialogOpen, setDialogOpen] = useState(() => initialReauthTarget === targetKey);
  const [state, formAction] = useActionState(
    async (prev: ExecutionActionState, fd: FormData) => {
      const res = await witnessAction(prev, fd);
      if (res.ok) setDialogOpen(false);
      return res;
    },
    INITIAL_STATE,
  );

  return (
    <div className="space-y-1.5">
      <Button type="button" variant="soft" onClick={() => setDialogOpen(true)}>
        {t("witnessConfirmButton")}
      </Button>
      <p className="m-0 text-[10px] text-ink-muted">{t("witnessNotSignatureNote")}</p>
      {!state.ok && state.error && (
        <div
          role="alert"
          className="flex items-start gap-1.5 rounded border border-fail-edge bg-fail-soft px-2 py-1 text-[11px] text-fail"
        >
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>{state.detail ?? t(`errors.${state.error}`)}</span>
        </div>
      )}
      <ElectronicSignatureDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title={t("witnessConfirmButton")}
        targetSummary={`${requirement} · #${attemptNumber} v${versionNumber}`}
        signatureMeaning="witnessed"
        contentHash={versionHash}
        signingAuth={signingAuth}
        signer={signingAuth.signer}
        reauthNextUrl={`/runs/${encodeURIComponent(runId)}/execution?reauth_target=${encodeURIComponent(targetKey)}`}
        action={formAction}
        confirmLabel={t("witnessConfirmButton")}
        error={!state.ok && state.error ? (state.detail ?? t(`errors.${state.error}`)) : null}
        isReauthError={!state.ok && state.error === "reauth_required"}
      >
        <input type="hidden" name="execution_id" value={executionId} />
        <input type="hidden" name="requirement" value={requirement} />
        <input type="hidden" name="attempt_number" value={attemptNumber} />
        <input type="hidden" name="version_number" value={versionNumber} />
        <input type="hidden" name="version_hash" value={versionHash} />
      </ElectronicSignatureDialog>
    </div>
  );
}

export function ExecutionRowDrawer({
  row,
  runId,
  executionId,
  executionInProgress,
  deviations,
  currentUser,
  canRecord,
  canCorrect,
  canRetest,
  witnessAction,
  signingAuth = { oidcMode: false, reauthAuthTime: null, signer: null },
  initialReauthTarget = null,
  open,
  onOpenChange,
  onRecord,
  onCorrect,
  onRetest,
}: {
  row: ExecutionRowView | null;
  runId: string;
  executionId: number;
  executionInProgress: boolean;
  deviations: DeviationView[];
  currentUser: { subject: string; issuer: string } | null;
  canRecord: boolean;
  canCorrect: boolean;
  canRetest: boolean;
  witnessAction:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  signingAuth?: SigningAuthState;
  initialReauthTarget?: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRecord: () => void;
  onCorrect: (attempt: AttemptView) => void;
  onRetest: (openDeviations: DeviationView[]) => void;
}) {
  const t = useTranslations("execution");
  const m = useTranslations("matrix");
  const when = useTranslations("decisions");

  if (!row) {
    return (
      <Drawer open={false} onOpenChange={() => {}} title="" size="wide">
        {null}
      </Drawer>
    );
  }

  const step = row.test_step;
  const openStepDeviations = deviations.filter(
    (d) => d.requirement === row.requirement && d.status !== "closed",
  );
  const lastAttempt = row.attempts[row.attempts.length - 1];
  const latestOfLast = lastAttempt?.latest ?? null;

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      size="wide"
      title={row.requirement}
      description={row.text}
    >
      <div className="space-y-5 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-sunken px-3 py-2">
          <span className="font-semibold text-ink">{t(`kinds.${row.kind}`)}</span>
          <PdfCitationButton runId={runId} cite={row.source} compact />
        </div>

        {row.kind === "vendor_reference" ? (
          <div className="space-y-2 border-t border-border pt-4">
            <ul className="m-0 list-disc space-y-1 pl-4 text-ink-muted tabular-nums">
              {row.evidence.map((e) => (
                <li key={`${e.doc}/${e.rev}/${e.step}`}>
                  {t("evidenceStep", { doc: e.doc, rev: e.rev, step: e.step })}
                </li>
              ))}
            </ul>
            <p className="m-0 text-ink-muted">{t("vendorNoControls")}</p>
          </div>
        ) : (
          <>
            {step && (
              <dl className="m-0 space-y-2 border-t border-border pt-4">
                <div>
                  <dt className="font-semibold text-ink-muted">{t("description")}</dt>
                  <dd className="m-0 mt-0.5 text-ink">{step.description}</dd>
                </div>
                <div>
                  <dt className="font-semibold text-ink-muted">{t("method")}</dt>
                  <dd className="m-0 mt-0.5 text-ink">{step.method}</dd>
                </div>
                <div>
                  <dt className="font-semibold text-ink-muted">{t("instrument")}</dt>
                  <dd className="m-0 mt-0.5 text-ink">{step.instrument ?? t("noInstrument")}</dd>
                </div>
                <div>
                  <dt className="font-semibold text-ink-muted">{t("colAcceptance")}</dt>
                  <dd className="m-0 mt-0.5 font-medium text-ink tabular-nums">
                    {formatValue(m, step.acceptance)}
                  </dd>
                </div>
              </dl>
            )}

            <section className="space-y-3 border-t border-border pt-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="m-0 text-xs font-bold tracking-wide text-ink-muted uppercase">
                  {t("colResult")}
                </h3>
                {canRecord && (
                  <Button type="button" variant="primary" onClick={onRecord}>
                    {t("recordResult")}
                  </Button>
                )}
              </div>

              {row.attempts.length === 0 ? (
                <p className="m-0 text-ink-muted">—</p>
              ) : (
                <div className="space-y-3">
                  {row.attempts.map((attempt, attemptIdx) => {
                    const isLatestAttempt = attemptIdx === row.attempts.length - 1;
                    const isAttemptPerformer =
                      currentUser !== null &&
                      attempt.subject === currentUser.subject &&
                      attempt.issuer === currentUser.issuer;

                    return (
                      <div
                        key={attempt.attempt_number}
                        className="space-y-2.5 border-l-2 border-border-strong bg-sunken/60 p-3"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-semibold text-ink tabular-nums">
                            {t("attemptNumber", { number: attempt.attempt_number })}
                          </span>
                          {executionInProgress && canCorrect && isAttemptPerformer && (
                            <Button type="button" variant="soft" onClick={() => onCorrect(attempt)}>
                              {t("correctAttemptButton")}
                            </Button>
                          )}
                        </div>

                        <div className="space-y-2">
                          {attempt.versions.map((ver, verIdx) => {
                            const isLatestVersion = verIdx === attempt.versions.length - 1;
                            const isCurrentResult = isLatestAttempt && isLatestVersion;
                            const confirmations = ver.witness_confirmations ?? [];
                            const isVersionPerformer =
                              currentUser !== null &&
                              ver.subject === currentUser.subject &&
                              ver.issuer === currentUser.issuer;
                            const alreadyConfirmed =
                              currentUser !== null &&
                              confirmations.some(
                                (w) =>
                                  w.subject === currentUser.subject &&
                                  w.issuer === currentUser.issuer,
                              );

                            return (
                              <div
                                key={ver.version}
                                className={`space-y-1.5 rounded-md border p-2.5 ${
                                  isCurrentResult
                                    ? "border-accent/40 bg-surface"
                                    : "border-border bg-canvas/70"
                                }`}
                              >
                                <div className="flex flex-wrap items-center gap-1.5">
                                  <span className="rounded bg-sunken px-1.5 py-0.5 font-mono text-[10px] font-bold text-ink tabular-nums">
                                    v{ver.version}
                                  </span>
                                  {isCurrentResult && (
                                    <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-semibold text-accent">
                                      {t("currentResultBadge")}
                                    </span>
                                  )}
                                  <VerdictBadge verdict={ver.verdict} />
                                  <span className="font-semibold text-ink tabular-nums">
                                    {formatAttemptValue(t, row, ver)}
                                  </span>
                                  <code
                                    title={ver.version_hash}
                                    className="rounded bg-sunken px-1.5 py-0.5 font-mono text-[10px] text-ink-muted tabular-nums"
                                  >
                                    {ver.version_hash.slice(0, 12)}
                                  </code>
                                </div>

                                {ver.reason_for_change && (
                                  <div className="text-[11px] text-ink">
                                    <span className="font-semibold text-ink-muted">
                                      {t("reasonForChangeLabel")}:{" "}
                                    </span>
                                    <span>{ver.reason_for_change}</span>
                                  </div>
                                )}

                                {ver.instruments.length > 0 && (
                                  <ul className="m-0 list-disc space-y-0.5 pl-4 text-[11px] text-ink-muted tabular-nums">
                                    {ver.instruments.map((inst) => (
                                      <li key={`${inst.identifier}-${inst.calibration_due_date}`}>
                                        {inst.identifier} ({inst.calibration_due_date})
                                      </li>
                                    ))}
                                  </ul>
                                )}
                                {ver.no_calibrated_instrument_reason && (
                                  <p className="m-0 text-[11px] text-warn">
                                    {t("noCalibratedDisplay", {
                                      reason: ver.no_calibrated_instrument_reason,
                                    })}
                                  </p>
                                )}
                                {ver.evidence.length > 0 && (
                                  <div className="text-[11px] text-ink-muted">
                                    {t("evidenceTitle")}: {ver.evidence.join(", ")}
                                  </div>
                                )}
                                {ver.observation && (
                                  <p className="m-0 text-[11px] text-ink-muted">{ver.observation}</p>
                                )}
                                <div className="text-[11px] text-ink-muted tabular-nums">
                                  {t("recordedBy", { name: ver.name, when: formatWhen(when, ver.at) })}
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
                                                {w.voided
                                                  ? t("witnessVoidedBadge")
                                                  : t("witnessConfirmedBadge")}
                                              </span>
                                            </span>
                                            <span className="text-ink tabular-nums">
                                              {t("witnessedBy", {
                                                name: w.name,
                                                when: formatWhen(when, w.at),
                                              })}
                                            </span>
                                          </div>
                                          <div className="text-[10px] text-ink-muted">
                                            {t("witnessNotSignatureNote")}
                                          </div>
                                          <SignatureBadge
                                            signature={w.electronic_signature}
                                            voided={w.voided}
                                            compact
                                          />
                                        </li>
                                      ))}
                                    </ul>
                                  ) : (
                                    isCurrentResult && (
                                      <div className="text-[11px] text-ink-muted">
                                        {t("witnessNotConfirmed")}
                                      </div>
                                    )
                                  )}

                                  {isCurrentResult && witnessAction !== null && executionInProgress && (
                                    <>
                                      {isVersionPerformer ? (
                                        <p className="m-0 text-[11px] text-ink-muted">
                                          {t("witnessPerformerRefused")}
                                        </p>
                                      ) : alreadyConfirmed ? (
                                        <p className="m-0 text-[11px] text-ink-muted">
                                          {t("witnessAlreadyConfirmed")}
                                        </p>
                                      ) : (
                                        <WitnessConfirmForm
                                          t={t}
                                          runId={runId}
                                          executionId={executionId}
                                          requirement={row.requirement}
                                          attemptNumber={attempt.attempt_number}
                                          versionNumber={ver.version}
                                          versionHash={ver.version_hash}
                                          signingAuth={signingAuth}
                                          initialReauthTarget={initialReauthTarget}
                                          witnessAction={witnessAction}
                                        />
                                      )}
                                    </>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}

                  {executionInProgress &&
                    canRetest &&
                    latestOfLast?.verdict === "fail" &&
                    openStepDeviations.length > 0 && (
                      <div>
                        <Button
                          type="button"
                          variant="soft"
                          onClick={() => onRetest(openStepDeviations)}
                        >
                          {t("retestButton")}
                        </Button>
                      </div>
                    )}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </Drawer>
  );
}
