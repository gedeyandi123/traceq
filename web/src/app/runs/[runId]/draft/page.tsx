import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { api } from "@/api/client";
import { bearerHeaders } from "@/auth/session";
import { ProtocolDraftView } from "@/components/ProtocolDraftView";
import { RunHeader } from "@/components/RunHeader";
import { EmptyState } from "@/components/ui/ui";
import { decisionError, loadDecisions } from "@/decisions/load";

export const dynamic = "force-dynamic";

/** The browser tab reads "<screen> · TraceQ" (the root layout's template); translations only, no fetch. */
export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("draft"))("title") };
}

/** The Protocol Draft of a Review Package run (spec #196, ticket #210). The API serves it with
 * a token only, so a signed-out viewer is asked to sign in; a run without a draft is not found. */
export default async function DraftPage({
  params,
  searchParams,
}: {
  params: Promise<{ runId: string }>;
  searchParams: Promise<{ error?: string | string[] }>;
}) {
  const { runId } = await params;
  const t = await getTranslations("draft");
  const path = { params: { path: { run_id: runId } } };
  const [run, decisions] = await Promise.all([api.GET("/runs/{run_id}", path), loadDecisions(runId)]);
  decisions.error = decisionError((await searchParams).error);
  if (!run.data?.review_package) notFound();
  const header = <RunHeader run={run.data} current="draft" intro={t("intro")} />;
  if (decisions.access.mode === "readOnly" && decisions.access.why === "signedOut") {
    return (
      <>
        {header}
        <EmptyState title={t("signedOut")}>{t("signedOutBody")}</EmptyState>
      </>
    );
  }
  let draft;
  try {
    draft = await api.GET("/runs/{run_id}/protocol-draft", { ...path, headers: await bearerHeaders() });
  } catch {
    draft = undefined;
  }
  if (draft?.response.status === 404) notFound();
  if (!draft?.data) {
    return (
      <>
        {header}
        <EmptyState title={t("unavailable")}>{t("unavailableBody")}</EmptyState>
      </>
    );
  }
  return (
    <>
      {header}
      <ProtocolDraftView draft={draft.data} runId={runId} decisions={decisions} />
    </>
  );
}
