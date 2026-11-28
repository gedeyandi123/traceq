import type { components } from "@/api/schema";

/** An Acceptance Criterion a human sets: range, exclusive_range, tolerance, number, one_of, or present. */
export type Acceptance = components["schemas"]["Acceptance"];
/** A Test Step as a human writes or edits it. */
export type StepContent = components["schemas"]["WrittenContent"];

/** The six shapes, in the order the form offers them. */
export const SHAPES = [
  "range",
  "exclusive_range",
  "tolerance",
  "number",
  "one_of",
  "present",
] as const;

function text(form: FormData, name: string): string {
  const v = form.get(name);
  return typeof v === "string" ? v.trim() : "";
}

function checked(form: FormData, name: string): boolean {
  const v = form.get(name);
  return v === "on" || v === "true" || v === "1";
}

/** A number as typed, with a decimal comma or point; `null` when blank, `NaN` when not one. */
function decimal(form: FormData, name: string): number | null {
  const raw = text(form, name);
  return raw === "" ? null : Number(raw.replace(",", "."));
}

function isFiniteOrNull(n: number | null): boolean {
  return n === null || Number.isFinite(n);
}

function acceptanceFrom(form: FormData): Acceptance | null {
  const unit = text(form, "ac_unit");
  switch (text(form, "ac_type")) {
    case "range": {
      const min = decimal(form, "ac_min");
      const max = decimal(form, "ac_max");
      if ((min === null && max === null) || !isFiniteOrNull(min) || !isFiniteOrNull(max) || unit === "") {
        return null;
      }
      if (min !== null && max !== null && min > max) return null;
      return { type: "range", min, max, unit };
    }
    case "exclusive_range": {
      const min = decimal(form, "ac_min");
      const max = decimal(form, "ac_max");
      const min_exclusive = checked(form, "ac_min_exclusive");
      const max_exclusive = checked(form, "ac_max_exclusive");
      if ((min === null && max === null) || !isFiniteOrNull(min) || !isFiniteOrNull(max) || unit === "") {
        return null;
      }
      if ((min_exclusive && min === null) || (max_exclusive && max === null)) return null;
      if (!min_exclusive && !max_exclusive) return null;
      if (min !== null && max !== null && min > max) return null;
      return { type: "exclusive_range", min, max, min_exclusive, max_exclusive, unit };
    }
    case "tolerance": {
      const nominal = decimal(form, "ac_nominal");
      const tolerance = decimal(form, "ac_tolerance");
      const tolerance_unit = text(form, "ac_tolerance_unit");
      if (
        nominal === null ||
        !Number.isFinite(nominal) ||
        tolerance === null ||
        !Number.isFinite(tolerance) ||
        tolerance < 0 ||
        unit === ""
      ) {
        return null;
      }
      if (tolerance_unit !== "%" && tolerance_unit !== unit) return null;
      return { type: "tolerance", nominal, tolerance, tolerance_unit, unit };
    }
    case "number": {
      const value = decimal(form, "ac_value");
      if (value === null || !Number.isFinite(value) || unit === "") return null;
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
