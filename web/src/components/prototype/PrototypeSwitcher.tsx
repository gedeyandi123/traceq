"use client";
// PROTOTYPE (feat/ui-redesign-prototype, never merged): the floating variant switcher.
// The page renders it only outside production builds.
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import s from "./PrototypeSwitcher.module.css";

export function PrototypeSwitcher({
  variants,
  current,
}: {
  variants: readonly { key: string; name: string }[];
  current: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const i = Math.max(
    0,
    variants.findIndex((v) => v.key === current),
  );
  const go = (step: number) => {
    const next = variants[(i + step + variants.length) % variants.length];
    if (next) router.replace(`${pathname}?variant=${next.key}`);
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.closest("input, textarea, select, [contenteditable]") !== null)) return;
      if (e.key === "ArrowLeft") go(-1);
      if (e.key === "ArrowRight") go(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  const v = variants[i];
  return (
    <div className={s.bar} role="toolbar" aria-label="Prototype variant">
      <button type="button" onClick={() => go(-1)} aria-label="Previous variant">
        ←
      </button>
      <span className={s.label}>
        {v?.key} ({v?.name})
      </span>
      <button type="button" onClick={() => go(1)} aria-label="Next variant">
        →
      </button>
    </div>
  );
}
