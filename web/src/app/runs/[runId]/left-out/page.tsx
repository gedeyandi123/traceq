import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { api } from "@/api/client";
import { LeftOutView } from "@/components/LeftOutView";
import { RunHeader } from "@/components/RunHeader";
import { loadTabBadges } from "@/decisions/tabBadges";

export const dynamic = "force-dynamic";

/** The browser tab reads "<screen> · TraceQ" (the root layout's template); translations only, no fetch. */
export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("leftOut"))("title") };
}

export default async function LeftOutPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const t = await getTranslations("leftOut");
  const path = { params: { path: { run_id: runId } } };
  const [run, dropped, completeness, badges] = await Promise.all([
    api.GET("/runs/{run_id}", path),
    api.GET("/runs/{run_id}/dropped", path),
    api.GET("/runs/{run_id}/completeness", path),
    loadTabBadges(runId),
  ]);
  if (!run.data || !dropped.data) notFound();
  return (
    <>
      <RunHeader run={run.data} current="leftOut" intro={t("intro")} badges={badges} />
      <LeftOutView dropped={dropped.data} completeness={completeness.data ?? null} />
    </>
  );
}
