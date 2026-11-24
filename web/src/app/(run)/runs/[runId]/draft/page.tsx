import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
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
  searchParams: Promise<{ error?: string | string[]; selected?: string | string[] }>;
}) {
  const { runId } = await params;
  const query = await searchParams;
  const t = await getTranslations("draft");
  const signin = await getTranslations("signin");
  const path = { params: { path: { run_id: runId } } };
  const [run, decisions] = await Promise.all([fetchRun(runId), loadDecisions(runId)]);
  decisions.error = decisionError(query.error);
  if (!run?.review_package) notFound();
  const selected = typeof query.selected === "string" && query.selected.trim() !== "" ? query.selected : null;
  const signInHref = `/signin?next=${encodeURIComponent(`/runs/${encodeURIComponent(runId)}/draft`)}`;
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
        <EmptyState title={t("signedOut")}>
          <p className="m-0 mb-3">{t("signedOutBody")}</p>
          <Link
            href={signInHref}
            className="inline-flex items-center rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent no-underline hover:bg-accent-hover"
          >
            {signin("link")}
          </Link>
        </EmptyState>
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
      <ProtocolDraftView
        draft={draft.data}
        runId={runId}
        decisions={decisions}
        initialSelected={selected}
      />
    </div>
  );
}
