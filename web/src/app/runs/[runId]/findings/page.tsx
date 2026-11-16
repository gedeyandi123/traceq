import { getTranslations } from "next-intl/server";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { api } from "@/api/client";
import { FindingsView } from "@/components/FindingsView";
import { decisionError, loadDecisions } from "@/decisions/load";

import { RunHeader } from "@/components/RunHeader";

export const dynamic = "force-dynamic";

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
  decisions.error = decisionError((await searchParams).error);
  if (!run.data || !findings.data) notFound();
  return (
    <div className="stack">
      <RunHeader run={run.data} current="findings" intro={t("intro")} />
      <FindingsView findings={findings.data} runId={runId} decisions={decisions} />
    </div>
  );
}
