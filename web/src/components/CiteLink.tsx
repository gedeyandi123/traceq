import { useTranslations } from "next-intl";

import { documentHref } from "@/api/client";
import type { Cite } from "@/api/client";

/** A citation: opens the cited page of the document as the run read it; the verbatim quote
 * shows on hover. */
export function CiteLink({ runId, cite }: { runId: string; cite: Cite }) {
  const t = useTranslations("common");
  return (
    <a href={documentHref(runId, cite)} target="_blank" rel="noreferrer" title={cite.quote}>
      {t("cite", { doc: cite.doc, rev: cite.rev, page: cite.page })}
    </a>
  );
}
