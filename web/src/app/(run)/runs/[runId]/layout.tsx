import { NextIntlClientProvider } from "next-intl";
import { getMessages } from "next-intl/server";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { signOutAction } from "@/auth/actions";
import { currentSession } from "@/auth/session";
import { RunShell } from "@/components/RunShell";
import type { RunSidebarBadges } from "@/components/RunSidebar";
import { LOCALE } from "@/i18n/request";
import { fetchDecisionCounts, fetchExecution, fetchProtocol, fetchRounds, fetchRun } from "@/runs/fetchers";

export default async function RunWorkspaceLayout({
  params,
  children,
}: {
  params: Promise<{ runId: string }>;
  children: ReactNode;
}) {
  const { runId } = await params;
  const [run, counts, protocolRes, roundsRes, session, allMessages] = await Promise.all([
    fetchRun(runId),
    fetchDecisionCounts(runId),
    fetchProtocol(runId),
    fetchRounds(runId),
    currentSession(),
    getMessages(),
  ]);

  if (!run) notFound();

  const protocolStatus = protocolRes.kind === "ok" ? protocolRes.data.status : null;
  const currentRound =
    roundsRes.kind === "ok"
      ? (roundsRes.data.rounds.find((r) => r.id === roundsRes.data.current_round_id) ?? null)
      : null;
  const executionRes = protocolStatus === "approved" ? await fetchExecution(runId) : null;
  const executionData = executionRes?.kind === "ok" ? executionRes.data : null;
  const openDeviations = executionData
    ? executionData.deviations.filter((d) => d.status !== "closed").length
    : undefined;

  const badges: RunSidebarBadges = {
    ...(counts
      ? {
          matrix: counts.coverage.undecided + counts.coverage.changed,
          findings:
            counts.check.undecided +
            counts.check.changed +
            counts.ai.undecided +
            counts.ai.changed,
          draft: counts.draft.undecided + counts.draft.changed,
        }
      : {}),
    executionStatus: executionData?.status ?? null,
    openDeviations,
    roundBadge: currentRound
      ? { roundNumber: currentRound.round_number, status: currentRound.status }
      : null,
  };

  return (
    <NextIntlClientProvider locale={LOCALE} messages={allMessages}>
      <RunShell
        run={run}
        badges={badges}
        protocolStatus={protocolStatus}
        session={session}
        signOutAction={signOutAction}
      >
        {children}
      </RunShell>
    </NextIntlClientProvider>
  );
}
