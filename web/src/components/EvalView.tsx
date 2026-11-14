import { useTranslations } from "next-intl";

import type { EvalSummary } from "@/api/client";

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
      <p>
        <strong className={summary.gates_passed ? "gates-pass" : "gates-fail"}>
          {t(summary.gates_passed ? "gatesPassed" : "gatesFailed")}
        </strong>
        {" · "}
        {t("cost", { usd: summary.cost_usd === null ? "–" : usd.format(summary.cost_usd) })}
        {summary.model && <> · {t("model", { model: summary.model })}</>}
        {" · "}
        {t("scorer", { version: summary.scorer_version })}
      </p>
      <table>
        <thead>
          <tr>
            <th>{t("metric")}</th>
            <th>{t("kn")}</th>
            <th>{t("rate")}</th>
            <th>{t("split")}</th>
          </tr>
        </thead>
        <tbody>
          {summary.rates.map((r) => (
            <tr key={r.metric} data-testid={r.metric}>
              <td>
                {t(`metrics.${r.metric}`)}
                <div className="muted">{t(`better.${r.better}`)}</div>
              </td>
              <td data-testid="kn">
                {r.k}/{r.n}
              </td>
              <td>{r.rate === null ? "–" : percent.format(r.rate)}</td>
              <td>{split}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">{t("smallN")}</p>
    </>
  );
}
