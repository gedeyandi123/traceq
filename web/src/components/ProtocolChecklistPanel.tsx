"use client";

import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { useTranslations } from "next-intl";

import type { ChecklistItem } from "@/api/client";
import type { ProtocolControls } from "./AssembledProtocolView";
import { SubmitButton } from "./ui/SubmitButton";

type T = ReturnType<typeof useTranslations<"protocol">>;

/** Sticky Submission Readiness Bar: shows the five checklist checks with their counts and
 * deep-links to the rows or missed numbers concerned, plus the submit control. */
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
  const blocked = items.some((i) => i.count > 0);

  return (
    <section
      aria-labelledby="protocol-checklist"
      className="sticky top-12 z-20 space-y-2.5 rounded-lg border border-border bg-surface/95 px-4 py-3 shadow-sm backdrop-blur-[2px]"
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

        {controls !== null && (
          <form action={controls.submit}>
            <input type="hidden" name="run_id" value={runId} />
            <input type="hidden" name="protocol_id" value={protocolId} />
            <SubmitButton variant="primary" disabled={blocked}>
              {t("submit")}
            </SubmitButton>
          </form>
        )}
      </div>

      <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
        {items.map((i) => {
          const hasBlockers = i.count > 0;
          return (
            <li
              key={i.check}
              data-testid={`check-${i.check}`}
              className={`rounded-md border px-2.5 py-1 text-xs tabular-nums ${
                hasBlockers
                  ? "border-fail-edge bg-fail-soft font-medium text-fail"
                  : "border-border bg-canvas text-ink-muted"
              }`}
            >
              <span>{t(`checklist.items.${i.check}`, { count: i.count })}</span>
              {hasBlockers && (
                <>
                  {": "}
                  {i.requirements.map((r, n) => (
                    <span key={r}>
                      {n > 0 && ", "}
                      <a
                        href={`#row-${r}`}
                        onClick={() => onNavigateToRow?.(r)}
                        className="font-mono font-semibold text-fail underline hover:text-ink"
                      >
                        {r}
                      </a>
                    </span>
                  ))}
                  {i.numbers.map((x, n) => (
                    <span key={`${x.doc}/${x.rev}/${x.number}`}>
                      {n > 0 && ", "}
                      <a
                        href="#protocol-missed"
                        onClick={() => onNavigateToMissed?.()}
                        className="font-mono font-semibold text-fail underline hover:text-ink"
                      >
                        {x.number}
                      </a>
                    </span>
                  ))}
                </>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
