import { useTranslations } from "next-intl";

import type { Completeness, DroppedClaim } from "@/api/client";

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
    <table>
      <thead>
        <tr>
          <th>{t("kind")}</th>
          <th>{t("subject")}</th>
          <th>{t("reason")}</th>
        </tr>
      </thead>
      <tbody>
        {items.map((d, i) => (
          <tr key={`${d.claim}/${d.id}/${i}`}>
            <td>{d.claim}</td>
            <td>{d.id}</td>
            <td>{d.reason}</td>
          </tr>
        ))}
      </tbody>
    </table>
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
  return (
    <>
      <section aria-labelledby="dropped-claims">
        <h2 id="dropped-claims">{t("dropped")}</h2>
        <p className="muted">{t("droppedNote")}</p>
        {groups.length === 0 ? (
          <p>{t("none")}</p>
        ) : (
          groups.map(([kind, items]) => (
            <section key={kind} aria-label={t("group", { kind })}>
              <h3>{t("group", { kind })}</h3>
              <DroppedTable items={items} />
            </section>
          ))
        )}
      </section>

      <section aria-labelledby="human-ac">
        <h2 id="human-ac">{t("humanAc")}</h2>
        <p className="muted">{t("humanAcNote")}</p>
        {human.length === 0 ? <p>{t("none")}</p> : <DroppedTable items={human} />}
      </section>

      <section aria-labelledby="completeness">
        <h2 id="completeness">{t("completeness")}</h2>
        {completeness === null ? (
          <p>{t("notRun")}</p>
        ) : (
          completeness.urs.map((u) => (
            <section key={`${u.doc}/${u.rev}`} aria-label={`${u.doc} rev ${u.rev}`}>
              <h3>{`${u.doc} rev ${u.rev}`}</h3>
              {u.numbers === "not_applicable" ? (
                <p>{t("numbersNotApplicable")}</p>
              ) : (
                <>
                  <p>{t("numbersFound", { found: u.found, missed: u.missed.length })}</p>
                  {u.missed.length > 0 && (
                    <ul>
                      {u.missed.map((m) => (
                        <li key={`${m.number}/${m.page}`}>
                          {t("missedNumber", { number: m.number, page: m.page })}
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
              <h4>{t("unquoted")}</h4>
              {u.unquoted.length === 0 ? (
                <p>{t("none")}</p>
              ) : (
                <ul>
                  {u.unquoted.map((x) => (
                    <li key={`${x.page}/${x.text}`}>
                      <span className="muted">{t("page", { page: x.page })}</span>
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
