import { getTranslations } from "next-intl/server";

export default async function RunLoading() {
  const t = await getTranslations("runHeader");
  return (
    <div role="status" aria-label={t("loading")} className="space-y-4">
      <span className="sr-only">{t("loading")}</span>
      <div className="space-y-2">
        <div className="h-6 w-56 animate-pulse rounded bg-sunken" />
        <div className="h-4 w-96 max-w-full animate-pulse rounded bg-sunken" />
      </div>
      <div className="rounded-lg border border-border bg-surface p-4">
        <div className="space-y-3">
          <div className="h-8 w-full animate-pulse rounded bg-sunken" />
          <div className="h-10 w-full animate-pulse rounded bg-sunken" />
          <div className="h-10 w-full animate-pulse rounded bg-sunken" />
          <div className="h-10 w-full animate-pulse rounded bg-sunken" />
          <div className="h-10 w-full animate-pulse rounded bg-sunken" />
        </div>
      </div>
    </div>
  );
}
