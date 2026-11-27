import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { api, type Proposal } from "@/api/client";
import { bearerHeaders } from "@/auth/session";
import { MatrixTable, type MatrixFilter } from "@/components/MatrixTable";
import type { CoverageBadgeKey } from "@/components/ui/StatusBadge";
import { decisionError, loadDecisions } from "@/decisions/load";
import { COVERAGE_CLASSES } from "@/decisions/vocabulary";
import { fetchRun } from "@/runs/fetchers";

export const dynamic = "force-dynamic";

const VALID_COVERAGE = new Set<CoverageBadgeKey>([...COVERAGE_CLASSES, "none"]);
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
  searchParams: Promise<{
    error?: string | string[];
    coverage?: string | string[];
    status?: string | string[];
    selected?: string | string[];
  }>;
}) {
  const { runId } = await params;
  const query = await searchParams;
  const t = await getTranslations("matrix");
  const path = { params: { path: { run_id: runId } }, headers: await bearerHeaders() };
  const [run, matrix, decisions] = await Promise.all([
    fetchRun(runId),
    api.GET("/runs/{run_id}/matrix", path),
    loadDecisions(runId),
  ]);
  decisions.error = decisionError(query.error);
  if (!run || !matrix.data) notFound();
  const cov =
    typeof query.coverage === "string" && VALID_COVERAGE.has(query.coverage as CoverageBadgeKey)
      ? (query.coverage as CoverageBadgeKey)
      : undefined;
  const st =
    typeof query.status === "string" && VALID_STATUS.has(query.status as Proposal["state"])
      ? (query.status as Proposal["state"])
      : undefined;
  const selected = typeof query.selected === "string" && query.selected.trim() !== "" ? query.selected : null;
  const filter: MatrixFilter = { coverage: cov, status: st };
  return (
    <MatrixTable
      matrix={matrix.data}
      runId={runId}
      decisions={decisions}
      filter={filter}
      initialSelected={selected}
      title={t("title")}
    />
  );
}
