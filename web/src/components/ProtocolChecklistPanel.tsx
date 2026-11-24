"use client";

import { AlertTriangle, CheckCircle2, ChevronDown } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import type { ChecklistItem } from "@/api/client";
import type { ProtocolControls } from "./AssembledProtocolView";
import { Modal } from "./ui/Modal";
import { SubmitButton } from "./ui/SubmitButton";

type T = ReturnType<typeof useTranslations<"protocol">>;

const MAX_INLINE_BLOCKERS = 4;

/** Sticky Submission Readiness Bar: shows the five checklist checks with their counts and
 * deep-links to the rows or missed numbers concerned, plus the submit control with confirmation modal. */
export function ProtocolChecklistPanel({
  t,
  items,
  runId,
  protocolId,
  controls,
  onNavigateToRow,
  onNavigateToMissed,
}: {
  t: T;
  items: readonly ChecklistItem[];
  runId: string;
  protocolId: number;
  controls: ProtocolControls;
  onNavigateToRow?: (requirement: string) => void;
  onNavigateToMissed?: () => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [submitOpen, setSubmitOpen] = useState(false);
  const blocked = items.some((i) => i.count > 0);

  return (
    <section
      aria-labelledby="protocol-checklist"
      className="z-20 space-y-2.5 rounded-lg border border-border bg-surface/95 px-4 py-3 shadow-sm backdrop-blur-[2px] lg:sticky lg:top-12"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {blocked ? (
            <AlertTriangle className="h-4 w-4 shrink-0 text-warn" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="h-4 w-4 shrink-0 text-pass" aria-hidden="true" />
          )}
          <div>
            <h2 id="protocol-checklist" className="m-0 text-sm font-bold text-ink">
              {t("checklist.title")}
            </h2>
            <p className="m-0 text-xs text-ink-muted">
              {blocked ? t("checklist.note") : t("checklist.ready")}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            aria-expanded={!collapsed}
            onClick={() => setCollapsed((c) => !c)}
            className="inline-flex h-8 cursor-pointer items-center gap-1 rounded-md border border-border bg-surface px-2.5 text-xs font-medium text-ink-muted hover:bg-sunken hover:text-ink"
          >
            <span>{t(collapsed ? "checklist.expand" : "checklist.collapse")}</span>
            <ChevronDown
              className={`h-3.5 w-3.5 transition-transform ${collapsed ? "" : "rotate-180"}`}
              aria-hidden="true"
            />
          </button>

          {controls !== null && (
            <>
              <button
                type="button"
                disabled={blocked}
                onClick={() => setSubmitOpen(true)}
                className="inline-flex h-8 cursor-pointer items-center justify-center rounded-md bg-accent px-3 text-xs font-semibold text-on-accent transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-55"
              >
                {t("submit")}
              </button>
              <Modal
                open={submitOpen}
                onOpenChange={setSubmitOpen}
                size="sm"
                title={t("submitModalTitle")}
                description={t("submitModalDesc")}
              >
                <form action={controls.submit} className="flex justify-end gap-2">
                  <input type="hidden" name="run_id" value={runId} />
                  <input type="hidden" name="protocol_id" value={protocolId} />
                  <button
                    type="button"
                    onClick={() => setSubmitOpen(false)}
                    className="inline-flex cursor-pointer items-center justify-center rounded-md border border-border-strong bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-sunken"
                  >
                    {t("cancel")}
                  </button>
                  <SubmitButton variant="primary">{t("submit")}</SubmitButton>
                </form>
              </Modal>
            </>
          )}
        </div>
      </div>

      {!collapsed && (
        <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
          {items.map((i) => {
            const hasBlockers = i.count > 0;
            const visibleReqs = i.requirements.slice(0, MAX_INLINE_BLOCKERS);
            const extraReqs = i.requirements.length - visibleReqs.length;
            const visibleNums = i.numbers.slice(0, MAX_INLINE_BLOCKERS);
            const extraNums = i.numbers.length - visibleNums.length;
            return (
              <li
                key={i.check}
                data-testid={`check-${i.check}`}
                className={`rounded-md border px-2.5 py-1 text-xs tabular-nums ${
                  hasBlockers
                    ? "border-fail-edge bg-fail-soft font-medium text-fail"
                    : "border-border bg-sunken text-ink-muted"
                }`}
              >
                <span>{t(`checklist.items.${i.check}`, { count: i.count })}</span>
                {hasBlockers && (
                  <>
                    {": "}
                    {visibleReqs.map((r, n) => (
                      <span key={r}>
                        {n > 0 && ", "}
                        <a
                          href={`#row-${r}`}
                          onClick={(e) => {
                            e.preventDefault();
                            onNavigateToRow?.(r);
                          }}
                          className="font-mono font-semibold text-fail underline hover:text-ink"
                        >
                          {r}
                        </a>
                      </span>
                    ))}
                    {extraReqs > 0 && (
                      <span className="ml-1 text-[11px] font-semibold text-fail">
                        {t("checklist.moreBlockers", { count: extraReqs })}
                      </span>
                    )}
                    {visibleNums.map((x, n) => (
                      <span key={`${x.doc}/${x.rev}/${x.number}`}>
                        {n > 0 && ", "}
                        <a
                          href="#protocol-missed"
                          onClick={(e) => {
                            e.preventDefault();
                            onNavigateToMissed?.();
                          }}
                          className="font-mono font-semibold text-fail underline hover:text-ink"
                        >
                          {x.number}
                        </a>
                      </span>
                    ))}
                    {extraNums > 0 && (
                      <span className="ml-1 text-[11px] font-semibold text-fail">
                        {t("checklist.moreBlockers", { count: extraNums })}
                      </span>
                    )}
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
