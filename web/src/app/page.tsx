import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { api } from "@/api/client";
import { formatWhen } from "@/components/formatWhen";
import { cell, DataTable, EmptyState, ModeBadge } from "@/components/ui/ui";

import s from "./page.module.css";

export const dynamic = "force-dynamic";

/** The browser tab reads "<screen> · TraceQ"; translations only, no fetch. The root layout's
 * template does not apply to a page in the layout's own segment, so the title is absolute. */
export async function generateMetadata(): Promise<Metadata> {
  const [runs, app] = await Promise.all([getTranslations("runs"), getTranslations("app")]);
  return { title: { absolute: `${runs("title")} · ${app("title")}` } };
}

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
            {data.map((r) => (
              <tr key={r.run_id}>
                <th scope="row" className={cell.id}>
                  <Link href={`/runs/${encodeURIComponent(r.run_id)}`}>{r.run_id}</Link>
                </th>
                <td className={s.equipment}>{r.equipment}</td>
                <td>{r.model}</td>
                <td>
                  <ModeBadge>{t(r.mode)}</ModeBadge>
                </td>
                <td className={cell.num}>{formatWhen(when, r.created)}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      )}
    </>
  );
}
