// The one timestamp format of every screen: run list, run header, decisions and AI Findings.

const DEFAULT_TIME_ZONE = "Asia/Jakarta";

const ZONE_LABELS: Record<string, string> = {
  "Asia/Jakarta": "WIB",
  "Asia/Makassar": "WITA",
  "Asia/Jayapura": "WIT",
  UTC: "UTC",
};

type Formatters = { date: Intl.DateTimeFormat; time: Intl.DateTimeFormat };
const FORMATTERS = new Map<string, Formatters>();

function formattersFor(timeZone: string): Formatters {
  const cached = FORMATTERS.get(timeZone);
  if (cached) return cached;
  const created: Formatters = {
    date: new Intl.DateTimeFormat("id-ID", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      timeZone,
    }),
    time: new Intl.DateTimeFormat("id-ID", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone,
    }),
  };
  FORMATTERS.set(timeZone, created);
  return created;
}

function shortZoneName(at: Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("id-ID", {
    timeZone,
    timeZoneName: "short",
  }).formatToParts(at);
  return parts.find((p) => p.type === "timeZoneName")?.value ?? timeZone;
}

/** Options to override the configured display timezone and its short label (primarily for tests). */
export type FormatWhenOptions = {
  timeZone?: string;
  tzLabel?: string;
};

/** The `decisions.when` message, from `useTranslations` or `getTranslations`. */
type When = (key: "when", values: { date: string; time: string; tz: string }) => string;

/** A timestamp as the screens read it ("16/11/2026 16.30 WIB"); the raw value when it does
 * not parse, so one bad value never breaks a screen. `t` is the `decisions` translator. */
export function formatWhen(t: When, iso: string, options?: FormatWhenOptions): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;

  const explicitTz = options?.timeZone?.trim();
  const envTz = process.env.NEXT_PUBLIC_TRACEQ_TIMEZONE?.trim();
  let timeZone = explicitTz || envTz || DEFAULT_TIME_ZONE;

  let formatters: Formatters;
  try {
    formatters = formattersFor(timeZone);
  } catch {
    timeZone = DEFAULT_TIME_ZONE;
    formatters = formattersFor(timeZone);
  }

  const explicitLabel = options?.tzLabel?.trim();
  const envLabel = process.env.NEXT_PUBLIC_TRACEQ_TZ_LABEL?.trim();
  const tz =
    explicitLabel ||
    (!explicitTz ? envLabel : undefined) ||
    ZONE_LABELS[timeZone] ||
    shortZoneName(at, timeZone);

  return t("when", {
    date: formatters.date.format(at),
    time: formatters.time.format(at),
    tz,
  });
}
