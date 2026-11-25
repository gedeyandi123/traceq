"use client";

import { Lock } from "lucide-react";
import { useTranslations } from "next-intl";

import type { FrozenDecision, FrozenRow, SubmissionView } from "@/api/client";
import { formatWhen } from "./formatWhen";
import { formatValue } from "./MatrixTable";
import { CopyHashButton } from "./ui/CopyHashButton";
import { PdfCitationButton } from "./ui/PdfCitationModal";
import { CoverageStatusBadge } from "./ui/StatusBadge";

type T = ReturnType<typeof useTranslations<"protocol">>;
type MatrixT = ReturnType<typeof useTranslations<"matrix">>;
type WhenT = ReturnType<typeof useTranslations<"decisions">>;

function By({ t, when, d }: { t: T; when: WhenT; d: FrozenDecision }) {
  return (
    <div className="mt-1 text-[11px] text-ink-muted">
      <div>{t(`copy.decisions.${d.decision}`, { name: d.author.name, when: formatWhen(when, d.at) })}</div>
      {d.reason && <div className="italic">{d.reason}</div>}
    </div>
  );
}

function Row({
  t,
  m,
  when,
  row,
  runId,
}: {
  t: T;
  m: MatrixT;
  when: WhenT;
  row: FrozenRow;
  runId: string;
}) {
  const step = row.test_step;
  return (
    <tr data-testid={`copy-${row.requirement}`} className="border-b border-border last:border-b-0">
      <th scope="row" className="max-w-[260px] px-3 py-2.5 align-top font-normal">
        <div className="font-mono text-xs font-semibold text-ink tabular-nums">{row.requirement}</div>
        <div className="mt-0.5 text-xs text-ink-muted">{row.text}</div>
        <div className="mt-1">
          <PdfCitationButton runId={runId} cite={row.source} compact />
        </div>
      </th>

      <td className="px-3 py-2.5 align-top">
        <CoverageStatusBadge coverage={row.coverage.coverage_class} size="xs" />
        <By t={t} when={when} d={row.coverage.decision} />
      </td>

      <td className="max-w-[360px] px-3 py-2.5 align-top">
        <strong className="text-xs font-semibold text-ink">{t(`kinds.${row.kind}`)}</strong>
        {row.kind === "vendor_reference" && (
          <ul className="m-0 mt-1 list-disc space-y-0.5 pl-4 text-[11px] text-ink-muted tabular-nums">
            {row.evidence.map((e) => (
              <li key={`${e.doc}/${e.rev}/${e.step}`}>
                {t("evidenceStep", { doc: e.doc, rev: e.rev, step: e.step })}
              </li>
            ))}
          </ul>
        )}
        {step && (
          <div className="mt-1.5 space-y-1 rounded border border-border bg-sunken p-2 text-[11px]">
            <div className="font-semibold text-ink">
              {step.origin === "written"
                ? t(step.proposal_id === null ? "writtenStep" : "editedStep", {
                    version: step.version ?? 1,
                  })
                : t("fromDraft")}
            </div>
            <dl className="m-0 space-y-1">
              <dt className="font-semibold text-ink-muted">{t("description")}</dt>
              <dd className="m-0 text-ink">{step.description}</dd>
              <dt className="font-semibold text-ink-muted">{t("method")}</dt>
              <dd className="m-0 text-ink">{step.method}</dd>
              <dt className="font-semibold text-ink-muted">{t("instrument")}</dt>
              <dd className="m-0 text-ink">{step.instrument ?? t("noInstrument")}</dd>
              <dt className="font-semibold text-ink-muted">{t("ac")}</dt>
              <dd className="m-0 font-medium text-ink tabular-nums">
                {formatValue(m, step.acceptance)}
              </dd>
            </dl>
          </div>
        )}
        {row.written.length > 0 && (
          <ul
            className="m-0 mt-1.5 list-disc space-y-0.5 pl-4 text-[11px] text-ink-muted"
            aria-label={t("versions.title", { count: row.written.length })}
          >
            {row.written.map((v) => (
              <li key={v.version}>
                {t(v.removed ? "versions.removed" : "versions.written", {
                  version: v.version,
                  name: v.author.name,
                  when: formatWhen(when, v.at),
                })}
              </li>
            ))}
          </ul>
        )}
      </td>

      <td className="px-3 py-2.5 align-top">
        {row.drafts.length === 0 ? (
          <span className="text-[11px] text-ink-muted">{t("noDrafts")}</span>
        ) : (
          <div className="space-y-2">
            {row.drafts.map((d) => (
              <div key={d.proposal_id} className="rounded border border-border bg-sunken p-2 text-[11px]">
                <div className="font-mono font-semibold text-ink">{d.draft_id}</div>
                {d.decision ? (
                  <By t={t} when={when} d={d.decision} />
                ) : (
                  <div className="text-ink-muted">{t("copy.undecidedDraft")}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </td>
    </tr>
  );
}

/** The frozen copy of a submitted Protocol: what the Approver reads, shown instead of live rows. */
export function FrozenCopy({
  t,
  submission,
  earlier,
  runId,
}: {
  t: T;
  submission: SubmissionView;
  earlier: readonly SubmissionView[];
  runId: string;
}) {
  const m = useTranslations("matrix");
  const when = useTranslations("decisions");
  const ui = useTranslations("ui");
  const copy = submission.frozen_copy;
  const missed = (copy.urs ?? []).flatMap((u) =>
    u.missed.map((n) => ({ ...n, doc: u.doc, rev: u.rev })),
  );
  const unquoted = (copy.urs ?? []).flatMap((u) =>
    u.unquoted.map((x) => ({ ...x, doc: u.doc, rev: u.rev })),
  );

  return (
    <section aria-labelledby="protocol-copy" className="space-y-4">
      <div className="rounded-lg border border-border bg-surface p-4 shadow-xs">
        <div className="flex flex-wrap items-center gap-2">
          <Lock className="h-4 w-4 text-accent" aria-hidden="true" />
          <h2 id="protocol-copy" className="m-0 text-sm font-bold text-ink">
            {t("copy.title")}
          </h2>
          <span className="rounded-full bg-sunken px-2 py-0.5 text-xs font-semibold text-ink-muted tabular-nums">
            {copy.rows.length}
          </span>
        </div>
        <p className="mt-1 mb-3 text-xs text-ink-muted">{t("copy.note")}</p>
        <dl className="m-0 grid grid-cols-1 gap-2 rounded-md border border-border bg-sunken p-3 text-xs sm:grid-cols-[120px_1fr]">
          <dt className="font-semibold text-ink-muted">{t("copy.hash")}</dt>
          <dd className="m-0 flex min-w-0 flex-wrap items-center gap-2">
            <code data-testid="copy-hash" className="font-mono text-xs break-all text-ink tabular-nums">
              {submission.hash}
            </code>
            <CopyHashButton
              value={submission.hash}
              copyLabel={ui("copyHash")}
              copiedLabel={ui("copied")}
            />
          </dd>
          <dt className="font-semibold text-ink-muted">{t("copy.preparer")}</dt>
          <dd className="m-0 text-ink tabular-nums">
            {t("copy.submittedBy", {
              name: copy.preparer.name,
              when: formatWhen(when, submission.at),
            })}
          </dd>
        </dl>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border bg-surface shadow-xs">
        <table className="w-full border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-border bg-sunken/70 text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
              <th scope="col" className="px-3 py-2">
                {t("requirement")}
              </th>
              <th scope="col" className="px-3 py-2">
                {t("coverage")}
              </th>
              <th scope="col" className="px-3 py-2">
                {t("content")}
              </th>
              <th scope="col" className="px-3 py-2">
                {t("drafts")}
              </th>
            </tr>
          </thead>
          <tbody>
            {copy.rows.map((r) => (
              <Row key={r.requirement} t={t} m={m} when={when} row={r} runId={runId} />
            ))}
          </tbody>
        </table>
      </div>

      {missed.length > 0 && (
        <section
          aria-label={t("missed.title")}
          className="space-y-2.5 rounded-lg border border-border bg-surface p-4"
        >
          <h3 className="m-0 text-sm font-bold text-ink">{t("missed.title")}</h3>
          <ul className="m-0 list-none space-y-2.5 p-0 text-xs">
            {missed.map((n) => (
              <li
                key={`${n.doc}/${n.rev}/${n.number}`}
                className="space-y-1.5 rounded border border-border bg-canvas p-3"
              >
                <div className="font-semibold text-ink">
                  {t("copy.missed", {
                    number: n.number,
                    doc: n.doc,
                    rev: n.rev,
                    kind: t(`copy.missedKinds.${n.disposition.kind}`),
                    name: n.disposition.author.name,
                  })}
                </div>
                <div className="text-ink-muted italic">{n.disposition.justification}</div>
                {n.dispositions.length > 1 && (
                  <ol
                    aria-label={t("missed.history", { count: n.dispositions.length })}
                    className="m-0 list-decimal space-y-1 pl-5"
                  >
                    {n.dispositions.map((v) => (
                      <li key={v.version} className="text-ink">
                        <div>
                          {t("missed.answeredBy", {
                            version: v.version,
                            name: v.author.name,
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
              </li>
            ))}
          </ul>
        </section>
      )}

      {unquoted.length > 0 && (
        <section
          aria-label={t("unquoted.title")}
          className="space-y-2.5 rounded-lg border border-border bg-surface p-4"
        >
          <h3 className="m-0 text-sm font-bold text-ink">{t("unquoted.title")}</h3>
          <ul className="m-0 list-none space-y-1.5 p-0 text-xs">
            {unquoted.map((x, i) => (
              <li
                key={`${x.doc}/${x.rev}/${x.page}/${i}`}
                className="rounded border border-border bg-sunken p-2.5 text-ink-muted tabular-nums"
              >
                {x.doc} rev {x.rev}, {t("missed.page", { page: x.page })}: {x.text}
              </li>
            ))}
          </ul>
        </section>
      )}

      {earlier.length > 0 && <EarlierCopies t={t} earlier={earlier} />}
    </section>
  );
}

/** The earlier submissions of a Protocol, each with its hash and the return that followed it. */
export function EarlierCopies({
  t,
  earlier,
  headingLevel = "h3",
}: {
  t: T;
  earlier: readonly SubmissionView[];
  headingLevel?: "h2" | "h3";
}) {
  const when = useTranslations("decisions");
  const Heading = headingLevel;
  return (
    <section
      aria-label={t("copy.earlier")}
      className="space-y-2.5 rounded-lg border border-border bg-surface p-4"
    >
      <Heading className="m-0 text-sm font-bold text-ink">{t("copy.earlier")}</Heading>
      <ul className="m-0 list-none space-y-2 p-0 text-xs">
        {earlier.map((e) => (
          <li
            key={e.event_id}
            data-testid={`earlier-${e.event_id}`}
            className="space-y-1 rounded border border-border bg-sunken p-3"
          >
            <div className="text-ink tabular-nums">
              {t("copy.earlierItem", { when: formatWhen(when, e.at) })}{" "}
              <code className="font-mono text-xs break-all">{e.hash}</code>
            </div>
            {e.outcome?.event === "returned" && (
              <div className="space-y-0.5 text-ink-muted">
                <div>
                  {t("copy.returnedBy", {
                    name: e.outcome.name,
                    when: formatWhen(when, e.outcome.at),
                  })}
                </div>
                {e.outcome.reason && <div className="italic">{e.outcome.reason}</div>}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
