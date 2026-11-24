"use client";

import { AlertCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";

import { Button } from "@/components/ui/ui";

export default function RunError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("runHeader");
  const app = useTranslations("app");
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-lg border border-fail-edge border-l-[3px] border-l-fail bg-fail-soft px-4 py-3 text-sm text-fail"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0">
        <div className="mb-1 font-semibold">{t("errorTitle")}</div>
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
      </div>
    </div>
  );
}
