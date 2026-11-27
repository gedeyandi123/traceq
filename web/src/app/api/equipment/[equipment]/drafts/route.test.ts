import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/auth/session", () => ({
  bearerHeaders: vi.fn(async () => ({ authorization: "Bearer test-token" })),
}));

import { POST } from "./route";

const ctx = (equipment: string) => ({ params: Promise.resolve({ equipment }) });

describe("POST /api/equipment/[equipment]/drafts", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("refuses an equipment id that is not a plain id", async () => {
    const res = await POST(new Request("http://localhost/x", { method: "POST" }), ctx("../x"));
    expect(res.status).toBe(400);
  });

  it("refuses a body that is not sent as a PDF", async () => {
    const res = await POST(
      new Request("http://localhost/x", {
        method: "POST",
        headers: { "content-type": "multipart/form-data; boundary=x" },
        body: "x",
      }),
      ctx("TP-201"),
    );
    expect(res.status).toBe(415);
  });

  it("forwards the PDF with the bearer token and returns the status of the API", async () => {
    const fetchMock = vi.fn(async () => new Response('{"id":1}', { status: 202 }));
    vi.stubGlobal("fetch", fetchMock);
    const res = await POST(
      new Request("http://localhost/x", {
        method: "POST",
        headers: { "content-type": "application/pdf" },
        body: "%PDF-1.4",
      }),
      ctx("TP-201"),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/equipment\/TP-201\/drafts$/),
      expect.objectContaining({
        method: "POST",
        headers: { authorization: "Bearer test-token", "content-type": "application/pdf" },
      }),
    );
    expect(res.status).toBe(202);
    expect(res.headers.get("cache-control")).toBe("no-store");
  });

  it.each([402, 403, 413, 422])("preserves upstream %i", async (status) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response('{"detail":"no"}', { status })),
    );
    const res = await POST(
      new Request("http://localhost/x", {
        method: "POST",
        headers: { "content-type": "application/pdf" },
        body: "x",
      }),
      ctx("TP-201"),
    );
    expect(res.status).toBe(status);
  });
});
