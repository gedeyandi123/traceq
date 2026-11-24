import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { api } from "@/api/client";
import { FindingsView } from "@/components/FindingsView";
import { decisionError, loadDecisions } from "@/decisions/load";
import { fetchRun } from "@/runs/fetchers";

export const dynamic = "force-dynamic";

/** The browser tab reads "<screen> · TraceQ" (the root layout's template); translations only, no fetch. */
export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("findings"))("title") };
}

export default async function FindingsPage({
  params,
  searchParams,
}: {
  params: Promise<{ runId: string }>;
  searchParams: Promise<{ error?: string | string[] }>;
}) {
  const { runId } = await params;
  const t = await getTranslations("findings");
  const path = { params: { path: { run_id: runId } } };
  const [run, findings, decisions] = await Promise.all([
    fetchRun(runId),
    api.GET("/runs/{run_id}/findings", path),
    loadDecisions(runId),
  ]);
  decisions.error = decisionError((await searchParams).error);
  if (!run || !findings.data) notFound();
  return (
    <div className="space-y-4">
      <div>
        <h1 className="m-0 text-lg font-bold text-ink">{t("title")}</h1>
        <p className="mt-0.5 mb-0 text-xs text-ink-muted">{t("intro")}</p>
      </div>
      <FindingsView
        findings={findings.data}
        runId={runId}
        decisions={decisions}
        hasReviewPackage={run.review_package != null}
      />
    </div>
  );
}
