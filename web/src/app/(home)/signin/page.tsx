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

function validNextPath(raw: string | string[] | undefined): string | undefined {
  if (typeof raw !== "string") return undefined;
  const trimmed = raw.trim();
  if (!trimmed.startsWith("/") || trimmed.startsWith("//")) return undefined;
  return trimmed;
}

async function signInAction(formData: FormData) {
  "use server";
  const username = formData.get("username");
  const rawNext = formData.get("next");
  const nextPath = typeof rawNext === "string" ? validNextPath(rawNext) : undefined;
  if (typeof username === "string" && (await signIn(username))) {
    redirect(nextPath ?? "/");
  }
  redirect(nextPath ? `/signin?next=${encodeURIComponent(nextPath)}` : "/signin");
}

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const nextPath = validNextPath((await searchParams).next);
  return <SignInView personas={await listPersonas()} action={signInAction} nextPath={nextPath} />;
}
