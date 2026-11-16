"use client";
// PROTOTYPE (feat/ui-redesign-prototype, never merged): the floating palette switcher. The
// layout renders it only outside production builds. It sets html[data-palette] from
// ?variant= or the last choice, so the palette survives navigation between pages.
import { useEffect, useState } from "react";

import s from "./PrototypeSwitcher.module.css";

const KEY = "traceq-prototype-palette";

export function PrototypeSwitcher({ variants }: { variants: readonly { key: string; name: string }[] }) {
  const [current, setCurrent] = useState<string | null>(null);

  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("variant");
    let saved: string | null = null;
    try {
      saved = window.localStorage.getItem(KEY);
    } catch {}
    const start = variants.find((v) => v.key === fromUrl)?.key ?? saved ?? variants[0]?.key ?? null;
    setCurrent(start);
  }, [variants]);

  useEffect(() => {
    if (current === null) return;
    document.documentElement.dataset.palette = current;
    try {
      window.localStorage.setItem(KEY, current);
    } catch {}
    const url = new URL(window.location.href);
    url.searchParams.set("variant", current);
    window.history.replaceState(window.history.state, "", url);
  }, [current]);

  const i = Math.max(0, variants.findIndex((v) => v.key === current));
  const go = (step: number) => setCurrent(variants[(i + step + variants.length) % variants.length]?.key ?? null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el?.closest("input, textarea, select, [contenteditable]")) return;
      if (e.key === "ArrowLeft") go(-1);
      if (e.key === "ArrowRight") go(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const v = variants[i];
  return (
    <div className={s.bar} role="toolbar" aria-label="Prototype palette">
      <button type="button" onClick={() => go(-1)} aria-label="Previous palette">
        ←
      </button>
      <span className={s.label}>
        {v?.key} ({v?.name})
      </span>
      <button type="button" onClick={() => go(1)} aria-label="Next palette">
        →
      </button>
    </div>
  );
}
