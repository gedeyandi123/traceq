"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export function CopyHashButton({
  value,
  copyLabel,
  copiedLabel,
  failedLabel,
  className,
}: {
  value: string;
  copyLabel: string;
  copiedLabel: string;
  failedLabel?: string;
  className?: string;
}) {
  const [status, setStatus] = useState<"idle" | "copied" | "failed">("idle");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
      }
    };
  }, []);

  const handleCopy = async () => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    try {
      await navigator.clipboard.writeText(value);
      setStatus("copied");
    } catch {
      setStatus("failed");
    }
    timerRef.current = setTimeout(() => {
      setStatus("idle");
      timerRef.current = null;
    }, 2000);
  };

  const label =
    status === "copied"
      ? copiedLabel
      : status === "failed"
        ? (failedLabel ?? copyLabel)
        : copyLabel;

  return (
    <>
      <button
        type="button"
        onClick={() => void handleCopy()}
        className={`inline-flex h-7 cursor-pointer items-center gap-1.5 rounded border border-border bg-surface px-2.5 text-xs font-medium text-ink transition-colors hover:bg-sunken ${className ?? ""}`.trim()}
      >
        {status === "copied" ? (
          <Check className="h-3.5 w-3.5 text-pass" aria-hidden="true" />
        ) : (
          <Copy className="h-3.5 w-3.5 text-ink-muted" aria-hidden="true" />
        )}
        <span>{label}</span>
      </button>
      <span className="sr-only" aria-live="polite">
        {status === "copied" ? copiedLabel : status === "failed" ? (failedLabel ?? "") : ""}
      </span>
    </>
  );
}
