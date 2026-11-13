import { useTranslations } from "next-intl";

import type { Cite, Findings } from "@/api/client";
import { CiteLink } from "./CiteLink";

function Citations({ cites, runId }: { cites: readonly Cite[]; runId: string }) {
  return (
    <ul className="citations">
      {cites.map((c) => (
        <li key={`${c.doc}/${c.rev}/${c.page}/${c.quote}`}>
          <CiteLink runId={runId} cite={c} />
        </li>
      ))}
    </ul>
  );
}

/** The Pre-review of a run: Check Findings (deterministic rules) and AI Findings (advisory,
 * pending a human) in separate sections, then the documents the VMP requires that the corpus
 * lacks. Every finding links to the page it cites. */
export function FindingsView({ findings, runId }: { findings: Findings; runId: string }) {
  const t = useTranslations("findings");
  return (
    <>
      <section className="findings findings-check" aria-labelledby="check-findings">
        <h2 id="check-findings">{t("check")}</h2>
        <p className="muted">{t("checkNote")}</p>
        {findings.check_findings.length === 0 ? (
          <p>{t("none")}</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>{t("type")}</th>
                <th>{t("document")}</th>
                <th>{t("detail")}</th>
                <th>{t("citations")}</th>
              </tr>
            </thead>
            <tbody>
              {findings.check_findings.map((f, i) => (
                <tr key={`${f.type}/${f.doc}/${i}`}>
                  <td>{t(`checkTypes.${f.type}`)}</td>
                  <td>{f.doc}</td>
                  <td>{f.detail}</td>
                  <td>
                    <Citations cites={f.citations} runId={runId} />
                    {f.rule && (
                      <div>
                        {t("rule")}: <CiteLink runId={runId} cite={f.rule} />
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="findings findings-ai" aria-labelledby="ai-findings">
        <h2 id="ai-findings">{t("ai")}</h2>
        <p className="muted">{t("aiNote")}</p>
        {findings.ai_findings.length === 0 ? (
          <p>{t("none")}</p>
        ) : (
          <table>
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
                  <td>{t(`aiTypes.${f.type}`)}</td>
                  <td>
                    {f.detail}
                    <div className="muted">
                      {t("trace", { model: f.model, prompt: f.prompt.slice(0, 12), created: f.created })}
                    </div>
                  </td>
                  <td>
                    <Citations cites={f.citations} runId={runId} />
                  </td>
                  <td>
                    <span className="pending">{t(`actions.${f.reviewer_action}`)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="findings findings-missing" aria-labelledby="missing-documents">
        <h2 id="missing-documents">{t("missing")}</h2>
        <p className="muted">{t("missingNote")}</p>
        {findings.missing_documents.length === 0 ? (
          <p>{t("none")}</p>
        ) : (
          <table>
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
                  <td>{d.doc_id}</td>
                  <td>{d.type}</td>
                  <td>{d.stage}</td>
                  <td>
                    <CiteLink runId={runId} cite={d.citation} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
