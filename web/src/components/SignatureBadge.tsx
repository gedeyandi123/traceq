"use client";

import { AlertTriangle, CheckCircle2, HelpCircle, Info, ShieldCheck, ShieldOff } from "lucide-react";
import { useTranslations } from "next-intl";

import type { ElectronicSignatureView } from "@/api/client";
import { formatWhen } from "./formatWhen";
import { CopyHashButton } from "./ui/CopyHashButton";

/** Displays an Electronic Signature binding (or honest pre-Step-8 recorded-status fallback)
 * with signer name, UTC timestamp, Signature Meaning, content_hash, verification status, and
 * ADR 0007 Demo vs Electronic Signature label. `verified` is three-valued: `true` (the bound
 * hash matches the hash recomputed from the stored data), `false` (it does not) and
 * `null`/absent ("not checked": nothing was compared, never shown as verified). */
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

  const check = signature.verified === true ? "verified" : signature.verified === false ? "failed" : "notChecked";

  const badgeTone = voided
    ? "border-warn-edge bg-warn-soft text-warn"
    : signature.is_demo
      ? "border-info-edge bg-info-soft text-info"
      : // A matching hash is not an approval: the outer pill is neutral, only a failure is red.
        check === "failed"
          ? "border-fail-edge bg-fail-soft text-fail"
          : "border-border bg-surface text-ink-muted";

  // The check beside "Hash cocok" is neutral, never green: a matching hash says the stored
  // data is unchanged, not that anyone approved it. A failed check stays red.
  const checkTone = check === "failed" ? "text-fail" : "text-ink-muted";

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
          ) : check === "verified" ? (
            <ShieldCheck className="h-3 w-3 shrink-0" aria-hidden="true" />
          ) : check === "failed" ? (
            <ShieldOff className="h-3 w-3 shrink-0" aria-hidden="true" />
          ) : (
            <HelpCircle className="h-3 w-3 shrink-0" aria-hidden="true" />
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

        <span className={`inline-flex items-center gap-1 text-[10px] font-semibold ${checkTone}`}>
          {check === "verified" && !voided && (
            <CheckCircle2
              className="h-3 w-3 shrink-0"
              aria-hidden="true"
              data-testid="signature-verified-check"
            />
          )}
          <span>
            {check === "verified"
              ? t("verified")
              : check === "failed"
                ? t("unverified")
                : t("notChecked")}
          </span>
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
