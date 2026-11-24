"use client";

import { useState, type ReactNode } from "react";

import type { ProtocolView, RunSummary } from "@/api/client";
import type { Session } from "@/auth/session";
import { RunContextBar } from "@/components/RunContextBar";
import { RunShellProvider, useRunShell } from "@/components/RunShellContext";
import { RunSidebar, type RunSidebarBadges } from "@/components/RunSidebar";

function RunShellInner({
  run,
  badges,
  protocolStatus,
  session,
  signOutAction,
  children,
}: {
  run: RunSummary;
  badges?: RunSidebarBadges;
  protocolStatus?: ProtocolView["status"] | null;
  session: Session | null;
  signOutAction: () => Promise<void>;
  children: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { drawerOpen } = useRunShell();

  return (
    <div className="flex min-h-screen w-full bg-canvas text-ink">
      <RunSidebar
        run={run}
        badges={badges}
        protocolStatus={protocolStatus}
        collapsed={collapsed}
        autoCollapsedForDrawer={drawerOpen}
        onToggleCollapse={() => setCollapsed((c) => !c)}
        mobileOpen={mobileOpen}
        onMobileOpenChange={setMobileOpen}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <RunContextBar
          run={run}
          session={session}
          signOutAction={signOutAction}
          onOpenMobileNav={() => setMobileOpen(true)}
        />
        <main className="min-w-0 flex-1 px-4 py-3 sm:px-5 sm:py-4">{children}</main>
      </div>
    </div>
  );
}

export function RunShell(props: {
  run: RunSummary;
  badges?: RunSidebarBadges;
  protocolStatus?: ProtocolView["status"] | null;
  session: Session | null;
  signOutAction: () => Promise<void>;
  children: ReactNode;
}) {
  return (
    <RunShellProvider>
      <RunShellInner {...props} />
    </RunShellProvider>
  );
}
