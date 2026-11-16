import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { currentSession, signOut } from "@/auth/session";

async function signOutAction() {
  "use server";
  await signOut();
  redirect("/signin");
}

/** Who is signed in, always as a demo identity, with a sign-out button. */
export async function SessionBar() {
  const t = await getTranslations("signin");
  const session = await currentSession();
  if (session === null) return <a href="/signin">{t("link")}</a>;
  return (
    <form action={signOutAction}>
      <span>{t("signedInAs", { name: session.name })}</span>{" "}
      <button type="submit">{t("out")}</button>
    </form>
  );
}
