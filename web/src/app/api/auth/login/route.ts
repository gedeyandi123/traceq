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

export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const origin = publicOrigin(url.origin);
  if (!isOidcMode()) {
    return NextResponse.redirect(`${origin}/signin`);
  }

  const returnTo = strictReturnTo(url.searchParams.get("next") ?? url.searchParams.get("returnTo"));
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

  const tx: OidcTx = {
    state,
    nonce,
    codeVerifier,
    returnTo,
    mode: "login",
  };

  const response = NextResponse.redirect(authUrl.toString());
  response.cookies.set(OIDC_TX_COOKIE, JSON.stringify(tx), cookieOptions({ maxAge: 300 }));
  return response;
}
