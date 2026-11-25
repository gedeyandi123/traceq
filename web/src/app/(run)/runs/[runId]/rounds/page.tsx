import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { currentSession } from "@/auth/session";
import { RoundsWorkbench } from "@/components/RoundsWorkbench";
import { EmptyState } from "@/components/ui/ui";
import { closeReviewRound, exportPreReviewReport } from "@/rounds/actions";
import { fetchRounds, fetchRun } from "@/runs/fetchers";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("rounds"))("title") };
}

/** Equipment Document Versions, Review Rounds & Diff, and Pre-review Report PDF exports (Step 6). */
export default async function RoundsPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  const t = await getTranslations("rounds");
  const signin = await getTranslations("signin");

  const [run, session, roundsRes] = await Promise.all([
    fetchRun(runId),
    currentSession(),
    fetchRounds(runId),
  ]);
  if (!run) notFound();

  const heading = (
    <div>
      <h1 className="m-0 text-lg font-bold text-ink">{t("title")}</h1>
      <p className="mt-0.5 mb-0 text-xs text-ink-muted">{t("intro")}</p>
    </div>
  );

  const signInHref = `/signin?next=${encodeURIComponent(`/runs/${encodeURIComponent(runId)}/rounds`)}`;
  if (session === null) {
    return (
      <div className="space-y-4">
        {heading}
        <EmptyState title={t("signedOut")}>
          <p className="m-0">{t("signedOutBody")}</p>
          <div className="mt-3">
            <Link
              href={signInHref}
              className="inline-flex items-center rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent no-underline hover:bg-accent-hover"
            >
              {signin("link")}
            </Link>
          </div>
        </EmptyState>
      </div>
    );
  }

  if (roundsRes.kind === "not_found") {
    return (
      <div className="space-y-4">
        {heading}
        <EmptyState title={t("notFound")} />
      </div>
    );
  }

  if (roundsRes.kind === "unavailable") {
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
      <RoundsWorkbench
        runId={runId}
        data={roundsRes.data}
        session={session}
        closeRoundAction={closeReviewRound}
        exportReportAction={exportPreReviewReport}
      />
    </div>
  );
}
