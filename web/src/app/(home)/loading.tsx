import { getTranslations } from "next-intl/server";

export default async function HomeLoading() {
  const t = await getTranslations("runHeader");
  return (
    <div role="status" aria-label={t("loadingHome")} className="space-y-4">
      <span className="sr-only">{t("loadingHome")}</span>
      <div className="space-y-2">
        <div className="h-6 w-48 animate-pulse rounded bg-sunken motion-reduce:animate-none" />
        <div className="h-4 w-80 max-w-full animate-pulse rounded bg-sunken motion-reduce:animate-none" />
      </div>
      <div className="rounded-lg border border-border bg-surface p-4">
        <div className="space-y-3">
          <div className="h-9 w-full animate-pulse rounded bg-sunken motion-reduce:animate-none" />
          <div className="h-10 w-full animate-pulse rounded bg-sunken motion-reduce:animate-none" />
          <div className="h-10 w-full animate-pulse rounded bg-sunken motion-reduce:animate-none" />
        </div>
      </div>
    </div>
  );
}
