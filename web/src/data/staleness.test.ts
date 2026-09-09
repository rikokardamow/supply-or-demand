import { describe, expect, it } from "vitest";

import { isStale } from "./staleness";

const NOW = new Date("2026-09-09T12:00:00Z");

describe("isStale", () => {
  it("measures against the data's own as-of, not the publish time", () => {
    // The case the badge exists for: a pipeline that republishes an unchanged lake every
    // night has a fresh published_at and stale data. serving.spreads is exactly this --
    // its EIA source stopped in April 2024, but publish_curve runs nightly.
    expect(isStale("curve", "2024-04-05T00:00:00Z", NOW)).toBe(true);
  });

  it("does not flag the current WPSR report, which is always ~12 days old as data", () => {
    // The real trap, measured live 2026-09-09: the newest report EIA had published was
    // for the week ending 28 August, making it 12.6 days old. Spec 32 §5's 8-day figure
    // measures ingestion age, not data age, and would have greyed the flagship panel
    // while it showed the freshest data in existence.
    expect(isStale("wpsr", "2026-08-28T00:00:00Z", NOW)).toBe(false);
    // A genuinely missed release -- three weeks with no new report -- still flags.
    expect(isStale("wpsr", "2026-08-14T00:00:00Z", NOW)).toBe(true);
  });

  it("absorbs GIE's own two-day publication lag", () => {
    expect(isStale("gie", "2026-09-07T00:00:00Z", NOW)).toBe(false);
    expect(isStale("gie", "2026-09-02T00:00:00Z", NOW)).toBe(true);
  });

  it("does not grey a panel whose cadence nobody has recorded", () => {
    // Defaulting an unknown pipeline to stale would present a guess as a finding.
    expect(isStale("a-pipeline-with-no-threshold", "2020-01-01T00:00:00Z", NOW)).toBe(
      false,
    );
  });

  it("treats a missing as-of as unknown rather than stale", () => {
    expect(isStale("wpsr", null, NOW)).toBe(false);
    expect(isStale(null, "2020-01-01T00:00:00Z", NOW)).toBe(false);
  });
});
