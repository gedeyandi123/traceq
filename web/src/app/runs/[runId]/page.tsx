import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { api, type Proposal } from "@/api/client";
import { MatrixTable, type MatrixFilter } from "@/components/MatrixTable";
import { RunHeader } from "@/components/RunHeader";
import type { CoverageKey } from "@/components/ui/ui";
import { decisionError, loadDecisions } from "@/decisions/load";
import { loadTabBadges } from "@/decisions/tabBadges";
import { COVERAGE_CLASSES } from "@/decisions/vocabulary";

export const dynamic = "force-dynamic";

const VALID_COVERAGE = new Set<CoverageKey>([...COVERAGE_CLASSES, "none"]);
const VALID_STATUS = new Set<Proposal["state"]>(["undecided", "decided", "changed"]);

/** The browser tab reads "<screen> · TraceQ" (the root layout's template); translations only, no fetch. */
export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("matrix"))("title") };
}

export default async function MatrixPage({
  params,
  searchParams,
}: {
  params: Promise<{ runId: string }>;
  searchParams: Promise<{ error?: string | string[]; coverage?: string | string[]; status?: string | string[] }>;
}) {
  const { runId } = await params;
  const query = await searchParams;
  const t = await getTranslations("matrix");
  const path = { params: { path: { run_id: runId } } };
  const [run, matrix, decisions] = await Promise.all([
    api.GET("/runs/{run_id}", path),
    api.GET("/runs/{run_id}/matrix", path),
    loadDecisions(runId),
  ]);
  const badges = await loadTabBadges(runId, decisions.counts);
  decisions.error = decisionError(query.error);
  if (!run.data || !matrix.data) notFound();
  const cov = typeof query.coverage === "string" && VALID_COVERAGE.has(query.coverage as CoverageKey)
    ? (query.coverage as CoverageKey)
    : undefined;
  const st = typeof query.status === "string" && VALID_STATUS.has(query.status as Proposal["state"])
    ? (query.status as Proposal["state"])
    : undefined;
  const filter: MatrixFilter = { coverage: cov, status: st };
  return (
    <>
      <RunHeader run={run.data} current="matrix" intro={t("intro")} badges={badges} />
      <MatrixTable matrix={matrix.data} runId={runId} decisions={decisions} filter={filter} />
    </>
  );
}
