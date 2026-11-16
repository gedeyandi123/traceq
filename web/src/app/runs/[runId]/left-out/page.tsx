import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { api } from "@/api/client";
import { LeftOutView } from "@/components/LeftOutView";

export const dynamic = "force-dynamic";

export default async function LeftOutPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const t = await getTranslations("leftOut");
  const path = { params: { path: { run_id: runId } } };
  const [run, dropped, completeness] = await Promise.all([
    api.GET("/runs/{run_id}", path),
    api.GET("/runs/{run_id}/dropped", path),
    api.GET("/runs/{run_id}/completeness", path),
  ]);
  if (!run.data || !dropped.data) notFound();
  return (
    <>
      <Link href={`/runs/${encodeURIComponent(runId)}`}>{t("back")}</Link>
      <h1>{t("title")}</h1>
      <p className="muted">{t("subtitle", { equipment: run.data.equipment, runId })}</p>
      <LeftOutView dropped={dropped.data} completeness={completeness.data ?? null} />
    </>
  );
}
