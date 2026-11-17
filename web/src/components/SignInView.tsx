import { useTranslations } from "next-intl";

import type { Persona } from "@/auth/session";
import { DECIDING_ROLE } from "@/decisions/vocabulary";

import s from "./SignInView.module.css";
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
 * as demo identities. No password. The action runs on the Next.js server; the token never
 * reaches client-side JavaScript. */
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
      <h1>{t("title")}</h1>
      <p className={s.lead}>{t("lead")}</p>
      <p className={s.note}>{t("demoNote")}</p>
      {personas === null && <EmptyState title={t("unavailable")} />}
      <ul className={s.cards}>
        {personas?.map((p) => {
          const decides = p.roles.includes(DECIDING_ROLE);
          return (
            <li key={p.username} className={s.card}>
              <form action={action} className={s.persona}>
                <input type="hidden" name="username" value={p.username} />
                <span className={s.avatar} aria-hidden="true">
                  {initials(p.name)}
                </span>
                <span className={s.who}>
                  <span className={s.name}>{p.name}</span>
                  <span className={s.role}>
                    <span className="visually-hidden">{t("role")}: </span>
                    <span className={decides ? s.decides : s.reads}>{decides ? t("canDecide") : t("readOnly")}</span>
                  </span>
                </span>
                <Button type="submit" variant={decides ? "primary" : "soft"} className={s.button}>
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
