import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { api } from "@/api/client";
import { cell, DataTable, EmptyState } from "@/components/ui/ui";

import s from "./page.module.css";

export const dynamic = "force-dynamic";

/** The browser tab reads "<screen> · TraceQ" (the root layout's template); translations only, no fetch. */
export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("runs"))("title") };
}

// The same format as the run header and the decision timestamps.
const date = new Intl.DateTimeFormat("id-ID", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" });
const time = new Intl.DateTimeFormat("id-ID", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });

export default async function RunsPage() {
  const t = await getTranslations("runs");
  const when = await getTranslations("decisions");
  const { data } = await api.GET("/runs").catch(() => ({ data: undefined }));
  return (
    <>
      <div className={s.head}>
        <h1>{t("title")}</h1>
        <p className={s.lead}>{t("lead")}</p>
      </div>
      {data === undefined && <EmptyState title={t("unavailableTitle")}>{t("unavailable")}</EmptyState>}
      {data?.length === 0 && <EmptyState title={t("emptyTitle")}>{t("empty")}</EmptyState>}
      {data !== undefined && data.length > 0 && (
        <DataTable>
          <thead>
            <tr>
              <th scope="col">{t("run")}</th>
              <th scope="col">{t("equipment")}</th>
              <th scope="col">{t("model")}</th>
              <th scope="col">{t("mode")}</th>
              <th scope="col">{t("created")}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((r) => {
              const created = new Date(r.created);
              return (
                <tr key={r.run_id}>
                  <th scope="row" className={cell.id}>
                    <Link href={`/runs/${encodeURIComponent(r.run_id)}`}>{r.run_id}</Link>
                  </th>
                  <td className={s.equipment}>{r.equipment}</td>
                  <td>{r.model}</td>
                  <td>
                    <span className={s.mode}>{t(r.mode)}</span>
                  </td>
                  <td className={cell.num}>{when("when", { date: date.format(created), time: time.format(created) })}</td>
                </tr>
              );
            })}
          </tbody>
        </DataTable>
      )}
    </>
  );
}
