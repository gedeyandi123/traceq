import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/auth/session", () => ({
  bearerHeaders: vi.fn(async () => ({ authorization: "Bearer test-token" })),
}));

import { GET } from "./route";

describe("GET /api/rounds/[roundId]/exports/[exportId]/pdf", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each([
    ["0", "1"],
    ["-2", "1"],
    ["abc", "1"],
    ["1", "0"],
    ["1", "1.5"],
    ["1", "xyz"],
  ])("returns 400 for invalid path params (%s, %s)", async (roundId, exportId) => {
    const res = await GET(new Request("http://localhost/api/rounds/x/exports/y/pdf"), {
      params: Promise.resolve({ roundId, exportId }),
    });
    expect(res.status).toBe(400);
  });

  it("forwards bearer headers and streams PDF with no-store cache headers", async () => {
    const fetchMock = vi.fn(async () => {
      return new Response(new Uint8Array([0x25, 0x50, 0x44, 0x46]), {
        status: 200,
        headers: {
          "content-type": "application/pdf",
          "content-disposition": 'attachment; filename="pre-review-r1.pdf"',
        },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const res = await GET(new Request("http://localhost/api/rounds/12/exports/34/pdf"), {
      params: Promise.resolve({ roundId: "12", exportId: "34" }),
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/rounds\/12\/exports\/34\/pdf$/),
      expect.objectContaining({
        method: "GET",
        headers: { authorization: "Bearer test-token" },
        cache: "no-store",
      }),
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("application/pdf");
    expect(res.headers.get("content-disposition")).toBe('attachment; filename="pre-review-r1.pdf"');
    expect(res.headers.get("cache-control")).toBe("no-store");
  });

  it.each([401, 403, 404])("preserves upstream %i status on failure", async (status) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response('{"detail":"nope"}', { status })),
    );

    const res = await GET(new Request("http://localhost/api/rounds/5/exports/6/pdf"), {
      params: Promise.resolve({ roundId: "5", exportId: "6" }),
    });

    expect(res.status).toBe(status);
    expect(res.headers.get("cache-control")).toBe("no-store");
  });
});
