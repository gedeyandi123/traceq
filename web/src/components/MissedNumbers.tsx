import { useTranslations } from "next-intl";

import type { MissedNumberView, ProtocolUrs } from "@/api/client";
import { documentHref } from "@/api/client";
import { formatWhen } from "./formatWhen";
import { Button, SectionHeading } from "./ui/ui";

import s from "./AssembledProtocolView.module.css";

type T = ReturnType<typeof useTranslations<"protocol">>;
type Action = (formData: FormData) => void | Promise<void>;

const KINDS = ["not_a_requirement", "not_tested_here"] as const;

function PageLink({ runId, doc, rev, page, t }: { runId: string; doc: string; rev: number; page: number; t: T }) {
  return (
    <a href={documentHref(runId, { doc, rev, page, quote: "" })} target="_blank" rel="noreferrer">
      {t("missed.page", { page })}
    </a>
  );
}

/** The answer form of a missed number: one of the two kinds and a written justification. No
 * Reason for Change: a later answer replaces the earlier, which is kept. */
function AnswerForm({
  t,
  u,
  m,
  runId,
  protocolId,
  answer,
}: {
  t: T;
  u: ProtocolUrs;
  m: MissedNumberView;
  runId: string;
  protocolId: number;
  answer: Action;
}) {
  const label = t(m.disposition ? "missed.change" : "missed.answer", { number: m.number });
  return (
    <details className={s.writeFold}>
      <summary>{label}</summary>
      <form action={answer} className={s.stepForm} aria-label={label}>
        <input type="hidden" name="run_id" value={runId} />
        <input type="hidden" name="protocol_id" value={protocolId} />
        <input type="hidden" name="doc" value={u.doc} />
        <input type="hidden" name="rev" value={u.rev} />
        <input type="hidden" name="number" value={m.number} />
        <label className={s.field}>
          {t("missed.kind")}
          <select name="kind" required defaultValue={m.disposition?.kind ?? ""}>
            <option value="">{t("missed.chooseKind")}</option>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {t(`missed.kinds.${k}`)}
              </option>
            ))}
          </select>
        </label>
        <label className={s.field}>
          {t("missed.justification")}
          <textarea name="justification" required defaultValue={m.disposition?.justification ?? ""} />
        </label>
        <Button type="submit" variant="soft">
          {t("missed.save")}
        </Button>
      </form>
    </details>
  );
}

function Missed({
  t,
  u,
  m,
  runId,
  protocolId,
  answer,
}: {
  t: T;
  u: ProtocolUrs;
  m: MissedNumberView;
  runId: string;
  protocolId: number;
  answer: Action | null;
}) {
  const when = useTranslations("decisions");
  const a = m.disposition;
  return (
    <li data-testid={`${u.doc}/${u.rev}/${m.number}`} className={m.blocking ? s.blockingRow : undefined}>
      <div>
        <strong>{m.number}</strong> <PageLink runId={runId} doc={u.doc} rev={u.rev} page={m.page} t={t} />
      </div>
      {a === null ? (
        <div className={s.blocking}>{t("missed.blocking")}</div>
      ) : (
        <div>
          <strong className={s.kind}>{t(`missed.kinds.${a.kind}`)}</strong>
          <div className={s.reason}>{a.justification}</div>
        </div>
      )}
      {m.dispositions.length > 0 && (
        <details className={s.versions}>
          <summary>{t("missed.history", { count: m.dispositions.length })}</summary>
          <ol>
            {m.dispositions.map((v) => (
              <li key={v.id}>
                <div>
                  {t("missed.answeredBy", { version: v.version, name: v.name, when: formatWhen(when, v.at) })}
                </div>
                <div className={s.muted}>
                  {t(`missed.kinds.${v.kind}`)} · {v.justification}
                </div>
              </li>
            ))}
          </ol>
        </details>
      )}
      {answer !== null && <AnswerForm t={t} u={u} m={m} runId={runId} protocolId={protocolId} answer={answer} />}
    </li>
  );
}

/** The printed requirement numbers the run missed, per URS of its completeness check, each
 * with its page, its answer in force and every earlier one, and the answer form for the
 * deciding role; then the URS text no requirement quotes, shown and never answered (spec #247,
 * "Missed requirement numbers"). `urs` `null`: the completeness check did not run. */
export function MissedNumbers({
  t,
  urs,
  runId,
  protocolId,
  answer,
}: {
  t: T;
  urs: readonly ProtocolUrs[] | null;
  runId: string;
  protocolId: number;
  /** The answer form's server action, for the deciding role; `null` for any other viewer. */
  answer: Action | null;
}) {
  const all = (urs ?? []).flatMap((u) => u.missed);
  const unanswered = all.filter((m) => m.blocking).length;
  const unquoted = (urs ?? []).reduce((n, u) => n + u.unquoted.length, 0);
  return (
    <>
      <section className={s.section} aria-labelledby="protocol-missed">
        <SectionHeading id="protocol-missed" title={t("missed.title")} count={all.length} note={t("missed.note")} />
        {urs === null ? (
          <p className={s.muted}>{t("missed.notRun")}</p>
        ) : (
          <>
            {unanswered > 0 && <p className={s.blocking}>{t("missed.unanswered", { count: unanswered })}</p>}
            {urs.map((u) => (
              <section key={`${u.doc}/${u.rev}`} aria-label={t("missed.urs", { doc: u.doc, rev: u.rev })}>
                <h3>{t("missed.urs", { doc: u.doc, rev: u.rev })}</h3>
                {u.numbers === "not_applicable" ? (
                  <p className={s.muted}>{t("missed.notApplicable")}</p>
                ) : u.missed.length === 0 ? (
                  <p className={s.muted}>{t("missed.noneMissed")}</p>
                ) : (
                  <ul className={s.list}>
                    {u.missed.map((m) => (
                      <Missed key={m.number} t={t} u={u} m={m} runId={runId} protocolId={protocolId} answer={answer} />
                    ))}
                  </ul>
                )}
              </section>
            ))}
          </>
        )}
      </section>
      {urs !== null && (
        <section className={s.section} aria-labelledby="protocol-unquoted">
          <SectionHeading id="protocol-unquoted" title={t("unquoted.title")} count={unquoted} note={t("unquoted.note")} />
          {unquoted === 0 ? (
            <p className={s.muted}>{t("unquoted.none")}</p>
          ) : (
            urs
              .filter((u) => u.unquoted.length > 0)
              .map((u) => (
                <details key={`${u.doc}/${u.rev}`} className={s.versions}>
                  <summary>{t("unquoted.show", { doc: u.doc, rev: u.rev, count: u.unquoted.length })}</summary>
                  <ul className={s.list}>
                    {u.unquoted.map((x) => (
                      <li key={`${x.page}/${x.text}`}>
                        <PageLink runId={runId} doc={u.doc} rev={u.rev} page={x.page} t={t} />
                        <pre>{x.text}</pre>
                      </li>
                    ))}
                  </ul>
                </details>
              ))
          )}
        </section>
      )}
    </>
  );
}
