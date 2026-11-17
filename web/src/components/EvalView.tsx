import { useTranslations } from "next-intl";

import type { EvalSummary } from "@/api/client";

import s from "./EvalView.module.css";
import { cell, DataTable, EmptyState, Panel, SectionHeading } from "./ui/ui";

const percent = new Intl.NumberFormat("id-ID", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const usd = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 4 });

/** The eval screen of a run: the fabrication gates and the run's cost in a panel, then each
 * rate with k/n and its split (dev TP-201 or held-out). `summary` is null when the run is not
 * scored or the harness is unreachable, which reads as "not scored yet", not an error. Only
 * aggregates reach this screen; the harness serves them, never the system's API. */
export function EvalView({ summary }: { summary: EvalSummary | null }) {
  const t = useTranslations("eval");
  if (summary === null) {
    return <EmptyState title={t("notScoredTitle")}>{t("notScored")}</EmptyState>;
  }
  const split = t(`splits.${summary.split}`, { equipment: summary.equipment });
  return (
    <div className={s.screen}>
      <Panel title={t("summaryTitle")}>
        <div className={s.top}>
          <div className={`${s.gate} ${summary.gates_passed ? s.pass : s.fail}`}>
            <span className={s.gateIcon} aria-hidden="true">
              {summary.gates_passed ? "✓" : "✕"}
            </span>
            <strong>{t(summary.gates_passed ? "gatesPassed" : "gatesFailed")}</strong>
          </div>
          <ul className={s.facts}>
            <li>{t("cost", { usd: summary.cost_usd === null ? "–" : usd.format(summary.cost_usd) })}</li>
            {summary.model && <li>{t("model", { model: summary.model })}</li>}
            <li>{t("scorer", { version: summary.scorer_version })}</li>
          </ul>
        </div>
      </Panel>
      <section aria-labelledby="eval-rates">
        <SectionHeading id="eval-rates" title={t("ratesTitle")} count={summary.rates.length} />
        <DataTable>
          <thead>
            <tr>
              <th>{t("metric")}</th>
              <th className={cell.num}>{t("kn")}</th>
              <th className={cell.num}>{t("rate")}</th>
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
                <td data-testid="kn" className={`${cell.num} ${s.kn}`}>
                  {r.k}/{r.n}
                </td>
                <td className={cell.num}>{r.rate === null ? "–" : percent.format(r.rate)}</td>
                <td className={s.split}>{split}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      </section>
      <p className={s.smallN}>{t("smallN")}</p>
    </div>
  );
}
