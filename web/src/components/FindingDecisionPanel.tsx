"use client";

import { AlertCircle, ChevronDown, Info } from "lucide-react";
import { useTranslations } from "next-intl";
import { useActionState, useState } from "react";

import type { Decision, DecisionCounts, Proposal } from "@/api/client";
import type { DecisionAccess, DecisionScreen, DecisionView } from "@/components/Decisions";
import { formatWhen } from "@/components/formatWhen";
import { FIELD_BASE_CLASS } from "@/components/ui/FormControls";
import { DecisionStateBadge } from "@/components/ui/StatusBadge";
import type { DecideActionState } from "@/decisions/actions";

type DecisionsT = ReturnType<typeof useTranslations<"decisions">>;
type MatrixT = ReturnType<typeof useTranslations<"matrix">>;

function decisionSummary(td: DecisionsT, tm: MatrixT, d: Decision): string {
  const when = formatWhen(td, d.at);
  if (d.decision === "edited") {
    if (d.coverage === null) return td("made.editedStep", { name: d.name, when });
    return td("made.edited", {
      class: tm(`classes.${d.coverage ?? "none"}`),
      name: d.name,
      when,
    });
  }
  return td(`made.${d.decision}`, { name: d.name, when });
}

function DecisionEntry({ td, tm, d }: { td: DecisionsT; tm: MatrixT; d: Decision }) {
  return (
    <div className="space-y-1">
      <div className="text-xs font-medium text-ink">{decisionSummary(td, tm, d)}</div>
      {d.reason && <div className="text-xs text-ink-muted italic">{d.reason}</div>}
    </div>
  );
}

function wrapLegacyAction(
  action: (formData: FormData) => void | Promise<void>,
): (prevState: DecideActionState, formData: FormData) => Promise<DecideActionState> {
  return async (_prevState, formData) => {
    await action(formData);
    return { ok: true, submittedAt: Date.now() };
  };
}

/** Read-only and error banner styled with Tailwind semantic tokens. */
export function DecisionNoticeBanner({
  view,
  approver = false,
}: {
  view: DecisionView;
  approver?: boolean;
}) {
  const td = useTranslations("decisions");
  if (view.access.mode !== "readOnly" && !view.error) return null;

  return (
    <div className="space-y-2">
      {view.access.mode === "readOnly" && (
        <div className="flex items-start gap-2 rounded-lg border border-info-edge bg-info-soft px-3.5 py-2.5 text-xs text-info">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p className="m-0">
            {td(
              `readOnly.${approver && view.access.why === "noRole" ? "approver" : view.access.why}`,
            )}
          </p>
        </div>
      )}
      {view.error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-fail-edge bg-fail-soft px-3.5 py-2.5 text-xs text-fail"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p className="m-0">{td(`errors.${view.error}`)}</p>
        </div>
      )}
    </div>
  );
}

/** Decision progress line and expandable breakdown table for a screen's proposal kinds. */
export function DecisionCountsSummary({
  counts,
  kinds,
  progressKinds,
}: {
  counts: DecisionCounts | undefined;
  kinds: readonly Proposal["kind"][];
  progressKinds?: readonly Proposal["kind"][];
}) {
  const td = useTranslations("decisions");
  const [open, setOpen] = useState(false);

  if (!counts) return null;

  const summaryKinds = progressKinds ?? kinds;
  const total = summaryKinds.reduce((n, k) => n + counts[k].total, 0);
  const decided = summaryKinds.reduce(
    (n, k) => n + counts[k].accepted + counts[k].edited + counts[k].rejected,
    0,
  );

  return (
    <div className="flex flex-col items-start gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-ink tabular-nums">
          {td("progress", { decided, total })}
        </span>
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          className="inline-flex cursor-pointer items-center gap-1 rounded border border-border bg-surface px-2 py-1 text-xs font-medium text-ink-muted hover:bg-sunken hover:text-ink"
        >
          <span>{td("counts.title")}</span>
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`}
            aria-hidden="true"
          />
        </button>
      </div>
      {open && (
        <div className="w-full overflow-x-auto rounded-lg border border-border bg-surface p-2 shadow-sm">
          <table className="w-full border-collapse text-left text-xs tabular-nums">
            <caption className="sr-only">{td("counts.title")}</caption>
            <thead>
              <tr className="border-b border-border text-ink-muted">
                <th scope="col" className="px-2 py-1 font-semibold">
                  {td("counts.kind")}
                </th>
                <th scope="col" className="px-2 py-1 font-semibold">
                  {td("counts.total")}
                </th>
                <th scope="col" className="px-2 py-1 font-semibold">
                  {td("counts.undecided")}
                </th>
                <th scope="col" className="px-2 py-1 font-semibold">
                  {td("counts.accepted")}
                </th>
                <th scope="col" className="px-2 py-1 font-semibold">
                  {td("counts.edited")}
                </th>
                <th scope="col" className="px-2 py-1 font-semibold">
                  {td("counts.rejected")}
                </th>
                <th scope="col" className="px-2 py-1 font-semibold">
                  {td("counts.changed")}
                </th>
                <th scope="col" className="px-2 py-1 font-semibold">
                  {td("counts.decidedNotProposed")}
                </th>
              </tr>
            </thead>
            <tbody>
              {kinds.map((k) => {
                const c = counts[k];
                return (
                  <tr key={k} className="border-b border-border last:border-b-0">
                    <th scope="row" className="px-2 py-1 font-medium text-ink">
                      {td(`kinds.${k}`)}
                    </th>
                    <td className="px-2 py-1">{c.total}</td>
                    <td className="px-2 py-1">{c.undecided}</td>
                    <td className="px-2 py-1">{c.accepted}</td>
                    <td className="px-2 py-1">{c.edited}</td>
                    <td className="px-2 py-1">{c.rejected}</td>
                    <td className="px-2 py-1">{c.changed}</td>
                    <td className="px-2 py-1">{c.decided_not_proposed}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function FindingDecisionForm({
  proposal,
  runId,
  screen,
  access,
  anchor,
  onDirtyChange,
}: {
  proposal: Proposal;
  runId: string;
  screen: DecisionScreen;
  access: Extract<DecisionAccess, { mode: "decide" }>;
  anchor?: string;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const td = useTranslations("decisions");
  const actionFn = access.inlineAction ?? wrapLegacyAction(access.action);
  const [reason, setReason] = useState("");
  const [redecideOpen, setRedecideOpen] = useState(false);
  const [redecideChoice, setRedecideChoice] = useState<"accepted" | "rejected">("accepted");
  const [rejectOpen, setRejectOpen] = useState(false);

  const [state, formAction, isPending] = useActionState(
    async (prev: DecideActionState, formData: FormData): Promise<DecideActionState> => {
      const next = await actionFn(prev, formData);
      if (next.ok) {
        setReason("");
        setRedecideOpen(false);
        setRejectOpen(false);
        onDirtyChange?.(false);
      } else if (next.values?.reason !== undefined) {
        setReason(next.values.reason);
      }
      return next;
    },
    { ok: true },
  );

  const handleReasonChange = (val: string) => {
    setReason(val);
    onDirtyChange?.(val.trim() !== "");
  };

  const replacing = proposal.state === "decided";

  const hiddenInputs = (decision: Decision["decision"]) => (
    <>
      <input type="hidden" name="run_id" value={runId} />
      <input type="hidden" name="proposal_id" value={proposal.id} />
      <input type="hidden" name="screen" value={screen} />
      <input type="hidden" name="decision" value={decision} />
      {anchor && <input type="hidden" name="anchor" value={anchor} />}
    </>
  );

  const reasonTextarea = (
    <textarea
      name="reason"
      required
      rows={2}
      value={reason}
      onChange={(e) => handleReasonChange(e.target.value)}
      aria-label={td("reason")}
      placeholder={td("reason")}
      className={`w-full text-xs ${FIELD_BASE_CLASS}`}
    />
  );

  const acceptForm = (
    <form action={formAction} className="space-y-2">
      {hiddenInputs("accepted")}
      <button
        type="submit"
        disabled={isPending}
        className="inline-flex cursor-pointer items-center justify-center rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
      >
        {td("accept")}
      </button>
    </form>
  );

  const rejectForm = (
    <form action={formAction} className="space-y-2">
      {hiddenInputs("rejected")}
      {reasonTextarea}
      <button
        type="submit"
        disabled={isPending}
        className="inline-flex cursor-pointer items-center justify-center rounded-md border border-border-strong bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-60"
      >
        {td("reject")}
      </button>
    </form>
  );

  return (
    <div className="space-y-3 pt-2">
      {!state.ok && state.error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-fail-edge bg-fail-soft px-3 py-2 text-xs text-fail"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{td(`errors.${state.error}`)}</span>
        </div>
      )}

      {replacing ? (
        <div className="space-y-2">
          <button
            type="button"
            aria-expanded={redecideOpen}
            onClick={() => setRedecideOpen((o) => !o)}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border-strong bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-sunken"
          >
            <span>{td("redecide")}</span>
            <ChevronDown
              className={`h-3.5 w-3.5 transition-transform ${redecideOpen ? "rotate-180" : ""}`}
              aria-hidden="true"
            />
          </button>
          {redecideOpen && (
            <form action={formAction} className="space-y-2.5 rounded-lg border border-border bg-sunken p-3">
              {hiddenInputs(redecideChoice)}
              <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={td("redecide")}>
                <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1 text-xs font-medium text-ink">
                  <input
                    type="radio"
                    name="redecide_choice"
                    value="accepted"
                    checked={redecideChoice === "accepted"}
                    onChange={() => setRedecideChoice("accepted")}
                  />
                  <span>{td("accept")}</span>
                </label>
                <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1 text-xs font-medium text-ink">
                  <input
                    type="radio"
                    name="redecide_choice"
                    value="rejected"
                    checked={redecideChoice === "rejected"}
                    onChange={() => setRedecideChoice("rejected")}
                  />
                  <span>{td("reject")}</span>
                </label>
              </div>
              {reasonTextarea}
              <button
                type="submit"
                disabled={isPending}
                className={`inline-flex cursor-pointer items-center justify-center rounded-md px-3 py-1.5 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-60 ${
                  redecideChoice === "accepted"
                    ? "bg-accent text-on-accent hover:bg-accent-hover"
                    : "border border-border-strong bg-surface text-ink hover:bg-canvas"
                }`}
              >
                {redecideChoice === "accepted" ? td("accept") : td("reject")}
              </button>
            </form>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            {acceptForm}
            <button
              type="button"
              aria-expanded={rejectOpen}
              onClick={() => setRejectOpen((o) => !o)}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border-strong bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-sunken"
            >
              <span>{td("reject")}…</span>
              <ChevronDown
                className={`h-3.5 w-3.5 transition-transform ${rejectOpen ? "rotate-180" : ""}`}
                aria-hidden="true"
              />
            </button>
          </div>
          {rejectOpen && (
            <div className="rounded-lg border border-border bg-sunken p-3">{rejectForm}</div>
          )}
        </div>
      )}
    </div>
  );
}

/** Shared decision status, history, and `useActionState` accept/reject workspace for Findings & Draft. */
export function FindingDecisionPanel({
  proposal,
  runId,
  screen,
  access,
  anchor,
  headingLevel = "h4",
  embedded = false,
  onDirtyChange,
}: {
  proposal: Proposal | undefined;
  runId: string;
  screen: DecisionScreen;
  access: DecisionAccess;
  anchor?: string;
  headingLevel?: "h3" | "h4";
  embedded?: boolean;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const td = useTranslations("decisions");
  const tm = useTranslations("matrix");

  if (proposal === undefined) return null;

  const [latestDecision, ...earlierDecisions] = proposal.decisions;
  const Heading = headingLevel;

  return (
    <section
      className={
        embedded
          ? "space-y-3 border-t border-border pt-4"
          : "space-y-3 rounded-lg border border-border bg-surface p-3.5"
      }
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Heading className="m-0 text-xs font-bold tracking-wide text-ink-muted uppercase">
          {td("column")}
        </Heading>
        <DecisionStateBadge state={proposal.state} />
      </div>

      {latestDecision && (
        <div className="rounded-md border border-border bg-sunken p-2.5">
          <DecisionEntry td={td} tm={tm} d={latestDecision} />
        </div>
      )}

      {earlierDecisions.length > 0 && (
        <div className="space-y-1.5 border-t border-border pt-2.5">
          <div className="text-xs font-semibold text-ink-muted">{td("earlier")}</div>
          <ul className="m-0 list-none space-y-2 p-0">
            {earlierDecisions.map((d) => (
              <li key={d.id} className="rounded-md border border-border bg-sunken px-2.5 py-2">
                <DecisionEntry td={td} tm={tm} d={d} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {proposal.previous && (
        <div className="space-y-1 rounded-md border border-warn-edge bg-warn-soft p-2.5 text-xs text-warn">
          <div>{td("previous", { summary: decisionSummary(td, tm, proposal.previous) })}</div>
          {proposal.previous_class && (
            <div className="font-semibold">
              {td("previousClass", { class: tm(`classes.${proposal.previous_class}`) })}
            </div>
          )}
          {proposal.previous.reason && <div className="italic">{proposal.previous.reason}</div>}
        </div>
      )}

      {access.mode === "decide" && (
        <FindingDecisionForm
          key={`${proposal.id}-${proposal.state}-${proposal.decisions[0]?.id ?? 0}`}
          proposal={proposal}
          runId={runId}
          screen={screen}
          access={access}
          anchor={anchor}
          onDirtyChange={onDirtyChange}
        />
      )}
    </section>
  );
}
