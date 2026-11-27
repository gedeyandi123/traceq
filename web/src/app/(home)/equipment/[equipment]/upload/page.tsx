import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { DraftUploadView } from "@/components/DraftUploadView";
import { Alert } from "@/components/ui/Alert";
import { EmptyState } from "@/components/ui/ui";
import { fetchDraftUploads } from "@/runs/fetchers";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const [t, app] = await Promise.all([getTranslations("upload"), getTranslations("app")]);
  return { title: { absolute: `${t("title")} · ${app("title")}` } };
}

/** Upload of a Protocol Draft revision for one Equipment (`/equipment/[equipment]/upload`). */
export default async function UploadPage({ params }: { params: Promise<{ equipment: string }> }) {
  const { equipment } = await params;
  const t = await getTranslations("upload");
  const signin = await getTranslations("signin");
  const res = await fetchDraftUploads(equipment);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="m-0 text-xl font-bold tracking-tight text-ink">
          {t("title")} · {equipment}
        </h1>
        <p className="mt-1 mb-0 max-w-3xl text-sm text-ink-muted">{t("lead")}</p>
      </div>

      {res.kind === "unauthorized" && (
        <Alert tone="info">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="m-0 text-info">{t("signedOut")}</p>
            <Link
              href={`/signin?next=/equipment/${encodeURIComponent(equipment)}/upload`}
              className="inline-flex shrink-0 items-center rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent no-underline hover:bg-accent-hover"
            >
              {signin("link")}
            </Link>
          </div>
        </Alert>
      )}
      {res.kind === "forbidden" && (
        <EmptyState title={t("forbiddenTitle")}>{t("forbidden")}</EmptyState>
      )}
      {res.kind === "not_enabled" && (
        <EmptyState title={t("notEnabledTitle")}>{t("notEnabled")}</EmptyState>
      )}
      {res.kind === "unavailable" && (
        <EmptyState title={t("unavailableTitle")}>{t("unavailable")}</EmptyState>
      )}
      {res.kind === "ok" && <DraftUploadView initial={res.data} />}
    </div>
  );
}
