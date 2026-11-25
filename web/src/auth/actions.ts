"use server";

import { redirect } from "next/navigation";

import { discoverOidc, isOidcMode, oidcClientId, publicOrigin } from "@/auth/oidc";
import { signOut } from "@/auth/session";

export async function signOutAction(): Promise<void> {
  const idToken = await signOut();
  let logoutUrl: string | null = null;
  if (isOidcMode()) {
    try {
      const discovery = await discoverOidc();
      if (discovery.end_session_endpoint) {
        const url = new URL(discovery.end_session_endpoint);
        url.searchParams.set("post_logout_redirect_uri", `${publicOrigin()}/signin`);
        if (idToken) {
          url.searchParams.set("id_token_hint", idToken);
        } else if (oidcClientId()) {
          url.searchParams.set("client_id", oidcClientId());
        }
        logoutUrl = url.toString();
      }
    } catch {
      // Fall through to local /signin redirect if discovery is unreachable.
    }
  }
  redirect(logoutUrl ?? "/signin");
}
