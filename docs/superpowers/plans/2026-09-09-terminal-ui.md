# Terminal UI Implementation Plan

> **REINSTATED 2026-09-09.** Briefly superseded when the user chose to keep the light
> product UI, then reinstated the same day — "blog page as magazine, data as Terminal",
> confirmed directly. **The direction has moved four times; production is live.** So this
> builds on branch `design/terminal-ui` in a separate worktree, and **the merge to `main`
> is the user's call, not the executor's** — merging is what switches a public site.
>
> Base: `cbea90f`. Revised against the live tree on reinstatement — see "Revisions on
> reinstatement" at the foot of this plan before starting Task 1. Three things changed
> under this plan while it was shelved and the tasks below already account for them.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle `web/` (Next.js, data.kardamow.com) into a Bloomberg-style terminal — black ground, monospace, amber accent, zero radius, full-bleed, 11px density — without touching the Streamlit app or `core/design.py`.

**Architecture:** One rewritten token file (`web/src/theme/tokens.css`) plus a small primitive class layer carries the identity; eight chrome/table/chart components move onto it; `theme/plotly.ts` and `VesselMap` get dark treatments. All 14 routes inherit — no route is restyled individually.

**Tech Stack:** Next.js (App Router, React server components), TypeScript, plain CSS custom properties (Tailwind v4 is imported but the design system is hand-rolled CSS), Plotly + MapLibre for charts/maps, Vitest for tests, pnpm.

**Spec:** `docs/superpowers/specs/2026-09-09-terminal-ui-design.md`

## Global Constraints

- **Surface:** `web/` only. Never edit `apps/dashboard/`, `core/design.py`, `core/theme.py`, or `.streamlit/config.toml`. If a Python test goes red, you touched something this plan forbids.
- **Amber is rationed.** `--accent` (`#ff9e1b`) is used as *type* on dark strips. A solid amber block is reserved for exactly two things: the active nav item and a stale-data badge.
- **Direction is carried by sign and colour, never colour alone.** Every figure showing `--up`/`--down` must also show its `+`/`−`.
- **No component hardcodes a colour.** Every hex lives in `tokens.css` or `theme/plotly.ts`.
- **Contrast floor: 4.5:1** for any text token against the ground it sits on. Enforced by test, not by eye.
- **Density:** `--base-font-px: 11px`. Every `--size-*` and `--space-*` token is in `rem` and must be re-derived against the new root — otherwise the result is the old design shrunk 27%.
- **Node/pnpm:** run all `web/` commands from `web/`. `pnpm test` = `vitest run`.
- **Commits:** stage files by name. Never `git add -A` — a peer session may be writing to this tree.

---

## File Structure

**Created:**
- `web/src/theme/contrast.ts` — WCAG relative-luminance and contrast-ratio helpers. Exists so the contrast floor is a test assertion rather than a claim in a comment.
- `web/src/theme/tokens.pins.test.ts` — pins the literal token values and asserts the contrast
  floor. A NEW file: `tokens.test.ts` already exists and is a different, load-bearing test.

**Modified:**
- `web/src/theme/tokens.css` — rewritten (palette, type, density, shape, primitives).
- `web/src/theme/plotly.ts` — dark layout, lifted series values, corrected header comment.
- `web/src/app/globals.css` — `main` loses the measure; the obsolete "no dark-mode block" comment is rewritten.
- `web/src/components/chrome/{NavBar,Masthead,TickerRail,PageHeader,Panel,StatStrip,ScreenCard,NotBuiltYet}.tsx`
- `web/src/components/tables/HeatTable.tsx`
- `web/src/components/charts/{ChartControls,SeasonalChart}.tsx`
- `web/src/components/map/VesselMap.tsx`
- `web/src/app/page.tsx`, `web/src/app/sanctions/page.tsx` — the two routes with hardcoded colour.
- `web/CLAUDE.md`, `CHANGELOG.md`

**Deliberately untouched:** all 14 route files except the two named above; every `src/data/**` query; `src/lib/format.ts`.

---

## Task 1: Token foundation and the contrast test

The whole identity lands here. Everything after this is components consuming these values.

**Files:**
- Create: `web/src/theme/contrast.ts`
- Create: `web/src/theme/tokens.pins.test.ts`
- Modify: `web/src/theme/tokens.css` (full rewrite)

> **Do not touch `web/src/theme/tokens.test.ts`.** It did not exist when this plan was
> written and now does (`7a6ad3e`, `a2ce7ee`): it walks every `.ts/.tsx/.css` under `src/`
> and asserts each `var(--x)` resolves against `tokens.css`, with a two-entry documented
> allowlist. It is the guard that caught five dead tokens, and this restyle renames tokens
> wholesale, so **it is the single most valuable test in the repo for this task.** Expect it
> to go red the moment you rename a token without updating its callers — that is the test
> working, not a problem to route around. The new pinning/contrast assertions go in a
> **separate** file so the two concerns stay separate and neither clobbers the other.

**Interfaces:**
- Consumes: nothing.
- Produces: `luminance(hex: string): number`, `contrastRatio(a: string, b: string): number` from `@/theme/contrast`. Every CSS custom property listed in Step 3 — later tasks reference these by name and must not invent new ones.

- [ ] **Step 1: Write the contrast helper**

Create `web/src/theme/contrast.ts`:

```ts
/**
 * WCAG 2.1 relative luminance and contrast ratio.
 *
 * Here so the design system's contrast floor is an assertion a test can fail on rather
 * than a number written in a comment and trusted. The spec originally recorded `--faint`
 * as ~4.7:1 against black; it is 4.34:1 and fails. Eyes are bad at this.
 */

/** One sRGB channel, 0-255, linearised per WCAG 2.1. */
function channel(value: number): number {
  const s = value / 255;
  return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

/** Relative luminance of a `#rrggbb` colour. Throws on any other format. */
export function luminance(hex: string): number {
  const match = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  if (!match) throw new Error(`not a 6-digit hex colour: ${hex}`);
  const n = Number.parseInt(match[1], 16);
  return (
    0.2126 * channel((n >> 16) & 0xff) +
    0.7152 * channel((n >> 8) & 0xff) +
    0.0722 * channel(n & 0xff)
  );
}

/** Contrast ratio between two `#rrggbb` colours, 1 (identical) to 21 (black on white). */
export function contrastRatio(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}
```

- [ ] **Step 2: Write the failing token test**

Create `web/src/theme/tokens.pins.test.ts` — a **new file**, leaving the existing
`tokens.test.ts` untouched. It reads `tokens.css` as text and pins values literally — deliberately, in the same style as `tests/test_design_tokens.py`: a test that recomputed the values from the file would assert nothing.

```ts
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
```

- [ ] **Step 3: Run it and watch it fail**

```bash
cd web && pnpm test src/theme/tokens.pins.test.ts
```

Expected: FAIL — `tokens.css` still holds the light palette, so `--bg` is `#f4f6f8`, not `#000000`.

- [ ] **Step 4: Rewrite `tokens.css`**

Replace the `:root` block and everything after it. Keep the file's habit of explaining *why* in comments — that is this repo's house style, not decoration.

```css
/**
 * The design system for data.kardamow.com — a terminal.
 *
 * **This surface does not match `core/design.py`, and now differs from it further.** That
 * module measures its chrome against kardamow.substack.com and drives the Streamlit app,
 * which keeps the identity it was restyled to on 2026-09-08. This is a terminal: black
 * ground, one monospace family, amber as the accent, no radius, no shadow, edge to edge.
 *
 * The two surfaces still agree on what the series *mean* — navy is the primary series,
 * orange is always the seasonal median — but no longer on the values. Navy at #0f2a4a is
 * invisible on black. See `theme/plotly.ts` for the full statement of that contract.
 *
 * Amber is rationed. It is type on a dark strip, not a fill. A solid amber block means
 * exactly two things: this nav item is the page you are on, or this data is stale. If
 * amber becomes the ground for every panel header there is nothing louder left for a
 * warning to use.
 */

:root {
  /* Ground and surface. The page is black; a panel is a barely-lifted ground with a
     1px edge. Structure is carried by the edge, never by a shadow. */
  --bg: #000000;
  --surface: #0a0b0d;
  --surface-2: #131519;
  --surface-hover: #131519;

  --border: #2a2f37;
  --border-strong: #3d434d;
  /* Between rows inside a table. Lighter than --border so a table does not read as a
     stack of separate panels. */
  --hairline: #16191f;

  --text: #e6e8eb;
  --muted: #9aa2ad;
  /* 5.63:1 on black. The obvious choice (#6b7280) is 4.34:1 and fails — and this token
     is used at 0.86rem for cadence lines, which is exactly where it matters. */
  --faint: #7d8590;

  --accent: #ff9e1b;
  --accent-soft: #2a1f0a;

  /* Direction. Never the only carrier of meaning: a figure always shows its sign too. */
  --up: #16c784;
  --down: #ee4a56;
  --up-soft: #06251a;
  --down-soft: #2a0f11;

  /* Status: a stale panel. This is the one place a solid amber bar is spent on
     something other than the active nav item. */
  --warn: #ff9e1b;
  --warn-soft: #2a1f0a;

  /* Series (data, not brand) — roles shared with core/design.py, values are ours. */
  --navy: #4d9fff;
  --light-blue: #9fd8ff;
  --red: #ff5a4d;
  --orange: #ffa62b;
  --grey: #99a3ad;
  --band: rgba(160, 170, 185, 0.18);
  --grid: #1e232b;

  /* One family, monospace, for every label, figure, heading and table cell. Inter is
     kept for running prose only — page deks and source notes — because a paragraph set
     in mono is the part of the real terminal worth leaving behind. */
  --font: "JetBrains Mono", "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo,
    Consolas, monospace;
  --font-prose: var(--font-inter), Inter, -apple-system, "Segoe UI", Roboto, Helvetica,
    Arial, sans-serif;
  --base-font-px: 11px;

  /* Re-derived against an 11px root. These are NOT the old rem values: at 11px the old
     scale would render the previous design 27% smaller rather than a denser one. */
  --size-micro: 0.86rem;
  --size-small: 0.95rem;
  --size-body: 1rem;
  --size-lead: 1.09rem;
  --size-panel: 0.95rem;
  --size-stat: 1.55rem;
  --size-page: 1.18rem;
  --size-display: 1.55rem;

  --space-1: 0.18rem;
  --space-2: 0.27rem;
  --space-3: 0.36rem;
  --space-4: 0.55rem;
  --space-5: 0.73rem;
  --space-6: 0.91rem;
  --space-8: 1.09rem;
  --space-12: 1.64rem;

  /* A terminal has no rounded corners. Kept as tokens so a component naming one still
     resolves rather than breaking. */
  --r-sm: 0;
  --r-md: 0;
  --r-lg: 0;
  --r-pill: 0;

  --shadow-sm: none;
  --shadow-md: none;

  /* Full-bleed: kept only so nothing referencing it breaks mid-migration. Task 2 removes
     the last consumer. */
  --measure: 100%;
  --ease: cubic-bezier(0.2, 0, 0.2, 1);
  --duration: 120ms;
}

html {
  font-size: var(--base-font-px);
  scrollbar-gutter: stable;
}

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  font-variant-numeric: tabular-nums;
  margin: 0;
  -webkit-font-smoothing: antialiased;
}

h1,
h2,
h3,
h4 {
  font-family: var(--font);
  color: var(--text);
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: 0.02em;
  margin: 0;
}

p {
  line-height: 1.5;
  margin: 0;
}

a {
  color: inherit;
  text-decoration: none;
}

/* Running prose — a page dek, a source note. The one place Inter survives. */
.prose {
  font-family: var(--font-prose);
  font-variant-numeric: normal;
}

.tabular {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum";
}

/* -- Primitives -------------------------------------------------------------------- */

/* A panel. The unit of the interface: an edge, a ground, and no radius. */
.term-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-collapse: collapse;
}

/* A panel's header strip: amber label left, as-of right. */
.term-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  background: var(--surface-2);
  color: var(--accent);
  font-size: var(--size-micro);
  font-weight: 700;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  padding: var(--space-2) var(--space-4);
  border-bottom: 1px solid var(--border);
}

/* A tiled grid of panels with no gutters — adjacent borders sit flush. */
.term-grid {
  display: grid;
  gap: 0;
}

.term-grid > * {
  border-right: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  min-width: 0;
}

/* One figure in a monitor row: label, value, delta. */
.term-cell {
  padding: var(--space-3) var(--space-4);
}

.term-cell .k {
  color: var(--faint);
  font-size: var(--size-micro);
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.term-cell .v {
  font-size: var(--size-stat);
  font-weight: 700;
  line-height: 1.1;
  margin: var(--space-1) 0;
}

.term-cell .d {
  font-size: var(--size-micro);
}

/* A key: nav item, range switch, series toggle. The active one is the inverted block. */
.term-key {
  display: inline-flex;
  align-items: center;
  border: 0;
  background: none;
  cursor: pointer;
  font-family: var(--font);
  font-size: var(--size-micro);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--muted);
  padding: var(--space-1) var(--space-3);
  white-space: nowrap;
  transition: color var(--duration) var(--ease);
}

.term-key:hover {
  color: var(--text);
}

.term-key[aria-current="page"],
.term-key[aria-pressed="true"] {
  background: var(--accent);
  color: #000000;
  font-weight: 700;
}

.term-key[aria-pressed="false"] {
  color: var(--faint);
  text-decoration: line-through;
}

/* An inverted status bar. Amber for stale; red reserved for a genuine failure. */
.term-bar {
  display: inline-flex;
  align-items: center;
  background: var(--warn);
  color: #000000;
  font-size: var(--size-micro);
  font-weight: 700;
  letter-spacing: 0.05em;
  padding: 0 var(--space-3);
  white-space: nowrap;
}

/* A data table inside a panel. */
.term-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--size-small);
}

.term-table th {
  text-align: right;
  padding: var(--space-2) var(--space-4);
  color: var(--faint);
  font-weight: 400;
  font-size: var(--size-micro);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.term-table td {
  text-align: right;
  padding: var(--space-1) var(--space-4);
  border-bottom: 1px solid var(--hairline);
  white-space: nowrap;
}

.term-table th:first-child,
.term-table td:first-child {
  text-align: left;
}

.term-table tbody tr:hover td {
  background: var(--surface-2);
}

/* -- Motion ------------------------------------------------------------------------ */

/* `.rise` and the card hover-lift are gone: both were product-UI promises that a thing
   is about to move or is clickable. A terminal does not move. `.flash` stays, because a
   value flashing when it ticks is genuine terminal behaviour. */
@keyframes flash {
  from {
    background: color-mix(in srgb, var(--flash-tone) 30%, transparent);
  }
  to {
    background: transparent;
  }
}

.flash {
  animation: flash 700ms var(--ease) both;
}

@media (prefers-reduced-motion: reduce) {
  .flash {
    animation: none;
  }
  * {
    transition-duration: 0.01ms !important;
  }
}

.no-bar {
  scrollbar-width: none;
}

.no-bar::-webkit-scrollbar {
  display: none;
}
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd web && pnpm test src/theme/tokens.pins.test.ts
```

Expected: PASS, all suites. If a contrast assertion fails, **change the token, not the threshold.**

- [ ] **Step 6: Commit**

```bash
cd web && cd .. && git add web/src/theme/tokens.css web/src/theme/contrast.ts web/src/theme/tokens.pins.test.ts && git commit -m "Rewrite the web tokens as a terminal palette

Black ground, one monospace family, amber rationed to type on dark strips, zero radius,
zero shadow, 11px root with the whole rem scale re-derived against it rather than
inherited (which would have shrunk the old design instead of densifying it).

Adds the contrast floor as a test rather than a claim. It immediately earned itself: the
spec recorded --faint #6b7280 as passing at ~4.7:1 against black. It is 4.34:1 and fails.
It is now #7d8590 at 5.63:1."
```

---

## Task 2: Full-bleed layout

Cheaper than the spec estimated: `--measure` has only four consumers, not one per route.

**Files:**
- Modify: `web/src/app/globals.css`
- Modify: `web/src/components/chrome/NavBar.tsx:23`
- Modify: `web/src/components/chrome/PageHeader.tsx:34`
- Modify: `web/src/components/chrome/TickerRail.tsx:128`

**Interfaces:**
- Consumes: the token set from Task 1.
- Produces: no `maxWidth: "var(--measure)"` anywhere in `src/`. Task 9's verification greps for it.

- [ ] **Step 1: Confirm the four consumers, and only four**

```bash
cd web && grep -rn "var(--measure)" src/
```

Expected: exactly 4 hits — `app/globals.css`, `chrome/NavBar.tsx`, `chrome/PageHeader.tsx`, `chrome/TickerRail.tsx`. If there are more, the extras get the same treatment.

- [ ] **Step 2: Take the measure off `main`**

In `web/src/app/globals.css`, replace the `main` rule and the stale comment above it:

```css
/* Full-bleed. Panels tile the window and carry their own edges, so the page has no
   outer gutter to give them — the previous centred measure spent the margins on
   nothing, which is a publication's habit rather than a terminal's. */
main {
  padding: 0;
}
```

Also replace the obsolete comment at the top of the file — it currently explains why there is deliberately no dark mode:

```css
/**
 * The palette is a single dark terminal theme, and every chart component is themed to
 * match it in `@/theme/plotly.ts`. There is no light variant, deliberately: a terminal
 * with a light mode is not the thing this surface is. The real palette lives in
 * `@/theme/tokens.css`.
 */
```

- [ ] **Step 3: Take the measure off the three components**

In each of `NavBar.tsx`, `PageHeader.tsx` and `TickerRail.tsx`, delete the
`maxWidth: "var(--measure)"` and `margin: "0 auto"` lines from the wrapper `style` object.
Leave the `padding` entry in place — Task 3 and Task 4 retune those.

- [ ] **Step 4: Verify nothing references the measure and the app still builds**

```bash
cd web && grep -rn "var(--measure)" src/ ; pnpm build
```

Expected: grep prints nothing; build succeeds.

- [ ] **Step 5: Commit**

```bash
cd .. && git add web/src/app/globals.css web/src/components/chrome/NavBar.tsx web/src/components/chrome/PageHeader.tsx web/src/components/chrome/TickerRail.tsx && git commit -m "Go full-bleed

The measure had four consumers, not one per route. globals.css's comment explaining why
there is deliberately no dark mode is now false and says the opposite."
```

---

## Task 3: The command bar

**Files:**
- Modify: `web/src/components/chrome/NavBar.tsx`
- Modify: `web/src/components/chrome/TickerRail.tsx`

**Interfaces:**
- Consumes: `.term-key`, `.term-bar`, token set from Task 1. `SCREENS` from `@/components/chrome/Masthead` (unchanged — it is the route list, not styling).
- Produces: `NavBar` and `TickerRail` render with no pill, no blur, no radius.

- [ ] **Step 1: Rewrite `NavBar`'s bar and mark**

Replace the `.app-bar` wrapper div's inline style with a flat bar, and the rounded navy mark with a square amber one. The `<h1>` stays — it is the document's only `<h1>` and the heading outline depends on it.

```tsx
export function NavBar({ active }: { active?: string }) {
  return (
    <div
      style={{
        position: "sticky",
        top: 0,
        zIndex: 30,
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        gap: "var(--space-6)",
        padding: "var(--space-2) var(--space-4)",
      }}
    >
      <Link href="/" style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", flexShrink: 0 }}>
        {/* A square, not a rounded tile. The terminal has no radius anywhere else and
            one rounded corner in the top-left reads as an oversight. */}
        <span
          aria-hidden
          style={{
            width: 16,
            height: 16,
            background: "var(--accent)",
            color: "#000",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "var(--size-micro)",
            fontWeight: 700,
          }}
        >
          K
        </span>
        <h1
          style={{
            fontSize: "var(--size-small)",
            fontWeight: 700,
            letterSpacing: "0.08em",
            color: "var(--accent)",
            margin: 0,
          }}
        >
          KARDAMOW
        </h1>
      </Link>

      <nav aria-label="Screens" className="no-bar" style={{ display: "flex", gap: 0, marginLeft: "auto", overflowX: "auto" }}>
        {SCREENS.map((screen) => (
          <Link
            key={screen.href}
            href={screen.href}
            className="term-key"
            aria-current={screen.href === active ? "page" : undefined}
          >
            {screen.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
```

Update the component's docstring: it currently describes "sections as pills" and a translucent blurred bar. Neither is true after this.

- [ ] **Step 2: Retune `TickerRail`**

Give the rail a flat ground, 1px right-borders between symbols, and remove any radius or shadow in its inline styles. Keep its existing data handling and the `.flash` behaviour untouched — only the presentation changes.

- [ ] **Step 3: Verify**

```bash
cd web && pnpm lint && pnpm build
```

Expected: both pass.

- [ ] **Step 4: Commit**

```bash
cd .. && git add web/src/components/chrome/NavBar.tsx web/src/components/chrome/TickerRail.tsx && git commit -m "Make the app bar a command bar"
```

---

## Task 4: Panel and PageHeader

**Files:**
- Modify: `web/src/components/chrome/Panel.tsx`
- Modify: `web/src/components/chrome/PageHeader.tsx`

**Interfaces:**
- Consumes: `.term-panel`, `.term-head`, `.term-bar`, `.prose`.
- Produces: `Panel({title, asOf, sourceNote, stale, pipeline, children})` and `AsOfBadge({asOf, stale, pipeline})` — **signatures unchanged**, so no route needs editing. `PageHeader({active, title, dek})` likewise unchanged.

- [ ] **Step 1: Move `Panel` onto the primitives**

Replace the `className="card"` section with `className="term-panel"`, the inline `<header>` with `className="term-head"`, drop the footer's `borderRadius`, and set the body padding to `var(--space-4)`. The `<h3>` keeps its role in the heading outline.

- [ ] **Step 2: Rework `AsOfBadge`**

A fresh badge is quiet type; a stale one is the inverted amber bar. This is the payoff for rationing amber in Task 1.

```tsx
<span className="tabular" title={stale ? "Older than this source's expected cadence" : undefined}>
  {stale ? (
    <span className="term-bar">STALE · {formatDate(asOf)}</span>
  ) : (
    <span style={{ color: "var(--faint)", fontSize: "var(--size-micro)", fontWeight: 400, letterSpacing: 0 }}>
      AS OF {formatDate(asOf)}
    </span>
  )}
</span>
```

Keep the cadence line beneath it exactly as it is — the comment above it explains why it must not be dropped, and that reasoning is unaffected by the restyle.

- [ ] **Step 3: Compact the `PageHeader`**

Replace the `<h2>` at `var(--size-page)` and the 60ch dek block with a compact title bar. The dek survives, as prose, on one line:

```tsx
<div
  style={{
    display: "flex",
    alignItems: "baseline",
    gap: "var(--space-4)",
    padding: "var(--space-3) var(--space-4)",
    borderBottom: "1px solid var(--border)",
  }}
>
  <h2 style={{ fontSize: "var(--size-page)", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
    {title}
  </h2>
  <p className="prose" style={{ fontSize: "var(--size-micro)", color: "var(--faint)" }}>
    {dek}
  </p>
</div>
```

- [ ] **Step 4: Verify**

```bash
cd web && pnpm lint && pnpm build
```

- [ ] **Step 5: Commit**

```bash
cd .. && git add web/src/components/chrome/Panel.tsx web/src/components/chrome/PageHeader.tsx && git commit -m "Make the card a panel and compact the page header

The stale badge becomes the inverted amber bar -- the one thing amber-as-ink was
rationed to leave room for."
```

---

## Task 5: The monitor row and the screen list

**Files:**
- Modify: `web/src/components/chrome/StatStrip.tsx`
- Modify: `web/src/components/chrome/ScreenCard.tsx`

**Interfaces:**
- Consumes: `.term-grid`, `.term-cell`, `.term-table`.
- Produces: `StatStrip({headlines, sparks})` and `ScreenCard`'s existing props — **unchanged**, so `app/page.tsx` needs no edit for this task.

- [ ] **Step 1: Turn `StatStrip`'s cards into a monitor row**

Replace the `repeat(auto-fit, minmax(176px, 1fr))` card grid with `.term-grid` at
`gridTemplateColumns: "repeat(auto-fit, minmax(128px, 1fr))"`, each `Link` becoming
`className="term-cell"` with no `card`, no `card-link`, no `rise`, and no
`animationDelay`. Structure per cell: `.k` label, `.v` value (keep `CountUp`), `.d`
delta, then the sparkline and the date.

**Keep `formatSigned`.** The sign is load-bearing — see Global Constraints.

- [ ] **Step 2: Turn `ScreenCard` into a list row**

Same treatment: drop `card`/`card-link`, drop the hover lift, keep the sparkline and the
figure. The docstring's reasoning — that a card with data in it is a reason to click —
still holds and should stay; only the surface changes.

- [ ] **Step 3: Verify**

```bash
cd web && pnpm lint && pnpm build
```

- [ ] **Step 4: Commit**

```bash
cd .. && git add web/src/components/chrome/StatStrip.tsx web/src/components/chrome/ScreenCard.tsx && git commit -m "Turn the headline cards into a monitor row"
```

---

## Task 6: Tables and the two hardcoded routes

**The dead-token half of this task is already done.** When this plan was written,
`HeatTable` referenced `var(--rule)` and `NotBuiltYet` `var(--heading-stack)`, neither
defined. A peer session fixed those and three more in `7a6ad3e`, and added the
`tokens.test.ts` guard. Do not redo it; do not reintroduce `--hairline` as
`HeatTable`'s border token without also defining it, or `tokens.test.ts` will fail —
correctly.

What remains here is the table's own treatment on a black ground, and two routes that
still hardcode colour.

**Files:**
- Modify: `web/src/components/tables/HeatTable.tsx`
- Modify: `web/src/components/chrome/NotBuiltYet.tsx`
- Modify: `web/src/app/page.tsx`
- Modify: `web/src/app/sanctions/page.tsx`

**Interfaces:**
- Consumes: `.term-table`, token set from Task 1.
- Produces: no hex literal in either route file; `HeatTable` and `NotBuiltYet` on the
  terminal primitives with every token they name defined in `tokens.css`.

- [ ] **Step 1: Confirm the dead tokens are already gone**

```bash
cd web && grep -rn "var(--rule)\|var(--heading-stack)\|var(--ink)\|var(--body-stack)" src/ --include=*.tsx ; pnpm test src/theme/tokens.test.ts
```

Expected: grep prints nothing, and the token-resolution test passes. If either fails, the
rebase lost `7a6ad3e` — stop and re-check the branch base before doing anything else.

- [ ] **Step 2: Move the two components onto the primitives**

`HeatTable`'s `cell` and `headCell` currently use `var(--border)`. Point them at
`var(--hairline)` for row rules (kept lighter than panel edges so a table does not read
as stacked panels) and leave `var(--border)` on `headCell`. Both tokens are defined in
Task 1.

In `NotBuiltYet.tsx`, give its `<main>` the `.term-panel` treatment so an unbuilt screen
reads as an empty panel rather than a hole. Its `fontFamily: "var(--font)"` is already
correct and needs no change.

- [ ] **Step 3: Re-tune the heat wash, and fix its asymmetry**

Two separate problems.

*It vanishes on black.* The current alphas (`0.08` → `0.30`) were built for white.

*It is already lopsided on white, and will stay lopsided unless fixed.* Measured off the
live render, the deficit tints carry chroma 18–41 while the surplus tints carry only
5–9 — navy at low alpha desaturates into a grey the eye reads as unstyled, while red
stays a distinct hue. Contrast is comparable (1.39 vs 1.52 at the extremes); the
asymmetry is colourfulness, not lightness. A reader scanning for outliers finds the draws
and misses the builds, though `heatStyle` gives both directions one symmetric ramp.

Fix both: raise the floor for the black ground, and give the two directions ramps tuned
to look equal rather than to *be* equal. Lifted blue `#4d9fff` is far more chromatic than
`#0f2a4a` was, which does most of the work by itself.

```ts
  // Tuned by eye, not symmetric by arithmetic: at equal alpha the blue reads weaker
  // than the red, so a symmetric ramp makes builds easier to miss than draws.
  const alpha = (pct > 0 ? 0.22 : 0.18) + scaled * (pct > 0 ? 0.38 : 0.34);
  // Blue for a surplus, red for a deficit -- the house series palette, not a
  // traffic-light scheme: a stock build is not "good" and a draw is not "bad".
  const rgb = pct > 0 ? "77, 159, 255" : "255, 90, 77";
```

**Verify by measuring, not by eye** — the whole point of this step is that eyes got it
wrong twice. Screenshot the table and sample the tinted cells; the strongest surplus and
the strongest deficit should land within roughly 20% of each other on both contrast and
chroma.

- [ ] **Step 4: De-hardcode the two routes**

In `app/page.tsx:247`, the call-to-action link sits on `var(--accent)`. Amber needs black
type, not white: `color: "#000"` → better, `color: "var(--bg)"`. Drop its `borderRadius`
and `boxShadow` entries.

In `app/sanctions/page.tsx:173`, the bar wash is hardcoded navy and will vanish:

```ts
background: `linear-gradient(to left, rgba(77, 159, 255, 0.22) ${(100 * count) / max}%, transparent ${(100 * count) / max}%)`,
```

- [ ] **Step 5: Verify**

```bash
cd web && grep -rn "var(--rule)\|var(--heading-stack)" src/ ; pnpm lint && pnpm build
```

Expected: grep prints nothing; lint and build pass.

- [ ] **Step 6: Commit**

```bash
cd .. && git add web/src/components/tables/HeatTable.tsx web/src/components/chrome/NotBuiltYet.tsx web/src/app/page.tsx web/src/app/sanctions/page.tsx && git commit -m "Re-tune the tables for black, and fix two tokens that never existed

HeatTable asked for var(--rule) and NotBuiltYet for var(--heading-stack). Neither is
defined in tokens.css -- both are core/design.py names that were never ported, so those
rules have been silently doing nothing since the surface was built."
```

---

## Task 7: Chart controls

**Files:**
- Modify: `web/src/components/charts/ChartControls.tsx`

**Interfaces:**
- Consumes: `.term-key`.
- Produces: `ChartControls`' exported props and `RangeKey` type unchanged.

- [ ] **Step 1: Replace the segmented control and chips with keys**

Swap `className="segmented"`/`className="segment"` and `className="chip"` for
`className="term-key"`. The `aria-pressed` attributes already drive `.term-key`'s
selected and struck-through states — keep them exactly as they are, including the
line-through for a disabled series, which the original comment correctly notes is there
because a colour going grey is not legible to everyone.

Keep the coloured swatch on each series toggle.

- [ ] **Step 2: Verify**

```bash
cd web && pnpm lint && pnpm build
```

- [ ] **Step 3: Commit**

```bash
cd .. && git add web/src/components/charts/ChartControls.tsx && git commit -m "Turn the chart controls into terminal keys"
```

---

## Task 8: Charts and the map

**Files:**
- Modify: `web/src/theme/plotly.ts`
- Modify: `web/src/components/charts/SeasonalChart.tsx`
- Modify: `web/src/components/map/VesselMap.tsx`

**Interfaces:**
- Consumes: the series values from Task 1.
- Produces: `SERIES`, `SERIES_CYCLE`, `GRID`, `MUTED`, `BODY_STACK`, `baseLayout(unit)`, `PLOT_CONFIG` — same names and shapes, new values. `SeasonalChart` imports from `@/theme/plotly` instead of declaring its own constants.

- [ ] **Step 1: Rewrite `plotly.ts`'s values and its header comment**

The comment currently promises a chart here and one from Python are indistinguishable.
That promise is what this change breaks, so it must state the real contract:

```ts
/**
 * The Plotly house style for a black ground.
 *
 * **This no longer matches `core/theme.py` value-for-value, deliberately.** It matches it
 * *role*-for-role: navy is still the primary series, orange is still always the seasonal
 * median, and the cycle order is unchanged. But navy at #0f2a4a is invisible on black, so
 * every series is re-derived at a luminance that survives the terminal ground. A chart
 * here and the same chart exported from Python therefore read the same and are not the
 * same colour. That is the trade the terminal restyle made; see
 * docs/superpowers/specs/2026-09-09-terminal-ui-design.md.
 */

export const SERIES = {
  navy: "#4d9fff",
  lightBlue: "#9fd8ff",
  red: "#ff5a4d",
  orange: "#ffa62b",
  grey: "#99a3ad",
  band: "rgba(160,170,185,0.18)",
} as const;

export const GRID = "#1e232b";
export const MUTED = "#9aa2ad";

/** Every figure and axis tick is monospace, matching the chrome. */
export const BODY_STACK =
  '"JetBrains Mono", "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
```

And in `baseLayout`, the grounds and the axes:

```ts
    font: { family: BODY_STACK, size: 10, color: MUTED },
    paper_bgcolor: "#0a0b0d",
    plot_bgcolor: "#0a0b0d",
    margin: { l: 46, r: 12, t: 8, b: 28 },
    xaxis: { showgrid: false, gridcolor: GRID, linecolor: "#2a2f37", zeroline: false },
    yaxis: {
      gridcolor: GRID,
      zeroline: false,
      linecolor: "#2a2f37",
      title: unit ? { text: unit, font: { family: BODY_STACK } } : undefined,
    },
```

Leave `hovermode` and `legend` as they are.

- [ ] **Step 2: Delete `SeasonalChart`'s duplicate constants**

`SeasonalChart.tsx:31-36` declares its own `NAVY`, `LIGHT_BLUE`, `ORANGE`, `BAND`, `GRID`
and `MUTED` — and its `GRID`/`MUTED` are the *Streamlit* values (`#e6e6e6`, `#757575`),
not this surface's, so the two have already drifted apart unnoticed. Delete all six and
import from the one source:

```ts
import { GRID, MUTED, SERIES } from "@/theme/plotly";
```

Then replace each local usage with `SERIES.navy`, `SERIES.lightBlue`, `SERIES.orange`,
`SERIES.band`, `GRID`, `MUTED`.

- [ ] **Step 3: Darken the map**

In `VesselMap.tsx`, `style: "carto-positron"` → `style: "carto-darkmatter"`, and move the
four hardcoded vessel-type colours onto the lifted series values:

```ts
  crude: "#ff5a4d",
  lng: "#ffa62b",
  products: "#9fd8ff",
  other: "#99a3ad",
```

- [ ] **Step 4: Verify no hardcoded colour survives outside the theme**

```bash
cd web && grep -rn "#[0-9a-fA-F]\{6\}" src/ --include=*.tsx
```

Expected: nothing. Then:

```bash
pnpm test && pnpm lint && pnpm build
```

- [ ] **Step 5: Commit**

```bash
cd .. && git add web/src/theme/plotly.ts web/src/components/charts/SeasonalChart.tsx web/src/components/map/VesselMap.tsx && git commit -m "Theme the charts and the map for black

Also deletes SeasonalChart's private copies of the series constants. Its GRID and MUTED
were the Streamlit values rather than this surface's -- the duplication had already
drifted, which is the argument for not having it."
```

---

## Task 9: Documentation, the full pass, and review

**Files:**
- Modify: `web/CLAUDE.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: everything above.
- Produces: a branch ready to merge.

- [ ] **Step 1: Walk all 14 routes**

```bash
cd web && pnpm dev
```

Visit every route — `/`, `/balances`, `/oil-math`, `/prices`, `/prices/[root]` (pick one
root), `/supply`, `/gas`, `/flows`, `/curves`, `/positioning`, `/vessels`, `/events`,
`/sanctions`, `/hormuz` — at a wide window and at ~900px. Look specifically for: a white
chart ground, a surviving radius or shadow, an unreadable figure, a panel with no edge.
Note anything found; fix before proceeding.

- [ ] **Step 2: Prove the light UI is gone**

```bash
cd web && grep -rn "card-link\|class=\"card\"\|className=\"card\"\|nav-pill\|segmented\|\"chip\"\|rise" src/
```

Expected: nothing. Any hit is a component that was missed.

- [ ] **Step 3: Confirm the Streamlit surface is untouched**

```bash
cd .. && git diff --name-only main...HEAD | grep -v "^web/\|^docs/\|^CHANGELOG.md"
```

Expected: nothing. A hit outside `web/`, `docs/` or the changelog means this branch broke
its own boundary.

```bash
.venv/Scripts/python.exe -m pytest -q
```

Expected: the full Python suite green and unchanged.

- [ ] **Step 4: Write the docs**

In `web/CLAUDE.md`, replace the design-system section with the terminal rules: the token
file is the only place chrome values live; amber is rationed to type, with the solid bar
reserved for the active nav item and stale data; direction is carried by sign and colour;
the contrast floor is 4.5:1 and enforced by `tokens.pins.test.ts`, while `tokens.test.ts`
enforces that every referenced token resolves; the series share roles with
`core/design.py` but not values, and why.

In `CHANGELOG.md`, add an entry in the existing house style recording the restyle and the
broken cross-surface colour contract.

- [ ] **Step 5: Full verification**

```bash
cd web && pnpm test && pnpm lint && pnpm build
```

Expected: all three pass. Do not proceed on a failure.

- [ ] **Step 6: Review**

Per the user's standing rule, code changes built across multiple tasks get an explicit
review pass before being called done:

```
/code-review high
/security-review
```

Address anything real that comes back; re-run Step 5 after any fix.

- [ ] **Step 7: Commit**

```bash
cd .. && git add web/CLAUDE.md CHANGELOG.md && git commit -m "Document the terminal restyle"
```

---

## Self-review notes

Checked against the spec, section by section:

- Decisions 1-7 → Tasks 1 (2, 4, 5, 7), 2 (6), 3-8 (3).
- Primitive layer → Task 1 Step 4; consumed in Tasks 3-7.
- All eight components in the spec's table → Tasks 3, 4, 5, 6, 7.
- Charts and map → Task 8.
- The broken `plotly.ts` contract → Task 8 Step 1, and documented in Task 9 Step 4.
- `tokens.pins.test.ts` and the contrast floor → Task 1.
- Manual pass over 14 routes → Task 9 Step 1.
- Definition of done items 1-8 → Task 9 Steps 1-7.

**Two corrections to the spec, found while planning:**

1. The spec's risk section says full-bleed "touches every page wrapper". It does not —
   `--measure` has exactly four consumers. The risk is smaller than recorded.
2. The spec records `--faint` `#6b7280` as ~4.7:1 against black and passing. It is
   **4.34:1 and fails.** The token is `#7d8590` (5.63:1) in this plan.

**Two pre-existing defects found and folded into Task 6**, because that task already
touches the type and borders they affect: `HeatTable` references `var(--rule)` and
`NotBuiltYet` references `var(--heading-stack)`, neither of which is defined in
`tokens.css` — both are `core/design.py` names that were never ported, so those rules
have silently done nothing since this surface was built.


---

## Revisions on reinstatement (2026-09-09)

This plan was written, shelved, and reinstated the same day. Five things changed under it
while it was shelved; each is already folded into the task it affects, and they are listed
here so an executor reading a task does not have to reconstruct why it differs from the
spec.

1. **`web/src/theme/tokens.test.ts` now exists** (`7a6ad3e`, `a2ce7ee`) and asserts every
   `var(--x)` in the tree resolves against `tokens.css`. Task 1 originally *created* a file
   at that path and would have destroyed it. The pinning and contrast assertions now go in
   `tokens.pins.test.ts` instead, and the existing file is explicitly off limits. It will
   fail during this restyle whenever a token is renamed without its callers — that is the
   test doing its job.

2. **The dead tokens are already fixed.** `--rule`, `--heading-stack`, `--ink` and
   `--body-stack` were live defects when Task 6 was written; a peer session fixed all five
   instances. Task 6 no longer fixes them and now only confirms they are gone — a failure
   there means the branch base is wrong.

3. **The heat wash is lopsided on white, not just invisible on black.** Measured off the
   live render: deficit tints carry chroma 18–41, surplus tints only 5–9, at comparable
   contrast. Navy at low alpha greys out; red stays a hue. Task 6 Step 3 now fixes both
   problems and requires the result to be *measured*, because eyes got this wrong twice —
   once calling the tints balanced, once diagnosing the imbalance as lightness.

4. **The front page hero now has three text blocks, not two** (`fe83d31`): a badge reading
   "{n} datasets · primary sources only", a rewritten lead, and "The working evidence
   behind Kardamow — independent research on energy, macro and geopolitics." Task 4's
   compact `PageHeader` and Task 9's route walk must expect three. The vocabulary rule that
   came with it is binding: **no user-facing copy mentions "the lake."**

5. **A sibling dark surface now exists.** `kardamow.com` (a separate app in `site/`, its own
   Vercel project) is going dark with an indigo-on-black palette and a vessel globe. This
   terminal is amber-on-black. Keep them visibly distinct; do not converge on a shared dark
   treatment by accident.

**Merge is not the executor's call.** The direction here has changed four times and
data.kardamow.com is live serving the light UI. Task 9 ends with the branch ready and the
user deciding.
