import { useTranslations } from "next-intl";

import type { Cite, DraftFindingView, DraftTestStep, PrintedRead, ProtocolDraftView as Draft } from "@/api/client";
import { CiteLink } from "./CiteLink";
import { DecisionCell, DecisionNotice, DecisionTally } from "./Decisions";
import type { DecisionView } from "./Decisions";
import { cell, DataTable, EmptyState, SectionHeading, SummaryLinks } from "./ui/ui";

import s from "./ProtocolDraftView.module.css";

type T = ReturnType<typeof useTranslations<"draft">>;

const number = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 3 });

/** A value as code read it from the print, in a few characters. */
export function formatPrinted(t: T, v: PrintedRead): string {
  switch (v.type) {
    case "range": {
      if (v.min != null && v.max != null) return `${number.format(v.min)}–${number.format(v.max)} ${v.unit}`;
      if (v.min != null) {
        return t(v.min_exclusive ? "values.above" : "values.atLeast", { min: number.format(v.min), unit: v.unit });
      }
      return t(v.max_exclusive ? "values.below" : "values.atMost", { max: number.format(v.max ?? 0), unit: v.unit });
    }
    case "number":
      return `${number.format(v.value)} ${v.unit}`;
    case "tolerance":
      return t("values.tolerance", {
        nominal: number.format(v.nominal),
        unit: v.unit,
        tolerance: number.format(v.tolerance),
        toleranceUnit: v.tolerance_unit,
      });
    case "text":
      return v.value;
    case "ambiguous":
      return t("values.ambiguous", { readings: v.readings.map((r) => number.format(r)).join(" / ") });
  }
}

/** A citation into the draft. The draft is not a corpus document the API serves, so it names
 * the page, with the verbatim quote on hover, and links nowhere. */
function DraftCite({ cite }: { cite: Cite }) {
  const c = useTranslations("common");
  return (
    <span className={s.draftCite} title={cite.quote}>
      {c("cite", { doc: cite.doc, rev: cite.rev, page: cite.page })}
    </span>
  );
}

/** A citation: into the draft (no link) or into a document the run read (a link). */
function AnyCite({ cite, runId, draftDoc }: { cite: Cite; runId: string; draftDoc: string }) {
  return cite.doc === draftDoc ? <DraftCite cite={cite} /> : <CiteLink runId={runId} cite={cite} />;
}

function Finding({
  t,
  view,
  runId,
  draftDoc,
  decisions,
}: {
  t: T;
  view: DraftFindingView;
  runId: string;
  draftDoc: string;
  decisions: DecisionView;
}) {
  const f = view.finding;
  return (
    <div className={s.finding}>
      <strong className={s.findingType}>{t(`types.${f.type}`)}</strong>
      <div>{f.detail}</div>
      <ul className={s.citations}>
        {f.citations.map((c) => (
          <li key={`${c.doc}/${c.rev}/${c.page}/${c.quote}`}>
            <AnyCite cite={c} runId={runId} draftDoc={draftDoc} />
          </li>
        ))}
      </ul>
      {view.proposal && (
        <DecisionCell proposal={view.proposal} runId={runId} screen="draft" access={decisions.access} />
      )}
    </div>
  );
}

function StepRow({
  t,
  step,
  findings,
  runId,
  draftDoc,
  decisions,
  anchor,
}: {
  t: T;
  step: DraftTestStep;
  findings: readonly DraftFindingView[];
  runId: string;
  draftDoc: string;
  decisions: DecisionView;
  anchor?: string;
}) {
  const ac = step.acceptance;
  return (
    <tr id={anchor}>
      <th scope="row" className={cell.id}>
        {step.id}
      </th>
      <td>
        <div className={s.printed}>{ac.printed}</div>
        {ac.value === null && <div className={s.muted}>{t("notParsed")}</div>}
        <DraftCite cite={ac.citation} />
      </td>
      <td>
        <ul className={s.traced}>
          {step.traced.map((tr) => (
            <li key={tr.requirement}>
              <span className={cell.id}>{tr.requirement}</span>
              {tr.urs_limit && <div className={s.printed}>{formatPrinted(t, tr.urs_limit)}</div>}
              {tr.not_parsed && <div className={s.muted}>{t("ursNotRead", { reason: tr.not_parsed })}</div>}
              {tr.citation && (
                <div>
                  <CiteLink runId={runId} cite={tr.citation} />
                </div>
              )}
              {tr.compared ? (
                <div className={tr.deviates ? s.deviates : s.within}>{t(tr.deviates ? "deviates" : "within")}</div>
              ) : (
                tr.not_compared && <div className={s.notCompared}>{t("notComparedBecause", { reason: tr.not_compared })}</div>
              )}
            </li>
          ))}
        </ul>
        {step.traced.length === 0 && step.not_compared && (
          <div className={s.notCompared}>{t("notComparedBecause", { reason: step.not_compared })}</div>
        )}
      </td>
      <td>
        {step.traced.every((tr) => tr.comparators.length === 0) ? (
          <span className={s.muted}>{t("noComparators")}</span>
        ) : (
          <ul className={s.comparators}>
            {step.traced.flatMap((tr) =>
              tr.comparators.flatMap((c) =>
                c.facts.map((f) => (
                  <li key={`${tr.requirement}/${c.doc}/${f.name}/${f.citation.quote}`}>
                    <span>
                      {t(`comparatorKinds.${c.kind}`)} {f.name}: {f.printed}
                    </span>{" "}
                    <CiteLink runId={runId} cite={f.citation} />
                  </li>
                )),
              ),
            )}
          </ul>
        )}
      </td>
      <td className={s.findings}>
        {findings.length === 0 ? (
          <span className={s.muted}>{t("noFinding")}</span>
        ) : (
          findings.map((f, i) => (
            <Finding key={`${f.finding.requirement}/${i}`} t={t} view={f} runId={runId} draftDoc={draftDoc} decisions={decisions} />
          ))
        )}
      </td>
    </tr>
  );
}

/** The Protocol Draft of a Review Package run: every Test Step in draft order with its AC as
 * read, the URS value it was compared with, the comparators available and its findings (or
 * "not compared" with the reason); then the findings about the whole document. Each finding
 * carries its decision state and, for the deciding role, the decision forms of slice 1.
 * TraceQ's own drafted OQ Test Steps are not shown here. */
export function ProtocolDraftView({
  draft,
  runId,
  decisions,
}: {
  draft: Draft;
  runId: string;
  decisions: DecisionView;
}) {
  const t = useTranslations("draft");
  const draftDoc = draft.document.doc_id;
  const stepIds = new Set(draft.test_steps.map((st) => st.id));
  const onStep = (id: string) => draft.findings.filter((f) => f.finding.test_step === id);
  const whole = draft.findings.filter((f) => f.finding.test_step == null || !stepIds.has(f.finding.test_step));
  const notCompared = draft.test_steps.filter((st) => !st.compared);
  const firstNotCompared = notCompared[0]?.id;
  return (
    <>
      <p className={s.document}>
        {t("document", { doc: draft.document.doc_id, rev: draft.document.rev, package: draft.package })}
      </p>
      <p className={s.note}>{t("ownSteps")}</p>
      <DecisionNotice view={decisions} />
      <div className={s.overview}>
        <SummaryLinks
          title={t("summaryTitle")}
          items={[
            { n: draft.test_steps.length, label: t("steps"), href: "#draft-steps" },
            { n: notCompared.length, label: t("notComparedSteps"), href: "#draft-not-compared" },
            { n: whole.length, label: t("documentFindings"), href: "#draft-document" },
          ]}
        />
        <DecisionTally counts={decisions.counts} kinds={["draft"]} />
      </div>
      <section className={s.section} aria-labelledby="draft-steps">
        <SectionHeading id="draft-steps" title={t("steps")} count={draft.test_steps.length} note={t("stepsNote")} />
        {draft.test_steps.length === 0 ? (
          <EmptyState title={t("noSteps")} />
        ) : (
          <DataTable>
            <thead>
              <tr>
                <th>{t("step")}</th>
                <th>{t("ac")}</th>
                <th>{t("urs")}</th>
                <th>{t("comparators")}</th>
                <th>{t("findings")}</th>
              </tr>
            </thead>
            <tbody>
              {draft.test_steps.map((st) => (
                <StepRow
                  key={st.id}
                  t={t}
                  step={st}
                  findings={onStep(st.id)}
                  runId={runId}
                  draftDoc={draftDoc}
                  decisions={decisions}
                  anchor={st.id === firstNotCompared ? "draft-not-compared" : undefined}
                />
              ))}
            </tbody>
          </DataTable>
        )}
      </section>
      <section className={s.section} aria-labelledby="draft-document">
        <SectionHeading
          id="draft-document"
          title={t("documentFindings")}
          count={whole.length}
          note={t("documentFindingsNote")}
        />
        {whole.length === 0 ? (
          <EmptyState title={t("noDocumentFinding")} />
        ) : (
          <DataTable>
            <thead>
              <tr>
                <th>{t("requirement")}</th>
                <th>{t("findings")}</th>
              </tr>
            </thead>
            <tbody>
              {whole.map((f, i) => (
                <tr key={`${f.finding.requirement}/${i}`}>
                  <th scope="row" className={cell.id}>
                    {f.finding.row ?? f.finding.requirement}
                  </th>
                  <td className={s.findings}>
                    <Finding t={t} view={f} runId={runId} draftDoc={draftDoc} decisions={decisions} />
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        )}
      </section>
    </>
  );
}
