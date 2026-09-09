import type { ReactNode } from "react";

import { Masthead } from "@/components/chrome/Masthead";
import { TickerRail } from "@/components/chrome/TickerRail";
import { fetchHeadlines } from "@/data/queries/overview";

/**
 * Everything above a section page's first panel: masthead, ticker rail, and the page's
 * own title.
 *
 * The title is set at display size against a wordmark that has deliberately shrunk. A
 * section page opens on "Gas", not on "Kardamow" -- the reader already knows whose site
 * they are on, and the earlier setting had a 3.25rem wordmark above a 1.6rem page title,
 * which put the weight on the masthead and left the subject of the page reading as a
 * caption.
 *
 * The heavy rule under the title is the one place in the system a rule is more than a
 * hairline. It marks where the shell ends and the reading begins, and there is exactly
 * one of them per page.
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

      {/* This block sits outside `main`, so it carries the measure itself. */}
      <div className="bleed-inner">
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "var(--space-2) var(--space-6)",
            borderBottom: "2px solid var(--ink)",
            padding: "var(--space-8) 0 var(--space-3)",
          }}
        >
          <h2
            style={{
              fontFamily: "var(--heading-stack)",
              fontSize: "var(--size-display)",
              lineHeight: 1,
              color: "var(--ink)",
              margin: 0,
            }}
          >
            {title}
          </h2>
          <p
            style={{
              fontSize: "var(--size-small)",
              color: "var(--muted)",
              maxWidth: "36rem",
              margin: 0,
            }}
          >
            {dek}
          </p>
        </div>
      </div>
    </>
  );
}
