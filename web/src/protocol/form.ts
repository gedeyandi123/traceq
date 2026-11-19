import type { components } from "@/api/schema";

/** An Acceptance Criterion a human sets: range, number, one of or present (spec #247). */
export type Acceptance = components["schemas"]["Acceptance"];
/** A Test Step as a human writes or edits it. */
export type StepContent = components["schemas"]["WrittenContent"];

/** The four shapes, in the order the form offers them. */
export const SHAPES = ["range", "number", "one_of", "present"] as const;

function text(form: FormData, name: string): string {
  const v = form.get(name);
  return typeof v === "string" ? v.trim() : "";
}

/** A number as typed, with a decimal comma or point; `null` when blank, `NaN` when not one. */
function decimal(form: FormData, name: string): number | null {
  const raw = text(form, name);
  return raw === "" ? null : Number(raw.replace(",", "."));
}

function acceptanceFrom(form: FormData): Acceptance | null {
  const unit = text(form, "ac_unit");
  switch (text(form, "ac_type")) {
    case "range": {
      const min = decimal(form, "ac_min");
      const max = decimal(form, "ac_max");
      if ((min === null && max === null) || Number.isNaN(min) || Number.isNaN(max) || unit === "") return null;
      if (min !== null && max !== null && min > max) return null;
      return { type: "range", min, max, unit };
    }
    case "number": {
      const value = decimal(form, "ac_value");
      if (value === null || Number.isNaN(value) || unit === "") return null;
      return { type: "number", value, unit };
    }
    case "one_of": {
      const allowed = text(form, "ac_allowed")
        .split(";")
        .map((v) => v.trim())
        .filter((v) => v !== "");
      return allowed.length === 0 ? null : { type: "one_of", allowed };
    }
    case "present":
      return { type: "present" };
    default:
      return null;
  }
}

/** The Test Step of a write or edit form, or `null` when it is not complete: a description, a
 * method and an Acceptance Criterion in one of the four shapes. The API checks it again. */
export function stepFrom(form: FormData): StepContent | null {
  const description = text(form, "description");
  const method = text(form, "method");
  const acceptance = acceptanceFrom(form);
  if (description === "" || method === "" || acceptance === null) return null;
  return { description, method, instrument: text(form, "instrument") || null, acceptance };
}
