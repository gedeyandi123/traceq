"use client";

import { AlertCircle, Info } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { ProtocolView } from "@/api/client";
import type { SigningAuthState } from "@/auth/session";
import type { ProtocolFormActionState } from "@/protocol/actions";
import type { DecisionView } from "./Decisions";
import { DecisionNoticeBanner } from "./FindingDecisionPanel";
import { EarlierCopies, FrozenCopy } from "./FrozenCopy";
import { MissedNumbers } from "./MissedNumbers";
import { ProtocolChecklistPanel } from "./ProtocolChecklistPanel";
import { ProtocolRowDrawer } from "./ProtocolRowDrawer";
import { ProtocolRowsTable } from "./ProtocolRowsTable";
import { ProtocolHistory, ProtocolStatusPanel, StartForm } from "./ProtocolStatusPanel";
import { useRunShell } from "./RunShellContext";
import { FilterBar } from "./ui/FilterBar";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/Tabs";
import { EmptyState } from "./ui/ui";

type RowFilter = "all" | "blocking" | "vendor" | "testStep";

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.closest(
      'input, textarea, select, [contenteditable], [contenteditable="true"], [role="listbox"], [role="menu"], [role="combobox"]',
    ) !== null
  );
}

/** Why the API refused a start or a withdrawal, as the page reports it. */
export type ProtocolError =
  | "conflict"
  | "refused"
  | "invalid"
  | "forbidden"
  | "unauthorized"
  | "reauth_required"
  | "failed";

type Action = (formData: FormData) => void | Promise<void>;
type InlineAction = (
  prevState: ProtocolFormActionState,
  formData: FormData,
) => Promise<ProtocolFormActionState>;

/** The forms' server actions (start, withdraw, write or remove a written Test Step, edit a
 * drafted one, answer a missed requirement number, submit), for a viewer with the deciding role;
 * `null` for any other viewer, who sees no controls. */
export type ProtocolControls = {
  start: Action;
  withdraw: Action;
  write: Action;
  remove: Action;
  edit: Action;
  answer: Action;
  submit: Action;
  writeInline?: InlineAction;
  removeInline?: InlineAction;
  editInline?: InlineAction;
  answerInline?: InlineAction;
  updateAttributesInline?: InlineAction;
} | null;

/** The approve and return actions, for a viewer with the approving role; `null` otherwise. */
export type ApprovalControls = { approve: Action; return: Action } | null;

type T = ReturnType<typeof useTranslations<"protocol">>;

const LIMITS = ["oneStep", "combined", "noPrint", "notSignature", "noNewVersion"] as const;

/** The known limits of the Protocol assembled in TraceQ (ADR 0012), always shown. */
function Limits({ t }: { t: T }) {
  return (
    <aside
      aria-labelledby="protocol-limits"
      className="space-y-2 rounded-lg border border-border bg-sunken px-4 py-3 text-xs text-ink-muted"
    >
      <h2 id="protocol-limits" className="m-0 text-xs font-bold tracking-wide text-ink uppercase">
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

/** The Protocol assembled in TraceQ from a run (spec #247, ADR 0012, ADR 0014):
 * Sticky Submission Readiness Bar, Radix Tabs (Baris Protokol, Nomor Terlewat & URS,
 * Riwayat & Salinan), Opsi A compact table + 640px Slide-Over Drawer, Confirmation Modals
 * for destructive actions, FrozenCopy + ApprovalForms (Dewi), and ADR 0012 Limits. */
export function AssembledProtocolView({
  protocol,
  runId,
  decisions,
  controls,
  approval = null,
  signingAuth = { oidcMode: false, reauthAuthTime: null, signer: null },
  initialReauthTarget = null,
  error,
  initialSelected = null,
}: {
  protocol: ProtocolView | null;
  runId: string;
  decisions: DecisionView;
  controls: ProtocolControls;
  approval?: ApprovalControls;
  signingAuth?: SigningAuthState;
  initialReauthTarget?: string | null;
  error?: ProtocolError;
  initialSelected?: string | null;
}) {
  const t = useTranslations("protocol");
  const { setDrawerOpen } = useRunShell();

  const rows = protocol?.rows ?? null;
  const blocking = rows?.filter((r) => r.blockers.length > 0).length ?? 0;
  const unansweredMissed = (protocol?.urs ?? [])
    .flatMap((u) => u.missed)
    .filter((m) => m.blocking).length;

  const [activeTab, setActiveTab] = useState<string>(rows !== null ? "rows" : "copy");
  const [rowFilter, setRowFilter] = useState<RowFilter>("all");
  const [selectedReq, setSelectedReq] = useState<string | null>(initialSelected);
  const [isFormDirty, setIsFormDirty] = useState(false);
  const [pendingReq, setPendingReq] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    setDrawerOpen(selectedReq !== null);
    return () => setDrawerOpen(false);
  }, [selectedReq, setDrawerOpen]);

  useEffect(() => {
    if (!selectedReq || typeof document === "undefined") return;
    const el = document.getElementById(`row-${selectedReq}`);
    if (el && typeof el.scrollIntoView === "function") {
      el.scrollIntoView({ block: "nearest" });
    }
  }, [selectedReq]);

  const filteredRows = useMemo(() => {
    if (!rows) return [];
    return rows.filter((r) => {
      if (rowFilter === "blocking") return r.blockers.length > 0;
      if (rowFilter === "vendor") return r.kind === "vendor_reference";
      if (rowFilter === "testStep") return r.kind === "test_step";
      return true;
    });
  }, [rows, rowFilter]);

  const selectedIndex = useMemo(
    () => (selectedReq ? filteredRows.findIndex((r) => r.requirement === selectedReq) : -1),
    [filteredRows, selectedReq],
  );
  const selectedRow =
    rows && selectedReq
      ? (filteredRows[selectedIndex] ?? rows.find((r) => r.requirement === selectedReq) ?? null)
      : null;

  const syncSelectedUrl = useCallback(
    (nextReq: string | null) => {
      if (typeof window === "undefined") return;
      const base = `/runs/${encodeURIComponent(runId)}/protocol`;
      const qs = new URLSearchParams(window.location.search);
      if (nextReq) qs.set("selected", nextReq);
      else qs.delete("selected");
      const q = qs.toString();
      window.history.replaceState(null, "", q ? `${base}?${q}` : base);
    },
    [runId],
  );

  const applySelection = useCallback(
    (nextReq: string | null) => {
      setSelectedReq(nextReq);
      setIsFormDirty(false);
      setPendingReq(undefined);
      syncSelectedUrl(nextReq);
    },
    [syncSelectedUrl],
  );

  const requestSelection = useCallback(
    (nextReq: string | null) => {
      if (nextReq === selectedReq) return;
      if (selectedReq !== null && isFormDirty) {
        setPendingReq(nextReq);
        return;
      }
      applySelection(nextReq);
    },
    [selectedReq, isFormDirty, applySelection],
  );

  useEffect(() => {
    if (rows === null) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key !== "j" && e.key !== "J" && e.key !== "k" && e.key !== "K") return;
      if (isTypingTarget(e.target)) return;
      if (filteredRows.length === 0) return;

      e.preventDefault();
      const goingDown = e.key === "j" || e.key === "J";
      if (selectedIndex === -1) {
        const first = filteredRows[0];
        if (first) requestSelection(first.requirement);
        return;
      }
      const nextIdx = goingDown
        ? Math.min(selectedIndex + 1, filteredRows.length - 1)
        : Math.max(selectedIndex - 1, 0);
      const target = filteredRows[nextIdx];
      if (target) requestSelection(target.requirement);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [rows, filteredRows, selectedIndex, requestSelection]);

  const navigateToRow = useCallback(
    (req: string) => {
      setActiveTab("rows");
      setRowFilter("all");
      requestSelection(req);
      if (typeof window !== "undefined") {
        window.requestAnimationFrame(() => {
          const el = document.getElementById(`row-${req}`);
          if (el && typeof el.scrollIntoView === "function") {
            el.scrollIntoView({ behavior: "smooth", block: "center" });
          }
        });
      }
    },
    [requestSelection],
  );

  const navigateToMissed = useCallback(() => {
    setActiveTab("missed");
    if (typeof window !== "undefined") {
      window.requestAnimationFrame(() => {
        const el = document.getElementById("protocol-missed");
        if (el && typeof el.scrollIntoView === "function") {
          el.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    }
  }, []);

  const normalizedDraftTab =
    activeTab === "missed" || activeTab === "history" ? activeTab : "rows";

  return (
    <div className="space-y-4">
      {error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-fail-edge bg-fail-soft px-3.5 py-2.5 text-xs text-fail"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{t(`errors.${error}`)}</span>
        </div>
      )}

      <DecisionNoticeBanner view={decisions} approver={approval !== null} />

      {protocol === null ? (
        <EmptyState title={t("none")}>
          <p className="m-0 mb-3 text-xs text-ink-muted">{t("noneBody")}</p>
          <StartForm t={t} runId={runId} action={controls} again={false} />
        </EmptyState>
      ) : (
        <>
          <ProtocolStatusPanel
            t={t}
            protocol={protocol}
            runId={runId}
            controls={controls}
            approval={approval}
            signingAuth={signingAuth}
            initialReauthTarget={initialReauthTarget}
          />

          {rows !== null && (
            <>
              {protocol.checklist && (
                <ProtocolChecklistPanel
                  t={t}
                  items={protocol.checklist}
                  runId={runId}
                  protocolId={protocol.id}
                  draftHash={protocol.draft_hash}
                  controls={controls}
                  signingAuth={signingAuth}
                  initialReauthTarget={initialReauthTarget}
                  onNavigateToRow={navigateToRow}
                  onNavigateToMissed={navigateToMissed}
                />
              )}

              <Tabs value={normalizedDraftTab} onValueChange={setActiveTab}>
                <TabsList>
                  <TabsTrigger value="rows">
                    <span>{t("tabs.rows")}</span>
                    <span className="rounded-full bg-sunken px-1.5 py-0.5 text-[11px] text-ink-muted tabular-nums">
                      {rows.length}
                    </span>
                  </TabsTrigger>
                  <TabsTrigger value="missed">
                    <span>{t("tabs.missed")}</span>
                    {unansweredMissed > 0 && (
                      <span className="rounded-full border border-fail-edge bg-fail-soft px-1.5 py-0.5 text-[11px] font-semibold text-fail tabular-nums">
                        {unansweredMissed}
                      </span>
                    )}
                  </TabsTrigger>
                  <TabsTrigger value="history">{t("tabs.history")}</TabsTrigger>
                </TabsList>

                <TabsContent value="rows" className="space-y-3">
                  <FilterBar
                    ariaLabel={t("rows")}
                    options={[
                      { id: "all", label: t("filters.all"), count: rows.length },
                      { id: "blocking", label: t("filters.blocking"), count: blocking },
                      {
                        id: "vendor",
                        label: t("filters.vendor"),
                        count: rows.filter((r) => r.kind === "vendor_reference").length,
                      },
                      {
                        id: "testStep",
                        label: t("filters.testStep"),
                        count: rows.filter((r) => r.kind === "test_step").length,
                      },
                    ]}
                    activeId={rowFilter}
                    onSelect={setRowFilter}
                  />
                  <p className="m-0 text-xs font-medium text-ink-muted tabular-nums">
                    {t("summary", {
                      rows: rows.length,
                      blocking,
                      vendor: rows.filter((r) => r.kind === "vendor_reference").length,
                      testStep: rows.filter((r) => r.kind === "test_step").length,
                    })}
                  </p>
                  <section aria-labelledby="protocol-rows" className="space-y-2">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <h2 id="protocol-rows" className="m-0 text-sm font-bold text-ink">
                        {t("rows")}
                      </h2>
                      <span className="text-xs text-ink-muted">{t("rowsNote")}</span>
                    </div>
                    <ProtocolRowsTable
                      rows={filteredRows}
                      runId={runId}
                      selectedRequirement={selectedReq}
                      onSelect={requestSelection}
                    />
                  </section>
                </TabsContent>

                <TabsContent value="missed">
                  <MissedNumbers
                    t={t}
                    urs={protocol.urs ?? null}
                    runId={runId}
                    protocolId={protocol.id}
                    answer={controls?.answer ?? null}
                    answerInline={controls?.answerInline}
                  />
                </TabsContent>

                <TabsContent value="history" className="space-y-4">
                  <ProtocolHistory t={t} events={protocol.events} />
                  {protocol.submissions.length > 0 && (
                    <EarlierCopies t={t} earlier={protocol.submissions} />
                  )}
                </TabsContent>
              </Tabs>

              <ProtocolRowDrawer
                row={selectedRow}
                runId={runId}
                protocolId={protocol.id}
                decisions={decisions}
                controls={controls}
                open={selectedRow !== null}
                rowIndex={selectedIndex}
                totalRows={filteredRows.length}
                dirtyPrompt={pendingReq !== undefined}
                onClose={() => requestSelection(null)}
                onPrev={() => {
                  if (selectedIndex > 0) {
                    const prev = filteredRows[selectedIndex - 1];
                    if (prev) requestSelection(prev.requirement);
                  }
                }}
                onNext={() => {
                  if (selectedIndex >= 0 && selectedIndex < filteredRows.length - 1) {
                    const next = filteredRows[selectedIndex + 1];
                    if (next) requestSelection(next.requirement);
                  }
                }}
                onDirtyChange={setIsFormDirty}
                onDiscardAndProceed={() => {
                  if (pendingReq !== undefined) applySelection(pendingReq);
                }}
                onCancelProceed={() => setPendingReq(undefined)}
              />
            </>
          )}

          {rows === null && protocol.status !== "withdrawn" && (
            <>
              <div className="flex items-center gap-2 rounded-md border border-border bg-canvas px-3.5 py-2 text-xs text-ink-muted">
                <Info className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span>{t("notDraftRows")}</span>
              </div>

              <Tabs value={activeTab === "history" ? "history" : "copy"} onValueChange={setActiveTab}>
                <TabsList>
                  <TabsTrigger value="copy">{t("tabs.frozenCopy")}</TabsTrigger>
                  <TabsTrigger value="history">{t("tabs.history")}</TabsTrigger>
                </TabsList>

                <TabsContent value="copy">
                  {protocol.submission && (
                    <FrozenCopy
                      t={t}
                      submission={protocol.submission}
                      earlier={protocol.submissions.filter(
                        (x) => x.event_id !== protocol.submission?.event_id,
                      )}
                      runId={runId}
                    />
                  )}
                </TabsContent>

                <TabsContent value="history" className="space-y-4">
                  <ProtocolHistory t={t} events={protocol.events} />
                  {protocol.submissions.length > 0 && (
                    <EarlierCopies t={t} earlier={protocol.submissions} />
                  )}
                </TabsContent>
              </Tabs>
            </>
          )}

          {protocol.status === "withdrawn" && (
            <div className="space-y-4">
              <ProtocolHistory t={t} events={protocol.events} />
              {protocol.submissions.length > 0 && (
                <EarlierCopies t={t} earlier={protocol.submissions} />
              )}
            </div>
          )}
        </>
      )}

      <Limits t={t} />
    </div>
  );
}
