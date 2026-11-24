import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { currentSession } from "@/auth/session";
import { AssembledProtocolView, type ProtocolError } from "@/components/AssembledProtocolView";
import { EmptyState } from "@/components/ui/ui";
import { decisionError, loadDecisions } from "@/decisions/load";
import {
  answerMissedNumber,
  answerMissedNumberInline,
  approveProtocol,
  editDraftedTestStep,
  editDraftedTestStepInline,
  removeTestStep,
  removeTestStepInline,
  returnProtocol,
  startProtocol,
  submitProtocol,
  withdrawProtocol,
  writeTestStep,
  writeTestStepInline,
} from "@/protocol/actions";
import { fetchProtocol, fetchRun } from "@/runs/fetchers";

export const dynamic = "force-dynamic";

const PROTOCOL_ERRORS: readonly ProtocolError[] = [
  "conflict",
  "refused",
  "invalid",
  "forbidden",
  "unauthorized",
  "failed",
];

/** The browser tab reads "<screen> · TraceQ" (the root layout's template); translations only, no fetch. */
export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("protocol"))("title") };
}

/** The Protocol assembled in TraceQ from this run (spec #247, ticket #249). The API serves it
 * with a token only; any signed-in role reads it, the deciding role starts, submits and withdraws it
 * and decides its drafted Test Steps, the approving role approves or returns it. */
export default async function ProtocolPage({
  params,
  searchParams,
}: {
  params: Promise<{ runId: string }>;
  searchParams: Promise<{
    error?: string | string[];
    protocolError?: string | string[];
    selected?: string | string[];
  }>;
}) {
  const { runId } = await params;
  const query = await searchParams;
  const t = await getTranslations("protocol");
  const signin = await getTranslations("signin");
  const [run, decisions, session, protocolRes] = await Promise.all([
    fetchRun(runId),
    loadDecisions(runId),
    currentSession(),
    fetchProtocol(runId),
  ]);
  decisions.error = decisionError(query.error);
  if (!run) notFound();
  const selected = typeof query.selected === "string" && query.selected.trim() !== "" ? query.selected : null;
  const signInHref = `/signin?next=${encodeURIComponent(`/runs/${encodeURIComponent(runId)}/protocol`)}`;
  const heading = (
    <div>
      <h1 className="m-0 text-lg font-bold text-ink">{t("title")}</h1>
      <p className="mt-0.5 mb-0 text-xs text-ink-muted">{t("intro")}</p>
    </div>
  );
  const access = decisions.access;
  if (access.mode === "readOnly" && access.why !== "noRole") {
    const why =
      access.why === "signedOut"
        ? "signedOut"
        : access.why === "notImported"
          ? "notImported"
          : "unavailable";
    return (
      <div className="space-y-4">
        {heading}
        <EmptyState title={t(why)}>
          <p className="m-0">{t(`${why}Body`)}</p>
          {access.why === "signedOut" && (
            <div className="mt-3">
              <Link
                href={signInHref}
                className="inline-flex items-center rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent no-underline hover:bg-accent-hover"
              >
                {signin("link")}
              </Link>
            </div>
          )}
        </EmptyState>
      </div>
    );
  }
  if (protocolRes.kind === "unavailable") {
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
      <AssembledProtocolView
        protocol={protocolRes.kind === "ok" ? protocolRes.data : null}
        runId={runId}
        decisions={decisions}
        controls={
          access.mode === "decide"
            ? {
                start: startProtocol,
                withdraw: withdrawProtocol,
                write: writeTestStep,
                remove: removeTestStep,
                edit: editDraftedTestStep,
                answer: answerMissedNumber,
                submit: submitProtocol,
                writeInline: writeTestStepInline,
                removeInline: removeTestStepInline,
                editInline: editDraftedTestStepInline,
                answerInline: answerMissedNumberInline,
              }
            : null
        }
        approval={session?.mayApprove ? { approve: approveProtocol, return: returnProtocol } : null}
        error={PROTOCOL_ERRORS.find((e) => e === query.protocolError)}
        initialSelected={selected}
      />
    </div>
  );
}
