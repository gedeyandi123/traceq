import { useTranslations } from "next-intl";

import type { Cite, Findings, Proposal } from "@/api/client";
import { CiteLink } from "./CiteLink";
import { DecisionCell, DecisionNotice, DecisionTally } from "./Decisions";
import type { DecisionView } from "./Decisions";
import { EmptyState, Panel, SectionHead, StatList } from "./ui/ui";
import s from "./FindingsView.module.css";
import tbl from "./ui/table.module.css";

function Citations({ cites, runId }: { cites: readonly Cite[]; runId: string }) {
  return (
    <ul className={tbl.cites}>
      {cites.map((c) => (
        <li key={`${c.doc}/${c.rev}/${c.page}/${c.quote}`}>
          <CiteLink runId={runId} cite={c} />
        </li>
      ))}
    </ul>
  );
}

function byPosition(view: DecisionView, kind: Proposal["kind"]): Map<number | null, Proposal> {
  return new Map(
    (view.proposals ?? []).filter((p) => p.kind === kind).map((p) => [p.position, p] as const),
  );
}

/** The Pre-review of a run: Check Findings (deterministic rules) and AI Findings (advisory,
 * pending a human) in separate sections, then the documents the VMP requires that the corpus
 * lacks. Every finding links to the page it cites. For an imported run each finding shows its
 * decision state in place of the file's "pending", and the decision forms when the viewer may
 * decide. */
export function FindingsView({
  findings,
  runId,
  decisions,
}: {
  findings: Findings;
  runId: string;
  decisions: DecisionView;
}) {
  const t = useTranslations("findings");
  const td = useTranslations("decisions");
  const decided = decisions.proposals !== undefined;
  const checks = byPosition(decisions, "check");
  const ais = byPosition(decisions, "ai");
  return (
    <>
      <DecisionNotice view={decisions} />
      <div className={s.overview}>
        <Panel title={t("summaryTitle")}>
          <StatList
            items={[
              { n: findings.check_findings.length, label: t("check"), href: "#check-findings" },
              { n: findings.ai_findings.length, label: t("ai"), href: "#ai-findings" },
              { n: findings.missing_documents.length, label: t("missing"), href: "#missing-documents" },
            ]}
          />
        </Panel>
        <DecisionTally counts={decisions.counts} kinds={["check", "ai"]} />
      </div>
      <section aria-labelledby="check-findings">
        <SectionHead id="check-findings" title={t("check")} count={findings.check_findings.length} note={t("checkNote")} />
        {findings.check_findings.length === 0 ? (
          <EmptyState title={t("none")} />
        ) : (
          <div className={tbl.wrap}>
          <table className={tbl.table}>
            <thead>
              <tr>
                <th>{t("type")}</th>
                <th>{t("document")}</th>
                <th>{t("detail")}</th>
                <th>{t("citations")}</th>
                {decided && <th>{td("column")}</th>}
              </tr>
            </thead>
            <tbody>
              {findings.check_findings.map((f, i) => (
                <tr key={`${f.type}/${f.doc}/${i}`}>
                  <td className={s.type}>{t(`checkTypes.${f.type}`)}</td>
                  <td className={tbl.id}>{f.doc}</td>
                  <td>{f.detail}</td>
                  <td>
                    <Citations cites={f.citations} runId={runId} />
                    {f.rule && (
                      <div className={s.rule}>
                        {t("rule")}: <CiteLink runId={runId} cite={f.rule} />
                      </div>
                    )}
                  </td>
                  {decided && (
                    <td>
                      <DecisionCell
                        proposal={checks.get(i)}
                        runId={runId}
                        screen="findings"
                        access={decisions.access}
                      />
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </section>

      <section aria-labelledby="ai-findings">
        <SectionHead id="ai-findings" title={t("ai")} count={findings.ai_findings.length} note={t("aiNote")} />
        {findings.ai_findings.length === 0 ? (
          <EmptyState title={t("none")} />
        ) : (
          <div className={tbl.wrap}>
          <table className={tbl.table}>
            <thead>
              <tr>
                <th>{t("type")}</th>
                <th>{t("detail")}</th>
                <th>{t("citations")}</th>
                <th>{t("status")}</th>
              </tr>
            </thead>
            <tbody>
              {findings.ai_findings.map((f, i) => (
                <tr key={`${f.type}/${i}`}>
                  <td className={s.type}>{t(`aiTypes.${f.type}`)}</td>
                  <td>
                    {f.detail}
                    <div className={s.trace}>
                      {t("trace", { model: f.model, prompt: f.prompt.slice(0, 12), created: f.created })}
                    </div>
                  </td>
                  <td>
                    <Citations cites={f.citations} runId={runId} />
                  </td>
                  <td>
                    {decided ? (
                      <DecisionCell
                        proposal={ais.get(i)}
                        runId={runId}
                        screen="findings"
                        access={decisions.access}
                      />
                    ) : (
                      <span className={s.pending}>{t(`actions.${f.reviewer_action}`)}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </section>

      <section aria-labelledby="missing-documents">
        <SectionHead id="missing-documents" title={t("missing")} count={findings.missing_documents.length} note={t("missingNote")} />
        {findings.missing_documents.length === 0 ? (
          <EmptyState title={t("none")} />
        ) : (
          <div className={tbl.wrap}>
          <table className={tbl.table}>
            <thead>
              <tr>
                <th>{t("document")}</th>
                <th>{t("type")}</th>
                <th>{t("stage")}</th>
                <th>{t("required")}</th>
              </tr>
            </thead>
            <tbody>
              {findings.missing_documents.map((d) => (
                <tr key={d.doc_id}>
                  <td className={tbl.id}>{d.doc_id}</td>
                  <td>{d.type}</td>
                  <td>{d.stage}</td>
                  <td>
                    <CiteLink runId={runId} cite={d.citation} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </section>
    </>
  );
}
