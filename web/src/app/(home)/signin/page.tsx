import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { listPersonas, signIn } from "@/auth/session";
import { SignInView } from "@/components/SignInView";

export const dynamic = "force-dynamic";

/** The browser tab reads "<screen> · TraceQ" (the root layout's template); translations only, no fetch. */
export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("signin"))("title") };
}

async function signInAction(formData: FormData) {
  "use server";
  const username = formData.get("username");
  if (typeof username === "string" && (await signIn(username))) redirect("/");
  redirect("/signin");
}

export default async function SignInPage() {
  return <SignInView personas={await listPersonas()} action={signInAction} />;
}
