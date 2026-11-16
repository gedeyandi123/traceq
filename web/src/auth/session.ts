// Server side only: `next/headers` refuses to load in client components.
import { cookies } from "next/headers";

import { ISSUER_URL } from "@/api/url";

/** The httpOnly cookie holding the demo token. Only the Next.js server reads it. */
export const TOKEN_COOKIE = "traceq_token";

export type Persona = { username: string; name: string; roles: string[] };

export type Session = { name: string };

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
    (await cookies()).set(TOKEN_COOKIE, access_token, {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      maxAge: expires_in,
    });
    return true;
  } catch {
    return false;
  }
}

export async function signOut(): Promise<void> {
  (await cookies()).delete(TOKEN_COOKIE);
}

/** The bearer header for a call to the API, from the cookie. Server side only. */
export async function bearerHeaders(): Promise<Record<string, string>> {
  const token = (await cookies()).get(TOKEN_COOKIE)?.value;
  return token ? { authorization: `Bearer ${token}` } : {};
}

/** Who is signed in, for display. The payload is read, not trusted: the API verifies the
 * token on every call. */
export async function currentSession(): Promise<Session | null> {
  const token = (await cookies()).get(TOKEN_COOKIE)?.value;
  if (!token) return null;
  try {
    const payload = JSON.parse(Buffer.from(token.split(".")[1] ?? "", "base64url").toString());
    return typeof payload.name === "string" ? { name: payload.name } : null;
  } catch {
    return null;
  }
}
