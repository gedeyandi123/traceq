import { useTranslations } from "next-intl";
import Link from "next/link";

/** The 404 page: what happened, and the way back to the run list. Synchronous, so a render
 * test mounts it under the same provider as the other views; the not-found route only
 * renders it. */
export function NotFoundView() {
  const t = useTranslations("app");
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4 py-12">
      <section className="w-full max-w-md rounded-lg border border-border bg-surface p-6 text-center shadow-xs">
        <p className="m-0 text-4xl font-bold tracking-tight text-accent tabular-nums" aria-hidden="true">
          404
        </p>
        <h1 className="mt-2 mb-0 text-lg font-bold text-ink">{t("notFoundTitle")}</h1>
        <p className="mt-2 mb-0 text-sm leading-relaxed text-ink-muted">{t("notFoundBody")}</p>
        <div className="mt-5">
          <Link
            href="/"
            className="inline-flex h-9 items-center justify-center rounded-md bg-accent px-4 text-xs font-semibold text-on-accent no-underline transition-colors hover:bg-accent-hover"
          >
            {t("toRuns")}
          </Link>
        </div>
      </section>
    </div>
  );
}
