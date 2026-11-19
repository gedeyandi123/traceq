import { useTranslations } from "next-intl";

import type { FrozenDecision, FrozenRow, SubmissionView } from "@/api/client";
import { CiteLink } from "./CiteLink";
import { formatWhen } from "./formatWhen";
import { formatValue } from "./MatrixTable";
import { cell, CoveragePill, DataTable, SectionHeading } from "./ui/ui";

import s from "./AssembledProtocolView.module.css";

type T = ReturnType<typeof useTranslations<"protocol">>;
type MatrixT = ReturnType<typeof useTranslations<"matrix">>;
type WhenT = ReturnType<typeof useTranslations<"decisions">>;

function By({ t, when, d }: { t: T; when: WhenT; d: FrozenDecision }) {
  return (
    <div className={s.muted}>
      {t(`copy.decisions.${d.decision}`, { name: d.author.name, when: formatWhen(when, d.at) })}
      {d.reason && <div className={s.reason}>{d.reason}</div>}
    </div>
  );
}

function Row({ t, m, when, row, runId }: { t: T; m: MatrixT; when: WhenT; row: FrozenRow; runId: string }) {
  const step = row.test_step;
  return (
    <tr data-testid={`copy-${row.requirement}`}>
      <th scope="row">
        <div className={cell.id}>{row.requirement}</div>
        <div className={s.text}>{row.text}</div>
        <CiteLink runId={runId} cite={row.source} />
      </th>
      <td>
        <CoveragePill cls={row.coverage.coverage_class} label={m(`classes.${row.coverage.coverage_class}`)} />
        <By t={t} when={when} d={row.coverage.decision} />
      </td>
      <td>
        <strong className={s.kind}>{t(`kinds.${row.kind}`)}</strong>
        {row.kind === "vendor_reference" && (
          <ul className={s.list}>
            {row.evidence.map((e) => (
              <li key={`${e.doc}/${e.rev}/${e.step}`}>{t("evidenceStep", { doc: e.doc, rev: e.rev, step: e.step })}</li>
            ))}
          </ul>
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
            <dd>{formatValue(m, step.acceptance)}</dd>
          </dl>
        )}
        {row.written.length > 0 && (
          <ul className={s.list} aria-label={t("versions.title", { count: row.written.length })}>
            {row.written.map((v) => (
              <li key={v.version}>
                {t(v.removed ? "versions.removed" : "versions.written", {
                  version: v.version,
                  name: v.author.name,
                  when: formatWhen(when, v.at),
                })}
              </li>
            ))}
          </ul>
        )}
      </td>
      <td>
        {row.drafts.length === 0 ? (
          <span className={s.muted}>{t("noDrafts")}</span>
        ) : (
          row.drafts.map((d) => (
            <div key={d.proposal_id} className={s.draft}>
              <div>{d.draft_id}</div>
              {d.decision ? <By t={t} when={when} d={d.decision} /> : <div className={s.muted}>{t("copy.undecidedDraft")}</div>}
            </div>
          ))
        )}
      </td>
    </tr>
  );
}

/** The frozen copy of a submitted Protocol (spec #247, ticket #252): what the Approver reads,
 * shown instead of live rows. Its hash, the Preparer, every row with the decision in force on
 * its Coverage and each drafted Test Step and who made it, its Test Step and every version of
 * its written one, the missed numbers with their dispositions, and the unquoted text. */
export function FrozenCopy({
  t,
  submission,
  earlier,
  runId,
}: {
  t: T;
  submission: SubmissionView;
  earlier: readonly SubmissionView[];
  runId: string;
}) {
  const m = useTranslations("matrix");
  const when = useTranslations("decisions");
  const copy = submission.frozen_copy;
  const missed = (copy.urs ?? []).flatMap((u) => u.missed.map((n) => ({ ...n, doc: u.doc, rev: u.rev })));
  const unquoted = (copy.urs ?? []).flatMap((u) => u.unquoted.map((x) => ({ ...x, doc: u.doc, rev: u.rev })));
  return (
    <section className={s.section} aria-labelledby="protocol-copy">
      <SectionHeading id="protocol-copy" title={t("copy.title")} count={copy.rows.length} note={t("copy.note")} />
      <dl className={s.step}>
        <dt>{t("copy.hash")}</dt>
        <dd>
          <code data-testid="copy-hash">{submission.hash}</code>
        </dd>
        <dt>{t("copy.preparer")}</dt>
        <dd>{t("copy.submittedBy", { name: copy.preparer.name, when: formatWhen(when, submission.at) })}</dd>
      </dl>
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
          {copy.rows.map((r) => (
            <Row key={r.requirement} t={t} m={m} when={when} row={r} runId={runId} />
          ))}
        </tbody>
      </DataTable>
      {missed.length > 0 && (
        <section aria-label={t("missed.title")}>
          <h3>{t("missed.title")}</h3>
          <ul className={s.list}>
            {missed.map((n) => (
              <li key={`${n.doc}/${n.rev}/${n.number}`}>
                {t("copy.missed", {
                  number: n.number,
                  doc: n.doc,
                  rev: n.rev,
                  kind: t(`copy.missedKinds.${n.disposition.kind}`),
                  name: n.disposition.author.name,
                })}
                <div className={s.reason}>{n.disposition.justification}</div>
              </li>
            ))}
          </ul>
        </section>
      )}
      {unquoted.length > 0 && (
        <section aria-label={t("unquoted.title")}>
          <h3>{t("unquoted.title")}</h3>
          <ul className={s.list}>
            {unquoted.map((x, i) => (
              <li key={i} className={s.reason}>
                {x.doc} rev {x.rev}, p. {x.page}: {x.text}
              </li>
            ))}
          </ul>
        </section>
      )}
      {earlier.length > 0 && (
        <section aria-label={t("copy.earlier")}>
          <h3>{t("copy.earlier")}</h3>
          <ul className={s.list}>
            {earlier.map((e) => (
              <li key={e.event_id}>
                {t("copy.earlierItem", { when: formatWhen(when, e.at) })} <code>{e.hash}</code>
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}
