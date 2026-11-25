import type { NextResponse } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const cookieStore = new Map<string, string>();
const deletedCookies: string[] = [];
const setCookies: Array<{ name: string; value: string; options: Record<string, unknown> }> = [];

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => {
      const value = cookieStore.get(name);
      return value !== undefined ? { value } : undefined;
    },
    set: (name: string, value: string, options: Record<string, unknown> = {}) => {
      cookieStore.set(name, value);
      setCookies.push({ name, value, options });
    },
    delete: (name: string) => {
      cookieStore.delete(name);
      deletedCookies.push(name);
    },
  }),
}));

const redirectCalls: string[] = [];
vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    redirectCalls.push(url);
    throw new Error(`NEXT_REDIRECT:${url}`);
  },
}));

function fakeJwt(payload: Record<string, unknown>): string {
  const header = Buffer.from(JSON.stringify({ alg: "RS256" })).toString("base64url");
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  return `${header}.${body}.sig`;
}

describe("OIDC auth routes, session, and signature bearer headers", () => {
  const originalFetch = globalThis.fetch;
  const originalEnv = { ...process.env };

  beforeEach(() => {
    cookieStore.clear();
    deletedCookies.length = 0;
    setCookies.length = 0;
    redirectCalls.length = 0;
    process.env.TRACEQ_OIDC_CLIENT_ID = "traceq-web";
    process.env.TRACEQ_PUBLIC_URL = "http://127.0.0.1:3000";
    process.env.TRACEQ_ROLE_CLAIM = "realm_access.roles";
    process.env.TRACEQ_COOKIE_SECURE = "false";
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    process.env = { ...originalEnv };
    vi.resetModules();
  });

  it("currentSession() rejects expired exp and exposes username", async () => {
    const { currentSession } = await import("./session");
    const futureExp = Math.floor(Date.now() / 1000) + 600;
    cookieStore.set(
      "traceq_token",
      fakeJwt({
        sub: "u-1",
        iss: "http://127.0.0.1:8080/realms/traceq",
        name: "Ayu Kartika Sari",
        preferred_username: "ayu",
        exp: futureExp,
        realm_access: { roles: ["qualification-decider"] },
      }),
    );

    const session = await currentSession();
    expect(session).toEqual({
      name: "Ayu Kartika Sari",
      subject: "u-1",
      issuer: "http://127.0.0.1:8080/realms/traceq",
      username: "ayu",
      mayDecide: true,
      mayApprove: false,
      mayExecute: false,
      mayWitness: false,
    });

    cookieStore.set(
      "traceq_token",
      fakeJwt({
        sub: "u-1",
        iss: "http://127.0.0.1:8080/realms/traceq",
        name: "Ayu Kartika Sari",
        exp: Math.floor(Date.now() / 1000) - 10,
      }),
    );
    expect(await currentSession()).toBeNull();
  });

  it("consumeSignatureBearerHeaders() consumes single-use traceq_reauth_token in OIDC mode", async () => {
    const { consumeSignatureBearerHeaders } = await import("./session");
    cookieStore.set("traceq_token", "session-tok");
    cookieStore.set("traceq_reauth_token", "fresh-reauth-tok");

    const first = await consumeSignatureBearerHeaders();
    expect(first).toEqual({ authorization: "Bearer fresh-reauth-tok" });
    expect(deletedCookies).toContain("traceq_reauth_token");

    const second = await consumeSignatureBearerHeaders();
    expect(second).toEqual({ authorization: "Bearer session-tok" });
  });

  it("login + callback validates state & nonce and sets session cookies", async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/.well-known/openid-configuration")) {
        return new Response(
          JSON.stringify({
            issuer: "http://127.0.0.1:8080/realms/traceq",
            authorization_endpoint: "http://127.0.0.1:8080/realms/traceq/protocol/openid-connect/auth",
            token_endpoint: "http://127.0.0.1:8080/realms/traceq/protocol/openid-connect/token",
            end_session_endpoint: "http://127.0.0.1:8080/realms/traceq/protocol/openid-connect/logout",
          }),
          { status: 200 },
        );
      }
      if (url.endsWith("/protocol/openid-connect/token")) {
        const tx = JSON.parse(cookieStore.get("traceq_oidc_tx") ?? "{}") as { nonce: string };
        return new Response(
          JSON.stringify({
            access_token: fakeJwt({ sub: "u-1", iss: "http://127.0.0.1:8080/realms/traceq" }),
            id_token: fakeJwt({
              sub: "u-1",
              iss: "http://127.0.0.1:8080/realms/traceq",
              nonce: tx.nonce,
            }),
            expires_in: 3600,
          }),
          { status: 200 },
        );
      }
      throw new Error(`unexpected fetch ${url}`);
    }) as typeof fetch;

    const { GET: loginGet } = await import("@/app/api/auth/login/route");
    const loginResp = (await loginGet(
      new Request("http://127.0.0.1:3000/api/auth/login?next=/runs/r1"),
    )) as NextResponse;
    expect(loginResp.status).toBe(307);
    const setTx = loginResp.cookies.get("traceq_oidc_tx");
    expect(setTx).toBeDefined();
    cookieStore.set("traceq_oidc_tx", setTx!.value);
    const tx = JSON.parse(setTx!.value) as { state: string; nonce: string; returnTo: string };
    expect(tx.returnTo).toBe("/runs/r1");

    const { GET: callbackGet } = await import("@/app/api/auth/callback/route");
    const cbResp = (await callbackGet(
      new Request(`http://127.0.0.1:3000/api/auth/callback?code=c1&state=${tx.state}`),
    )) as NextResponse;
    expect(cbResp.status).toBe(307);
    expect(cbResp.headers.get("location")).toBe("http://127.0.0.1:3000/runs/r1");
    expect(cbResp.cookies.get("traceq_token")?.value).toBeDefined();
    expect(cbResp.cookies.get("traceq_id_token")?.value).toBeDefined();
    expect(cbResp.cookies.get("traceq_oidc_tx")?.value).toBe("");
  });

  it("reauth callback stores traceq_reauth_token without overwriting traceq_token", async () => {
    const futureExp = Math.floor(Date.now() / 1000) + 600;
    const origToken = fakeJwt({
      sub: "u-1",
      iss: "http://127.0.0.1:8080/realms/traceq",
      name: "Ayu Kartika Sari",
      preferred_username: "ayu",
      exp: futureExp,
    });
    cookieStore.set("traceq_token", origToken);

    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/.well-known/openid-configuration")) {
        return new Response(
          JSON.stringify({
            issuer: "http://127.0.0.1:8080/realms/traceq",
            authorization_endpoint: "http://127.0.0.1:8080/realms/traceq/protocol/openid-connect/auth",
            token_endpoint: "http://127.0.0.1:8080/realms/traceq/protocol/openid-connect/token",
          }),
          { status: 200 },
        );
      }
      const tx = JSON.parse(cookieStore.get("traceq_oidc_tx") ?? "{}") as { nonce: string };
      return new Response(
        JSON.stringify({
          access_token: fakeJwt({ sub: "u-1", iss: "http://127.0.0.1:8080/realms/traceq", auth_time: 123 }),
          id_token: fakeJwt({ sub: "u-1", iss: "http://127.0.0.1:8080/realms/traceq", nonce: tx.nonce }),
        }),
        { status: 200 },
      );
    }) as typeof fetch;

    const { GET: reauthGet } = await import("@/app/api/auth/reauth/route");
    const reauthResp = (await reauthGet(
      new Request("http://127.0.0.1:3000/api/auth/reauth?next=/runs/r1/protocol"),
    )) as NextResponse;
    const authRedirect = new URL(reauthResp.headers.get("location")!);
    expect(authRedirect.searchParams.get("prompt")).toBe("login");
    expect(authRedirect.searchParams.get("max_age")).toBe("0");
    expect(authRedirect.searchParams.get("login_hint")).toBe("ayu");

    const setTx = reauthResp.cookies.get("traceq_oidc_tx")!;
    cookieStore.set("traceq_oidc_tx", setTx.value);
    const tx = JSON.parse(setTx.value) as { state: string };

    const { GET: callbackGet } = await import("@/app/api/auth/callback/route");
    const cbResp = (await callbackGet(
      new Request(`http://127.0.0.1:3000/api/auth/callback?code=c2&state=${tx.state}`),
    )) as NextResponse;
    expect(cbResp.headers.get("location")).toBe("http://127.0.0.1:3000/runs/r1/protocol");
    expect(cbResp.cookies.get("traceq_reauth_token")?.value).toBeDefined();
    expect(cbResp.cookies.get("traceq_token")).toBeUndefined();
  });

  it("signOutAction redirects to Keycloak end_session_endpoint with id_token_hint", async () => {
    cookieStore.set("traceq_id_token", "id-tok-123");
    globalThis.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({
          issuer: "http://127.0.0.1:8080/realms/traceq",
          authorization_endpoint: "http://127.0.0.1:8080/realms/traceq/protocol/openid-connect/auth",
          token_endpoint: "http://127.0.0.1:8080/realms/traceq/protocol/openid-connect/token",
          end_session_endpoint: "http://127.0.0.1:8080/realms/traceq/protocol/openid-connect/logout",
        }),
        { status: 200 },
      ),
    ) as typeof fetch;

    const { signOutAction } = await import("./actions");
    await expect(signOutAction()).rejects.toThrow("NEXT_REDIRECT:");
    expect(redirectCalls[0]).toContain("/protocol/openid-connect/logout");
    const logoutUrl = new URL(redirectCalls[0]!);
    expect(logoutUrl.searchParams.get("id_token_hint")).toBe("id-tok-123");
    expect(logoutUrl.searchParams.get("post_logout_redirect_uri")).toBe(
      "http://127.0.0.1:3000/signin",
    );
  });
});
