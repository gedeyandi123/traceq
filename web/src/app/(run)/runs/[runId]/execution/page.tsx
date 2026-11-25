import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { currentSession } from "@/auth/session";
import { ExecutionViewPanel } from "@/components/ExecutionView";
import { EmptyState } from "@/components/ui/ui";
import {
  addDeviationInvestigation,
  closeDeviation,
  confirmWitness,
  openManualDeviation,
  recordAttempt,
  returnDeviation,
  startExecution,
  submitDeviation,
} from "@/execution/actions";
import { fetchExecution, fetchProtocol, fetchRun } from "@/runs/fetchers";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("execution"))("title") };
}

/** Execution of an Approved Protocol (ADR 0013, spec #270, #271). Any signed-in role reads it;
 * only `qualification-executor` may start it from an Approved Protocol. */
export default async function ExecutionPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  const t = await getTranslations("execution");
  const signin = await getTranslations("signin");
  const [run, session, protocolRes, executionRes] = await Promise.all([
    fetchRun(runId),
    currentSession(),
    fetchProtocol(runId),
    fetchExecution(runId),
  ]);
  if (!run) notFound();

  const heading = (
    <div>
      <h1 className="m-0 text-lg font-bold text-ink">{t("title")}</h1>
      <p className="mt-0.5 mb-0 text-xs text-ink-muted">{t("intro")}</p>
    </div>
  );

  const signInHref = `/signin?next=${encodeURIComponent(`/runs/${encodeURIComponent(runId)}/execution`)}`;
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

  if (protocolRes.kind === "unavailable" || executionRes.kind === "unavailable") {
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
      <ExecutionViewPanel
        execution={executionRes.kind === "ok" ? executionRes.data : null}
        protocol={protocolRes.kind === "ok" ? protocolRes.data : null}
        runId={runId}
        currentUser={{ subject: session.subject, issuer: session.issuer }}
        startAction={session.mayExecute ? startExecution : null}
        recordAction={session.mayExecute ? recordAttempt : null}
        witnessAction={session.mayWitness ? confirmWitness : null}
        openDeviationAction={session.mayExecute ? openManualDeviation : null}
        investigateAction={session.mayExecute ? addDeviationInvestigation : null}
        submitDeviationAction={session.mayExecute ? submitDeviation : null}
        closeDeviationAction={session.mayApprove ? closeDeviation : null}
        returnDeviationAction={session.mayApprove ? returnDeviation : null}
      />
    </div>
  );
}
