import type {
  InputHTMLAttributes,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

/** Shared base styling for form controls: WCAG 1.4.11 compliant `--color-input-border`
 * without `focus:outline-none`, preserving the global 2px `:focus-visible` ring. */
export const FIELD_BASE_CLASS =
  "rounded-md border border-input-border bg-surface px-2.5 py-1.5 text-sm text-ink placeholder:text-ink-muted focus:border-accent disabled:cursor-not-allowed disabled:bg-sunken disabled:opacity-60";

export function FieldInput({
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${FIELD_BASE_CLASS} ${className ?? ""}`.trim()} />;
}

export function FieldTextarea({
  className,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`${FIELD_BASE_CLASS} ${className ?? ""}`.trim()} />;
}

export function FieldSelect({
  className,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${FIELD_BASE_CLASS} ${className ?? ""}`.trim()} />;
}
