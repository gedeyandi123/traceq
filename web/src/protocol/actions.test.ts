// The server actions that carry the latest draft revision (spec #375, ticket S4b): submit and
// approve name it; a 409 that says a newer revision arrived is told apart from the other
// conflicts; starting from the draft sends `from_draft`.
import { startProtocol, submitProtocol, approveProtocol, mapDraftStepInline } from "./actions";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  put: vi.fn(),
  redirect: vi.fn((url: string) => {
    throw new Error(`redirect:${url}`);
  }),
}));

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));
vi.mock("@/auth/session", () => ({
  bearerHeaders: async () => ({ authorization: "Bearer t" }),
  consumeSignatureBearerHeaders: async () => ({ authorization: "Bearer s" }),
}));
vi.mock("@/api/client", () => ({ api: { POST: mocks.post, PUT: mocks.put } }));

function form(fields: Record<string, string>): FormData {
  const f = new FormData();
  for (const [k, v] of Object.entries(fields)) f.set(k, v);
  return f;
}

function reply(status: number, body: unknown = {}, code?: string) {
  return {
    response: new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json", ...(code ? { "x-traceq-conflict": code } : {}) },
    }),
  };
}

async function redirectedTo(run: () => Promise<unknown>): Promise<string> {
  await expect(run()).rejects.toThrow(/^redirect:/);
  return String(mocks.redirect.mock.calls.at(-1)?.[0]);
}

beforeEach(() => {
  mocks.post.mockReset();
  mocks.put.mockReset();
  mocks.redirect.mockClear();
});

const PINNED =
  "Protocol 7 is pinned to revision 0 of the Protocol Draft, but revision 1 has arrived: it is not signed. Withdraw it, then start a new Protocol from the latest revision";
const STALE = "a newer revision of the Protocol Draft arrived (revision 2, you read 1): reload before signing";

test("starting from the draft sends from_draft; the plain start does not", async () => {
  mocks.post.mockResolvedValue(reply(201));
  await redirectedTo(() => startProtocol(form({ run_id: "r1", from_draft: "true" })));
  expect(mocks.post.mock.calls[0]?.[1].body).toEqual({ from_draft: true });
  await redirectedTo(() => startProtocol(form({ run_id: "r1" })));
  expect(mocks.post.mock.calls[1]?.[1].body).toEqual({ from_draft: false });
});

test("submit names the latest draft revision the page read", async () => {
  mocks.post.mockResolvedValue(reply(200));
  const url = await redirectedTo(() =>
    submitProtocol(
      form({ run_id: "r1", protocol_id: "7", expected_draft_hash: "h", expected_latest_draft_rev: "1" }),
    ),
  );
  expect(url).toBe("/runs/r1/protocol");
  expect(mocks.post.mock.calls[0]?.[1].body).toEqual({
    expected_draft_hash: "h",
    expected_latest_draft_rev: 1,
  });
});

test("a Protocol not started from the draft sends no revision", async () => {
  mocks.post.mockResolvedValue(reply(200));
  await redirectedTo(() =>
    submitProtocol(form({ run_id: "r1", protocol_id: "7", expected_draft_hash: "h" })),
  );
  expect(mocks.post.mock.calls[0]?.[1].body.expected_latest_draft_rev).toBeNull();
});

test("a stale submit comes back as stale_draft, any other conflict as conflict", async () => {
  mocks.post.mockResolvedValue(reply(409, { detail: STALE }, "stale_draft"));
  const fields = { run_id: "r1", protocol_id: "7", expected_draft_hash: "h", expected_latest_draft_rev: "1" };
  expect(await redirectedTo(() => submitProtocol(form(fields)))).toBe(
    "/runs/r1/protocol?protocolError=stale_draft",
  );
  mocks.post.mockResolvedValue(reply(409, { detail: STALE }));
  expect(await redirectedTo(() => submitProtocol(form(fields)))).toBe(
    "/runs/r1/protocol?protocolError=conflict",
  );
  mocks.post.mockResolvedValue(reply(409, { detail: "the draft changed since you read it" }));
  expect(await redirectedTo(() => submitProtocol(form(fields)))).toBe(
    "/runs/r1/protocol?protocolError=conflict",
  );
});

test("a Protocol pinned to an older revision comes back as pinned_behind on submit and approve", async () => {
  mocks.post.mockResolvedValue(reply(409, { detail: PINNED }, "pinned_behind"));
  const submit = { run_id: "r1", protocol_id: "7", expected_draft_hash: "h", expected_latest_draft_rev: "1" };
  expect(await redirectedTo(() => submitProtocol(form(submit)))).toBe(
    "/runs/r1/protocol?protocolError=pinned_behind",
  );
  const approve = { run_id: "r1", protocol_id: "7", submission_event_id: "12", hash: "h", expected_latest_draft_rev: "1" };
  expect(await redirectedTo(() => approveProtocol(form(approve)))).toBe(
    "/runs/r1/protocol?protocolError=pinned_behind",
  );
});

test("approve names the revision and reports a stale one", async () => {
  mocks.post.mockResolvedValue(reply(409, { detail: STALE }, "stale_draft"));
  const url = await redirectedTo(() =>
    approveProtocol(
      form({
        run_id: "r1",
        protocol_id: "7",
        submission_event_id: "12",
        hash: "h",
        expected_latest_draft_rev: "1",
      }),
    ),
  );
  expect(url).toBe("/runs/r1/protocol?protocolError=stale_draft");
  expect(mocks.post.mock.calls[0]?.[1].body).toEqual({
    submission_event_id: 12,
    hash: "h",
    expected_latest_draft_rev: 1,
  });
});

test("mapping a draft step sends the one requirement chosen, and none chosen is not sent", async () => {
  mocks.put.mockResolvedValue(reply(200));
  const ok = await mapDraftStepInline(
    { ok: false },
    form({ protocol_id: "7", step: "OQ-40", requirement: "URS-TP201-030" }),
  );
  expect(ok.ok).toBe(true);
  expect(mocks.put.mock.calls[0]?.[1]).toMatchObject({
    params: { path: { protocol_id: 7, step: "OQ-40" } },
    body: { requirement: "URS-TP201-030" },
  });
  const none = await mapDraftStepInline({ ok: false }, form({ protocol_id: "7", step: "OQ-40" }));
  expect(none).toEqual({ ok: false, error: "invalid" });
  expect(mocks.put).toHaveBeenCalledTimes(1);
});
