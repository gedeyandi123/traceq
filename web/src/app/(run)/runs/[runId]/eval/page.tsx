import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { evalApi } from "@/api/client";
import { EvalView } from "@/components/EvalView";
import { fetchRun } from "@/runs/fetchers";

export const dynamic = "force-dynamic";

/** The browser tab reads "<screen> · TraceQ" (the root layout's template); translations only, no fetch. */
export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("eval"))("title") };
}

/** The eval screen: the run comes from the system's API, its scores from the harness's. */
export default async function EvalPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const t = await getTranslations("eval");
  const path = { params: { path: { run_id: runId } } };
  const [run, summary] = await Promise.all([
    fetchRun(runId),
    evalApi.GET("/evals/{run_id}", path).catch(() => ({ data: undefined })),
  ]);
  if (!run) notFound();
  return (
    <div className="space-y-4">
      <div>
        <h1 className="m-0 text-lg font-bold text-ink">{t("title")}</h1>
        <p className="mt-0.5 mb-0 text-xs text-ink-muted">{t("intro")}</p>
      </div>
      <EvalView summary={summary.data ?? null} />
    </div>
  );
}
