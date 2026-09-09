"use client";

import { useEffect, useLayoutEffect, useRef } from "react";

import { formatNumber } from "@/lib/format";

/**
 * A figure that arrives by counting up to itself.
 *
 * The front page opens on six numbers and nothing else. Painting them instantly is
 * correct but inert; running them up over half a second makes the page read as something
 * that has just resolved, which is what it has. Stripe and Revolut both do this, for the
 * same reason: a balance that lands rather than appears feels current.
 *
 * It counts from **zero**, not from a previous value. This only ever runs on mount, where
 * there is no previous value, and starting anywhere else would put a figure on screen
 * that the series never held.
 *
 * **The animation writes to the DOM node, not to React state.** Thirty-odd renders to
 * change one text node is work for nothing, and setting state on every frame of an effect
 * is exactly the cascade `react-hooks/set-state-in-effect` exists to stop. The server
 * still renders the real figure into the HTML, so a reader with no JavaScript — or one
 * who has asked for less motion — sees the number and never the animation.
 *
 * The last frame is set from the prop rather than from the animation's arithmetic, so no
 * accumulated rounding can leave a wrong digit on screen.
 */

const DURATION_MS = 620;

/**
 * `useLayoutEffect` on the client, `useEffect` on the server.
 *
 * The count has to be reset to zero *before* the browser paints, or the reader sees the
 * true figure for a frame and then watches it drop — which reads as a glitch rather than
 * as an arrival. `useLayoutEffect` runs before paint; it also warns when React renders it
 * on the server, where there is no layout, hence the swap. The branch is decided once per
 * environment, so the hook order never changes between renders.
 */
const useBeforePaint =
  typeof window === "undefined" ? useEffect : useLayoutEffect;

export function CountUp({
  value,
  digits,
}: {
  value: number | null;
  digits: number;
}) {
  const node = useRef<HTMLSpanElement>(null);
  const frame = useRef<number | null>(null);

  useBeforePaint(() => {
    const span = node.current;
    if (span === null || value === null) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    span.textContent = formatNumber(0, digits);
    const started = performance.now();

    const step = (now: number) => {
      const progress = Math.min(1, (now - started) / DURATION_MS);
      if (progress === 1) {
        span.textContent = formatNumber(value, digits);
        return;
      }
      // Ease out: quick off the mark, settling at the end. A linear count reads
      // mechanical, like an odometer rather than a figure resolving.
      span.textContent = formatNumber(
        value * (1 - (1 - progress) ** 3),
        digits,
      );
      frame.current = requestAnimationFrame(step);
    };

    frame.current = requestAnimationFrame(step);
    return () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      // Whatever partial figure the last frame left behind, the node ends on the real
      // one. An unmount mid-count must not be able to strand a wrong number.
      span.textContent = formatNumber(value, digits);
    };
  }, [value, digits]);

  return <span ref={node}>{formatNumber(value, digits)}</span>;
}
