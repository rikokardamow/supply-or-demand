import { describe, expect, it } from "vitest";

import { formatNumber, formatSigned } from "@/lib/content";

/**
 * These two decide how every live figure on the landing page reads.
 *
 * They are worth pinning because both encode a house rule rather than a preference, and a
 * plausible-looking "tidy-up" would quietly break either one: an en dash for a missing
 * value is not the same as a zero, and a signed change must carry its sign even when a
 * colour is already saying the same thing.
 */

describe("formatNumber", () => {
  it("holds the requested precision rather than trimming it", () => {
    // Trailing zeros are significant on a price: 71.50 is a two-decimal quote, not 71.5.
    expect(formatNumber(71.5, 2)).toBe("71.50");
    expect(formatNumber(1234.567, 1)).toBe("1,234.6");
    expect(formatNumber(0, 2)).toBe("0.00");
  });

  it("distinguishes no data from zero", () => {
    // An en dash, not "0" and not "" -- a missing observation is not a measured zero, and
    // the whole project refuses to bridge that gap anywhere else either.
    expect(formatNumber(null, 2)).toBe("–");
    expect(formatNumber(Number.NaN, 2)).toBe("–");
  });

  it("groups in en-GB", () => {
    expect(formatNumber(1000000, 0)).toBe("1,000,000");
  });
});

describe("formatSigned", () => {
  it("always carries a sign, because direction is never colour alone", () => {
    expect(formatSigned(1.2, 1)).toBe("+1.2");
    expect(formatSigned(-1.2, 1)).toBe("−1.2");
  });

  it("uses a real minus sign, not a hyphen", () => {
    // U+2212, which aligns with digits in a tabular font; a hyphen-minus does not.
    expect(formatSigned(-3, 0)).toBe("−3");
    expect(formatSigned(-3, 0)).not.toBe("-3");
  });

  it("leaves zero unsigned", () => {
    // "+0.0" claims a rise that did not happen.
    expect(formatSigned(0, 1)).toBe("0.0");
  });

  it("returns nothing at all for no data", () => {
    // Empty rather than an en dash: this sits beside a value that already shows one.
    expect(formatSigned(null, 1)).toBe("");
    expect(formatSigned(Number.NaN, 1)).toBe("");
  });
});
