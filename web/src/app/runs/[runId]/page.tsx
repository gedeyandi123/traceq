import { getTranslations } from "next-intl/server";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { api } from "@/api/client";
import { MatrixTable } from "@/components/MatrixTable";
import { decisionError, loadDecisions } from "@/decisions/load";

import { RunHeader } from "@/components/RunHeader";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("matrix"))("title") };
}

export default async function MatrixPage({
  params,
  searchParams,
}: {
  params: Promise<{ runId: string }>;
  searchParams: Promise<{ error?: string | string[] }>;
}) {
  const { runId } = await params;
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
      <RunHeader run={run.data} current="matrix" />
      <MatrixTable matrix={matrix.data} runId={runId} decisions={decisions} />
    </>
  );
}
