import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { contrastRatio } from "@/theme/contrast";

const CSS = readFileSync(join(__dirname, "tokens.css"), "utf8");

/** The value of a `--name: value;` declaration in the `:root` block. */
function token(name: string): string {
  const match = new RegExp(`--${name}:\\s*([^;]+);`).exec(CSS);
  if (!match) throw new Error(`token --${name} is not defined in tokens.css`);
  return match[1].trim();
}

/** A `#rrggbb` hex colour as the decimal "r, g, b" triple `rgba()` needs. */
function toRgbTriple(hex: string): string {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!match) throw new Error(`not a 6-digit hex colour: ${hex}`);
  return match
    .slice(1)
    .map((channel) => Number.parseInt(channel, 16))
    .join(", ");
}

describe("chrome tokens", () => {
  it("is the terminal palette", () => {
    expect(token("bg")).toBe("#000000");
    expect(token("surface")).toBe("#0a0b0d");
    expect(token("surface-2")).toBe("#131519");
    expect(token("border")).toBe("#2a2f37");
    expect(token("hairline")).toBe("#16191f");
    expect(token("text")).toBe("#e6e8eb");
    expect(token("muted")).toBe("#9aa2ad");
    expect(token("faint")).toBe("#7d8590");
    expect(token("accent")).toBe("#ff9e1b");
    expect(token("up")).toBe("#16c784");
    // Not #ea3943: that value is 4.495:1 on --surface-2, short of the contrast floor
    // below by the same margin --faint originally missed it by. See tokens.css.
    expect(token("down")).toBe("#ee4a56");
  });

  it("carries the series roles at values that survive a black ground", () => {
    expect(token("navy")).toBe("#4d9fff");
    expect(token("light-blue")).toBe("#9fd8ff");
    expect(token("orange")).toBe("#ffa62b");
    expect(token("red")).toBe("#ff5a4d");
    expect(token("grey")).toBe("#99a3ad");
    expect(token("grid")).toBe("#1e232b");
  });

  it("keeps the rgba channel triples derived from their hex twins, not restated", () => {
    // rgba() cannot interpolate var(--navy)/var(--red) directly, so these triples exist
    // purely to mirror them. The expectation is computed from the hex token itself, not
    // written as a literal here -- a literal pin would keep passing if someone retuned
    // --navy and updated navy-rgb's literal to match, which is exactly the drift this
    // test exists to catch.
    expect(token("navy-rgb")).toBe(toRgbTriple(token("navy")));
    expect(token("red-rgb")).toBe(toRgbTriple(token("red")));
  });

  it("is monospace at 11px", () => {
    expect(token("font")).toContain("JetBrains Mono");
    expect(token("base-font-px")).toBe("11px");
  });

  it("has no radius and no shadow", () => {
    // Kept as tokens rather than deleted so a component naming one does not break.
    for (const name of ["r-sm", "r-md", "r-lg"]) expect(token(name)).toBe("0");
    for (const name of ["shadow-sm", "shadow-md"]) expect(token(name)).toBe("none");
  });
});

describe("contrast floor", () => {
  // Every text token, against every ground it is actually painted on.
  const GROUNDS = ["#000000", "#0a0b0d", "#131519"];

  it.each(["text", "muted", "faint", "accent", "up", "down"])(
    "--%s clears 4.5:1 on every ground",
    (name) => {
      for (const ground of GROUNDS) {
        expect(contrastRatio(token(name), ground)).toBeGreaterThanOrEqual(4.5);
      }
    },
  );

  it.each(["navy", "light-blue", "orange", "red", "grey"])(
    "series --%s is visible on the panel ground",
    (name) => {
      expect(contrastRatio(token(name), "#0a0b0d")).toBeGreaterThanOrEqual(4.5);
    },
  );
});
