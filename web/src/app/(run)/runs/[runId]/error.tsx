"use client";

import { useTranslations } from "next-intl";

import { RouteErrorView } from "@/components/ui/RouteErrorView";

export default function RunError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("runHeader");
  const app = useTranslations("app");
  return (
    <RouteErrorView
      title={t("errorTitle")}
      body={t("errorBody")}
      retryLabel={t("retry")}
      homeLabel={app("toRuns")}
      digest={error.digest}
      onReset={reset}
    />
  );
}
