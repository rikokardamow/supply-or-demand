/**
 * Number, unit and date formatting. British English throughout (DEVELOPMENT.md rule 6).
 *
 * Every figure the UI shows goes through here, so "no data" renders one way everywhere:
 * an en dash, never "0", "NaN" or "null". A zero and an absence are different claims.
 */

const EN_DASH = "–";

/** A value, or an en dash when there is none. `maximumFractionDigits` defaults to 1. */
export function formatNumber(
  value: number | null | undefined,
  digits = 1,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EN_DASH;
  return value.toLocaleString("en-GB", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** A signed figure -- "+2.1" / "−4.5". Uses a real minus sign, not a hyphen. */
export function formatSigned(
  value: number | null | undefined,
  digits = 1,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EN_DASH;
  const formatted = Math.abs(value).toLocaleString("en-GB", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  if (value === 0) return formatted;
  return `${value > 0 ? "+" : "−"}${formatted}`;
}

export function formatPercent(
  value: number | null | undefined,
  digits = 1,
): string {
  const formatted = formatSigned(value, digits);
  return formatted === EN_DASH ? formatted : `${formatted}%`;
}

/** "4 Sep 2026" -- the house date style, no leading zero, no comma. */
export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return EN_DASH;
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return EN_DASH;
  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/**
 * A day-of-year on `core.seasonal`'s normalised calendar rendered as a date label.
 *
 * The reference year is 2001 -- a non-leap year, matching `core.seasonal.REFERENCE_YEAR`,
 * which drops 29 February entirely. Using any leap year here would shift every label
 * after February by a day.
 */
export function formatDayOfYear(doy: number): string {
  const date = new Date(Date.UTC(2001, 0, doy));
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}
