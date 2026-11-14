import { useTranslations } from "next-intl";

import type { Matrix, MatrixRow, ObservedValue, Value } from "@/api/client";
import { CiteLink } from "./CiteLink";

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

function Evidence({ row, runId, t }: { row: MatrixRow; runId: string; t: T }) {
  if (row.evidence.length === 0 && row.design.length === 0) {
    return <span className="muted">{t("noEvidence")}</span>;
  }
  return (
    <ul className="evidence">
      {row.evidence.map((e) => (
        <li key={`${e.doc}/${e.step}`}>
          <strong>
            {e.stage} {e.step}
          </strong>{" "}
          {e.test}
          <div>
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
          <strong>{t("design")}</strong> {d.name}: {t("printed", { printed: d.printed })}
          <div>
            <CiteLink runId={runId} cite={d.citation} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** The traceability matrix: one row per requirement, with its Coverage class and reason,
 * and every piece of Evidence linked to the page it cites. */
export function MatrixTable({ matrix, runId }: { matrix: Matrix; runId: string }) {
  const t = useTranslations("matrix");
  return (
    <>
      <table className="matrix">
        <thead>
          <tr>
            <th>{t("requirement")}</th>
            <th>{t("value")}</th>
            <th>{t("coverage")}</th>
            <th>{t("reason")}</th>
            <th>{t("evidence")}</th>
          </tr>
        </thead>
        <tbody>
          {matrix.requirements.map((row) => (
            <tr key={row.id} data-testid={row.id}>
              <td>
                <strong>{row.id}</strong>
                <p>{row.text}</p>
                <CiteLink runId={runId} cite={row.source} />
              </td>
              <td>
                {row.value ? formatValue(t, row.value) : <span className="muted">{t("noValue")}</span>}
                {row.value_citation && (
                  <div>
                    <CiteLink runId={runId} cite={row.value_citation} />
                  </div>
                )}
              </td>
              <td>
                <span className={`coverage coverage-${row.coverage ?? "none"}`}>
                  {t(`classes.${row.coverage ?? "none"}`)}
                </span>
              </td>
              <td>{row.reason}</td>
              <td>
                <Evidence row={row} runId={runId} t={t} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {matrix.not_read.length > 0 && (
        <section>
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
