// PROTOTYPE (feat/ui-redesign-prototype, never merged).
// Variant B, "Triage": master-detail. The left list groups requirements riskiest first
// (Konflik, Celah, Sebagian, ...); the right pane shows one requirement in full, with the
// evidence as cards and the decision at the bottom. Selection is the `req` URL parameter.
import { useTranslations } from "next-intl";
import Link from "next/link";

import type { MatrixRow } from "@/api/client";
import { CiteLink } from "@/components/CiteLink";
import { DecisionCell } from "@/components/Decisions";
import { formatValue } from "@/components/MatrixTable";

import { CoveragePill, RISK_ORDER, StubActions, byRequirement, countBy, cov } from "./shared";
import type { VariantProps } from "./shared";
import s from "./VariantB.module.css";
import ui from "./ui.module.css";

export const NAME = "Triage";

export function VariantB({ matrix, runId, decisions, equipment, selected }: VariantProps) {
  const t = useTranslations("matrix");
  const td = useTranslations("decisions");
  const proposals = byRequirement(decisions);
  const counts = countBy(matrix.requirements);
  const ordered: MatrixRow[] = RISK_ORDER.flatMap((k) =>
    matrix.requirements.filter((r) => cov(r) === k),
  );
  const row = ordered.find((r) => r.id === selected) ?? ordered[0];
  if (row === undefined) return null;
  const i = ordered.indexOf(row);
  const prev = ordered[i - 1];
  const next = ordered[i + 1];
  const run = encodeURIComponent(runId);
  const href = (id: string) => `/runs/${run}?variant=B&req=${encodeURIComponent(id)}`;
  const total = matrix.requirements.length;
  const p = proposals.get(row.id);
  const c = decisions.counts?.coverage;

  return (
    <div className={`${ui.tokens} ${s.root}`}>
      <div className={s.top}>
        <Link href="/" className={s.back}>
          ← {t("back")}
        </Link>
        <h1 className={s.title}>
          {t("title")} · {equipment}
        </h1>
        <div className={s.bar} aria-label={t("coverage")}>
          {RISK_ORDER.filter((k) => counts[k] > 0).map((k) => (
            <span
              key={k}
              className={`${s.seg} ${ui[`cov_${k}`]}`}
              style={{ flexGrow: counts[k] }}
              title={`${t(`classes.${k}`)}: ${counts[k]}`}
            >
              {counts[k]}
            </span>
          ))}
        </div>
        {c && (
          <span className={s.progress}>
            {td("states.decided")} {c.total - c.undecided}/{c.total}
          </span>
        )}
        <nav className={s.links}>
          <Link href={`/runs/${run}/findings`}>{t("toFindings")}</Link>
          <Link href={`/runs/${run}/left-out`}>{t("toLeftOut")}</Link>
          <Link href={`/runs/${run}/eval`}>{t("toEval")}</Link>
        </nav>
      </div>

      {decisions.access.mode === "readOnly" && (
        <p className={ui.notice}>{td(`readOnly.${decisions.access.why}`)}</p>
      )}

      <div className={s.split}>
        <nav className={s.list} aria-label={t("requirement")}>
          {RISK_ORDER.filter((k) => counts[k] > 0).map((k) => (
            <section key={k}>
              <h2 className={s.group}>
                <CoveragePill c={k} /> <span className={ui.muted}>{counts[k]}</span>
              </h2>
              <ul>
                {ordered
                  .filter((r) => cov(r) === k)
                  .map((r) => {
                    const state = proposals.get(r.id)?.state;
                    return (
                      <li key={r.id}>
                        <Link
                          href={href(r.id)}
                          scroll={false}
                          className={`${s.item} ${r.id === row.id ? s.on : ""}`}
                        >
                          <span className={`${s.dot} ${state ? s[`dot_${state}`] : ""}`} />
                          <span className={s.itemId}>{r.id.replace(/^URS-[A-Z0-9]+-/, "")}</span>
                          <span className={s.itemText}>{r.text}</span>
                        </Link>
                      </li>
                    );
                  })}
              </ul>
            </section>
          ))}
        </nav>

        <article className={s.detail}>
          <div className={s.dhead}>
            <div className={s.did}>
              {row.id} <CoveragePill c={cov(row)} />
            </div>
            <div className={s.pager}>
              {prev ? <Link href={href(prev.id)} scroll={false}>← {prev.id.slice(-3)}</Link> : <span />}
              <span className={ui.muted}>
                {i + 1}/{total}
              </span>
              {next ? <Link href={href(next.id)} scroll={false}>{next.id.slice(-3)} →</Link> : <span />}
            </div>
          </div>
          <p className={s.text}>{row.text}</p>
          <div className={s.meta}>
            <div>
              <div className={s.label}>{t("value")}</div>
              <div className={s.big}>
                {row.value ? formatValue(t, row.value) : <span className={ui.muted}>{t("noValue")}</span>}
              </div>
            </div>
            <div>
              <div className={s.label}>{t("reason")}</div>
              <div>{row.reason}</div>
            </div>
            <div>
              <div className={s.label}>URS</div>
              <CiteLink runId={runId} cite={row.source} />
            </div>
          </div>

          <h3 className={s.h3}>
            {t("evidence")} ({row.evidence.length + row.design.length})
          </h3>
          {row.evidence.length + row.design.length === 0 && (
            <p className={ui.muted}>{t("noEvidence")}</p>
          )}
          <div className={s.cards}>
            {row.evidence.map((e) => (
              <div key={`${e.doc}/${e.step}`} className={`${s.card} ${e.result === "fail" ? s.fail : ""}`}>
                <div className={s.cardHead}>
                  <b>
                    {e.stage} {e.step}
                  </b>
                  <span className={`${s.result} ${s[`r_${e.result ?? "none"}`]}`}>
                    {t(`results.${e.result ?? "none"}`)}
                  </span>
                </div>
                <div>{e.test}</div>
                <dl className={s.dl}>
                  <dt>Kriteria</dt>
                  <dd>{e.acceptance}</dd>
                  <dt>Teramati</dt>
                  <dd>{e.observed_value ? formatValue(t, e.observed_value, true) : e.observed}</dd>
                </dl>
                {e.failure && <div className={s.failure}>{e.failure}</div>}
                <CiteLink runId={runId} cite={e.citation} />
              </div>
            ))}
            {row.design.map((d) => (
              <div key={`${d.doc}/${d.name}`} className={s.card}>
                <div className={s.cardHead}>
                  <b>{t("design")}</b>
                </div>
                <div>{d.name}</div>
                <dl className={s.dl}>
                  <dt>Tercetak</dt>
                  <dd>{d.printed}</dd>
                </dl>
                <CiteLink runId={runId} cite={d.citation} />
              </div>
            ))}
          </div>

          {decisions.proposals && (
            <footer className={s.decide}>
              <div className={s.decState}>
                <DecisionCell
                  proposal={p}
                  runId={runId}
                  screen="matrix"
                  access={{ mode: "readOnly", why: "noRole" }}
                  proposed={row.coverage}
                />
              </div>
              <StubActions decisions={decisions} proposed={row.coverage} />
            </footer>
          )}
        </article>
      </div>
    </div>
  );
}
