import { useTranslations } from "next-intl";

import type { CoverageClass, Decision, DecisionCounts, Proposal } from "@/api/client";
import type { DecideActionState } from "@/decisions/actions";
import { COVERAGE_CLASSES } from "@/decisions/vocabulary";
import { formatWhen } from "./formatWhen";
import { SubmitButton } from "./ui/SubmitButton";

/** Why a run shows read-only: not signed in, signed in without the deciding role, the run is
 * not imported, or the API refused the token or has no database. */
export type ReadOnlyReason = "signedOut" | "noRole" | "notImported" | "unavailable";

/** Why the API refused a decision, as the screen reports it. */
export type DecisionError = "refused" | "conflict" | "forbidden" | "unauthorized" | "failed";

export type DecisionAccess =
  | {
      mode: "decide";
      action: (formData: FormData) => void | Promise<void>;
      inlineAction?: (prevState: DecideActionState, formData: FormData) => Promise<DecideActionState>;
    }
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
export type DecisionScreen = "matrix" | "findings" | "draft" | "protocol";

type T = ReturnType<typeof useTranslations<"decisions">>;
type ClassT = ReturnType<typeof useTranslations<"matrix">>;

function summary(t: T, classes: ClassT, d: Decision): string {
  const when = formatWhen(t, d.at);
  if (d.decision === "edited") {
    // A drafted Test Step edited carries no class: it is edited into a written Test Step.
    if (d.coverage === null) return t("made.editedStep", { name: d.name, when });
    return t("made.edited", { class: classes(`classes.${d.coverage ?? "none"}`), name: d.name, when });
  }
  return t(`made.${d.decision}`, { name: d.name, when });
}

function Made({ t, classes, d }: { t: T; classes: ClassT; d: Decision }) {
  return (
    <>
      <span>{summary(t, classes, d)}</span>
      {d.reason && (
        <div className="mt-1 border-l-2 border-border-strong pl-2 text-ink-muted">{d.reason}</div>
      )}
    </>
  );
}

/** The read-only line (what is needed to decide) and the outcome of a refused decision. With
 * `approver`, an identity without the deciding role is told what it can do instead (the
 * Protocol screen, where the approving role approves or returns a Submitted Protocol). */
export function DecisionNotice({ view, approver = false }: { view: DecisionView; approver?: boolean }) {
  const t = useTranslations("decisions");
  if (view.access.mode !== "readOnly" && !view.error) return null;
  return (
    <div className="mb-3 flex flex-col gap-2">
      {view.access.mode === "readOnly" && (
        <p className="m-0 rounded border border-border bg-sunken px-3 py-2 text-xs text-ink-muted">
          {t(`readOnly.${approver && view.access.why === "noRole" ? "approver" : view.access.why}`)}
        </p>
      )}
      {view.error && (
        <p
          role="alert"
          className="m-0 rounded border border-fail-edge bg-fail-soft px-3 py-2 text-xs font-semibold text-fail"
        >
          {t(`errors.${view.error}`)}
        </p>
      )}
    </div>
  );
}

/** How many Proposals of the kinds a screen shows are decided (accepted, edited or rejected
 * on their current content), and under it, folded, the decision counts of the run. Counts of
 * stored decisions, not a score. `also`: kinds decided on another screen, shown in the folded
 * counts only. */
export function DecisionTally({
  counts,
  kinds,
  also = [],
}: {
  counts: DecisionCounts | undefined;
  kinds: readonly Proposal["kind"][];
  also?: readonly Proposal["kind"][];
}) {
  const t = useTranslations("decisions");
  if (!counts) return null;
  const total = kinds.reduce((n, k) => n + counts[k].total, 0);
  const decided = kinds.reduce(
    (n, k) => n + counts[k].accepted + counts[k].edited + counts[k].rejected,
    0,
  );
  return (
    <div className="mb-4">
      <p className="m-0 text-base font-semibold text-ink tabular-nums">{t("progress", { decided, total })}</p>
      <details className="mt-1">
        <summary className="text-xs font-semibold text-accent">{t("counts.title")}</summary>
        <div className="mt-2 overflow-x-auto rounded-lg border border-border bg-surface">
          <table className="w-full border-collapse text-xs">
            <caption className="sr-only">{t("counts.title")}</caption>
            <thead>
              <tr className="border-b border-border bg-sunken/70 text-ink-muted">
                <th scope="col" className="px-3 py-2 text-left font-semibold">
                  {t("counts.kind")}
                </th>
                <th scope="col" className="px-3 py-2 text-right font-semibold tabular-nums">
                  {t("counts.total")}
                </th>
                <th scope="col" className="px-3 py-2 text-right font-semibold tabular-nums">
                  {t("counts.undecided")}
                </th>
                <th scope="col" className="px-3 py-2 text-right font-semibold tabular-nums">
                  {t("counts.accepted")}
                </th>
                <th scope="col" className="px-3 py-2 text-right font-semibold tabular-nums">
                  {t("counts.edited")}
                </th>
                <th scope="col" className="px-3 py-2 text-right font-semibold tabular-nums">
                  {t("counts.rejected")}
                </th>
                <th scope="col" className="px-3 py-2 text-right font-semibold tabular-nums">
                  {t("counts.changed")}
                </th>
                <th scope="col" className="px-3 py-2 text-right font-semibold tabular-nums">
                  {t("counts.decidedNotProposed")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {[...kinds, ...also].map((k) => {
                const c = counts[k];
                return (
                  <tr key={k}>
                    <th scope="row" className="px-3 py-2 text-left font-medium text-ink">
                      {t(`kinds.${k}`)}
                    </th>
                    <td className="px-3 py-2 text-right tabular-nums">{c.total}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{c.undecided}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{c.accepted}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{c.edited}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{c.rejected}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{c.changed}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{c.decided_not_proposed}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

function Hidden({
  runId,
  proposal,
  screen,
  decision,
  returnQuery,
  anchor,
}: {
  runId: string;
  proposal: Proposal;
  screen: DecisionScreen;
  decision: Decision["decision"];
  returnQuery?: string;
  anchor?: string;
}) {
  return (
    <>
      <input type="hidden" name="run_id" value={runId} />
      <input type="hidden" name="proposal_id" value={proposal.id} />
      <input type="hidden" name="screen" value={screen} />
      <input type="hidden" name="decision" value={decision} />
      {returnQuery && <input type="hidden" name="return_query" value={returnQuery} />}
      {anchor && <input type="hidden" name="anchor" value={anchor} />}
    </>
  );
}

function Reason({ t }: { t: T }) {
  return (
    <textarea
      name="reason"
      required
      aria-label={t("reason")}
      placeholder={t("reason")}
      className="min-h-14 w-full rounded border border-border-strong bg-surface p-2 text-xs text-ink placeholder:text-ink-muted"
    />
  );
}

const STATE_TONES: Record<Proposal["state"], string> = {
  undecided: "text-ink-muted",
  decided: "text-pass",
  changed: "text-warn",
};

/** One decision per form: accept, reject (findings) or change the class (Coverage rows). */
function Forms({
  t,
  classes,
  proposal,
  runId,
  screen,
  proposed,
  action,
  returnQuery,
  anchor,
}: {
  t: T;
  classes: ClassT;
  proposal: Proposal;
  runId: string;
  screen: DecisionScreen;
  proposed: CoverageClass | null | undefined;
  action: (formData: FormData) => void | Promise<void>;
  returnQuery?: string;
  anchor?: string;
}) {
  const replacing = proposal.state === "decided";
  const coverage = proposal.kind === "coverage";
  const accept = !(coverage && proposed == null) && (
    <form action={action} className="flex flex-col items-start gap-2">
      <Hidden
        runId={runId}
        proposal={proposal}
        screen={screen}
        decision="accepted"
        returnQuery={returnQuery}
        anchor={anchor}
      />
      {replacing && <Reason t={t} />}
      <SubmitButton variant="soft">{t("accept")}</SubmitButton>
    </form>
  );
  const other = coverage ? (
    <form action={action} className="flex flex-col items-start gap-2">
      <Hidden
        runId={runId}
        proposal={proposal}
        screen={screen}
        decision="edited"
        returnQuery={returnQuery}
        anchor={anchor}
      />
      <select
        name="coverage"
        required
        aria-label={t("toClass")}
        defaultValue=""
        className="min-h-7 max-w-full rounded border border-border-strong bg-surface px-2 text-xs text-ink"
      >
        <option value="" disabled>
          {t("toClass")}
        </option>
        {COVERAGE_CLASSES.filter((c) => c !== proposed).map((c) => (
          <option key={c} value={c}>
            {classes(`classes.${c}`)}
          </option>
        ))}
      </select>
      <Reason t={t} />
      <SubmitButton>{t("edit")}</SubmitButton>
    </form>
  ) : (
    <form action={action} className="flex flex-col items-start gap-2">
      <Hidden
        runId={runId}
        proposal={proposal}
        screen={screen}
        decision="rejected"
        returnQuery={returnQuery}
        anchor={anchor}
      />
      <Reason t={t} />
      <SubmitButton>{t("reject")}</SubmitButton>
    </form>
  );
  if (replacing) {
    return (
      <div className="mt-2 flex flex-col gap-2">
        <details>
          <summary className="py-1 text-xs font-semibold text-accent">{t("redecide")}</summary>
          <div className="mt-2 flex flex-col gap-3">
            {accept}
            {other}
          </div>
        </details>
      </div>
    );
  }
  return (
    <div className="mt-2 flex flex-wrap items-start gap-x-3 gap-y-2">
      {accept}
      <details>
        <summary className="py-1 text-xs font-semibold text-accent">{coverage ? t("edit") : t("reject")}…</summary>
        <div className="mt-2 flex flex-col gap-3">{other}</div>
      </details>
    </div>
  );
}

/** Where one Proposal stands: its decision state, the decisions on this content (current
 * first) or, when its content changed, the latest earlier decision with, for a Coverage row,
 * the class it settled on; and the decision forms when the viewer may decide. */
export function DecisionCell({
  proposal,
  runId,
  screen,
  access,
  proposed,
  returnQuery,
  anchor,
}: {
  proposal: Proposal | undefined;
  runId: string;
  screen: DecisionScreen;
  access: DecisionAccess;
  proposed?: CoverageClass | null;
  returnQuery?: string;
  anchor?: string;
}) {
  const t = useTranslations("decisions");
  const classes = useTranslations("matrix");
  if (proposal === undefined) return null;
  const [current, ...earlier] = proposal.decisions;
  return (
    <div className={`flex flex-col gap-1 text-xs ${access.mode === "decide" ? "min-w-44" : ""}`.trim()}>
      <strong className={`font-semibold ${STATE_TONES[proposal.state]}`}>{t(`states.${proposal.state}`)}</strong>
      {current && (
        <div className="text-ink">
          <Made t={t} classes={classes} d={current} />
        </div>
      )}
      {earlier.length > 0 && (
        <div className="text-xs text-ink-muted">
          {t("earlier")}
          <ul className="mt-1 mb-0 pl-4">
            {earlier.map((d) => (
              <li key={d.id}>
                <Made t={t} classes={classes} d={d} />
              </li>
            ))}
          </ul>
        </div>
      )}
      {proposal.previous && (
        <div className="text-xs text-ink-muted">
          <span>{t("previous", { summary: summary(t, classes, proposal.previous) })}</span>
          {proposal.previous_class && (
            <div>{t("previousClass", { class: classes(`classes.${proposal.previous_class}`) })}</div>
          )}
          {proposal.previous.reason && (
            <div className="mt-1 border-l-2 border-border-strong pl-2 text-ink-muted">
              {proposal.previous.reason}
            </div>
          )}
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
          returnQuery={returnQuery}
          anchor={anchor}
        />
      )}
    </div>
  );
}
