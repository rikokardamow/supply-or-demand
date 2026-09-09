import Link from "next/link";

import { Sparkline } from "@/components/charts/Sparkline";
import { formatNumber, formatSigned } from "@/lib/format";

/**
 * One screen's card: name, latest figure, a year of shape, and a line of what is on it.
 *
 * The earlier version was eight identical grey paragraphs. Nothing on it distinguished
 * Balances from Sanctions, and a reader had to decide where to go by reading prose. The
 * market interfaces this was measured against (Kalshi, Polymarket, 2026-09-09) all put
 * real numbers inside every card for that reason: a card with data in it is a reason to
 * click, a card with a description in it is a chore.
 *
 * **A card without a series shows no chart rather than a placeholder.** Curves, Vessels
 * and Events are curves and registers, not time series; drawing a flat line or a fake
 * shape for them would be inventing data to fill a slot.
 */

export type ScreenStat = {
  /** Points for the sparkline, oldest first. Omitted where the screen has no series. */
  spark?: number[];
  value?: number | null;
  change?: number | null;
  unit?: string | null;
  digits?: number;
  /** A count where there is no series to plot — "19,365 listed entries". */
  note?: string;
};

/**
 * The change across the drawn window, and the tone that matches it.
 *
 * The card previously paired a year-long sparkline with the *last observation's* change,
 * so Positioning showed a red line falling across the year beside a green "+14,345" from
 * the final week — two true statements about different horizons, sitting adjacent with
 * nothing to say they were different, which reads as a contradiction. Both now describe
 * the same year.
 */
function overWindow(spark: number[] | undefined): number | null {
  if (!spark || spark.length < 2) return null;
  return spark[spark.length - 1] - spark[0];
}

/**
 * The direction the drawn window travelled, not the last observation's move.
 *
 * The sparkline covers a year; colouring it by the most recent week-on-week change would
 * paint a year of decline green because the final point happened to tick up. The tone has
 * to describe the line the reader is looking at.
 */
function windowTone(spark: number[] | undefined): string {
  const change = overWindow(spark);
  if (change === null || change === 0) return "var(--muted)";
  return change > 0 ? "var(--up)" : "var(--down)";
}

export function ScreenCard({
  href,
  title,
  blurb,
  stat,
  delay,
}: {
  href: string;
  title: string;
  blurb: string;
  stat?: ScreenStat;
  delay: number;
}) {
  const yearChange = overWindow(stat?.spark);

  return (
    <Link
      href={href}
      className="card card-link rise"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-3)",
        padding: "var(--space-4)",
        animationDelay: `${delay}ms`,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "var(--space-3)",
        }}
      >
        <h4 style={{ fontSize: "var(--size-lead)", fontWeight: 600 }}>
          {title}
        </h4>
        {stat?.value !== undefined && stat.value !== null ? (
          <span
            className="tabular"
            style={{ fontSize: "var(--size-small)", fontWeight: 600 }}
          >
            {formatNumber(stat.value, stat.digits ?? 2)}
            <span style={{ color: "var(--faint)", fontWeight: 400 }}>
              {stat.unit ? ` ${stat.unit}` : ""}
            </span>
          </span>
        ) : null}
      </div>

      {stat?.spark && stat.spark.length > 1 ? (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-3)",
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <Sparkline
              values={stat.spark}
              color={windowTone(stat.spark)}
              label={`${title}: the last year`}
              height={32}
            />
          </div>
          <span
            className="tabular"
            style={{
              fontSize: "var(--size-micro)",
              fontWeight: 600,
              color: windowTone(stat.spark),
              whiteSpace: "nowrap",
            }}
          >
            {formatSigned(yearChange, stat.digits ?? 2)}
            <span style={{ color: "var(--faint)", fontWeight: 400 }}> 1y</span>
          </span>
        </div>
      ) : stat?.note ? (
        <p
          className="tabular"
          style={{ fontSize: "var(--size-small)", fontWeight: 500 }}
        >
          {stat.note}
        </p>
      ) : null}

      <p style={{ fontSize: "var(--size-small)", color: "var(--muted)" }}>
        {blurb}
      </p>
    </Link>
  );
}
