// Reading a Test Step and its Acceptance Criterion from the write and edit forms of the
// Protocol page (spec #247, ticket #250): only the four shapes, never free text.
import { stepFrom } from "./form";

function form(fields: Record<string, string>): FormData {
  const f = new FormData();
  for (const [k, v] of Object.entries(fields)) f.set(k, v);
  return f;
}

const base = { description: " Verifikasi kecepatan. ", method: "Baca takometer.", instrument: "" };

test("a range takes one or two bounds and a unit", () => {
  expect(stepFrom(form({ ...base, ac_type: "range", ac_min: "20", ac_max: "70", ac_unit: "rpm" }))).toEqual({
    description: "Verifikasi kecepatan.",
    method: "Baca takometer.",
    instrument: null,
    acceptance: { type: "range", min: 20, max: 70, unit: "rpm" },
  });
  expect(stepFrom(form({ ...base, ac_type: "range", ac_max: "0,5", ac_unit: "mm" }))?.acceptance).toEqual({
    type: "range",
    min: null,
    max: 0.5,
    unit: "mm",
  });
  expect(stepFrom(form({ ...base, ac_type: "range", ac_unit: "rpm" }))).toBeNull();
  expect(stepFrom(form({ ...base, ac_type: "range", ac_min: "20" }))).toBeNull();
});

test("a number takes an exact value and a unit", () => {
  expect(stepFrom(form({ ...base, ac_type: "number", ac_value: "12.5", ac_unit: "kN" }))?.acceptance).toEqual({
    type: "number",
    value: 12.5,
    unit: "kN",
  });
  expect(stepFrom(form({ ...base, ac_type: "number", ac_value: "abc", ac_unit: "kN" }))).toBeNull();
});

test("one of takes the allowed values separated by semicolons; present takes none", () => {
  expect(stepFrom(form({ ...base, ac_type: "one_of", ac_allowed: "terbuka; tertutup ;" }))?.acceptance).toEqual({
    type: "one_of",
    allowed: ["terbuka", "tertutup"],
  });
  expect(stepFrom(form({ ...base, ac_type: "one_of", ac_allowed: " ; " }))).toBeNull();
  expect(stepFrom(form({ ...base, ac_type: "present", ac_value: "1" }))?.acceptance).toEqual({ type: "present" });
});

test("free text, no shape or a blank description or method is not a Test Step", () => {
  expect(stepFrom(form({ ...base, ac_type: "text", ac_value: "baik" }))).toBeNull();
  expect(stepFrom(form({ ...base }))).toBeNull();
  expect(stepFrom(form({ ...base, description: " ", ac_type: "present" }))).toBeNull();
  expect(stepFrom(form({ ...base, method: "", ac_type: "present" }))).toBeNull();
});
