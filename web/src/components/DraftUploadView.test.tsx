import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, expect, test, vi } from "vitest";

import type { DraftUploads, UploadJobView } from "@/api/client";

import messages from "../../messages/id.json";
import { DraftUploadView } from "./DraftUploadView";

const job = (over: Partial<UploadJobView>): UploadJobView => ({
  id: 1,
  equipment: "TP-201",
  rev: 0,
  sha256: "a".repeat(64),
  size_bytes: 1000,
  pages: 2,
  status: "queued",
  reserved_usd: 0.004,
  cost_usd: null,
  run_id: null,
  message: null,
  at: "2026-11-27T09:00:00Z",
  started_at: null,
  finished_at: null,
  name: "Ayu",
  ...over,
});

const initial = (jobs: UploadJobView[] = []): DraftUploads => ({
  equipment: "TP-201",
  max_bytes: 1000,
  max_pages: 40,
  live_budget_usd: 0,
  live_remaining_usd: 0,
  cloud_notice: "x",
  jobs,
});

function view(data: DraftUploads) {
  return render(
    <NextIntlClientProvider locale="id" messages={messages}>
      <DraftUploadView initial={data} />
    </NextIntlClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("states before any file is chosen that Mode Cloud sends text out and only synthetic data is allowed", () => {
  view(initial());
  const note = screen.getByText(/Mode Cloud mengirim teks dokumen ke penyedia model eksternal/);
  expect(note.textContent).toMatch(/Hanya data sintetis/);
});

test("a file over the size cap is refused in the browser without a request", () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  view(initial());
  const file = new File([new Uint8Array(2000)], "d.pdf", { type: "application/pdf" });
  fireEvent.change(screen.getByLabelText("Berkas PDF"), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: /Unggah/ }));
  expect(screen.getByRole("alert").textContent).toMatch(/melebihi batas ukuran/);
  expect(fetchMock).not.toHaveBeenCalled();
});

test("an upload is sent as a PDF body and its job appears, then a refusal is shown", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(job({ rev: 3, id: 9 })), { status: 202 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "no" }), { status: 402 }));
  vi.stubGlobal("fetch", fetchMock);
  view(initial());
  const file = new File([new Uint8Array(10)], "d.pdf", { type: "application/pdf" });
  const send = () => {
    fireEvent.change(screen.getByLabelText("Berkas PDF"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: /Unggah/ }));
  };
  send();
  await screen.findByText("Revisi 3");
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/equipment/TP-201/drafts",
    expect.objectContaining({
      method: "POST",
      body: file,
      headers: { "content-type": "application/pdf" },
    }),
  );
  send();
  await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/Anggaran/));
});

test("a succeeded job links to its draft and rounds; a failed one shows why", () => {
  view(
    initial([
      job({ id: 2, rev: 1, status: "succeeded", run_id: "r-1" }),
      job({ id: 1, rev: 0, status: "failed", message: "tidak ada rekaman" }),
    ]),
  );
  expect(screen.getByRole("link", { name: "Buka draf" }).getAttribute("href")).toBe(
    "/runs/r-1/draft",
  );
  // The server's English text, which can name server paths, is never shown to the uploader.
  expect(screen.queryByText("tidak ada rekaman")).toBeNull();
  expect(screen.getByText(/Pra-tinjauan gagal/)).toBeTruthy();
});

test("a refusal shows plain Indonesian, never the API detail or a server path", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "no recording at /srv/recordings/x.json" }), {
        status: 409,
      }),
    ),
  );
  view(initial());
  const file = new File([new Uint8Array(10)], "d.pdf", { type: "application/pdf" });
  fireEvent.change(screen.getByLabelText("Berkas PDF"), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: /Unggah/ }));
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).not.toMatch(/recording|srv/);
  expect(alert.textContent).toMatch(/revisi/i);
});

test("job status is a polite live region and the error alert is not inside one", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 413 })));
  view(initial([job({})]));
  expect(screen.getByRole("table").querySelector("[aria-live=polite]")).not.toBeNull();
  const file = new File([new Uint8Array(10)], "d.pdf", { type: "application/pdf" });
  fireEvent.change(screen.getByLabelText("Berkas PDF"), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: /Unggah/ }));
  const alert = await screen.findByRole("alert");
  expect(alert.closest("[aria-live]")).toBeNull();
});

test("polling stops and says the session is invalid on 401", async () => {
  vi.useFakeTimers();
  try {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    view(initial([job({})]));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("alert").textContent).toMatch(/Sesi tidak valid/);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  } finally {
    vi.useRealTimers();
  }
});

test("polling does not fetch while the tab is hidden and resumes when it shows", async () => {
  vi.useFakeTimers();
  try {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(job({})), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const state = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    view(initial([job({})]));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6100);
    });
    expect(fetchMock).not.toHaveBeenCalled();
    state.mockReturnValue("visible");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    expect(fetchMock).toHaveBeenCalled();
    state.mockRestore();
  } finally {
    vi.useRealTimers();
  }
});

test("the upload screen labels figures as dev only", () => {
  view(initial());
  expect(screen.getByText(/hanya data pengembangan/i)).toBeTruthy();
});
