"use client";

import { useState } from "react";

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
  onDirty?: () => void;
};

const INPUT_CLASS =
  "w-full rounded-md border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none";

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
  onDirty,
}: AcShapeFieldsProps) {
  const [shape, setShape] = useState(initialShape);
  const [minVal, setMinVal] = useState(String(initialMin));
  const [maxVal, setMaxVal] = useState(String(initialMax));
  const [numVal, setNumVal] = useState(String(initialValue));
  const [unitVal, setUnitVal] = useState(initialUnit);
  const [allowedVal, setAllowedVal] = useState(initialAllowed);

  return (
    <fieldset className="space-y-2.5 rounded-md border border-border bg-canvas p-3">
      <legend className="px-1 text-xs font-semibold text-ink">{labels.legend}</legend>
      <label className="block space-y-1 text-xs font-medium text-ink">
        <span>{labels.shape}</span>
        <select
          name="ac_type"
          required
          value={shape}
          onChange={(e) => {
            setShape(e.target.value);
            onDirty?.();
          }}
          className={INPUT_CLASS}
        >
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
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <label className="block space-y-1 text-xs font-medium text-ink">
            <span>{labels.min}</span>
            <input
              name="ac_min"
              inputMode="decimal"
              value={minVal}
              onChange={(e) => {
                setMinVal(e.target.value);
                onDirty?.();
              }}
              className={`${INPUT_CLASS} tabular-nums`}
            />
          </label>
          <label className="block space-y-1 text-xs font-medium text-ink">
            <span>{labels.max}</span>
            <input
              name="ac_max"
              inputMode="decimal"
              value={maxVal}
              onChange={(e) => {
                setMaxVal(e.target.value);
                onDirty?.();
              }}
              className={`${INPUT_CLASS} tabular-nums`}
            />
          </label>
          <label className="block space-y-1 text-xs font-medium text-ink">
            <span>{labels.unit}</span>
            <input
              name="ac_unit"
              value={unitVal}
              onChange={(e) => {
                setUnitVal(e.target.value);
                onDirty?.();
              }}
              className={INPUT_CLASS}
            />
          </label>
        </div>
      )}
      {shape === "number" && (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <label className="block space-y-1 text-xs font-medium text-ink">
            <span>{labels.value}</span>
            <input
              name="ac_value"
              inputMode="decimal"
              value={numVal}
              onChange={(e) => {
                setNumVal(e.target.value);
                onDirty?.();
              }}
              className={`${INPUT_CLASS} tabular-nums`}
            />
          </label>
          <label className="block space-y-1 text-xs font-medium text-ink">
            <span>{labels.unit}</span>
            <input
              name="ac_unit"
              value={unitVal}
              onChange={(e) => {
                setUnitVal(e.target.value);
                onDirty?.();
              }}
              className={INPUT_CLASS}
            />
          </label>
        </div>
      )}
      {shape === "one_of" && (
        <label className="block space-y-1 text-xs font-medium text-ink">
          <span>{labels.allowed}</span>
          <input
            name="ac_allowed"
            value={allowedVal}
            onChange={(e) => {
              setAllowedVal(e.target.value);
              onDirty?.();
            }}
            className={INPUT_CLASS}
          />
        </label>
      )}
      <p className="m-0 text-[11px] leading-relaxed text-ink-muted" id={`${id}-hint`}>
        {labels.hint}
      </p>
    </fieldset>
  );
}
