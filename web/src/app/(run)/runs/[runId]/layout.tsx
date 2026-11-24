import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { signOutAction } from "@/auth/actions";
import { currentSession } from "@/auth/session";
import { RunShell } from "@/components/RunShell";
import type { RunSidebarBadges } from "@/components/RunSidebar";
import { fetchDecisionCounts, fetchProtocol, fetchRun } from "@/runs/fetchers";

export default async function RunWorkspaceLayout({
  params,
  children,
}: {
  params: Promise<{ runId: string }>;
  children: ReactNode;
}) {
  const { runId } = await params;
  const [run, counts, protocolRes, session] = await Promise.all([
    fetchRun(runId),
    fetchDecisionCounts(runId),
    fetchProtocol(runId),
    currentSession(),
  ]);

  if (!run) notFound();

  const badges: RunSidebarBadges = counts
    ? {
        matrix: counts.coverage.undecided + counts.coverage.changed,
        findings:
          counts.check.undecided +
          counts.check.changed +
          counts.ai.undecided +
          counts.ai.changed,
        draft: counts.draft.undecided + counts.draft.changed,
      }
    : {};

  const protocolStatus = protocolRes.kind === "ok" ? protocolRes.data.status : null;

  return (
    <RunShell
      run={run}
      badges={badges}
      protocolStatus={protocolStatus}
      session={session}
      signOutAction={signOutAction}
    >
      {children}
    </RunShell>
  );
}
