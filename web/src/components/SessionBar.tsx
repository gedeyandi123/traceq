import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { currentSession, signOut } from "@/auth/session";

import s from "./SessionBar.module.css";

async function signOutAction() {
  "use server";
  await signOut();
  redirect("/signin");
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0] ?? "")
    .join("")
    .toUpperCase();
}

/** Who is signed in, always as a demo identity, with a sign-out button. */
export async function SessionBar() {
  const t = await getTranslations("signin");
  const session = await currentSession();
  if (session === null)
    return (
      <a href="/signin" className={s.signin}>
        {t("link")}
      </a>
    );
  return (
    <form action={signOutAction} className={s.bar}>
      <span className={s.avatar} aria-hidden="true">
        {initials(session.name)}
      </span>
      <span className={s.who}>{t("signedInAs", { name: session.name })}</span>
      <button type="submit" className={s.out}>
        {t("out")}
      </button>
    </form>
  );
}
