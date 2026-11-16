import { useTranslations } from "next-intl";

import type { CoverageClass, Decision, DecisionCounts, Proposal } from "@/api/client";

/** Why a run shows read-only: not signed in, signed in without the deciding role, the run is
 * not imported, or the API refused the token or has no database. */
export type ReadOnlyReason = "signedOut" | "noRole" | "notImported" | "unavailable";

/** Why the API refused a decision, as the screen reports it. */
export type DecisionError = "refused" | "forbidden" | "unauthorized" | "failed";

export type DecisionAccess =
  | { mode: "decide"; action: (formData: FormData) => void | Promise<void> }
  | { mode: "readOnly"; why: ReadOnlyReason };

/** What a screen knows about the decisions of its run. ``proposals`` and ``counts`` are absent
 * when the API could not give them (not signed in, run not imported). */
export type DecisionView = {
  proposals?: readonly Proposal[];
  counts?: DecisionCounts;
  access: DecisionAccess;
  error?: DecisionError;
};

/** The screen a decision form returns to. */
export type DecisionScreen = "matrix" | "findings";

const CLASSES: readonly CoverageClass[] = [
  "covered_by_vendor",
  "partial",
  "site_only",
  "gap",
  "conflict",
];

type T = ReturnType<typeof useTranslations<"decisions">>;
type ClassT = ReturnType<typeof useTranslations<"matrix">>;

const date = new Intl.DateTimeFormat("id-ID", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  timeZone: "UTC",
});
const time = new Intl.DateTimeFormat("id-ID", {
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
});

function summary(t: T, classes: ClassT, d: Decision): string {
  const at = new Date(d.at);
  const when = t("when", { date: date.format(at), time: time.format(at) });
  if (d.decision === "edited") {
    return t("made.edited", { class: classes(`classes.${d.coverage ?? "none"}`), name: d.name, when });
  }
  return t(`made.${d.decision}`, { name: d.name, when });
}

function Made({ t, classes, d }: { t: T; classes: ClassT; d: Decision }) {
  return (
    <>
      <span>{summary(t, classes, d)}</span>
      {d.reason && <div className="reason">{d.reason}</div>}
    </>
  );
}

/** The read-only line (what is needed to decide) and the outcome of a refused decision. */
export function DecisionNotice({ view }: { view: DecisionView }) {
  const t = useTranslations("decisions");
  return (
    <>
      {view.access.mode === "readOnly" && (
        <p className="read-only">{t(`readOnly.${view.access.why}`)}</p>
      )}
      {view.error && (
        <p role="alert" className="failure">
          {t(`errors.${view.error}`)}
        </p>
      )}
    </>
  );
}

/** The decision counts of the run for the kinds a screen shows. Counts of stored decisions,
 * not a score. */
export function DecisionTally({
  counts,
  kinds,
}: {
  counts: DecisionCounts | undefined;
  kinds: readonly Proposal["kind"][];
}) {
  const t = useTranslations("decisions");
  if (!counts) return null;
  return (
    <table className="tally">
      <caption>{t("counts.title")}</caption>
      <thead>
        <tr>
          <th scope="col">{t("counts.kind")}</th>
          <th scope="col">{t("counts.total")}</th>
          <th scope="col">{t("counts.undecided")}</th>
          <th scope="col">{t("counts.accepted")}</th>
          <th scope="col">{t("counts.edited")}</th>
          <th scope="col">{t("counts.rejected")}</th>
          <th scope="col">{t("counts.changed")}</th>
          <th scope="col">{t("counts.decidedNotProposed")}</th>
        </tr>
      </thead>
      <tbody>
        {kinds.map((k) => {
          const c = counts[k];
          return (
            <tr key={k}>
              <th scope="row">{t(`kinds.${k}`)}</th>
              <td>{c.total}</td>
              <td>{c.undecided}</td>
              <td>{c.accepted}</td>
              <td>{c.edited}</td>
              <td>{c.rejected}</td>
              <td>{c.changed}</td>
              <td>{c.decided_not_proposed}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Hidden({
  runId,
  proposal,
  screen,
  decision,
}: {
  runId: string;
  proposal: Proposal;
  screen: DecisionScreen;
  decision: Decision["decision"];
}) {
  return (
    <>
      <input type="hidden" name="run_id" value={runId} />
      <input type="hidden" name="proposal_id" value={proposal.id} />
      <input type="hidden" name="screen" value={screen} />
      <input type="hidden" name="decision" value={decision} />
    </>
  );
}

function Reason({ t }: { t: T }) {
  return <textarea name="reason" required aria-label={t("reason")} placeholder={t("reason")} />;
}

/** One decision per form: accept, reject (findings) or change the class (Coverage rows). A
 * Reason for Change is required to reject, to change a class, and to replace a decision
 * already made on this content. */
function Forms({
  t,
  classes,
  proposal,
  runId,
  screen,
  proposed,
  action,
}: {
  t: T;
  classes: ClassT;
  proposal: Proposal;
  runId: string;
  screen: DecisionScreen;
  proposed: CoverageClass | null | undefined;
  action: (formData: FormData) => void | Promise<void>;
}) {
  const replacing = proposal.state === "decided";
  const coverage = proposal.kind === "coverage";
  return (
    <div className="decide">
      {!(coverage && proposed == null) && (
        <form action={action}>
          <Hidden runId={runId} proposal={proposal} screen={screen} decision="accepted" />
          {replacing && <Reason t={t} />}
          <button type="submit">{t("accept")}</button>
        </form>
      )}
      {coverage ? (
        <form action={action}>
          <Hidden runId={runId} proposal={proposal} screen={screen} decision="edited" />
          <select name="coverage" required aria-label={t("toClass")} defaultValue="">
            <option value="" disabled>
              {t("toClass")}
            </option>
            {CLASSES.filter((c) => c !== proposed).map((c) => (
              <option key={c} value={c}>
                {classes(`classes.${c}`)}
              </option>
            ))}
          </select>
          <Reason t={t} />
          <button type="submit">{t("edit")}</button>
        </form>
      ) : (
        <form action={action}>
          <Hidden runId={runId} proposal={proposal} screen={screen} decision="rejected" />
          <Reason t={t} />
          <button type="submit">{t("reject")}</button>
        </form>
      )}
    </div>
  );
}

/** Where one Proposal stands: its decision state, the decisions on this content (current
 * first) or, when its content changed, the latest earlier decision; and the decision forms
 * when the viewer may decide. ``proposed``: the class the system proposed, for a Coverage
 * row. Nothing when the run holds no such Proposal. */
export function DecisionCell({
  proposal,
  runId,
  screen,
  access,
  proposed,
}: {
  proposal: Proposal | undefined;
  runId: string;
  screen: DecisionScreen;
  access: DecisionAccess;
  proposed?: CoverageClass | null;
}) {
  const t = useTranslations("decisions");
  const classes = useTranslations("matrix");
  if (proposal === undefined) return null;
  const [current, ...earlier] = proposal.decisions;
  return (
    <div className={`decision decision-${proposal.state}`}>
      <strong>{t(`states.${proposal.state}`)}</strong>
      {current && (
        <div>
          <Made t={t} classes={classes} d={current} />
        </div>
      )}
      {earlier.length > 0 && (
        <div className="muted">
          {t("earlier")}
          <ul>
            {earlier.map((d) => (
              <li key={d.id}>
                <Made t={t} classes={classes} d={d} />
              </li>
            ))}
          </ul>
        </div>
      )}
      {proposal.previous && (
        <div className="muted">
          <span>{t("previous", { summary: summary(t, classes, proposal.previous) })}</span>
          {proposal.previous.reason && <div className="reason">{proposal.previous.reason}</div>}
        </div>
      )}
      {access.mode === "decide" && (
        <Forms
          t={t}
          classes={classes}
          proposal={proposal}
          runId={runId}
          screen={screen}
          proposed={proposed}
          action={access.action}
        />
      )}
    </div>
  );
}
