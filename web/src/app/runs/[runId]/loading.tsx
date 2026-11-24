import { getTranslations } from "next-intl/server";

import s from "@/components/ui/ui.module.css";

export default async function RunLoading() {
  const t = await getTranslations("runHeader");
  return (
    <div role="status" className={s.loadingBox}>
      <p>{t("loading")}</p>
    </div>
  );
}
