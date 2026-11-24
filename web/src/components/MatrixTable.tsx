"use client";

import { ArrowRight, ChevronDown, FileWarning, RotateCcw } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { CoverageClass, Matrix, Proposal } from "@/api/client";
import type { DecisionView } from "@/components/Decisions";
import { DecisionCountsSummary, DecisionNoticeBanner } from "@/components/FindingDecisionPanel";
import { MatrixDrawer } from "@/components/MatrixDrawer";
import { formatValue, RequiredObservedUnit } from "@/components/RequiredObservedUnit";
import { useRunShell } from "@/components/RunShellContext";
import { FilterBar, type FilterPillOption } from "@/components/ui/FilterBar";

export { formatValue };
import {
  CoverageStatusBadge,
  DecisionStateBadge,
  type CoverageBadgeKey,
} from "@/components/ui/StatusBadge";

const RISK: readonly CoverageBadgeKey[] = [
  "conflict",
  "gap",
  "partial",
  "site_only",
  "covered_by_vendor",
  "none",
];

const STATES: readonly Proposal["state"][] = ["undecided", "changed", "decided"];

export type MatrixFilter = {
  coverage?: CoverageBadgeKey;
  status?: Proposal["state"];
};

function buildMatrixUrl(
  base: string,
  coverage: CoverageBadgeKey | undefined,
  status: Proposal["state"] | undefined,
  selected: string | null,
): string {
  const qs = new URLSearchParams();
  if (coverage) qs.set("coverage", coverage);
  if (status) qs.set("status", status);
  if (selected) qs.set("selected", selected);
  const query = qs.toString();
  return query ? `${base}?${query}` : base;
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.closest(
      'input, textarea, select, [contenteditable], [contenteditable="true"], [role="listbox"], [role="menu"], [role="combobox"]',
    ) !== null
  );
}

export function MatrixTable({
  matrix,
  runId,
  decisions,
  filter,
  initialSelected = null,
  title,
}: {
  matrix: Matrix;
  runId: string;
  decisions: DecisionView;
  filter?: MatrixFilter;
  initialSelected?: string | null;
  title?: string;
}) {
  const t = useTranslations("matrix");
  const td = useTranslations("decisions");
  const th = useTranslations("runHeader");
  const { setDrawerOpen } = useRunShell();

  const [activeCoverage, setActiveCoverage] = useState<CoverageBadgeKey | undefined>(
    filter?.coverage,
  );
  const [activeStatus, setActiveStatus] = useState<Proposal["state"] | undefined>(
    decisions.proposals !== undefined ? filter?.status : undefined,
  );
  const [selectedId, setSelectedId] = useState<string | null>(initialSelected);
  const [legendOpen, setLegendOpen] = useState(false);

  // Dirty-form guard state
  const [isFormDirty, setIsFormDirty] = useState(false);
  const [pendingTargetId, setPendingTargetId] = useState<string | null | undefined>(undefined);

  const byRequirement = useMemo(
    () =>
      new Map(
        (decisions.proposals ?? [])
          .filter((p) => p.kind === "coverage")
          .map((p) => [p.requirement, p] as const),
      ),
    [decisions.proposals],
  );

  const decided = decisions.proposals !== undefined;
  const isFiltered = activeCoverage !== undefined || activeStatus !== undefined;

  const filteredRows = useMemo(
    () =>
      matrix.requirements.filter((row) => {
        if (activeCoverage !== undefined && (row.coverage ?? "none") !== activeCoverage) {
          return false;
        }
        if (activeStatus !== undefined) {
          const state = byRequirement.get(row.id)?.state ?? "undecided";
          if (state !== activeStatus) return false;
        }
        return true;
      }),
    [matrix.requirements, activeCoverage, activeStatus, byRequirement],
  );

  const base = `/runs/${encodeURIComponent(runId)}`;

  const syncUrl = useCallback(
    (
      cov: CoverageBadgeKey | undefined,
      st: Proposal["state"] | undefined,
      sel: string | null,
    ) => {
      if (typeof window === "undefined") return;
      const next = buildMatrixUrl(base, cov, st, sel);
      window.history.replaceState(null, "", next);
    },
    [base],
  );

  // Wire drawer open/close state with RunShellContext so left sidebar auto-collapses below 1440px
  useEffect(() => {
    setDrawerOpen(selectedId !== null);
    return () => setDrawerOpen(false);
  }, [selectedId, setDrawerOpen]);

  useEffect(() => {
    if (!selectedId || typeof document === "undefined") return;
    const el = document.getElementById(selectedId);
    if (el && typeof el.scrollIntoView === "function") {
      el.scrollIntoView({ block: "nearest" });
    }
  }, [selectedId]);

  const applySelection = useCallback(
    (nextId: string | null) => {
      setSelectedId(nextId);
      setIsFormDirty(false);
      setPendingTargetId(undefined);
      syncUrl(activeCoverage, activeStatus, nextId);
    },
    [activeCoverage, activeStatus, syncUrl],
  );

  const requestSelection = useCallback(
    (nextId: string | null) => {
      if (nextId === selectedId) return;
      if (selectedId !== null && isFormDirty) {
        setPendingTargetId(nextId);
        return;
      }
      applySelection(nextId);
    },
    [selectedId, isFormDirty, applySelection],
  );

  const applyFilters = useCallback(
    (cov: CoverageBadgeKey | undefined, st: Proposal["state"] | undefined) => {
      setActiveCoverage(cov);
      setActiveStatus(decided ? st : undefined);
      syncUrl(cov, decided ? st : undefined, selectedId);
    },
    [decided, selectedId, syncUrl],
  );

  const selectedIndex = useMemo(
    () => (selectedId ? filteredRows.findIndex((r) => r.id === selectedId) : -1),
    [filteredRows, selectedId],
  );
  const selectedRow =
    selectedId !== null
      ? (filteredRows.find((r) => r.id === selectedId) ??
        matrix.requirements.find((r) => r.id === selectedId) ??
        null)
      : null;

  // J/K keyboard shortcuts (disabled inside inputs/menus/combos or with modifier keys)
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key !== "j" && e.key !== "J" && e.key !== "k" && e.key !== "K") return;
      if (isTypingTarget(e.target)) return;
      if (filteredRows.length === 0) return;

      e.preventDefault();
      const goingDown = e.key === "j" || e.key === "J";
      if (selectedIndex === -1) {
        const first = filteredRows[0];
        if (first) requestSelection(first.id);
        return;
      }
      const nextIdx = goingDown
        ? Math.min(selectedIndex + 1, filteredRows.length - 1)
        : Math.max(selectedIndex - 1, 0);
      const target = filteredRows[nextIdx];
      if (target) requestSelection(target.id);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [filteredRows, selectedIndex, requestSelection]);

  const countsByClass = useMemo(() => {
    const map = new Map<CoverageBadgeKey, number>();
    for (const r of matrix.requirements) {
      const k: CoverageBadgeKey = r.coverage ?? "none";
      map.set(k, (map.get(k) ?? 0) + 1);
    }
    return map;
  }, [matrix.requirements]);

  const undecidedCount = useMemo(() => {
    if (!decided) return 0;
    return matrix.requirements.filter((r) => (byRequirement.get(r.id)?.state ?? "undecided") === "undecided").length;
  }, [decided, matrix.requirements, byRequirement]);

  const qs = new URLSearchParams();
  if (activeCoverage) qs.set("coverage", activeCoverage);
  if (activeStatus) qs.set("status", activeStatus);
  const returnQuery = qs.toString() || undefined;

  type BlockerFilterId = "all" | "conflict" | "gap" | "undecided";
  const activeBlockerId: BlockerFilterId =
    !isFiltered
      ? "all"
      : activeCoverage === "conflict" && activeStatus === undefined
        ? "conflict"
        : activeCoverage === "gap" && activeStatus === undefined
          ? "gap"
          : activeStatus === "undecided" && activeCoverage === undefined
            ? "undecided"
            : "all";

  const blockerOptions: FilterPillOption<BlockerFilterId>[] = [
    { id: "all", label: t("filterBlockers.all"), count: matrix.requirements.length },
    {
      id: "conflict",
      label: t("filterBlockers.conflict"),
      count: countsByClass.get("conflict") ?? 0,
      activeClass: "border-cov-conflict-edge bg-cov-conflict-bg text-cov-conflict-fg",
    },
    {
      id: "gap",
      label: t("filterBlockers.gap"),
      count: countsByClass.get("gap") ?? 0,
      activeClass: "border-cov-gap-edge bg-cov-gap-bg text-cov-gap-fg",
    },
    ...(decided
      ? [
          {
            id: "undecided" as const,
            label: t("filterBlockers.undecided"),
            count: undecidedCount,
          },
        ]
      : []),
  ];

  const handleBlockerSelect = (id: BlockerFilterId) => {
    if (id === "all") applyFilters(undefined, undefined);
    else if (id === "conflict")
      applyFilters(activeCoverage === "conflict" ? undefined : "conflict", undefined);
    else if (id === "gap") applyFilters(activeCoverage === "gap" ? undefined : "gap", undefined);
    else applyFilters(undefined, activeStatus === "undecided" ? undefined : "undecided");
  };

  return (
    <div className="space-y-2.5">
      {(title || decisions.counts) && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          {title && <h1 className="m-0 text-lg font-bold text-ink">{title}</h1>}
          <DecisionCountsSummary
            counts={decisions.counts}
            kinds={["coverage", "test_step"]}
            progressKinds={["coverage"]}
          />
        </div>
      )}

      <DecisionNoticeBanner view={decisions} />

      {/* Compact 1-line clickable coverage summary + legend + not-read jump */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-surface px-3 py-2">
        <ul
          aria-label={t("summaryTitle")}
          className="m-0 flex list-none flex-wrap items-center gap-1 p-0"
        >
          {RISK.map((k) => {
            const count = countsByClass.get(k) ?? 0;
            const active = activeCoverage === k;
            return (
              <li key={k}>
                <button
                  type="button"
                  aria-pressed={active}
                  onClick={() => applyFilters(active ? undefined : k, activeStatus)}
                  className={`inline-flex cursor-pointer items-center gap-1 rounded-md border px-1.5 py-0.5 transition-colors ${
                    active
                      ? "border-accent bg-accent-soft"
                      : "border-transparent hover:bg-sunken"
                  } ${count === 0 && !active ? "opacity-55" : ""}`}
                >
                  <span className="text-xs font-bold text-ink tabular-nums">{count}</span>
                  <CoverageStatusBadge coverage={k} size="xs" />
                </button>
              </li>
            );
          })}
        </ul>
        <div className="flex flex-wrap items-center gap-1.5">
          {matrix.not_read.length > 0 && (
            <a
              href="#matrix-not-read"
              className="inline-flex items-center gap-1 rounded border border-warn-edge bg-warn-soft px-2 py-0.5 text-[11px] font-semibold text-warn no-underline hover:opacity-85 tabular-nums"
            >
              <FileWarning className="h-3 w-3 shrink-0" aria-hidden="true" />
              <span>{t("notReadJump", { count: matrix.not_read.length })}</span>
            </a>
          )}
          <button
            type="button"
            aria-expanded={legendOpen}
            onClick={() => setLegendOpen((o) => !o)}
            className="inline-flex cursor-pointer items-center gap-1 rounded border border-border bg-canvas px-2 py-0.5 text-[11px] font-medium text-ink-muted hover:bg-sunken hover:text-ink"
          >
            <span>{t("legendTitle")}</span>
            <ChevronDown
              className={`h-3 w-3 transition-transform ${legendOpen ? "rotate-180" : ""}`}
              aria-hidden="true"
            />
          </button>
        </div>
      </div>

      {legendOpen && (
        <dl className="m-0 grid grid-cols-1 gap-2 rounded-lg border border-border bg-surface p-3 text-xs sm:grid-cols-2 lg:grid-cols-3">
          {RISK.map((k) => (
            <div key={k} className="flex items-start gap-2">
              <dt className="shrink-0">
                <CoverageStatusBadge coverage={k} size="xs" />
              </dt>
              <dd className="m-0 text-ink-muted">{t(`help.${k}`)}</dd>
            </div>
          ))}
        </dl>
      )}

      {/* 1-click blocker filter pills + secondary select filters */}
      <FilterBar
        ariaLabel={t("filterCoverage")}
        options={blockerOptions}
        activeId={activeBlockerId}
        onSelect={handleBlockerSelect}
        trailing={
          <>
            <select
              aria-label={t("filterCoverage")}
              value={activeCoverage ?? ""}
              onChange={(e) => {
                const val = e.target.value as CoverageBadgeKey | "";
                applyFilters(val === "" ? undefined : val, activeStatus);
              }}
              className="h-8 rounded-md border border-border bg-surface px-2 text-xs text-ink"
            >
              <option value="">{t("filterAll")}</option>
              {RISK.map((k) => (
                <option key={k} value={k}>
                  {t(`classes.${k}`)}
                </option>
              ))}
            </select>
            {decided && (
              <select
                aria-label={t("filterStatus")}
                value={activeStatus ?? ""}
                onChange={(e) => {
                  const val = e.target.value as Proposal["state"] | "";
                  applyFilters(activeCoverage, val === "" ? undefined : val);
                }}
                className="h-8 rounded-md border border-border bg-surface px-2 text-xs text-ink"
              >
                <option value="">{t("filterAll")}</option>
                {STATES.map((st) => (
                  <option key={st} value={st}>
                    {td(`states.${st}`)}
                  </option>
                ))}
              </select>
            )}
            {isFiltered && (
              <>
                <button
                  type="button"
                  onClick={() => applyFilters(undefined, undefined)}
                  className="inline-flex h-8 cursor-pointer items-center gap-1 rounded-md border border-border bg-surface px-2.5 text-xs font-medium text-ink-muted hover:bg-sunken hover:text-ink"
                >
                  <RotateCcw className="h-3 w-3" aria-hidden="true" />
                  <span>{t("filterReset")}</span>
                </button>
                <span className="text-xs text-ink-muted tabular-nums">
                  {t("filterCount", {
                    shown: filteredRows.length,
                    total: matrix.requirements.length,
                  })}
                </span>
              </>
            )}
          </>
        }
      />

      {/* Opsi A 4-column compact table */}
      {filteredRows.length === 0 && isFiltered ? (
        <div className="rounded-lg border border-border bg-surface p-8 text-center text-sm text-ink-muted">
          {t("filterEmpty")}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-surface shadow-xs">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-border bg-sunken/70 text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
                <th scope="col" className="sticky top-0 z-10 w-[33%] bg-sunken/95 px-3 py-2">
                  {t("requirement")}
                </th>
                <th scope="col" className="sticky top-0 z-10 w-[35%] bg-sunken/95 px-3 py-2">
                  {t("disyaratkan")} / {t("teramati")}
                </th>
                <th scope="col" className="sticky top-0 z-10 w-[16%] bg-sunken/95 px-3 py-2">
                  {t("coverage")}
                </th>
                <th scope="col" className="sticky top-0 z-10 w-[16%] bg-sunken/95 px-3 py-2">
                  {td("column")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredRows.map((row) => {
                const proposal = byRequirement.get(row.id);
                const proposed: CoverageBadgeKey = row.coverage ?? "none";
                const current = proposal?.state === "decided" ? proposal.decisions[0] : undefined;
                const decidedClass: CoverageClass | null | undefined =
                  current?.decision === "edited" ? current.coverage : null;
                const isSelected = selectedId === row.id;
                const badgeState =
                  proposal?.state === "decided" && current ? current.decision : proposal?.state;

                return (
                  <tr
                    key={row.id}
                    id={row.id}
                    data-testid={row.id}
                    className={`group transition-colors ${
                      isSelected
                        ? "bg-accent-soft shadow-[inset_3px_0_0_var(--color-accent)]"
                        : "hover:bg-sunken/40"
                    }`}
                  >
                    <td className="px-3 py-2 align-middle">
                      <div className="flex flex-col gap-0.5">
                        <div className="flex items-center justify-between gap-2">
                          <button
                            type="button"
                            onClick={() => requestSelection(row.id)}
                            aria-expanded={isSelected}
                            aria-label={row.id}
                            className="w-fit cursor-pointer rounded text-left text-xs font-bold text-accent tabular-nums underline decoration-accent/40 underline-offset-2 hover:text-accent-hover hover:decoration-accent"
                          >
                            {row.id}
                          </button>
                          <span
                            aria-hidden="true"
                            className="text-[11px] font-medium text-accent opacity-0 transition-opacity group-hover:opacity-100"
                          >
                            {t("inspectRow")} →
                          </span>
                        </div>
                        <p className="m-0 line-clamp-1 text-xs text-ink" title={row.text}>
                          {row.text}
                        </p>
                      </div>
                    </td>
                    <td className="px-3 py-2 align-middle">
                      <RequiredObservedUnit row={row} runId={runId} variant="compact" />
                    </td>
                    <td className="px-3 py-2 align-middle">
                      <div className="flex flex-wrap items-center gap-1">
                        <CoverageStatusBadge coverage={proposed} size="xs" />
                        {decidedClass != null && (
                          <>
                            <span aria-hidden="true" className="text-xs text-ink-muted">
                              →
                            </span>
                            <span className="sr-only">{t("decidedClass")}</span>
                            <CoverageStatusBadge coverage={decidedClass} size="xs" />
                          </>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2 align-middle">
                      {badgeState !== undefined ? (
                        <DecisionStateBadge state={badgeState} />
                      ) : (
                        <span className="text-xs text-ink-muted">{t("drawer.readOnlyCell")}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Preserved matrix.not_read panel */}
      {matrix.not_read.length > 0 && (
        <section id="matrix-not-read" className="rounded-lg border border-warn-edge bg-warn-soft p-4">
          <div className="flex items-center gap-2 text-sm font-bold text-warn">
            <FileWarning className="h-4 w-4 shrink-0" aria-hidden="true" />
            <h2 className="m-0 text-sm font-bold text-warn">{t("notRead")}</h2>
          </div>
          <ul className="mt-2 mb-0 list-disc space-y-1 pl-5 text-xs text-ink">
            {matrix.not_read.map((d) => (
              <li key={`${d.doc_id}/${d.rev}`} className="tabular-nums">
                {d.doc_id} rev {d.rev} ({d.format})
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Handoff bar */}
      <nav
        aria-label={th("handoffTitle")}
        className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface px-4 py-3"
      >
        <span className="text-xs font-semibold text-ink-muted">{th("handoffTitle")}</span>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href={`${base}/findings`}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-canvas px-3 py-1.5 text-xs font-semibold text-ink no-underline hover:bg-sunken"
          >
            <span>{th("toFindings")}</span>
            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
          <Link
            href={`${base}/protocol`}
            className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent no-underline hover:bg-accent-hover"
          >
            <span>{th("toProtocol")}</span>
            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>
      </nav>

      {/* Slide-over drawer */}
      <MatrixDrawer
        row={selectedRow}
        proposal={selectedRow ? byRequirement.get(selectedRow.id) : undefined}
        runId={runId}
        decisions={decisions}
        returnQuery={returnQuery}
        open={selectedRow !== null}
        rowIndex={selectedIndex}
        totalRows={filteredRows.length}
        dirtyPrompt={pendingTargetId !== undefined}
        onClose={() => requestSelection(null)}
        onPrev={() => {
          if (selectedIndex > 0) {
            const prev = filteredRows[selectedIndex - 1];
            if (prev) requestSelection(prev.id);
          }
        }}
        onNext={() => {
          if (selectedIndex >= 0 && selectedIndex < filteredRows.length - 1) {
            const next = filteredRows[selectedIndex + 1];
            if (next) requestSelection(next.id);
          }
        }}
        onDirtyChange={setIsFormDirty}
        onDiscardAndProceed={() => {
          if (pendingTargetId !== undefined) {
            applySelection(pendingTargetId);
          }
        }}
        onCancelProceed={() => setPendingTargetId(undefined)}
      />
    </div>
  );
}
