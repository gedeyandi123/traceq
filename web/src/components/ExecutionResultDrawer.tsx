"use client";

import { AlertCircle, Plus, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useActionState, useState } from "react";

import type { AttemptView, DeviationView, ExecutionRowView } from "@/api/client";
import type { ExecutionActionState } from "@/execution/actions";
import { formatValue } from "./MatrixTable";
import { Drawer } from "./ui/Drawer";
import { SubmitButton } from "./ui/SubmitButton";
import { Button } from "./ui/ui";

type ResultAction = (
  prevState: ExecutionActionState,
  formData: FormData,
) => Promise<ExecutionActionState>;

export type ResultDrawerMode =
  | { kind: "record" }
  | { kind: "correct"; attempt: AttemptView }
  | { kind: "retest"; openDeviations: DeviationView[] };

const INITIAL_STATE: ExecutionActionState = { ok: true };

type InstrumentDraft = {
  key: number;
  identifier: string;
  dueDate: string;
};

type EvidenceDraft = {
  key: number;
  value: string;
};

/** Drawer form to record, correct, or retest an attempt on a Test Step row (ADR 0013, #272, #277).
 * Uses React 19 `useActionState` with controlled inputs so 422/409 errors preserve typed text. */
export function ExecutionResultDrawer({
  executionId,
  row,
  mode = { kind: "record" },
  open,
  onOpenChange,
  recordAction,
}: {
  executionId: number;
  row: ExecutionRowView;
  mode?: ResultDrawerMode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  recordAction: ResultAction;
}) {
  const t = useTranslations("execution");
  const m = useTranslations("matrix");
  const step = row.test_step;
  const seed = mode.kind === "correct" ? mode.attempt.latest : null;

  const [outcomeKind, setOutcomeKind] = useState<"value" | "not_performable">(
    seed?.outcome_kind ?? "value",
  );
  const [notPerformableReason, setNotPerformableReason] = useState(
    seed?.not_performable_reason ?? "",
  );
  const [numericValue, setNumericValue] = useState(
    seed?.value?.type === "number" ? String(seed.value.value) : "",
  );
  const [oneOfChoice, setOneOfChoice] = useState(() => {
    if (seed?.value?.type === "one_of") {
      return seed.value.not_one_of ? "__not_one_of__" : seed.value.value;
    }
    return step?.acceptance.type === "one_of" ? (step.acceptance.allowed[0] ?? "") : "";
  });
  const [oneOfObserved, setOneOfObserved] = useState(
    seed?.value?.type === "one_of" && seed.value.not_one_of ? seed.value.value : "",
  );
  const [presentValue, setPresentValue] = useState<"true" | "false">(
    seed?.value?.type === "present" ? (seed.value.value ? "true" : "false") : "true",
  );

  const needsInstrument = step !== null && (step.instrument?.trim() ?? "") !== "";
  const [instrumentMode, setInstrumentMode] = useState<"calibrated" | "none">(
    seed?.no_calibrated_instrument_reason ? "none" : "calibrated",
  );
  const [instruments, setInstruments] = useState<InstrumentDraft[]>(() => {
    if (seed && seed.instruments.length > 0) {
      return seed.instruments.map((inst, idx) => ({
        key: idx + 1,
        identifier: inst.identifier,
        dueDate: inst.calibration_due_date,
      }));
    }
    return [{ key: 1, identifier: step?.instrument ?? "", dueDate: "" }];
  });
  const [noInstReason, setNoInstReason] = useState(seed?.no_calibrated_instrument_reason ?? "");
  const [evidenceItems, setEvidenceItems] = useState<EvidenceDraft[]>(() =>
    seed
      ? seed.evidence.map((value, idx) => ({ key: 100 + idx, value }))
      : [],
  );
  const [observation, setObservation] = useState(seed?.observation ?? "");
  const [reasonForChange, setReasonForChange] = useState("");
  const [retestReason, setRetestReason] = useState("");
  const [selectedDeviationId, setSelectedDeviationId] = useState<string>(() =>
    mode.kind === "retest" && mode.openDeviations[0] ? String(mode.openDeviations[0].id) : "",
  );
  const [nextKey, setNextKey] = useState(200);

  const [state, formAction] = useActionState(async (prev: ExecutionActionState, fd: FormData) => {
    const res = await recordAction(prev, fd);
    if (res.ok) {
      onOpenChange(false);
    }
    return res;
  }, INITIAL_STATE);

  if (!step) return null;

  const ac = step.acceptance;

  const addInstrumentRow = () => {
    setInstruments((prev) => [...prev, { key: nextKey, identifier: "", dueDate: "" }]);
    setNextKey((k) => k + 1);
  };

  const removeInstrumentRow = (key: number) => {
    setInstruments((prev) => prev.filter((item) => item.key !== key));
  };

  const addEvidenceRow = () => {
    setEvidenceItems((prev) => [...prev, { key: nextKey, value: "" }]);
    setNextKey((k) => k + 1);
  };

  const removeEvidenceRow = (key: number) => {
    setEvidenceItems((prev) => prev.filter((item) => item.key !== key));
  };

  const drawerTitle =
    mode.kind === "correct"
      ? t("correctAttemptTitle", {
          requirement: row.requirement,
          attemptNumber: mode.attempt.attempt_number,
        })
      : mode.kind === "retest"
        ? t("retestRowTitle", { requirement: row.requirement })
        : t("recordResultTitle", { requirement: row.requirement });

  const submitLabel =
    mode.kind === "correct"
      ? t("submitCorrection")
      : mode.kind === "retest"
        ? t("submitRetest")
        : t("submitResult");

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title={drawerTitle}
      description={step.description}
    >
      <form action={formAction} className="space-y-4">
        <input type="hidden" name="execution_id" value={executionId} />
        <input type="hidden" name="requirement" value={row.requirement} />
        <input type="hidden" name="acceptance_type" value={ac.type} />
        <input type="hidden" name="outcome_kind" value={outcomeKind} />
        {mode.kind === "correct" && (
          <input type="hidden" name="attempt_number" value={mode.attempt.attempt_number} />
        )}
        {needsInstrument && (
          <input type="hidden" name="instrument_mode" value={instrumentMode} />
        )}

        {!state.ok && state.error && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-fail-edge bg-fail-soft px-3 py-2 text-xs text-fail"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{state.detail ?? t(`errors.${state.error}`)}</span>
          </div>
        )}

        <div className="rounded-md border border-border bg-sunken px-3 py-2.5 text-xs">
          <div className="font-semibold text-ink">{step.method}</div>
          <div className="mt-1 text-ink-muted tabular-nums">
            {t("colAcceptance")}: <span className="font-medium text-ink">{formatValue(m, ac)}</span>
          </div>
        </div>

        <fieldset className="space-y-2 border-0 p-0">
          <legend className="text-xs font-bold text-ink">{t("outcomeKind")}</legend>
          <div className="flex flex-wrap gap-3 text-xs">
            <label className="inline-flex cursor-pointer items-center gap-1.5">
              <input
                type="radio"
                name="outcome_kind_radio"
                checked={outcomeKind === "value"}
                onChange={() => setOutcomeKind("value")}
              />
              <span>{t("outcomeValue")}</span>
            </label>
            <label className="inline-flex cursor-pointer items-center gap-1.5">
              <input
                type="radio"
                name="outcome_kind_radio"
                checked={outcomeKind === "not_performable"}
                onChange={() => setOutcomeKind("not_performable")}
              />
              <span>{t("outcomeNotPerformable")}</span>
            </label>
          </div>
        </fieldset>

        {outcomeKind === "not_performable" ? (
          <div className="space-y-1">
            <label
              htmlFor={`not-perf-${row.requirement}`}
              className="block text-xs font-semibold text-ink"
            >
              {t("notPerformableReason")}
            </label>
            <textarea
              id={`not-perf-${row.requirement}`}
              name="not_performable_reason"
              rows={2}
              required
              value={notPerformableReason}
              onChange={(e) => setNotPerformableReason(e.target.value)}
              className="w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-ink"
            />
          </div>
        ) : (
          <div className="space-y-2">
            {(ac.type === "number" || ac.type === "range") && (
              <div className="space-y-1">
                <label
                  htmlFor={`num-val-${row.requirement}`}
                  className="block text-xs font-semibold text-ink"
                >
                  {t("observedValue")}
                </label>
                <div className="flex items-center gap-2">
                  <input
                    id={`num-val-${row.requirement}`}
                    name="numeric_value"
                    type="number"
                    step="any"
                    required
                    value={numericValue}
                    onChange={(e) => setNumericValue(e.target.value)}
                    className="w-44 rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-ink tabular-nums"
                  />
                  <span
                    data-testid="ac-unit-label"
                    className="rounded border border-border bg-sunken px-2 py-1 text-xs font-medium text-ink-muted"
                  >
                    {ac.unit}
                  </span>
                </div>
              </div>
            )}

            {ac.type === "one_of" && (
              <div className="space-y-2">
                <fieldset className="space-y-1.5 border-0 p-0">
                  <legend className="text-xs font-semibold text-ink">{t("observedValue")}</legend>
                  <div className="flex flex-col gap-1.5 text-xs">
                    {ac.allowed.map((opt) => (
                      <label key={opt} className="inline-flex cursor-pointer items-center gap-1.5">
                        <input
                          type="radio"
                          name="one_of_choice"
                          value={opt}
                          checked={oneOfChoice === opt}
                          onChange={() => setOneOfChoice(opt)}
                        />
                        <span>{opt}</span>
                      </label>
                    ))}
                    <label className="inline-flex cursor-pointer items-center gap-1.5">
                      <input
                        type="radio"
                        name="one_of_choice"
                        value="__not_one_of__"
                        checked={oneOfChoice === "__not_one_of__"}
                        onChange={() => setOneOfChoice("__not_one_of__")}
                      />
                      <span>{t("oneOfNotListed")}</span>
                    </label>
                  </div>
                </fieldset>
                {oneOfChoice === "__not_one_of__" && (
                  <div className="space-y-1">
                    <label
                      htmlFor={`one-of-obs-${row.requirement}`}
                      className="block text-xs font-semibold text-ink"
                    >
                      {t("oneOfObserved")}
                    </label>
                    <input
                      id={`one-of-obs-${row.requirement}`}
                      name="one_of_observed"
                      type="text"
                      required
                      value={oneOfObserved}
                      onChange={(e) => setOneOfObserved(e.target.value)}
                      className="w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-ink"
                    />
                  </div>
                )}
              </div>
            )}

            {ac.type === "present" && (
              <fieldset className="space-y-1.5 border-0 p-0">
                <legend className="text-xs font-semibold text-ink">{t("presentChoice")}</legend>
                <div className="flex flex-wrap gap-3 text-xs">
                  <label className="inline-flex cursor-pointer items-center gap-1.5">
                    <input
                      type="radio"
                      name="present_value"
                      value="true"
                      checked={presentValue === "true"}
                      onChange={() => setPresentValue("true")}
                    />
                    <span>{t("presentTrue")}</span>
                  </label>
                  <label className="inline-flex cursor-pointer items-center gap-1.5">
                    <input
                      type="radio"
                      name="present_value"
                      value="false"
                      checked={presentValue === "false"}
                      onChange={() => setPresentValue("false")}
                    />
                    <span>{t("presentFalse")}</span>
                  </label>
                </div>
              </fieldset>
            )}
          </div>
        )}

        {needsInstrument && (
          <fieldset className="space-y-2 rounded-md border border-border p-3">
            <legend className="px-1 text-xs font-bold text-ink">{t("instrumentsTitle")}</legend>
            <div className="flex flex-col gap-1.5 text-xs">
              <label className="inline-flex cursor-pointer items-center gap-1.5">
                <input
                  type="radio"
                  name="instrument_mode_radio"
                  checked={instrumentMode === "calibrated"}
                  onChange={() => setInstrumentMode("calibrated")}
                />
                <span>{t("useCalibratedInstruments")}</span>
              </label>
              <label className="inline-flex cursor-pointer items-center gap-1.5">
                <input
                  type="radio"
                  name="instrument_mode_radio"
                  checked={instrumentMode === "none"}
                  onChange={() => setInstrumentMode("none")}
                />
                <span>{t("noCalibratedInstrument")}</span>
              </label>
            </div>

            {instrumentMode === "calibrated" ? (
              <div className="space-y-2 pt-1">
                {instruments.map((inst, idx) => (
                  <div key={inst.key} className="flex flex-wrap items-end gap-2">
                    <div className="min-w-[140px] flex-1 space-y-1">
                      <label
                        htmlFor={`inst-id-${inst.key}`}
                        className="block text-[11px] font-medium text-ink-muted"
                      >
                        {t("instrumentId")}
                      </label>
                      <input
                        id={`inst-id-${inst.key}`}
                        name="instrument_id"
                        type="text"
                        required
                        value={inst.identifier}
                        onChange={(e) => {
                          const v = e.target.value;
                          setInstruments((prev) =>
                            prev.map((p) => (p.key === inst.key ? { ...p, identifier: v } : p)),
                          );
                        }}
                        className="w-full rounded-md border border-border-strong bg-surface px-2 py-1 text-xs text-ink"
                      />
                    </div>
                    <div className="space-y-1">
                      <label
                        htmlFor={`inst-due-${inst.key}`}
                        className="block text-[11px] font-medium text-ink-muted"
                      >
                        {t("calibrationDueDate")}
                      </label>
                      <input
                        id={`inst-due-${inst.key}`}
                        name="instrument_due"
                        type="date"
                        required
                        value={inst.dueDate}
                        onChange={(e) => {
                          const v = e.target.value;
                          setInstruments((prev) =>
                            prev.map((p) => (p.key === inst.key ? { ...p, dueDate: v } : p)),
                          );
                        }}
                        className="rounded-md border border-border-strong bg-surface px-2 py-1 text-xs text-ink tabular-nums"
                      />
                    </div>
                    {idx > 0 && (
                      <Button
                        type="button"
                        variant="quiet"
                        aria-label={t("removeInstrument")}
                        onClick={() => removeInstrumentRow(inst.key)}
                      >
                        <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                      </Button>
                    )}
                  </div>
                ))}
                <Button type="button" variant="soft" onClick={addInstrumentRow}>
                  <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{t("addInstrument")}</span>
                </Button>
              </div>
            ) : (
              <div className="space-y-1 pt-1">
                <label
                  htmlFor={`no-inst-${row.requirement}`}
                  className="block text-xs font-semibold text-ink"
                >
                  {t("noCalibratedInstrumentReason")}
                </label>
                <textarea
                  id={`no-inst-${row.requirement}`}
                  name="no_calibrated_instrument_reason"
                  rows={2}
                  required
                  value={noInstReason}
                  onChange={(e) => setNoInstReason(e.target.value)}
                  className="w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-ink"
                />
              </div>
            )}
          </fieldset>
        )}

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-ink">{t("evidenceTitle")}</span>
            <Button type="button" variant="quiet" onClick={addEvidenceRow}>
              <Plus className="h-3.5 w-3.5" aria-hidden="true" />
              <span>{t("addEvidence")}</span>
            </Button>
          </div>
          {evidenceItems.map((ev) => (
            <div key={ev.key} className="flex items-center gap-2">
              <input
                name="evidence_ref"
                type="text"
                aria-label={t("evidenceTitle")}
                placeholder={t("evidencePlaceholder")}
                value={ev.value}
                onChange={(e) => {
                  const v = e.target.value;
                  setEvidenceItems((prev) =>
                    prev.map((p) => (p.key === ev.key ? { ...p, value: v } : p)),
                  );
                }}
                className="flex-1 rounded-md border border-border-strong bg-surface px-2.5 py-1 text-xs text-ink"
              />
              <Button
                type="button"
                variant="quiet"
                aria-label={t("removeEvidence")}
                onClick={() => removeEvidenceRow(ev.key)}
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
            </div>
          ))}
        </div>

        <div className="space-y-1">
          <label
            htmlFor={`obs-${row.requirement}`}
            className="block text-xs font-semibold text-ink"
          >
            {t("observation")}
          </label>
          <textarea
            id={`obs-${row.requirement}`}
            name="observation"
            rows={2}
            value={observation}
            onChange={(e) => setObservation(e.target.value)}
            className="w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-ink"
          />
        </div>

        {mode.kind === "correct" && (
          <div className="space-y-1">
            <label
              htmlFor={`rfc-${row.requirement}`}
              className="block text-xs font-semibold text-ink"
            >
              {t("reasonForChangeLabel")}
            </label>
            <textarea
              id={`rfc-${row.requirement}`}
              name="reason_for_change"
              rows={2}
              required
              placeholder={t("reasonForChangePlaceholder")}
              value={reasonForChange}
              onChange={(e) => setReasonForChange(e.target.value)}
              className="w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-ink"
            />
          </div>
        )}

        {mode.kind === "retest" && (
          <div className="space-y-3 rounded-md border border-border bg-sunken p-3">
            <div className="space-y-1">
              <label
                htmlFor={`retest-dev-${row.requirement}`}
                className="block text-xs font-semibold text-ink"
              >
                {t("retestDeviationLabel")}
              </label>
              <select
                id={`retest-dev-${row.requirement}`}
                name="deviation_id"
                required
                value={selectedDeviationId}
                onChange={(e) => setSelectedDeviationId(e.target.value)}
                className="w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-ink"
              >
                {mode.openDeviations.map((d) => (
                  <option key={d.id} value={String(d.id)}>
                    {t("retestDeviationItem", {
                      number: d.deviation_number,
                      description: d.description,
                    })}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label
                htmlFor={`retest-reason-${row.requirement}`}
                className="block text-xs font-semibold text-ink"
              >
                {t("retestReasonLabel")}
              </label>
              <textarea
                id={`retest-reason-${row.requirement}`}
                name="retest_reason"
                rows={2}
                required
                placeholder={t("retestReasonPlaceholder")}
                value={retestReason}
                onChange={(e) => setRetestReason(e.target.value)}
                className="w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-ink"
              />
            </div>
          </div>
        )}

        <div className="flex justify-end border-t border-border pt-3">
          <SubmitButton variant="primary">{submitLabel}</SubmitButton>
        </div>
      </form>
    </Drawer>
  );
}
