import { useTranslations } from "next-intl";

import type { ProtocolEvent, ProtocolRowView, ProtocolView, RowDraft } from "@/api/client";
import { CiteLink } from "./CiteLink";
import { DecisionCell, DecisionNotice } from "./Decisions";
import type { DecisionAccess, DecisionView } from "./Decisions";
import { formatWhen } from "./formatWhen";
import { formatValue } from "./MatrixTable";
import { MissedNumbers } from "./MissedNumbers";
import { EditDraftForm, Versions, WriteForm } from "./TestStepForms";
import { Button, cell, CoveragePill, DataTable, EmptyState, SectionHeading } from "./ui/ui";

import s from "./AssembledProtocolView.module.css";

/** Why the API refused a start or a withdrawal, as the page reports it. */
export type ProtocolError = "conflict" | "refused" | "invalid" | "forbidden" | "unauthorized" | "failed";

type Action = (formData: FormData) => void | Promise<void>;

/** The forms' server actions (start, withdraw, write or remove a written Test Step, edit a
 * drafted one, answer a missed requirement number), for a viewer with the deciding role;
 * `null` for any other viewer, who sees no controls. */
export type ProtocolControls = {
  start: Action;
  withdraw: Action;
  write: Action;
  remove: Action;
  edit: Action;
  answer: Action;
} | null;

type T = ReturnType<typeof useTranslations<"protocol">>;
type MatrixT = ReturnType<typeof useTranslations<"matrix">>;

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

function StartForm({ t, runId, action, again }: { t: T; runId: string; action: ProtocolControls; again: boolean }) {
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

function Status({
  t,
  protocol,
  runId,
  controls,
}: {
  t: T;
  protocol: ProtocolView;
  runId: string;
  controls: ProtocolControls;
}) {
  return (
    <section className={s.status} aria-labelledby="protocol-status">
      <div className={s.statusRow}>
        <h2 id="protocol-status" className={s.statusTitle}>
          {t("status", { id: protocol.id })}
        </h2>
        <strong className={`${s.badge} ${s[`status_${protocol.status}`]}`}>{t(`statuses.${protocol.status}`)}</strong>
      </div>
      <p className={s.muted}>{t("startedFrom", { run: protocol.run_id })}</p>
      <History t={t} events={protocol.events} />
      {protocol.status === "draft" && controls !== null && (
        <form action={controls.withdraw} className={s.form}>
          <input type="hidden" name="run_id" value={runId} />
          <input type="hidden" name="protocol_id" value={protocol.id} />
          <textarea name="reason" required aria-label={t("withdrawReason")} placeholder={t("withdrawReason")} />
          <button type="submit">{t("withdraw")}</button>
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

function Coverage({ t, m, row, runId }: { t: T; m: MatrixT; row: ProtocolRowView; runId: string }) {
  if (row.decided_class) {
    return <CoveragePill cls={row.decided_class} label={m(`classes.${row.decided_class}`)} />;
  }
  const changed = row.coverage.state === "changed";
  return (
    <div>
      <strong className={s.blocking}>{t(changed ? "coverageChanged" : "coverageUndecided")}</strong>
      <div>
        <a href={`/runs/${encodeURIComponent(runId)}#${encodeURIComponent(row.requirement)}`}>{t("toMatrix")}</a>
      </div>
    </div>
  );
}

function Content({
  t,
  m,
  row,
  runId,
  protocolId,
  controls,
}: {
  t: T;
  m: MatrixT;
  row: ProtocolRowView;
  runId: string;
  protocolId: number;
  controls: ProtocolControls;
}) {
  const step = row.test_step;
  return (
    <div>
      <strong className={s.kind}>{t(`kinds.${row.kind}`)}</strong>
      {row.kind === "vendor_reference" && (
        <>
          <div>{t("vendorEvidence")}</div>
          <ul className={s.list}>
            {row.evidence.map((e) => (
              <li key={`${e.doc}/${e.rev}/${e.step}`}>{t("evidenceStep", { doc: e.doc, rev: e.rev, step: e.step })}</li>
            ))}
          </ul>
        </>
      )}
      {step && (
        <dl className={s.step}>
          <dt className={s.stepOrigin}>
            {step.origin === "written"
              ? t(step.proposal_id === null ? "writtenStep" : "editedStep", { version: step.version ?? 1 })
              : t("fromDraft")}
          </dt>
          <dt>{t("description")}</dt>
          <dd>{step.description}</dd>
          <dt>{t("method")}</dt>
          <dd>{step.method}</dd>
          <dt>{t("instrument")}</dt>
          <dd>{step.instrument ?? t("noInstrument")}</dd>
          <dt>{t("ac")}</dt>
          <dd>
            {step.acceptance ? formatValue(m, step.acceptance) : t("acToSet", { flag: step.acceptance_flag ?? "" })}
          </dd>
        </dl>
      )}
      {row.blockers.map((b) => (
        <div key={b} className={s.blocking}>
          {t(`blockers.${b}`)}
        </div>
      ))}
      {controls !== null && row.kind !== "undecided" && (
        <WriteForm
          t={t}
          row={row}
          runId={runId}
          protocolId={protocolId}
          write={controls.write}
          remove={controls.remove}
        />
      )}
      <Versions t={t} m={m} versions={row.written} />
    </div>
  );
}

function Draft({
  t,
  m,
  d,
  runId,
  access,
  vendor,
  edit,
}: {
  t: T;
  m: MatrixT;
  d: RowDraft;
  runId: string;
  access: DecisionAccess;
  vendor: boolean;
  /** The edit form, when the viewer may edit this draft now. */
  edit: { protocolId: number; action: Action } | null;
}) {
  const x = d.draft;
  return (
    <div className={s.draft}>
      <div>{x.description}</div>
      <div className={s.muted}>
        {t("method")}: {x.method}
      </div>
      <div className={s.muted}>
        {t("instrument")}: {x.instrument ?? t("noInstrument")}
      </div>
      <div>
        {t("ac")}:{" "}
        {x.acceptance ? formatValue(m, x.acceptance) : t("acToSet", { flag: x.acceptance_flag ?? "" })}{" "}
        {x.acceptance_citation && <CiteLink runId={runId} cite={x.acceptance_citation} />}
      </div>
      {vendor && <div className={s.muted}>{t("vendorDraftNote")}</div>}
      <DecisionCell proposal={d.proposal} runId={runId} screen="protocol" access={access} />
      {edit && <EditDraftForm t={t} d={d} runId={runId} protocolId={edit.protocolId} edit={edit.action} />}
    </div>
  );
}

function Rows({
  t,
  rows,
  runId,
  access,
  protocolId,
  controls,
}: {
  t: T;
  rows: readonly ProtocolRowView[];
  runId: string;
  access: DecisionAccess;
  protocolId: number;
  controls: ProtocolControls;
}) {
  const m = useTranslations("matrix");
  return (
    <DataTable>
      <thead>
        <tr>
          <th>{t("requirement")}</th>
          <th>{t("coverage")}</th>
          <th>{t("content")}</th>
          <th>{t("drafts")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.requirement} data-testid={r.requirement} className={r.blockers.length > 0 ? s.blockingRow : undefined}>
            <th scope="row">
              <div className={cell.id}>{r.requirement}</div>
              <div className={s.text}>{r.text}</div>
              <CiteLink runId={runId} cite={r.source} />
            </th>
            <td>
              <Coverage t={t} m={m} row={r} runId={runId} />
            </td>
            <td>
              <Content t={t} m={m} row={r} runId={runId} protocolId={protocolId} controls={controls} />
            </td>
            <td className={s.drafts}>
              {r.drafts.length === 0 ? (
                <span className={s.muted}>{t("noDrafts")}</span>
              ) : (
                r.drafts.map((d) => (
                  <Draft
                    key={d.proposal.id}
                    t={t}
                    m={m}
                    d={d}
                    runId={runId}
                    access={access}
                    vendor={r.kind === "vendor_reference"}
                    edit={
                      controls !== null && r.test_step?.origin !== "written"
                        ? { protocolId, action: controls.edit }
                        : null
                    }
                  />
                ))
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}

/** The Protocol assembled in TraceQ from a run (spec #247, ADR 0012): its status and every
 * status change, and while in Draft status one row per requirement computed from the current
 * decisions (Coverage decided by a human, the kind of row, the Vendor Reference's Evidence or
 * its Test Step, accepted or written, and what blocks), each drafted Test Step with the
 * decision controls of slice 1 and its edit form, each row's write form with the four
 * Acceptance Criterion shapes and every version of its written Test Step, then the printed
 * requirement numbers the run missed with their answer forms and the unquoted URS text.
 * Without a Protocol, the start control; the known limits always. A
 * viewer without the deciding role sees no controls. Never the site's Protocol Draft. */
export function AssembledProtocolView({
  protocol,
  runId,
  decisions,
  controls,
  error,
}: {
  protocol: ProtocolView | null;
  runId: string;
  decisions: DecisionView;
  controls: ProtocolControls;
  error?: ProtocolError;
}) {
  const t = useTranslations("protocol");
  const rows = protocol?.rows ?? null;
  const blocking = rows?.filter((r) => r.blockers.length > 0).length ?? 0;
  return (
    <>
      {error && (
        <p role="alert" className={s.failure}>
          {t(`errors.${error}`)}
        </p>
      )}
      <DecisionNotice view={decisions} />
      {protocol === null ? (
        <EmptyState title={t("none")}>
          <p>{t("noneBody")}</p>
          <StartForm t={t} runId={runId} action={controls} again={false} />
        </EmptyState>
      ) : (
        <Status t={t} protocol={protocol} runId={runId} controls={controls} />
      )}
      {rows !== null && (
        <>
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
            <Rows
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
        </>
      )}
      {protocol !== null && rows === null && protocol.status !== "withdrawn" && <p className={s.muted}>{t("notDraftRows")}</p>}
      <Limits t={t} />
    </>
  );
}
