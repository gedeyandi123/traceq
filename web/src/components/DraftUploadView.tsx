"use client";

import { Upload } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";

import type { DraftUploads, UploadJobView } from "@/api/client";
import { Alert } from "@/components/ui/Alert";
import { FIELD_BASE_CLASS } from "@/components/ui/FormControls";
import { Button, EmptyState } from "@/components/ui/ui";

const POLL_MS = 2000;
const MAX_POLL_MS = 30_000;
const BACKOFF = 1.5;
/** The server's upload job deadline (1800 s): past it no news will come. */
const POLL_DEADLINE_MS = 1_800_000;
const MAX_LOST_TICKS = 5;
const TONES: Record<UploadJobView["status"], string> = {
  queued: "border-info-edge bg-info-soft text-info",
  running: "border-warn-edge bg-warn-soft text-warn",
  succeeded: "border-pass-edge bg-pass-soft text-pass",
  failed: "border-fail-edge bg-fail-soft text-fail",
};

type Problem =
  | "notPdf"
  | "tooLarge"
  | "budget"
  | "forbidden"
  | "unauthorized"
  | "conflict"
  | "failed";
/** Why automatic updates stopped; shown under the table, apart from upload errors. */
type PollProblem = "unauthorized" | "pollLost" | "pollTimeout";

/** The page shows only these codes, never the API `detail`: it is English and can name
 * server files. */
function problemOf(status: number): Problem {
  if (status === 409) return "conflict";
  if (status === 413) return "tooLarge";
  if (status === 402) return "budget";
  if (status === 403) return "forbidden";
  if (status === 401) return "unauthorized";
  if (status === 415 || status === 422) return "notPdf";
  return "failed";
}

function megabytes(bytes: number): string {
  return String(Math.round(bytes / (1024 * 1024)));
}

/** Upload of a Protocol Draft PDF and the progress of the runs it starts. Mode Cloud sends
 * text to an external provider and only synthetic data is allowed (ADR 0001): the notice is
 * always visible, before the file is chosen. */
export function DraftUploadView({ initial }: { initial: DraftUploads }) {
  const t = useTranslations("upload");
  const [jobs, setJobs] = useState<UploadJobView[]>(initial.jobs);
  const [problem, setProblem] = useState<{ kind: Problem } | null>(null);
  const [busy, setBusy] = useState(false);
  const [pollProblem, setPollProblem] = useState<PollProblem | null>(null);
  const [stopped, setStopped] = useState(false);
  // Bumped by every accepted upload so the polling effect restarts with a fresh delay/deadline.
  const [pollEpoch, setPollEpoch] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const jobsRef = useRef(jobs);
  useEffect(() => {
    jobsRef.current = jobs;
  }, [jobs]);

  const pending = jobs.some((j) => j.status === "queued" || j.status === "running");
  // One timer chain for as long as something is open: it reads the latest jobs from a ref,
  // skips a tick while the tab is hidden, backs off from 2 s to 30 s, gives up when a job
  // outlives the server's deadline, and stops for good when the session is gone (401).
  useEffect(() => {
    if (!pending || stopped) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = POLL_MS;
    let lostTicks = 0;
    const startedAt = Date.now();
    const stop = (kind: PollProblem) => {
      cancelled = true;
      setStopped(true);
      setPollProblem(kind);
    };
    const tick = async () => {
      if (cancelled) return;
      if (Date.now() - startedAt >= POLL_DEADLINE_MS) {
        stop("pollTimeout");
        return;
      }
      if (document.visibilityState !== "hidden") {
        const open = jobsRef.current.filter((j) => j.status === "queued" || j.status === "running");
        const next = await Promise.all(
          open.map(async (j) => {
            try {
              const res = await fetch(`/api/uploads/${j.id}`, { cache: "no-store" });
              if (res.status === 401) return "signedOut" as const;
              return res.ok ? ((await res.json()) as UploadJobView) : ("lost" as const);
            } catch {
              return "lost" as const;
            }
          }),
        );
        if (cancelled) return;
        if (next.includes("signedOut")) {
          stop("unauthorized");
          return;
        }
        // A status that keeps failing (404, 500, no network) is not polled forever.
        lostTicks = next.every((n) => n === "lost") ? lostTicks + 1 : 0;
        if (lostTicks >= MAX_LOST_TICKS) {
          stop("pollLost");
          return;
        }
        const fresh = next.filter((n): n is UploadJobView => typeof n === "object");
        // Re-render only when a status or run changed (the only columns that depend on a poll;
        // widen this check if another polled field is ever shown).
        setJobs((all) => {
          let changed = false;
          const merged = all.map((j) => {
            const n = fresh.find((f) => f.id === j.id);
            if (n !== undefined && (n.status !== j.status || n.run_id !== j.run_id)) {
              changed = true;
              return n;
            }
            return j;
          });
          return changed ? merged : all;
        });
        delay = Math.min(delay * BACKOFF, MAX_POLL_MS);
      }
      if (!cancelled) timer = setTimeout(tick, delay);
    };
    timer = setTimeout(tick, delay);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [pending, stopped, pollEpoch]);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const file = input.current?.files?.[0];
    if (file === undefined) {
      setProblem({ kind: "notPdf" });
      return;
    }
    if (file.size > initial.max_bytes) {
      setProblem({ kind: "tooLarge" });
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      const res = await fetch(`/api/equipment/${encodeURIComponent(initial.equipment)}/drafts`, {
        method: "POST",
        headers: { "content-type": "application/pdf" },
        body: file,
      });
      if (res.status === 202) {
        const job = (await res.json()) as UploadJobView;
        setJobs((all) => [job, ...all]);
        setStopped(false);
        setPollProblem(null);
        setPollEpoch((n) => n + 1);
        if (input.current) input.current.value = "";
      } else {
        if (res.status === 401) setStopped(true);
        setProblem({ kind: problemOf(res.status) });
      }
    } catch {
      setProblem({ kind: "failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <Alert tone="warn" title={t("cloudTitle")}>
        {t("cloudNotice")}
      </Alert>

      <form
        onSubmit={submit}
        className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-surface p-4 shadow-xs"
      >
        <div className="flex min-w-0 flex-col gap-1">
          <label htmlFor="draft-file" className="text-xs font-semibold text-ink">
            {t("fileLabel")}
          </label>
          <input
            id="draft-file"
            ref={input}
            type="file"
            accept="application/pdf,.pdf"
            className={FIELD_BASE_CLASS}
          />
          <p className="m-0 text-[11px] text-ink-muted">
            {t("limits", {
              mb: megabytes(initial.max_bytes),
              pages: initial.max_pages,
            })}
          </p>
        </div>
        <Button variant="primary" type="submit" disabled={busy}>
          <Upload className="h-3.5 w-3.5" aria-hidden="true" />
          {busy ? t("sending") : t("send")}
        </Button>
      </form>

      <p className="m-0 text-[11px] text-ink-muted">{t("devOnly")}</p>

      {problem !== null && (
        <Alert tone="fail" role="alert" title={t(`problem.${problem.kind}`)}>
          {null}
        </Alert>
      )}

      {jobs.length === 0 ? (
        <EmptyState title={t("emptyTitle")}>{t("empty")}</EmptyState>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-surface shadow-xs">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-border bg-sunken/70 text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
                <th scope="col" className="px-4 py-2.5">
                  {t("colRev")}
                </th>
                <th scope="col" className="px-4 py-2.5">
                  {t("colFile")}
                </th>
                <th scope="col" className="px-4 py-2.5">
                  {t("colStatus")}
                </th>
                <th scope="col" className="px-4 py-2.5">
                  {t("colResult")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border" aria-live="polite">
              {jobs.map((j) => (
                <tr key={j.id}>
                  <th scope="row" className="px-4 py-3 font-bold text-ink tabular-nums">
                    {t("revLabel", { rev: j.rev })}
                  </th>
                  <td className="px-4 py-3 text-xs text-ink-muted">
                    <span className="font-mono">{j.sha256.slice(0, 12)}</span>
                    <span className="ml-2 tabular-nums">{t("pages", { count: j.pages })}</span>
                    {j.reserved_usd === 0 && (
                      <span className="ml-2">{t("replayNote")}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    <span
                      className={`inline-flex rounded-full border px-2 py-0.5 font-semibold ${TONES[j.status]}`}
                    >
                      {t(`status.${j.status}`)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {j.status === "succeeded" && j.run_id !== null && (
                      <span className="flex flex-wrap gap-3">
                        <Link href={`/runs/${encodeURIComponent(j.run_id)}/draft`}>
                          {t("openDraft")}
                        </Link>
                        <Link href={`/runs/${encodeURIComponent(j.run_id)}/rounds`}>
                          {t("openRounds")}
                        </Link>
                      </span>
                    )}
                    {j.status === "failed" && <span className="text-fail">{t("jobFailed")}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pollProblem !== null && (
        <Alert
          tone="fail"
          role="alert"
          title={t(`problem.${pollProblem}`, { minutes: POLL_DEADLINE_MS / 60_000 })}
        >
          {null}
        </Alert>
      )}
    </div>
  );
}
