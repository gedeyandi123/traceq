"use client";

import { AlertCircle, CheckCircle2, ChevronDown, History } from "lucide-react";
import { useTranslations } from "next-intl";
import { useActionState, useState } from "react";

import type { ProtocolRowView, RowDraft, Value } from "@/api/client";
import type { components } from "@/api/schema";
import type { ProtocolFormActionState } from "@/protocol/actions";
import { SHAPES, type Acceptance } from "@/protocol/form";
import { AcShapeFields } from "./AcShapeFields";
import { formatWhen } from "./formatWhen";
import { formatValue } from "./MatrixTable";

type T = ReturnType<typeof useTranslations<"protocol">>;
type MatrixT = ReturnType<typeof useTranslations<"matrix">>;
type Version = components["schemas"]["WrittenVersionView"];
type Action = (formData: FormData) => void | Promise<void>;
type InlineAction = (
  prevState: ProtocolFormActionState,
  formData: FormData,
) => Promise<ProtocolFormActionState>;

/** What a form starts from: description, method, instrument and an Acceptance Criterion in
 * one of the four shapes, or none. */
type Start = {
  description: string;
  method: string;
  instrument?: string | null;
  acceptance: Acceptance | null;
};

/** A drafted Acceptance Criterion as a form can start from it: free text is not one of the
 * four shapes, so the human sets it. */
function shaped(v: Value | null | undefined): Acceptance | null {
  if (!v || v.type === "text") return null;
  return v;
}

function wrapLegacyAction(action: Action): InlineAction {
  return async (_prev, formData) => {
    await action(formData);
    return { ok: true, submittedAt: Date.now() };
  };
}

const TEXTAREA_CLASS =
  "w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none";

const INPUT_CLASS =
  "w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none";

/** The fields of a Test Step: description, method, instrument, and the Acceptance Criterion
 * as one of four shapes with its values. */
function Fields({
  t,
  id,
  start,
  onDirty,
}: {
  t: T;
  id: string;
  start: Start | null;
  onDirty?: () => void;
}) {
  const a = start?.acceptance ?? null;
  const [description, setDescription] = useState(start?.description ?? "");
  const [method, setMethod] = useState(start?.method ?? "");
  const [instrument, setInstrument] = useState(start?.instrument ?? "");
  return (
    <div className="space-y-2.5">
      <label className="block space-y-1 text-xs font-medium text-ink">
        <span>{t("description")}</span>
        <textarea
          name="description"
          required
          rows={2}
          value={description}
          onChange={(e) => {
            setDescription(e.target.value);
            onDirty?.();
          }}
          className={TEXTAREA_CLASS}
        />
      </label>
      <label className="block space-y-1 text-xs font-medium text-ink">
        <span>{t("method")}</span>
        <textarea
          name="method"
          required
          rows={2}
          value={method}
          onChange={(e) => {
            setMethod(e.target.value);
            onDirty?.();
          }}
          className={TEXTAREA_CLASS}
        />
      </label>
      <label className="block space-y-1 text-xs font-medium text-ink">
        <span>{t("instrument")}</span>
        <input
          name="instrument"
          value={instrument}
          onChange={(e) => {
            setInstrument(e.target.value);
            onDirty?.();
          }}
          className={INPUT_CLASS}
        />
      </label>
      <AcShapeFields
        id={id}
        initialShape={a?.type ?? ""}
        initialMin={a?.type === "range" ? (a.min ?? "") : ""}
        initialMax={a?.type === "range" ? (a.max ?? "") : ""}
        initialValue={a?.type === "number" ? a.value : ""}
        initialUnit={a?.type === "range" || a?.type === "number" ? a.unit : ""}
        initialAllowed={a?.type === "one_of" ? a.allowed.join("; ") : ""}
        shapes={SHAPES.map((shape) => ({ value: shape, label: t(`form.shapes.${shape}`) }))}
        labels={{
          legend: t("ac"),
          shape: t("form.shape"),
          chooseShape: t("form.chooseShape"),
          min: t("form.min"),
          max: t("form.max"),
          value: t("form.value"),
          unit: t("form.unit"),
          allowed: t("form.allowed"),
          hint: t("form.hint"),
        }}
        onDirty={onDirty}
      />
    </div>
  );
}

function Hidden({ runId, protocolId }: { runId: string; protocolId: number }) {
  return (
    <>
      <input type="hidden" name="run_id" value={runId} />
      <input type="hidden" name="protocol_id" value={protocolId} />
    </>
  );
}

function ActionFeedback({ t, state }: { t: T; state: ProtocolFormActionState }) {
  if (!state.ok && state.error) {
    return (
      <div
        role="alert"
        className="flex items-start gap-2 rounded-md border border-fail-edge bg-fail-soft px-3 py-2 text-xs text-fail"
      >
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <span>{t(`errors.${state.error}`)}</span>
      </div>
    );
  }
  if (state.ok && state.submittedAt) {
    return (
      <div
        role="status"
        className="flex items-center gap-2 rounded-md border border-pass-edge bg-pass-soft px-3 py-2 text-xs text-pass"
      >
        <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span>{t("form.saved")}</span>
      </div>
    );
  }
  return null;
}

/** The write form of a row (and the removal of its written Test Step), for the deciding
 * role on a Protocol in Draft status. */
export function WriteForm({
  t,
  row,
  runId,
  protocolId,
  write,
  remove,
  writeInline,
  removeInline,
  onDirtyChange,
}: {
  t: T;
  row: ProtocolRowView;
  runId: string;
  protocolId: number;
  write: Action;
  remove: Action;
  writeInline?: InlineAction;
  removeInline?: InlineAction;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [open, setOpen] = useState(true);
  const writeActionFn = writeInline ?? wrapLegacyAction(write);
  const removeActionFn = removeInline ?? wrapLegacyAction(remove);

  const [writeState, writeFormAction, isWritePending] = useActionState(
    async (prev: ProtocolFormActionState, formData: FormData) => {
      const next = await writeActionFn(prev, formData);
      if (next.ok) onDirtyChange?.(false);
      return next;
    },
    { ok: true },
  );

  const [removeState, removeFormAction, isRemovePending] = useActionState(
    async (prev: ProtocolFormActionState, formData: FormData) => {
      const next = await removeActionFn(prev, formData);
      if (next.ok) onDirtyChange?.(false);
      return next;
    },
    { ok: true },
  );

  if (row.test_step?.origin === "accepted_draft") {
    return (
      <p className="m-0 rounded-md border border-border bg-sunken px-3 py-2 text-xs text-ink-muted">
        {t("form.acceptedFirst")}
      </p>
    );
  }

  const inForce = row.test_step?.origin === "written";
  const p = row.prefill;
  const id = `write-${row.requirement}`;
  const title = t(inForce ? "form.change" : "form.write");

  return (
    <section className="space-y-3 rounded-lg border border-border bg-surface p-3.5">
      <div className="flex items-center justify-between gap-2">
        <h3 className="m-0 text-xs font-bold tracking-wide text-ink uppercase">{title}</h3>
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          className="inline-flex h-6 w-6 cursor-pointer items-center justify-center rounded border border-border bg-sunken text-ink-muted hover:text-ink"
        >
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`}
            aria-hidden="true"
          />
        </button>
      </div>
      {open && (
        <>
          {p && p.origin !== "written" && (
            <p className="m-0 text-xs text-ink-muted">{t(`form.prefill.${p.origin}`)}</p>
          )}
          <ActionFeedback t={t} state={writeState} />
          <form
            key={`${id}-${writeState.submittedAt ?? 0}`}
            action={writeFormAction}
            className="space-y-3"
            aria-label={title}
          >
            <Hidden runId={runId} protocolId={protocolId} />
            <input type="hidden" name="requirement" value={row.requirement} />
            <Fields
              t={t}
              id={id}
              start={p ? { ...p, acceptance: p.acceptance ?? null } : null}
              onDirty={() => onDirtyChange?.(true)}
            />
            <button
              type="submit"
              disabled={isWritePending}
              className="inline-flex cursor-pointer items-center justify-center rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
            >
              {t("form.save")}
            </button>
          </form>
          {inForce && (
            <div className="border-t border-border pt-3">
              <ActionFeedback t={t} state={removeState} />
              <form action={removeFormAction}>
                <Hidden runId={runId} protocolId={protocolId} />
                <input type="hidden" name="requirement" value={row.requirement} />
                <button
                  type="submit"
                  disabled={isRemovePending}
                  className="inline-flex cursor-pointer items-center justify-center rounded-md border border-fail-edge bg-surface px-3 py-1.5 text-xs font-semibold text-fail hover:bg-fail-soft disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {t("form.remove")}
                </button>
              </form>
            </div>
          )}
        </>
      )}
    </section>
  );
}

/** The edit form of a drafted Test Step: the `edited` decision with its Reason for Change and
 * the Test Step it gives. */
export function EditDraftForm({
  t,
  d,
  runId,
  protocolId,
  edit,
  editInline,
  onDirtyChange,
}: {
  t: T;
  d: RowDraft;
  runId: string;
  protocolId: number;
  edit: Action;
  editInline?: InlineAction;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const x = d.draft;
  const editActionFn = editInline ?? wrapLegacyAction(edit);
  const [reason, setReason] = useState("");
  const [state, formAction, isPending] = useActionState(
    async (prev: ProtocolFormActionState, formData: FormData) => {
      const next = await editActionFn(prev, formData);
      if (next.ok) {
        setReason("");
        onDirtyChange?.(false);
      }
      return next;
    },
    { ok: true },
  );

  const [open, setOpen] = useState(true);
  const label = t(x.acceptance && x.acceptance.type !== "text" ? "form.edit" : "form.editSetAc");

  return (
    <section className="space-y-3 rounded-lg border border-border bg-surface p-3.5">
      <div className="flex items-center justify-between gap-2">
        <h4 className="m-0 text-xs font-bold tracking-wide text-ink uppercase">{label}</h4>
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          className="inline-flex h-6 w-6 cursor-pointer items-center justify-center rounded border border-border bg-sunken text-ink-muted hover:text-ink"
        >
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`}
            aria-hidden="true"
          />
        </button>
      </div>
      {open && (
        <>
          <ActionFeedback t={t} state={state} />
          <form
            key={`edit-${d.proposal.id}-${state.submittedAt ?? 0}`}
            action={formAction}
            className="space-y-3"
            aria-label={t("form.edit")}
          >
            <Hidden runId={runId} protocolId={protocolId} />
            <input type="hidden" name="proposal_id" value={d.proposal.id} />
            <Fields
              t={t}
              id={`edit-${d.proposal.id}`}
              start={{ ...x, acceptance: shaped(x.acceptance) }}
              onDirty={() => onDirtyChange?.(true)}
            />
            <label className="block space-y-1 text-xs font-medium text-ink">
              <span>{t("form.reason")}</span>
              <textarea
                name="reason"
                required
                rows={2}
                value={reason}
                onChange={(e) => {
                  setReason(e.target.value);
                  onDirtyChange?.(true);
                }}
                className={TEXTAREA_CLASS}
              />
            </label>
            <button
              type="submit"
              disabled={isPending}
              className="inline-flex cursor-pointer items-center justify-center rounded-md border border-border-strong bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-60"
            >
              {t("form.saveEdit")}
            </button>
          </form>
        </>
      )}
    </section>
  );
}

/** Every version of the row's written Test Step, oldest first: who, when, and its content or
 * the removal. */
export function Versions({ t, m, versions }: { t: T; m: MatrixT; versions: readonly Version[] }) {
  const when = useTranslations("decisions");
  const [open, setOpen] = useState(true);
  if (versions.length === 0) return null;

  return (
    <section className="space-y-2 rounded-lg border border-border bg-sunken p-3">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full cursor-pointer items-center justify-between gap-2 text-left text-xs font-bold text-ink"
      >
        <span className="inline-flex items-center gap-1.5">
          <History className="h-3.5 w-3.5 text-ink-muted" aria-hidden="true" />
          <span>{t("versions.title", { count: versions.length })}</span>
        </span>
        <ChevronDown
          className={`h-3.5 w-3.5 text-ink-muted transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>
      {open && (
        <ol className="m-0 list-decimal space-y-2 pl-5 text-xs">
          {versions.map((v) => (
            <li key={v.id} className="space-y-0.5 text-ink">
              <div>
                {t(v.removed ? "versions.removed" : "versions.written", {
                  version: v.version,
                  name: v.name,
                  when: formatWhen(when, v.at),
                })}
                {v.from_proposal_id !== null && (
                  <span className="text-ink-muted"> {t("versions.fromDraft")}</span>
                )}
              </div>
              {v.test_step && (
                <div className="text-ink-muted">
                  {v.test_step.description} · {v.test_step.method} ·{" "}
                  {v.test_step.instrument ?? t("noInstrument")} ·{" "}
                  {formatValue(m, v.test_step.acceptance)}
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
