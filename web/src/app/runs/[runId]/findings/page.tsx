import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { api } from "@/api/client";
import { FindingsView } from "@/components/FindingsView";
import { RunHeader } from "@/components/RunHeader";
import { decisionError, loadDecisions } from "@/decisions/load";
import { loadTabBadges } from "@/decisions/tabBadges";

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
    api.GET("/runs/{run_id}", path),
    api.GET("/runs/{run_id}/findings", path),
    loadDecisions(runId),
  ]);
  const badges = await loadTabBadges(runId, decisions.counts);
  decisions.error = decisionError((await searchParams).error);
  if (!run.data || !findings.data) notFound();
  return (
    <>
      <RunHeader run={run.data} current="findings" intro={t("intro")} badges={badges} />
      <FindingsView findings={findings.data} runId={runId} decisions={decisions} />
    </>
  );
}
