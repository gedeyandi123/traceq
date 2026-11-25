"use client";

import { AlertCircle, CheckCircle2, Info, Send, Undo2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useActionState, useState } from "react";

import type { DeviationView } from "@/api/client";
import type { ExecutionActionState } from "@/execution/actions";
import { formatWhen } from "./formatWhen";
import { Drawer } from "./ui/Drawer";
import { DeviationStatusBadge } from "./ui/StatusBadge";
import { SubmitButton } from "./ui/SubmitButton";

type Action = (
  prevState: ExecutionActionState,
  formData: FormData,
) => Promise<ExecutionActionState>;

const INITIAL_STATE: ExecutionActionState = { ok: true };

const CLASSES = ["minor", "major", "critical"] as const;

/** Drawer showing full Deviation detail, Investigation history, status history, and
 * role-gated Investigation / Submit / Close / Return controls (ADR 0013, spec #273). */
export function DeviationDetailDrawer({
  executionId,
  executionInProgress,
  deviation,
  open,
  onOpenChange,
  investigateAction,
  submitAction,
  closeAction,
  returnAction,
}: {
  executionId: number;
  executionInProgress: boolean;
  deviation: DeviationView;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  investigateAction: Action | null;
  submitAction: Action | null;
  closeAction: Action | null;
  returnAction: Action | null;
}) {
  const t = useTranslations("execution");
  const when = useTranslations("decisions");

  const latestInv = deviation.investigations[deviation.investigations.length - 1];
  const [investigationText, setInvestigationText] = useState(latestInv?.investigation ?? "");
  const [deviationClass, setDeviationClass] = useState<"minor" | "major" | "critical">(
    latestInv?.deviation_class ?? "minor",
  );
  const [capa, setCapa] = useState(latestInv?.capa ?? "");
  const [reasonForChange, setReasonForChange] = useState("");
  const [returnReason, setReturnReason] = useState("");

  const [invState, invFormAction] = useActionState(
    async (prev: ExecutionActionState, fd: FormData) => {
      if (!investigateAction) return prev;
      const res = await investigateAction(prev, fd);
      if (res.ok) {
        setReasonForChange("");
      }
      return res;
    },
    INITIAL_STATE,
  );

  const [subState, subFormAction] = useActionState(
    submitAction ?? (async () => INITIAL_STATE),
    INITIAL_STATE,
  );
  const [closeState, closeFormAction] = useActionState(
    closeAction ?? (async () => INITIAL_STATE),
    INITIAL_STATE,
  );
  const [retState, retFormAction] = useActionState(
    async (prev: ExecutionActionState, fd: FormData) => {
      if (!returnAction) return prev;
      const res = await returnAction(prev, fd);
      if (res.ok) {
        setReturnReason("");
      }
      return res;
    },
    INITIAL_STATE,
  );

  const activeError = [invState, subState, closeState, retState].find((s) => !s.ok && s.error);
  const canInvestigate =
    executionInProgress && deviation.status === "open" && investigateAction !== null;
  const canSubmit =
    executionInProgress &&
    deviation.status === "open" &&
    deviation.investigations.length > 0 &&
    submitAction !== null;
  const canApprove = executionInProgress && deviation.status === "submitted";

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title={t("deviationDetailTitle", { number: deviation.deviation_number })}
      description={deviation.requirement ?? t("deviationLinkExecution")}
      headerExtra={<DeviationStatusBadge status={deviation.status} />}
    >
      <div className="space-y-5 text-xs">
        {activeError && activeError.error && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-fail-edge bg-fail-soft px-3 py-2 text-xs text-fail"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{activeError.detail ?? t(`errors.${activeError.error}`)}</span>
          </div>
        )}

        <section className="space-y-2 rounded-lg border border-border bg-sunken p-3.5">
          <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-ink-muted">
            <span>
              {t("deviationCauseLabel")}:{" "}
              <strong className="text-ink">{t(`deviationCauses.${deviation.cause}`)}</strong>
            </span>
            <span>
              {t("deviationColClass")}:{" "}
              <strong className="text-ink">
                {deviation.deviation_class
                  ? t(`deviationClasses.${deviation.deviation_class}`)
                  : t("deviationClassUnset")}
              </strong>
            </span>
          </div>
          <p className="m-0 text-xs font-medium text-ink">{deviation.description}</p>
          <p className="m-0 text-[11px] text-ink-muted tabular-nums">
            {t("deviationOpener", {
              name: deviation.name,
              when: formatWhen(when, deviation.at),
            })}
          </p>
        </section>

        {deviation.status === "closed" && (
          <div className="flex items-start gap-2 rounded-lg border border-pass-edge bg-pass-soft px-3 py-2.5 text-xs text-pass">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{t("deviationClosureNote")}</span>
          </div>
        )}

        <section className="space-y-2">
          <h3 className="m-0 text-xs font-bold text-ink">
            {t("deviationInvestigationsTitle", { count: deviation.investigations.length })}
          </h3>
          {deviation.investigations.length === 0 ? (
            <p className="m-0 text-xs text-ink-muted">{t("deviationInvestigationsEmpty")}</p>
          ) : (
            <ol className="m-0 list-none space-y-2 p-0">
              {deviation.investigations.map((inv) => (
                <li
                  key={inv.id}
                  className="space-y-1.5 rounded-lg border border-border bg-surface p-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-bold text-ink tabular-nums">
                      {t("deviationInvestigationVersion", { version: inv.version })} ·{" "}
                      {t(`deviationClasses.${inv.deviation_class}`)}
                    </span>
                    <span className="text-[11px] text-ink-muted tabular-nums">
                      {t("deviationInvestigationBy", {
                        name: inv.name,
                        when: formatWhen(when, inv.at),
                      })}
                    </span>
                  </div>
                  <p className="m-0 whitespace-pre-wrap text-ink">{inv.investigation}</p>
                  {inv.capa && (
                    <p className="m-0 text-[11px] text-ink-muted">
                      <strong>CAPA:</strong> {inv.capa}
                    </p>
                  )}
                  {inv.reason_for_change && (
                    <p className="m-0 text-[11px] text-ink-muted">
                      <strong>{t("deviationReasonForChange")}:</strong> {inv.reason_for_change}
                    </p>
                  )}
                </li>
              ))}
            </ol>
          )}
        </section>

        {canInvestigate && (
          <section className="space-y-3 rounded-lg border border-border bg-surface p-3.5">
            <form action={invFormAction} className="space-y-3">
              <input type="hidden" name="execution_id" value={executionId} />
              <input type="hidden" name="deviation_id" value={deviation.id} />

              <div className="space-y-1">
                <label
                  htmlFor="dev-inv-text"
                  className="block text-xs font-semibold text-ink"
                >
                  {t("deviationInvestigationLabel")}
                </label>
                <textarea
                  id="dev-inv-text"
                  name="investigation"
                  required
                  rows={3}
                  value={investigationText}
                  onChange={(e) => setInvestigationText(e.target.value)}
                  className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-ink"
                />
              </div>

              <div className="space-y-1">
                <label
                  htmlFor="dev-inv-class"
                  className="block text-xs font-semibold text-ink"
                >
                  {t("deviationClassLabel")}
                </label>
                <select
                  id="dev-inv-class"
                  name="deviation_class"
                  value={deviationClass}
                  onChange={(e) =>
                    setDeviationClass(e.target.value as "minor" | "major" | "critical")
                  }
                  className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-ink"
                >
                  {CLASSES.map((c) => (
                    <option key={c} value={c}>
                      {t(`deviationClasses.${c}`)}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1">
                <label
                  htmlFor="dev-inv-capa"
                  className="block text-xs font-semibold text-ink"
                >
                  {t("deviationCapaLabel")}
                </label>
                <textarea
                  id="dev-inv-capa"
                  name="capa"
                  rows={2}
                  value={capa}
                  onChange={(e) => setCapa(e.target.value)}
                  className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-ink"
                />
              </div>

              {deviation.investigations.length >= 1 && (
                <div className="space-y-1">
                  <label
                    htmlFor="dev-inv-rfc"
                    className="block text-xs font-semibold text-ink"
                  >
                    {t("deviationReasonForChange")}
                  </label>
                  <input
                    id="dev-inv-rfc"
                    name="reason_for_change"
                    type="text"
                    required
                    value={reasonForChange}
                    onChange={(e) => setReasonForChange(e.target.value)}
                    className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-ink"
                  />
                </div>
              )}

              <div className="flex flex-wrap items-center justify-end gap-2">
                <SubmitButton variant="soft">{t("deviationSaveInvestigation")}</SubmitButton>
              </div>
            </form>

            {canSubmit && (
              <form action={subFormAction} className="border-t border-border pt-3">
                <input type="hidden" name="execution_id" value={executionId} />
                <input type="hidden" name="deviation_id" value={deviation.id} />
                <SubmitButton variant="primary">
                  <Send className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{t("deviationSubmitForReview")}</span>
                </SubmitButton>
              </form>
            )}
          </section>
        )}

        {canApprove && (closeAction !== null || returnAction !== null) && (
          <section className="space-y-3 rounded-lg border border-border bg-surface p-3.5">
            <div className="flex items-start gap-2 rounded-md border border-info-edge bg-info-soft px-3 py-2 text-[11px] text-info">
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span>{t("deviationClosureNote")}</span>
            </div>

            {closeAction !== null && (
              <form action={closeFormAction}>
                <input type="hidden" name="execution_id" value={executionId} />
                <input type="hidden" name="deviation_id" value={deviation.id} />
                <SubmitButton variant="primary">
                  <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{t("deviationCloseButton")}</span>
                </SubmitButton>
              </form>
            )}

            {returnAction !== null && (
              <form action={retFormAction} className="space-y-2 border-t border-border pt-3">
                <input type="hidden" name="execution_id" value={executionId} />
                <input type="hidden" name="deviation_id" value={deviation.id} />
                <label
                  htmlFor="dev-return-reason"
                  className="block text-xs font-semibold text-ink"
                >
                  {t("deviationReturnReason")}
                </label>
                <input
                  id="dev-return-reason"
                  name="reason"
                  type="text"
                  required
                  value={returnReason}
                  onChange={(e) => setReturnReason(e.target.value)}
                  placeholder={t("deviationReturnReasonPlaceholder")}
                  className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-ink"
                />
                <SubmitButton variant="soft">
                  <Undo2 className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{t("deviationReturnButton")}</span>
                </SubmitButton>
              </form>
            )}
          </section>
        )}

        <section className="space-y-2">
          <h3 className="m-0 text-xs font-bold text-ink">{t("deviationStatusHistoryTitle")}</h3>
          <ol className="m-0 list-decimal space-y-1 pl-5 text-xs text-ink tabular-nums">
            {deviation.events.map((e) => (
              <li key={e.id}>
                <span>{t(`deviationEvents.${e.event}`, { name: e.name, when: formatWhen(when, e.at) })}</span>
                {e.reason && <span className="text-ink-muted"> — {e.reason}</span>}
              </li>
            ))}
          </ol>
        </section>
      </div>
    </Drawer>
  );
}
