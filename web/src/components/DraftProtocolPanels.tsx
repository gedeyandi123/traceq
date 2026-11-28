"use client";

import { AlertCircle, AlertTriangle, CheckCircle2, FileText } from "lucide-react";
import { useTranslations } from "next-intl";
import { useActionState, useEffect, useState } from "react";

import type {
  DraftMappingView,
  ProtocolRowView,
  ProtocolView,
  RowCandidate,
  RowFindingView,
  Value,
} from "@/api/client";
import type { ProtocolFormActionState } from "@/protocol/actions";
import type { Acceptance } from "@/protocol/form";
import type { ProtocolControls } from "./AssembledProtocolView";
import type { DecisionView } from "./Decisions";
import { FindingDecisionPanel } from "./FindingDecisionPanel";
import { formatWhen } from "./formatWhen";
import { formatValue } from "./MatrixTable";
import { EditDraftForm } from "./TestStepForms";
import { FIELD_BASE_CLASS } from "./ui/FormControls";
import { PdfCitationButton } from "./ui/PdfCitationModal";
import { DecisionStateBadge } from "./ui/StatusBadge";
import { SubmitButton } from "./ui/SubmitButton";

type T = ReturnType<typeof useTranslations<"protocol">>;

/** The drafted Acceptance Criterion as the edit form can start from it: only a shape a Test
 * Step can hold; a reading the form cannot hold (unjudgeable tolerance, free text, ambiguous) is
 * set by a human. Starting from null would drop a criterion the draft read. */
function formShape(
  v:
    | {
        type: string;
        min?: number | null;
        max?: number | null;
        min_exclusive?: boolean;
        max_exclusive?: boolean;
        nominal?: number;
        tolerance?: number;
        tolerance_unit?: string;
        unit?: string;
        value?: unknown;
        allowed?: readonly string[];
      }
    | null
    | undefined,
): Acceptance | null {
  if (v === null || v === undefined) return null;
  if (v.type === "range" && (v.min_exclusive === true || v.max_exclusive === true)) {
    return {
      type: "exclusive_range",
      min: v.min ?? null,
      max: v.max ?? null,
      min_exclusive: Boolean(v.min_exclusive),
      max_exclusive: Boolean(v.max_exclusive),
      unit: v.unit ?? "",
    };
  }
  if (v.type === "tolerance") {
    const unit = (v.unit ?? "").trim();
    const tolUnit = (v.tolerance_unit ?? "").trim();
    if (tolUnit !== "%" && (unit === "" || tolUnit !== unit)) return null;
    return {
      type: "tolerance",
      nominal: v.nominal ?? 0,
      tolerance: v.tolerance ?? 0,
      tolerance_unit: tolUnit,
      unit,
    };
  }
  if (v.type === "exclusive_range") return v as Acceptance;
  return v.type === "range" || v.type === "number" || v.type === "one_of" || v.type === "present"
    ? (v as Acceptance)
    : null;
}

const PILL = "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold";

/** "dev only" and "awaiting the practitioner's answer (#245)": every default of the draft flow
 * stands in for domain evidence a practitioner has not given (ADR 0010 and 0012, amended). */
export function DraftLabels({ t, note = false }: { t: T; note?: boolean }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5" data-testid="draft-labels">
      <span className={`${PILL} border-warn-edge bg-warn-soft text-warn`}>
        {t("draftFlow.devOnly")}
      </span>
      <span className={`${PILL} border-info-edge bg-info-soft text-info`}>
        {t("draftFlow.awaiting")}
      </span>
      {note && <span className="text-[11px] text-ink-muted">{t("draftFlow.labels")}</span>}
    </span>
  );
}

/** The label of a finding of a type no practitioner has reviewed. */
export function NotReviewedLabel({ t }: { t: T }) {
  return (
    <span className={`${PILL} border-warn-edge bg-warn-soft text-warn`}>
      {t("draftFlow.notReviewed")}
    </span>
  );
}

/** The draft the Protocol was pinned to and, when a newer revision arrived, the warning that
 * the Protocol does not follow it. */
export function DraftSourcePanel({ t, protocol }: { t: T; protocol: ProtocolView }) {
  const source = protocol.source;
  if (!source) return null;
  const latest = protocol.latest_draft_rev ?? source.rev;
  const behind = latest > source.rev;
  return (
    <section
      aria-labelledby="protocol-draft-source"
      className="space-y-2 rounded-lg border border-border bg-surface p-4 shadow-xs"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2
          id="protocol-draft-source"
          className="m-0 flex items-center gap-2 text-sm font-bold text-ink"
        >
          <FileText className="h-4 w-4 text-ink-muted" aria-hidden="true" />
          <span>{t("draftFlow.source.title")}</span>
        </h2>
        <DraftLabels t={t} />
      </div>
      <p className="m-0 text-xs break-all text-ink tabular-nums" data-testid="draft-source-line">
        {t("draftFlow.source.line", { doc: source.doc, rev: source.rev, hash: source.sha256 })}
      </p>
      <p className="m-0 text-xs text-ink-muted">{t("draftFlow.source.pinned")}</p>
      <p className="m-0 text-xs text-ink-muted tabular-nums">
        {t("draftFlow.source.latest", { latest })}
      </p>
      {behind && (
        <div
          data-testid="draft-behind"
          className="flex items-start gap-2 rounded-md border border-warn-edge bg-warn-soft px-3 py-2 text-xs font-medium text-warn"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{t("draftFlow.source.newer", { latest, rev: source.rev })}</span>
        </div>
      )}
    </section>
  );
}

type InlineAction = (
  prevState: ProtocolFormActionState,
  formData: FormData,
) => Promise<ProtocolFormActionState>;

function Feedback({
  t,
  state,
  saved,
  scope,
}: {
  t: T;
  state: ProtocolFormActionState;
  saved: string;
  scope?: "map" | "reason";
}) {
  if (!state.ok && state.error) {
    // The map and reason forms have their own words for 409 and 422; the rest is generic.
    const own =
      scope !== undefined && (state.error === "conflict" || state.error === "refused")
        ? t(`draftFlow.errors.${scope}.${state.error}`)
        : null;
    return (
      <p role="alert" className="m-0 flex items-start gap-1.5 text-xs text-fail">
        <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span>{own ?? t(`errors.${state.error}`)}</span>
      </p>
    );
  }
  if (state.ok && state.submittedAt) {
    return (
      <p role="status" className="m-0 flex items-center gap-1 text-xs text-pass">
        <CheckCircle2 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span>{saved}</span>
      </p>
    );
  }
  return null;
}

function MappingLine({ t, m }: { t: T; m: DraftMappingView }) {
  const when = useTranslations("decisions");
  return (
    <li className="text-[11px] text-ink-muted tabular-nums">
      {t("draftFlow.steps.mappedBy", {
        requirement: m.requirement,
        name: m.name,
        when: formatWhen(when, m.at),
      })}
    </li>
  );
}

function MapForm({
  t,
  protocolId,
  step,
  requirements,
  action,
}: {
  t: T;
  protocolId: number;
  step: string;
  requirements: readonly string[];
  action: InlineAction;
}) {
  const [state, formAction] = useActionState(action, { ok: false });
  // The form goes once the step is mapped: focus moves to the step's own card, which stays.
  useEffect(() => {
    if (state.ok && state.submittedAt) document.getElementById(`draft-step-${step}`)?.focus();
  }, [state, step]);
  return (
    <form action={formAction} className="space-y-2" aria-label={t("draftFlow.steps.mapTo")}>
      <input type="hidden" name="protocol_id" value={protocolId} />
      <input type="hidden" name="step" value={step} />
      <label className="block space-y-1 text-xs font-medium text-ink">
        <span>{t("draftFlow.steps.mapTo")}</span>
        <select name="requirement" required defaultValue="" className={`w-full text-xs ${FIELD_BASE_CLASS}`}>
          <option value="">{t("draftFlow.steps.choose")}</option>
          {requirements.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </label>
      <Feedback t={t} state={state} saved={t("form.saved")} scope="map" />
      <SubmitButton variant="soft">{t("draftFlow.steps.save")}</SubmitButton>
    </form>
  );
}

/** Every Test Step of the pinned draft: the ones that stand for no requirement are unusable
 * until a person maps one to exactly one requirement or rejects it. */
export function DraftStepsPanel({
  t,
  protocol,
  decisions,
  controls,
}: {
  t: T;
  protocol: ProtocolView;
  decisions: DecisionView;
  controls: ProtocolControls;
}) {
  const steps = protocol.draft_steps ?? [];
  const requirements = (protocol.rows ?? []).map((r) => r.requirement);
  return (
    <section aria-labelledby="draft-steps" className="space-y-3">
      <div>
        <h2 id="draft-steps" className="m-0 text-sm font-bold text-ink">
          {t("draftFlow.steps.title")}
        </h2>
        <p className="m-0 mt-0.5 text-xs text-ink-muted">{t("draftFlow.steps.note")}</p>
      </div>
      {steps.length === 0 ? (
        <p className="m-0 text-xs text-ink-muted">{t("draftFlow.steps.empty")}</p>
      ) : (
        <ul className="m-0 list-none space-y-2 p-0">
          {steps.map((e) => (
            <li
              key={e.proposal.id}
              id={`draft-step-${e.step.id}`}
              tabIndex={-1}
              data-testid={`draft-step-${e.step.id}`}
              className={`space-y-2 rounded-lg border p-3 text-xs ${
                e.resolved ? "border-border bg-surface" : "border-fail-edge bg-fail-soft/30"
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-mono font-semibold text-ink">{e.step.id}</span>
                <span
                  className={`${PILL} ${
                    e.resolved
                      ? "border-pass-edge bg-pass-soft text-pass"
                      : "border-fail-edge bg-fail-soft text-fail"
                  }`}
                >
                  {e.resolved
                    ? e.requirement
                      ? t("draftFlow.steps.resolved", { requirement: e.requirement })
                      : t("draftFlow.steps.resolvedNone")
                    : t("draftFlow.steps.unresolved")}
                </span>
              </div>
              {e.step.description && <p className="m-0 text-ink">{e.step.description}</p>}
              {e.step.not_read && (
                <p className="m-0 text-ink-muted">
                  {t("draftFlow.steps.notRead", { why: e.step.not_read })}
                </p>
              )}
              {e.mappings.length > 0 && (
                <ul className="m-0 list-disc space-y-0.5 pl-4">
                  {e.mappings.map((m) => (
                    <MappingLine key={m.version} t={t} m={m} />
                  ))}
                </ul>
              )}
              {!e.resolved && controls?.mapInline && (
                <MapForm
                  t={t}
                  protocolId={protocol.id}
                  step={e.step.id}
                  requirements={requirements}
                  action={controls.mapInline}
                />
              )}
              {!e.resolved && (
                <FindingDecisionPanel
                  proposal={e.proposal}
                  runId={protocol.run_id}
                  screen="protocol"
                  access={decisions.access}
                  embedded
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ReasonForm({
  t,
  protocolId,
  f,
  action,
  onDirtyChange,
}: {
  t: T;
  protocolId: number;
  f: RowFindingView;
  action: InlineAction;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const when = useTranslations("decisions");
  const [reason, setReason] = useState("");
  const [state, formAction] = useActionState(
    async (prev: ProtocolFormActionState, form: FormData) => {
      const next = await action(prev, form);
      if (next.ok) {
        setReason("");
        onDirtyChange?.(false);
      }
      return next;
    },
    { ok: false } as ProtocolFormActionState,
  );
  return (
    <div className="space-y-2 rounded-md border border-warn-edge bg-warn-soft/40 p-2.5">
      <div className="text-xs font-bold text-ink">{t("draftFlow.findings.reasonTitle")}</div>
      <p className="m-0 text-xs text-ink-muted">{t("draftFlow.findings.reasonHint")}</p>
      {f.reasons.length > 0 && (
        <ul className="m-0 list-none space-y-1 p-0 text-xs text-ink">
          {f.reasons.map((r) => (
            <li key={r.id}>
              <div className="italic">{r.reason}</div>
              <div className="text-[11px] text-ink-muted tabular-nums">
                {t("draftFlow.findings.reasonBy", { name: r.name, when: formatWhen(when, r.at) })}
              </div>
            </li>
          ))}
        </ul>
      )}
      <form action={formAction} className="space-y-2">
        <input type="hidden" name="protocol_id" value={protocolId} />
        <input type="hidden" name="proposal_id" value={f.proposal.id} />
        <textarea
          name="reason"
          required
          rows={2}
          value={reason}
          onChange={(e) => {
            setReason(e.target.value);
            onDirtyChange?.(e.target.value.trim() !== "");
          }}
          aria-label={t("draftFlow.findings.reasonLabel")}
          placeholder={t("draftFlow.findings.reasonLabel")}
          className={`w-full text-xs ${FIELD_BASE_CLASS}`}
        />
        <Feedback t={t} state={state} saved={t("form.saved")} scope="reason" />
        <SubmitButton variant="soft">{t("draftFlow.findings.reasonSave")}</SubmitButton>
      </form>
    </div>
  );
}

function Candidate({
  t,
  c,
  row,
  runId,
  protocolId,
  decisions,
  controls,
  onDirtyChange,
}: {
  t: T;
  c: RowCandidate;
  row: ProtocolRowView;
  runId: string;
  protocolId: number;
  decisions: DecisionView;
  controls: ProtocolControls;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const m = useTranslations("matrix");
  const when = useTranslations("decisions");
  const stepAccepted = c.proposal.decisions[0]?.decision === "accepted";
  return (
    <div
      data-testid={`candidate-${c.step.id}`}
      className="space-y-3 rounded-lg border border-border bg-sunken p-3.5"
    >
      <div className="space-y-1.5 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono font-semibold text-ink">{c.step.id}</span>
          {c.accepted && (
            <span className={`${PILL} border-pass-edge bg-pass-soft text-pass`}>
              {t("draftFlow.candidates.ready")}
            </span>
          )}
        </div>
        <div className="font-medium text-ink">{c.step.description}</div>
        {c.step.method && (
          <div className="text-ink-muted">
            {t("method")}: {c.step.method}
          </div>
        )}
        {c.step.instrument && (
          <div className="text-ink-muted">
            {t("instrument")}: {c.step.instrument}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-1.5 text-ink">
          {c.criterion ? (
            <>
              <span>
                {t("ac")}: {c.criterion.value ? formatValue(m, c.criterion.value) : c.criterion.printed}
              </span>
              <PdfCitationButton runId={runId} cite={c.criterion.citation} compact />
            </>
          ) : (
            <span className="text-ink-muted">{t("draftFlow.candidates.noCriterion")}</span>
          )}
        </div>
        {c.mapping && (
          <div className="text-[11px] text-ink-muted tabular-nums">
            {t("draftFlow.candidates.mappedBy", {
              name: c.mapping.name,
              when: formatWhen(when, c.mapping.at),
            })}
          </div>
        )}
      </div>

      <div className="space-y-1">
        <div className="text-[11px] font-bold tracking-wide text-ink-muted uppercase">
          {t("draftFlow.candidates.stepDecision")}
        </div>
        <FindingDecisionPanel
          proposal={c.proposal}
          runId={runId}
          screen="protocol"
          access={decisions.access}
          anchor={`row-${row.requirement}`}
          onDirtyChange={onDirtyChange}
          embedded
        />
      </div>

      {c.criterion_proposal && stepAccepted && (
        <div className="space-y-1">
          <div className="text-[11px] font-bold tracking-wide text-ink-muted uppercase">
            {t("draftFlow.candidates.criterionDecision")}
          </div>
          <FindingDecisionPanel
            proposal={c.criterion_proposal}
            runId={runId}
            screen="protocol"
            access={decisions.access}
            anchor={`row-${row.requirement}`}
            onDirtyChange={onDirtyChange}
            embedded
          />
        </div>
      )}

      {controls !== null && row.test_step?.origin !== "written" && (
        <EditDraftForm
          t={t}
          proposalId={c.proposal.id}
          start={{
            description: c.step.description,
            method: c.step.method,
            instrument: c.step.instrument,
            acceptance: formShape(c.criterion?.value),
          }}
          runId={runId}
          protocolId={protocolId}
          edit={controls.edit}
          editInline={controls.editInline}
          onDirtyChange={onDirtyChange}
        />
      )}
    </div>
  );
}

function Finding({
  t,
  f,
  row,
  runId,
  protocolId,
  decisions,
  controls,
  onDirtyChange,
}: {
  t: T;
  f: RowFindingView;
  row: ProtocolRowView;
  runId: string;
  protocolId: number;
  decisions: DecisionView;
  controls: ProtocolControls;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const d = useTranslations("draft");
  const accepted = f.proposal.decisions[0]?.decision === "accepted";
  const needsReason = accepted && !row.changed;
  return (
    <div
      data-testid={`finding-${f.proposal.id}`}
      className="space-y-3 rounded-md border-l-2 border-fail bg-sunken/60 p-3"
    >
      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-bold text-fail">{d(`types.${f.finding.type}`)}</span>
          {f.finding.label && <NotReviewedLabel t={t} />}
          <DraftLabels t={t} />
        </div>
        {f.finding.test_step && (
          <div className="text-[11px] text-ink-muted tabular-nums">
            {t("draftFlow.findings.location", { step: f.finding.test_step })}
          </div>
        )}
        <p lang="en" className="m-0 text-xs leading-relaxed text-ink">
          {f.finding.detail}
        </p>
        <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
          {f.finding.citations.map((c, i) => (
            <li key={`${c.doc}/${c.rev}/${c.page}/${i}`}>
              <PdfCitationButton runId={runId} cite={c} compact />
            </li>
          ))}
        </ul>
        <DecisionStateBadge state={f.proposal.state} />
      </div>
      <FindingDecisionPanel
        proposal={f.proposal}
        runId={runId}
        screen="protocol"
        access={decisions.access}
        anchor={`row-${row.requirement}`}
        onDirtyChange={onDirtyChange}
        embedded
      />
      {needsReason && controls?.giveReasonInline && (
        <ReasonForm
          t={t}
          protocolId={protocolId}
          f={f}
          action={controls.giveReasonInline}
          onDirtyChange={onDirtyChange}
        />
      )}
    </div>
  );
}

/** The draft's candidate Test Steps and findings of one row of a Protocol started from the draft. */
export function DraftRowSections({
  t,
  row,
  runId,
  protocolId,
  decisions,
  controls,
  onDirtyChange,
}: {
  t: T;
  row: ProtocolRowView;
  runId: string;
  protocolId: number;
  decisions: DecisionView;
  controls: ProtocolControls;
  onDirtyChange: (dirty: boolean) => void;
}) {
  return (
    <>
      {row.candidates.length > 0 && (
        <section className="space-y-3" aria-label={t("draftFlow.candidates.title")}>
          <h3 className="m-0 text-xs font-bold tracking-wide text-ink-muted uppercase">
            {t("draftFlow.candidates.title")}
          </h3>
          {row.candidates.map((c) => (
            <Candidate
              key={c.proposal.id}
              t={t}
              c={c}
              row={row}
              runId={runId}
              protocolId={protocolId}
              decisions={decisions}
              controls={controls}
              onDirtyChange={onDirtyChange}
            />
          ))}
        </section>
      )}
      {row.findings.length > 0 && (
        <section className="space-y-3" aria-label={t("draftFlow.findings.title")}>
          <h3 className="m-0 text-xs font-bold tracking-wide text-ink-muted uppercase">
            {t("draftFlow.findings.title")}
          </h3>
          {row.findings.map((f) => (
            <Finding
              key={f.proposal.id}
              t={t}
              f={f}
              row={row}
              runId={runId}
              protocolId={protocolId}
              decisions={decisions}
              controls={controls}
              onDirtyChange={onDirtyChange}
            />
          ))}
        </section>
      )}
    </>
  );
}
