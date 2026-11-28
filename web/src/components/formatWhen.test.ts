import { afterEach, describe, expect, test } from "vitest";

import messages from "../../messages/id.json";
import { formatWhen } from "./formatWhen";

function translateWhen(_key: "when", values: { date: string; time: string; tz: string }): string {
  return messages.decisions.when
    .replace("{date}", values.date)
    .replace("{time}", values.time)
    .replace("{tz}", values.tz);
}

describe("formatWhen", () => {
  const prevTz = process.env.NEXT_PUBLIC_TRACEQ_TIMEZONE;
  const prevLabel = process.env.NEXT_PUBLIC_TRACEQ_TZ_LABEL;

  afterEach(() => {
    if (prevTz === undefined) delete process.env.NEXT_PUBLIC_TRACEQ_TIMEZONE;
    else process.env.NEXT_PUBLIC_TRACEQ_TIMEZONE = prevTz;
    if (prevLabel === undefined) delete process.env.NEXT_PUBLIC_TRACEQ_TZ_LABEL;
    else process.env.NEXT_PUBLIC_TRACEQ_TZ_LABEL = prevLabel;
  });

  test("defaults to WIB (Asia/Jakarta, UTC+7)", () => {
    delete process.env.NEXT_PUBLIC_TRACEQ_TIMEZONE;
    delete process.env.NEXT_PUBLIC_TRACEQ_TZ_LABEL;
    expect(formatWhen(translateWhen, "2026-11-16T09:30:00Z")).toBe("16/11/2026 16.30 WIB");
  });

  test("derives WITA, WIT, UTC, and short zone fallback via options", () => {
    expect(
      formatWhen(translateWhen, "2026-11-16T09:30:00Z", { timeZone: "Asia/Makassar" }),
    ).toBe("16/11/2026 17.30 WITA");
    expect(
      formatWhen(translateWhen, "2026-11-16T09:30:00Z", { timeZone: "Asia/Jayapura" }),
    ).toBe("16/11/2026 18.30 WIT");
    expect(
      formatWhen(translateWhen, "2026-11-16T09:30:00Z", { timeZone: "UTC" }),
    ).toBe("16/11/2026 09.30 UTC");
    expect(
      formatWhen(translateWhen, "2026-11-16T09:30:00Z", { timeZone: "Asia/Tokyo" }),
    ).toMatch(/^16\/11\/2026 18\.30 \S+$/);
    expect(
      formatWhen(translateWhen, "2026-11-16T09:30:00Z", {
        timeZone: "Asia/Jakarta",
        tzLabel: "JKT",
      }),
    ).toBe("16/11/2026 16.30 JKT");
  });

  test("reads NEXT_PUBLIC_TRACEQ_TIMEZONE and NEXT_PUBLIC_TRACEQ_TZ_LABEL dynamically", () => {
    process.env.NEXT_PUBLIC_TRACEQ_TIMEZONE = "UTC";
    expect(formatWhen(translateWhen, "2026-11-16T09:30:00Z")).toBe("16/11/2026 09.30 UTC");

    process.env.NEXT_PUBLIC_TRACEQ_TIMEZONE = "Asia/Makassar";
    process.env.NEXT_PUBLIC_TRACEQ_TZ_LABEL = "WITA-CUSTOM";
    expect(formatWhen(translateWhen, "2026-11-16T09:30:00Z")).toBe(
      "16/11/2026 17.30 WITA-CUSTOM",
    );
  });

  test("returns the raw value when the timestamp does not parse", () => {
    expect(formatWhen(translateWhen, "not-a-timestamp")).toBe("not-a-timestamp");
  });
});
