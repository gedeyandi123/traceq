"use client";

import { AlertCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { useActionState, useState } from "react";

import type { ExecutionRowView } from "@/api/client";
import type { ExecutionActionState } from "@/execution/actions";
import { Drawer } from "./ui/Drawer";
import { FIELD_BASE_CLASS } from "./ui/FormControls";
import { SubmitButton } from "./ui/SubmitButton";
import { Button } from "./ui/ui";

type Action = (
  prevState: ExecutionActionState,
  formData: FormData,
) => Promise<ExecutionActionState>;

const INITIAL_STATE: ExecutionActionState = { ok: true };

/** Drawer form to open a manual Deviation linked to a Test Step row or to the Execution. */
export function ManualDeviationDrawer({
  executionId,
  rows,
  open,
  onOpenChange,
  openAction,
}: {
  executionId: number;
  rows: ExecutionRowView[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  openAction: Action;
}) {
  const t = useTranslations("execution");
  const [requirement, setRequirement] = useState<string>("");
  const [description, setDescription] = useState<string>("");

  const [state, formAction] = useActionState(async (prev: ExecutionActionState, fd: FormData) => {
    const res = await openAction(prev, fd);
    if (res.ok) {
      setRequirement("");
      setDescription("");
      onOpenChange(false);
    }
    return res;
  }, INITIAL_STATE);

  const testStepRows = rows.filter((r) => r.kind === "test_step");

  return (
    <Drawer open={open} onOpenChange={onOpenChange} title={t("openManualDeviationTitle")}>
      <form action={formAction} className="space-y-4">
        <input type="hidden" name="execution_id" value={executionId} />

        {!state.ok && state.error && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-fail-edge bg-fail-soft px-3 py-2 text-xs text-fail"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{state.detail ?? t(`errors.${state.error}`)}</span>
          </div>
        )}

        <div className="space-y-1.5">
          <label htmlFor="manual-dev-target" className="block text-xs font-semibold text-ink">
            {t("deviationLinkTarget")}
          </label>
          <select
            id="manual-dev-target"
            name="requirement"
            value={requirement}
            onChange={(e) => setRequirement(e.target.value)}
            className={`w-full text-xs ${FIELD_BASE_CLASS}`}
          >
            <option value="">{t("deviationLinkExecution")}</option>
            {testStepRows.map((r) => (
              <option key={r.requirement} value={r.requirement}>
                {r.requirement} — {r.test_step?.description ?? r.text}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="manual-dev-desc" className="block text-xs font-semibold text-ink">
            {t("deviationDescription")}
          </label>
          <textarea
            id="manual-dev-desc"
            name="description"
            required
            rows={4}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder={t("deviationDescriptionPlaceholder")}
            className={`w-full py-2 text-xs ${FIELD_BASE_CLASS}`}
          />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="quiet" onClick={() => onOpenChange(false)}>
            {t("cancel")}
          </Button>
          <SubmitButton variant="primary">{t("deviationSubmitOpen")}</SubmitButton>
        </div>
      </form>
    </Drawer>
  );
}
