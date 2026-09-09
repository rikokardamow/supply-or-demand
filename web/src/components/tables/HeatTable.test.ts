import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { heatWash, washChroma } from "@/components/tables/HeatTable";

/**
 * The two directions of the heat wash must carry equal visual weight.
 *
 * This is not a style preference, it is the difference between a column a reader can scan
 * and one they can only half scan. Measured off the live `/balances` table before the fix:
 * deficits rendered at chroma 19-41 and surpluses at 5-9, while contrast was comparable at
 * 1.39 against 1.52. So the asymmetry was saturation rather than lightness, and the
 * practical effect was that every draw stood out and every build disappeared into what
 * looked like unstyled grey shading.
 *
 * The cause is arithmetic. A wash is an alpha blend onto white, and the chroma it produces
 * scales with how unevenly the source colour's channels sit below white. The old surplus
 * colour was the chart navy #0f2a4a, which sits 240/213/181 below white -- a spread of 59
 * against red's 149 -- so it produced 40% of red's colour at identical alpha.
 */

/** Distances from the median that should look equally strong in either direction. */
const DISTANCES = [12, 16, 22, 30, 45];

describe("heat wash", () => {
  it("gives a surplus and a deficit the same chroma at the same distance", () => {
    for (const pct of DISTANCES) {
      const surplus = heatWash(pct);
      const deficit = heatWash(-pct);
      expect(surplus).not.toBeNull();
      expect(deficit).not.toBeNull();

      const ratio = washChroma(surplus!) / washChroma(deficit!);
      // Within 10%. Exact parity is not achievable with two real colours across the whole
      // ramp, and is not the point -- the point is that neither direction can quietly
      // become half as visible as the other again.
      expect(ratio).toBeGreaterThan(0.9);
      expect(ratio).toBeLessThan(1.1);
    }
  });

  it("would have failed against the old navy surplus colour", () => {
    // The regression this test exists for, stated as arithmetic rather than as a memory.
    // Navy at the alpha the old ramp used, against red at the same alpha.
    const navy = washChroma({ rgb: "15, 42, 74", alpha: 0.169 });
    const red = washChroma({ rgb: "192, 57, 43", alpha: 0.169 });
    expect(navy / red).toBeLessThan(0.5);
  });

  it("draws nothing inside the threshold, and saturates beyond the cap", () => {
    expect(heatWash(9.9)).toBeNull();
    expect(heatWash(-9.9)).toBeNull();
    expect(heatWash(null)).toBeNull();
    expect(heatWash(Number.NaN)).toBeNull();

    // Past the saturation point the ramp stops climbing, so a -400% outlier cannot paint a
    // cell darker than a -40% one and imply a difference the scale does not encode.
    expect(heatWash(-40)!.alpha).toBeCloseTo(heatWash(-400)!.alpha, 10);
    expect(heatWash(40)!.alpha).toBeCloseTo(heatWash(400)!.alpha, 10);
  });

  it("keeps both washes dark enough to read light text on", () => {
    // The mirror of the light UI's assertion, and it has to be the mirror rather than the
    // same numbers: there the figure was dark text on a pale wash and the wash had to stay
    // light; here it is --text #e6e8eb on a wash over near-black, so the wash must stay
    // DARK. Carrying the old `> 170` across unchanged would have failed for the right
    // reason and been "fixed" by loosening it, which is how a legibility test quietly
    // stops testing legibility.
    for (const pct of [45, -45]) {
      const wash = heatWash(pct)!;
      const channels = wash.rgb.split(",").map((n) => Number(n.trim()));
      const blended = channels.map((c) => c * wash.alpha);
      expect(Math.max(...blended)).toBeLessThan(150);
    }
  });

  it("keeps the numeric wash colours identical to the channel tokens", () => {
    // HeatTable carries the channels as numbers because washChroma must do arithmetic on
    // them, while the emitted CSS uses var(--navy-rgb)/var(--red-rgb) so no component
    // hardcodes a colour. Two representations of one value drift unless something asserts
    // they agree -- and a drift here paints a colour the palette no longer contains, with
    // every other test still green.
    const css = readFileSync(
      join(import.meta.dirname, "..", "..", "theme", "tokens.css"),
      "utf8",
    );
    const token = (name: string): string => {
      const match = new RegExp(`--${name}:\s*([^;]+);`).exec(css);
      if (!match) throw new Error(`token --${name} is not defined in tokens.css`);
      return match[1].trim();
    };
    expect(heatWash(45)!.rgb).toBe(token("navy-rgb"));
    expect(heatWash(-45)!.rgb).toBe(token("red-rgb"));
  });
});
