import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { api } from "@/api/client";
import { MatrixTable } from "@/components/MatrixTable";
import { PrototypeSwitcher } from "@/components/prototype/PrototypeSwitcher";
import { VariantA } from "@/components/prototype/VariantA";
import { VariantB } from "@/components/prototype/VariantB";
import { VariantC } from "@/components/prototype/VariantC";
import { decisionError, loadDecisions } from "@/decisions/load";

export const dynamic = "force-dynamic";

export default async function MatrixPage({
  params,
  searchParams,
}: {
  params: Promise<{ runId: string }>;
  searchParams: Promise<{ error?: string | string[]; variant?: string; req?: string }>;
}) {
  const { runId } = await params;
  const t = await getTranslations("matrix");
  const path = { params: { path: { run_id: runId } } };
  const [run, matrix, decisions] = await Promise.all([
    api.GET("/runs/{run_id}", path),
    api.GET("/runs/{run_id}/matrix", path),
    loadDecisions(runId),
  ]);
  const query = await searchParams;
  decisions.error = decisionError(query.error);
  if (!run.data || !matrix.data) notFound();
  // PROTOTYPE (feat/ui-redesign-prototype, never merged): three layouts on ?variant=A|B|C,
  // the current page as "0". Production builds ignore the parameter and hide the switcher.
  const prototype = process.env.NODE_ENV !== "production";
  const variant = prototype ? (query.variant ?? "0") : "0";
  const props = {
    matrix: matrix.data,
    runId,
    decisions,
    equipment: run.data.equipment,
    selected: query.req,
  };
  const switcher = prototype && (
    <PrototypeSwitcher
      current={variant}
      variants={[
        { key: "0", name: "Sekarang" },
        { key: "A", name: "Ledger" },
        { key: "B", name: "Triage" },
        { key: "C", name: "Board" },
      ]}
    />
  );
  if (variant === "A") return <><VariantA {...props} />{switcher}</>;
  if (variant === "B") return <><VariantB {...props} />{switcher}</>;
  if (variant === "C") return <><VariantC {...props} />{switcher}</>;
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
      {switcher}
    </>
  );
}
