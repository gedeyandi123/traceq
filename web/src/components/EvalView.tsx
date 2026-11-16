import { useTranslations } from "next-intl";

import type { EvalSummary } from "@/api/client";

import { Panel } from "./ui/ui";
import s from "./EvalView.module.css";
import tbl from "./ui/table.module.css";

const percent = new Intl.NumberFormat("id-ID", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const usd = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 4 });

/** The eval screen of a scored run: each rate with k/n and its split (dev TP-201 or
 * held-out), the fabrication gates and the run's cost. Only aggregates reach this screen; the
 * harness serves them, never the system's API. */
export function EvalView({ summary }: { summary: EvalSummary }) {
  const t = useTranslations("eval");
  const split = t(`splits.${summary.split}`, { equipment: summary.equipment });
  return (
    <>
      <Panel title={t("summaryTitle")}>
      <div className={s.top}>
        <div className={`${s.gate} ${summary.gates_passed ? s.pass : s.fail}`}>
          <span className={s.gateIcon} aria-hidden="true">
            {summary.gates_passed ? "✓" : "✕"}
          </span>
          <strong className={summary.gates_passed ? "gates-pass" : "gates-fail"}>
            {t(summary.gates_passed ? "gatesPassed" : "gatesFailed")}
          </strong>
        </div>
        <dl className={s.facts}>
          <div>
            <dd className="num">
              {t("cost", { usd: summary.cost_usd === null ? "–" : usd.format(summary.cost_usd) })}
            </dd>
          </div>
          {summary.model && (
            <div>
              <dd>{t("model", { model: summary.model })}</dd>
            </div>
          )}
          <div>
            <dd>{t("scorer", { version: summary.scorer_version })}</dd>
          </div>
          <div>
            <dd className={s.split}>{split}</dd>
          </div>
        </dl>
      </div>
      </Panel>
      <div className={tbl.wrap}>
        <table className={tbl.table}>
          <thead>
            <tr>
              <th>{t("metric")}</th>
              <th className={tbl.num}>{t("kn")}</th>
              <th className={s.colRate}>{t("rate")}</th>
              <th>{t("split")}</th>
            </tr>
          </thead>
          <tbody>
            {summary.rates.map((r) => (
              <tr key={r.metric} data-testid={r.metric}>
                <td>
                  <span className={s.metric}>{t(`metrics.${r.metric}`)}</span>
                  <div className={s.better}>{t(`better.${r.better}`)}</div>
                </td>
                <td data-testid="kn" className={`${tbl.num} ${s.kn}`}>
                  {r.k}/{r.n}
                </td>
                <td className={s.colRate}>
                  <div className={s.rate}>
                    <span className="num">{r.rate === null ? "–" : percent.format(r.rate)}</span>
                    {r.rate !== null && (
                      <span className={s.meter} aria-hidden="true">
                        <span
                          className={r.better === "lower" ? s.fillLower : s.fill}
                          style={{ width: `${Math.round(r.rate * 100)}%` }}
                        />
                      </span>
                    )}
                  </div>
                </td>
                <td className={s.splitCell}>{split}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className={s.smallN}>{t("smallN")}</p>
    </>
  );
}
