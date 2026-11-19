import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { api } from "@/api/client";
import { bearerHeaders, currentSession } from "@/auth/session";
import { AssembledProtocolView, type ProtocolError } from "@/components/AssembledProtocolView";
import { RunHeader } from "@/components/RunHeader";
import { EmptyState } from "@/components/ui/ui";
import { decisionError, loadDecisions } from "@/decisions/load";
import {
  answerMissedNumber,
  approveProtocol,
  editDraftedTestStep,
  removeTestStep,
  returnProtocol,
  startProtocol,
  submitProtocol,
  withdrawProtocol,
  writeTestStep,
} from "@/protocol/actions";

export const dynamic = "force-dynamic";

const PROTOCOL_ERRORS: readonly ProtocolError[] = ["conflict", "refused", "invalid", "forbidden", "unauthorized", "failed"];

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
  searchParams: Promise<{ error?: string | string[]; protocolError?: string | string[] }>;
}) {
  const { runId } = await params;
  const query = await searchParams;
  const t = await getTranslations("protocol");
  const path = { params: { path: { run_id: runId } } };
  const [run, decisions, session] = await Promise.all([
    api.GET("/runs/{run_id}", path),
    loadDecisions(runId),
    currentSession(),
  ]);
  decisions.error = decisionError(query.error);
  if (!run.data) notFound();
  const header = <RunHeader run={run.data} current="protocol" intro={t("intro")} />;
  const access = decisions.access;
  if (access.mode === "readOnly" && access.why !== "noRole") {
    const why = access.why === "signedOut" ? "signedOut" : access.why === "notImported" ? "notImported" : "unavailable";
    return (
      <>
        {header}
        <EmptyState title={t(why)}>{t(`${why}Body`)}</EmptyState>
      </>
    );
  }
  let protocol;
  try {
    protocol = await api.GET("/runs/{run_id}/protocol", { ...path, headers: await bearerHeaders() });
  } catch {
    protocol = undefined;
  }
  if (!protocol || (!protocol.data && protocol.response.status !== 404)) {
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
      <AssembledProtocolView
        protocol={protocol.data ?? null}
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
              }
            : null
        }
        approval={session?.mayApprove ? { approve: approveProtocol, return: returnProtocol } : null}
        error={PROTOCOL_ERRORS.find((e) => e === query.protocolError)}
      />
    </>
  );
}
