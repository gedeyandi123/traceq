"use client";

import {
  ArchiveX,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  FileSearch,
  FileWarning,
  PlayCircle,
  Table2,
  X,
} from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useSelectedLayoutSegment } from "next/navigation";
import { Dialog } from "radix-ui";

import type { ProtocolView, RunSummary } from "@/api/client";
import { BrandMark } from "@/components/BrandMark";
import { ProtocolStatusBadge } from "@/components/ui/StatusBadge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/Tooltip";

export type RunNavKey = "matrix" | "findings" | "draft" | "protocol" | "leftOut" | "eval";

export type RunSidebarBadges = {
  matrix?: number;
  findings?: number;
  draft?: number;
};

const SEGMENT_TO_KEY: Record<string, RunNavKey> = {
  findings: "findings",
  draft: "draft",
  protocol: "protocol",
  "left-out": "leftOut",
  eval: "eval",
};

type NavItem = {
  key: RunNavKey;
  href: string;
  label: string;
  icon: typeof Table2;
  badge?: number;
  protocolStatus?: ProtocolView["status"] | null;
};

function SidebarNavList({
  run,
  badges,
  protocolStatus,
  collapsed,
  onNavigate,
}: {
  run: RunSummary;
  badges?: RunSidebarBadges;
  protocolStatus?: ProtocolView["status"] | null;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const t = useTranslations("runHeader");
  const segment = useSelectedLayoutSegment();
  const activeKey: RunNavKey = (segment ? SEGMENT_TO_KEY[segment] : undefined) ?? "matrix";
  const base = `/runs/${encodeURIComponent(run.run_id)}`;

  const workflowItems: NavItem[] = [
    { key: "matrix", href: base, label: t("matrixTriage"), icon: Table2, badge: badges?.matrix },
    {
      key: "findings",
      href: `${base}/findings`,
      label: t("findings"),
      icon: FileWarning,
      badge: badges?.findings,
    },
    ...(run.review_package
      ? [
          {
            key: "draft" as const,
            href: `${base}/draft`,
            label: t("draft"),
            icon: FileSearch,
            badge: badges?.draft,
          },
        ]
      : []),
    {
      key: "protocol",
      href: `${base}/protocol`,
      label: t("protocolShort"),
      icon: ClipboardCheck,
      protocolStatus,
    },
  ];

  const auditItems: NavItem[] = [
    { key: "leftOut", href: `${base}/left-out`, label: t("leftOut"), icon: ArchiveX },
    { key: "eval", href: `${base}/eval`, label: t("eval"), icon: BarChart3 },
  ];

  const renderLink = (item: NavItem) => {
    const Icon = item.icon;
    const isActive = item.key === activeKey;
    const linkEl = (
      <Link
        key={item.key}
        href={item.href}
        aria-current={isActive ? "page" : undefined}
        onClick={onNavigate}
        className={`group flex items-center gap-2.5 rounded-md px-2.5 py-2 text-xs font-medium no-underline transition-colors ${
          isActive
            ? "bg-accent-soft font-semibold text-accent"
            : "text-ink-muted hover:bg-sunken hover:text-ink"
        } ${collapsed ? "justify-center px-0" : ""}`}
      >
        <Icon
          className={`h-4 w-4 shrink-0 ${isActive ? "text-accent" : "text-ink-muted group-hover:text-ink"}`}
          aria-hidden="true"
        />
        {!collapsed && <span className="min-w-0 flex-1 truncate">{item.label}</span>}
        {!collapsed && item.badge !== undefined && item.badge > 0 && (
          <span className="inline-flex min-w-5 items-center justify-center rounded-full bg-sunken px-1.5 py-0.5 text-[11px] font-semibold text-ink tabular-nums">
            {item.badge}
          </span>
        )}
        {!collapsed && item.protocolStatus && (
          <ProtocolStatusBadge status={item.protocolStatus} />
        )}
      </Link>
    );

    if (collapsed) {
      return (
        <Tooltip key={item.key}>
          <TooltipTrigger asChild>{linkEl}</TooltipTrigger>
          <TooltipContent side="right">{item.label}</TooltipContent>
        </Tooltip>
      );
    }
    return linkEl;
  };

  return (
    <TooltipProvider delayDuration={200}>
      <nav aria-label={t("tabs")} className="flex flex-1 flex-col gap-5 overflow-y-auto px-2.5 py-3">
        <div className="flex flex-col gap-1">
          {!collapsed && (
            <div className="px-2.5 pb-1 text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
              {t("alurKualifikasi")}
            </div>
          )}
          {workflowItems.map(renderLink)}
          <div
            aria-disabled="true"
            title={t("executionDeviation")}
            className={`flex cursor-not-allowed items-center gap-2.5 rounded-md px-2.5 py-2 text-xs font-medium text-ink-muted/60 ${
              collapsed ? "justify-center px-0" : ""
            }`}
          >
            <PlayCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
            {!collapsed && (
              <>
                <span className="min-w-0 flex-1 truncate">{t("executionDeviation")}</span>
                <span className="rounded border border-border bg-sunken px-1.5 py-0.5 text-[10px] font-semibold text-ink-muted">
                  {t("comingSoon")}
                </span>
              </>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-1 border-t border-border pt-3">
          {!collapsed && (
            <div className="px-2.5 pb-1 text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
              {t("auditDiagnostik")}
            </div>
          )}
          {auditItems.map(renderLink)}
        </div>
      </nav>
    </TooltipProvider>
  );
}

export function RunSidebar({
  run,
  badges,
  protocolStatus,
  collapsed,
  autoCollapsedForDrawer,
  onToggleCollapse,
  mobileOpen,
  onMobileOpenChange,
}: {
  run: RunSummary;
  badges?: RunSidebarBadges;
  protocolStatus?: ProtocolView["status"] | null;
  collapsed: boolean;
  autoCollapsedForDrawer: boolean;
  onToggleCollapse: () => void;
  mobileOpen: boolean;
  onMobileOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("runHeader");
  const app = useTranslations("app");
  const ui = useTranslations("ui");

  const widthClass = collapsed
    ? "w-14"
    : autoCollapsedForDrawer
      ? "w-14 min-[1440px]:w-60"
      : "w-60";

  return (
    <>
      <aside
        className={`hidden shrink-0 flex-col border-r border-border bg-canvas transition-[width] duration-150 lg:sticky lg:top-0 lg:flex lg:h-screen ${widthClass}`}
      >
        <div
          className={`flex h-12 shrink-0 items-center border-b border-border px-3 ${
            collapsed ? "justify-center" : "justify-between"
          }`}
        >
          {!collapsed && (
            <Link
              href="/"
              className="inline-flex min-w-0 items-center gap-2 text-sm font-bold text-ink no-underline hover:text-accent"
            >
              <BrandMark />
              <span className="truncate">{app("title")}</span>
            </Link>
          )}
          <button
            type="button"
            data-tw=""
            onClick={onToggleCollapse}
            aria-label={collapsed ? t("expandSidebar") : t("collapseSidebar")}
            className="inline-flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-md border border-border bg-surface text-ink-muted hover:bg-sunken hover:text-ink"
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        </div>

        <SidebarNavList
          run={run}
          badges={badges}
          protocolStatus={protocolStatus}
          collapsed={collapsed}
        />
      </aside>

      <Dialog.Root open={mobileOpen} onOpenChange={onMobileOpenChange}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-ink/25 backdrop-blur-[1px] lg:hidden" />
          <Dialog.Content className="fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col border-r border-border bg-canvas text-ink shadow-2xl outline-none lg:hidden">
            <div className="flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
              <Dialog.Title className="m-0 flex items-center gap-2 text-sm font-bold text-ink">
                <BrandMark />
                <span>{app("title")}</span>
              </Dialog.Title>
              <Dialog.Description className="sr-only">{t("tabs")}</Dialog.Description>
              <Dialog.Close asChild>
                <button
                  type="button"
                  data-tw=""
                  aria-label={ui("closePanel")}
                  className="inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-md border border-border bg-surface text-ink-muted hover:bg-sunken hover:text-ink"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </Dialog.Close>
            </div>
            <SidebarNavList
              run={run}
              badges={badges}
              protocolStatus={protocolStatus}
              collapsed={false}
              onNavigate={() => onMobileOpenChange(false)}
            />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
