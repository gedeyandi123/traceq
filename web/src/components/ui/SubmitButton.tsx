"use client";

import type { ButtonHTMLAttributes } from "react";
import { useFormStatus } from "react-dom";

import { Button } from "./ui";

/** Thin client island wrapping Button with `useFormStatus()` pending state. */
export function SubmitButton({
  variant,
  disabled,
  children,
  ...props
}: {
  variant?: "primary" | "soft" | "quiet" | "danger";
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  const { pending } = useFormStatus();
  const isDisabled = Boolean(disabled) || pending;
  if (variant) {
    return (
      <Button {...props} type="submit" variant={variant} disabled={isDisabled} aria-busy={pending || undefined}>
        {children}
      </Button>
    );
  }
  return (
    <button {...props} type="submit" disabled={isDisabled} aria-busy={pending || undefined}>
      {children}
    </button>
  );
}
