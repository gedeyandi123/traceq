// Reading a Test Step and its Acceptance Criterion from the write and edit forms of the
// Protocol page (spec #247, ticket #250, #426): only the six Acceptance shapes, never free text.
import { SHAPES, stepFrom } from "./form";

function form(fields: Record<string, string>): FormData {
  const f = new FormData();
  for (const [k, v] of Object.entries(fields)) f.set(k, v);
  return f;
}

const base = { description: " Verifikasi kecepatan. ", method: "Baca takometer.", instrument: "" };

test("SHAPES includes exclusive_range and tolerance alongside the core four shapes", () => {
  expect(SHAPES).toEqual(["range", "exclusive_range", "tolerance", "number", "one_of", "present"]);
});

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

test("an exclusive_range takes at least one strict bound and enforces ExclusiveRange invariants", () => {
  expect(
    stepFrom(
      form({
        ...base,
        ac_type: "exclusive_range",
        ac_max: "0,8",
        ac_max_exclusive: "on",
        ac_unit: "µm",
      }),
    )?.acceptance,
  ).toEqual({
    type: "exclusive_range",
    min: null,
    max: 0.8,
    min_exclusive: false,
    max_exclusive: true,
    unit: "µm",
  });

  expect(
    stepFrom(
      form({
        ...base,
        ac_type: "exclusive_range",
        ac_min: "10",
        ac_max: "20",
        ac_min_exclusive: "on",
        ac_unit: "bar",
      }),
    )?.acceptance,
  ).toEqual({
    type: "exclusive_range",
    min: 10,
    max: 20,
    min_exclusive: true,
    max_exclusive: false,
    unit: "bar",
  });

  // Neither bound strict -> rejected
  expect(
    stepFrom(form({ ...base, ac_type: "exclusive_range", ac_min: "10", ac_unit: "bar" })),
  ).toBeNull();
  // Strict bound without value -> rejected
  expect(
    stepFrom(
      form({
        ...base,
        ac_type: "exclusive_range",
        ac_max: "10",
        ac_min_exclusive: "on",
        ac_max_exclusive: "on",
        ac_unit: "bar",
      }),
    ),
  ).toBeNull();
  // min > max -> rejected
  expect(
    stepFrom(
      form({
        ...base,
        ac_type: "exclusive_range",
        ac_min: "20",
        ac_max: "10",
        ac_max_exclusive: "on",
        ac_unit: "bar",
      }),
    ),
  ).toBeNull();
  // Missing unit -> rejected
  expect(
    stepFrom(
      form({
        ...base,
        ac_type: "exclusive_range",
        ac_max: "0,8",
        ac_max_exclusive: "on",
        ac_unit: "",
      }),
    ),
  ).toBeNull();
});

test("a tolerance takes nominal, non-negative tolerance, matching tolerance_unit or %, and unit", () => {
  expect(
    stepFrom(
      form({
        ...base,
        ac_type: "tolerance",
        ac_nominal: "380",
        ac_tolerance: "10",
        ac_tolerance_unit: "%",
        ac_unit: "V",
      }),
    )?.acceptance,
  ).toEqual({
    type: "tolerance",
    nominal: 380,
    tolerance: 10,
    tolerance_unit: "%",
    unit: "V",
  });

  expect(
    stepFrom(
      form({
        ...base,
        ac_type: "tolerance",
        ac_nominal: "100",
        ac_tolerance: "0,5",
        ac_tolerance_unit: "mm",
        ac_unit: "mm",
      }),
    )?.acceptance,
  ).toEqual({
    type: "tolerance",
    nominal: 100,
    tolerance: 0.5,
    tolerance_unit: "mm",
    unit: "mm",
  });

  // Wrong discriminator ("tolerance_band" instead of "tolerance") -> rejected
  expect(
    stepFrom(
      form({
        ...base,
        ac_type: "tolerance_band",
        ac_nominal: "380",
        ac_tolerance: "10",
        ac_tolerance_unit: "%",
        ac_unit: "V",
      }),
    ),
  ).toBeNull();
  // Negative tolerance -> rejected
  expect(
    stepFrom(
      form({
        ...base,
        ac_type: "tolerance",
        ac_nominal: "380",
        ac_tolerance: "-1",
        ac_tolerance_unit: "%",
        ac_unit: "V",
      }),
    ),
  ).toBeNull();
  // Mismatched tolerance_unit -> rejected
  expect(
    stepFrom(
      form({
        ...base,
        ac_type: "tolerance",
        ac_nominal: "380",
        ac_tolerance: "10",
        ac_tolerance_unit: "mV",
        ac_unit: "V",
      }),
    ),
  ).toBeNull();
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
