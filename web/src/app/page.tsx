import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { api } from "@/api/client";

export const dynamic = "force-dynamic";

export default async function RunsPage() {
  const t = await getTranslations("runs");
  const { data } = await api.GET("/runs").catch(() => ({ data: undefined }));
  return (
    <>
      <h1>{t("title")}</h1>
      {data === undefined && <p>{t("unavailable")}</p>}
      {data?.length === 0 && <p>{t("empty")}</p>}
      <ul>
        {data?.map((r) => (
          <li key={r.run_id}>
            <Link href={`/runs/${encodeURIComponent(r.run_id)}`}>{r.run_id}</Link>
            {" · "}
            {t("equipment")} {r.equipment} · {t("model")} {r.model} · {t("mode")} {t(r.mode)}
          </li>
        ))}
      </ul>
    </>
  );
}
