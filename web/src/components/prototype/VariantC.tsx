// PROTOTYPE (feat/ui-redesign-prototype, never merged).
// Variant C, "Board": one column per Coverage class, riskiest on the left, each requirement a
// card; a headline states how many need attention. Evidence shows as step chips (green pass,
// red fail) with the full list folded inside the card.
import { useTranslations } from "next-intl";
import Link from "next/link";

import { CiteLink } from "@/components/CiteLink";
import { Evidence, formatValue } from "@/components/MatrixTable";

import { CoveragePill, RISK_ORDER, StubActions, byRequirement, countBy, cov } from "./shared";
import type { VariantProps } from "./shared";
import s from "./VariantC.module.css";
import ui from "./ui.module.css";

export const NAME = "Board";

export function VariantC({ matrix, runId, decisions, equipment }: VariantProps) {
  const t = useTranslations("matrix");
  const td = useTranslations("decisions");
  const proposals = byRequirement(decisions);
  const counts = countBy(matrix.requirements);
  const attention = counts.conflict + counts.gap;
  const run = encodeURIComponent(runId);
  const c = decisions.counts?.coverage;
  return (
    <div className={`${ui.tokens} ${s.root}`}>
      <div className={s.hero}>
        <div>
          <Link href="/" className={s.back}>
            ← {t("back")}
          </Link>
          <h1 className={s.headline}>
            {equipment}: <b>{attention}</b> dari {matrix.requirements.length} persyaratan perlu
            perhatian
          </h1>
          <div className={ui.muted}>
            {t("title")} · run {runId}
            {c && (
              <>
                {" · "}
                {td("states.undecided")} {c.undecided}
              </>
            )}
          </div>
        </div>
        <nav className={s.nav}>
          <Link href={`/runs/${run}/findings`}>{t("toFindings")} →</Link>
          <Link href={`/runs/${run}/left-out`}>{t("toLeftOut")} →</Link>
          <Link href={`/runs/${run}/eval`}>{t("toEval")} →</Link>
        </nav>
      </div>

      {decisions.access.mode === "readOnly" && (
        <p className={ui.notice}>{td(`readOnly.${decisions.access.why}`)}</p>
      )}

      <div className={s.board}>
        {RISK_ORDER.filter((k) => counts[k] > 0).map((k) => (
          <section key={k} className={`${s.col} ${s[`col_${k}`]}`}>
            <h2 className={s.colHead}>
              <CoveragePill c={k} />
              <span className={s.count}>{counts[k]}</span>
            </h2>
            {matrix.requirements
              .filter((r) => cov(r) === k)
              .map((r) => {
                const p = proposals.get(r.id);
                return (
                  <div key={r.id} className={s.card}>
                    <div className={s.cardTop}>
                      <span className={s.id}>{r.id}</span>
                      {p && (
                        <span className={`${s.state} ${s[`st_${p.state}`]}`}>
                          {td(`states.${p.state}`).split(":")[0]}
                        </span>
                      )}
                    </div>
                    <div className={s.text}>{r.text}</div>
                    {r.value && <div className={s.value}>{formatValue(t, r.value)}</div>}
                    <div className={s.reason}>{r.reason}</div>
                    {r.evidence.length + r.design.length > 0 ? (
                      <details className={s.ev}>
                        <summary>
                          {r.evidence.map((e) => (
                            <span
                              key={`${e.doc}/${e.step}`}
                              className={`${s.chip} ${s[`chip_${e.result ?? "none"}`]}`}
                            >
                              {e.step}
                            </span>
                          ))}
                          {r.design.length > 0 && (
                            <span className={s.chip}>
                              {t("design")} {r.design.length}
                            </span>
                          )}
                        </summary>
                        <Evidence row={r} runId={runId} t={t} />
                      </details>
                    ) : (
                      <div className={`${ui.muted} ${s.small}`}>{t("noEvidence")}</div>
                    )}
                    <div className={s.small}>
                      <CiteLink runId={runId} cite={r.source} />
                    </div>
                    <StubActions decisions={decisions} proposed={r.coverage} compact />
                  </div>
                );
              })}
          </section>
        ))}
      </div>
    </div>
  );
}
