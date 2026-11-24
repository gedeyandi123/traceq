import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { signOutAction } from "@/auth/actions";
import { currentSession } from "@/auth/session";

/** Who is signed in, always as a demo identity, with a sign-out button. */
export async function SessionBar() {
  const t = await getTranslations("signin");
  const session = await currentSession();
  if (session === null) {
    return (
      <Link
        href="/signin"
        className="inline-flex h-8 items-center rounded-md border border-border bg-surface px-3 text-xs font-semibold text-ink no-underline transition-colors hover:bg-sunken"
      >
        {t("link")}
      </Link>
    );
  }
  return (
    <form action={signOutAction} className="flex items-center gap-2.5">
      <span className="hidden text-xs text-ink-muted sm:inline">{t("signedInAs", { name: session.name })}</span>
      <button
        type="submit"
        data-tw=""
        className="inline-flex h-8 cursor-pointer items-center rounded-md border border-border bg-surface px-3 text-xs font-semibold text-ink transition-colors hover:bg-sunken"
      >
        {t("out")}
      </button>
    </form>
  );
}
