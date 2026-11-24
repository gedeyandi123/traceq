"use client";

/** Standardized `role="alertdialog"` dirty-form guard banner for drawers and split panes. */
export function DirtyGuardBanner({
  message,
  discardLabel,
  keepLabel,
  onDiscard,
  onKeep,
  className,
}: {
  message: string;
  discardLabel: string;
  keepLabel: string;
  onDiscard: () => void;
  onKeep: () => void;
  className?: string;
}) {
  return (
    <div
      role="alertdialog"
      aria-label={message}
      className={`rounded-lg border border-warn-edge bg-warn-soft p-3 text-xs text-warn ${className ?? ""}`.trim()}
    >
      <p className="m-0 font-semibold">{message}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onDiscard}
          className="cursor-pointer rounded border border-warn-edge bg-surface px-2.5 py-1 text-xs font-semibold text-warn hover:bg-sunken"
        >
          {discardLabel}
        </button>
        <button
          type="button"
          onClick={onKeep}
          className="cursor-pointer rounded bg-accent px-2.5 py-1 text-xs font-semibold text-on-accent hover:bg-accent-hover"
        >
          {keepLabel}
        </button>
      </div>
    </div>
  );
}
