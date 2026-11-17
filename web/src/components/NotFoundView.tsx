import { useTranslations } from "next-intl";
import Link from "next/link";

import s from "./NotFoundView.module.css";

/** The 404 page: what happened, and the way back to the run list. Synchronous, so a render
 * test mounts it under the same provider as the other views; the not-found route only
 * renders it. */
export function NotFoundView() {
  const t = useTranslations("app");
  return (
    <section className={s.box}>
      <p className={s.code} aria-hidden="true">
        404
      </p>
      <h1>{t("notFoundTitle")}</h1>
      <p className={s.body}>{t("notFoundBody")}</p>
      <Link href="/" className={s.back}>
        {t("toRuns")}
      </Link>
    </section>
  );
}
