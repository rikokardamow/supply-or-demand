import type { ReactNode } from "react";

import { RELEASE_CADENCE } from "@/data/staleness";
import { formatDate } from "@/lib/format";

/**
 * A panel: an `<h3>` heading over a hairline rule, then the chart or table, then an
 * optional source line. Mirrors `apps/dashboard/components/section.py::section()` --
 * the bordered `card()` it replaced no longer exists on the Streamlit side either.
 *
 * Nothing decorative: no shadow, no rounded border, no background tint. The rule and the
 * heading do all the separating work.
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
    <section style={{ marginBottom: "2rem" }}>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "1rem",
        }}
      >
        <h3
          style={{
            fontFamily: "var(--heading-stack)",
            fontSize: "1.15rem",
            margin: "0 0 0.35rem",
          }}
        >
          {title}
        </h3>
        {asOf ? (
          <AsOfBadge asOf={asOf} stale={stale} pipeline={pipeline} />
        ) : null}
      </div>
      <hr
        style={{
          border: 0,
          borderTop: "1px solid var(--rule)",
          margin: "0 0 0.9rem",
        }}
      />
      {children}
      {sourceNote ? (
        <p
          style={{
            fontFamily: "var(--body-stack)",
            fontSize: "0.78rem",
            color: "var(--muted)",
            margin: "0.6rem 0 0",
          }}
        >
          {sourceNote}
        </p>
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
        gap: "0.15rem",
      }}
    >
      <span
        className="tabular"
        title={stale ? "Older than this source's expected cadence" : undefined}
        style={{
          fontSize: "0.72rem",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: stale ? "var(--status-amber)" : "var(--muted)",
          whiteSpace: "nowrap",
        }}
      >
        {stale ? "Stale · " : "As of "}
        {formatDate(asOf)}
      </span>
      {cadence ? (
        <span
          style={{
            fontSize: "0.68rem",
            color: "var(--muted)",
            whiteSpace: "nowrap",
          }}
        >
          {cadence}
        </span>
      ) : null}
    </span>
  );
}
