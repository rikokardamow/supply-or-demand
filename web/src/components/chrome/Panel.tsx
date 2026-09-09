import type { ReactNode } from "react";

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
  children,
}: {
  title: string;
  asOf?: string | null;
  sourceNote?: string | null;
  stale?: boolean;
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
        {asOf ? <AsOfBadge asOf={asOf} stale={stale} /> : null}
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
 */
export function AsOfBadge({ asOf, stale }: { asOf: string; stale?: boolean }) {
  return (
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
  );
}
