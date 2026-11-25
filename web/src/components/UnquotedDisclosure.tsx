"use client";

import { ChevronDown } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import type { Completeness } from "@/api/client";
import { PdfCitationButton } from "./ui/PdfCitationModal";

export function UnquotedDisclosure({
  u,
  runId,
}: {
  u: Completeness["urs"][number];
  runId?: string;
}) {
  const t = useTranslations("leftOut");
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-md border border-border bg-sunken/40">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full cursor-pointer items-center justify-between gap-2 px-3 py-2 text-left text-xs font-semibold text-accent hover:bg-sunken/70"
      >
        <span>{t("showUnquoted", { count: u.unquoted.length })}</span>
        <ChevronDown
          className={`h-3.5 w-3.5 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>
      <ul
        className={`m-0 list-none flex-col gap-2.5 px-3 pt-1 pb-3 ${open ? "flex" : "hidden"}`}
      >
        {u.unquoted.map((x) => (
          <li key={`${x.page}/${x.text}`} className="rounded border border-border bg-surface p-3">
            <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-semibold text-ink-muted tabular-nums">
                {t("page", { page: x.page })}
              </span>
              {runId && (
                <PdfCitationButton
                  runId={runId}
                  cite={{ doc: u.doc, rev: u.rev, page: x.page, quote: x.text.slice(0, 120) }}
                  compact
                />
              )}
            </div>
            <pre className="m-0 font-sans text-xs leading-relaxed whitespace-pre-wrap text-ink">
              {x.text}
            </pre>
          </li>
        ))}
      </ul>
    </div>
  );
}
