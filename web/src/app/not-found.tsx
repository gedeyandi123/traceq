import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { EmptyState } from "@/components/ui/ui";

/** The 404 of every route, also for a run the API does not know (`notFound()`). */
export default async function NotFound() {
  const t = await getTranslations("app");
  return (
    <EmptyState title={t("notFoundTitle")}>
      <p>{t("notFoundBody")}</p>
      <p style={{ marginTop: "var(--space-3)" }}>
        <Link href="/">{t("toRuns")}</Link>
      </p>
    </EmptyState>
  );
}
