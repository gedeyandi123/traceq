import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { api, evalApi } from "@/api/client";
import { EvalView } from "@/components/EvalView";
import { RunHeader } from "@/components/RunHeader";

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
    api.GET("/runs/{run_id}", path),
    evalApi.GET("/evals/{run_id}", path).catch(() => ({ data: undefined })),
  ]);
  if (!run.data) notFound();
  return (
    <>
      <RunHeader run={run.data} current="eval" intro={t("intro")} />
      {summary.data ? <EvalView summary={summary.data} /> : <p>{t("notScored")}</p>}
    </>
  );
}
