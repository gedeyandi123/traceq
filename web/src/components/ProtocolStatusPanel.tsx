"use client";

import { AlertTriangle, ArrowRight, CheckCircle2, History as HistoryIcon, Info } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";

import type { ProtocolEvent, ProtocolView } from "@/api/client";
import type { SigningAuthState } from "@/auth/session";
import type { ApprovalControls, ProtocolControls, ProtocolError } from "./AssembledProtocolView";
import { useSigningDialog } from "./useSigningDialog";
import { ElectronicSignatureDialog } from "./ElectronicSignatureDialog";
import { formatWhen } from "./formatWhen";
import { SignatureBadge } from "./SignatureBadge";
import { FIELD_BASE_CLASS } from "./ui/FormControls";
import { Modal } from "./ui/Modal";
import { ProtocolStatusBadge } from "./ui/StatusBadge";
import { SubmitButton } from "./ui/SubmitButton";
import { Button } from "./ui/ui";

type T = ReturnType<typeof useTranslations<"protocol">>;

const TEXTAREA_CLASS = `w-full text-xs ${FIELD_BASE_CLASS}`;

export function StartForm({
  t,
  runId,
  action,
  again,
  hasDraft = false,
}: {
  t: T;
  runId: string;
  action: ProtocolControls;
  again: boolean;
  /** The run read a Protocol Draft: the Protocol may start from it instead. */
  hasDraft?: boolean;
}) {
  if (action === null) return null;
  return (
    <div className="flex flex-wrap items-start gap-3">
      <form action={action.start}>
        <input type="hidden" name="run_id" value={runId} />
        <SubmitButton variant={hasDraft ? "soft" : "primary"}>
          {t(again ? "startAgain" : "start")}
        </SubmitButton>
      </form>
      {hasDraft && (
        <form action={action.start} className="space-y-1">
          <input type="hidden" name="run_id" value={runId} />
          <input type="hidden" name="from_draft" value="true" />
          <SubmitButton variant="primary">{t("draftFlow.start")}</SubmitButton>
          <p className="m-0 max-w-md text-[11px] text-ink-muted">{t("draftFlow.startNote")}</p>
        </form>
      )}
    </div>
  );
}

/** Chronological protocol lifecycle event timeline. */
export function ProtocolHistory({
  t,
  events,
  headingLevel = "h3",
}: {
  t: T;
  events: readonly ProtocolEvent[];
  headingLevel?: "h2" | "h3";
}) {
  const when = useTranslations("decisions");
  const Heading = headingLevel;
  return (
    <section
      aria-labelledby="protocol-history"
      className="space-y-3 rounded-lg border border-border bg-surface p-4"
    >
      <Heading id="protocol-history" className="m-0 flex items-center gap-2 text-sm font-bold text-ink">
        <HistoryIcon className="h-4 w-4 text-ink-muted" aria-hidden="true" />
        <span>{t("history")}</span>
      </Heading>
      <ol className="m-0 list-decimal space-y-2 pl-5 text-xs tabular-nums">
        {events.map((e) => (
          <li key={e.id} className="space-y-1 text-ink">
            <div>{t(`events.${e.event}`, { name: e.name, when: formatWhen(when, e.at) })}</div>
            {(e.event === "submitted" || e.event === "approved") && (
              <SignatureBadge signature={e.electronic_signature} compact />
            )}
            {e.reason && (
              <div className="rounded border border-border bg-sunken px-2.5 py-1.5 text-ink-muted italic">
                {e.reason}
              </div>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

/** Approve (bound to the submission shown: its event id and hash) and return with a reason
 * inside a Radix Confirmation Modal, for the approving role while Submitted. */
function ApprovalForms({
  t,
  protocol,
  runId,
  approval,
  signingAuth,
  initialReauthTarget,
  error,
}: {
  t: T;
  protocol: ProtocolView;
  runId: string;
  approval: ApprovalControls;
  signingAuth: SigningAuthState;
  initialReauthTarget: string | null;
  error?: ProtocolError;
}) {
  const { open: approveOpen, setOpen: setApproveOpen } = useSigningDialog(
    error,
    initialReauthTarget === "protocol_approval",
  );
  const [returnOpen, setReturnOpen] = useState(false);
  const shown = protocol.submission;
  if (protocol.status !== "submitted" || approval === null || shown === null) return null;

  return (
    <div className="space-y-3 rounded-lg border border-info-edge bg-info-soft p-3.5 text-xs text-ink">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="primary" onClick={() => setApproveOpen(true)}>
          {t("approval.approve")}
        </Button>
        <button
          type="button"
          onClick={() => setReturnOpen(true)}
          className="inline-flex cursor-pointer items-center justify-center rounded-md border border-fail-edge bg-surface px-3 py-1.5 text-xs font-semibold text-fail hover:bg-fail-soft"
        >
          {t("approval.return")}
        </button>
      </div>

      <ElectronicSignatureDialog
        open={approveOpen}
        onOpenChange={setApproveOpen}
        title={t("approval.approve")}
        targetSummary={t("status", { id: protocol.id })}
        signatureMeaning="approved"
        contentHash={shown.hash}
        signingAuth={signingAuth}
        signer={signingAuth.signer}
        reauthNextUrl={`/runs/${encodeURIComponent(runId)}/protocol?reauth_target=protocol_approval`}
        action={approval.approve}
        confirmLabel={t("approval.approve")}
        cancelLabel={t("cancel")}
        error={error ? t(`errors.${error}`) : null}
        isReauthError={error === "reauth_required"}
      >
        <input type="hidden" name="run_id" value={runId} />
        <input type="hidden" name="protocol_id" value={protocol.id} />
        <input type="hidden" name="submission_event_id" value={shown.event_id} />
        <input type="hidden" name="hash" value={shown.hash} />
        {protocol.source && protocol.latest_draft_rev != null && (
          <input type="hidden" name="expected_latest_draft_rev" value={protocol.latest_draft_rev} />
        )}
      </ElectronicSignatureDialog>

      <Modal
        open={returnOpen}
        onOpenChange={setReturnOpen}
        size="sm"
        title={t("approval.returnModalTitle")}
        description={t("approval.returnModalDesc")}
      >
        <form action={approval.return} className="space-y-3">
          <input type="hidden" name="run_id" value={runId} />
          <input type="hidden" name="protocol_id" value={protocol.id} />
          <label className="block space-y-1 text-xs font-medium text-ink">
            <span>{t("approval.returnReason")}</span>
            <textarea
              name="reason"
              required
              rows={3}
              aria-label={t("approval.returnReason")}
              placeholder={t("approval.returnReason")}
              className={TEXTAREA_CLASS}
            />
          </label>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setReturnOpen(false)}
              className="inline-flex cursor-pointer items-center justify-center rounded-md border border-border-strong bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-sunken"
            >
              {t("cancel")}
            </button>
            <SubmitButton variant="danger">{t("approval.return")}</SubmitButton>
          </div>
        </form>
      </Modal>
    </div>
  );
}

const LIFECYCLE_STEPS = ["draft", "submitted", "approved"] as const;

/** Compact protocol status header card with 3-step lifecycle indicator, withdraw modal,
 * approve/return, SoD note, or restart after withdrawal. */
export function ProtocolStatusPanel({
  t,
  protocol,
  runId,
  controls,
  approval,
  signingAuth = { oidcMode: false, reauthAuthTime: null, signer: null },
  initialReauthTarget = null,
  error,
  hasDraft = false,
}: {
  t: T;
  protocol: ProtocolView;
  runId: string;
  controls: ProtocolControls;
  approval: ApprovalControls;
  signingAuth?: SigningAuthState;
  initialReauthTarget?: string | null;
  error?: ProtocolError;
  hasDraft?: boolean;
}) {
  const [withdrawOpen, setWithdrawOpen] = useState(false);
  const currentStepIdx =
    protocol.status === "approved" ? 2 : protocol.status === "submitted" ? 1 : 0;
  const latestSubmittedEvent = [...protocol.events]
    .reverse()
    .find((e) => e.event === "submitted");
  const latestApprovedEvent = [...protocol.events]
    .reverse()
    .find((e) => e.event === "approved");

  return (
    <section
      aria-labelledby="protocol-status"
      className="space-y-3 rounded-lg border border-border bg-surface p-4 shadow-xs"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <h2 id="protocol-status" className="m-0 text-base font-bold text-ink tabular-nums">
              {t("status", { id: protocol.id })}
            </h2>
            <ProtocolStatusBadge status={protocol.status} />
          </div>
          <p className="m-0 text-xs text-ink-muted tabular-nums">
            {t("startedFrom", { run: protocol.run_id })}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {protocol.status !== "withdrawn" && (
            <ol className="m-0 flex list-none items-center gap-1.5 p-0 text-[11px]">
              {LIFECYCLE_STEPS.map((step, idx) => {
                const done = idx < currentStepIdx;
                const current = idx === currentStepIdx;
                return (
                  <li key={step} className="flex items-center gap-1.5">
                    {idx > 0 && (
                      <span aria-hidden="true" className="text-ink-muted">
                        →
                      </span>
                    )}
                    <span
                      className={`rounded-full border px-2 py-0.5 font-semibold ${
                        current
                          ? "border-accent bg-accent-soft text-accent"
                          : done
                            ? "border-pass-edge bg-pass-soft text-pass"
                            : "border-border bg-sunken text-ink-muted"
                      }`}
                    >
                      {t(`lifecycle.${step}`)}
                    </span>
                  </li>
                );
              })}
            </ol>
          )}

          {protocol.status === "draft" && controls !== null && (
            <button
              type="button"
              onClick={() => setWithdrawOpen(true)}
              className="inline-flex cursor-pointer items-center justify-center gap-1.5 rounded-md border border-fail-edge bg-surface px-3 py-1.5 text-xs font-semibold text-fail hover:bg-fail-soft"
            >
              <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
              <span>{t("withdraw")}</span>
            </button>
          )}
        </div>
      </div>

      {protocol.status === "approved" && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-pass-edge bg-pass-soft px-3 py-2 text-xs text-pass">
            <div className="flex items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{t("limits.noNewVersion")}</span>
            </div>
            <Link
              href={`/runs/${encodeURIComponent(runId)}/execution`}
              className="inline-flex items-center gap-1 text-xs font-semibold text-accent no-underline hover:text-accent-hover hover:underline"
            >
              <span>{t("toExecution")}</span>
              <ArrowRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            </Link>
          </div>
          <SignatureBadge signature={latestApprovedEvent?.electronic_signature} />
        </div>
      )}

      {protocol.status === "submitted" && (
        <SignatureBadge signature={latestSubmittedEvent?.electronic_signature} />
      )}

      {protocol.status === "submitted" && controls !== null && approval === null && (
        <div className="flex items-start gap-2 rounded-md border border-info-edge bg-info-soft px-3 py-2 text-xs text-info">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{t("preparerSubmittedNote")}</span>
        </div>
      )}

      <ApprovalForms
        t={t}
        protocol={protocol}
        runId={runId}
        approval={approval}
        signingAuth={signingAuth}
        initialReauthTarget={initialReauthTarget}
        error={error}
      />

      {protocol.status === "withdrawn" && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-sunken px-3.5 py-2.5">
          <p className="m-0 text-xs text-ink-muted">{t("withdrawnNote")}</p>
          <StartForm t={t} runId={runId} action={controls} again hasDraft={hasDraft} />
        </div>
      )}

      {protocol.status === "draft" && controls !== null && (
        <Modal
          open={withdrawOpen}
          onOpenChange={setWithdrawOpen}
          size="sm"
          title={t("withdrawModalTitle")}
          description={t("withdrawModalDesc")}
        >
          <form action={controls.withdraw} className="space-y-3">
            <input type="hidden" name="run_id" value={runId} />
            <input type="hidden" name="protocol_id" value={protocol.id} />
            <label className="block space-y-1 text-xs font-medium text-ink">
              <span>{t("withdrawReason")}</span>
              <textarea
                name="reason"
                required
                rows={3}
                aria-label={t("withdrawReason")}
                placeholder={t("withdrawReason")}
                className={TEXTAREA_CLASS}
              />
            </label>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setWithdrawOpen(false)}
                className="inline-flex cursor-pointer items-center justify-center rounded-md border border-border-strong bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-sunken"
              >
                {t("cancel")}
              </button>
              <SubmitButton variant="danger">{t("withdraw")}</SubmitButton>
            </div>
          </form>
        </Modal>
      )}
    </section>
  );
}
