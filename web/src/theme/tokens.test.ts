import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Every design token a component asks for must actually exist.
 *
 * CSS fails silently here in a way that is easy to ship: referencing an undefined custom
 * property makes the *whole declaration* invalid, so `borderBottom: "1px solid
 * var(--rule)"` does not fall back to a default border — it draws no border at all, with
 * no console warning and no build error. TypeScript cannot help, because the token name is
 * just a string.
 *
 * This bit for real. `tokens.css` was rewritten for the product UI and several variables
 * were renamed — `--rule` became `--border`, `--ink` became `--text`, and the two font
 * stacks collapsed into one `--font`. Five files were never updated, so a table border in
 * HeatTable, row rules on /events and /sanctions, the heading face in NotBuiltYet and the
 * active-ticker underline on /prices had all been rendering as nothing. A peer session
 * found two of them by eye; this test found the rest.
 */

const SRC = join(import.meta.dirname, "..");
const TOKENS = join(SRC, "theme", "tokens.css");

/**
 * Tokens that are legitimately defined somewhere other than `tokens.css`.
 *
 * Deliberately a short, justified list rather than a general escape hatch — anything added
 * here needs a reason, because the whole value of this test is that the default answer is
 * "define it in tokens.css".
 */
const DEFINED_ELSEWHERE = new Set([
  // Injected on <html> by next/font in app/layout.tsx, which owns the self-hosted file.
  "--font-inter",
  // Set inline per element by TickerRail, so the flash tints with the direction of the
  // move it is announcing. It has no sensible global value.
  "--flash-tone",
]);

function walk(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return walk(path);
    // Test files are excluded, this one included: it quotes token names in prose to
    // explain the bug it guards against, and would otherwise report itself.
    if (/\.test\.tsx?$/.test(entry.name)) return [];
    return /\.(tsx?|css)$/.test(entry.name) ? [path] : [];
  });
}

function definedTokens(): Set<string> {
  const css = readFileSync(TOKENS, "utf8");
  return new Set(
    [...css.matchAll(/^\s*(--[a-z0-9-]+)\s*:/gm)].map((m) => m[1]),
  );
}

describe("design tokens", () => {
  const defined = definedTokens();

  it("defines a reasonable number of tokens", () => {
    // A sanity check on the parser itself: if the regex ever stops matching, every
    // reference below would pass vacuously and the test would go quietly useless.
    expect(defined.size).toBeGreaterThan(30);
  });

  it("has no reference to a token that is never defined", () => {
    const missing: string[] = [];

    for (const file of walk(SRC)) {
      const source = readFileSync(file, "utf8");
      for (const match of source.matchAll(/var\((--[a-z0-9-]+)/g)) {
        const token = match[1];
        if (defined.has(token) || DEFINED_ELSEWHERE.has(token)) continue;
        missing.push(
          `${file.slice(SRC.length + 1).replace(/\\/g, "/")}: ${token}`,
        );
      }
    }

    expect([...new Set(missing)]).toEqual([]);
  });
});
