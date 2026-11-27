"use client";

import { AlertTriangle, CheckCircle2, CircleDot, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";

import type { Cite, MatrixRow, ObservedValue, Value } from "@/api/client";
import type { components } from "@/api/schema";
import { PdfCitationButton } from "@/components/ui/PdfCitationModal";

type MatrixT = ReturnType<typeof useTranslations<"matrix">>;
export type Evidence = MatrixRow["evidence"][number];

const numberFormat = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 3 });

/** A required or observed value in a few characters. */
export function formatValue(
  t: MatrixT,
  v: Value | ObservedValue | components["schemas"]["Acceptance"],
  observed = false,
): string {
  switch (v.type) {
    case "exclusive_range": {
      const parts: string[] = [];
      if (v.min != null) parts.push(`${v.min_exclusive ? ">" : "≥"} ${numberFormat.format(v.min)}`);
      if (v.max != null) parts.push(`${v.max_exclusive ? "<" : "≤"} ${numberFormat.format(v.max)}`);
      return `${parts.join(" ")} ${v.unit}`;
    }
    case "tolerance":
      return `${numberFormat.format(v.nominal)} ${v.unit} ± ${numberFormat.format(v.tolerance)} ${v.tolerance_unit}`;
    case "range":
      if (v.min != null && v.max != null) {
        return `${numberFormat.format(v.min)}–${numberFormat.format(v.max)} ${v.unit}`;
      }
      return v.min != null
        ? t("values.atLeast", { min: numberFormat.format(v.min), unit: v.unit })
        : t("values.atMost", { max: numberFormat.format(v.max ?? 0), unit: v.unit });
    case "number":
      return `${numberFormat.format(v.value)} ${v.unit}`;
    case "one_of":
      return v.allowed.join(" / ");
    case "text":
      return v.value;
    case "present":
      if (!observed || v.value == null) return t("values.present");
      return v.value ? t("values.presentObserved") : t("values.absentObserved");
    case "ambiguous":
      return t("ambiguous", { readings: v.readings.map((r) => numberFormat.format(r)).join(" / ") });
  }
}

/** Deduplicate stage prefix when the step ID already begins with the stage (e.g. FAT + FAT-M-02 -> FAT-M-02). */
export function formatStepLabel(stage: string, step: string): string {
  if (stage && step.toUpperCase().startsWith(stage.toUpperCase())) {
    return step;
  }
  return stage ? `${stage} ${step}` : step;
}

export function sameCite(a: Cite, b: Cite): boolean {
  return a.doc === b.doc && a.rev === b.rev && a.page === b.page && a.quote === b.quote;
}

export type EvidenceTone = "fail" | "warn" | "pass" | "neutral";

/** GMP-safe precedence: `result === "fail"` (red) ALWAYS overrides `observed_value.type === "ambiguous"`.
 * Only when `result !== "fail"` and `ambiguous` is true does the UI render amber `warn`. */
export function resolveEvidenceTone(e: Evidence): {
  tone: EvidenceTone;
  isAmbiguousWarn: boolean;
} {
  if (e.result === "fail") {
    return { tone: "fail", isAmbiguousWarn: false };
  }
  if (e.observed_value?.type === "ambiguous") {
    return { tone: "warn", isAmbiguousWarn: true };
  }
  if (e.result === "pass") {
    return { tone: "pass", isAmbiguousWarn: false };
  }
  return { tone: "neutral", isAmbiguousWarn: false };
}

function shortObserved(t: MatrixT, e: Evidence): string {
  const v = e.observed_value;
  if (!v) return e.observed;
  if (v.type === "ambiguous") {
    return `${v.readings.map((r) => numberFormat.format(r)).join(" / ")} ?`;
  }
  return formatValue(t, v, true);
}

const TONE_CHIP_CLASS: Record<EvidenceTone, string> = {
  fail: "border-fail-edge bg-fail-soft text-fail",
  warn: "border-warn-edge bg-warn-soft text-warn",
  pass: "border-pass-edge bg-pass-soft text-pass",
  neutral: "border-border bg-sunken text-ink-muted",
};

function ToneIcon({ tone }: { tone: EvidenceTone }) {
  switch (tone) {
    case "fail":
      return <XCircle className="h-3 w-3 shrink-0" aria-hidden="true" />;
    case "warn":
      return <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />;
    case "pass":
      return <CheckCircle2 className="h-3 w-3 shrink-0" aria-hidden="true" />;
    case "neutral":
      return <CircleDot className="h-3 w-3 shrink-0" aria-hidden="true" />;
  }
}

export function RequiredObservedUnit({
  row,
  runId,
  variant = "compact",
}: {
  row: MatrixRow;
  runId: string;
  variant?: "compact" | "detailed";
}) {
  const t = useTranslations("matrix");
  const requiredText = row.value ? formatValue(t, row.value) : t("noValue");

  if (variant === "compact") {
    const [design] = row.design;
    const extraDesigns = row.design.length > 1 ? row.design.length - 1 : 0;
    const visibleEvidence = row.evidence.slice(0, 2);
    const extraEvidence = row.evidence.length > 2 ? row.evidence.length - 2 : 0;
    return (
      <div className="grid grid-cols-1 gap-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] sm:items-center sm:gap-2">
        <div className="min-w-0">
          <span
            className={`block truncate text-xs font-medium tabular-nums ${
              row.value ? "text-ink" : "text-ink-muted"
            }`}
            title={requiredText}
          >
            {requiredText}
          </span>
        </div>
        <div className="min-w-0">
          {row.evidence.length === 0 && row.design.length === 0 ? (
            <span className="text-xs text-ink-muted">{t("noEvidence")}</span>
          ) : (
            <div className="flex flex-wrap items-center gap-1">
              {visibleEvidence.map((e) => {
                const { tone, isAmbiguousWarn } = resolveEvidenceTone(e);
                const stepLabel = formatStepLabel(e.stage, e.step);
                const resultLabel = t(`results.${e.result ?? "none"}`);
                const title = isAmbiguousWarn
                  ? `${stepLabel}: ${t("ambiguousConfirm")}`
                  : `${stepLabel}: ${resultLabel}`;
                return (
                  <span
                    key={`${e.doc}/${e.step}`}
                    title={title}
                    className={`inline-flex max-w-full items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-medium tabular-nums ${TONE_CHIP_CLASS[tone]}`}
                  >
                    <ToneIcon tone={tone} />
                    <span className="truncate">{`${stepLabel} · ${shortObserved(t, e)}`}</span>
                    {isAmbiguousWarn && (
                      <>
                        <span aria-hidden="true" className="shrink-0 text-[10px] font-semibold">
                          · {t("ambiguousShort")}
                        </span>
                        <span className="sr-only">{t("ambiguousConfirm")}</span>
                      </>
                    )}
                  </span>
                );
              })}
              {extraEvidence > 0 && (
                <span className="inline-flex items-center rounded border border-border bg-sunken px-1.5 py-0.5 text-[11px] font-medium text-ink-muted tabular-nums">
                  {t("moreEvidence", { count: extraEvidence })}
                </span>
              )}
              {design && (
                <span
                  title={design.name}
                  className="inline-flex max-w-full items-center gap-1 rounded border border-border bg-sunken px-1.5 py-0.5 text-[11px] font-medium text-ink-muted tabular-nums"
                >
                  <span className="truncate">{`${t("designShort")} · ${design.printed}`}</span>
                </span>
              )}
              {extraDesigns > 0 && (
                <span className="inline-flex items-center rounded border border-border bg-sunken px-1.5 py-0.5 text-[11px] font-medium text-ink-muted tabular-nums">
                  {t("moreDesigns", { count: extraDesigns })}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  const primaryEvidence = row.evidence[0];
  const primaryDesign = row.design[0];
  const primaryObservedSummary = primaryEvidence
    ? `${formatStepLabel(primaryEvidence.stage, primaryEvidence.step)} · ${
        primaryEvidence.observed_value
          ? formatValue(t, primaryEvidence.observed_value, true)
          : primaryEvidence.observed
      }`
    : primaryDesign
      ? `${t("designShort")} · ${primaryDesign.printed}`
      : null;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 rounded-lg border border-border bg-sunken p-3 sm:grid-cols-2">
        <div>
          <div className="text-xs font-semibold tracking-wide text-ink-muted uppercase">
            {t("disyaratkan")}
          </div>
          <div
            className={`mt-1 text-sm font-semibold tabular-nums ${
              row.value ? "text-ink" : "text-ink-muted"
            }`}
          >
            {requiredText}
          </div>
          {row.value_citation && !sameCite(row.value_citation, row.source) && (
            <div className="mt-2">
              <PdfCitationButton runId={runId} cite={row.value_citation} compact />
            </div>
          )}
        </div>
        <div>
          <div className="text-xs font-semibold tracking-wide text-ink-muted uppercase">
            {t("teramati")}
          </div>
          {primaryObservedSummary === null ? (
            <div className="mt-1 text-sm text-ink-muted">{t("noEvidence")}</div>
          ) : (
            <div className="mt-1 space-y-0.5">
              <div className="text-sm font-semibold text-ink tabular-nums">
                {primaryObservedSummary}
              </div>
              <div className="text-xs text-ink-muted tabular-nums">
                {row.evidence.length} {t("evidence").toLowerCase()}
                {row.design.length > 0 ? ` · ${row.design.length} ${t("designShort").toLowerCase()}` : ""}
              </div>
            </div>
          )}
        </div>
      </div>

      {(row.evidence.length > 0 || row.design.length > 0) && (
        <ul className="m-0 list-none space-y-2 p-0">
          {row.evidence.map((e) => {
            const { tone, isAmbiguousWarn } = resolveEvidenceTone(e);
            const stepLabel = formatStepLabel(e.stage, e.step);
            const observedText = e.observed_value
              ? formatValue(t, e.observed_value, true)
              : e.observed;
            const resultLabel = t(`results.${e.result ?? "none"}`);
            return (
              <li
                key={`${e.doc}/${e.step}`}
                className="rounded-lg border border-border bg-surface p-3 text-sm"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-semibold text-ink tabular-nums">
                    {stepLabel}
                    {e.test ? (
                      <span className="ml-1.5 font-normal text-ink-muted">{e.test}</span>
                    ) : null}
                  </div>
                  <span
                    className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${TONE_CHIP_CLASS[tone]}`}
                  >
                    <ToneIcon tone={tone} />
                    <span>{isAmbiguousWarn ? t("ambiguousConfirm") : resultLabel}</span>
                  </span>
                </div>
                <div className="mt-1.5 text-xs text-ink tabular-nums">
                  {t("observed", { observed: observedText })}
                </div>
                {e.failure && (
                  <div className="mt-2 rounded border border-fail-edge bg-fail-soft px-2.5 py-1.5 text-xs font-medium text-fail">
                    {e.failure}
                  </div>
                )}
                <div className="mt-2">
                  <PdfCitationButton runId={runId} cite={e.citation} compact />
                </div>
              </li>
            );
          })}
          {row.design.map((d) => (
            <li
              key={`${d.doc}/${d.name}`}
              className="rounded-lg border border-border bg-surface p-3 text-sm"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-semibold text-ink">
                  {t("design")}: <span className="font-normal">{d.name}</span>
                </div>
                <span className="text-xs font-medium text-ink-muted tabular-nums">
                  {t("printed", { printed: d.printed })}
                </span>
              </div>
              <div className="mt-2">
                <PdfCitationButton runId={runId} cite={d.citation} compact />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
