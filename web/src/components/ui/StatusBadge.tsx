"use client";

import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  CircleDashed,
  Clock,
  HelpCircle,
  MapPin,
  Pencil,
  Send,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import { useTranslations } from "next-intl";

import type { CoverageClass } from "@/api/client";

export type CoverageBadgeKey = CoverageClass | "none";

const COVERAGE_STYLE: Record<
  CoverageBadgeKey,
  { badgeClass: string; icon: typeof CheckCircle2 }
> = {
  covered_by_vendor: {
    badgeClass: "bg-cov-covered-bg text-cov-covered-fg border-cov-covered-edge",
    icon: CheckCircle2,
  },
  partial: {
    badgeClass: "bg-cov-partial-bg text-cov-partial-fg border-cov-partial-edge",
    icon: AlertTriangle,
  },
  site_only: {
    badgeClass: "bg-cov-site-bg text-cov-site-fg border-cov-site-edge",
    icon: MapPin,
  },
  gap: {
    badgeClass: "bg-cov-gap-bg text-cov-gap-fg border-cov-gap-edge",
    icon: XCircle,
  },
  conflict: {
    badgeClass: "bg-cov-conflict-bg text-cov-conflict-fg border-cov-conflict-edge",
    icon: ShieldAlert,
  },
  none: {
    badgeClass: "bg-cov-none-bg text-cov-none-fg border-cov-none-edge",
    icon: HelpCircle,
  },
};

export function CoverageStatusBadge({
  coverage,
  size = "sm",
}: {
  coverage: CoverageBadgeKey;
  size?: "xs" | "sm";
}) {
  const t = useTranslations("ui.coverage");
  const cfg = COVERAGE_STYLE[coverage];
  const Icon = cfg.icon;
  const sizing = size === "xs" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-0.5 text-xs";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-semibold whitespace-nowrap ${sizing} ${cfg.badgeClass}`}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span>{t(coverage)}</span>
    </span>
  );
}

export type DecisionStateBadgeKey =
  | "undecided"
  | "decided"
  | "changed"
  | "accepted"
  | "edited"
  | "rejected";

const DECISION_STYLE: Record<
  DecisionStateBadgeKey,
  { badgeClass: string; icon: typeof CheckCircle2 }
> = {
  undecided: {
    badgeClass: "bg-sunken text-ink-muted border-border-strong",
    icon: CircleDashed,
  },
  decided: {
    badgeClass: "bg-pass-soft text-pass border-pass-edge",
    icon: CheckCircle2,
  },
  changed: {
    badgeClass: "bg-warn-soft text-warn border-warn-edge",
    icon: Clock,
  },
  accepted: {
    badgeClass: "bg-pass-soft text-pass border-pass-edge",
    icon: CheckCircle2,
  },
  edited: {
    badgeClass: "bg-info-soft text-info border-info-edge",
    icon: Pencil,
  },
  rejected: {
    badgeClass: "bg-fail-soft text-fail border-fail-edge",
    icon: XCircle,
  },
};

export function DecisionStateBadge({ state }: { state: DecisionStateBadgeKey }) {
  const t = useTranslations("ui.decisionStates");
  const cfg = DECISION_STYLE[state];
  const Icon = cfg.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap ${cfg.badgeClass}`}
    >
      <Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
      <span>{t(state)}</span>
    </span>
  );
}

export type ProtocolStatusBadgeKey = "draft" | "submitted" | "approved" | "withdrawn";

const PROTOCOL_STYLE: Record<
  ProtocolStatusBadgeKey,
  { badgeClass: string; icon: typeof CheckCircle2 }
> = {
  draft: {
    badgeClass: "bg-warn-soft text-warn border-warn-edge",
    icon: Clock,
  },
  submitted: {
    badgeClass: "bg-info-soft text-info border-info-edge",
    icon: Send,
  },
  approved: {
    badgeClass: "bg-pass-soft text-pass border-pass-edge",
    icon: CheckCircle2,
  },
  withdrawn: {
    badgeClass: "bg-sunken text-ink-muted border-border-strong",
    icon: Archive,
  },
};

export function ProtocolStatusBadge({ status }: { status: ProtocolStatusBadgeKey }) {
  const t = useTranslations("ui.protocolStatuses");
  const cfg = PROTOCOL_STYLE[status];
  const Icon = cfg.icon;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap ${cfg.badgeClass}`}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span>{t(status)}</span>
    </span>
  );
}
