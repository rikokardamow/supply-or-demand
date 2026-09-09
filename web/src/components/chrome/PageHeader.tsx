import type { ReactNode } from "react";

import { Masthead } from "@/components/chrome/Masthead";
import { TickerRail } from "@/components/chrome/TickerRail";
import { fetchHeadlines } from "@/data/queries/overview";

/**
 * Everything above a section page's first card: the app bar, the ticker rail, and the
 * page's own title.
 *
 * The title is a page title, not a display headline. A section page opens on a grid of
 * exhibits and the reader is there to read them; setting "Gas" at 2.6rem over a heavy rule
 * spent a third of the fold announcing a word the navigation had already highlighted.
 */
export async function PageHeader({
  active,
  title,
  dek,
}: {
  active: string;
  title: string;
  /** Nodes, not a string: several deks count rows or interpolate a week-ending date. */
  dek: ReactNode;
}) {
  const headlines = await fetchHeadlines();

  return (
    <>
      <Masthead active={active} />
      <TickerRail headlines={headlines} />

      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "var(--space-4)",
          padding: "var(--space-3) var(--space-4)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <h2
          style={{
            fontSize: "var(--size-page)",
            fontWeight: 700,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
          }}
        >
          {title}
        </h2>
        <p
          className="prose"
          style={{ fontSize: "var(--size-micro)", color: "var(--faint)" }}
        >
          {dek}
        </p>
      </div>
    </>
  );
}
