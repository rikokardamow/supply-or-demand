import Link from "next/link";

import { SCREENS } from "@/components/chrome/Masthead";

/**
 * The sticky bar: mark and wordmark on the left, screens as terminal keys on the right.
 *
 * A server component. The earlier version was a client component running an
 * IntersectionObserver purely so a hidden wordmark could fade in once the masthead
 * scrolled past -- with the masthead gone there is nothing to reveal, so the JavaScript
 * goes too. `position: sticky` needs none of it, and the bar is a direct child of the page
 * rather than nested in a short parent, which is what lets it stay stuck for the whole
 * document.
 *
 * The bar is a flat, opaque strip -- no blur, no radius -- so it reads as part of the
 * terminal's chrome rather than a floating panel over the content.
 */
export function NavBar({ active }: { active?: string }) {
  return (
    <div
      style={{
        position: "sticky",
        top: 0,
        zIndex: 30,
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        gap: "var(--space-6)",
        padding: "var(--space-2) var(--space-4)",
      }}
    >
      <Link href="/" style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", flexShrink: 0 }}>
        {/* A square, not a rounded tile. The terminal has no radius anywhere else and
            one rounded corner in the top-left reads as an oversight. Outlined, not
            filled: a solid amber block is reserved for "you are here" and "this data
            is stale", so the identity mark takes a border instead and never competes
            with either. */}
        <span
          aria-hidden
          style={{
            width: 16,
            height: 16,
            border: "1px solid var(--accent)",
            color: "var(--accent)",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "var(--size-micro)",
            fontWeight: 700,
          }}
        >
          K
        </span>
        <h1
          style={{
            fontSize: "var(--size-small)",
            fontWeight: 700,
            letterSpacing: "0.08em",
            color: "var(--accent)",
            margin: 0,
          }}
        >
          Kardamow
        </h1>
      </Link>

      <nav aria-label="Screens" className="no-bar" style={{ display: "flex", gap: 0, marginLeft: "auto", overflowX: "auto" }}>
        {SCREENS.map((screen) => (
          <Link
            key={screen.href}
            href={screen.href}
            className="term-key"
            aria-current={screen.href === active ? "page" : undefined}
          >
            {screen.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
