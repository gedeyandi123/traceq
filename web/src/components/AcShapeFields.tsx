"use client";

import { useState } from "react";

import s from "./AssembledProtocolView.module.css";

export type AcShapeFieldsProps = {
  id: string;
  initialShape: string;
  initialMin: string | number;
  initialMax: string | number;
  initialValue: string | number;
  initialUnit: string;
  initialAllowed: string;
  shapes: readonly { value: string; label: string }[];
  labels: {
    legend: string;
    shape: string;
    chooseShape: string;
    min: string;
    max: string;
    value: string;
    unit: string;
    allowed: string;
    hint: string;
  };
};

/** Thin client island: shows only the Acceptance Criterion inputs matching the selected `ac_type`. */
export function AcShapeFields({
  id,
  initialShape,
  initialMin,
  initialMax,
  initialValue,
  initialUnit,
  initialAllowed,
  shapes,
  labels,
}: AcShapeFieldsProps) {
  const [shape, setShape] = useState(initialShape);

  return (
    <fieldset className={s.acFields}>
      <legend>{labels.legend}</legend>
      <label className={s.field}>
        {labels.shape}
        <select name="ac_type" required value={shape} onChange={(e) => setShape(e.target.value)}>
          <option value="" disabled>
            {labels.chooseShape}
          </option>
          {shapes.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>
      {shape === "range" && (
        <>
          <label className={s.field}>
            {labels.min}
            <input name="ac_min" inputMode="decimal" defaultValue={initialMin} />
          </label>
          <label className={s.field}>
            {labels.max}
            <input name="ac_max" inputMode="decimal" defaultValue={initialMax} />
          </label>
          <label className={s.field}>
            {labels.unit}
            <input name="ac_unit" defaultValue={initialUnit} />
          </label>
        </>
      )}
      {shape === "number" && (
        <>
          <label className={s.field}>
            {labels.value}
            <input name="ac_value" inputMode="decimal" defaultValue={initialValue} />
          </label>
          <label className={s.field}>
            {labels.unit}
            <input name="ac_unit" defaultValue={initialUnit} />
          </label>
        </>
      )}
      {shape === "one_of" && (
        <label className={s.field}>
          {labels.allowed}
          <input name="ac_allowed" defaultValue={initialAllowed} />
        </label>
      )}
      <p className={s.muted} id={`${id}-hint`}>
        {labels.hint}
      </p>
    </fieldset>
  );
}
