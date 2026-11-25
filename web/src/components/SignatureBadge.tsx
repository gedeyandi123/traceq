"use client";

import { AlertTriangle, CheckCircle2, Info, ShieldCheck, ShieldOff } from "lucide-react";
import { useTranslations } from "next-intl";

import type { ElectronicSignatureView } from "@/api/client";
import { formatWhen } from "./formatWhen";
import { CopyHashButton } from "./ui/CopyHashButton";

/** Displays an Electronic Signature binding (or honest pre-Step-8 recorded-status fallback)
 * with signer name, UTC timestamp, Signature Meaning, content_hash, verified status, and
 * ADR 0007 Demo vs Electronic Signature label. */
export function SignatureBadge({
  signature,
  voided = false,
  compact = false,
}: {
  signature: ElectronicSignatureView | null | undefined;
  voided?: boolean;
  compact?: boolean;
}) {
  const t = useTranslations("signature");
  const when = useTranslations("decisions");
  const ui = useTranslations("ui");

  if (!signature) {
    return (
      <div className="inline-flex flex-wrap items-center gap-1.5 rounded-md border border-border bg-sunken px-2.5 py-1 text-[11px] text-ink-muted">
        <Info className="h-3.5 w-3.5 shrink-0 text-info" aria-hidden="true" />
        <span className="font-semibold text-ink">{t("recordedStatusBadge")}</span>
        <span>·</span>
        <span>{t("recordedStatusLabel")}</span>
      </div>
    );
  }

  const badgeTone = voided
    ? "border-warn-edge bg-warn-soft text-warn"
    : signature.is_demo
      ? "border-info-edge bg-info-soft text-info"
      : signature.verified
        ? "border-pass-edge bg-pass-soft text-pass"
        : "border-fail-edge bg-fail-soft text-fail";

  return (
    <div
      className={`rounded-md border border-border bg-sunken/70 ${compact ? "space-y-1 p-2" : "space-y-1.5 p-2.5"} text-[11px]`}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span
          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${badgeTone}`}
        >
          {voided ? (
            <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
          ) : signature.verified ? (
            <ShieldCheck className="h-3 w-3 shrink-0" aria-hidden="true" />
          ) : (
            <ShieldOff className="h-3 w-3 shrink-0" aria-hidden="true" />
          )}
          <span>{signature.is_demo ? t("demoBadge") : t("electronicBadge")}</span>
        </span>

        {voided && (
          <span className="inline-flex items-center rounded-full border border-warn-edge bg-warn-soft px-2 py-0.5 text-[10px] font-semibold text-warn">
            {t("voided")}
          </span>
        )}

        <span className="inline-flex items-center rounded-full border border-border bg-surface px-2 py-0.5 text-[10px] font-medium text-ink">
          {t(`meanings.${signature.signature_meaning}`)}
        </span>

        <span
          className={`inline-flex items-center gap-1 text-[10px] font-semibold ${
            signature.verified ? "text-pass" : "text-fail"
          }`}
        >
          {signature.verified && <CheckCircle2 className="h-3 w-3 shrink-0" aria-hidden="true" />}
          <span>{signature.verified ? t("verified") : t("unverified")}</span>
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-ink tabular-nums">
        <span className="font-semibold">{signature.signer_name}</span>
        <span className="text-ink-muted">·</span>
        <span className="text-ink-muted">{formatWhen(when, signature.at)}</span>
        <span className="text-ink-muted">·</span>
        <code
          title={signature.content_hash}
          className="rounded bg-surface px-1.5 py-0.5 font-mono text-[10px] text-ink tabular-nums"
        >
          {signature.content_hash.slice(0, 12)}…
        </code>
        <CopyHashButton
          value={signature.content_hash}
          copyLabel={ui("copyHash")}
          copiedLabel={ui("copied")}
          className="h-6 px-2 text-[10px]"
        />
      </div>

      <p className="m-0 text-[10px] leading-relaxed text-ink-muted">{signature.label}</p>
    </div>
  );
}
