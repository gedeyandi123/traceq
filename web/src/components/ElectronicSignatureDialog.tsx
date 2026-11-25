"use client";

import { AlertCircle, Clock, Info, KeyRound, ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState, type ReactNode } from "react";

import type { SignatureMeaning } from "@/api/client";
import type { SigningAuthState } from "@/auth/session";
import { Modal } from "./ui/Modal";
import { SubmitButton } from "./ui/SubmitButton";

const REAUTH_WINDOW_SECONDS = 60;

/** Owned Radix Dialog for Electronic Signature confirmation (ADR 0007, ADR 0014):
 * - Displays target summary, content_hash preview, Signature Meaning, and honest Demo vs OIDC label.
 * - In OIDC mode: triggers `/api/auth/reauth`, shows live countdown from `auth_time`, and requires
 *   explicit 1-click confirmation (no auto-submit).
 * - In Demo mode: explicit 1-click confirmation minting a fresh single-use demo token. */
export function ElectronicSignatureDialog({
  open,
  onOpenChange,
  title,
  targetSummary,
  signatureMeaning,
  contentHash,
  signingAuth,
  reauthNextUrl,
  onBeforeReauth,
  onReauthNavigate,
  action,
  confirmLabel,
  cancelLabel,
  error,
  isReauthError = false,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  targetSummary: string;
  signatureMeaning: SignatureMeaning;
  contentHash?: string | null;
  signingAuth: SigningAuthState;
  reauthNextUrl: string;
  onBeforeReauth?: () => void;
  onReauthNavigate?: (url: string) => void;
  action: (formData: FormData) => void | Promise<void>;
  confirmLabel: string;
  cancelLabel?: string;
  error?: string | null;
  isReauthError?: boolean;
  children?: ReactNode;
}) {
  const t = useTranslations("signature");
  const tp = useTranslations("protocol");

  const [nowSeconds, setNowSeconds] = useState(() => Math.floor(Date.now() / 1000));

  useEffect(() => {
    if (!open || !signingAuth.oidcMode || signingAuth.reauthAuthTime === null) return;
    const immediate = setTimeout(() => {
      setNowSeconds(Math.floor(Date.now() / 1000));
    }, 0);
    const timer = setInterval(() => {
      setNowSeconds(Math.floor(Date.now() / 1000));
    }, 1000);
    return () => {
      clearTimeout(immediate);
      clearInterval(timer);
    };
  }, [open, signingAuth.oidcMode, signingAuth.reauthAuthTime]);

  const remainingSeconds =
    signingAuth.oidcMode && signingAuth.reauthAuthTime !== null
      ? Math.max(0, signingAuth.reauthAuthTime + REAUTH_WINDOW_SECONDS - nowSeconds)
      : 0;
  const reauthExpired =
    signingAuth.oidcMode && signingAuth.reauthAuthTime !== null && remainingSeconds <= 0;
  const isReauthFresh =
    signingAuth.oidcMode && remainingSeconds > 0 && !isReauthError;

  const reauthHref = `/api/auth/reauth?next=${encodeURIComponent(reauthNextUrl)}`;

  const handleReauthClick = () => {
    onBeforeReauth?.();
    if (onReauthNavigate) {
      onReauthNavigate(reauthHref);
    } else if (typeof window !== "undefined") {
      window.location.assign(reauthHref);
    }
  };

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      size="sm"
      title={title}
      description={targetSummary}
    >
      <div className="space-y-3 text-xs">
        <div
          className={`flex items-start gap-2 rounded-md border px-3 py-2 text-[11px] leading-relaxed ${
            signingAuth.oidcMode
              ? "border-pass-edge bg-pass-soft text-pass"
              : "border-info-edge bg-info-soft text-info"
          }`}
        >
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>{signingAuth.oidcMode ? t("oidcHonestNote") : t("demoHonestNote")}</span>
        </div>

        <dl className="m-0 space-y-2 rounded-md border border-border bg-sunken p-3">
          <div>
            <dt className="text-[11px] font-semibold text-ink-muted">{t("targetLabel")}</dt>
            <dd className="m-0 mt-0.5 font-medium text-ink">{targetSummary}</dd>
          </div>
          <div>
            <dt className="text-[11px] font-semibold text-ink-muted">{t("meaningLabel")}</dt>
            <dd className="m-0 mt-0.5 font-semibold text-ink">
              {t(`meanings.${signatureMeaning}`)}
            </dd>
          </div>
          {contentHash && (
            <div>
              <dt className="text-[11px] font-semibold text-ink-muted">{t("contentHashLabel")}</dt>
              <dd className="m-0 mt-0.5">
                <code
                  title={contentHash}
                  className="block font-mono text-[11px] text-ink tabular-nums"
                >
                  {contentHash.slice(0, 16)}…
                </code>
              </dd>
            </div>
          )}
        </dl>

        {error && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-md border border-fail-edge bg-fail-soft px-3 py-2 text-xs text-fail"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}

        {signingAuth.oidcMode ? (
          isReauthFresh ? (
            <form action={action} className="space-y-3">
              {children}
              <div className="flex items-center gap-2 rounded-md border border-pass-edge bg-pass-soft px-3 py-2 text-[11px] font-semibold text-pass tabular-nums">
                <Clock className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span>{t("reauthVerified", { seconds: remainingSeconds })}</span>
              </div>
              <p className="m-0 text-[11px] text-ink-muted">{t("oidcConfirmHint")}</p>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => onOpenChange(false)}
                  className="cursor-pointer rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-sunken"
                >
                  {cancelLabel ?? tp("cancel")}
                </button>
                <SubmitButton variant="primary">
                  <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{confirmLabel}</span>
                </SubmitButton>
              </div>
            </form>
          ) : (
            <div className="space-y-3">
              <div className="flex items-start gap-2 rounded-md border border-warn-edge bg-warn-soft px-3 py-2 text-[11px] text-warn">
                <KeyRound className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span>{reauthExpired ? t("reauthExpired") : t("reauthPrompt")}</span>
              </div>
              <div className="flex flex-wrap justify-end gap-2">
                <button
                  type="button"
                  onClick={() => onOpenChange(false)}
                  className="cursor-pointer rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-sunken"
                >
                  {cancelLabel ?? tp("cancel")}
                </button>
                <button
                  type="button"
                  onClick={handleReauthClick}
                  className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-accent bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent transition-colors hover:bg-accent-hover"
                >
                  <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{t("reauthButton")}</span>
                </button>
              </div>
            </div>
          )
        ) : (
          <form action={action} className="space-y-3">
            {children}
            <p className="m-0 text-[11px] text-ink-muted">{t("demoConfirmHint")}</p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => onOpenChange(false)}
                className="cursor-pointer rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-sunken"
              >
                {cancelLabel ?? tp("cancel")}
              </button>
              <SubmitButton variant="primary">
                <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                <span>{confirmLabel}</span>
              </SubmitButton>
            </div>
          </form>
        )}
      </div>
    </Modal>
  );
}
