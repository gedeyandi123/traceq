import { createHash, randomBytes } from "node:crypto";

import { ISSUER_URL } from "@/api/url";

export const TOKEN_COOKIE = "traceq_token";
export const ID_TOKEN_COOKIE = "traceq_id_token";
export const OIDC_TX_COOKIE = "traceq_oidc_tx";
export const REAUTH_TOKEN_COOKIE = "traceq_reauth_token";

export type CookieOptions = {
  httpOnly: true;
  sameSite: "lax";
  path: "/";
  secure: boolean;
  maxAge?: number;
};

/** Computes cookie attributes for auth cookies (#317).
 * Explicit `"true"` / `"false"` on `TRACEQ_COOKIE_SECURE` wins; otherwise `secure`
 * defaults to `true` only when `TRACEQ_PUBLIC_URL` starts with `https://`. */
export function cookieOptions(options?: { maxAge?: number }): CookieOptions {
  const raw = process.env.TRACEQ_COOKIE_SECURE?.trim().toLowerCase();
  const secure =
    raw === "true"
      ? true
      : raw === "false"
        ? false
        : (process.env.TRACEQ_PUBLIC_URL?.trim().startsWith("https://") ?? false);
  return {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    secure,
    ...(options?.maxAge !== undefined ? { maxAge: options.maxAge } : {}),
  };
}

export function isOidcMode(): boolean {
  return Boolean(process.env.TRACEQ_OIDC_CLIENT_ID?.trim());
}

export function oidcClientId(): string {
  return process.env.TRACEQ_OIDC_CLIENT_ID?.trim() ?? "";
}

export function oidcClientSecret(): string | undefined {
  return process.env.TRACEQ_OIDC_CLIENT_SECRET?.trim() || undefined;
}

export function publicOrigin(fallbackOrigin = "http://127.0.0.1:3000"): string {
  const configured = process.env.TRACEQ_PUBLIC_URL?.trim();
  if (configured) return configured.replace(/\/+$/, "");
  return fallbackOrigin.replace(/\/+$/, "");
}

/** Validates an internal redirect target, rejecting protocol-relative or backslash paths. */
export function strictReturnTo(raw: string | null | undefined): string {
  if (typeof raw !== "string") return "/";
  const trimmed = raw.trim();
  return /^\/(?!\/|\\)/.test(trimmed) ? trimmed : "/";
}

export function pkcePair(): { codeVerifier: string; codeChallenge: string } {
  const codeVerifier = randomBytes(32).toString("base64url");
  const codeChallenge = createHash("sha256").update(codeVerifier).digest("base64url");
  return { codeVerifier, codeChallenge };
}

export function randomToken(): string {
  return randomBytes(24).toString("base64url");
}

export function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const parts = token.split(".");
  if (parts.length !== 3 || !parts[1]) return null;
  try {
    const parsed: unknown = JSON.parse(Buffer.from(parts[1], "base64url").toString("utf-8"));
    return typeof parsed === "object" && parsed !== null
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

export function isTokenExpired(
  payload: Record<string, unknown>,
  nowSeconds = Math.floor(Date.now() / 1000),
): boolean {
  if (typeof payload.exp !== "number") return false;
  return payload.exp <= nowSeconds;
}

/** Detects RFC 9470 `WWW-Authenticate: Bearer error="insufficient_user_authentication", ...`. */
export function parseWwwAuthenticateReauth(headerValue: string | null | undefined): boolean {
  if (!headerValue) return false;
  return /insufficient_user_authentication/i.test(headerValue);
}

export function isReauthRequiredResponse(response: Pick<Response, "status" | "headers">): boolean {
  return (
    response.status === 401 &&
    parseWwwAuthenticateReauth(response.headers.get("www-authenticate"))
  );
}

export type OidcDiscovery = {
  issuer: string;
  authorization_endpoint: string;
  token_endpoint: string;
  end_session_endpoint?: string;
};

export async function discoverOidc(issuerUrl = ISSUER_URL): Promise<OidcDiscovery> {
  const base = issuerUrl.replace(/\/+$/, "");
  const r = await fetch(`${base}/.well-known/openid-configuration`, { cache: "no-store" });
  if (!r.ok) {
    throw new Error(`OIDC discovery failed (${r.status})`);
  }
  return (await r.json()) as OidcDiscovery;
}

export type OidcTx = {
  state: string;
  nonce: string;
  codeVerifier: string;
  returnTo: string;
  mode: "login" | "reauth";
  expectedSub?: string;
  expectedIss?: string;
};
