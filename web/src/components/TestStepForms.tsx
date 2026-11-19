import { useTranslations } from "next-intl";

import type { ProtocolRowView, RowDraft, Value } from "@/api/client";
import type { components } from "@/api/schema";
import { SHAPES, type Acceptance } from "@/protocol/form";
import { formatWhen } from "./formatWhen";
import { formatValue } from "./MatrixTable";
import { Button } from "./ui/ui";

import s from "./AssembledProtocolView.module.css";

type T = ReturnType<typeof useTranslations<"protocol">>;
type MatrixT = ReturnType<typeof useTranslations<"matrix">>;
type Version = components["schemas"]["WrittenVersionView"];
type Action = (formData: FormData) => void | Promise<void>;

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

/** The fields of a Test Step: description, method, instrument, and the Acceptance Criterion
 * as one of four shapes with its values. Without script every field is in view; the form
 * reads only those of the chosen shape. */
function Fields({ t, id, start }: { t: T; id: string; start: Start | null }) {
  const a = start?.acceptance ?? null;
  return (
    <>
      <label className={s.field}>
        {t("description")}
        <textarea name="description" required defaultValue={start?.description ?? ""} />
      </label>
      <label className={s.field}>
        {t("method")}
        <textarea name="method" required defaultValue={start?.method ?? ""} />
      </label>
      <label className={s.field}>
        {t("instrument")}
        <input name="instrument" defaultValue={start?.instrument ?? ""} />
      </label>
      <fieldset className={s.acFields}>
        <legend>{t("ac")}</legend>
        <label className={s.field}>
          {t("form.shape")}
          <select name="ac_type" required defaultValue={a?.type ?? ""}>
            <option value="" disabled>
              {t("form.chooseShape")}
            </option>
            {SHAPES.map((shape) => (
              <option key={shape} value={shape}>
                {t(`form.shapes.${shape}`)}
              </option>
            ))}
          </select>
        </label>
        <label className={s.field}>
          {t("form.min")}
          <input name="ac_min" inputMode="decimal" defaultValue={a?.type === "range" ? (a.min ?? "") : ""} />
        </label>
        <label className={s.field}>
          {t("form.max")}
          <input name="ac_max" inputMode="decimal" defaultValue={a?.type === "range" ? (a.max ?? "") : ""} />
        </label>
        <label className={s.field}>
          {t("form.value")}
          <input name="ac_value" inputMode="decimal" defaultValue={a?.type === "number" ? a.value : ""} />
        </label>
        <label className={s.field}>
          {t("form.unit")}
          <input
            name="ac_unit"
            defaultValue={a?.type === "range" || a?.type === "number" ? a.unit : ""}
          />
        </label>
        <label className={s.field}>
          {t("form.allowed")}
          <input name="ac_allowed" defaultValue={a?.type === "one_of" ? a.allowed.join("; ") : ""} />
        </label>
        <p className={s.muted} id={`${id}-hint`}>
          {t("form.hint")}
        </p>
      </fieldset>
    </>
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

/** The write form of a row (and the removal of its written Test Step), for the deciding
 * role on a Protocol in Draft status. Starts from the row's prefill: the written Test Step in
 * force, else the latest version in the most recent withdrawn Protocol, else the draft. While
 * a draft of the row is accepted, a note says to reject it first instead. */
export function WriteForm({
  t,
  row,
  runId,
  protocolId,
  write,
  remove,
}: {
  t: T;
  row: ProtocolRowView;
  runId: string;
  protocolId: number;
  write: Action;
  remove: Action;
}) {
  if (row.test_step?.origin === "accepted_draft") {
    return <p className={s.muted}>{t("form.acceptedFirst")}</p>;
  }
  const inForce = row.test_step?.origin === "written";
  const p = row.prefill;
  const id = `write-${row.requirement}`;
  return (
    <details className={s.writeFold}>
      <summary>{t(inForce ? "form.change" : "form.write")}</summary>
      {p && p.origin !== "written" && <p className={s.muted}>{t(`form.prefill.${p.origin}`)}</p>}
      <form action={write} className={s.stepForm} aria-label={t(inForce ? "form.change" : "form.write")}>
        <Hidden runId={runId} protocolId={protocolId} />
        <input type="hidden" name="requirement" value={row.requirement} />
        <Fields t={t} id={id} start={p ? { ...p, acceptance: p.acceptance ?? null } : null} />
        <Button type="submit" variant="soft">
          {t("form.save")}
        </Button>
      </form>
      {inForce && (
        <form action={remove} className={s.form}>
          <Hidden runId={runId} protocolId={protocolId} />
          <input type="hidden" name="requirement" value={row.requirement} />
          <button type="submit">{t("form.remove")}</button>
        </form>
      )}
    </details>
  );
}

/** The edit form of a drafted Test Step: the `edited` decision with its Reason for Change and
 * the Test Step it gives, starting from the draft (its Acceptance Criterion only when in one
 * of the four shapes, so a missing one is set here). */
export function EditDraftForm({
  t,
  d,
  runId,
  protocolId,
  edit,
}: {
  t: T;
  d: RowDraft;
  runId: string;
  protocolId: number;
  edit: Action;
}) {
  const x = d.draft;
  return (
    <details className={s.writeFold}>
      <summary>{t(x.acceptance && x.acceptance.type !== "text" ? "form.edit" : "form.editSetAc")}</summary>
      <form action={edit} className={s.stepForm} aria-label={t("form.edit")}>
        <Hidden runId={runId} protocolId={protocolId} />
        <input type="hidden" name="proposal_id" value={d.proposal.id} />
        <Fields
          t={t}
          id={`edit-${d.proposal.id}`}
          start={{ ...x, acceptance: shaped(x.acceptance) }}
        />
        <label className={s.field}>
          {t("form.reason")}
          <textarea name="reason" required />
        </label>
        <Button type="submit" variant="soft">
          {t("form.saveEdit")}
        </Button>
      </form>
    </details>
  );
}

/** Every version of the row's written Test Step, oldest first: who, when, and its content or
 * the removal. Each version's content is shown in full, so the old and the new can be read
 * side by side. */
export function Versions({ t, m, versions }: { t: T; m: MatrixT; versions: readonly Version[] }) {
  const when = useTranslations("decisions");
  if (versions.length === 0) return null;
  return (
    <details className={s.versions}>
      <summary>{t("versions.title", { count: versions.length })}</summary>
      <ol>
        {versions.map((v) => (
          <li key={v.id}>
            <div>
              {t(v.removed ? "versions.removed" : "versions.written", {
                version: v.version,
                name: v.name,
                when: formatWhen(when, v.at),
              })}
              {v.from_proposal_id !== null && <span className={s.muted}> {t("versions.fromDraft")}</span>}
            </div>
            {v.test_step && (
              <div className={s.muted}>
                {v.test_step.description} · {v.test_step.method} · {v.test_step.instrument ?? t("noInstrument")} ·{" "}
                {formatValue(m, v.test_step.acceptance)}
              </div>
            )}
          </li>
        ))}
      </ol>
    </details>
  );
}
