import { ArrowRight } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";

import type { EquipmentSummary } from "@/api/client";
import {
  ExecutionStatusBadge,
  ProtocolStatusBadge,
  RoundStatusBadge,
  TechnicalConclusionBadge,
} from "@/components/ui/StatusBadge";
import { EmptyState } from "@/components/ui/ui";

/** Equipment Registry table (`/equipment`, Step 7).
 * Every nested summary (`latest_round`, `latest_protocol`, `latest_execution`,
 * `latest_qualification_report`) links using its own `run_id`. */
export function EquipmentRegistryView({ items }: { items: EquipmentSummary[] }) {
  const t = useTranslations("equipment");

  if (items.length === 0) {
    return <EmptyState title={t("emptyTitle")}>{t("empty")}</EmptyState>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface shadow-xs">
      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-border bg-sunken/70 text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
            <th scope="col" className="px-4 py-2.5">
              {t("colEquipment")}
            </th>
            <th scope="col" className="px-4 py-2.5">
              {t("colRound")}
            </th>
            <th scope="col" className="px-4 py-2.5">
              {t("colProtocol")}
            </th>
            <th scope="col" className="px-4 py-2.5">
              {t("colExecution")}
            </th>
            <th scope="col" className="px-4 py-2.5">
              {t("colReport")}
            </th>
            <th scope="col" className="px-4 py-2.5">
              {t("colRequal")}
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map((eq) => {
            const lr = eq.latest_run;
            const round = eq.latest_round;
            const proto = eq.latest_protocol;
            const exec = eq.latest_execution;
            const rep = eq.latest_qualification_report;

            return (
              <tr key={eq.equipment} className="transition-colors hover:bg-sunken/40">
                <th scope="row" className="px-4 py-3 font-semibold text-ink">
                  <div className="flex flex-col gap-0.5">
                    {lr ? (
                      <Link
                        href={`/runs/${encodeURIComponent(lr.run_id)}`}
                        className="inline-flex items-center gap-1 font-bold text-accent no-underline tabular-nums hover:text-accent-hover hover:underline"
                      >
                        <span>{eq.equipment}</span>
                        <ArrowRight className="h-3 w-3" aria-hidden="true" />
                      </Link>
                    ) : (
                      <span className="font-bold text-ink tabular-nums">{eq.equipment}</span>
                    )}
                    <span className="text-[11px] font-normal text-ink-muted tabular-nums">
                      {t("runCount", { count: eq.run_count })}
                    </span>
                    <Link
                      href={`/equipment/${encodeURIComponent(eq.equipment)}/upload`}
                      className="text-[11px] font-semibold text-accent no-underline hover:underline"
                    >
                      {t("uploadLink")}
                    </Link>
                  </div>
                </th>

                <td className="px-4 py-3 text-xs">
                  {round ? (
                    <Link
                      href={`/runs/${encodeURIComponent(round.run_id)}/rounds`}
                      className="inline-flex items-center no-underline hover:opacity-85"
                    >
                      <RoundStatusBadge status={round.status} roundNumber={round.round_number} />
                    </Link>
                  ) : (
                    <span className="text-ink-muted">—</span>
                  )}
                </td>

                <td className="px-4 py-3 text-xs">
                  {proto ? (
                    <Link
                      href={`/runs/${encodeURIComponent(proto.run_id)}/protocol`}
                      className="inline-flex items-center no-underline hover:opacity-85"
                    >
                      <ProtocolStatusBadge status={proto.status} />
                    </Link>
                  ) : (
                    <span className="text-ink-muted">—</span>
                  )}
                </td>

                <td className="px-4 py-3 text-xs">
                  {exec ? (
                    <Link
                      href={`/runs/${encodeURIComponent(exec.run_id)}/execution`}
                      className="inline-flex flex-wrap items-center gap-1.5 no-underline hover:opacity-85"
                    >
                      <ExecutionStatusBadge status={exec.status} />
                      {exec.open_deviations > 0 && (
                        <span className="inline-flex items-center rounded-full border border-warn-edge bg-warn-soft px-2 py-0.5 text-[11px] font-semibold text-warn tabular-nums">
                          {t("openDeviations", { count: exec.open_deviations })}
                        </span>
                      )}
                    </Link>
                  ) : (
                    <span className="text-ink-muted">—</span>
                  )}
                </td>

                <td className="px-4 py-3 text-xs">
                  {rep ? (
                    <Link
                      href={`/runs/${encodeURIComponent(rep.run_id)}/report`}
                      className="inline-flex flex-wrap items-center gap-1.5 no-underline hover:opacity-85"
                    >
                      <TechnicalConclusionBadge conclusion={rep.technical_conclusion} size="xs" />
                      <span className="font-mono text-[11px] font-semibold text-ink-muted tabular-nums">
                        Rev {rep.revision_number}
                      </span>
                    </Link>
                  ) : (
                    <span className="text-ink-muted">—</span>
                  )}
                </td>

                <td className="px-4 py-3 text-xs whitespace-nowrap text-ink-muted tabular-nums">
                  {rep?.next_requalification_date ?? t("unscheduled")}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
