import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  cookieOptions,
  decodeJwtPayload,
  discoverOidc,
  ID_TOKEN_COOKIE,
  isOidcMode,
  OIDC_TX_COOKIE,
  type OidcTx,
  oidcClientId,
  oidcClientSecret,
  publicOrigin,
  REAUTH_TOKEN_COOKIE,
  strictReturnTo,
  TOKEN_COOKIE,
} from "@/auth/oidc";

function parseTx(raw: string | undefined): OidcTx | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<OidcTx>;
    if (
      typeof parsed.state !== "string" ||
      typeof parsed.nonce !== "string" ||
      typeof parsed.codeVerifier !== "string" ||
      (parsed.mode !== "login" && parsed.mode !== "reauth")
    ) {
      return null;
    }
    return {
      state: parsed.state,
      nonce: parsed.nonce,
      codeVerifier: parsed.codeVerifier,
      returnTo: strictReturnTo(parsed.returnTo),
      mode: parsed.mode,
      expectedSub: typeof parsed.expectedSub === "string" ? parsed.expectedSub : undefined,
      expectedIss: typeof parsed.expectedIss === "string" ? parsed.expectedIss : undefined,
    };
  } catch {
    return null;
  }
}

export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const origin = publicOrigin(url.origin);
  if (!isOidcMode()) {
    return NextResponse.redirect(`${origin}/signin`);
  }

  const store = await cookies();
  const tx = parseTx(store.get(OIDC_TX_COOKIE)?.value);

  const clearTxRedirect = (target: string): NextResponse => {
    const res = NextResponse.redirect(target);
    res.cookies.delete(OIDC_TX_COOKIE);
    return res;
  };

  const errorParam = url.searchParams.get("error");
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");

  if (errorParam || !tx || !code || !state || state !== tx.state) {
    return clearTxRedirect(`${origin}/signin?error=oidc_failed`);
  }

  const discovery = await discoverOidc();
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: oidcClientId(),
    code,
    redirect_uri: `${origin}/api/auth/callback`,
    code_verifier: tx.codeVerifier,
  });
  const secret = oidcClientSecret();
  if (secret) {
    body.set("client_secret", secret);
  }

  const tokenResp = await fetch(discovery.token_endpoint, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: body.toString(),
    cache: "no-store",
  });
  if (!tokenResp.ok) {
    return clearTxRedirect(`${origin}/signin?error=oidc_token_failed`);
  }

  const tokenData = (await tokenResp.json()) as {
    access_token?: string;
    id_token?: string;
    expires_in?: number;
  };
  if (typeof tokenData.access_token !== "string") {
    return clearTxRedirect(`${origin}/signin?error=oidc_token_failed`);
  }

  if (typeof tokenData.id_token !== "string") {
    return clearTxRedirect(`${origin}/signin?error=oidc_nonce_failed`);
  }
  const idPayload = decodeJwtPayload(tokenData.id_token);
  if (!idPayload || idPayload.nonce !== tx.nonce) {
    return clearTxRedirect(`${origin}/signin?error=oidc_nonce_failed`);
  }

  const returnTo = strictReturnTo(tx.returnTo);

  if (tx.mode === "reauth") {
    const accessPayload = decodeJwtPayload(tokenData.access_token);
    const sub = accessPayload?.sub ?? idPayload.sub;
    const iss = accessPayload?.iss ?? idPayload.iss;
    if (sub !== tx.expectedSub || iss !== tx.expectedIss) {
      return clearTxRedirect(`${origin}${returnTo}`);
    }
    const res = clearTxRedirect(`${origin}${returnTo}`);
    res.cookies.set(REAUTH_TOKEN_COOKIE, tokenData.access_token, cookieOptions({ maxAge: 120 }));
    return res;
  }

  const maxAge = typeof tokenData.expires_in === "number" ? tokenData.expires_in : 3600;
  const res = clearTxRedirect(`${origin}${returnTo}`);
  res.cookies.set(TOKEN_COOKIE, tokenData.access_token, cookieOptions({ maxAge }));
  res.cookies.set(ID_TOKEN_COOKIE, tokenData.id_token, cookieOptions({ maxAge }));
  return res;
}
