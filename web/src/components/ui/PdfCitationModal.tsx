"use client";

import { AlertCircle, ExternalLink, FileSpreadsheet, FileText, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { documentHref, type Cite } from "@/api/client";
import { Modal } from "./Modal";

type ProbeState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "pdf"; contentType: string }
  | { status: "nonPdf"; contentType: string }
  | { status: "error"; message: string };

export function PdfCitationModal({
  open,
  onOpenChange,
  runId,
  cite,
  label,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  runId: string;
  cite: Cite;
  label?: string;
}) {
  const tUi = useTranslations("ui");
  const tCommon = useTranslations("common");
  const [probe, setProbe] = useState<{ url: string; state: ProbeState } | null>(null);
  const [isDesktop, setIsDesktop] = useState(true);

  const href = documentHref(runId, cite);
  const headUrl = href.split("#")[0] ?? href;
  const displayLabel = label ?? tCommon("cite", { doc: cite.doc, rev: cite.rev, page: cite.page });

  useEffect(() => {
    if (typeof window === "undefined") return;
    const check = () => setIsDesktop(window.innerWidth >= 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;

    fetch(headUrl, { method: "HEAD" })
      .then((res) => {
        if (cancelled) return;
        if (!res.ok) {
          setProbe({
            url: headUrl,
            state: {
              status: "error",
              message:
                res.status === 404
                  ? tUi("documentNotFound", { doc: cite.doc, rev: cite.rev })
                  : tUi("documentLoadFailed", { doc: cite.doc, status: res.status }),
            },
          });
          return;
        }
        const ct = (res.headers.get("content-type") ?? "").toLowerCase();
        if (ct.includes("application/pdf")) {
          setProbe({ url: headUrl, state: { status: "pdf", contentType: ct } });
        } else {
          setProbe({
            url: headUrl,
            state: { status: "nonPdf", contentType: ct || "application/octet-stream" },
          });
        }
      })
      .catch(() => {
        if (cancelled) return;
        setProbe({
          url: headUrl,
          state: {
            status: "error",
            message: tUi("documentServerError", { doc: cite.doc, rev: cite.rev }),
          },
        });
      });

    return () => {
      cancelled = true;
    };
  }, [open, headUrl, cite.doc, cite.rev, tUi]);

  const currentProbe: ProbeState = !open
    ? { status: "idle" }
    : probe?.url === headUrl
      ? probe.state
      : { status: "loading" };

  const showIframe = currentProbe.status === "pdf" && isDesktop;
  const showFallback =
    currentProbe.status === "nonPdf" || (currentProbe.status === "pdf" && !isDesktop);
  const isSpreadsheet =
    currentProbe.status === "nonPdf" &&
    (currentProbe.contentType.includes("spreadsheetml") ||
      currentProbe.contentType.includes("ms-excel") ||
      cite.doc.toLowerCase().endsWith(".xlsx"));
  const fileTypeLabel = isSpreadsheet
    ? tUi("excelFileType")
    : currentProbe.status === "nonPdf"
      ? currentProbe.contentType
      : "";

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      size="wide"
      title={tUi("citationTitle", { label: displayLabel })}
      description={cite.quote ? `${tUi("verbatimQuote")}: "${cite.quote}"` : undefined}
      headerActions={
        showIframe ? (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-accent no-underline hover:bg-accent-soft"
          >
            <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            <span>{tUi("openInNewTab")}</span>
          </a>
        ) : undefined
      }
    >
      {currentProbe.status === "loading" && (
        <div className="flex h-full min-h-[240px] flex-col items-center justify-center gap-2 text-sm text-ink-muted">
          <Loader2 className="h-6 w-6 animate-spin text-accent" aria-hidden="true" />
          <span>{tUi("checkingDocument", { doc: cite.doc })}</span>
        </div>
      )}

      {currentProbe.status === "error" && (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-md border border-fail-edge bg-fail-soft p-4 text-sm text-fail"
        >
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
          <div>
            <div className="font-semibold">{tUi("documentUnavailable")}</div>
            <div className="mt-1">{currentProbe.message}</div>
          </div>
        </div>
      )}

      {showIframe && (
        <iframe
          key={`${cite.doc}-${cite.rev}-${cite.page}`}
          src={href}
          title={displayLabel}
          className="h-full min-h-[65vh] w-full rounded-md border border-border bg-sunken"
        />
      )}

      {showFallback && (
        <div className="flex flex-col items-start gap-3 rounded-md border border-border bg-sunken p-5 text-sm text-ink">
          <div className="flex items-center gap-2 font-semibold">
            {isSpreadsheet ? (
              <FileSpreadsheet className="h-5 w-5 text-accent" aria-hidden="true" />
            ) : (
              <FileText className="h-5 w-5 text-accent" aria-hidden="true" />
            )}
            <span>{displayLabel}</span>
          </div>
          <p className="m-0 text-xs text-ink-muted">
            {currentProbe.status === "nonPdf" ? tUi("nonPdfNotice") : tUi("mobilePdfNotice")}
          </p>
          <div className="text-xs text-ink-muted">
            {tUi("fileType")}: <span className="font-medium text-ink">{fileTypeLabel}</span>
          </div>
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-xs font-semibold text-on-accent no-underline hover:bg-accent-hover"
          >
            <ExternalLink className="h-4 w-4" aria-hidden="true" />
            <span>{isSpreadsheet ? tUi("downloadSpreadsheet") : tUi("openOrDownload")}</span>
          </a>
        </div>
      )}
    </Modal>
  );
}

export function PdfCitationButton({
  runId,
  cite,
  label,
  compact = false,
}: {
  runId: string;
  cite: Cite;
  label?: string;
  compact?: boolean;
}) {
  const tCommon = useTranslations("common");
  const [open, setOpen] = useState(false);
  const displayLabel = label ?? tCommon("cite", { doc: cite.doc, rev: cite.rev, page: cite.page });

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title={cite.quote}
        className={`inline-flex cursor-pointer items-center gap-1.5 rounded border border-border bg-surface font-medium text-accent transition-colors hover:border-accent hover:bg-accent-soft ${
          compact ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-xs"
        }`}
      >
        <FileText className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span className="tabular-nums">{displayLabel}</span>
      </button>

      <PdfCitationModal
        open={open}
        onOpenChange={setOpen}
        runId={runId}
        cite={cite}
        label={displayLabel}
      />
    </>
  );
}
