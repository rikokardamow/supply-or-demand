import Link from "next/link";

import { SCREENS } from "@/components/chrome/Masthead";

/**
 * The sticky bar: mark and wordmark on the left, sections as pills on the right.
 *
 * A server component. The earlier version was a client component running an
 * IntersectionObserver purely so a hidden wordmark could fade in once the masthead
 * scrolled past -- with the masthead gone there is nothing to reveal, so the JavaScript
 * goes too. `position: sticky` needs none of it, and the bar is a direct child of the page
 * rather than nested in a short parent, which is what lets it stay stuck for the whole
 * document.
 *
 * The bar is translucent with a blur behind it so content scrolling underneath is visibly
 * *under* it rather than clipped by it.
 */
export function NavBar({ active }: { active?: string }) {
  return (
    <div className="app-bar">
      <div
        style={{
          maxWidth: "var(--measure)",
          margin: "0 auto",
          padding: "var(--space-3) var(--space-6)",
          display: "flex",
          alignItems: "center",
          gap: "var(--space-6)",
        }}
      >
        <Link
          href="/"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.5rem",
            flexShrink: 0,
          }}
        >
          {/* The mark. A filled navy square with the initial reversed out -- enough to
              hold the corner of a browser tab, and no illustration to go stale. */}
          <span
            aria-hidden
            style={{
              width: 24,
              height: 24,
              borderRadius: 7,
              background: "var(--accent)",
              color: "#fff",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "0.8rem",
              fontWeight: 700,
              letterSpacing: "-0.02em",
            }}
          >
            K
          </span>
          <h1
            style={{
              fontSize: "var(--size-lead)",
              fontWeight: 650,
              letterSpacing: "-0.02em",
              margin: 0,
            }}
          >
            Kardamow
          </h1>
        </Link>

        <nav
          aria-label="Screens"
          className="no-bar"
          style={{
            display: "flex",
            gap: "0.15rem",
            marginLeft: "auto",
            overflowX: "auto",
          }}
        >
          {SCREENS.map((screen) => (
            <Link
              key={screen.href}
              href={screen.href}
              className="nav-pill"
              aria-current={screen.href === active ? "page" : undefined}
            >
              {screen.label}
            </Link>
          ))}
        </nav>
      </div>
    </div>
  );
}
