import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { api } from "@/api/client";
import { EmptyState } from "@/components/ui/ui";
import tbl from "@/components/ui/table.module.css";

import s from "./page.module.css";

export const dynamic = "force-dynamic";

const created = new Intl.DateTimeFormat("id-ID", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
});

export default async function RunsPage() {
  const t = await getTranslations("runs");
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
        <div className={tbl.wrap}>
          <table className={tbl.table}>
            <thead>
              <tr>
                <th>{t("equipment")}</th>
                <th>{t("run")}</th>
                <th>{t("model")}</th>
                <th>{t("mode")}</th>
                <th>{t("created")}</th>
                <th>
                  <span className="visually-hidden">{t("open")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => {
                const href = `/runs/${encodeURIComponent(r.run_id)}`;
                return (
                  <tr key={r.run_id}>
                    <td className={s.equipment}>{r.equipment}</td>
                    <td>
                      <Link href={href} className={tbl.id}>
                        {r.run_id}
                      </Link>
                    </td>
                    <td>{r.model}</td>
                    <td>
                      <span className={s.mode}>{t(r.mode)}</span>
                    </td>
                    <td className="num">{created.format(new Date(r.created))} UTC</td>
                    <td className={s.open}>
                      <Link href={href} className={s.openLink}>
                        {t("open")} →
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
