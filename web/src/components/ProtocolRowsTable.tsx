import { useTranslations } from "next-intl";

import type { ProtocolRowView, RowDraft } from "@/api/client";
import type { ProtocolControls } from "./AssembledProtocolView";
import { CiteLink } from "./CiteLink";
import { DecisionCell } from "./Decisions";
import type { DecisionAccess } from "./Decisions";
import { formatValue } from "./MatrixTable";
import { EditDraftForm, Versions, WriteForm } from "./TestStepForms";
import { cell, CoveragePill, DataTable } from "./ui/ui";

import s from "./AssembledProtocolView.module.css";

type T = ReturnType<typeof useTranslations<"protocol">>;
type MatrixT = ReturnType<typeof useTranslations<"matrix">>;
type Action = (formData: FormData) => void | Promise<void>;

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
  anchor,
  edit,
}: {
  t: T;
  m: MatrixT;
  d: RowDraft;
  runId: string;
  access: DecisionAccess;
  vendor: boolean;
  anchor: string;
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
      <DecisionCell proposal={d.proposal} runId={runId} screen="protocol" access={access} anchor={anchor} />
      {edit && <EditDraftForm t={t} d={d} runId={runId} protocolId={edit.protocolId} edit={edit.action} />}
    </div>
  );
}

/** One row per requirement computed from the current decisions while the Protocol is in Draft status. */
export function ProtocolRowsTable({
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
          <tr
            key={r.requirement}
            id={`row-${r.requirement}`}
            data-testid={r.requirement}
            className={r.blockers.length > 0 ? s.blockingRow : undefined}
          >
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
                    anchor={`row-${r.requirement}`}
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
