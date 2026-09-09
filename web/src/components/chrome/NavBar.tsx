"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { SCREENS } from "@/components/chrome/Masthead";

/**
 * The section navigation, stuck to the top of the window once the masthead has scrolled
 * past it.
 *
 * "Stuck" is detected with a sentinel element and an IntersectionObserver rather than a
 * scroll listener. A scroll handler fires on every frame of every scroll and has to be
 * throttled to stay smooth; an observer fires twice -- once when the sentinel leaves the
 * viewport and once when it returns -- and costs nothing in between. On a page of eight
 * Plotly charts that difference is visible.
 *
 * The sentinel sits *above* the bar, so it leaves the viewport at exactly the moment the
 * bar would begin to stick. Watching the bar itself does not work: a `position: sticky`
 * element never stops intersecting.
 */
export function NavBar({ active }: { active?: string }) {
  const sentinel = useRef<HTMLDivElement>(null);
  const [stuck, setStuck] = useState(false);

  useEffect(() => {
    const node = sentinel.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      ([entry]) => setStuck(!entry.isIntersecting),
      { threshold: 0 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <>
      <div ref={sentinel} aria-hidden style={{ height: 1 }} />
      <div className="nav-bar" data-stuck={stuck}>
        <div
          className="bleed-inner"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-6)",
            padding: "var(--space-3) var(--space-6)",
          }}
        >
          <Link
            href="/"
            className="nav-mark"
            aria-hidden={!stuck}
            tabIndex={stuck ? undefined : -1}
            style={{
              fontFamily: "var(--heading-stack)",
              fontSize: "1.05rem",
              fontWeight: 600,
              color: "var(--ink)",
              textDecoration: "none",
              letterSpacing: "-0.01em",
              whiteSpace: "nowrap",
            }}
          >
            Kardamow
          </Link>

          <nav
            aria-label="Screens"
            style={{
              display: "flex",
              gap: "var(--space-6)",
              margin: "0 auto",
              overflowX: "auto",
              // The scrollbar a narrow window would paint under the nav is noise; the row
              // still scrolls by touch and by wheel.
              scrollbarWidth: "none",
            }}
          >
            {SCREENS.map((screen) => {
              const isActive = screen.href === active;
              return (
                <Link
                  key={screen.href}
                  href={screen.href}
                  className="nav-link"
                  aria-current={isActive ? "page" : undefined}
                  style={{
                    fontFamily: "var(--body-stack)",
                    fontSize: "var(--size-small)",
                    letterSpacing: "0.04em",
                    textTransform: "uppercase",
                    textDecoration: "none",
                    whiteSpace: "nowrap",
                    color: isActive ? "var(--ink)" : "var(--muted)",
                    fontWeight: isActive ? 600 : 500,
                  }}
                >
                  {screen.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </div>
    </>
  );
}
