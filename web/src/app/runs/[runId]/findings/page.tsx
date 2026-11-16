import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { api } from "@/api/client";
import { FindingsView } from "@/components/FindingsView";
import { decisionError, loadDecisions } from "@/decisions/load";

export const dynamic = "force-dynamic";

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
    <>
      <Link href={`/runs/${encodeURIComponent(runId)}`}>{t("back")}</Link>
      <h1>{t("title")}</h1>
      <p className="muted">
        {t("subtitle", { equipment: run.data.equipment, runId })}
        {" · "}
        <Link href={`/runs/${encodeURIComponent(runId)}/left-out`}>{t("toLeftOut")}</Link>
      </p>
      <FindingsView findings={findings.data} runId={runId} decisions={decisions} />
    </>
  );
}
