import { useTranslations } from "next-intl";

import type { Completeness, DroppedClaim } from "@/api/client";

import { EmptyState } from "./ui/ui";
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
            <th className={s.colKind}>{t("kind")}</th>
            <th className={s.colSubject}>{t("subject")}</th>
            <th>{t("reason")}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((d, i) => (
            <tr key={`${d.claim}/${d.id}/${i}`}>
              <td>
                <span className={s.kind}>{d.claim}</span>
              </td>
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
  return (
    <>
      <section className={s.section} aria-labelledby="dropped-claims">
        <div className={s.head}>
          <h2 id="dropped-claims">{t("dropped")}</h2>
          <span className={s.count}>{droppedCount}</span>
        </div>
        <p className={s.note}>{t("droppedNote")}</p>
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

      <section className={s.section} aria-labelledby="human-ac">
        <div className={s.head}>
          <h2 id="human-ac">{t("humanAc")}</h2>
          <span className={s.count}>{human.length}</span>
        </div>
        <p className={s.note}>{t("humanAcNote")}</p>
        {human.length === 0 ? <EmptyState title={t("none")} /> : <DroppedTable items={human} />}
      </section>

      <section className={s.section} aria-labelledby="completeness">
        <div className={s.head}>
          <h2 id="completeness">{t("completeness")}</h2>
        </div>
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
