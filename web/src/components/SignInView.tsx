import { useTranslations } from "next-intl";

export type PersonaItem = { username: string; name: string; roles: string[] };

/** The sign-in screen: the demo personas, labelled as demo identities. No password. The
 * action runs on the Next.js server; the token never reaches client-side JavaScript. */
export function SignInView({
  personas,
  action,
}: {
  personas: readonly PersonaItem[] | null;
  action: (formData: FormData) => void | Promise<void>;
}) {
  const t = useTranslations("signin");
  return (
    <>
      <h1>{t("title")}</h1>
      <p>{t("demoNote")}</p>
      {personas === null && <p>{t("unavailable")}</p>}
      <ul>
        {personas?.map((p) => (
          <li key={p.username}>
            <form action={action}>
              <input type="hidden" name="username" value={p.username} />
              <button type="submit">{t("as", { name: p.name })}</button>{" "}
              <span className="muted">{p.roles.length > 0 ? t("canDecide") : t("readOnly")}</span>
            </form>
          </li>
        ))}
      </ul>
    </>
  );
}
