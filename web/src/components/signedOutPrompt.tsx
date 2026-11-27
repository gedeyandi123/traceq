import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { EmptyState } from "@/components/ui/ui";

/** What a signed-out viewer sees in place of a run screen: the run routes need a token, so
 * without a session there is nothing to show but the way to sign in. */
export async function signedOutPrompt(next: string) {
  const t = await getTranslations("runs");
  const signin = await getTranslations("signin");
  return (
    <EmptyState title={t("signedOutTitle")}>
      <p className="m-0 mb-3">{t("signedOutBody")}</p>
      <Link
        href={`/signin?next=${encodeURIComponent(next)}`}
        className="inline-flex items-center rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent no-underline hover:bg-accent-hover"
      >
        {signin("link")}
      </Link>
    </EmptyState>
  );
}
