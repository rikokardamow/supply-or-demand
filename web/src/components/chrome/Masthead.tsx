import Link from "next/link";

import { NavBar } from "@/components/chrome/NavBar";

/**
 * The masthead: a centred wordmark over the section navigation, mirroring
 * `apps/dashboard/app.py` so the web UI and the Streamlit app read as one publication.
 * No left rail and no sidebar -- that layout predates the 2026-09-08 restyle (Spec 33 §5).
 *
 * The wordmark is printed once, at the top, and scrolls away; the navigation stays with
 * the reader and grows a compact mark in its place. That is the newspaper's own
 * behaviour, and on a page of eight charts it is the difference between always knowing
 * where you are and having to scroll back to find out.
 *
 * `full` gives the front page the larger setting. A section page opens on its own title,
 * so a wordmark at display size there would sit above -- and outweigh -- the thing the
 * reader actually came for.
 *
 * The wordmark is the document's only `<h1>`; each page's own title is an `<h2>` and each
 * panel heading an `<h3>`, giving one valid descending outline with "Kardamow" at its top.
 */

export const SCREENS = [
  { href: "/", label: "Overview" },
  { href: "/balances", label: "Balances" },
  { href: "/prices", label: "Prices" },
  { href: "/supply", label: "Supply" },
  { href: "/gas", label: "Gas" },
  { href: "/curves", label: "Curves" },
  { href: "/positioning", label: "Positioning" },
  { href: "/vessels", label: "Vessels" },
  { href: "/events", label: "Events" },
  { href: "/sanctions", label: "Sanctions" },
] as const;

export function Masthead({
  active,
  full = false,
}: {
  active?: string;
  full?: boolean;
}) {
  // The navigation is a sibling of <header>, not a child of it, and deliberately so. A
  // `position: sticky` element only stays stuck while its own parent box is still in
  // view; nested inside a <header> that ends an inch below it, the bar would unstick the
  // moment the masthead scrolled past -- which is exactly when it becomes useful. As a
  // child of the page it sticks for the whole document. <nav> outside <header> is valid.
  return (
    <>
      <header className="bleed">
        <div className="bleed-inner">
          <h1
            style={{
              textAlign: "center",
              fontFamily: "var(--heading-stack)",
              fontSize: full ? "var(--size-wordmark)" : "2.1rem",
              fontWeight: 600,
              color: "var(--ink)",
              letterSpacing: "-0.02em",
              margin: 0,
              padding: full
                ? "var(--space-8) 0 var(--space-3)"
                : "var(--space-4) 0 var(--space-2)",
            }}
          >
            <Link href="/" style={{ textDecoration: "none", color: "inherit" }}>
              Kardamow
            </Link>
          </h1>

          {full ? (
            <p
              style={{
                textAlign: "center",
                fontSize: "var(--size-micro)",
                letterSpacing: "0.16em",
                textTransform: "uppercase",
                color: "var(--muted)",
                margin: "0 0 var(--space-6)",
              }}
            >
              Energy and macro research
            </p>
          ) : null}
        </div>
      </header>

      <NavBar active={active} />
    </>
  );
}
