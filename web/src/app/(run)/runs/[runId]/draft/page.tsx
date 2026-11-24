import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { api } from "@/api/client";
import { bearerHeaders } from "@/auth/session";
import { ProtocolDraftView } from "@/components/ProtocolDraftView";
import { EmptyState } from "@/components/ui/ui";
import { decisionError, loadDecisions } from "@/decisions/load";
import { fetchRun } from "@/runs/fetchers";

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
  const [run, decisions] = await Promise.all([fetchRun(runId), loadDecisions(runId)]);
  decisions.error = decisionError((await searchParams).error);
  if (!run?.review_package) notFound();
  const heading = (
    <div>
      <h1 className="m-0 text-lg font-bold text-ink">{t("title")}</h1>
      <p className="mt-0.5 mb-0 text-xs text-ink-muted">{t("intro")}</p>
    </div>
  );
  if (decisions.access.mode === "readOnly" && decisions.access.why === "signedOut") {
    return (
      <div className="space-y-4">
        {heading}
        <EmptyState title={t("signedOut")}>{t("signedOutBody")}</EmptyState>
      </div>
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
      <div className="space-y-4">
        {heading}
        <EmptyState title={t("unavailable")}>{t("unavailableBody")}</EmptyState>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      {heading}
      <ProtocolDraftView draft={draft.data} runId={runId} decisions={decisions} />
    </div>
  );
}
