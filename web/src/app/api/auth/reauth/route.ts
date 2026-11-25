import { NextResponse } from "next/server";

import {
  cookieOptions,
  discoverOidc,
  isOidcMode,
  OIDC_TX_COOKIE,
  type OidcTx,
  oidcClientId,
  pkcePair,
  publicOrigin,
  randomToken,
  strictReturnTo,
} from "@/auth/oidc";
import { currentSession } from "@/auth/session";

export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const origin = publicOrigin(url.origin);
  const returnTo = strictReturnTo(url.searchParams.get("next") ?? url.searchParams.get("returnTo"));

  if (!isOidcMode()) {
    return NextResponse.redirect(`${origin}${returnTo}`);
  }

  const session = await currentSession();
  if (!session) {
    return NextResponse.redirect(`${origin}/signin?next=${encodeURIComponent(returnTo)}`);
  }

  const discovery = await discoverOidc();
  const { codeVerifier, codeChallenge } = pkcePair();
  const state = randomToken();
  const nonce = randomToken();

  const authUrl = new URL(discovery.authorization_endpoint);
  authUrl.searchParams.set("client_id", oidcClientId());
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("scope", "openid profile email");
  authUrl.searchParams.set("redirect_uri", `${origin}/api/auth/callback`);
  authUrl.searchParams.set("state", state);
  authUrl.searchParams.set("nonce", nonce);
  authUrl.searchParams.set("code_challenge", codeChallenge);
  authUrl.searchParams.set("code_challenge_method", "S256");
  authUrl.searchParams.set("prompt", "login");
  authUrl.searchParams.set("max_age", "0");
  if (session.username) {
    authUrl.searchParams.set("login_hint", session.username);
  }

  const tx: OidcTx = {
    state,
    nonce,
    codeVerifier,
    returnTo,
    mode: "reauth",
    expectedSub: session.subject,
    expectedIss: session.issuer,
  };

  const response = NextResponse.redirect(authUrl.toString());
  response.cookies.set(OIDC_TX_COOKIE, JSON.stringify(tx), cookieOptions({ maxAge: 300 }));
  return response;
}
