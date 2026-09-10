import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
  heatWash,
  PANEL_GROUND_RGB,
  washChroma,
} from "@/components/tables/HeatTable";
import { contrastRatio } from "@/theme/contrast";

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
 * The cause is arithmetic. A wash is an alpha blend onto the panel ground, and the chroma
 * it produces depends on how each channel of the source colour sits relative to that
 * ground -- not, as a first (wrong) pass at this fix assumed, simply on the source
 * colour's own channel spread. Getting the ground wrong doesn't throw; it silently
 * re-derives the old defect at a different ratio, which is why washChroma's ground is
 * pinned against tokens.css below and the ramp's chroma is pinned as literal numbers
 * computed independently of washChroma, not just re-measured through it.
 */

const CSS = readFileSync(join(import.meta.dirname, "..", "..", "theme", "tokens.css"), "utf8");

/** The value of a `--name: value;` declaration in tokens.css's `:root` block. */
function token(name: string): string {
  const match = new RegExp(`--${name}:\\s*([^;]+);`).exec(CSS);
  if (!match) throw new Error(`token --${name} is not defined in tokens.css`);
  return match[1].trim();
}

/** A `#rrggbb` hex colour as the decimal "r, g, b" triple washChroma/rgba() need. */
function toRgbTriple(hex: string): string {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!match) throw new Error(`not a 6-digit hex colour: ${hex}`);
  return match
    .slice(1)
    .map((channel) => Number.parseInt(channel, 16))
    .join(", ");
}

/**
 * The true composite of a wash against a ground, as a `#rrggbb` hex -- for the legibility
 * test below, which needs a real colour to feed to `contrastRatio`, not just a chroma
 * number. Deliberately a second, independent implementation of the blend rather than a
 * call into `washChroma`: the legibility test exists to check the actual painted colour,
 * so it should not inherit a bug from the function it is meant to catch regressions in.
 */
function compositeHex(wash: { rgb: string; alpha: number }, groundRgb: string): string {
  const c = wash.rgb.split(",").map((n) => Number(n.trim()));
  const g = groundRgb.split(",").map((n) => Number(n.trim()));
  const blended = c.map((ci, i) =>
    Math.round(ci * wash.alpha + g[i] * (1 - wash.alpha)),
  );
  return `#${blended.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

/**
 * Distances from the median that should look equally strong in either direction --
 * the threshold itself (`heatWash` washes AT 10, only excludes BELOW it), several mid
 * points, the saturation cap, and past the cap, so no sample set can dodge either end of
 * the ramp the way an earlier version of this test did.
 */
const DISTANCES = [10, 17.5, 25, 32.5, 40, 45];

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
    // Navy at the alpha the old ramp used, against red at the same alpha, both composited
    // against the real panel ground. The bound is 0.6, not the original 0.5: that number
    // was measured through the old (wrong) c*alpha blend, and the true composite against
    // rgb(10,11,13) narrows the gap between the two old colours somewhat -- but old navy
    // is still unmistakably the weaker of the two (ratio ~0.55), which is all this test
    // needs to prove.
    const navy = washChroma({ rgb: "15, 42, 74", alpha: 0.169 });
    const red = washChroma({ rgb: "192, 57, 43", alpha: 0.169 });
    expect(navy / red).toBeLessThan(0.6);
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

  it("pins the true-composite chroma at the ramp's ends, independent of washChroma's own arithmetic", () => {
    // The property test above measures parity THROUGH washChroma -- fine once washChroma
    // composites against the real ground, but it shares whatever bug washChroma has: if
    // the blend ever regresses to `c * alpha`, the function and the property test drift
    // together and both stay green, which is exactly how three earlier passes agreed on a
    // wrong 7.7% figure. These fixtures are computed by hand against g = rgb(10,11,13)
    // (--surface), not by calling washChroma, so they fail on that regression even though
    // the property test wouldn't.
    //
    // blended_channel = g + (c - g) * alpha; chroma = max(blended) - min(blended).
    //   surplus @ threshold (rgb 77,159,255, alpha 0.152):
    //     R 10+67*.152=20.18, G 11+148*.152=33.50, B 13+242*.152=49.78 -> chroma 29.60
    //   deficit @ threshold (rgb 255,90,77, alpha 0.18):
    //     R 10+245*.18=54.10, G 11+79*.18=25.22, B 13+64*.18=24.52   -> chroma 29.58
    //   surplus @ cap (alpha 0.504):
    //     R 10+67*.504=43.77, G 11+148*.504=85.59, B 13+242*.504=134.97 -> chroma 91.20
    //   deficit @ cap (alpha 0.52):
    //     R 10+245*.52=137.40, G 11+79*.52=52.08, B 13+64*.52=46.28  -> chroma 91.12
    expect(washChroma(heatWash(10)!)).toBeCloseTo(29.6, 2);
    expect(washChroma(heatWash(-10)!)).toBeCloseTo(29.58, 2);
    expect(washChroma(heatWash(40)!)).toBeCloseTo(91.2, 2);
    expect(washChroma(heatWash(-40)!)).toBeCloseTo(91.12, 2);
  });

  it("keeps the panel-ground constant identical to --surface", () => {
    // washChroma's blend is only correct if this constant tracks --surface. Read out of
    // tokens.css, not restated, so a retuned --surface silently mismatching this literal
    // fails loudly -- the same pattern as plotly.test.ts's chart-ground guard and
    // tokens.pins.test.ts's --navy-rgb derivation.
    expect(PANEL_GROUND_RGB).toBe(toRgbTriple(token("surface")));
  });

  it("keeps both washes dark enough to read light text on", () => {
    // The mirror of the light UI's assertion, and it has to be the mirror rather than the
    // same numbers: there the figure was dark text on a pale wash and the wash had to stay
    // light; here it is --text on a wash over near-black, so the wash must stay DARK. The
    // real property is contrast, not a blended-channel ceiling: `max(blended) < 150`
    // shared washChroma's old c*alpha bug and was itself only a proxy. This asserts the
    // actual WCAG contrast of the STRONGEST wash of each sign (magnitude 45, past the
    // saturation cap, so alpha is at its maximum) against --text, read from tokens.css.
    const text = token("text");
    const ground = token("surface");
    for (const pct of [45, -45]) {
      const wash = heatWash(pct)!;
      const hex = compositeHex(wash, toRgbTriple(ground));
      expect(contrastRatio(text, hex)).toBeGreaterThanOrEqual(4.5);
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
    const pattern = (name: string): RegExp =>
      // `\\s`, not `\s`: inside a template literal the single-backslash form is an
      // unrecognised escape, so JS drops the backslash and the compiled pattern becomes
      // `--navy-rgb:s*([^;]+);`. That matched tokens.css's real declarations only by
      // accident -- there is always a space after the colon, so `s*` matches zero
      // occurrences and `[^;]+` absorbs the space instead, which `.trim()` then removes.
      // It breaks the instant a value's first character sits flush against the colon: see
      // the round-trip check below. The sibling in tokens.pins.test.ts already gets this
      // right with `\\s`.
      new RegExp(`--${name}:\\s*([^;]+);`);
    const localToken = (name: string): string => {
      const match = pattern(name).exec(css);
      if (!match) throw new Error(`token --${name} is not defined in tokens.css`);
      return match[1].trim();
    };

    // Prove the matcher itself is correct, not merely that it happens to work on today's
    // tokens.css: a value with no space after the colon, whose first character is "s" --
    // exactly what the broken `s*` pattern would eat -- must still round-trip exactly.
    const roundTrip = pattern("foo").exec("--foo:sans-serif;")?.[1].trim();
    expect(roundTrip).toBe("sans-serif");

    expect(heatWash(45)!.rgb).toBe(localToken("navy-rgb"));
    expect(heatWash(-45)!.rgb).toBe(localToken("red-rgb"));
  });
});
