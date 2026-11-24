import { CheckCircle2, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";

import type { EvalSummary } from "@/api/client";

import { cell, DataTable, EmptyState, SectionHeading } from "./ui/ui";

const percent = new Intl.NumberFormat("id-ID", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const usd = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 4 });

/** The eval screen of a run: Gate & Cost hero banner, then a compact tabular-nums rates
 * table with k/n, percentage, and split. `summary` is null when the run is not scored or the
 * harness is unreachable, which reads as "not scored yet", not an error. Only aggregates reach
 * this screen; the harness serves them, never the system's API. */
export function EvalView({ summary }: { summary: EvalSummary | null }) {
  const t = useTranslations("eval");
  if (summary === null) {
    return <EmptyState title={t("notScoredTitle")}>{t("notScored")}</EmptyState>;
  }
  const split = t(`splits.${summary.split}`, { equipment: summary.equipment });
  const GateIcon = summary.gates_passed ? CheckCircle2 : XCircle;
  return (
    <div className="flex flex-col gap-6">
      <section className="flex min-w-0 flex-col gap-3 rounded-lg border border-border bg-surface px-5 py-4 shadow-xs">
        <h2 className="m-0 text-xs font-semibold tracking-wider text-ink-muted uppercase">{t("summaryTitle")}</h2>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div
            className={`inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-sm font-semibold ${
              summary.gates_passed
                ? "border-pass-edge bg-pass-soft text-pass"
                : "border-fail-edge bg-fail-soft text-fail"
            }`}
          >
            <GateIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
            <strong>{t(summary.gates_passed ? "gatesPassed" : "gatesFailed")}</strong>
          </div>
          <ul className="m-0 flex list-none flex-wrap items-center gap-x-4 gap-y-1.5 p-0 text-xs text-ink-muted tabular-nums">
            <li className="font-medium text-ink">
              {t("cost", { usd: summary.cost_usd === null ? "–" : usd.format(summary.cost_usd) })}
            </li>
            {summary.model && <li>{t("model", { model: summary.model })}</li>}
            <li>{t("scorer", { version: summary.scorer_version })}</li>
          </ul>
        </div>
      </section>

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
                  <span className="font-semibold text-ink">{t(`metrics.${r.metric}`)}</span>
                  <div className="mt-0.5 text-xs text-ink-muted">{t(`better.${r.better}`)}</div>
                </td>
                <td data-testid="kn" className={`${cell.num} font-medium text-ink`}>
                  {r.k}/{r.n}
                </td>
                <td className={`${cell.num} font-bold text-ink`}>
                  {r.rate === null ? "–" : percent.format(r.rate)}
                </td>
                <td className="text-xs whitespace-nowrap text-ink-muted tabular-nums">{split}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      </section>

      <p className="m-0 max-w-[75ch] text-xs text-ink-muted">{t("smallN")}</p>
    </div>
  );
}
