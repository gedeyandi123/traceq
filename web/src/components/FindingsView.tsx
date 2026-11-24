"use client";

import {
  ArrowRight,
  CheckCircle2,
  FileWarning,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useMemo, useState } from "react";

import type { Cite, Findings, Proposal } from "@/api/client";
import type { DecisionView } from "@/components/Decisions";
import {
  DecisionCountsSummary,
  DecisionNoticeBanner,
  FindingDecisionPanel,
} from "@/components/FindingDecisionPanel";
import { formatWhen } from "@/components/formatWhen";
import { PdfCitationButton } from "@/components/ui/PdfCitationModal";
import { DecisionStateBadge } from "@/components/ui/StatusBadge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";

type TriageFilter = "all" | "undecided" | "rule" | "ai";

type FindingItem =
  | {
      key: string;
      kind: "check";
      index: number;
      finding: Findings["check_findings"][number];
      proposal: Proposal | undefined;
    }
  | {
      key: string;
      kind: "ai";
      index: number;
      finding: Findings["ai_findings"][number];
      proposal: Proposal | undefined;
    };

function CitationsList({ cites, runId }: { cites: readonly Cite[]; runId: string }) {
  return (
    <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
      {cites.map((c) => (
        <li key={`${c.doc}/${c.rev}/${c.page}/${c.quote}`}>
          <PdfCitationButton runId={runId} cite={c} compact />
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

/** Pre-Review Findings (Opsi B Grouped Split-Pane): explicit visual and filter separation
 * between deterministic Check Findings and advisory-only AI Findings, plus a read-only
 * Missing Documents tab for VMP requirements. */
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
  const checks = useMemo(() => byPosition(decisions, "check"), [decisions]);
  const ais = useMemo(() => byPosition(decisions, "ai"), [decisions]);

  const allItems = useMemo<FindingItem[]>(() => {
    const checkItems: FindingItem[] = findings.check_findings.map((finding, index) => ({
      key: `check:${index}`,
      kind: "check",
      index,
      finding,
      proposal: checks.get(index),
    }));
    const aiItems: FindingItem[] = findings.ai_findings.map((finding, index) => ({
      key: `ai:${index}`,
      kind: "ai",
      index,
      finding,
      proposal: ais.get(index),
    }));
    return [...checkItems, ...aiItems];
  }, [findings.check_findings, findings.ai_findings, checks, ais]);

  const [activeFilter, setActiveFilter] = useState<TriageFilter>("all");
  const [selectedKey, setSelectedKey] = useState<string | null>(() => allItems[0]?.key ?? null);
  const [isFormDirty, setIsFormDirty] = useState(false);
  const [pendingAction, setPendingAction] = useState<
    | { type: "select"; key: string }
    | { type: "filter"; filter: TriageFilter }
    | null
  >(null);

  const filteredItems = useMemo(() => {
    return allItems.filter((item) => {
      if (activeFilter === "rule") return item.kind === "check";
      if (activeFilter === "ai") return item.kind === "ai";
      if (activeFilter === "undecided") {
        return (item.proposal?.state ?? "undecided") !== "decided";
      }
      return true;
    });
  }, [allItems, activeFilter]);

  const filteredChecks = useMemo(
    () => filteredItems.filter((i): i is Extract<FindingItem, { kind: "check" }> => i.kind === "check"),
    [filteredItems],
  );
  const filteredAi = useMemo(
    () => filteredItems.filter((i): i is Extract<FindingItem, { kind: "ai" }> => i.kind === "ai"),
    [filteredItems],
  );

  const effectiveSelected = useMemo(() => {
    if (filteredItems.length === 0) return null;
    return filteredItems.find((i) => i.key === selectedKey) ?? filteredItems[0] ?? null;
  }, [filteredItems, selectedKey]);

  const requestSelect = (key: string) => {
    if (key === effectiveSelected?.key) return;
    if (isFormDirty) {
      setPendingAction({ type: "select", key });
      return;
    }
    setSelectedKey(key);
    setPendingAction(null);
  };

  const requestFilter = (filter: TriageFilter) => {
    if (filter === activeFilter) return;
    if (isFormDirty) {
      setPendingAction({ type: "filter", filter });
      return;
    }
    setActiveFilter(filter);
    setPendingAction(null);
  };

  const handleDiscardAndProceed = () => {
    if (!pendingAction) return;
    setIsFormDirty(false);
    if (pendingAction.type === "select") {
      setSelectedKey(pendingAction.key);
    } else {
      setActiveFilter(pendingAction.filter);
    }
    setPendingAction(null);
  };

  const docType = (type: string) => (t.has(`docTypes.${type}`) ? t(`docTypes.${type}`) : type);

  const filterOptions: readonly { id: TriageFilter; label: string; count: number }[] = [
    { id: "all", label: t("filters.all"), count: allItems.length },
    ...(decided
      ? [
          {
            id: "undecided" as const,
            label: t("filters.undecided"),
            count: allItems.filter((i) => (i.proposal?.state ?? "undecided") !== "decided").length,
          },
        ]
      : []),
    { id: "rule", label: t("filters.rule"), count: findings.check_findings.length },
    { id: "ai", label: t("filters.ai"), count: findings.ai_findings.length },
  ];

  return (
    <div className="space-y-4">
      <DecisionNoticeBanner view={decisions} />

      <div className="flex flex-wrap items-start justify-between gap-3">
        <DecisionCountsSummary counts={decisions.counts} kinds={["check", "ai"]} />
      </div>

      <Tabs defaultValue="findings">
        <TabsList>
          <TabsTrigger value="findings">
            <span>{t("tabs.findings")}</span>
            <span className="rounded-full bg-sunken px-1.5 py-0.5 text-[11px] font-semibold text-ink-muted tabular-nums">
              {allItems.length}
            </span>
          </TabsTrigger>
          <TabsTrigger value="missing">
            <span>{t("tabs.missing")}</span>
            <span className="rounded-full bg-sunken px-1.5 py-0.5 text-[11px] font-semibold text-ink-muted tabular-nums">
              {findings.missing_documents.length}
            </span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="findings" className="space-y-3">
          {/* 1-click triage filters */}
          <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-border bg-surface p-2">
            {filterOptions.map((opt) => {
              const active = activeFilter === opt.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  data-tw=""
                  aria-pressed={active}
                  onClick={() => requestFilter(opt.id)}
                  className={`inline-flex cursor-pointer items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-semibold transition-colors ${
                    active
                      ? "border-accent bg-accent text-on-accent"
                      : "border-border bg-canvas text-ink hover:bg-sunken"
                  }`}
                >
                  <span>{opt.label}</span>
                  <span
                    className={`rounded-full px-1.5 py-0.2 text-[11px] tabular-nums ${
                      active ? "bg-surface/20 text-on-accent" : "bg-surface text-ink-muted"
                    }`}
                  >
                    {opt.count}
                  </span>
                </button>
              );
            })}
          </div>

          {filteredItems.length === 0 ? (
            <div className="rounded-lg border border-border bg-surface p-6 text-center text-xs text-ink-muted">
              {t("workspace.noMatches")}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(300px,380px)_1fr]">
              {/* Left Master List: Grouped Check Findings vs AI Findings */}
              <div className="space-y-4">
                {(activeFilter === "all" ||
                  activeFilter === "undecided" ||
                  activeFilter === "rule") && (
                  <section
                    aria-labelledby="check-findings-heading"
                    className="overflow-hidden rounded-lg border border-border bg-surface"
                  >
                    <div className="border-b border-border bg-sunken px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <h2
                          id="check-findings-heading"
                          className="m-0 flex items-center gap-1.5 text-xs font-bold text-ink"
                        >
                          <ShieldCheck className="h-3.5 w-3.5 text-accent" aria-hidden="true" />
                          <span>{t("check")}</span>
                        </h2>
                        <span className="rounded-full bg-surface px-2 py-0.5 text-[11px] font-semibold text-ink-muted tabular-nums">
                          {filteredChecks.length}
                        </span>
                      </div>
                      <p className="mt-0.5 mb-0 text-[11px] text-ink-muted">{t("checkNote")}</p>
                    </div>
                    {filteredChecks.length === 0 ? (
                      <p className="m-0 px-3 py-3 text-xs text-ink-muted">{t("none")}</p>
                    ) : (
                      <ul className="m-0 list-none divide-y divide-border p-0">
                        {filteredChecks.map((item) => {
                          const isSelected = effectiveSelected?.key === item.key;
                          return (
                            <li key={item.key}>
                              <button
                                type="button"
                                data-tw=""
                                aria-pressed={isSelected}
                                onClick={() => requestSelect(item.key)}
                                className={`flex w-full cursor-pointer flex-col gap-1.5 px-3 py-2.5 text-left transition-colors ${
                                  isSelected
                                    ? "border-l-4 border-l-accent bg-accent-soft"
                                    : "hover:bg-canvas"
                                }`}
                              >
                                <div className="flex items-start justify-between gap-2">
                                  <span className="text-xs font-semibold text-ink">
                                    {t(`checkTypes.${item.finding.type}`)}
                                  </span>
                                  {decided && item.proposal && (
                                    <DecisionStateBadge state={item.proposal.state} />
                                  )}
                                </div>
                                <div className="flex items-center justify-between gap-2 text-[11px] text-ink-muted">
                                  <span className="font-mono font-medium tabular-nums">
                                    {item.finding.doc}
                                  </span>
                                </div>
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </section>
                )}

                {(activeFilter === "all" ||
                  activeFilter === "undecided" ||
                  activeFilter === "ai") && (
                  <section
                    aria-labelledby="ai-findings-heading"
                    className="overflow-hidden rounded-lg border border-border bg-surface"
                  >
                    <div className="border-b border-border bg-sunken px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <h2
                          id="ai-findings-heading"
                          className="m-0 flex items-center gap-1.5 text-xs font-bold text-ink"
                        >
                          <Sparkles className="h-3.5 w-3.5 text-info" aria-hidden="true" />
                          <span>{t("ai")}</span>
                        </h2>
                        <span className="rounded-full bg-surface px-2 py-0.5 text-[11px] font-semibold text-ink-muted tabular-nums">
                          {filteredAi.length}
                        </span>
                      </div>
                      <p className="mt-0.5 mb-0 text-[11px] text-ink-muted">{t("aiNote")}</p>
                    </div>
                    {filteredAi.length === 0 ? (
                      <p className="m-0 px-3 py-3 text-xs text-ink-muted">{t("none")}</p>
                    ) : (
                      <ul className="m-0 list-none divide-y divide-border p-0">
                        {filteredAi.map((item) => {
                          const isSelected = effectiveSelected?.key === item.key;
                          return (
                            <li key={item.key}>
                              <button
                                type="button"
                                data-tw=""
                                aria-pressed={isSelected}
                                onClick={() => requestSelect(item.key)}
                                className={`flex w-full cursor-pointer flex-col gap-1.5 px-3 py-2.5 text-left transition-colors ${
                                  isSelected
                                    ? "border-l-4 border-l-accent bg-accent-soft"
                                    : "hover:bg-canvas"
                                }`}
                              >
                                <div className="flex items-start justify-between gap-2">
                                  <span className="text-xs font-semibold text-ink">
                                    {t(`aiTypes.${item.finding.type}`)}
                                  </span>
                                  {decided && item.proposal ? (
                                    <DecisionStateBadge state={item.proposal.state} />
                                  ) : (
                                    <span className="rounded-full border border-border-strong bg-sunken px-2 py-0.5 text-[11px] font-medium text-ink-muted">
                                      {t(`actions.${item.finding.reviewer_action}`)}
                                    </span>
                                  )}
                                </div>
                                <div className="text-[11px] text-ink-muted tabular-nums">
                                  {item.finding.model}
                                </div>
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </section>
                )}
              </div>

              {/* Right Inspection & Decision Workspace */}
              <section
                aria-label={t("detail")}
                className="rounded-lg border border-border bg-surface p-4"
              >
                {pendingAction && (
                  <div
                    role="alertdialog"
                    aria-label={t("workspace.dirtyWarning")}
                    className="mb-4 rounded-lg border border-warn-edge bg-warn-soft p-3 text-xs text-warn"
                  >
                    <p className="m-0 font-semibold">{t("workspace.dirtyWarning")}</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button
                        type="button"
                        data-tw=""
                        onClick={handleDiscardAndProceed}
                        className="cursor-pointer rounded border border-warn-edge bg-surface px-2.5 py-1 text-xs font-semibold text-warn hover:bg-sunken"
                      >
                        {t("workspace.discardChanges")}
                      </button>
                      <button
                        type="button"
                        data-tw=""
                        onClick={() => setPendingAction(null)}
                        className="cursor-pointer rounded bg-accent px-2.5 py-1 text-xs font-semibold text-on-accent hover:bg-accent-hover"
                      >
                        {t("workspace.keepEditing")}
                      </button>
                    </div>
                  </div>
                )}

                {!effectiveSelected ? (
                  <p className="m-0 text-xs text-ink-muted">{t("workspace.empty")}</p>
                ) : effectiveSelected.kind === "check" ? (
                  <div className="space-y-4">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
                      <div className="space-y-1">
                        <span className="inline-flex items-center gap-1 rounded-full border border-pass-edge bg-pass-soft px-2 py-0.5 text-[11px] font-semibold text-pass">
                          <ShieldCheck className="h-3 w-3" aria-hidden="true" />
                          <span>{t("badges.rule")}</span>
                        </span>
                        <h3 className="m-0 text-sm font-bold text-ink">
                          {t(`checkTypes.${effectiveSelected.finding.type}`)}
                        </h3>
                      </div>
                      <span className="rounded border border-border bg-sunken px-2 py-1 font-mono text-xs font-semibold text-ink tabular-nums">
                        {effectiveSelected.finding.doc}
                      </span>
                    </div>

                    <p className="m-0 text-xs leading-relaxed text-ink">
                      {effectiveSelected.finding.detail}
                    </p>

                    <div className="space-y-2 rounded-lg border border-border bg-sunken p-3">
                      <div className="text-xs font-semibold text-ink-muted">{t("citations")}</div>
                      <CitationsList
                        cites={effectiveSelected.finding.citations}
                        runId={runId}
                      />
                      {effectiveSelected.finding.rule && (
                        <div className="flex flex-wrap items-center gap-2 border-t border-border pt-2 text-xs text-ink-muted">
                          <span className="font-semibold">{t("rule")}:</span>
                          <PdfCitationButton
                            runId={runId}
                            cite={effectiveSelected.finding.rule}
                            compact
                          />
                        </div>
                      )}
                    </div>

                    {decided && (
                      <FindingDecisionPanel
                        key={effectiveSelected.key}
                        proposal={effectiveSelected.proposal}
                        runId={runId}
                        screen="findings"
                        access={decisions.access}
                        onDirtyChange={setIsFormDirty}
                      />
                    )}
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
                      <div className="space-y-1">
                        <span className="inline-flex items-center gap-1 rounded-full border border-info-edge bg-info-soft px-2 py-0.5 text-[11px] font-semibold text-info">
                          <Sparkles className="h-3 w-3" aria-hidden="true" />
                          <span>{t("badges.ai")}</span>
                        </span>
                        <h3 className="m-0 text-sm font-bold text-ink">
                          {t(`aiTypes.${effectiveSelected.finding.type}`)}
                        </h3>
                      </div>
                      {!decided && (
                        <span className="rounded-full border border-border-strong bg-sunken px-2.5 py-0.5 text-xs font-medium text-ink-muted">
                          {t(`actions.${effectiveSelected.finding.reviewer_action}`)}
                        </span>
                      )}
                    </div>

                    <p className="m-0 text-xs leading-relaxed text-ink">
                      {effectiveSelected.finding.detail}
                    </p>

                    <div className="rounded-md border border-border bg-canvas px-3 py-2 text-xs text-ink-muted tabular-nums">
                      {t("trace", {
                        model: effectiveSelected.finding.model,
                        prompt: effectiveSelected.finding.prompt.slice(0, 12),
                        created: formatWhen(td, effectiveSelected.finding.created),
                      })}
                    </div>

                    <div className="space-y-2 rounded-lg border border-border bg-sunken p-3">
                      <div className="text-xs font-semibold text-ink-muted">{t("citations")}</div>
                      <CitationsList cites={effectiveSelected.finding.citations} runId={runId} />
                    </div>

                    {decided && (
                      <FindingDecisionPanel
                        key={effectiveSelected.key}
                        proposal={effectiveSelected.proposal}
                        runId={runId}
                        screen="findings"
                        access={decisions.access}
                        onDirtyChange={setIsFormDirty}
                      />
                    )}
                  </div>
                )}
              </section>
            </div>
          )}
        </TabsContent>

        <TabsContent value="missing">
          <section
            aria-labelledby="missing-documents-heading"
            className="overflow-hidden rounded-lg border border-border bg-surface"
          >
            <div className="border-b border-border bg-sunken px-4 py-3">
              <div className="flex items-center justify-between gap-2">
                <h2
                  id="missing-documents-heading"
                  className="m-0 flex items-center gap-1.5 text-sm font-bold text-ink"
                >
                  <FileWarning className="h-4 w-4 text-warn" aria-hidden="true" />
                  <span>{t("missing")}</span>
                </h2>
                <span className="rounded-full bg-surface px-2 py-0.5 text-xs font-semibold text-ink-muted tabular-nums">
                  {findings.missing_documents.length}
                </span>
              </div>
              <p className="mt-0.5 mb-0 text-xs text-ink-muted">{t("missingNote")}</p>
            </div>
            {findings.missing_documents.length === 0 ? (
              <div className="flex items-center gap-2 p-4 text-xs text-ink-muted">
                <CheckCircle2 className="h-4 w-4 text-pass" aria-hidden="true" />
                <span>{t("none")}</span>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left text-xs">
                  <thead>
                    <tr className="border-b border-border bg-canvas text-ink-muted">
                      <th scope="col" className="px-3 py-2 font-semibold">
                        {t("document")}
                      </th>
                      <th scope="col" className="px-3 py-2 font-semibold">
                        {t("type")}
                      </th>
                      <th scope="col" className="px-3 py-2 font-semibold">
                        {t("stage")}
                      </th>
                      <th scope="col" className="px-3 py-2 font-semibold">
                        {t("required")}
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {findings.missing_documents.map((d) => (
                      <tr key={d.doc_id} className="hover:bg-canvas/60">
                        <td className="px-3 py-2.5 font-mono font-semibold text-ink tabular-nums">
                          {d.doc_id}
                        </td>
                        <td className="px-3 py-2.5 text-ink">{docType(d.type)}</td>
                        <td className="px-3 py-2.5 text-ink-muted">{d.stage}</td>
                        <td className="px-3 py-2.5">
                          <PdfCitationButton runId={runId} cite={d.citation} compact />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </TabsContent>
      </Tabs>

      {/* Handoff Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-surface px-4 py-3">
        <span className="text-xs font-medium text-ink-muted">{th("handoffTitle")}</span>
        <Link
          href={`/runs/${encodeURIComponent(runId)}/protocol`}
          className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent no-underline hover:bg-accent-hover"
        >
          <span>{th("toProtocol")}</span>
          <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
        </Link>
      </div>
    </div>
  );
}
