import { useTranslations } from "next-intl";

import type { ProtocolView } from "@/api/client";
import { DecisionNotice } from "./Decisions";
import type { DecisionView } from "./Decisions";
import { EarlierCopies, FrozenCopy } from "./FrozenCopy";
import { MissedNumbers } from "./MissedNumbers";
import { ProtocolChecklistPanel } from "./ProtocolChecklistPanel";
import { ProtocolRowsTable } from "./ProtocolRowsTable";
import { ProtocolStatusPanel, StartForm } from "./ProtocolStatusPanel";
import { Alert, EmptyState, SectionHeading } from "./ui/ui";

import s from "./AssembledProtocolView.module.css";

/** Why the API refused a start or a withdrawal, as the page reports it. */
export type ProtocolError = "conflict" | "refused" | "invalid" | "forbidden" | "unauthorized" | "failed";

type Action = (formData: FormData) => void | Promise<void>;

/** The forms' server actions (start, withdraw, write or remove a written Test Step, edit a
 * drafted one, answer a missed requirement number, submit), for a viewer with the deciding role;
 * `null` for any other viewer, who sees no controls. */
export type ProtocolControls = {
  start: Action;
  withdraw: Action;
  write: Action;
  remove: Action;
  edit: Action;
  answer: Action;
  submit: Action;
} | null;

/** The approve and return actions, for a viewer with the approving role; `null` otherwise. */
export type ApprovalControls = { approve: Action; return: Action } | null;

type T = ReturnType<typeof useTranslations<"protocol">>;

const LIMITS = ["oneStep", "combined", "noPrint", "notSignature", "noNewVersion"] as const;

/** The known limits of the Protocol assembled in TraceQ (ADR 0012), always shown. */
function Limits({ t }: { t: T }) {
  return (
    <aside className={s.limits} aria-labelledby="protocol-limits">
      <h2 id="protocol-limits" className={s.limitsTitle}>
        {t("limitsTitle")}
      </h2>
      <ul>
        {LIMITS.map((k) => (
          <li key={k}>{t(`limits.${k}`)}</li>
        ))}
      </ul>
    </aside>
  );
}

/** The Protocol assembled in TraceQ from a run (spec #247, ADR 0012): its status and every
 * status change, and while in Draft status one row per requirement computed from the current
 * decisions (Coverage decided by a human, the kind of row, the Vendor Reference's Evidence or
 * its Test Step, accepted or written, and what blocks), each drafted Test Step with the
 * decision controls of slice 1 and its edit form, each row's write form with the four
 * Acceptance Criterion shapes and every version of its written Test Step, then the printed
 * requirement numbers the run missed with their answer forms and the unquoted URS text; the
 * checklist of what blocks submission and the submit control. A Submitted or Approved
 * Protocol shows its frozen copy and hash instead of live rows; while Submitted the approving
 * role approves it (a recorded status, not an Electronic Signature) or returns it with a
 * reason, and a returned Protocol lists its earlier copies with the reasons.
 * Without a Protocol, the start control; the known limits always. A
 * viewer without the deciding role sees no controls. Never the site's Protocol Draft. */
export function AssembledProtocolView({
  protocol,
  runId,
  decisions,
  controls,
  approval = null,
  error,
}: {
  protocol: ProtocolView | null;
  runId: string;
  decisions: DecisionView;
  controls: ProtocolControls;
  approval?: ApprovalControls;
  error?: ProtocolError;
}) {
  const t = useTranslations("protocol");
  const rows = protocol?.rows ?? null;
  const blocking = rows?.filter((r) => r.blockers.length > 0).length ?? 0;
  return (
    <>
      {error && (
        <Alert tone="fail" role="alert" className={s.errorBanner}>
          {t(`errors.${error}`)}
        </Alert>
      )}
      <DecisionNotice view={decisions} approver={approval !== null} />
      {protocol === null ? (
        <EmptyState title={t("none")}>
          <p>{t("noneBody")}</p>
          <StartForm t={t} runId={runId} action={controls} again={false} />
        </EmptyState>
      ) : (
        <ProtocolStatusPanel t={t} protocol={protocol} runId={runId} controls={controls} approval={approval} />
      )}
      {rows !== null && (
        <>
          {protocol?.checklist && (
            <ProtocolChecklistPanel
              t={t}
              items={protocol.checklist}
              runId={runId}
              protocolId={protocol.id}
              controls={controls}
            />
          )}
          <p className={s.summary}>
            {t("summary", {
              rows: rows.length,
              blocking,
              vendor: rows.filter((r) => r.kind === "vendor_reference").length,
              testStep: rows.filter((r) => r.kind === "test_step").length,
            })}
          </p>
          <section className={s.section} aria-labelledby="protocol-rows">
            <SectionHeading id="protocol-rows" title={t("rows")} count={rows.length} note={t("rowsNote")} />
            <ProtocolRowsTable
              t={t}
              rows={rows}
              runId={runId}
              access={decisions.access}
              protocolId={protocol?.id ?? 0}
              controls={controls}
            />
          </section>
          <MissedNumbers
            t={t}
            urs={protocol?.urs ?? null}
            runId={runId}
            protocolId={protocol?.id ?? 0}
            answer={controls?.answer ?? null}
          />
          {protocol && protocol.submissions.length > 0 && <EarlierCopies t={t} earlier={protocol.submissions} />}
        </>
      )}
      {protocol?.submission && (
        <FrozenCopy
          t={t}
          submission={protocol.submission}
          earlier={protocol.submissions.filter((x) => x.event_id !== protocol.submission?.event_id)}
          runId={runId}
        />
      )}
      {protocol !== null && rows === null && protocol.status !== "withdrawn" && (
        <p className={s.muted}>{t("notDraftRows")}</p>
      )}
      <Limits t={t} />
    </>
  );
}
