"use client";

import { useTranslations } from "next-intl";

import { RouteErrorView } from "@/components/ui/RouteErrorView";

export default function HomeError({
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
      title={t("homeErrorTitle")}
      body={t("homeErrorBody")}
      retryLabel={t("retry")}
      homeLabel={app("toRuns")}
      digest={error.digest}
      onReset={reset}
    />
  );
}
