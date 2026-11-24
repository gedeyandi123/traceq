import { useTranslations } from "next-intl";

import type { Cite, Findings, Proposal } from "@/api/client";
import { CiteLink } from "./CiteLink";
import { DecisionCell, DecisionNotice, DecisionTally } from "./Decisions";
import { formatWhen } from "./formatWhen";
import type { DecisionView } from "./Decisions";
import { cell, DataTable, EmptyState, HandoffBar, SectionHeading, SummaryLinks } from "./ui/ui";

import s from "./FindingsView.module.css";

function Citations({ cites, runId }: { cites: readonly Cite[]; runId: string }) {
  return (
    <ul className={s.citations}>
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
 * lacks, after a summary that links to each section. Every finding links to the page it cites. For an imported run each finding shows its
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
  const th = useTranslations("runHeader");
  const decided = decisions.proposals !== undefined;
  const checks = byPosition(decisions, "check");
  const ais = byPosition(decisions, "ai");
  // A document type the messages have no label for shows as it is, never as a missing key.
  const docType = (type: string) => (t.has(`docTypes.${type}`) ? t(`docTypes.${type}`) : type);
  return (
    <>
      <DecisionNotice view={decisions} />
      <div className={s.overview}>
        <SummaryLinks
          title={t("summaryTitle")}
          items={[
            { n: findings.check_findings.length, label: t("check"), href: "#check-findings" },
            { n: findings.ai_findings.length, label: t("ai"), href: "#ai-findings" },
            { n: findings.missing_documents.length, label: t("missing"), href: "#missing-documents" },
          ]}
        />
        <DecisionTally counts={decisions.counts} kinds={["check", "ai"]} />
      </div>
      <section className={s.section} aria-labelledby="check-findings">
        <SectionHeading
          id="check-findings"
          title={t("check")}
          count={findings.check_findings.length}
          note={t("checkNote")}
        />
        {findings.check_findings.length === 0 ? (
          <EmptyState title={t("none")} />
        ) : (
          <DataTable>
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
                  <td className={cell.id}>{f.doc}</td>
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
                    <td className={s.decision}>
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
          </DataTable>
        )}
      </section>

      <section className={s.section} aria-labelledby="ai-findings">
        <SectionHeading
          id="ai-findings"
          title={t("ai")}
          count={findings.ai_findings.length}
          note={t("aiNote")}
        />
        {findings.ai_findings.length === 0 ? (
          <EmptyState title={t("none")} />
        ) : (
          <DataTable>
            <thead>
              <tr>
                <th>{t("type")}</th>
                <th>{t("detail")}</th>
                <th>{t("citations")}</th>
                <th>{decided ? td("column") : t("status")}</th>
              </tr>
            </thead>
            <tbody>
              {findings.ai_findings.map((f, i) => (
                <tr key={`${f.type}/${i}`}>
                  <td className={s.type}>{t(`aiTypes.${f.type}`)}</td>
                  <td>
                    {f.detail}
                    <div className={s.trace}>
                      {t("trace", {
                        model: f.model,
                        prompt: f.prompt.slice(0, 12),
                        created: formatWhen(td, f.created),
                      })}
                    </div>
                  </td>
                  <td>
                    <Citations cites={f.citations} runId={runId} />
                  </td>
                  <td className={s.decision}>
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
          </DataTable>
        )}
      </section>

      <section className={s.section} aria-labelledby="missing-documents">
        <SectionHeading
          id="missing-documents"
          title={t("missing")}
          count={findings.missing_documents.length}
          note={t("missingNote")}
        />
        {findings.missing_documents.length === 0 ? (
          <EmptyState title={t("none")} />
        ) : (
          <DataTable>
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
                  <td className={cell.id}>{d.doc_id}</td>
                  <td>{docType(d.type)}</td>
                  <td>{d.stage}</td>
                  <td>
                    <CiteLink runId={runId} cite={d.citation} />
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        )}
      </section>
      <HandoffBar
        label={th("handoffTitle")}
        links={[{ href: `/runs/${encodeURIComponent(runId)}/protocol`, text: th("toProtocol") }]}
      />
    </>
  );
}
