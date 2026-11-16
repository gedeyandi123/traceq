import { useTranslations } from "next-intl";

import type { Completeness, DroppedClaim } from "@/api/client";

import { EmptyState, Panel, SectionHead, StatList } from "./ui/ui";
import s from "./LeftOutView.module.css";
import tbl from "./ui/table.module.css";

/** The reason the drafting step gives for an Acceptance Criterion it leaves empty. */
const HUMAN_REASON = "to be set by a human";

function isHumanAc(d: DroppedClaim): boolean {
  return d.claim === "acceptance" && d.reason.startsWith(HUMAN_REASON);
}

function groupByKind(dropped: readonly DroppedClaim[]): [string, DroppedClaim[]][] {
  const groups = new Map<string, DroppedClaim[]>();
  for (const d of dropped) groups.set(d.claim, [...(groups.get(d.claim) ?? []), d]);
  return [...groups];
}

function DroppedTable({ items }: { items: readonly DroppedClaim[] }) {
  const t = useTranslations("leftOut");
  return (
    <div className={tbl.wrap}>
      <table className={tbl.table}>
        <thead>
          <tr>
            <th className={s.colSubject}>{t("subject")}</th>
            <th>{t("reason")}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((d, i) => (
            <tr key={`${d.claim}/${d.id}/${i}`}>
              <td className={tbl.id}>{d.id}</td>
              <td>{d.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** What the system left out of a run: claims the citation check dropped (by kind, with the
 * Acceptance Criteria left to a human apart) and the URS completeness check. A dropped claim
 * shows kind, subject and reason only, never its content. `completeness` is null for a run
 * folder written before the check existed. */
export function LeftOutView({
  dropped,
  completeness,
}: {
  dropped: readonly DroppedClaim[];
  completeness: Completeness | null;
}) {
  const t = useTranslations("leftOut");
  const human = dropped.filter(isHumanAc);
  const groups = groupByKind(dropped.filter((d) => !isHumanAc(d)));
  const droppedCount = groups.reduce((n, [, items]) => n + items.length, 0);
  const unquoted = (completeness?.urs ?? []).reduce((n, u) => n + u.unquoted.length, 0);
  return (
    <>
      <Panel title={t("summaryTitle")}>
        <StatList
          items={[
            { n: droppedCount, label: t("dropped"), href: "#dropped-claims" },
            { n: human.length, label: t("humanAc"), href: "#human-ac" },
            ...(completeness === null ? [] : [{ n: unquoted, label: t("unquotedTotal"), href: "#completeness" }]),
          ]}
        />
      </Panel>
      <section aria-labelledby="dropped-claims">
        <SectionHead id="dropped-claims" title={t("dropped")} count={droppedCount} note={t("droppedNote")} />
        {groups.length === 0 ? (
          <EmptyState title={t("none")} />
        ) : (
          groups.map(([kind, items]) => (
            <section key={kind} aria-label={t("group", { kind })} className={s.group}>
              <h3>{t("group", { kind })}</h3>
              <DroppedTable items={items} />
            </section>
          ))
        )}
      </section>

      <section aria-labelledby="human-ac">
        <SectionHead id="human-ac" title={t("humanAc")} count={human.length} note={t("humanAcNote")} />
        {human.length === 0 ? <EmptyState title={t("none")} /> : <DroppedTable items={human} />}
      </section>

      <section aria-labelledby="completeness">
        <SectionHead id="completeness" title={t("completeness")} />
        {completeness === null ? (
          <EmptyState title={t("notRun")} />
        ) : (
          completeness.urs.map((u) => (
            <section key={`${u.doc}/${u.rev}`} aria-label={`${u.doc} rev ${u.rev}`} className={s.urs}>
              <h3>{`${u.doc} rev ${u.rev}`}</h3>
              {u.numbers === "not_applicable" ? (
                <p className={s.numbers}>{t("numbersNotApplicable")}</p>
              ) : (
                <>
                  <p className={s.numbers}>{t("numbersFound", { found: u.found, missed: u.missed.length })}</p>
                  {u.missed.length > 0 && (
                    <ul className={s.missed}>
                      {u.missed.map((m) => (
                        <li key={`${m.number}/${m.page}`}>
                          {t("missedNumber", { number: m.number, page: m.page })}
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
              <h4 className={s.h4}>
                {t("unquoted")} <span className={s.count}>{u.unquoted.length}</span>
              </h4>
              {u.unquoted.length === 0 ? (
                <p className="muted">{t("none")}</p>
              ) : (
                <ul className={s.unquoted}>
                  {u.unquoted.map((x) => (
                    <li key={`${x.page}/${x.text}`}>
                      <span className={s.page}>{t("page", { page: x.page })}</span>
                      <pre>{x.text}</pre>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ))
        )}
      </section>
    </>
  );
}
