import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { api } from "@/api/client";
import { formatWhen } from "@/components/formatWhen";
import { EmptyState, ModeBadge } from "@/components/ui/ui";

export const dynamic = "force-dynamic";

/** The browser tab reads "<screen> · TraceQ"; translations only, no fetch. */
export async function generateMetadata(): Promise<Metadata> {
  const [runs, app] = await Promise.all([getTranslations("runs"), getTranslations("app")]);
  return { title: { absolute: `${runs("title")} · ${app("title")}` } };
}

export default async function RunsPage() {
  const t = await getTranslations("runs");
  const when = await getTranslations("decisions");
  const { data } = await api.GET("/runs").catch(() => ({ data: undefined }));

  return (
    <div className="space-y-5">
      <div>
        <h1 className="m-0 text-xl font-bold tracking-tight text-ink">{t("title")}</h1>
        <p className="mt-1 mb-0 max-w-3xl text-sm text-ink-muted">{t("lead")}</p>
      </div>

      {data === undefined && <EmptyState title={t("unavailableTitle")}>{t("unavailable")}</EmptyState>}
      {data?.length === 0 && <EmptyState title={t("emptyTitle")}>{t("empty")}</EmptyState>}

      {data !== undefined && data.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border bg-surface shadow-xs">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-border bg-sunken/70 text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
                <th scope="col" className="px-4 py-2.5">
                  {t("equipment")}
                </th>
                <th scope="col" className="px-4 py-2.5">
                  {t("mode")}
                </th>
                <th scope="col" className="px-4 py-2.5">
                  {t("model")}
                </th>
                <th scope="col" className="px-4 py-2.5">
                  {t("created")}
                </th>
                <th scope="col" className="px-4 py-2.5">
                  {t("run")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.map((r) => (
                <tr key={r.run_id} className="transition-colors hover:bg-sunken/40">
                  <th scope="row" className="px-4 py-3 font-semibold text-ink">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        href={`/runs/${encodeURIComponent(r.run_id)}`}
                        className="font-bold text-accent no-underline tabular-nums hover:text-accent-hover hover:underline"
                      >
                        {r.equipment}
                      </Link>
                      {r.review_package && (
                        <span className="inline-flex items-center rounded-full border border-info-edge bg-info-soft px-2 py-0.5 text-[11px] font-semibold text-info tabular-nums">
                          {`${t("reviewPackageBadge")}: ${r.review_package.doc_id}`}
                        </span>
                      )}
                    </div>
                  </th>
                  <td className="px-4 py-3">
                    <ModeBadge>{t(r.mode)}</ModeBadge>
                  </td>
                  <td className="px-4 py-3 text-xs text-ink-muted">{r.model}</td>
                  <td className="px-4 py-3 text-xs whitespace-nowrap text-ink-muted tabular-nums">
                    {formatWhen(when, r.created)}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-ink-muted tabular-nums">
                    {r.run_id}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
