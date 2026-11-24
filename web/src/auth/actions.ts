"use server";

import { redirect } from "next/navigation";

import { signOut } from "@/auth/session";

export async function signOutAction(): Promise<void> {
  await signOut();
  redirect("/signin");
}
