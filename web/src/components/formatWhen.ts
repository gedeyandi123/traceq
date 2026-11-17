// The one timestamp format of every screen: run list, run header, decisions and AI Findings.

const date = new Intl.DateTimeFormat("id-ID", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  timeZone: "UTC",
});
const time = new Intl.DateTimeFormat("id-ID", {
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
});

/** The `decisions.when` message, from `useTranslations` or `getTranslations`. */
type When = (key: "when", values: { date: string; time: string }) => string;

/** A timestamp as the screens read it ("16/11/2026 09.30 UTC"); the raw value when it does
 * not parse, so one bad value never breaks a screen. `t` is the `decisions` translator. */
export function formatWhen(t: When, iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  return t("when", { date: date.format(at), time: time.format(at) });
}
