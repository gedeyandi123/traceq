import { getTranslations } from "next-intl/server";
import Link from "next/link";
import type { ReactNode } from "react";

import { BrandMark } from "@/components/BrandMark";
import { SessionBar } from "@/components/SessionBar";

/** Compact entry layout for `/` and `/signin` (zero double header with `(run)`). */
export default async function HomeLayout({ children }: { children: ReactNode }) {
  const t = await getTranslations("app");
  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <header className="sticky top-0 z-30 h-12 border-b border-border bg-surface">
        <div className="mx-auto flex h-full max-w-[1280px] items-center justify-between gap-4 px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <Link
              href="/"
              className="inline-flex items-center gap-2 text-sm font-bold text-ink no-underline hover:text-accent"
            >
              <BrandMark />
              <span>{t("title")}</span>
            </Link>
            <span className="hidden truncate border-l border-border pl-3 text-xs text-ink-muted md:inline">
              {t("tagline")}
            </span>
          </div>
          <SessionBar />
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-6 sm:px-6">{children}</main>
    </div>
  );
}
