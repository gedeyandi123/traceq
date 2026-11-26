"use client";

import {
  AlertCircle,
  Award,
  CheckCircle2,
  Download,
  FileCheck2,
  GitBranch,
  Lock,
  ShieldCheck,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useActionState, useEffect, useState } from "react";

import type { ExecutionView, QualificationReportView } from "@/api/client";
import type { Session, SigningAuthState } from "@/auth/session";
import { ElectronicSignatureDialog } from "@/components/ElectronicSignatureDialog";
import { formatWhen } from "@/components/formatWhen";
import { SignatureBadge } from "@/components/SignatureBadge";
import { Alert } from "@/components/ui/Alert";
import { CopyHashButton } from "@/components/ui/CopyHashButton";
import { FIELD_BASE_CLASS, FieldTextarea } from "@/components/ui/FormControls";
import {
  DeviationStatusBadge,
  StageBadge,
  TechnicalConclusionBadge,
  VerdictBadge,
} from "@/components/ui/StatusBadge";
import { EmptyState, SectionHeading, Button } from "@/components/ui/ui";
import type { ApproveReportActionState, ReportError } from "@/report/actions";

export type ApproveReportAction = (
  prevState: ApproveReportActionState,
  formData: FormData,
) => Promise<ApproveReportActionState>;

function errorMessage(
  t: ReturnType<typeof useTranslations<"report">>,
  err?: ReportError,
  detail?: string,
): string {
  if (detail) return detail;
  if (!err) return "";
  return t(`errors.${err}`);
}

/** Qualification Report Workbench (`/runs/[runId]/report`, Step 7). */
export function QualificationReportWorkbench({
  runId,
  report,
  execution,
  session,
  signingAuth = { oidcMode: false, reauthAuthTime: null },
  initialReauthTarget = null,
  approveAction,
}: {
  runId: string;
  report: QualificationReportView;
  execution: ExecutionView | null;
  session: Session | null;
  signingAuth?: SigningAuthState;
  initialReauthTarget?: string | null;
  approveAction: ApproveReportAction;
}) {
  const t = useTranslations("report");
  const execT = useTranslations("execution");
  const when = useTranslations("decisions");
  const ui = useTranslations("ui");

  const storageKey = `traceq:reauth:report:${runId}`;
  const canApprove = Boolean(session?.mayApprove);

  const readSavedDraft = () => {
    if (typeof window === "undefined") {
      return { conclusionNote: "", nextDate: "" };
    }
    try {
      const saved = window.sessionStorage.getItem(storageKey);
      if (!saved) return { conclusionNote: "", nextDate: "" };
      const parsed = JSON.parse(saved) as {
        conclusion_note?: unknown;
        next_requalification_date?: unknown;
      };
      return {
        conclusionNote: typeof parsed.conclusion_note === "string" ? parsed.conclusion_note : "",
        nextDate:
          typeof parsed.next_requalification_date === "string"
            ? parsed.next_requalification_date
            : "",
      };
    } catch {
      return { conclusionNote: "", nextDate: "" };
    }
  };

  const [conclusionNote, setConclusionNote] = useState(() => readSavedDraft().conclusionNote);
  const [nextDate, setNextDate] = useState(() => readSavedDraft().nextDate);
  const [signDialogOpen, setSignDialogOpen] = useState(
    () => canApprove && initialReauthTarget === "qualification_report",
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.sessionStorage.removeItem(storageKey);
    } catch {
      // Ignore storage errors.
    }
  }, [storageKey]);

  const saveFormBeforeReauth = () => {
    if (typeof window === "undefined") return;
    try {
      window.sessionStorage.setItem(
        storageKey,
        JSON.stringify({
          conclusion_note: conclusionNote,
          next_requalification_date: nextDate,
        }),
      );
    } catch {
      // Ignore storage quota errors.
    }
  };

  const [approveState, formAction] = useActionState(
    async (prev: ApproveReportActionState, fd: FormData) => {
      const next = await approveAction(prev, fd);
      if (next.ok && next.submittedAt) {
        setConclusionNote("");
        setNextDate("");
        setSignDialogOpen(false);
      } else if (!next.ok && next.error) {
        if (next.conclusionNote !== undefined) setConclusionNote(next.conclusionNote);
        if (next.nextRequalificationDate !== undefined) setNextDate(next.nextRequalificationDate);
      }
      return next;
    },
    { ok: false },
  );

  const isNotQualified = report.technical_conclusion === "not_qualified";
  const counts = report.counts;

  const frozenRows = execution?.frozen_copy?.rows ?? [];
  const liveRows = execution?.rows ?? [];
  const testStepRows =
    liveRows.length > 0
      ? liveRows.filter((r) => r.kind === "test_step")
      : frozenRows.filter((r) => r.kind === "test_step");
  const deviations = execution?.frozen_copy?.deviations ?? execution?.deviations ?? [];
  const witnessRows = testStepRows.filter((r) => r.test_step?.witness_required);

  return (
    <div className="space-y-6">
      {/* Technical conclusion & frozen execution summary */}
      <section className="rounded-lg border border-border bg-surface p-4 shadow-xs">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <Award className="h-4 w-4 text-accent" aria-hidden="true" />
              <h2 className="m-0 text-sm font-bold text-ink">{t("conclusionTitle")}</h2>
              <TechnicalConclusionBadge conclusion={report.technical_conclusion} />
            </div>
            <p className="m-0 text-xs text-ink-muted tabular-nums">
              {t("executionMeta", {
                executionId: report.execution_id,
                protocolId: report.protocol_id,
                when: formatWhen(when, report.completed_at),
              })}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-sunken px-2.5 py-1.5 text-xs">
            <Lock className="h-3.5 w-3.5 text-pass" aria-hidden="true" />
            <span className="font-medium text-ink-muted">{t("copyHash")}:</span>
            <code className="font-mono text-[11px] text-ink tabular-nums">
              {report.execution_copy_hash.slice(0, 12)}…
            </code>
            <CopyHashButton
              value={report.execution_copy_hash}
              copyLabel={ui("copyHash")}
              copiedLabel={ui("copied")}
            />
          </div>
        </div>

        {/* Per-stage counts */}
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-md border border-border bg-sunken/60 p-3">
            <div className="text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
              {t("stages.iq")}
            </div>
            <div className="mt-1 text-lg font-bold text-ink tabular-nums">{counts.iq_total}</div>
            <div className="mt-0.5 text-[11px] text-ink-muted tabular-nums">
              {t("stagePassFail", { passed: counts.iq_passed, failed: counts.iq_failed })}
            </div>
          </div>

          <div className="rounded-md border border-border bg-sunken/60 p-3">
            <div className="text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
              {t("stages.oq")}
            </div>
            <div className="mt-1 text-lg font-bold text-ink tabular-nums">{counts.oq_total}</div>
            <div className="mt-0.5 text-[11px] text-ink-muted tabular-nums">
              {t("stagePassFail", { passed: counts.oq_passed, failed: counts.oq_failed })}
            </div>
          </div>

          <div className="rounded-md border border-border bg-sunken/60 p-3">
            <div className="text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
              {t("stages.unsplit")}
            </div>
            <div className="mt-1 text-lg font-bold text-ink tabular-nums">
              {counts.unsplit_total}
            </div>
            <div className="mt-0.5 text-[11px] text-ink-muted tabular-nums">
              {t("stagePassFail", {
                passed: counts.unsplit_passed,
                failed: counts.unsplit_failed,
              })}
            </div>
          </div>

          <div className="rounded-md border border-border bg-sunken/60 p-3">
            <div className="text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
              {t("stages.vendorRef")}
            </div>
            <div className="mt-1 text-lg font-bold text-ink tabular-nums">
              {counts.vendor_reference_count}
            </div>
            <div className="mt-0.5 text-[11px] text-ink-muted tabular-nums">
              {t("totalSummary", {
                rows: counts.total_rows,
                deviations: counts.total_deviations,
              })}
            </div>
          </div>
        </div>
      </section>

      {/* ADR 0007 explicit notice */}
      <Alert tone="info" title={t("adrNoticeTitle")}>
        <p className="m-0">{report.approval_note || t("adrNoticeBody")}</p>
      </Alert>

      {/* Approver issue form */}
      <section className="space-y-3 rounded-lg border border-border bg-surface p-4 shadow-xs">
        <SectionHeading
          id="report-issue-heading"
          title={t("issueTitle")}
          note={
            report.latest_export
              ? t("latestRevision", { rev: report.latest_export.revision_number })
              : t("noExportYet")
          }
        />

        {!canApprove ? (
          <p className="m-0 text-xs text-ink-muted">{t("approverOnly")}</p>
        ) : (
          // Not a <form>: Enter in the date field would submit the approval without the signature
          // dialog. Only the dialog's own form (below) carries the fields and submits.
          <div className="space-y-3">
            {approveState.error && (
              <Alert tone="fail">
                <div className="flex items-start gap-2">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                  <span>{errorMessage(t, approveState.error, approveState.detail)}</span>
                </div>
              </Alert>
            )}

            {approveState.ok && approveState.submittedAt && (
              <Alert tone="pass">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span>{t("issueSuccess")}</span>
                </div>
              </Alert>
            )}

            <div className="space-y-1">
              <label
                htmlFor="conclusion-note"
                className="block text-xs font-semibold text-ink"
              >
                {t("conclusionNoteLabel")}
              </label>
              <FieldTextarea
                id="conclusion-note"
                name="conclusion_note"
                value={conclusionNote}
                onChange={(e) => setConclusionNote(e.target.value)}
                rows={3}
                placeholder={t("conclusionNotePlaceholder")}
                className="w-full text-xs"
              />
            </div>

            {!isNotQualified ? (
              <div className="max-w-xs space-y-1">
                <label
                  htmlFor="next-requalification-date"
                  className="block text-xs font-semibold text-ink"
                >
                  {t("nextRequalificationLabel")}
                </label>
                <input
                  id="next-requalification-date"
                  name="next_requalification_date"
                  type="date"
                  value={nextDate}
                  onChange={(e) => setNextDate(e.target.value)}
                  className={`w-full text-xs ${FIELD_BASE_CLASS}`}
                />
                <p className="m-0 text-[11px] text-ink-muted">{t("nextRequalificationHint")}</p>
              </div>
            ) : (
              <p className="m-0 rounded border border-warn-edge bg-warn-soft px-3 py-2 text-xs text-warn">
                {t("notQualifiedNoRequal")}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" variant="primary" onClick={() => setSignDialogOpen(true)}>
                <FileCheck2 className="h-3.5 w-3.5" aria-hidden="true" />
                <span>{t("issueButton")}</span>
              </Button>
            </div>

            <ElectronicSignatureDialog
              open={signDialogOpen}
              onOpenChange={setSignDialogOpen}
              title={t("issueButton")}
              targetSummary={`${t("issueTitle")} · ${t("latestRevision", { rev: (report.latest_export?.revision_number ?? 0) + 1 })}`}
              signatureMeaning="approved"
              contentHash={report.execution_copy_hash}
              signingAuth={signingAuth}
              reauthNextUrl={`/runs/${encodeURIComponent(runId)}/report?reauth_target=qualification_report`}
              onBeforeReauth={saveFormBeforeReauth}
              action={formAction}
              confirmLabel={t("issueButton")}
              error={
                approveState.error
                  ? errorMessage(t, approveState.error, approveState.detail)
                  : null
              }
              isReauthError={approveState.error === "reauth_required"}
            >
              <input type="hidden" name="run_id" value={runId} />
              <input type="hidden" name="execution_id" value={report.execution_id} />
              <input
                type="hidden"
                name="expected_revision_number"
                value={(report.latest_export?.revision_number ?? 0) + 1}
              />
              <input
                type="hidden"
                name="expected_execution_copy_hash"
                value={report.execution_copy_hash}
              />
              <input type="hidden" name="conclusion_note" value={conclusionNote} />
              <input type="hidden" name="next_requalification_date" value={nextDate} />
            </ElectronicSignatureDialog>
          </div>
        )}
      </section>

      {/* Immutable Export History */}
      <section className="space-y-3">
        <SectionHeading
          id="report-exports-heading"
          title={t("exportsTitle")}
          count={report.exports.length}
        />
        {report.exports.length === 0 ? (
          <EmptyState title={t("exportsEmptyTitle")}>{t("exportsEmpty")}</EmptyState>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border bg-surface shadow-xs">
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-border bg-sunken/70 text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
                  <th scope="col" className="px-3 py-2">
                    {t("colRevision")}
                  </th>
                  <th scope="col" className="px-3 py-2">
                    {t("colConclusion")}
                  </th>
                  <th scope="col" className="px-3 py-2">
                    {t("colIssuer")}
                  </th>
                  <th scope="col" className="px-3 py-2">
                    {t("colRequalDate")}
                  </th>
                  <th scope="col" className="px-3 py-2">
                    {t("colHashes")}
                  </th>
                  <th scope="col" className="px-3 py-2 text-right">
                    {t("colDownload")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {report.exports.map((exp) => (
                  <tr key={exp.id} className="hover:bg-sunken/40">
                    <th scope="row" className="px-3 py-2.5 font-mono font-semibold text-ink tabular-nums">
                      Rev {exp.revision_number}
                    </th>
                    <td className="px-3 py-2.5">
                      <TechnicalConclusionBadge conclusion={exp.technical_conclusion} size="xs" />
                      {exp.conclusion_note && (
                        <div className="mt-1 max-w-xs text-[11px] text-ink-muted">
                          {exp.conclusion_note}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-ink">
                      <div className="font-medium">{exp.name}</div>
                      <div className="text-[11px] text-ink-muted tabular-nums">
                        {formatWhen(when, exp.at)}
                      </div>
                      <div className="mt-1.5">
                        <SignatureBadge signature={exp.electronic_signature} compact />
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-ink-muted tabular-nums">
                      {exp.next_requalification_date ?? t("unscheduled")}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="space-y-1">
                        <div className="flex items-center gap-1.5">
                          <span className="text-[11px] text-ink-muted">snap:</span>
                          <code className="font-mono text-[11px] text-ink tabular-nums">
                            {exp.snapshot_hash.slice(0, 10)}…
                          </code>
                          <CopyHashButton
                            value={exp.snapshot_hash}
                            copyLabel={ui("copyHash")}
                            copiedLabel={ui("copied")}
                          />
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className="text-[11px] text-ink-muted">pdf:</span>
                          <code className="font-mono text-[11px] text-ink tabular-nums">
                            {exp.pdf_sha256.slice(0, 10)}…
                          </code>
                          <CopyHashButton
                            value={exp.pdf_sha256}
                            copyLabel={ui("copyHash")}
                            copiedLabel={ui("copied")}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap">
                      <a
                        href={`/api/executions/${report.execution_id}/qualification-reports/${exp.id}/pdf`}
                        download
                        className="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-2.5 py-1 text-xs font-semibold text-accent no-underline hover:bg-sunken"
                      >
                        <Download className="h-3.5 w-3.5" aria-hidden="true" />
                        <span>{t("downloadPdf")}</span>
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Test Steps & Retest Lineage */}
      {testStepRows.length > 0 && (
        <section className="space-y-3">
          <SectionHeading
            id="report-steps-heading"
            title={t("stepsTitle")}
            count={testStepRows.length}
          />
          <div className="overflow-x-auto rounded-lg border border-border bg-surface shadow-xs">
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-border bg-sunken/70 text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
                  <th scope="col" className="px-3 py-2">
                    {execT("colRequirement")}
                  </th>
                  <th scope="col" className="px-3 py-2">
                    {t("colStageWitness")}
                  </th>
                  <th scope="col" className="px-3 py-2">
                    {t("colAttempts")}
                  </th>
                  <th scope="col" className="px-3 py-2">
                    {execT("colResult")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {testStepRows.map((row) => {
                  const lastAttempt = row.attempts.at(-1);
                  const latest = lastAttempt
                    ? "latest" in lastAttempt
                      ? lastAttempt.latest
                      : lastAttempt.versions.at(-1)
                    : undefined;
                  const activeWitnesses = (latest?.witness_confirmations ?? []).filter(
                    (w) => !w.voided,
                  );
                  const retests = row.attempts.filter((a) => a.retest_deviation_id != null);

                  return (
                    <tr key={row.requirement} className="hover:bg-sunken/40">
                      <th scope="row" className="px-3 py-2.5 font-mono font-semibold text-ink tabular-nums">
                        <div>{row.requirement}</div>
                        <div className="mt-0.5 line-clamp-1 font-sans text-[11px] font-normal text-ink-muted">
                          {row.text}
                        </div>
                      </th>
                      <td className="px-3 py-2.5">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <StageBadge stage={row.test_step?.stage} />
                          {row.test_step?.witness_required && (
                            <span className="inline-flex items-center gap-1 rounded-full border border-info-edge bg-info-soft px-2 py-0.5 text-[11px] font-semibold text-info">
                              <ShieldCheck className="h-3 w-3 shrink-0" aria-hidden="true" />
                              <span>{t("witnessRequiredBadge")}</span>
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-ink tabular-nums">
                        <div>{t("attemptCount", { count: row.attempts.length })}</div>
                        {retests.length > 0 && (
                          <div className="mt-0.5 flex flex-wrap items-center gap-1 text-[11px] text-warn">
                            <GitBranch className="h-3 w-3 shrink-0" aria-hidden="true" />
                            <span>
                              {retests
                                .map((a) =>
                                  t("retestLink", {
                                    attempt: a.attempt_number,
                                    devId: a.retest_deviation_id ?? 0,
                                  }),
                                )
                                .join(" · ")}
                            </span>
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="flex flex-wrap items-center gap-1.5">
                          {latest ? <VerdictBadge verdict={latest.verdict} /> : <span>—</span>}
                          {activeWitnesses.length > 0 && (
                            <span className="inline-flex items-center gap-1 rounded-full border border-pass-edge bg-pass-soft px-1.5 py-0.5 text-[10px] font-semibold text-pass">
                              <ShieldCheck className="h-3 w-3 shrink-0" aria-hidden="true" />
                              <span>{execT("witnessConfirmedBadge")}</span>
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Deviations & Witnessing Summary */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="space-y-3 rounded-lg border border-border bg-surface p-4 shadow-xs">
          <SectionHeading
            id="report-deviations-heading"
            title={t("deviationsTitle")}
            count={deviations.length}
          />
          {deviations.length === 0 ? (
            <p className="m-0 text-xs text-ink-muted">{execT("deviationsEmpty")}</p>
          ) : (
            <ul className="m-0 list-none space-y-2 p-0 text-xs">
              {deviations.map((d) => (
                <li
                  key={d.id}
                  className="flex flex-wrap items-start justify-between gap-2 rounded-md border border-border bg-sunken/50 px-3 py-2"
                >
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-ink tabular-nums">
                        #{d.deviation_number}
                      </span>
                      <DeviationStatusBadge status={d.status} />
                      {d.requirement && (
                        <span className="font-mono text-[11px] text-ink-muted">
                          {d.requirement}
                        </span>
                      )}
                    </div>
                    <p className="m-0 text-ink">{d.description}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="space-y-3 rounded-lg border border-border bg-surface p-4 shadow-xs">
          <SectionHeading
            id="report-witnessing-heading"
            title={t("witnessingTitle")}
            count={witnessRows.length}
          />
          {witnessRows.length === 0 ? (
            <p className="m-0 text-xs text-ink-muted">{t("witnessingEmpty")}</p>
          ) : (
            <ul className="m-0 list-none space-y-2 p-0 text-xs">
              {witnessRows.map((row) => {
                const lastAttempt = row.attempts.at(-1);
                const latest = lastAttempt
                  ? "latest" in lastAttempt
                    ? lastAttempt.latest
                    : lastAttempt.versions.at(-1)
                  : undefined;
                const active = (latest?.witness_confirmations ?? []).filter((w) => !w.voided);
                return (
                  <li
                    key={row.requirement}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-sunken/50 px-3 py-2"
                  >
                    <span className="font-mono font-semibold text-ink tabular-nums">
                      {row.requirement}
                    </span>
                    <span className="text-ink-muted">
                      {active.length > 0
                        ? active
                            .map((w) => {
                              const wName = "witness" in w ? w.witness.name : w.name;
                              const wAt = "recorded_at" in w ? w.recorded_at : w.at;
                              return `${wName} (${formatWhen(when, wAt)})`;
                            })
                            .join(", ")
                        : t("witnessUnconfirmed")}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
