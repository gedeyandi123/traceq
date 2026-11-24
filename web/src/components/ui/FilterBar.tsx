"use client";

import type { ReactNode } from "react";

export type FilterPillOption<T extends string> = {
  id: T;
  label: string;
  count: number;
  activeClass?: string;
};

/** Unified rounded-full filter pill bar shared across Matrix, Findings, Draft, and Protocol. */
export function FilterBar<T extends string>({
  ariaLabel,
  options,
  activeId,
  onSelect,
  trailing,
  className,
}: {
  ariaLabel: string;
  options: readonly FilterPillOption<T>[];
  activeId: T;
  onSelect: (id: T) => void;
  trailing?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-wrap items-center justify-between gap-2 ${className ?? ""}`.trim()}>
      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={ariaLabel}>
        {options.map((opt) => {
          const active = activeId === opt.id;
          const activeStyle = opt.activeClass ?? "border-accent bg-accent text-on-accent";
          return (
            <button
              key={opt.id}
              type="button"
              aria-pressed={active}
              onClick={() => onSelect(opt.id)}
              className={`inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold tabular-nums transition-colors ${
                active ? activeStyle : "border-border bg-surface text-ink hover:bg-sunken"
              }`}
            >
              <span>{opt.label}</span>
              <span
                className={`rounded-full px-1.5 py-0.5 text-[11px] leading-none tabular-nums ${
                  active ? "bg-surface/20 text-current" : "bg-sunken text-ink-muted"
                }`}
              >
                {opt.count}
              </span>
            </button>
          );
        })}
      </div>
      {trailing && <div className="flex flex-wrap items-center gap-2">{trailing}</div>}
    </div>
  );
}
