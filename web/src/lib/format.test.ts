import { describe, expect, it } from "vitest";

import {
  formatDate,
  formatDayOfYear,
  formatNumber,
  formatPercent,
  formatSigned,
} from "./format";

const EN_DASH = "–";

describe("missing values", () => {
  it.each([null, undefined, Number.NaN])(
    "renders %s as an en dash, never as zero",
    (value) => {
      // A zero and an absence are different claims. serving.wpsr_lines deliberately
      // publishes null rather than 0.0 for a comparison it cannot make, and that
      // distinction has to survive all the way to the screen.
      expect(formatNumber(value)).toBe(EN_DASH);
      expect(formatSigned(value)).toBe(EN_DASH);
      expect(formatPercent(value)).toBe(EN_DASH);
    },
  );

  it("renders a real zero as zero, not as an en dash", () => {
    expect(formatNumber(0)).toBe("0.0");
    expect(formatSigned(0)).toBe("0.0");
  });
});

describe("signed figures", () => {
  it("uses a real minus sign rather than a hyphen", () => {
    expect(formatSigned(-4450)).toBe("−4,450.0");
    expect(formatSigned(-4450)).not.toContain("-");
  });

  it("marks a rise with a plus", () => {
    expect(formatSigned(80)).toBe("+80.0");
  });

  it("appends a per-cent sign only to percentages", () => {
    expect(formatPercent(-18.3)).toBe("−18.3%");
    expect(formatNumber(-18.3)).toBe("-18.3");
  });
});

describe("dates", () => {
  it("uses the house style: no leading zero, short month, no comma", () => {
    expect(formatDate("2026-09-04")).toBe("4 Sept 2026");
  });

  it("renders an unparseable date as an en dash", () => {
    expect(formatDate("not a date")).toBe(EN_DASH);
    expect(formatDate(null)).toBe(EN_DASH);
  });
});

describe("day-of-year labels", () => {
  it("maps doy onto core.seasonal's non-leap reference calendar", () => {
    // REFERENCE_YEAR is 2001, deliberately not a leap year: core.seasonal drops 29
    // February entirely. Using a leap year here would shift every label after February
    // by one day against the band it sits under.
    expect(formatDayOfYear(1)).toBe("1 Jan");
    expect(formatDayOfYear(60)).toBe("1 Mar");
    expect(formatDayOfYear(365)).toBe("31 Dec");
  });
});
