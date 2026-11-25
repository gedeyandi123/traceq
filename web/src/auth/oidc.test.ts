import { createHash } from "node:crypto";

import { afterEach, describe, expect, it } from "vitest";

import {
  cookieOptions,
  isReauthRequiredResponse,
  isTokenExpired,
  parseWwwAuthenticateReauth,
  pkcePair,
  publicOrigin,
  strictReturnTo,
} from "./oidc";

const ORIGINAL_SECURE = process.env.TRACEQ_COOKIE_SECURE;
const ORIGINAL_PUBLIC = process.env.TRACEQ_PUBLIC_URL;

afterEach(() => {
  if (ORIGINAL_SECURE === undefined) delete process.env.TRACEQ_COOKIE_SECURE;
  else process.env.TRACEQ_COOKIE_SECURE = ORIGINAL_SECURE;

  if (ORIGINAL_PUBLIC === undefined) delete process.env.TRACEQ_PUBLIC_URL;
  else process.env.TRACEQ_PUBLIC_URL = ORIGINAL_PUBLIC;
});

describe("cookieOptions (#317)", () => {
  it("honors explicit TRACEQ_COOKIE_SECURE='true' and 'false'", () => {
    process.env.TRACEQ_PUBLIC_URL = "http://127.0.0.1:3000";
    process.env.TRACEQ_COOKIE_SECURE = "true";
    expect(cookieOptions({ maxAge: 60 })).toEqual({
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      secure: true,
      maxAge: 60,
    });

    process.env.TRACEQ_PUBLIC_URL = "https://traceq.example.com";
    process.env.TRACEQ_COOKIE_SECURE = "false";
    expect(cookieOptions().secure).toBe(false);
  });

  it("falls back to TRACEQ_PUBLIC_URL https:// prefix when TRACEQ_COOKIE_SECURE is unset", () => {
    delete process.env.TRACEQ_COOKIE_SECURE;
    process.env.TRACEQ_PUBLIC_URL = "https://traceq.example.com";
    expect(cookieOptions().secure).toBe(true);

    process.env.TRACEQ_PUBLIC_URL = "http://127.0.0.1:3000";
    expect(cookieOptions().secure).toBe(false);

    delete process.env.TRACEQ_PUBLIC_URL;
    expect(cookieOptions().secure).toBe(false);
  });
});

describe("strictReturnTo & publicOrigin", () => {
  it("allows single-slash internal paths and rejects open redirects", () => {
    expect(strictReturnTo("/runs/r1/protocol")).toBe("/runs/r1/protocol");
    expect(strictReturnTo("/")).toBe("/");
    expect(strictReturnTo("//evil.com")).toBe("/");
    expect(strictReturnTo("/\\evil.com")).toBe("/");
    expect(strictReturnTo("https://evil.com")).toBe("/");
    expect(strictReturnTo("")).toBe("/");
    expect(strictReturnTo(undefined)).toBe("/");
  });

  it("strips trailing slashes from TRACEQ_PUBLIC_URL", () => {
    process.env.TRACEQ_PUBLIC_URL = "https://traceq.example.com/";
    expect(publicOrigin("http://127.0.0.1:3000")).toBe("https://traceq.example.com");
  });
});

describe("pkcePair, isTokenExpired, and RFC 9470 detection", () => {
  it("generates S256 PKCE verifier/challenge pairs", () => {
    const { codeVerifier, codeChallenge } = pkcePair();
    const expected = createHash("sha256").update(codeVerifier).digest("base64url");
    expect(codeChallenge).toBe(expected);
  });

  it("checks exp claim against current epoch seconds", () => {
    expect(isTokenExpired({ exp: 1000 }, 1000)).toBe(true);
    expect(isTokenExpired({ exp: 999 }, 1000)).toBe(true);
    expect(isTokenExpired({ exp: 1001 }, 1000)).toBe(false);
    expect(isTokenExpired({}, 1000)).toBe(false);
  });

  it("distinguishes RFC 9470 insufficient_user_authentication from plain 401", () => {
    expect(
      parseWwwAuthenticateReauth('Bearer error="insufficient_user_authentication", max_age=60'),
    ).toBe(true);
    expect(parseWwwAuthenticateReauth("Bearer")).toBe(false);

    const reauthResp = new Response(null, {
      status: 401,
      headers: { "www-authenticate": 'Bearer error="insufficient_user_authentication", max_age=60' },
    });
    const plain401 = new Response(null, {
      status: 401,
      headers: { "www-authenticate": "Bearer" },
    });
    expect(isReauthRequiredResponse(reauthResp)).toBe(true);
    expect(isReauthRequiredResponse(plain401)).toBe(false);
  });
});
