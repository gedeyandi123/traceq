"use client";

import { AlertCircle, ArrowRight, History as HistoryIcon, PlayCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useActionState } from "react";

import type { ExecutionRowView, ExecutionView, ProtocolView } from "@/api/client";
import type { ExecutionActionState } from "@/execution/actions";
import { formatWhen } from "./formatWhen";
import { formatValue } from "./MatrixTable";
import { PdfCitationButton } from "./ui/PdfCitationModal";
import { ExecutionStatusBadge } from "./ui/StatusBadge";
import { SubmitButton } from "./ui/SubmitButton";
import { EmptyState } from "./ui/ui";

type T = ReturnType<typeof useTranslations<"execution">>;
type MatrixT = ReturnType<typeof useTranslations<"matrix">>;
type WhenT = ReturnType<typeof useTranslations<"decisions">>;

const INITIAL_STATE: ExecutionActionState = { ok: true };

const LIMITS = [
  "evidenceText",
  "noWitness",
  "retestNoPermission",
  "noRounding",
  "typedCalibration",
  "liveOnly",
  "oneExecution",
  "combined",
  "notSignature",
] as const;

function Limits({ t }: { t: T }) {
  return (
    <aside
      aria-labelledby="execution-limits"
      className="space-y-2 rounded-lg border border-border bg-sunken px-4 py-3 text-xs text-ink-muted"
    >
      <h2 id="execution-limits" className="m-0 text-xs font-bold tracking-wide text-ink uppercase">
        {t("limitsTitle")}
      </h2>
      <ul className="m-0 list-disc space-y-1 pl-4">
        {LIMITS.map((k) => (
          <li key={k}>{t(`limits.${k}`)}</li>
        ))}
      </ul>
    </aside>
  );
}

function ExecutionRow({
  t,
  m,
  row,
  runId,
}: {
  t: T;
  m: MatrixT;
  row: ExecutionRowView;
  runId: string;
}) {
  const step = row.test_step;
  return (
    <tr data-testid={`exec-row-${row.requirement}`} className="border-b border-border last:border-b-0">
      <th scope="row" className="max-w-[260px] px-3 py-2.5 text-left align-top font-normal">
        <div className="font-mono text-xs font-semibold text-ink tabular-nums">{row.requirement}</div>
        <div className="mt-0.5 text-xs text-ink-muted">{row.text}</div>
        <div className="mt-1">
          <PdfCitationButton runId={runId} cite={row.source} compact />
        </div>
      </th>

      <td className="px-3 py-2.5 align-top whitespace-nowrap">
        <span className="inline-flex rounded border border-border bg-sunken px-2 py-0.5 text-[11px] font-semibold text-ink">
          {t(`kinds.${row.kind}`)}
        </span>
      </td>

      <td className="max-w-[400px] px-3 py-2.5 align-top">
        {row.kind === "vendor_reference" ? (
          <div className="space-y-1.5">
            <ul className="m-0 list-disc space-y-0.5 pl-4 text-xs text-ink tabular-nums">
              {row.evidence.map((e) => (
                <li key={`${e.doc}/${e.rev}/${e.step}`}>
                  {t("evidenceStep", { doc: e.doc, rev: e.rev, step: e.step })}
                </li>
              ))}
            </ul>
            <p className="m-0 text-[11px] text-ink-muted">{t("vendorNoControls")}</p>
          </div>
        ) : (
          step && (
            <dl className="m-0 space-y-1 text-xs">
              <div>
                <dt className="inline font-semibold text-ink-muted">{t("description")}: </dt>
                <dd className="m-0 inline text-ink">{step.description}</dd>
              </div>
              <div>
                <dt className="inline font-semibold text-ink-muted">{t("method")}: </dt>
                <dd className="m-0 inline text-ink">{step.method}</dd>
              </div>
              <div>
                <dt className="inline font-semibold text-ink-muted">{t("instrument")}: </dt>
                <dd className="m-0 inline text-ink">{step.instrument ?? t("noInstrument")}</dd>
              </div>
            </dl>
          )
        )}
      </td>

      <td className="px-3 py-2.5 align-top text-xs font-medium text-ink tabular-nums">
        {step ? formatValue(m, step.acceptance) : "—"}
      </td>
    </tr>
  );
}

export function ExecutionViewPanel({
  execution,
  protocol,
  runId,
  startAction,
}: {
  execution: ExecutionView | null;
  protocol: ProtocolView | null;
  runId: string;
  startAction:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
}) {
  const t = useTranslations("execution");
  const m = useTranslations("matrix");
  const when: WhenT = useTranslations("decisions");

  const [state, formAction] = useActionState(
    startAction ?? (async () => INITIAL_STATE),
    INITIAL_STATE,
  );

  const protocolHref = `/runs/${encodeURIComponent(runId)}/protocol`;

  return (
    <div className="space-y-4">
      {!state.ok && state.error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-fail-edge bg-fail-soft px-3.5 py-2.5 text-xs text-fail"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{t(`errors.${state.error}`)}</span>
        </div>
      )}

      {execution === null ? (
        protocol === null || protocol.status !== "approved" ? (
          <EmptyState title={t("noApprovedProtocol")}>
            <p className="m-0 mb-3 text-xs text-ink-muted">{t("noApprovedProtocolBody")}</p>
            <Link
              href={protocolHref}
              className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent no-underline hover:bg-accent-hover"
            >
              <span>{t("toProtocol")}</span>
              <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
            </Link>
          </EmptyState>
        ) : (
          <EmptyState title={t("notStarted")}>
            <p className="m-0 mb-3 text-xs text-ink-muted">
              {t("notStartedBody", { protocolId: protocol.id })}
            </p>
            {startAction !== null ? (
              <form action={formAction}>
                <input type="hidden" name="protocol_id" value={protocol.id} />
                <SubmitButton variant="primary">
                  <PlayCircle className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{t("start")}</span>
                </SubmitButton>
              </form>
            ) : (
              <p className="m-0 text-xs text-ink-muted">{t("notStartedReadOnly")}</p>
            )}
          </EmptyState>
        )
      ) : (
        <>
          <section
            aria-labelledby="execution-status"
            className="space-y-3 rounded-lg border border-border bg-surface p-4 shadow-xs"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2.5">
                  <h2 id="execution-status" className="m-0 text-base font-bold text-ink tabular-nums">
                    {t("status", { id: execution.id })}
                  </h2>
                  <ExecutionStatusBadge status={execution.status} />
                </div>
                <p className="m-0 text-xs text-ink-muted tabular-nums">
                  {t("protocolRef", {
                    protocolId: execution.protocol_id,
                    runId: execution.run_id,
                    eventId: execution.submission_event_id,
                  })}
                </p>
              </div>
            </div>

            <div className="space-y-2 border-t border-border pt-3">
              <h3 className="m-0 flex items-center gap-2 text-xs font-bold text-ink">
                <HistoryIcon className="h-3.5 w-3.5 text-ink-muted" aria-hidden="true" />
                <span>{t("history")}</span>
              </h3>
              <ol className="m-0 list-decimal space-y-1 pl-5 text-xs text-ink tabular-nums">
                {execution.events.map((e) => (
                  <li key={e.id}>
                    {t(`events.${e.event}`, { name: e.name, when: formatWhen(when, e.at) })}
                  </li>
                ))}
              </ol>
            </div>
          </section>

          <section aria-labelledby="execution-rows" className="space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 id="execution-rows" className="m-0 text-sm font-bold text-ink tabular-nums">
                {t("rows", { count: execution.rows.length })}
              </h2>
              <span className="text-xs text-ink-muted">{t("rowsNote")}</span>
            </div>

            <div className="overflow-x-auto rounded-lg border border-border bg-surface shadow-xs">
              <table className="w-full border-collapse text-left text-xs">
                <thead className="border-b border-border bg-sunken text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
                  <tr>
                    <th scope="col" className="px-3 py-2">
                      {t("colRequirement")}
                    </th>
                    <th scope="col" className="px-3 py-2">
                      {t("colKind")}
                    </th>
                    <th scope="col" className="px-3 py-2">
                      {t("colDetail")}
                    </th>
                    <th scope="col" className="px-3 py-2">
                      {t("colAcceptance")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {execution.rows.map((r) => (
                    <ExecutionRow key={r.requirement} t={t} m={m} row={r} runId={runId} />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      <Limits t={t} />
    </div>
  );
}
