"use server";

import { redirect } from "next/navigation";

import {
  discoverOidc,
  isOidcMode,
  oidcClientId,
  publicOrigin,
  strictReturnTo,
} from "@/auth/oidc";
import { signOut } from "@/auth/session";

/** Clears the local session and, in OIDC mode, redirects through Keycloak's end_session_endpoint
 * (with `id_token_hint`) so the SSO session ends too. Returns to `postLogoutPath` afterwards. */
async function endSessionAndRedirect(postLogoutPath: string): Promise<never> {
  const idToken = await signOut();
  let logoutUrl: string | null = null;
  if (isOidcMode()) {
    try {
      const discovery = await discoverOidc();
      if (discovery.end_session_endpoint) {
        const url = new URL(discovery.end_session_endpoint);
        url.searchParams.set("post_logout_redirect_uri", `${publicOrigin()}${postLogoutPath}`);
        if (idToken) {
          url.searchParams.set("id_token_hint", idToken);
        } else if (oidcClientId()) {
          url.searchParams.set("client_id", oidcClientId());
        }
        logoutUrl = url.toString();
      }
    } catch {
      // Fall through to local redirect if discovery is unreachable.
    }
  }
  redirect(logoutUrl ?? postLogoutPath);
}

export async function signOutAction(): Promise<void> {
  await endSessionAndRedirect("/signin");
}

/** "Ganti persona". In OIDC mode the Keycloak SSO session would silently sign the same user back
 * in, so it ends that session first and lands on `/signin?next=<strict returnTo>`. In demo mode it
 * only navigates to `/signin?next=` (the demo picker issues a fresh token). */
export async function switchPersonaAction(next: string): Promise<void> {
  const signInPath = `/signin?next=${encodeURIComponent(strictReturnTo(next))}`;
  if (!isOidcMode()) {
    redirect(signInPath);
  }
  await endSessionAndRedirect(signInPath);
}
