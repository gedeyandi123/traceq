import { Info } from "lucide-react";
import { useTranslations } from "next-intl";

import type { Persona } from "@/auth/session";
import {
  APPROVING_ROLE,
  DECIDING_ROLE,
  EXECUTING_ROLE,
  WITNESSING_ROLE,
} from "@/decisions/vocabulary";
import { initials, resolveRoleKey } from "@/lib/persona";

import { Button, EmptyState } from "./ui/ui";

/** The sign-in screen: the demo personas as cards, each with its role as a label and labelled
 * as demo identities (ADR 0005). No password. The action runs on the Next.js server; the token
 * never reaches client-side JavaScript. */
export function SignInView({
  personas,
  action,
  nextPath,
  oidcMode = false,
  oidcLoginHref = "/api/auth/login",
}: {
  personas: readonly Persona[] | null;
  action: (formData: FormData) => void | Promise<void>;
  nextPath?: string;
  oidcMode?: boolean;
  oidcLoginHref?: string;
}) {
  const t = useTranslations("signin");
  if (oidcMode) {
    return (
      <div className="mx-auto max-w-xl space-y-5">
        <div>
          <h1 className="m-0 text-xl font-bold tracking-tight text-ink">{t("title")}</h1>
          <p className="mt-1 mb-0 text-sm text-ink-muted">{t("oidcNote")}</p>
        </div>
        <div className="rounded-lg border border-border bg-surface p-5 shadow-xs">
          <a
            href={oidcLoginHref}
            className="inline-flex h-9 w-full items-center justify-center rounded-md border border-accent bg-accent px-4 text-sm font-semibold text-on-accent no-underline transition-colors hover:bg-accent-hover"
          >
            {t("oidcSignIn")}
          </a>
        </div>
      </div>
    );
  }
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="m-0 text-xl font-bold tracking-tight text-ink">{t("title")}</h1>
        <p className="mt-1 mb-0 text-sm text-ink-muted">{t("lead")}</p>
      </div>

      <div className="flex items-start gap-2.5 rounded-lg border border-info-edge bg-info-soft px-4 py-3 text-xs leading-relaxed text-ink">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-info" aria-hidden="true" />
        <p className="m-0">{t("demoNote")}</p>
      </div>

      {personas === null && <EmptyState title={t("unavailable")} />}
      {personas?.length === 0 && <EmptyState title={t("empty")} />}

      <ul className="m-0 grid list-none grid-cols-1 gap-4 p-0 sm:grid-cols-2 lg:grid-cols-3">
        {personas?.map((p) => {
          const flags = {
            mayDecide: p.roles.includes(DECIDING_ROLE),
            mayApprove: p.roles.includes(APPROVING_ROLE),
            mayExecute: p.roles.includes(EXECUTING_ROLE),
            mayWitness: p.roles.includes(WITNESSING_ROLE),
          };
          const label = resolveRoleKey(flags);
          const avatarStyle = flags.mayDecide
            ? "border-accent/30 bg-accent-soft text-accent"
            : flags.mayApprove
              ? "border-info-edge bg-info-soft text-info"
              : flags.mayExecute
                ? "border-warn-edge bg-warn-soft text-warn"
                : flags.mayWitness
                  ? "border-pass-edge bg-pass-soft text-pass"
                  : "border-border bg-sunken text-ink-muted";
          const badgeStyle = avatarStyle;
          return (
            <li
              key={p.username}
              className="rounded-lg border border-border bg-surface p-4 shadow-xs transition-colors hover:border-border-strong"
            >
              <form action={action} className="flex h-full flex-col justify-between gap-4">
                <input type="hidden" name="username" value={p.username} />
                {nextPath && <input type="hidden" name="next" value={nextPath} />}
                <div className="space-y-2.5">
                  <div className="flex items-center gap-3">
                    <span
                      aria-hidden="true"
                      className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border text-sm font-bold ${avatarStyle}`}
                    >
                      {initials(p.name)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div title={p.name} className="truncate text-sm font-bold text-ink">
                        {p.name}
                      </div>
                      <div className="mt-1">
                        <span className="sr-only">{t("role")}: </span>
                        <span
                          className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${badgeStyle}`}
                        >
                          {t(label)}
                        </span>
                      </div>
                    </div>
                  </div>
                  <p className="m-0 text-xs leading-relaxed text-ink-muted">
                    {t(`roleDesc.${label}`)}
                  </p>
                </div>

                <Button type="submit" variant="soft" className="w-full justify-center">
                  {t("as", { name: p.name })}
                </Button>
              </form>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
