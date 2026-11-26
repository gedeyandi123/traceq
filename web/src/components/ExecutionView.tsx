"use client";

import { AlertCircle, ArrowRight, PlayCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useActionState, useEffect, useState } from "react";

import type {
  AttemptView,
  DeviationView,
  ExecutionView,
  ProtocolView,
} from "@/api/client";
import type { SigningAuthState } from "@/auth/session";
import type { ExecutionActionState } from "@/execution/actions";
import { DeviationDetailDrawer } from "./DeviationDetailDrawer";
import { ExecutionResultDrawer, type ResultDrawerMode } from "./ExecutionResultDrawer";
import { ExecutionRowDrawer } from "./ExecutionRowDrawer";
import { ExecutionRowsTable } from "./ExecutionRowsTable";
import { ManualDeviationDrawer } from "./ManualDeviationDrawer";
import {
  CompletionChecklistPanel,
  ExecutionFrozenCopyPanel,
  ExecutionLimits,
  ExecutionStatusPanel,
} from "./ExecutionSummaryPanels";
import { useRunShell } from "./RunShellContext";
import { Alert } from "./ui/Alert";
import { DeviationStatusBadge } from "./ui/StatusBadge";
import { SubmitButton } from "./ui/SubmitButton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/Tabs";
import { Button, EmptyState } from "./ui/ui";

type T = ReturnType<typeof useTranslations<"execution">>;
const INITIAL_STATE: ExecutionActionState = { ok: true };

function DeviationsSection({
  t,
  deviations,
  canOpenManual,
  onOpenManual,
  onSelectDeviation,
}: {
  t: T;
  deviations: DeviationView[];
  canOpenManual: boolean;
  onOpenManual: () => void;
  onSelectDeviation: (id: number) => void;
}) {
  return (
    <section aria-labelledby="execution-deviations" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="execution-deviations" className="m-0 text-sm font-bold text-ink tabular-nums">
          {t("deviationsTitle", { count: deviations.length })}
        </h2>
        {canOpenManual && (
          <Button type="button" variant="soft" onClick={onOpenManual}>
            {t("openManualDeviation")}
          </Button>
        )}
      </div>
      {deviations.length === 0 ? (
        <p className="m-0 rounded-lg border border-border bg-surface px-4 py-3 text-xs text-ink-muted">
          {t("deviationsEmpty")}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-surface shadow-xs">
          <table className="w-full border-collapse text-left text-xs leading-5">
            <thead className="border-b border-border bg-sunken text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
              <tr>
                <th scope="col" className="px-3 py-2">
                  {t("deviationColNumber")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("deviationColStatus")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("deviationColClass")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("deviationColStep")}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t("deviationColDescription")}
                </th>
              </tr>
            </thead>
            <tbody>
              {deviations.map((d) => (
                <tr key={d.id} className="border-b border-border last:border-b-0 hover:bg-sunken/40">
                  <th scope="row" className="px-3 py-2.5 text-left font-mono font-semibold text-ink tabular-nums">
                    <button
                      type="button"
                      onClick={() => onSelectDeviation(d.id)}
                      className="cursor-pointer font-mono text-xs font-semibold text-accent tabular-nums underline decoration-accent/40 underline-offset-2 hover:text-accent-hover hover:decoration-accent"
                    >
                      #{d.deviation_number}
                    </button>
                  </th>
                  <td className="px-3 py-2.5">
                    <DeviationStatusBadge status={d.status} />
                  </td>
                  <td className="px-3 py-2.5 text-ink-muted">
                    {d.deviation_class
                      ? t(`deviationClasses.${d.deviation_class}`)
                      : t("deviationClassUnset")}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-ink tabular-nums">
                    {d.requirement ?? "—"}
                  </td>
                  <td className="px-3 py-2.5 text-ink">{d.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function ExecutionViewPanel({
  execution,
  protocol,
  runId,
  currentUser = null,
  startAction,
  recordAction = null,
  correctAction = null,
  retestAction = null,
  witnessAction = null,
  openDeviationAction = null,
  investigateAction = null,
  submitDeviationAction = null,
  closeDeviationAction = null,
  returnDeviationAction = null,
  completeAction = null,
  signingAuth = { oidcMode: false, reauthAuthTime: null, signer: null },
  initialReauthTarget = null,
}: {
  execution: ExecutionView | null;
  protocol: ProtocolView | null;
  runId: string;
  currentUser?: { subject: string; issuer: string } | null;
  signingAuth?: SigningAuthState;
  initialReauthTarget?: string | null;
  startAction:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  recordAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  correctAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  retestAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  witnessAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  openDeviationAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  investigateAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  submitDeviationAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  closeDeviationAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  returnDeviationAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
  completeAction?:
    | ((prevState: ExecutionActionState, formData: FormData) => Promise<ExecutionActionState>)
    | null;
}) {
  const t = useTranslations("execution");
  const when = useTranslations("decisions");
  const { setDrawerOpen } = useRunShell();

  const [state, formAction] = useActionState(
    startAction ?? (async () => INITIAL_STATE),
    INITIAL_STATE,
  );
  const initialDevId = (() => {
    if (!initialReauthTarget?.startsWith("deviation_closure:")) return null;
    const id = Number(initialReauthTarget.slice("deviation_closure:".length));
    return Number.isInteger(id) ? id : null;
  })();
  const initialWitnessReq = (() => {
    if (!initialReauthTarget?.startsWith("witness_confirmation:")) return null;
    const parts = initialReauthTarget.split(":");
    return parts[1] ? decodeURIComponent(parts[1]) : null;
  })();

  const [activeTab, setActiveTab] = useState<"rows" | "deviations" | "history">(() =>
    initialDevId !== null ? "deviations" : "rows",
  );
  const [selectedReq, setSelectedReq] = useState<string | null>(initialWitnessReq);
  const [drawerTarget, setDrawerTarget] = useState<{
    requirement: string;
    mode: ResultDrawerMode;
  } | null>(null);
  const [manualDevOpen, setManualDevOpen] = useState(false);
  const [activeDeviationId, setActiveDeviationId] = useState<number | null>(initialDevId);

  const anyDrawerOpen =
    selectedReq !== null ||
    drawerTarget !== null ||
    manualDevOpen ||
    activeDeviationId !== null;

  useEffect(() => {
    setDrawerOpen(anyDrawerOpen);
    return () => setDrawerOpen(false);
  }, [anyDrawerOpen, setDrawerOpen]);

  const protocolHref = `/runs/${encodeURIComponent(runId)}/protocol`;
  const selectedRow =
    execution && selectedReq ? (execution.rows.find((r) => r.requirement === selectedReq) ?? null) : null;
  const activeRow =
    execution && drawerTarget
      ? (execution.rows.find((r) => r.requirement === drawerTarget.requirement) ?? null)
      : null;
  const activeDeviation =
    execution && activeDeviationId !== null
      ? (execution.deviations.find((d) => d.id === activeDeviationId) ?? null)
      : null;

  const isReadOnly =
    execution !== null &&
    recordAction === null &&
    correctAction === null &&
    retestAction === null &&
    witnessAction === null &&
    openDeviationAction === null &&
    investigateAction === null &&
    submitDeviationAction === null &&
    closeDeviationAction === null &&
    returnDeviationAction === null &&
    completeAction === null;

  const openDeviationsCount =
    execution?.deviations.filter((d) => d.status !== "closed").length ?? 0;

  return (
    <div className="space-y-4">
      {!state.ok && state.error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-fail-edge bg-fail-soft px-3.5 py-2.5 text-xs text-fail"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{state.detail ?? t(`errors.${state.error}`)}</span>
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
          {isReadOnly && <Alert tone="info">{t("readOnlyBanner")}</Alert>}

          {execution.status === "in_progress" ? (
            <CompletionChecklistPanel
              t={t}
              executionId={execution.id}
              blockers={execution.completion_blockers}
              completeAction={completeAction}
              onSelectRow={(req) => {
                setActiveTab("rows");
                setSelectedReq(req);
              }}
              onSelectDeviation={(num) => {
                const match = execution.deviations.find((d) => d.deviation_number === num);
                setActiveTab("deviations");
                if (match) setActiveDeviationId(match.id);
              }}
            />
          ) : (
            execution.frozen_copy &&
            execution.copy_hash && (
              <ExecutionFrozenCopyPanel
                t={t}
                when={when}
                frozenCopy={execution.frozen_copy}
                copyHash={execution.copy_hash}
              />
            )
          )}

          <Tabs
            value={activeTab}
            onValueChange={(v) => setActiveTab(v as "rows" | "deviations" | "history")}
          >
            <TabsList>
              <TabsTrigger value="rows">
                <span>{t("tabs.rows")}</span>
                <span className="rounded-full bg-sunken px-1.5 py-0.5 text-[11px] font-semibold text-ink-muted tabular-nums">
                  {execution.rows.length}
                </span>
              </TabsTrigger>
              <TabsTrigger value="deviations">
                <span>{t("tabs.deviations")}</span>
                <span
                  className={`rounded-full px-1.5 py-0.5 text-[11px] font-semibold tabular-nums ${
                    openDeviationsCount > 0
                      ? "bg-warn-soft text-warn"
                      : "bg-sunken text-ink-muted"
                  }`}
                >
                  {execution.deviations.length}
                </span>
              </TabsTrigger>
              <TabsTrigger value="history">
                <span>{t("tabs.history")}</span>
              </TabsTrigger>
            </TabsList>

            <TabsContent value="rows">
              <ExecutionRowsTable
                rows={execution.rows}
                runId={runId}
                selectedRequirement={selectedReq}
                onSelectRow={(req) => setSelectedReq(req)}
                canRecordRow={(r) =>
                  execution.status === "in_progress" &&
                  r.kind === "test_step" &&
                  r.attempts.length === 0 &&
                  recordAction !== null
                }
                onRecordRow={(r) =>
                  setDrawerTarget({ requirement: r.requirement, mode: { kind: "record" } })
                }
              />
            </TabsContent>

            <TabsContent value="deviations">
              <DeviationsSection
                t={t}
                deviations={execution.deviations}
                canOpenManual={execution.status === "in_progress" && openDeviationAction !== null}
                onOpenManual={() => setManualDevOpen(true)}
                onSelectDeviation={(id) => setActiveDeviationId(id)}
              />
            </TabsContent>

            <TabsContent value="history" className="space-y-4">
              <ExecutionStatusPanel t={t} when={when} execution={execution} />
              {execution.frozen_copy && execution.copy_hash && (
                <ExecutionFrozenCopyPanel
                  t={t}
                  when={when}
                  frozenCopy={execution.frozen_copy}
                  copyHash={execution.copy_hash}
                />
              )}
            </TabsContent>
          </Tabs>

          <ExecutionRowDrawer
            row={selectedRow}
            runId={runId}
            executionId={execution.id}
            executionInProgress={execution.status === "in_progress"}
            deviations={execution.deviations}
            currentUser={currentUser}
            canRecord={
              selectedRow !== null &&
              execution.status === "in_progress" &&
              selectedRow.kind === "test_step" &&
              selectedRow.attempts.length === 0 &&
              recordAction !== null
            }
            canCorrect={correctAction !== null}
            canRetest={retestAction !== null}
            witnessAction={witnessAction}
            signingAuth={signingAuth}
            initialReauthTarget={initialReauthTarget}
            open={selectedRow !== null}
            onOpenChange={(open) => {
              if (!open) setSelectedReq(null);
            }}
            onRecord={() => {
              if (selectedRow) {
                setDrawerTarget({ requirement: selectedRow.requirement, mode: { kind: "record" } });
              }
            }}
            onCorrect={(attempt: AttemptView) => {
              if (selectedRow) {
                setDrawerTarget({
                  requirement: selectedRow.requirement,
                  mode: { kind: "correct", attempt },
                });
              }
            }}
            onRetest={(openDeviations: DeviationView[]) => {
              if (selectedRow) {
                setDrawerTarget({
                  requirement: selectedRow.requirement,
                  mode: { kind: "retest", openDeviations },
                });
              }
            }}
          />

          {activeRow &&
            drawerTarget &&
            (() => {
              const action =
                drawerTarget.mode.kind === "correct"
                  ? correctAction
                  : drawerTarget.mode.kind === "retest"
                    ? retestAction
                    : recordAction;
              if (!action) return null;
              const drawerKey =
                drawerTarget.mode.kind === "correct"
                  ? `${activeRow.requirement}-correct-${drawerTarget.mode.attempt.attempt_number}`
                  : `${activeRow.requirement}-${drawerTarget.mode.kind}`;
              return (
                <ExecutionResultDrawer
                  key={drawerKey}
                  executionId={execution.id}
                  row={activeRow}
                  mode={drawerTarget.mode}
                  open={true}
                  onOpenChange={(open) => {
                    if (!open) setDrawerTarget(null);
                  }}
                  recordAction={action}
                />
              );
            })()}

          {manualDevOpen && openDeviationAction && (
            <ManualDeviationDrawer
              executionId={execution.id}
              rows={execution.rows}
              open={true}
              onOpenChange={setManualDevOpen}
              openAction={openDeviationAction}
            />
          )}

          {activeDeviation && (
            <DeviationDetailDrawer
              key={activeDeviation.id}
              runId={runId}
              executionId={execution.id}
              executionInProgress={execution.status === "in_progress"}
              deviation={activeDeviation}
              signingAuth={signingAuth}
              initialReauthTarget={initialReauthTarget}
              open={true}
              onOpenChange={(open) => {
                if (!open) setActiveDeviationId(null);
              }}
              investigateAction={investigateAction}
              submitAction={submitDeviationAction}
              closeAction={closeDeviationAction}
              returnAction={returnDeviationAction}
            />
          )}
        </>
      )}

      <ExecutionLimits t={t} />
    </div>
  );
}
