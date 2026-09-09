import Link from "next/link";

/**
 * The masthead and top navigation, mirroring `apps/dashboard/app.py` so the web UI and
 * the Streamlit app read as one publication: a centred wordmark over a hairline rule,
 * with grouped navigation beneath it. No left rail and no sidebar -- that layout predates
 * the 2026-09-08 restyle (Spec 33 §5).
 *
 * The wordmark is the document's only `<h1>`; each page's own title is an `<h2>` and each
 * panel heading an `<h3>`, giving one valid descending outline with "Kardamow" at its top.
 */

const SCREENS = [
  { href: "/balances", label: "Balances" },
  { href: "/prices", label: "Prices" },
  { href: "/supply", label: "Supply" },
  { href: "/hormuz", label: "Hormuz" },
  { href: "/gas", label: "Gas" },
  { href: "/curves", label: "Curves" },
] as const;

export function Masthead({ active }: { active?: string }) {
  return (
    <header>
      <h1
        style={{
          textAlign: "center",
          fontFamily: "var(--heading-stack)",
          fontSize: "3.25rem",
          fontWeight: 600,
          color: "var(--text)",
          margin: 0,
          padding: "0.4rem 0 0.7rem",
        }}
      >
        Kardamow
      </h1>
      <hr
        style={{
          border: 0,
          borderTop: "1px solid var(--rule)",
          margin: "0 0 0.4rem",
        }}
      />
      <nav
        aria-label="Screens"
        style={{
          display: "flex",
          justifyContent: "center",
          gap: "1.75rem",
          padding: "0.35rem 0 0.9rem",
        }}
      >
        {SCREENS.map((screen) => {
          const isActive = screen.href === active;
          return (
            <Link
              key={screen.href}
              href={screen.href}
              aria-current={isActive ? "page" : undefined}
              style={{
                fontFamily: "var(--body-stack)",
                fontSize: "0.95rem",
                textDecoration: "none",
                color: isActive ? "var(--ink)" : "var(--muted)",
                fontWeight: isActive ? 600 : 400,
                borderBottom: isActive
                  ? "2px solid var(--ink)"
                  : "2px solid transparent",
                paddingBottom: "0.15rem",
              }}
            >
              {screen.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
