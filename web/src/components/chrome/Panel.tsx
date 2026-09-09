import type { ReactNode } from "react";

import { RELEASE_CADENCE } from "@/data/staleness";
import { formatDate } from "@/lib/format";

/**
 * A card: heading and as-of stamp in a header strip, then the chart or table, then an
 * optional source line.
 *
 * The previous version was a heading over a hairline rule with the chart sitting loose on
 * the page. That is how a document sets a figure; an interface gives each exhibit a
 * surface of its own, so a reader can see where one ends and the next begins without
 * reading the headings.
 */
export function Panel({
  title,
  asOf,
  sourceNote,
  stale,
  pipeline,
  children,
}: {
  title: string;
  asOf?: string | null;
  sourceNote?: string | null;
  stale?: boolean;
  /** Names the source's cadence beside the as-of date. See `AsOfBadge`. */
  pipeline?: string;
  children: ReactNode;
}) {
  return (
    <section className="term-panel" style={{ marginBottom: "var(--space-6)" }}>
      <header className="term-head">
        <h3 style={{ fontSize: "var(--size-panel)", fontWeight: 600 }}>
          {title}
        </h3>
        {asOf ? (
          <AsOfBadge asOf={asOf} stale={stale} pipeline={pipeline} />
        ) : null}
      </header>

      <div style={{ padding: "var(--space-4)" }}>{children}</div>

      {sourceNote ? (
        <footer
          style={{
            padding: "var(--space-3) var(--space-5)",
            borderTop: "1px solid var(--border)",
            background: "var(--surface-2)",
            fontSize: "var(--size-micro)",
            color: "var(--muted)",
            lineHeight: 1.55,
          }}
        >
          {sourceNote}
        </footer>
      ) : null}
    </section>
  );
}

/**
 * The as-of stamp. Reads `serving.publish_log.as_of` -- the *data's* own as-of, never
 * `published_at` and never `max(ts)` of the series (Spec 33 §6). A republished but
 * unchanged feed must not look fresh.
 *
 * The cadence sits under the date because a date on its own cannot tell a reader whether
 * it is current. The flagship WPSR panel is dated twelve days back and is the newest
 * report EIA has released; without "weekly, Wed 10:30 ET" beside it, that reads as a site
 * nobody maintains.
 */
export function AsOfBadge({
  asOf,
  stale,
  pipeline,
}: {
  asOf: string;
  stale?: boolean;
  pipeline?: string;
}) {
  const cadence = pipeline ? RELEASE_CADENCE[pipeline] : undefined;

  return (
    <span
      style={{
        display: "inline-flex",
        flexDirection: "column",
        alignItems: "flex-end",
        gap: "0.2rem",
        flexShrink: 0,
      }}
    >
      <span
        className="tabular"
        title={stale ? "Older than this source's expected cadence" : undefined}
      >
        {stale ? (
          <span className="term-bar">STALE · {formatDate(asOf)}</span>
        ) : (
          <span
            style={{
              color: "var(--faint)",
              fontSize: "var(--size-micro)",
              fontWeight: 400,
              letterSpacing: 0,
            }}
          >
            AS OF {formatDate(asOf)}
          </span>
        )}
      </span>
      {cadence ? (
        <span
          style={{
            fontSize: "var(--size-micro)",
            color: "var(--faint)",
            whiteSpace: "nowrap",
          }}
        >
          {cadence}
        </span>
      ) : null}
    </span>
  );
}
