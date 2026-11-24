import { useTranslations } from "next-intl";

import type { ProtocolEvent, ProtocolView } from "@/api/client";
import type { ApprovalControls, ProtocolControls } from "./AssembledProtocolView";
import { formatWhen } from "./formatWhen";
import { Button, StatusBadge, type SemanticTone } from "./ui/ui";

import s from "./AssembledProtocolView.module.css";

type T = ReturnType<typeof useTranslations<"protocol">>;

const STATUS_TONE: Record<ProtocolView["status"], SemanticTone> = {
  draft: "warn",
  submitted: "info",
  approved: "pass",
  withdrawn: "neutral",
};

export function StartForm({
  t,
  runId,
  action,
  again,
}: {
  t: T;
  runId: string;
  action: ProtocolControls;
  again: boolean;
}) {
  if (action === null) return null;
  return (
    <form action={action.start} className={s.form}>
      <input type="hidden" name="run_id" value={runId} />
      <Button type="submit" variant="primary">
        {t(again ? "startAgain" : "start")}
      </Button>
    </form>
  );
}

function History({ t, events }: { t: T; events: readonly ProtocolEvent[] }) {
  const when = useTranslations("decisions");
  return (
    <section aria-labelledby="protocol-history" className={s.history}>
      <h3 id="protocol-history" className={s.historyTitle}>
        {t("history")}
      </h3>
      <ol>
        {events.map((e) => (
          <li key={e.id}>
            {t(`events.${e.event}`, { name: e.name, when: formatWhen(when, e.at) })}
            {e.reason && <div className={s.reason}>{e.reason}</div>}
          </li>
        ))}
      </ol>
    </section>
  );
}

/** Approve (bound to the submission shown: its event id and hash) and return with a reason,
 * for the approving role while Submitted. */
function ApprovalForms({
  t,
  protocol,
  runId,
  approval,
}: {
  t: T;
  protocol: ProtocolView;
  runId: string;
  approval: ApprovalControls;
}) {
  const shown = protocol.submission;
  if (protocol.status !== "submitted" || approval === null || shown === null) return null;
  return (
    <div className={s.approvalForms}>
      <p>{t("approval.note")}</p>
      <div className={s.formRow}>
        <form action={approval.approve} className={s.form}>
          <input type="hidden" name="run_id" value={runId} />
          <input type="hidden" name="protocol_id" value={protocol.id} />
          <input type="hidden" name="submission_event_id" value={shown.event_id} />
          <input type="hidden" name="hash" value={shown.hash} />
          <Button type="submit" variant="primary">
            {t("approval.approve")}
          </Button>
        </form>
        <form action={approval.return} className={s.form}>
          <input type="hidden" name="run_id" value={runId} />
          <input type="hidden" name="protocol_id" value={protocol.id} />
          <textarea
            name="reason"
            required
            aria-label={t("approval.returnReason")}
            placeholder={t("approval.returnReason")}
          />
          <Button type="submit" variant="danger">
            {t("approval.return")}
          </Button>
        </form>
      </div>
    </div>
  );
}

/** Protocol status card: current status badge, event history, and lifecycle actions
 * (withdraw, approve/return, or restart after withdrawal). */
export function ProtocolStatusPanel({
  t,
  protocol,
  runId,
  controls,
  approval,
}: {
  t: T;
  protocol: ProtocolView;
  runId: string;
  controls: ProtocolControls;
  approval: ApprovalControls;
}) {
  return (
    <section className={s.status} aria-labelledby="protocol-status">
      <div className={s.statusRow}>
        <h2 id="protocol-status" className={s.statusTitle}>
          {t("status", { id: protocol.id })}
        </h2>
        <StatusBadge tone={STATUS_TONE[protocol.status] ?? "neutral"}>{t(`statuses.${protocol.status}`)}</StatusBadge>
      </div>
      <p className={s.muted}>{t("startedFrom", { run: protocol.run_id })}</p>
      <History t={t} events={protocol.events} />
      {protocol.status === "approved" && <p className={s.approvedNote}>{t("approval.approvedNote")}</p>}
      <ApprovalForms t={t} protocol={protocol} runId={runId} approval={approval} />
      {protocol.status === "draft" && controls !== null && (
        <form action={controls.withdraw} className={s.form}>
          <input type="hidden" name="run_id" value={runId} />
          <input type="hidden" name="protocol_id" value={protocol.id} />
          <textarea name="reason" required aria-label={t("withdrawReason")} placeholder={t("withdrawReason")} />
          <Button type="submit" variant="danger">
            {t("withdraw")}
          </Button>
        </form>
      )}
      {protocol.status === "withdrawn" && (
        <>
          <p>{t("withdrawnNote")}</p>
          <StartForm t={t} runId={runId} action={controls} again />
        </>
      )}
    </section>
  );
}
