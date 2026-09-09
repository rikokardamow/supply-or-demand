import Link from "next/link";

import { Sparkline } from "@/components/charts/Sparkline";
import { formatNumber, formatSigned } from "@/lib/format";

/**
 * One screen's card on the front page: name, a line of what is on it, and — where the
 * screen has a series to show — a sparkline with its latest figure.
 *
 * The earlier version was eight identical grey paragraphs. Nothing on it distinguished
 * Balances from Sanctions, and a reader had to decide where to go by reading prose. The
 * market sites this was measured against (Kalshi, Polymarket, 2026-09-09) all put real
 * numbers inside every card for that reason: a card with data in it is a reason to click,
 * a card with a description in it is a chore.
 *
 * **A card without a series shows no chart rather than a placeholder.** Vessels, Events
 * and Sanctions are registers, not time series; drawing a flat line or a fake shape for
 * them would be inventing data to fill a slot.
 */

export type ScreenStat = {
  /** Points for the sparkline, oldest first. Omitted where the screen has no series. */
  spark?: number[];
  value?: number | null;
  change?: number | null;
  unit?: string | null;
  digits?: number;
  /** A count where there is no series to plot — "2,506 listed entries". */
  note?: string;
};

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
  const tone =
    stat?.change === undefined || stat.change === null || stat.change === 0
      ? "var(--muted)"
      : stat.change > 0
        ? "var(--navy)"
        : "var(--red)";

  return (
    <Link
      href={href}
      className="rise screen-card"
      style={{
        textDecoration: "none",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-3)",
        paddingTop: "var(--space-3)",
        borderTop: "1px solid var(--rule)",
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
        <h4
          style={{
            fontFamily: "var(--heading-stack)",
            fontSize: "var(--size-lead)",
            fontWeight: 600,
            color: "var(--ink)",
            margin: 0,
          }}
        >
          {title}
        </h4>
        {stat?.value !== undefined && stat.value !== null ? (
          <span
            className="tabular"
            style={{
              fontSize: "var(--size-small)",
              color: "var(--ink)",
              fontWeight: 600,
            }}
          >
            {formatNumber(stat.value, stat.digits ?? 2)}
            <span style={{ color: "var(--muted)", fontWeight: 400 }}>
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
              label={`${title}: twelve months of ${title.toLowerCase()}`}
            />
          </div>
          <span
            className="tabular"
            style={{
              fontSize: "var(--size-micro)",
              color: tone,
              whiteSpace: "nowrap",
            }}
          >
            {formatSigned(stat.change ?? null, stat.digits ?? 2)}
          </span>
        </div>
      ) : stat?.note ? (
        <p
          className="tabular"
          style={{
            fontSize: "var(--size-small)",
            color: "var(--text)",
            margin: 0,
          }}
        >
          {stat.note}
        </p>
      ) : null}

      <p
        style={{
          fontSize: "var(--size-small)",
          color: "var(--muted)",
          margin: 0,
        }}
      >
        {blurb}
      </p>
    </Link>
  );
}
