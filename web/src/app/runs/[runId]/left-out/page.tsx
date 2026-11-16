import { getTranslations } from "next-intl/server";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { api } from "@/api/client";
import { LeftOutView } from "@/components/LeftOutView";

import { RunHeader } from "@/components/RunHeader";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("leftOut"))("title") };
}

export default async function LeftOutPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const path = { params: { path: { run_id: runId } } };
  const [run, dropped, completeness] = await Promise.all([
    api.GET("/runs/{run_id}", path),
    api.GET("/runs/{run_id}/dropped", path),
    api.GET("/runs/{run_id}/completeness", path),
  ]);
  if (!run.data || !dropped.data) notFound();
  return (
    <>
      <RunHeader run={run.data} current="leftOut" />
      <LeftOutView dropped={dropped.data} completeness={completeness.data ?? null} />
    </>
  );
}
