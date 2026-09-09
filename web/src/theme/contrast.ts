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
