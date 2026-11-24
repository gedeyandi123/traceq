import { getTranslations } from "next-intl/server";

export default async function HomeLoading() {
  const t = await getTranslations("runs");
  return (
    <div role="status" aria-label={t("title")} className="space-y-4">
      <span className="sr-only">{t("title")}</span>
      <div className="space-y-2">
        <div className="h-6 w-48 animate-pulse rounded bg-sunken" />
        <div className="h-4 w-80 max-w-full animate-pulse rounded bg-sunken" />
      </div>
      <div className="rounded-lg border border-border bg-surface p-4">
        <div className="space-y-3">
          <div className="h-9 w-full animate-pulse rounded bg-sunken" />
          <div className="h-10 w-full animate-pulse rounded bg-sunken" />
          <div className="h-10 w-full animate-pulse rounded bg-sunken" />
        </div>
      </div>
    </div>
  );
}
