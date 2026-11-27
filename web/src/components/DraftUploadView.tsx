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
const TONES: Record<UploadJobView["status"], string> = {
  queued: "border-info-edge bg-info-soft text-info",
  running: "border-warn-edge bg-warn-soft text-warn",
  succeeded: "border-pass-edge bg-pass-soft text-pass",
  failed: "border-fail-edge bg-fail-soft text-fail",
};

type Problem = "notPdf" | "tooLarge" | "budget" | "forbidden" | "unauthorized" | "failed";

function problemOf(status: number): Problem {
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
  const [problem, setProblem] = useState<{ kind: Problem; detail?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const pending = jobs.some((j) => j.status === "queued" || j.status === "running");
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(async () => {
      const open = jobs.filter((j) => j.status === "queued" || j.status === "running");
      const next = await Promise.all(
        open.map(async (j) => {
          try {
            const res = await fetch(`/api/uploads/${j.id}`, { cache: "no-store" });
            return res.ok ? ((await res.json()) as UploadJobView) : j;
          } catch {
            return j;
          }
        }),
      );
      setJobs((all) => all.map((j) => next.find((n) => n.id === j.id) ?? j));
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [pending, jobs]);

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
        if (input.current) input.current.value = "";
      } else {
        const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
        setProblem({
          kind: problemOf(res.status),
          detail: typeof body?.detail === "string" ? body.detail : undefined,
        });
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

      <div aria-live="polite">
        {problem !== null && (
          <Alert tone="fail" role="alert" title={t(`problem.${problem.kind}`)}>
            {problem.detail ?? ""}
          </Alert>
        )}
      </div>

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
            <tbody className="divide-y divide-border">
              {jobs.map((j) => (
                <tr key={j.id}>
                  <th scope="row" className="px-4 py-3 font-bold text-ink tabular-nums">
                    Rev {j.rev}
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
                    {j.status === "failed" && <span className="text-fail">{j.message}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
