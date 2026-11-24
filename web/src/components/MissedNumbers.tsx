"use client";

import { AlertCircle, AlertTriangle, CheckCircle2, ChevronDown } from "lucide-react";
import { useTranslations } from "next-intl";
import { useActionState, useState } from "react";

import type { MissedNumberView, ProtocolUrs } from "@/api/client";
import type { ProtocolFormActionState } from "@/protocol/actions";
import { formatWhen } from "./formatWhen";
import { PdfCitationButton } from "./ui/PdfCitationModal";

type T = ReturnType<typeof useTranslations<"protocol">>;
type Action = (formData: FormData) => void | Promise<void>;
type InlineAction = (
  prevState: ProtocolFormActionState,
  formData: FormData,
) => Promise<ProtocolFormActionState>;

const KINDS = ["not_a_requirement", "not_tested_here"] as const;

const INPUT_CLASS =
  "w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none";

function wrapLegacyAction(action: Action): InlineAction {
  return async (_prev, formData) => {
    await action(formData);
    return { ok: true, submittedAt: Date.now() };
  };
}

/** The answer form of a missed number: one of the two kinds and a written justification. */
function AnswerForm({
  t,
  u,
  m,
  runId,
  protocolId,
  answer,
  answerInline,
}: {
  t: T;
  u: ProtocolUrs;
  m: MissedNumberView;
  runId: string;
  protocolId: number;
  answer: Action;
  answerInline?: InlineAction;
}) {
  const [open, setOpen] = useState(m.blocking);
  const actionFn = answerInline ?? wrapLegacyAction(answer);
  const [state, formAction, isPending] = useActionState(actionFn, { ok: true });
  const label = t(m.disposition ? "missed.change" : "missed.answer", { number: m.number });

  return (
    <div className="pt-1">
      <button
        type="button"
        data-tw=""
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border-strong bg-surface px-2.5 py-1 text-xs font-semibold text-ink hover:bg-sunken"
      >
        <span>{label}</span>
        <ChevronDown
          className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div className="mt-2 space-y-2.5 rounded-md border border-border bg-canvas p-3">
          {!state.ok && state.error && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-fail-edge bg-fail-soft px-3 py-2 text-xs text-fail"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{t(`errors.${state.error}`)}</span>
            </div>
          )}
          {state.ok && state.submittedAt && (
            <div
              role="status"
              className="flex items-center gap-2 rounded-md border border-pass-edge bg-pass-soft px-3 py-2 text-xs text-pass"
            >
              <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{t("missed.saved")}</span>
            </div>
          )}
          <form
            key={`${u.doc}/${u.rev}/${m.number}-${state.submittedAt ?? 0}`}
            action={formAction}
            className="space-y-2.5"
            aria-label={label}
          >
            <input type="hidden" name="run_id" value={runId} />
            <input type="hidden" name="protocol_id" value={protocolId} />
            <input type="hidden" name="doc" value={u.doc} />
            <input type="hidden" name="rev" value={u.rev} />
            <input type="hidden" name="number" value={m.number} />
            <label className="block space-y-1 text-xs font-medium text-ink">
              <span>{t("missed.kind")}</span>
              <select
                name="kind"
                required
                defaultValue={m.disposition?.kind ?? ""}
                className={INPUT_CLASS}
              >
                <option value="">{t("missed.chooseKind")}</option>
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {t(`missed.kinds.${k}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="block space-y-1 text-xs font-medium text-ink">
              <span>{t("missed.justification")}</span>
              <textarea
                name="justification"
                required
                rows={2}
                defaultValue={m.disposition?.justification ?? ""}
                className={INPUT_CLASS}
              />
            </label>
            <button
              type="submit"
              data-tw=""
              disabled={isPending}
              className="inline-flex cursor-pointer items-center justify-center rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
            >
              {t("missed.save")}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

function Missed({
  t,
  u,
  m,
  runId,
  protocolId,
  answer,
  answerInline,
}: {
  t: T;
  u: ProtocolUrs;
  m: MissedNumberView;
  runId: string;
  protocolId: number;
  answer: Action | null;
  answerInline?: InlineAction;
}) {
  const when = useTranslations("decisions");
  const [historyOpen, setHistoryOpen] = useState(false);
  const a = m.disposition;

  return (
    <li
      data-testid={`${u.doc}/${u.rev}/${m.number}`}
      className={`space-y-2 rounded-lg border p-3.5 text-xs ${
        m.blocking ? "border-fail-edge bg-fail-soft/20" : "border-border bg-surface"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <strong className="font-mono text-sm font-bold text-ink tabular-nums">{m.number}</strong>
          <PdfCitationButton
            runId={runId}
            cite={{ doc: u.doc, rev: u.rev, page: m.page, quote: "" }}
            label={t("missed.page", { page: m.page })}
            compact
          />
        </div>
        {a === null ? (
          <span className="inline-flex items-center gap-1 rounded-full border border-fail-edge bg-fail-soft px-2 py-0.5 text-[11px] font-semibold text-fail">
            <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
            <span>{t("missed.blocking")}</span>
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full border border-pass-edge bg-pass-soft px-2 py-0.5 text-[11px] font-semibold text-pass">
            <CheckCircle2 className="h-3 w-3 shrink-0" aria-hidden="true" />
            <span>{t(`missed.kinds.${a.kind}`)}</span>
          </span>
        )}
      </div>

      {a !== null && (
        <div className="rounded border border-border bg-sunken px-2.5 py-1.5 text-ink">
          {a.justification}
        </div>
      )}

      {m.dispositions.length > 0 && (
        <div className="space-y-1.5">
          <button
            type="button"
            data-tw=""
            aria-expanded={historyOpen}
            onClick={() => setHistoryOpen((o) => !o)}
            className="inline-flex cursor-pointer items-center gap-1 text-xs font-semibold text-ink-muted hover:text-ink"
          >
            <span>{t("missed.history", { count: m.dispositions.length })}</span>
            <ChevronDown
              className={`h-3.5 w-3.5 transition-transform ${historyOpen ? "rotate-180" : ""}`}
              aria-hidden="true"
            />
          </button>
          {historyOpen && (
            <ol className="m-0 list-decimal space-y-1.5 pl-5">
              {m.dispositions.map((v) => (
                <li key={v.id} className="text-ink">
                  <div>
                    {t("missed.answeredBy", {
                      version: v.version,
                      name: v.name,
                      when: formatWhen(when, v.at),
                    })}
                  </div>
                  <div className="text-ink-muted">
                    {t(`missed.kinds.${v.kind}`)} · {v.justification}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}

      {answer !== null && (
        <AnswerForm
          t={t}
          u={u}
          m={m}
          runId={runId}
          protocolId={protocolId}
          answer={answer}
          answerInline={answerInline}
        />
      )}
    </li>
  );
}

/** The printed requirement numbers the run missed, per URS of its completeness check,
 * plus the URS text no requirement quotes. */
export function MissedNumbers({
  t,
  urs,
  runId,
  protocolId,
  answer,
  answerInline,
}: {
  t: T;
  urs: readonly ProtocolUrs[] | null;
  runId: string;
  protocolId: number;
  answer: Action | null;
  answerInline?: InlineAction;
}) {
  const [unquotedOpen, setUnquotedOpen] = useState<Record<string, boolean>>({});
  const all = (urs ?? []).flatMap((u) => u.missed);
  const unanswered = all.filter((m) => m.blocking).length;
  const unquoted = (urs ?? []).reduce((n, u) => n + u.unquoted.length, 0);

  return (
    <div className="space-y-6">
      <section aria-labelledby="protocol-missed" className="space-y-3">
        <div>
          <h2 id="protocol-missed" className="m-0 flex items-center gap-2 text-sm font-bold text-ink">
            <span>{t("missed.title")}</span>
            <span className="rounded-full bg-sunken px-2 py-0.5 text-xs font-semibold text-ink-muted tabular-nums">
              {all.length}
            </span>
          </h2>
          <p className="mt-1 mb-0 text-xs text-ink-muted">{t("missed.note")}</p>
        </div>

        {urs === null ? (
          <p className="m-0 rounded-lg border border-border bg-surface p-3.5 text-xs text-ink-muted">
            {t("missed.notRun")}
          </p>
        ) : (
          <div className="space-y-4">
            {unanswered > 0 && (
              <div className="flex items-center gap-2 rounded-md border border-fail-edge bg-fail-soft px-3 py-2 text-xs font-semibold text-fail">
                <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span>{t("missed.unanswered", { count: unanswered })}</span>
              </div>
            )}
            {urs.map((u) => (
              <section
                key={`${u.doc}/${u.rev}`}
                aria-label={t("missed.urs", { doc: u.doc, rev: u.rev })}
                className="space-y-2"
              >
                <h3 className="m-0 text-xs font-bold tracking-wide text-ink uppercase tabular-nums">
                  {t("missed.urs", { doc: u.doc, rev: u.rev })}
                </h3>
                {u.numbers === "not_applicable" ? (
                  <p className="m-0 text-xs text-ink-muted">{t("missed.notApplicable")}</p>
                ) : u.missed.length === 0 ? (
                  <p className="m-0 text-xs text-ink-muted">{t("missed.noneMissed")}</p>
                ) : (
                  <ul className="m-0 list-none space-y-2.5 p-0">
                    {u.missed.map((m) => (
                      <Missed
                        key={m.number}
                        t={t}
                        u={u}
                        m={m}
                        runId={runId}
                        protocolId={protocolId}
                        answer={answer}
                        answerInline={answerInline}
                      />
                    ))}
                  </ul>
                )}
              </section>
            ))}
          </div>
        )}
      </section>

      {urs !== null && (
        <section aria-labelledby="protocol-unquoted" className="space-y-3">
          <div>
            <h2
              id="protocol-unquoted"
              className="m-0 flex items-center gap-2 text-sm font-bold text-ink"
            >
              <span>{t("unquoted.title")}</span>
              <span className="rounded-full bg-sunken px-2 py-0.5 text-xs font-semibold text-ink-muted tabular-nums">
                {unquoted}
              </span>
            </h2>
            <p className="mt-1 mb-0 text-xs text-ink-muted">{t("unquoted.note")}</p>
          </div>
          {unquoted === 0 ? (
            <p className="m-0 text-xs text-ink-muted">{t("unquoted.none")}</p>
          ) : (
            <div className="space-y-2">
              {urs
                .filter((u) => u.unquoted.length > 0)
                .map((u) => {
                  const key = `${u.doc}/${u.rev}`;
                  const isOpen = unquotedOpen[key] ?? false;
                  return (
                    <div
                      key={key}
                      className="rounded-lg border border-border bg-surface p-3 text-xs"
                    >
                      <button
                        type="button"
                        data-tw=""
                        aria-expanded={isOpen}
                        onClick={() =>
                          setUnquotedOpen((prev) => ({ ...prev, [key]: !isOpen }))
                        }
                        className="flex w-full cursor-pointer items-center justify-between gap-2 text-left font-semibold text-ink"
                      >
                        <span>
                          {t("unquoted.show", {
                            doc: u.doc,
                            rev: u.rev,
                            count: u.unquoted.length,
                          })}
                        </span>
                        <ChevronDown
                          className={`h-3.5 w-3.5 text-ink-muted transition-transform ${isOpen ? "rotate-180" : ""}`}
                          aria-hidden="true"
                        />
                      </button>
                      {isOpen && (
                        <ul className="m-0 mt-2.5 list-none space-y-2 border-t border-border pt-2.5 p-0">
                          {u.unquoted.map((x) => (
                            <li
                              key={`${x.page}/${x.text}`}
                              className="space-y-1 rounded border border-border bg-canvas p-2.5"
                            >
                              <PdfCitationButton
                                runId={runId}
                                cite={{ doc: u.doc, rev: u.rev, page: x.page, quote: x.text }}
                                label={t("missed.page", { page: x.page })}
                                compact
                              />
                              <pre className="m-0 font-sans text-xs whitespace-pre-wrap text-ink">
                                {x.text}
                              </pre>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  );
                })}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
