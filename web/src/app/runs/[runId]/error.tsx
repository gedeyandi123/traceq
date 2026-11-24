"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { Alert, Button } from "@/components/ui/ui";

export default function RunError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const t = useTranslations("runHeader");
  const app = useTranslations("app");
  return (
    <Alert tone="fail" role="alert" title={t("errorTitle")}>
      <p>{t("errorBody")}</p>
      <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center", marginTop: "var(--space-2)" }}>
        <Button type="button" variant="soft" onClick={reset}>
          {t("retry")}
        </Button>
        <Link href="/">{app("toRuns")}</Link>
      </div>
    </Alert>
  );
}
