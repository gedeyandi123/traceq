import { useTranslations } from "next-intl";

import type { Persona } from "@/auth/session";
import { DECIDING_ROLE } from "@/decisions/vocabulary";

import { Callout, EmptyState } from "./ui/ui";
import s from "./SignInView.module.css";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0] ?? "")
    .join("")
    .toUpperCase();
}

/** The sign-in screen: the demo personas, labelled as demo identities. No password. The
 * action runs on the Next.js server; the token never reaches client-side JavaScript. */
export function SignInView({
  personas,
  action,
}: {
  personas: readonly Persona[] | null;
  action: (formData: FormData) => void | Promise<void>;
}) {
  const t = useTranslations("signin");
  return (
    <div className={s.page}>
      <div className={s.card}>
        <h1>{t("title")}</h1>
        <p className={s.lead}>{t("lead")}</p>
        <Callout tone="info">
          <p>{t("demoNote")}</p>
        </Callout>
        {personas === null && <EmptyState title={t("unavailable")} />}
        <ul className={s.list}>
          {personas?.map((p) => {
            const decides = p.roles.includes(DECIDING_ROLE);
            return (
              <li key={p.username}>
                <form action={action} className={s.persona}>
                  <input type="hidden" name="username" value={p.username} />
                  <span className={s.avatar} aria-hidden="true">
                    {initials(p.name)}
                  </span>
                  <span className={s.who}>
                    <span className={s.name}>{p.name}</span>
                    <span className={decides ? s.roleDecide : s.roleRead}>
                      {decides ? t("canDecide") : t("readOnly")}
                    </span>
                  </span>
                  <button type="submit" data-variant={decides ? "primary" : undefined}>
                    {t("as", { name: p.name })}
                  </button>
                </form>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
