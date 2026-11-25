"use client";

import { ArrowRight, Menu } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useSelectedLayoutSegment } from "next/navigation";

import type { ProtocolView, RunSummary } from "@/api/client";
import type { Session } from "@/auth/session";
import { SessionMenu } from "@/components/SessionMenu";
import { ModeBadge } from "@/components/ui/ui";

export function RunContextBar({
  run,
  protocolStatus,
  session,
  signOutAction,
  onOpenMobileNav,
}: {
  run: RunSummary;
  protocolStatus?: ProtocolView["status"] | null;
  session: Session | null;
  signOutAction: () => Promise<void>;
  onOpenMobileNav: () => void;
}) {
  const t = useTranslations("runHeader");
  const runs = useTranslations("runs");
  const segment = useSelectedLayoutSegment();

  const base = `/runs/${encodeURIComponent(run.run_id)}`;
  const pkg = run.review_package;

  let nextAction: { href: string; label: string } | null = null;
  if (segment === null) {
    nextAction = { href: `${base}/findings`, label: t("toFindings") };
  } else if (segment === "findings") {
    nextAction = pkg
      ? { href: `${base}/draft`, label: t("toDraft") }
      : { href: `${base}/protocol`, label: t("toProtocol") };
  } else if (segment === "draft") {
    nextAction = { href: `${base}/protocol`, label: t("toProtocol") };
  } else if (segment === "protocol" && protocolStatus === "approved") {
    nextAction = { href: `${base}/execution`, label: t("toExecution") };
  }

  return (
    <header className="sticky top-0 z-30 flex h-12 shrink-0 items-center justify-between gap-3 border-b border-border bg-surface px-3 sm:px-5">
      <div className="flex min-w-0 items-center gap-2.5">
        <button
          type="button"
          onClick={onOpenMobileNav}
          aria-label={t("openNav")}
          className="inline-flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-md border border-border bg-surface text-ink-muted hover:bg-sunken hover:text-ink lg:hidden"
        >
          <Menu className="h-4 w-4" aria-hidden="true" />
        </button>

        <nav aria-label={t("breadcrumb")} className="flex min-w-0 items-center gap-1.5 text-xs">
          <Link href="/" className="hidden text-ink-muted no-underline hover:text-ink sm:inline">
            {t("back")}
          </Link>
          <span aria-hidden="true" className="hidden text-ink-muted sm:inline">
            /
          </span>
          <span title={run.equipment} className="truncate font-bold text-ink tabular-nums">
            {run.equipment}
          </span>
        </nav>

        <ModeBadge>{runs(run.mode)}</ModeBadge>

        {pkg && (
          <span className="hidden items-center gap-1 rounded border border-border bg-sunken px-2 py-0.5 text-[11px] font-medium text-ink-muted tabular-nums xl:inline-flex">
            {`${pkg.doc_id} rev ${pkg.rev} (${pkg.package} ${pkg.version})`}
          </span>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
        {nextAction && (
          <Link
            href={nextAction.href}
            title={nextAction.label}
            className="inline-flex h-8 max-w-[140px] items-center gap-1 rounded-md bg-accent px-2 text-xs font-semibold text-on-accent no-underline transition-colors hover:bg-accent-hover sm:max-w-none sm:gap-1.5 sm:px-3"
          >
            <span className="truncate">{nextAction.label}</span>
            <ArrowRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          </Link>
        )}

        <SessionMenu session={session} signOutAction={signOutAction} />
      </div>
    </header>
  );
}
