"use client";

import { ArrowRight, FileText } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  DraftFindingView,
  DraftTestStep,
  ProtocolDraftView as Draft,
} from "@/api/client";
import type { DecisionView } from "@/components/Decisions";
import {
  AnyCite,
  DraftCite,
  DraftStepDrawer,
  formatPrinted,
} from "@/components/DraftStepDrawer";
import {
  DecisionCountsSummary,
  DecisionNoticeBanner,
  FindingDecisionPanel,
} from "@/components/FindingDecisionPanel";
import { useRunShell } from "@/components/RunShellContext";
import { DecisionStateBadge } from "@/components/ui/StatusBadge";

export { formatPrinted };

type DraftFilter = "all" | "withFindings" | "notCompared" | "notRead";
type VendorDoc = Draft["vendor_documents"][number];
type Comparator = DraftTestStep["traced"][number]["comparators"][number];

function CompactComparators({
  t,
  step,
  vendorDocs,
}: {
  t: ReturnType<typeof useTranslations<"draft">>;
  step: DraftTestStep;
  vendorDocs: readonly VendorDoc[];
}) {
  const same = (d: { doc: string; rev: number }) => (c: Comparator) =>
    c.doc === d.doc && c.rev === d.rev;

  if (vendorDocs.length === 0) {
    return <span className="text-ink-muted">{t("noComparators")}</span>;
  }

  return (
    <ul className="m-0 list-none space-y-0.5 p-0 text-[11px]">
      {vendorDocs.map((d) => {
        const facts = step.traced.flatMap((tr) =>
          tr.comparators.filter(same(d)).flatMap((c) => c.facts),
        );
        return (
          <li key={`${d.doc}/${d.rev}`} data-vendor-doc="" className="text-ink-muted">
            <span className="font-medium text-ink">
              {t(`vendorKinds.${d.kind}`)} {d.doc}:
            </span>{" "}
            {facts.length > 0 ? (
              <span className="tabular-nums">
                {facts.map((f) => `${f.name}: ${f.printed}`).join(", ")}
              </span>
            ) : (
              <span>{t("noComparators")}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** Protocol Draft (Opsi A Compact Ordered Table + Slide-Over Drawer): preserves sequential
 * 26-step draft order in a compact table with 1-click triage filters, opens step inspection
 * and decisions in a right slide-over Drawer, and keeps "Temuan tentang seluruh dokumen"
 * below the table. */
export function ProtocolDraftView({
  draft,
  runId,
  decisions,
}: {
  draft: Draft;
  runId: string;
  decisions: DecisionView;
}) {
  const t = useTranslations("draft");
  const th = useTranslations("runHeader");
  const { setDrawerOpen } = useRunShell();

  const draftDoc = draft.document.doc_id;
  const stepIds = useMemo(() => new Set(draft.test_steps.map((st) => st.id)), [draft.test_steps]);

  const findingsByStep = useMemo(() => {
    const map = new Map<string, DraftFindingView[]>();
    for (const f of draft.findings) {
      const id = f.finding.test_step;
      if (id && stepIds.has(id)) {
        const list = map.get(id) ?? [];
        list.push(f);
        map.set(id, list);
      }
    }
    return map;
  }, [draft.findings, stepIds]);

  const whole = useMemo(
    () =>
      draft.findings.filter(
        (f) => f.finding.test_step == null || !stepIds.has(f.finding.test_step),
      ),
    [draft.findings, stepIds],
  );

  const notRead = useMemo(
    () => draft.test_steps.filter((st) => st.acceptance === null),
    [draft.test_steps],
  );
  const notCompared = useMemo(
    () => draft.test_steps.filter((st) => st.acceptance !== null && !st.compared),
    [draft.test_steps],
  );
  const withFindings = useMemo(
    () => draft.test_steps.filter((st) => (findingsByStep.get(st.id)?.length ?? 0) > 0),
    [draft.test_steps, findingsByStep],
  );

  const [activeFilter, setActiveFilter] = useState<DraftFilter>("all");
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [isFormDirty, setIsFormDirty] = useState(false);
  const [pendingStepId, setPendingStepId] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    setDrawerOpen(selectedStepId !== null);
    return () => setDrawerOpen(false);
  }, [selectedStepId, setDrawerOpen]);

  const filteredSteps = useMemo(() => {
    return draft.test_steps.filter((st) => {
      if (activeFilter === "withFindings") return (findingsByStep.get(st.id)?.length ?? 0) > 0;
      if (activeFilter === "notCompared") return st.acceptance !== null && !st.compared;
      if (activeFilter === "notRead") return st.acceptance === null;
      return true;
    });
  }, [draft.test_steps, activeFilter, findingsByStep]);

  const selectedIndex = useMemo(
    () => (selectedStepId ? filteredSteps.findIndex((st) => st.id === selectedStepId) : -1),
    [filteredSteps, selectedStepId],
  );
  const selectedStep = selectedIndex >= 0 ? (filteredSteps[selectedIndex] ?? null) : null;

  const applySelection = useCallback((nextId: string | null) => {
    setSelectedStepId(nextId);
    setIsFormDirty(false);
    setPendingStepId(undefined);
  }, []);

  const requestSelection = useCallback(
    (nextId: string | null) => {
      if (nextId === selectedStepId) return;
      if (selectedStepId !== null && isFormDirty) {
        setPendingStepId(nextId);
        return;
      }
      applySelection(nextId);
    },
    [selectedStepId, isFormDirty, applySelection],
  );

  const filterOptions: readonly { id: DraftFilter; label: string; count: number }[] = [
    { id: "all", label: t("filters.all"), count: draft.test_steps.length },
    { id: "withFindings", label: t("filters.withFindings"), count: withFindings.length },
    { id: "notCompared", label: t("filters.notCompared"), count: notCompared.length },
    ...(notRead.length > 0
      ? [{ id: "notRead" as const, label: t("filters.notRead"), count: notRead.length }]
      : []),
  ];

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-surface px-4 py-3 text-xs">
        <div className="flex items-center gap-2 font-semibold text-ink tabular-nums">
          <FileText className="h-4 w-4 text-accent" aria-hidden="true" />
          <span>
            {t("document", {
              doc: draft.document.doc_id,
              rev: draft.document.rev,
              package: draft.package,
            })}
          </span>
        </div>
        <p className="mt-1 mb-0 text-ink-muted">{t("ownSteps")}</p>
      </div>

      <DecisionNoticeBanner view={decisions} />

      <div className="flex flex-wrap items-start justify-between gap-3">
        <DecisionCountsSummary counts={decisions.counts} kinds={["draft"]} />
      </div>

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
              onClick={() => setActiveFilter(opt.id)}
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

      {/* Section 1: Sequential Ordered Steps Table */}
      <section aria-labelledby="draft-steps" className="space-y-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div className="flex items-center gap-2">
            <h2 id="draft-steps" className="m-0 text-sm font-bold text-ink">
              {t("steps")}
            </h2>
            <span className="rounded-full bg-sunken px-2 py-0.5 text-xs font-semibold text-ink-muted tabular-nums">
              {filteredSteps.length}
            </span>
          </div>
          <p className="m-0 text-xs text-ink-muted">{t("stepsNote")}</p>
        </div>

        {draft.test_steps.length === 0 ? (
          <div className="rounded-lg border border-border bg-surface p-6 text-center text-xs text-ink-muted">
            {t("noSteps")}
          </div>
        ) : filteredSteps.length === 0 ? (
          <div className="rounded-lg border border-border bg-surface p-6 text-center text-xs text-ink-muted">
            {t("noMatches")}
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border bg-surface">
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-border bg-canvas text-ink-muted">
                  <th scope="col" className="px-3 py-2 font-semibold">
                    {t("step")}
                  </th>
                  <th scope="col" className="px-3 py-2 font-semibold">
                    {t("ac")}
                  </th>
                  <th scope="col" className="px-3 py-2 font-semibold">
                    {t("urs")}
                  </th>
                  <th scope="col" className="px-3 py-2 font-semibold">
                    {t("comparators")}
                  </th>
                  <th scope="col" className="px-3 py-2 font-semibold">
                    {t("findings")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredSteps.map((st) => {
                  const stepFindings = findingsByStep.get(st.id) ?? [];
                  const isSelected = selectedStepId === st.id;
                  const ac = st.acceptance;
                  return (
                    <tr
                      key={st.id}
                      className={isSelected ? "bg-accent-soft" : "hover:bg-canvas/60"}
                    >
                      <th scope="row" className="px-3 py-2.5 align-top whitespace-nowrap">
                        <button
                          type="button"
                          data-tw=""
                          onClick={() => requestSelection(st.id)}
                          aria-expanded={isSelected}
                          className="inline-flex cursor-pointer items-center gap-1 rounded border border-border bg-surface px-2 py-1 font-mono text-xs font-bold text-accent tabular-nums hover:border-accent hover:bg-accent-soft"
                        >
                          {st.id}
                        </button>
                      </th>

                      {ac === null ? (
                        <td colSpan={4} className="px-3 py-2.5 align-top text-warn">
                          {t("notRead", { reason: st.not_read ?? "" })}
                        </td>
                      ) : (
                        <>
                          <td className="px-3 py-2.5 align-top">
                            <div className="font-medium text-ink">{ac.printed}</div>
                            {ac.value === null && (
                              <div className="text-[11px] text-ink-muted">{t("notParsed")}</div>
                            )}
                            <div className="mt-0.5">
                              <DraftCite cite={ac.citation} />
                            </div>
                          </td>
                          <td className="px-3 py-2.5 align-top">
                            <ul className="m-0 list-none space-y-1 p-0">
                              {st.traced.map((tr) => (
                                <li key={tr.requirement} className="space-y-0.5">
                                  <div className="font-mono font-semibold text-ink tabular-nums">
                                    {tr.requirement}
                                  </div>
                                  {tr.urs_limit && (
                                    <div className="text-ink-muted tabular-nums">
                                      {formatPrinted(t, tr.urs_limit)}
                                    </div>
                                  )}
                                  {tr.compared ? (
                                    <span
                                      className={`inline-block rounded-full border px-2 py-0.5 text-[11px] font-semibold ${
                                        tr.deviates
                                          ? "border-fail-edge bg-fail-soft text-fail"
                                          : "border-pass-edge bg-pass-soft text-pass"
                                      }`}
                                    >
                                      {t(tr.deviates ? "deviates" : "within")}
                                    </span>
                                  ) : (
                                    tr.not_compared && (
                                      <span className="inline-block text-[11px] text-warn">
                                        {t("notComparedBecause", { reason: tr.not_compared })}
                                      </span>
                                    )
                                  )}
                                </li>
                              ))}
                            </ul>
                            {st.traced.length === 0 && st.not_compared && (
                              <div className="text-[11px] text-warn">
                                {t("notComparedBecause", { reason: st.not_compared })}
                              </div>
                            )}
                          </td>
                          <td className="px-3 py-2.5 align-top">
                            <CompactComparators
                              t={t}
                              step={st}
                              vendorDocs={draft.vendor_documents}
                            />
                          </td>
                          <td className="px-3 py-2.5 align-top">
                            {stepFindings.length === 0 ? (
                              <span className="text-ink-muted">{t("noFinding")}</span>
                            ) : (
                              <div className="space-y-1.5">
                                {stepFindings.map((f, i) => (
                                  <div key={`${f.finding.requirement}/${i}`} className="space-y-1">
                                    <div className="font-semibold text-fail">
                                      {t(`types.${f.finding.type}`)}
                                    </div>
                                    {f.proposal && <DecisionStateBadge state={f.proposal.state} />}
                                  </div>
                                ))}
                              </div>
                            )}
                          </td>
                        </>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Section 2: Findings about the whole document (below the table) */}
      <section aria-labelledby="draft-document" className="space-y-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div className="flex items-center gap-2">
            <h2 id="draft-document" className="m-0 text-sm font-bold text-ink">
              {t("documentFindings")}
            </h2>
            <span className="rounded-full bg-sunken px-2 py-0.5 text-xs font-semibold text-ink-muted tabular-nums">
              {whole.length}
            </span>
          </div>
          <p className="m-0 text-xs text-ink-muted">{t("documentFindingsNote")}</p>
        </div>

        {whole.length === 0 ? (
          <div className="rounded-lg border border-border bg-surface p-4 text-xs text-ink-muted">
            {t("noDocumentFinding")}
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border bg-surface">
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-border bg-canvas text-ink-muted">
                  <th scope="col" className="px-3 py-2 font-semibold">
                    {t("requirement")}
                  </th>
                  <th scope="col" className="px-3 py-2 font-semibold">
                    {t("findings")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {whole.map((f, i) => (
                  <tr key={`${f.finding.requirement}/${i}`}>
                    <th
                      scope="row"
                      className="px-3 py-3 align-top font-mono font-bold text-ink tabular-nums whitespace-nowrap"
                    >
                      {f.finding.row ?? f.finding.requirement}
                    </th>
                    <td className="space-y-3 px-3 py-3 align-top">
                      <div className="space-y-1">
                        <div className="font-bold text-ink">
                          {t(`types.${f.finding.type}`)}
                        </div>
                        <p className="m-0 text-ink">{f.finding.detail}</p>
                      </div>
                      <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
                        {f.finding.citations.map((c) => (
                          <li key={`${c.doc}/${c.rev}/${c.page}/${c.quote}`}>
                            <AnyCite cite={c} runId={runId} draftDoc={draftDoc} />
                          </li>
                        ))}
                      </ul>
                      {f.proposal && (
                        <FindingDecisionPanel
                          key={`whole-${f.proposal.id}-${f.proposal.state}-${f.proposal.decisions[0]?.id ?? 0}`}
                          proposal={f.proposal}
                          runId={runId}
                          screen="draft"
                          access={decisions.access}
                        />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

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

      {/* Slide-Over Step Inspection & Decision Drawer */}
      <DraftStepDrawer
        step={selectedStep}
        findings={selectedStep ? (findingsByStep.get(selectedStep.id) ?? []) : []}
        vendorDocs={draft.vendor_documents}
        draftDoc={draftDoc}
        runId={runId}
        decisions={decisions}
        open={selectedStep !== null}
        stepIndex={selectedIndex}
        totalSteps={filteredSteps.length}
        dirtyPrompt={pendingStepId !== undefined}
        onClose={() => requestSelection(null)}
        onPrev={() => {
          if (selectedIndex > 0) {
            const prev = filteredSteps[selectedIndex - 1];
            if (prev) requestSelection(prev.id);
          }
        }}
        onNext={() => {
          if (selectedIndex >= 0 && selectedIndex < filteredSteps.length - 1) {
            const next = filteredSteps[selectedIndex + 1];
            if (next) requestSelection(next.id);
          }
        }}
        onDirtyChange={setIsFormDirty}
        onDiscardAndProceed={() => {
          if (pendingStepId !== undefined) applySelection(pendingStepId);
        }}
        onCancelProceed={() => setPendingStepId(undefined)}
      />
    </div>
  );
}
