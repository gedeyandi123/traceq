import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { api, evalApi } from "@/api/client";
import { EvalView } from "@/components/EvalView";

export const dynamic = "force-dynamic";

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
      <Link href={`/runs/${encodeURIComponent(runId)}`}>{t("back")}</Link>
      <h1>{t("title")}</h1>
      <p className="muted">{t("subtitle", { equipment: run.data.equipment, runId })}</p>
      {summary.data ? <EvalView summary={summary.data} /> : <p>{t("notScored")}</p>}
    </>
  );
}
