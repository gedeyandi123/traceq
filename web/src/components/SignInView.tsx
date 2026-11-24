import { Info } from "lucide-react";
import { useTranslations } from "next-intl";

import type { Persona } from "@/auth/session";
import { APPROVING_ROLE, DECIDING_ROLE } from "@/decisions/vocabulary";

import { Button, EmptyState } from "./ui/ui";

/** The first letters of a persona's first two names, for the card's avatar. */
function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w.charAt(0))
    .join("")
    .toUpperCase();
}

/** The sign-in screen: the demo personas as cards, each with its role as a label and labelled
 * as demo identities (ADR 0005). No password. The action runs on the Next.js server; the token
 * never reaches client-side JavaScript. */
export function SignInView({
  personas,
  action,
}: {
  personas: readonly Persona[] | null;
  action: (formData: FormData) => void | Promise<void>;
}) {
  const t = useTranslations("signin");
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1 className="m-0 text-xl font-bold tracking-tight text-ink">{t("title")}</h1>
        <p className="mt-1 mb-0 text-sm text-ink-muted">{t("lead")}</p>
      </div>

      <div className="flex items-start gap-2.5 rounded-lg border border-info-edge bg-info-soft px-4 py-3 text-xs leading-relaxed text-ink">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-info" aria-hidden="true" />
        <p className="m-0">{t("demoNote")}</p>
      </div>

      {personas === null && <EmptyState title={t("unavailable")} />}

      <ul className="m-0 grid list-none grid-cols-1 gap-4 p-0 sm:grid-cols-2">
        {personas?.map((p) => {
          const decides = p.roles.includes(DECIDING_ROLE);
          const approves = p.roles.includes(APPROVING_ROLE);
          const label = decides ? "canDecide" : approves ? "canApprove" : "readOnly";
          const hasAuthority = decides || approves;
          return (
            <li
              key={p.username}
              className="rounded-lg border border-border bg-surface p-4 shadow-xs transition-colors hover:border-border-strong"
            >
              <form action={action} className="flex h-full flex-col justify-between gap-4">
                <input type="hidden" name="username" value={p.username} />
                <div className="flex items-center gap-3">
                  <span
                    aria-hidden="true"
                    className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border text-sm font-bold ${
                      hasAuthority
                        ? "border-accent/30 bg-accent-soft text-accent"
                        : "border-border bg-sunken text-ink-muted"
                    }`}
                  >
                    {initials(p.name)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-bold text-ink">{p.name}</div>
                    <div className="mt-1">
                      <span className="sr-only">{t("role")}: </span>
                      <span
                        className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${
                          hasAuthority
                            ? "border-accent/25 bg-accent-soft text-accent"
                            : "border-border bg-sunken text-ink-muted"
                        }`}
                      >
                        {t(label)}
                      </span>
                    </div>
                  </div>
                </div>

                <Button
                  type="submit"
                  variant={hasAuthority ? "primary" : "soft"}
                  className="w-full justify-center"
                >
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
