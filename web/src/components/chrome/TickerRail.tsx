"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import type { Headline } from "@/data/queries/overview";
import { formatNumber, formatSigned } from "@/lib/format";

/**
 * The headline figures as a rail beneath the navigation, on every section page.
 *
 * A reader looking at European storage still wants to know where Brent closed, and making
 * them go back to the front page to find out is the sort of thing a site does when nobody
 * asked how it would be read.
 *
 * **It re-checks, but it does not pretend.** The rail refetches on a timer, and a figure
 * flashes only when it has genuinely changed. These series publish weekly or daily, so
 * almost every refetch changes nothing and nothing flashes -- which is the honest outcome.
 * A rail that ticked on a schedule regardless would be inventing movement the data does
 * not have.
 *
 * The server renders the first set, so the figures are in the HTML and a reader with no
 * JavaScript still gets them; the timer only ever replaces what is already there.
 */

const REFRESH_MS = 300_000;
/**
 * After a failure, wait longer each time, to a ceiling.
 *
 * `/api/headlines` is ISR-cached, so in the normal case every open tab is served from one
 * cached response and Supabase sees one query per window. **An error is not cacheable**,
 * so during a Supabase outage that protection disappears exactly when it is needed and
 * every tab's poll reaches the query again. Backing off turns a steady retry storm into a
 * handful of attempts, and the jitter stops every tab in the world retrying on the same
 * second.
 */
const MAX_BACKOFF_MS = 1_800_000;

function decimals(unit: string | null): number {
  if (unit === "MBBL" || unit === "rigs") return 0;
  return unit === "%" ? 1 : 2;
}

function toneFor(value: number | null): string {
  if (value === null || value === 0) return "var(--muted)";
  return value > 0 ? "var(--up)" : "var(--down)";
}

export function TickerRail({ headlines }: { headlines: Headline[] }) {
  const [rows, setRows] = useState(headlines);
  // Keys whose value differs from the render before this one. Held in state rather than
  // derived so the flash class mounts once and the animation actually runs.
  const [changed, setChanged] = useState<ReadonlySet<string>>(new Set());
  const previous = useRef(headlines);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;

    function scheduleNext() {
      if (cancelled) return;
      // Full jitter on the backoff: without it, every tab that failed at the same moment
      // retries at the same moment too.
      const delay =
        failures === 0
          ? REFRESH_MS
          : Math.min(MAX_BACKOFF_MS, REFRESH_MS * 2 ** failures) *
            (0.5 + Math.random());
      timer = setTimeout(refresh, delay);
    }

    async function refresh() {
      try {
        const response = await fetch("/api/headlines");
        if (!response.ok) {
          failures += 1;
          // Logged, not swallowed. The reader is deliberately shown no error -- the
          // figures on screen are still true and carry their own as-of dates -- but a
          // persistent failure has to leave a trace somewhere, or the rail can stop
          // updating forever with nothing anywhere to say so.
          console.error(
            `ticker refresh failed: /api/headlines returned ${response.status}`,
          );
          scheduleNext();
          return;
        }

        const next = (await response.json()).headlines as Headline[];
        if (cancelled) return;

        const moved = new Set(
          next
            .filter((row) => {
              const before = previous.current.find((r) => r.key === row.key);
              return before !== undefined && before.value !== row.value;
            })
            .map((row) => row.key),
        );
        previous.current = next;
        setRows(next);
        setChanged(moved);
        failures = 0;
      } catch (error) {
        failures += 1;
        console.error("ticker refresh failed", error);
      }
      scheduleNext();
    }

    scheduleNext();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  return (
    <div
      style={{
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <div
        className="no-bar"
        style={{
          display: "flex",
          gap: "var(--space-6)",
          overflowX: "auto",
          padding: "var(--space-3) var(--space-6)",
        }}
      >
        {rows.map((row) => (
          <Link
            key={row.key}
            href={row.href}
            className={changed.has(row.key) ? "flash" : undefined}
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: "0.4rem",
              whiteSpace: "nowrap",
              // The flash tints with the direction of the move, so the colour says which
              // way as well as that something happened.
              ["--flash-tone" as string]: toneFor(row.change),
            }}
          >
            <span
              style={{
                fontSize: "var(--size-micro)",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
                color: "var(--muted)",
              }}
            >
              {row.label}
            </span>
            <span
              className="tabular"
              style={{ fontSize: "var(--size-small)", fontWeight: 600 }}
            >
              {formatNumber(row.value, decimals(row.unit))}
            </span>
            <span
              className="tabular"
              style={{
                fontSize: "var(--size-micro)",
                fontWeight: 600,
                color: toneFor(row.change),
              }}
            >
              {formatSigned(row.change, decimals(row.unit))}
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
