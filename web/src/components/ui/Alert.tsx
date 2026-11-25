import { AlertCircle, AlertTriangle, CheckCircle2, Info } from "lucide-react";
import type { ReactNode } from "react";

export type AlertTone = "info" | "warn" | "fail" | "pass";

const TONE_CLASSES: Record<AlertTone, string> = {
  info: "border-info-edge bg-info-soft text-info",
  warn: "border-warn-edge bg-warn-soft text-warn",
  fail: "border-fail-edge bg-fail-soft text-fail",
  pass: "border-pass-edge bg-pass-soft text-pass",
};

const TONE_ICONS: Record<AlertTone, typeof Info> = {
  info: Info,
  warn: AlertTriangle,
  fail: AlertCircle,
  pass: CheckCircle2,
};

export function Alert({
  tone = "info",
  role,
  title,
  children,
  className,
}: {
  tone?: AlertTone;
  role?: "alert" | "status";
  title?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const Icon = TONE_ICONS[tone];
  return (
    <div
      role={role}
      className={`flex items-start gap-2.5 rounded-lg border px-3.5 py-2.5 text-xs ${TONE_CLASSES[tone]} ${className ?? ""}`.trim()}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        {title !== undefined && <p className="m-0 font-semibold text-ink">{title}</p>}
        <div className={title !== undefined ? "mt-0.5 text-ink-muted" : "text-ink"}>
          {children}
        </div>
      </div>
    </div>
  );
}
