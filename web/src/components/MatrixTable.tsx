import { useTranslations } from "next-intl";

import type { Cite, Matrix, MatrixRow, ObservedValue, Proposal, Value } from "@/api/client";
import { CiteLink } from "./CiteLink";
import { DecisionCell, DecisionNotice, DecisionTally } from "./Decisions";
import type { DecisionView } from "./Decisions";
import { cell, CoveragePill, DataTable, Panel } from "./ui/ui";
import type { CoverageKey } from "./ui/ui";

import s from "./MatrixTable.module.css";

type T = ReturnType<typeof useTranslations<"matrix">>;
type Evidence = MatrixRow["evidence"][number];

const number = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 3 });

/** Riskiest first: the order of the Coverage summary and the legend. */
const RISK: readonly CoverageKey[] = ["conflict", "gap", "partial", "site_only", "covered_by_vendor", "none"];

function formatValue(t: T, v: Value | ObservedValue, observed = false): string {
  switch (v.type) {
    case "range":
      if (v.min != null && v.max != null) {
        return `${number.format(v.min)}–${number.format(v.max)} ${v.unit}`;
      }
      return v.min != null
        ? t("values.atLeast", { min: number.format(v.min), unit: v.unit })
        : t("values.atMost", { max: number.format(v.max ?? 0), unit: v.unit });
    case "number":
      return `${number.format(v.value)} ${v.unit}`;
    case "one_of":
      return v.allowed.join(" / ");
    case "text":
      return v.value;
    case "present":
      if (!observed || v.value == null) return t("values.present");
      return v.value ? t("values.presentObserved") : t("values.absentObserved");
    case "ambiguous":
      return t("ambiguous", { readings: v.readings.map((r) => number.format(r)).join(" / ") });
  }
}

/** An observed value in a few characters, for a chip. A reading that needs confirmation shows
 * its readings and a question mark; the full sentence is in the opened list. */
function shortObserved(t: T, e: Evidence): string {
  const v = e.observed_value;
  if (!v) return e.observed;
  if (v.type === "ambiguous") return `${v.readings.map((r) => number.format(r)).join(" / ")} ?`;
  return formatValue(t, v, true);
}

function sameCite(a: Cite, b: Cite): boolean {
  return a.doc === b.doc && a.rev === b.rev && a.page === b.page && a.quote === b.quote;
}

const MARK = { pass: "✓", fail: "✕", none: "·" } as const;

/** Evidence on one line of chips (each step with its observed value, and the first design
 * value); the full list, its quotes and citations one click away. A chip is not a link, and
 * its text is one node, so it never doubles a value or a citation the row shows elsewhere. */
function EvidenceCell({ row, runId, t }: { row: MatrixRow; runId: string; t: T }) {
  if (row.evidence.length === 0 && row.design.length === 0) {
    return <span className="muted">{t("noEvidence")}</span>;
  }
  const [design] = row.design;
  return (
    <details className={s.evidence}>
      <summary>
        <span className={s.chips}>
          {row.evidence.map((e) => {
            const result = e.result ?? "none";
            return (
              <span
                key={`${e.doc}/${e.step}`}
                className={`${s.chip} ${s[`chip_${result}`]}`}
                title={`${e.stage} ${e.step}: ${t(`results.${result}`)}`}
              >
                <span aria-hidden="true">{MARK[result]}</span>
                <span className={s.chipText}>{`${e.step} · ${shortObserved(t, e)}`}</span>
              </span>
            );
          })}
          {design && (
            <span className={s.chip} title={design.name}>
              <span className={s.chipText}>{`${t("designShort")} · ${design.printed}`}</span>
            </span>
          )}
        </span>
        <span className="visually-hidden">{t("allEvidence")}</span>
      </summary>
      <ul className={s.evidenceList}>
        {row.evidence.map((e) => (
          <li key={`${e.doc}/${e.step}`}>
            <strong>
              {e.stage} {e.step}
            </strong>{" "}
            {e.test}
            <div className={s.observed}>
              {t("observed", {
                observed: e.observed_value ? formatValue(t, e.observed_value, true) : e.observed,
              })}
              {" · "}
              {t("result", { result: t(`results.${e.result ?? "none"}`) })}
            </div>
            {e.failure && <div className={s.failure}>{e.failure}</div>}
            <CiteLink runId={runId} cite={e.citation} />
          </li>
        ))}
        {row.design.map((d) => (
          <li key={`${d.doc}/${d.name}`}>
            <strong>{t("design")}</strong> {d.name}: {t("printed", { printed: d.printed })}
            <div>
              <CiteLink runId={runId} cite={d.citation} />
            </div>
          </li>
        ))}
      </ul>
    </details>
  );
}

/** The proposed class, and after it the class a human changed it to, so the final class does
 * not hide in the decision text. */
function CoverageCell({ row, proposal, t }: { row: MatrixRow; proposal: Proposal | undefined; t: T }) {
  const proposed: CoverageKey = row.coverage ?? "none";
  const current = proposal?.state === "decided" ? proposal.decisions[0] : undefined;
  const decided = current?.decision === "edited" ? current.coverage : null;
  return (
    <span className={s.classes}>
      <CoveragePill cls={proposed} label={t(`classes.${proposed}`)} help={t(`help.${proposed}`)} />
      {decided != null && (
        <>
          <span aria-hidden="true" className={s.arrow}>
            →
          </span>
          <span className="visually-hidden">{t("decidedClass")}</span>
          <CoveragePill cls={decided} label={t(`classes.${decided}`)} help={t(`help.${decided}`)} />
        </>
      )}
    </span>
  );
}

/** How many rows the system put in each class, riskiest first, and the meaning of each class
 * one click away. */
function CoverageSummary({ rows, t }: { rows: readonly MatrixRow[]; t: T }) {
  const counts = new Map<CoverageKey, number>();
  for (const r of rows) {
    const k = r.coverage ?? "none";
    counts.set(k, (counts.get(k) ?? 0) + 1);
  }
  return (
    <Panel title={t("summaryTitle")}>
      <ul className={s.summary} aria-label={t("summaryTitle")}>
        {RISK.map((k) => (
          <li key={k} className={counts.has(k) ? undefined : s.zero}>
            <span className={s.summaryCount}>{counts.get(k) ?? 0}</span>
            <CoveragePill cls={k} label={t(`classes.${k}`)} help={t(`help.${k}`)} />
          </li>
        ))}
      </ul>
      <details className={s.legend}>
        <summary>{t("legendTitle")}</summary>
        <dl>
          {RISK.map((k) => (
            <div key={k}>
              <dt>
                <CoveragePill cls={k} label={t(`classes.${k}`)} />
              </dt>
              <dd>{t(`help.${k}`)}</dd>
            </div>
          ))}
        </dl>
      </details>
    </Panel>
  );
}

/** The traceability matrix: one row per requirement, with its Coverage class and reason,
 * and every piece of Evidence linked to the page it cites. For an imported run each row also
 * shows its decision state and decisions, and the decision forms when the viewer may decide. */
export function MatrixTable({
  matrix,
  runId,
  decisions,
}: {
  matrix: Matrix;
  runId: string;
  decisions: DecisionView;
}) {
  const t = useTranslations("matrix");
  const td = useTranslations("decisions");
  const byRequirement = new Map(
    (decisions.proposals ?? [])
      .filter((p) => p.kind === "coverage")
      .map((p) => [p.requirement, p] as const),
  );
  const decided = decisions.proposals !== undefined;
  return (
    <>
      <DecisionNotice view={decisions} />
      <div className={s.overview}>
        <CoverageSummary rows={matrix.requirements} t={t} />
        <DecisionTally counts={decisions.counts} kinds={["coverage"]} also={["test_step"]} />
      </div>
      <DataTable
        className={decisions.access.mode === "readOnly" ? `${s.matrix} ${s.readOnly}` : s.matrix}
      >
        <thead>
          <tr>
            <th className={s.colRequirement}>{t("requirement")}</th>
            <th className={s.colValue}>{t("value")}</th>
            <th className={s.colCoverage}>{t("coverage")}</th>
            <th className={s.colReason}>{t("reason")}</th>
            <th className={s.colEvidence}>{t("evidence")}</th>
            {decided && <th className={s.colDecision}>{td("column")}</th>}
          </tr>
        </thead>
        <tbody>
          {matrix.requirements.map((row) => (
            <tr key={row.id} data-testid={row.id} className={s[`edge_${row.coverage ?? "none"}`]}>
              <td>
                <strong className={cell.id}>{row.id}</strong>
                <p className={s.text}>{row.text}</p>
                <span className={s.cite}>
                  <CiteLink runId={runId} cite={row.source} />
                </span>
              </td>
              <td>
                {row.value ? (
                  <span className={s.value}>{formatValue(t, row.value)}</span>
                ) : (
                  <span className="muted">{t("noValue")}</span>
                )}
                {row.value_citation && !sameCite(row.value_citation, row.source) && (
                  <div className={s.cite}>
                    <CiteLink runId={runId} cite={row.value_citation} />
                  </div>
                )}
              </td>
              <td>
                <CoverageCell row={row} proposal={byRequirement.get(row.id)} t={t} />
              </td>
              <td className={s.reason}>{row.reason}</td>
              <td>
                <EvidenceCell row={row} runId={runId} t={t} />
              </td>
              {decided && (
                <td>
                  <DecisionCell
                    proposal={byRequirement.get(row.id)}
                    runId={runId}
                    screen="matrix"
                    access={decisions.access}
                    proposed={row.coverage}
                  />
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </DataTable>
      {matrix.not_read.length > 0 && (
        <section className={s.notRead}>
          <h2>{t("notRead")}</h2>
          <ul>
            {matrix.not_read.map((d) => (
              <li key={`${d.doc_id}/${d.rev}`}>
                {d.doc_id} rev {d.rev} ({d.format})
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
