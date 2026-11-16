// PROTOTYPE (feat/ui-redesign-prototype, never merged).
// Variant A, "Ledger": one dense table, in URS order, with a sticky header, a summary strip of
// class counts above it, and evidence folded to one line per row (open for the full list).
import { useTranslations } from "next-intl";
import Link from "next/link";

import { CiteLink } from "@/components/CiteLink";
import { DecisionCell } from "@/components/Decisions";
import { Evidence, formatValue } from "@/components/MatrixTable";

import { CoveragePill, RISK_ORDER, StubActions, byRequirement, countBy, cov } from "./shared";
import type { VariantProps } from "./shared";
import s from "./VariantA.module.css";
import ui from "./ui.module.css";

export const NAME = "Ledger";

export function VariantA({ matrix, runId, decisions, equipment }: VariantProps) {
  const t = useTranslations("matrix");
  const td = useTranslations("decisions");
  const proposals = byRequirement(decisions);
  const counts = countBy(matrix.requirements);
  const c = decisions.counts?.coverage;
  const run = encodeURIComponent(runId);
  return (
    <div className={`${ui.tokens} ${s.root}`}>
      <div className={s.head}>
        <div>
          <Link href="/" className={s.back}>
            ← {t("back")}
          </Link>
          <h1 className={s.title}>
            {t("title")} <span className={s.eq}>{equipment}</span>
          </h1>
          <div className={ui.muted}>run {runId}</div>
        </div>
        <nav className={s.tabs}>
          <span className={s.tabOn}>{t("title")}</span>
          <Link href={`/runs/${run}/findings`}>{t("toFindings")}</Link>
          <Link href={`/runs/${run}/left-out`}>{t("toLeftOut")}</Link>
          <Link href={`/runs/${run}/eval`}>{t("toEval")}</Link>
        </nav>
      </div>

      <div className={s.strip}>
        <div className={s.stat}>
          <b>{matrix.requirements.length}</b>
          <span>{t("requirement")}</span>
        </div>
        {RISK_ORDER.filter((k) => counts[k] > 0).map((k) => (
          <div key={k} className={s.stat}>
            <b>{counts[k]}</b>
            <CoveragePill c={k} />
          </div>
        ))}
        {c && (
          <div className={`${s.stat} ${s.decided}`}>
            <b>
              {c.total - c.undecided}/{c.total}
            </b>
            <span>
              {td("states.decided")} · {td("counts.accepted")} {c.accepted} · {td("counts.edited")}{" "}
              {c.edited} · {td("counts.changed")} {c.changed}
            </span>
          </div>
        )}
      </div>

      {decisions.access.mode === "readOnly" && (
        <p className={ui.notice}>{td(`readOnly.${decisions.access.why}`)}</p>
      )}

      <table className={s.table}>
        <thead>
          <tr>
            <th className={s.colReq}>{t("requirement")}</th>
            <th className={s.colVal}>{t("value")}</th>
            <th className={s.colCov}>
              {t("coverage")} / {t("reason")}
            </th>
            <th>{t("evidence")}</th>
            {decisions.proposals && <th className={s.colDec}>{td("column")}</th>}
          </tr>
        </thead>
        <tbody>
          {matrix.requirements.map((row) => {
            const p = proposals.get(row.id);
            const first = row.evidence[0];
            const more = row.evidence.length + row.design.length;
            return (
              <tr key={row.id} className={s[`row_${cov(row)}`]}>
                <td>
                  <div className={s.id}>{row.id}</div>
                  <div>{row.text}</div>
                  <div className={s.cite}>
                    <CiteLink runId={runId} cite={row.source} />
                  </div>
                </td>
                <td>
                  {row.value ? (
                    <span className={s.value}>{formatValue(t, row.value)}</span>
                  ) : (
                    <span className={ui.muted}>{t("noValue")}</span>
                  )}
                </td>
                <td>
                  <CoveragePill c={cov(row)} />
                  <div className={s.reason}>{row.reason}</div>
                </td>
                <td>
                  {more === 0 ? (
                    <span className={ui.muted}>{t("noEvidence")}</span>
                  ) : (
                    <details className={s.ev}>
                      <summary>
                        {first ? (
                          <>
                            <b>{first.step}</b>{" "}
                            {t("observed", {
                              observed: first.observed_value
                                ? formatValue(t, first.observed_value, true)
                                : first.observed,
                            })}{" "}
                            · {t(`results.${first.result ?? "none"}`)}
                          </>
                        ) : (
                          <b>{t("design")}</b>
                        )}
                        {more > 1 && <span className={s.more}> +{more - 1}</span>}
                      </summary>
                      <Evidence row={row} runId={runId} t={t} />
                    </details>
                  )}
                </td>
                {decisions.proposals && (
                  <td>
                    <div className={s.dec}>
                      <DecisionCell
                        proposal={p}
                        runId={runId}
                        screen="matrix"
                        access={{ mode: "readOnly", why: "noRole" }}
                        proposed={row.coverage}
                      />
                    </div>
                    <StubActions decisions={decisions} proposed={row.coverage} compact />
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
