// Server-side only: loads cross-tab undecided/blocker badge counts in parallel with safe fallback.
import { api, type DecisionCounts } from "@/api/client";
import { bearerHeaders, currentSession } from "@/auth/session";
import type { RunTab } from "@/components/RunHeader";

export async function loadTabBadges(
  runId: string,
  existingCounts?: DecisionCounts,
): Promise<Partial<Record<RunTab, number>>> {
  const session = await currentSession();
  if (session === null) return {};
  try {
    const headers = await bearerHeaders();
    const path = { params: { path: { run_id: runId } }, headers };
    const [countsRes, protocolRes] = await Promise.all([
      existingCounts ? Promise.resolve({ data: existingCounts }) : api.GET("/runs/{run_id}/decision-counts", path),
      api.GET("/runs/{run_id}/protocol", path),
    ]);
    const badges: Partial<Record<RunTab, number>> = {};
    const c = countsRes.data;
    if (c) {
      badges.matrix = c.coverage.undecided + c.coverage.changed;
      badges.findings = c.check.undecided + c.check.changed + c.ai.undecided + c.ai.changed;
      badges.draft = c.draft.undecided + c.draft.changed;
    }
    const p = protocolRes.data;
    if (p && p.status === "draft" && p.checklist) {
      badges.protocol = p.checklist.reduce((sum, item) => sum + item.count, 0);
    }
    return badges;
  } catch {
    return {};
  }
}
