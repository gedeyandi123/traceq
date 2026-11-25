// Server side only: `next/headers` refuses to load in client components.
import { cookies } from "next/headers";

import { ISSUER_URL } from "@/api/url";
import {
  APPROVING_ROLE,
  DECIDING_ROLE,
  EXECUTING_ROLE,
  WITNESSING_ROLE,
} from "@/decisions/vocabulary";

import {
  cookieOptions,
  decodeJwtPayload,
  ID_TOKEN_COOKIE,
  isOidcMode,
  isTokenExpired,
  OIDC_TX_COOKIE,
  REAUTH_TOKEN_COOKIE,
  TOKEN_COOKIE,
} from "./oidc";

export { TOKEN_COOKIE };

export type Persona = { username: string; name: string; roles: string[] };

/** ``mayDecide``: the token names the deciding role; ``mayApprove``: the approving role;
 * ``mayExecute``: the executing role; ``mayWitness``: the witnessing role. Read for display only:
 * the API checks the role again on every call. */
export type Session = {
  name: string;
  subject: string;
  issuer: string;
  username?: string;
  mayDecide: boolean;
  mayApprove: boolean;
  mayExecute: boolean;
  mayWitness: boolean;
};

/** Server-derived OIDC / re-authentication state passed to client signing dialogs. */
export type SigningAuthState = {
  oidcMode: boolean;
  /** Epoch seconds (`auth_time`) from the single-use `traceq_reauth_token` cookie if present and unexpired. */
  reauthAuthTime: number | null;
};

/** The claim holding the roles, a dotted path for a nested claim; the same setting as the
 * API's `--role-claim`. */
function roleClaimPath(): string {
  return process.env.TRACEQ_ROLE_CLAIM ?? "roles";
}

function roles(payload: unknown): unknown {
  let at: unknown = payload;
  for (const part of roleClaimPath().split(".")) {
    at = typeof at === "object" && at !== null ? (at as Record<string, unknown>)[part] : undefined;
  }
  return at;
}

/** The personas the demo issuer offers, or null when it cannot be reached. */
export async function listPersonas(): Promise<Persona[] | null> {
  try {
    const r = await fetch(`${ISSUER_URL}/demo/personas`, { cache: "no-store" });
    return r.ok ? ((await r.json()) as Persona[]) : null;
  } catch {
    return null;
  }
}

/** Asks the demo issuer for a persona's token (no password: demo identities only) and keeps
 * it in an httpOnly cookie. Returns false when the issuer refuses or is unreachable. */
export async function signIn(username: string): Promise<boolean> {
  try {
    const r = await fetch(`${ISSUER_URL}/demo/token`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username }),
      cache: "no-store",
    });
    if (!r.ok) return false;
    const { access_token, expires_in } = (await r.json()) as {
      access_token: string;
      expires_in: number;
    };
    (await cookies()).set(TOKEN_COOKIE, access_token, cookieOptions({ maxAge: expires_in }));
    return true;
  } catch {
    return false;
  }
}

export async function signOut(): Promise<string | undefined> {
  const store = await cookies();
  const idToken = store.get(ID_TOKEN_COOKIE)?.value;
  store.delete(TOKEN_COOKIE);
  store.delete(ID_TOKEN_COOKIE);
  store.delete(OIDC_TX_COOKIE);
  store.delete(REAUTH_TOKEN_COOKIE);
  return idToken;
}

/** The bearer header for a call to the API, from the cookie. Server side only. */
export async function bearerHeaders(): Promise<Record<string, string>> {
  const token = (await cookies()).get(TOKEN_COOKIE)?.value;
  return token ? { authorization: `Bearer ${token}` } : {};
}

/** Returns a fresh-auth bearer header for signing actions.
 * In OIDC mode: consumes the single-use `traceq_reauth_token` cookie if present, else falls
 * back to `traceq_token` (so recently signed-in users succeed within `max_age` and stale
 * sessions trigger RFC 9470 `reauth_required`).
 * In demo mode: mints a fresh single-use `/demo/token` using `preferred_username`. */
export async function consumeSignatureBearerHeaders(): Promise<Record<string, string>> {
  const store = await cookies();
  if (isOidcMode()) {
    const reauthToken = store.get(REAUTH_TOKEN_COOKIE)?.value;
    if (reauthToken) {
      store.delete(REAUTH_TOKEN_COOKIE);
      return { authorization: `Bearer ${reauthToken}` };
    }
    const token = store.get(TOKEN_COOKIE)?.value;
    return token ? { authorization: `Bearer ${token}` } : {};
  }

  const token = store.get(TOKEN_COOKIE)?.value;
  if (!token) return {};
  try {
    const payload = decodeJwtPayload(token);
    const username =
      payload && typeof payload.preferred_username === "string"
        ? payload.preferred_username
        : null;
    if (!username) return { authorization: `Bearer ${token}` };
    const r = await fetch(`${ISSUER_URL}/demo/token`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username }),
      cache: "no-store",
    });
    if (!r.ok) return { authorization: `Bearer ${token}` };
    const { access_token } = (await r.json()) as { access_token: string };
    return { authorization: `Bearer ${access_token}` };
  } catch {
    return { authorization: `Bearer ${token}` };
  }
}

/** Who is signed in, for display. Checks `exp` when present. The payload is read, not trusted:
 * the API verifies the token on every call. */
export async function currentSession(): Promise<Session | null> {
  const token = (await cookies()).get(TOKEN_COOKIE)?.value;
  if (!token) return null;
  const payload = decodeJwtPayload(token);
  if (!payload || isTokenExpired(payload) || typeof payload.name !== "string") return null;
  const held = roles(payload);
  const has = (role: string) => Array.isArray(held) && held.includes(role);
  return {
    name: payload.name,
    subject: typeof payload.sub === "string" ? payload.sub : "",
    issuer: typeof payload.iss === "string" ? payload.iss : "",
    username:
      typeof payload.preferred_username === "string" ? payload.preferred_username : undefined,
    mayDecide: has(DECIDING_ROLE),
    mayApprove: has(APPROVING_ROLE),
    mayExecute: has(EXECUTING_ROLE),
    mayWitness: has(WITNESSING_ROLE),
  };
}

/** Reads OIDC mode and any valid `traceq_reauth_token` `auth_time` for `ElectronicSignatureDialog`. */
export async function signingAuthState(): Promise<SigningAuthState> {
  const oidcMode = isOidcMode();
  if (!oidcMode) {
    return { oidcMode: false, reauthAuthTime: null };
  }
  const reauthToken = (await cookies()).get(REAUTH_TOKEN_COOKIE)?.value;
  if (!reauthToken) {
    return { oidcMode: true, reauthAuthTime: null };
  }
  const payload = decodeJwtPayload(reauthToken);
  if (!payload || isTokenExpired(payload) || typeof payload.auth_time !== "number") {
    return { oidcMode: true, reauthAuthTime: null };
  }
  return { oidcMode: true, reauthAuthTime: payload.auth_time };
}
