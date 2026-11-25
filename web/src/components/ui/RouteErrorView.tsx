"use client";

import { AlertTriangle } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/ui";

export function RouteErrorView({
  title,
  body,
  retryLabel,
  homeLabel,
  digest,
  onReset,
}: {
  title: string;
  body: string;
  retryLabel: string;
  homeLabel?: string;
  digest?: string;
  onReset: () => void;
}) {
  return (
    <div className="mx-auto my-8 max-w-lg rounded-lg border border-fail-edge bg-surface p-6 shadow-xs">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-fail-soft text-fail">
          <AlertTriangle className="h-5 w-5" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="m-0 text-base font-bold text-ink">{title}</h1>
          <p className="mt-1 mb-0 text-sm text-ink-muted">{body}</p>
          {digest && (
            <p className="mt-2 mb-0 font-mono text-xs text-ink-muted tabular-nums">
              ID: {digest}
            </p>
          )}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Button type="button" variant="primary" onClick={onReset}>
              {retryLabel}
            </Button>
            {homeLabel && (
              <Link
                href="/"
                className="inline-flex min-h-7 items-center rounded border border-border bg-surface px-3 text-xs font-semibold text-ink no-underline transition-colors hover:bg-sunken"
              >
                {homeLabel}
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
