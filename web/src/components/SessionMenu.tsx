"use client";

import { ChevronDown, LogOut, UserRoundCog } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname } from "next/navigation";

import type { Session } from "@/auth/session";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w.charAt(0))
    .join("")
    .toUpperCase();
}

export function SessionMenu({
  session,
  signOutAction,
}: {
  session: Session | null;
  signOutAction: () => Promise<void>;
}) {
  const t = useTranslations("signin");
  const ui = useTranslations("ui");
  const pathname = usePathname();
  const signInHref = pathname && pathname !== "/signin"
    ? `/signin?next=${encodeURIComponent(pathname)}`
    : "/signin";

  if (session === null) {
    return (
      <Link
        href={signInHref}
        className="inline-flex h-8 items-center rounded-md border border-border bg-surface px-3 text-xs font-semibold text-ink no-underline transition-colors hover:bg-sunken"
      >
        {t("link")}
      </Link>
    );
  }

  const roleLabel = session.mayDecide
    ? t("canDecide")
    : session.mayApprove
      ? t("canApprove")
      : t("readOnly");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="inline-flex h-8 cursor-pointer items-center gap-2 rounded-md border border-border bg-surface px-2.5 text-xs font-medium text-ink transition-colors hover:bg-sunken"
        >
          <span
            aria-hidden="true"
            className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[10px] font-bold text-accent"
          >
            {initials(session.name)}
          </span>
          <span className="hidden max-w-[160px] truncate font-semibold sm:inline">
            {session.name}
          </span>
          <span className="hidden rounded border border-border bg-sunken px-1.5 py-0.5 text-[10px] font-semibold text-ink-muted md:inline">
            {roleLabel}
          </span>
          <ChevronDown className="h-3.5 w-3.5 text-ink-muted" aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel className="flex flex-col gap-0.5">
          <span className="text-xs font-semibold text-ink">{session.name}</span>
          <span className="text-[11px] font-normal text-ink-muted">{roleLabel}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href={signInHref} className="no-underline">
            <UserRoundCog className="h-3.5 w-3.5" aria-hidden="true" />
            <span>{ui("switchPersona")}</span>
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() => {
            void signOutAction();
          }}
        >
          <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
          <span>{t("out")}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
