import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { api } from "@/api/client";
import { LeftOutView } from "@/components/LeftOutView";
import { fetchRun } from "@/runs/fetchers";

export const dynamic = "force-dynamic";

/** The browser tab reads "<screen> · TraceQ" (the root layout's template); translations only, no fetch. */
export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("leftOut"))("title") };
}

export default async function LeftOutPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const t = await getTranslations("leftOut");
  const path = { params: { path: { run_id: runId } } };
  const [run, dropped, completeness] = await Promise.all([
    fetchRun(runId),
    api.GET("/runs/{run_id}/dropped", path),
    api.GET("/runs/{run_id}/completeness", path),
  ]);
  if (!run || !dropped.data) notFound();
  return (
    <div className="space-y-4">
      <div>
        <h1 className="m-0 text-lg font-bold text-ink">{t("title")}</h1>
        <p className="mt-0.5 mb-0 text-xs text-ink-muted">{t("intro")}</p>
      </div>
      <LeftOutView
        dropped={dropped.data}
        completeness={completeness.data ?? null}
        runId={runId}
      />
    </div>
  );
}
