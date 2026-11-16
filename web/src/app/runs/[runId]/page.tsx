import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { api } from "@/api/client";
import { MatrixTable } from "@/components/MatrixTable";
import { decisionError, loadDecisions } from "@/decisions/load";

export const dynamic = "force-dynamic";

export default async function MatrixPage({
  params,
  searchParams,
}: {
  params: Promise<{ runId: string }>;
  searchParams: Promise<{ error?: string | string[] }>;
}) {
  const { runId } = await params;
  const t = await getTranslations("matrix");
  const path = { params: { path: { run_id: runId } } };
  const [run, matrix, decisions] = await Promise.all([
    api.GET("/runs/{run_id}", path),
    api.GET("/runs/{run_id}/matrix", path),
    loadDecisions(runId),
  ]);
  decisions.error = decisionError((await searchParams).error);
  if (!run.data || !matrix.data) notFound();
  return (
    <>
      <Link href="/">{t("back")}</Link>
      <h1>{t("title")}</h1>
      <p className="muted">
        {t("subtitle", { equipment: run.data.equipment, runId })}
        {" · "}
        <Link href={`/runs/${encodeURIComponent(runId)}/findings`}>{t("toFindings")}</Link>
        {" · "}
        <Link href={`/runs/${encodeURIComponent(runId)}/left-out`}>{t("toLeftOut")}</Link>
        {" · "}
        <Link href={`/runs/${encodeURIComponent(runId)}/eval`}>{t("toEval")}</Link>
      </p>
      <MatrixTable matrix={matrix.data} runId={runId} decisions={decisions} />
    </>
  );
}
