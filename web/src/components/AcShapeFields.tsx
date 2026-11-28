"use client";

import { useState } from "react";

import { FIELD_BASE_CLASS } from "./ui/FormControls";

export type AcShapeFieldsProps = {
  id: string;
  initialShape: string;
  initialMin: string | number;
  initialMax: string | number;
  initialMinExclusive?: boolean;
  initialMaxExclusive?: boolean;
  initialNominal?: string | number;
  initialTolerance?: string | number;
  initialToleranceUnit?: string;
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
    minExclusive: string;
    maxExclusive: string;
    nominal: string;
    tolerance: string;
    toleranceUnit: string;
    value: string;
    unit: string;
    allowed: string;
    hint: string;
  };
  onDirty?: () => void;
};

const INPUT_CLASS = `w-full text-xs ${FIELD_BASE_CLASS}`;

/** Thin client island: shows only the Acceptance Criterion inputs matching the selected `ac_type`. */
export function AcShapeFields({
  id,
  initialShape,
  initialMin,
  initialMax,
  initialMinExclusive = false,
  initialMaxExclusive = false,
  initialNominal = "",
  initialTolerance = "",
  initialToleranceUnit = "",
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
  const [minExclusive, setMinExclusive] = useState(initialMinExclusive);
  const [maxExclusive, setMaxExclusive] = useState(initialMaxExclusive);
  const [nominalVal, setNominalVal] = useState(String(initialNominal));
  const [toleranceVal, setToleranceVal] = useState(String(initialTolerance));
  const [toleranceUnitVal, setToleranceUnitVal] = useState(initialToleranceUnit);
  const [numVal, setNumVal] = useState(String(initialValue));
  const [unitVal, setUnitVal] = useState(initialUnit);
  const [allowedVal, setAllowedVal] = useState(initialAllowed);

  return (
    <fieldset
      aria-describedby={`${id}-hint`}
      className="space-y-2.5 rounded-md border border-border bg-canvas p-3"
    >
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
      {(shape === "range" || shape === "exclusive_range") && (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <div className="space-y-1">
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
            {shape === "exclusive_range" && (
              <label className="inline-flex cursor-pointer items-center gap-1.5 text-[11px] text-ink">
                <input
                  type="checkbox"
                  name="ac_min_exclusive"
                  checked={minExclusive}
                  onChange={(e) => {
                    setMinExclusive(e.target.checked);
                    onDirty?.();
                  }}
                  className="h-3.5 w-3.5 rounded border-border-strong accent-accent"
                />
                <span>{labels.minExclusive}</span>
              </label>
            )}
          </div>
          <div className="space-y-1">
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
            {shape === "exclusive_range" && (
              <label className="inline-flex cursor-pointer items-center gap-1.5 text-[11px] text-ink">
                <input
                  type="checkbox"
                  name="ac_max_exclusive"
                  checked={maxExclusive}
                  onChange={(e) => {
                    setMaxExclusive(e.target.checked);
                    onDirty?.();
                  }}
                  className="h-3.5 w-3.5 rounded border-border-strong accent-accent"
                />
                <span>{labels.maxExclusive}</span>
              </label>
            )}
          </div>
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
      {shape === "tolerance" && (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <label className="block space-y-1 text-xs font-medium text-ink">
            <span>{labels.nominal}</span>
            <input
              name="ac_nominal"
              inputMode="decimal"
              value={nominalVal}
              onChange={(e) => {
                setNominalVal(e.target.value);
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
          <label className="block space-y-1 text-xs font-medium text-ink">
            <span>{labels.tolerance}</span>
            <input
              name="ac_tolerance"
              inputMode="decimal"
              value={toleranceVal}
              onChange={(e) => {
                setToleranceVal(e.target.value);
                onDirty?.();
              }}
              className={`${INPUT_CLASS} tabular-nums`}
            />
          </label>
          <label className="block space-y-1 text-xs font-medium text-ink">
            <span>{labels.toleranceUnit}</span>
            <input
              name="ac_tolerance_unit"
              value={toleranceUnitVal}
              onChange={(e) => {
                setToleranceUnitVal(e.target.value);
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
