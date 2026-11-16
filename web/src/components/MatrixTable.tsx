import { useTranslations } from "next-intl";

import type { Matrix, MatrixRow, ObservedValue, Value } from "@/api/client";
import { CiteLink } from "./CiteLink";
import { CoverageBadge } from "./ui/ui";
import type { CoverageKey } from "./ui/ui";
import s from "./MatrixTable.module.css";
import tbl from "./ui/table.module.css";
import { DecisionCell, DecisionNotice, DecisionTally } from "./Decisions";
import type { DecisionView } from "./Decisions";

type T = ReturnType<typeof useTranslations<"matrix">>;

const number = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 3 });

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

/** Riskiest first: the order of the coverage summary. */
const RISK: readonly CoverageKey[] = ["conflict", "gap", "partial", "site_only", "covered_by_vendor", "none"];

function EvidenceChips({ row, t }: { row: MatrixRow; t: T }) {
  return (
    <span className={s.chips}>
      {row.evidence.map((e) => (
        <span key={`${e.doc}/${e.step}`} className={`${s.chip} ${s[`chip_${e.result ?? "none"}`]}`}>
          <span aria-hidden="true">{e.result === "pass" ? "✓" : e.result === "fail" ? "✕" : "·"}</span>
          {e.step}
        </span>
      ))}
      {row.design.length > 0 && (
        <span className={s.chip}>
          {t("design")} ×{row.design.length}
        </span>
      )}
    </span>
  );
}

function Evidence({ row, runId, t }: { row: MatrixRow; runId: string; t: T }) {
  if (row.evidence.length === 0 && row.design.length === 0) {
    return <span className="muted">{t("noEvidence")}</span>;
  }
  return (
    <details className={s.ev}>
      <summary>
        <EvidenceChips row={row} t={t} />
      </summary>
      <ul className={s.evList}>
        {row.evidence.map((e) => (
          <li key={`${e.doc}/${e.step}`}>
            <div className={s.evHead}>
              <span className={s.stage}>{e.stage}</span>
              <strong>{e.step}</strong>
            </div>
            <div>{e.test}</div>
            <div className={s.obs}>
              {t("observed", {
                observed: e.observed_value ? formatValue(t, e.observed_value, true) : e.observed,
              })}
              {" · "}
              {t("result", { result: t(`results.${e.result ?? "none"}`) })}
            </div>
            {e.failure && <div className="failure">{e.failure}</div>}
            <CiteLink runId={runId} cite={e.citation} />
          </li>
        ))}
        {row.design.map((d) => (
          <li key={`${d.doc}/${d.name}`}>
            <div className={s.evHead}>
              <span className={s.stage}>{t("design")}</span>
            </div>
            <div>
              {d.name}: {t("printed", { printed: d.printed })}
            </div>
            <CiteLink runId={runId} cite={d.citation} />
          </li>
        ))}
      </ul>
    </details>
  );
}

function CoverageSummary({ rows, t }: { rows: readonly MatrixRow[]; t: T }) {
  const counts = new Map<CoverageKey, number>();
  for (const r of rows) counts.set(r.coverage ?? "none", (counts.get(r.coverage ?? "none") ?? 0) + 1);
  const present = RISK.filter((k) => (counts.get(k) ?? 0) > 0);
  return (
    <div className={s.summary}>
      <div className={s.summaryHead}>
        <span className={s.total}>{rows.length}</span>
        <span className={s.totalLabel}>{t("requirement")}</span>
      </div>
      <div className={s.bar} aria-hidden="true">
        {present.map((k) => (
          <span key={k} className={s[`seg_${k}`]} style={{ flexGrow: counts.get(k) }} />
        ))}
      </div>
      <ul className={s.legend}>
        {present.map((k) => (
          <li key={k}>
            <span className={s.legendN}>{counts.get(k)}</span>
            <CoverageBadge cls={k} label={t(`classes.${k}`)} />
          </li>
        ))}
      </ul>
    </div>
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
        <DecisionTally counts={decisions.counts} kinds={["coverage"]} />
      </div>
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
      <div className={tbl.wrap}>
        <table className={`${tbl.table} ${s.matrix}`}>
          <thead>
            <tr>
              <th className={s.colReq}>{t("requirement")}</th>
              <th className={s.colVal}>{t("value")}</th>
              <th className={s.colCov}>{t("coverage")}</th>
              <th className={s.colEv}>{t("evidence")}</th>
              {decided && <th className={s.colDec}>{td("column")}</th>}
            </tr>
          </thead>
          <tbody>
            {matrix.requirements.map((row) => (
              <tr key={row.id} data-testid={row.id} className={s[`row_${row.coverage ?? "none"}`]}>
                <td>
                  <div className={tbl.id}>{row.id}</div>
                  <p className={s.text}>{row.text}</p>
                  <div className={s.cite}>
                    <CiteLink runId={runId} cite={row.source} />
                  </div>
                </td>
                <td>
                  {row.value ? (
                    <span className={s.value}>{formatValue(t, row.value)}</span>
                  ) : (
                    <span className="muted">{t("noValue")}</span>
                  )}
                  {row.value_citation && (
                    <div className={s.cite}>
                      <CiteLink runId={runId} cite={row.value_citation} />
                    </div>
                  )}
                </td>
                <td>
                  <CoverageBadge cls={row.coverage ?? "none"} label={t(`classes.${row.coverage ?? "none"}`)} />
                  <p className={s.reason}>{row.reason}</p>
                </td>
                <td>
                  <Evidence row={row} runId={runId} t={t} />
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
        </table>
      </div>
    </>
  );
}
