import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { EquipmentRegistryView } from "@/components/EquipmentRegistryView";
import { Alert } from "@/components/ui/Alert";
import { EmptyState } from "@/components/ui/ui";
import { fetchEquipmentList } from "@/runs/fetchers";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const [eq, app] = await Promise.all([getTranslations("equipment"), getTranslations("app")]);
  return { title: { absolute: `${eq("title")} · ${app("title")}` } };
}

/** Equipment Registry (`/equipment`, Step 7). */
export default async function EquipmentPage() {
  const t = await getTranslations("equipment");
  const signin = await getTranslations("signin");
  const res = await fetchEquipmentList();

  return (
    <div className="space-y-5">
      <div>
        <h1 className="m-0 text-xl font-bold tracking-tight text-ink">{t("title")}</h1>
        <p className="mt-1 mb-0 max-w-3xl text-sm text-ink-muted">{t("lead")}</p>
      </div>

      {res.kind === "unauthorized" && (
        <Alert tone="info">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="m-0 text-info">{t("signedOutBanner")}</p>
            <Link
              href="/signin?next=/equipment"
              className="inline-flex shrink-0 items-center rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent no-underline hover:bg-accent-hover"
            >
              {signin("link")}
            </Link>
          </div>
        </Alert>
      )}

      {res.kind === "unavailable" && (
        <EmptyState title={t("unavailableTitle")}>{t("unavailable")}</EmptyState>
      )}

      {res.kind === "ok" && <EquipmentRegistryView items={res.data} />}
    </div>
  );
}
