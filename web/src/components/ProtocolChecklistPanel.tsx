import { useTranslations } from "next-intl";

import type { ChecklistItem } from "@/api/client";
import type { ProtocolControls } from "./AssembledProtocolView";
import { Button, SectionHeading } from "./ui/ui";

import s from "./AssembledProtocolView.module.css";

type T = ReturnType<typeof useTranslations<"protocol">>;

/** What blocks submission: each of the five checks with its count and links to the rows or
 * numbers concerned, then the submit control for the deciding role, usable when none blocks. */
export function ProtocolChecklistPanel({
  t,
  items,
  runId,
  protocolId,
  controls,
}: {
  t: T;
  items: readonly ChecklistItem[];
  runId: string;
  protocolId: number;
  controls: ProtocolControls;
}) {
  const blocked = items.some((i) => i.count > 0);
  return (
    <section className={s.checklistPanel} aria-labelledby="protocol-checklist">
      <SectionHeading id="protocol-checklist" title={t("checklist.title")} note={t("checklist.note")} />
      <ul className={s.list}>
        {items.map((i) => (
          <li key={i.check} data-testid={`check-${i.check}`} className={i.count > 0 ? s.blocking : undefined}>
            {t(`checklist.items.${i.check}`, { count: i.count })}
            {i.count > 0 && (
              <>
                {": "}
                {i.requirements.map((r, n) => (
                  <span key={r}>
                    {n > 0 && ", "}
                    <a href={`#row-${r}`}>{r}</a>
                  </span>
                ))}
                {i.numbers.map((x, n) => (
                  <span key={`${x.doc}/${x.rev}/${x.number}`}>
                    {n > 0 && ", "}
                    <a href="#protocol-missed">{x.number}</a>
                  </span>
                ))}
              </>
            )}
          </li>
        ))}
      </ul>
      {!blocked && <p className={s.readyNote}>{t("checklist.ready")}</p>}
      {controls !== null && (
        <form action={controls.submit} className={s.form}>
          <input type="hidden" name="run_id" value={runId} />
          <input type="hidden" name="protocol_id" value={protocolId} />
          <Button type="submit" variant="primary" disabled={blocked}>
            {t("submit")}
          </Button>
        </form>
      )}
    </section>
  );
}
