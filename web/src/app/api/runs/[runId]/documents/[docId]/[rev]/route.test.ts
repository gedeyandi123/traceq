import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/auth/session", () => ({
  bearerHeaders: vi.fn(async () => ({ authorization: "Bearer test-token" })),
}));

import { GET, HEAD } from "./route";

const ctx = (runId: string, docId: string, rev: string) => ({
  params: Promise.resolve({ runId, docId, rev }),
});
const req = new Request("http://localhost/api/runs/r/documents/d/0");

describe("GET /api/runs/[runId]/documents/[docId]/[rev]", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each([
    ["../x", "FAT-TP201-M", "0"],
    ["run-1", "a/b", "0"],
    ["run-1", "FAT-TP201-M", "-1"],
    ["run-1", "FAT-TP201-M", "x"],
  ])("returns 400 for invalid path parts (%s, %s, %s)", async (runId, docId, rev) => {
    expect((await GET(req, ctx(runId, docId, rev))).status).toBe(400);
  });

  it("forwards the bearer token and the document headers", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(new Uint8Array([0x25, 0x50]), {
          status: 200,
          headers: {
            "content-type": "application/pdf",
            "content-security-policy": "frame-ancestors 'self'",
          },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const res = await GET(req, ctx("run-1", "FAT-TP201-M", "0"));
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/runs\/run-1\/documents\/FAT-TP201-M\/0$/),
      expect.objectContaining({ method: "GET", headers: { authorization: "Bearer test-token" } }),
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("application/pdf");
    expect(res.headers.get("content-security-policy")).toBe("frame-ancestors 'self'");
  });

  it.each([401, 404])("preserves upstream %i on HEAD", async (status) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status })),
    );
    expect((await HEAD(req, ctx("run-1", "FAT-TP201-M", "0"))).status).toBe(status);
  });

  it("keeps the upstream cache-control and ETag", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(new Uint8Array([1]), {
            status: 200,
            headers: { "content-type": "application/pdf", etag: '"abc"', "cache-control": "private, max-age=300" },
          }),
      ),
    );
    const res = await GET(req, ctx("run-1", "FAT-TP201-M", "0"));
    expect(res.headers.get("cache-control")).toBe("private, max-age=300");
    expect(res.headers.get("etag")).toBe('"abc"');
  });

  it("forwards If-None-Match and returns 304", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(null, {
          status: 304,
          headers: { etag: '"abc"', "cache-control": "private, max-age=300" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const r = new Request("http://localhost/x", { headers: { "if-none-match": '"abc"' } });
    const res = await GET(r, ctx("run-1", "FAT-TP201-M", "0"));
    expect(res.status).toBe(304);
    expect(res.headers.get("etag")).toBe('"abc"');
    expect(fetchMock).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: { authorization: "Bearer test-token", "if-none-match": '"abc"' },
      }),
    );
  });
});
