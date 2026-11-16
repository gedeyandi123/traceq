// PROTOTYPE (feat/ui-redesign-prototype, never merged): bits the three variants share.
// Decision buttons are disabled stubs: no form, no action, no mutation.
import { useTranslations } from "next-intl";

import type { CoverageClass, Matrix, MatrixRow, Proposal } from "@/api/client";
import type { DecisionView } from "@/components/Decisions";
import { COVERAGE_CLASSES } from "@/decisions/vocabulary";

import ui from "./ui.module.css";

export type Cov = CoverageClass | "none";

/** Riskiest first: what a reviewer should look at first. */
export const RISK_ORDER: readonly Cov[] = ["conflict", "gap", "partial", "site_only", "covered_by_vendor", "none"];

export type VariantProps = {
  matrix: Matrix;
  runId: string;
  decisions: DecisionView;
  equipment: string;
  selected?: string;
};

export function cov(row: MatrixRow): Cov {
  return row.coverage ?? "none";
}

export function byRequirement(d: DecisionView): Map<string | null, Proposal> {
  return new Map(
    (d.proposals ?? []).filter((p) => p.kind === "coverage").map((p) => [p.requirement, p] as const),
  );
}

export function countBy(rows: readonly MatrixRow[]): Record<Cov, number> {
  const c = { conflict: 0, gap: 0, partial: 0, site_only: 0, covered_by_vendor: 0, none: 0 };
  for (const r of rows) c[cov(r)] += 1;
  return c;
}

export function CoveragePill({ c }: { c: Cov }) {
  const t = useTranslations("matrix");
  return <span className={`${ui.pill} ${ui[`cov_${c}`]}`}>{t(`classes.${c}`)}</span>;
}

/** The decision buttons, disabled. Shown only when the viewer may decide, as in the app. */
export function StubActions({
  decisions,
  proposed,
  compact = false,
}: {
  decisions: DecisionView;
  proposed: CoverageClass | null | undefined;
  compact?: boolean;
}) {
  const t = useTranslations("decisions");
  const classes = useTranslations("matrix");
  if (decisions.access.mode !== "decide") return null;
  return (
    <div className={ui.actions} title="Prototipe: tombol keputusan dinonaktifkan">
      {proposed != null && (
        <button type="button" className={ui.primary} disabled>
          {t("accept")}
        </button>
      )}
      {!compact && (
        <select disabled defaultValue="" aria-label={t("toClass")}>
          <option value="">{t("toClass")}</option>
          {COVERAGE_CLASSES.filter((c) => c !== proposed).map((c) => (
            <option key={c} value={c}>
              {classes(`classes.${c}`)}
            </option>
          ))}
        </select>
      )}
      <button type="button" disabled>
        {t("edit")}
      </button>
    </div>
  );
}
