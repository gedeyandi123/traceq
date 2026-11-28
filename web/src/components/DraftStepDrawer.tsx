"use client";

import { CheckCircle2, ChevronLeft, ChevronRight, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";

import type { Cite, DraftFindingView, DraftTestStep, ProtocolDraftView as Draft } from "@/api/client";
import type { DecisionView } from "@/components/Decisions";
import { FindingDecisionPanel } from "@/components/FindingDecisionPanel";
import { DirtyGuardBanner } from "@/components/ui/DirtyGuardBanner";
import { Drawer } from "@/components/ui/Drawer";
import { PdfCitationButton } from "@/components/ui/PdfCitationModal";

type T = ReturnType<typeof useTranslations<"draft">>;
type VendorDoc = Draft["vendor_documents"][number];
type Comparator = DraftTestStep["traced"][number]["comparators"][number];

const number = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 3 });

/** A value as code read it from the print, in a few characters. */
export function formatPrinted(t: T, v: DraftTestStep["traced"][number]["urs_limit"] & object): string {
  switch (v.type) {
    case "range": {
      if (v.min != null && v.max != null) {
        return `${number.format(v.min)}–${number.format(v.max)} ${v.unit}`;
      }
      if (v.min != null) {
        return t(v.min_exclusive ? "values.above" : "values.atLeast", {
          min: number.format(v.min),
          unit: v.unit,
        });
      }
      return t(v.max_exclusive ? "values.below" : "values.atMost", {
        max: number.format(v.max ?? 0),
        unit: v.unit,
      });
    }
    case "number":
      return `${number.format(v.value)} ${v.unit}`;
    case "tolerance":
      return t("values.tolerance", {
        nominal: number.format(v.nominal),
        unit: v.unit,
        tolerance: number.format(v.tolerance),
        toleranceUnit: v.tolerance_unit,
      });
    case "text":
      return v.value;
    case "ambiguous":
      return t("values.ambiguous", {
        readings: v.readings.map((r) => number.format(r)).join(" / "),
      });
  }
}

/** A citation into the draft: opens the PDF citation modal at the cited page. */
export function DraftCite({ cite, runId }: { cite: Cite; runId: string }) {
  return <PdfCitationButton runId={runId} cite={cite} compact />;
}

/** A citation: opens the PDF citation modal for both draft and corpus documents. */
export function AnyCite({
  cite,
  runId,
  draftDoc,
}: {
  cite: Cite;
  runId: string;
  draftDoc: string;
}) {
  return cite.doc === draftDoc ? (
    <DraftCite cite={cite} runId={runId} />
  ) : (
    <PdfCitationButton runId={runId} cite={cite} compact />
  );
}

function Facts({
  step,
  of,
  runId,
}: {
  step: DraftTestStep;
  of: (c: Comparator) => boolean;
  runId: string;
}) {
  const many = step.traced.length > 1;
  const facts = step.traced.flatMap((tr) =>
    tr.comparators
      .filter(of)
      .flatMap((c) => c.facts.map((f) => ({ requirement: tr.requirement, c, f }))),
  );
  return (
    <ul className="m-0 mt-1 list-none space-y-1.5 pl-3">
      {facts.map(({ requirement, c, f }) => (
        <li
          key={`${requirement}/${c.doc}/${f.name}/${f.citation.quote}`}
          className="flex flex-wrap items-center gap-1.5 text-xs text-ink"
        >
          <span>
            {many && <span className="font-mono font-semibold">{requirement} </span>}
            <span className="font-medium">{f.name}:</span> {f.printed}
          </span>
          <PdfCitationButton runId={runId} cite={f.citation} compact />
        </li>
      ))}
    </ul>
  );
}

function DrawerComparators({
  t,
  step,
  vendorDocs,
  runId,
}: {
  t: T;
  step: DraftTestStep;
  vendorDocs: readonly VendorDoc[];
  runId: string;
}) {
  const same = (d: { doc: string; rev: number }) => (c: Comparator) =>
    c.doc === d.doc && c.rev === d.rev;
  const listed = (c: Comparator) => vendorDocs.some((d) => same(d)(c));
  const others = [
    ...new Map(
      step.traced.flatMap((tr) =>
        tr.comparators.filter((c) => !listed(c)).map((c) => [`${c.doc}/${c.rev}`, c] as const),
      ),
    ).values(),
  ];

  if (vendorDocs.length === 0 && others.length === 0) {
    return <p className="m-0 text-xs text-ink-muted">{t("noComparators")}</p>;
  }

  return (
    <ul className="m-0 list-none space-y-2 p-0">
      {vendorDocs.map((d) => {
        const has = step.traced.some((tr) =>
          tr.comparators.some((c) => same(d)(c) && c.facts.length > 0),
        );
        return (
          <li key={`${d.doc}/${d.rev}`} className="rounded-md border border-border bg-sunken p-2.5 text-xs">
            <div className="font-semibold text-ink">
              {t(`vendorKinds.${d.kind}`)} {d.doc}:
            </div>
            {has ? (
              <Facts step={step} of={same(d)} runId={runId} />
            ) : (
              <div className="mt-0.5 text-ink-muted">{t("noComparators")}</div>
            )}
          </li>
        );
      })}
      {others.map((c) => (
        <li key={`${c.doc}/${c.rev}`} className="rounded-md border border-border bg-sunken p-2.5 text-xs">
          <div className="font-semibold text-ink">
            {t(`comparatorKinds.${c.kind}`)} {c.doc}:
          </div>
          <Facts step={step} of={same(c)} runId={runId} />
        </li>
      ))}
    </ul>
  );
}

export function DraftStepDrawer({
  step,
  findings,
  vendorDocs,
  draftDoc,
  runId,
  decisions,
  open,
  stepIndex,
  totalSteps,
  dirtyPrompt,
  onClose,
  onPrev,
  onNext,
  onDirtyChange,
  onDiscardAndProceed,
  onCancelProceed,
}: {
  step: DraftTestStep | null;
  findings: readonly DraftFindingView[];
  vendorDocs: readonly VendorDoc[];
  draftDoc: string;
  runId: string;
  decisions: DecisionView;
  open: boolean;
  stepIndex: number;
  totalSteps: number;
  dirtyPrompt: boolean;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
  onDirtyChange: (dirty: boolean) => void;
  onDiscardAndProceed: () => void;
  onCancelProceed: () => void;
}) {
  const t = useTranslations("draft");

  if (!step) {
    return (
      <Drawer open={false} onOpenChange={() => {}} title="">
        {null}
      </Drawer>
    );
  }

  return (
    <Drawer
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
      title={step.id}
      description={
        step.requirements.length > 0
          ? t("tracesTo", { requirements: step.requirements.join(", ") })
          : undefined
      }
      headerExtra={
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onPrev}
            disabled={stepIndex <= 0}
            aria-label={t("drawer.prev")}
            className="inline-flex h-7 cursor-pointer items-center gap-1 rounded border border-border bg-surface px-2 text-xs font-medium text-ink hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-45"
          >
            <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">{t("drawer.prev")}</span>
          </button>
          <span className="px-1.5 text-xs font-medium text-ink-muted tabular-nums">
            {t("drawer.position", { current: stepIndex + 1, total: totalSteps })}
          </span>
          <button
            type="button"
            onClick={onNext}
            disabled={stepIndex < 0 || stepIndex >= totalSteps - 1}
            aria-label={t("drawer.next")}
            className="inline-flex h-7 cursor-pointer items-center gap-1 rounded border border-border bg-surface px-2 text-xs font-medium text-ink hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-45"
          >
            <span className="hidden sm:inline">{t("drawer.next")}</span>
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        {dirtyPrompt && (
          <DirtyGuardBanner
            message={t("drawer.dirtyWarning")}
            discardLabel={t("drawer.discardChanges")}
            keepLabel={t("drawer.keepEditing")}
            onDiscard={onDiscardAndProceed}
            onKeep={onCancelProceed}
          />
        )}

        {/* Acceptance criteria */}
        <section className="space-y-2 rounded-lg border border-border bg-sunken p-3.5">
          <h3 className="m-0 text-xs font-bold tracking-wide text-ink-muted uppercase">
            {t("ac")}
          </h3>
          {step.acceptance === null ? (
            <p className="m-0 text-xs font-medium text-warn">
              {t("notRead", { reason: step.not_read ?? "" })}
            </p>
          ) : (
            <div className="space-y-1.5">
              <div className="text-sm font-semibold text-ink">{step.acceptance.printed}</div>
              {step.acceptance.value === null && (
                <div className="text-xs text-ink-muted">{t("notParsed")}</div>
              )}
              <DraftCite cite={step.acceptance.citation} runId={runId} />
            </div>
          )}
        </section>

        {/* Traced URS requirements */}
        {step.acceptance !== null && (
          <section className="space-y-2.5 rounded-lg border border-border bg-surface p-3.5">
            <h3 className="m-0 text-xs font-bold tracking-wide text-ink-muted uppercase">
              {t("urs")}
            </h3>
            {step.traced.length === 0 && step.not_compared && (
              <p className="m-0 text-xs text-warn">
                {t("notComparedBecause", { reason: step.not_compared })}
              </p>
            )}
            <ul className="m-0 list-none space-y-2.5 p-0">
              {step.traced.map((tr) => (
                <li
                  key={tr.requirement}
                  className="space-y-1.5 rounded-md border border-border bg-sunken p-2.5 text-xs"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-mono font-bold text-ink tabular-nums">
                      {tr.requirement}
                    </span>
                    {tr.compared ? (
                      <span
                        className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${
                          tr.deviates
                            ? "border-fail-edge bg-fail-soft text-fail"
                            : "border-pass-edge bg-pass-soft text-pass"
                        }`}
                      >
                        {tr.deviates ? (
                          <XCircle className="h-3 w-3 shrink-0" aria-hidden="true" />
                        ) : (
                          <CheckCircle2 className="h-3 w-3 shrink-0" aria-hidden="true" />
                        )}
                        <span>{t(tr.deviates ? "deviates" : "within")}</span>
                      </span>
                    ) : (
                      tr.not_compared && (
                        <span className="rounded-full border border-warn-edge bg-warn-soft px-2 py-0.5 text-[11px] font-medium text-warn">
                          {t("notComparedBecause", { reason: tr.not_compared })}
                        </span>
                      )
                    )}
                  </div>
                  {tr.urs_limit && (
                    <div className="font-medium text-ink tabular-nums">
                      {formatPrinted(t, tr.urs_limit)}
                    </div>
                  )}
                  {tr.not_parsed && (
                    <div className="text-ink-muted">
                      {t("ursNotRead", { reason: tr.not_parsed })}
                    </div>
                  )}
                  {tr.citation && (
                    <div>
                      <PdfCitationButton runId={runId} cite={tr.citation} compact />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Comparators */}
        {step.acceptance !== null && (
          <section className="space-y-2.5 border-t border-border pt-4">
            <h3 className="m-0 text-xs font-bold tracking-wide text-ink-muted uppercase">
              {t("comparators")}
            </h3>
            <DrawerComparators t={t} step={step} vendorDocs={vendorDocs} runId={runId} />
          </section>
        )}

        {/* Step findings & decisions */}
        <section className="space-y-3 border-t border-border pt-4">
          <h3 className="m-0 text-xs font-bold tracking-wide text-ink-muted uppercase">
            {t("findings")}
          </h3>
          {findings.length === 0 ? (
            <p className="m-0 rounded-md bg-sunken p-3 text-xs text-ink-muted">
              {t("noFinding")}
            </p>
          ) : (
            findings.map((f, i) => (
              <div
                key={`${f.finding.requirement}/${i}`}
                className="space-y-3 rounded-md border-l-2 border-fail bg-sunken/60 p-3"
              >
                <div className="space-y-1">
                  <div className="text-xs font-bold text-fail">
                    {t(`types.${f.finding.type}`)}
                  </div>
                  {f.finding.label && (
                    <div className="text-xs text-ink-muted">{t("notReviewed")}</div>
                  )}
                  <p className="m-0 text-xs leading-relaxed text-ink">{f.finding.detail}</p>
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
                    key={`${step.id}-${f.proposal.id}-${f.proposal.state}-${f.proposal.decisions[0]?.id ?? 0}`}
                    proposal={f.proposal}
                    runId={runId}
                    screen="draft"
                    access={decisions.access}
                    embedded
                    onDirtyChange={onDirtyChange}
                  />
                )}
              </div>
            ))
          )}
        </section>
      </div>
    </Drawer>
  );
}
