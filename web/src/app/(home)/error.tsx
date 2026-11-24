"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";

import { Alert, Button } from "@/components/ui/ui";

export default function HomeError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("runHeader");
  const app = useTranslations("app");
  return (
    <Alert tone="fail" role="alert" title={t("errorTitle")}>
      <p className="m-0 text-sm text-ink">{t("errorBody")}</p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button type="button" variant="soft" onClick={reset}>
          {t("retry")}
        </Button>
        <Link
          href="/"
          className="text-xs font-semibold text-accent no-underline hover:text-accent-hover hover:underline"
        >
          {app("toRuns")}
        </Link>
      </div>
    </Alert>
  );
}
