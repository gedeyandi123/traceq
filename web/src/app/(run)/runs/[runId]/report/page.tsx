import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { currentSession } from "@/auth/session";
import { QualificationReportWorkbench } from "@/components/QualificationReportWorkbench";
import { EmptyState } from "@/components/ui/ui";
import { approveQualificationReport } from "@/report/actions";
import { fetchExecution, fetchQualificationReport, fetchRun } from "@/runs/fetchers";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("report"))("title") };
}

/** Qualification Report & Immutable PDF Exports (Step 7). */
export default async function QualificationReportPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  const t = await getTranslations("report");
  const signin = await getTranslations("signin");

  const [run, session, reportRes, executionRes] = await Promise.all([
    fetchRun(runId),
    currentSession(),
    fetchQualificationReport(runId),
    fetchExecution(runId),
  ]);
  if (!run) notFound();

  const heading = (
    <div>
      <h1 className="m-0 text-lg font-bold text-ink">{t("title")}</h1>
      <p className="mt-0.5 mb-0 text-xs text-ink-muted">{t("intro")}</p>
    </div>
  );

  const signInHref = `/signin?next=${encodeURIComponent(`/runs/${encodeURIComponent(runId)}/report`)}`;
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

  if (reportRes.kind === "not_found") {
    return (
      <div className="space-y-4">
        {heading}
        <EmptyState title={t("notCompletedTitle")}>
          <p className="m-0 mb-3">{t("notCompletedBody")}</p>
          <Link
            href={`/runs/${encodeURIComponent(runId)}/execution`}
            className="inline-flex items-center rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent no-underline hover:bg-accent-hover"
          >
            {t("toExecution")}
          </Link>
        </EmptyState>
      </div>
    );
  }

  if (reportRes.kind === "unavailable") {
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
      <QualificationReportWorkbench
        runId={runId}
        report={reportRes.data}
        execution={executionRes.kind === "ok" ? executionRes.data : null}
        session={session}
        approveAction={approveQualificationReport}
      />
    </div>
  );
}
