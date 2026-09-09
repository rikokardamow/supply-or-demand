import { Masthead } from "@/components/chrome/Masthead";

/**
 * A placeholder for a screen the nav already offers but no session has built.
 *
 * The alternative is a 404 on a link the chrome itself renders, which reads as broken
 * rather than unfinished. It says plainly which session builds it -- an empty screen that
 * explains itself is honest; one that silently shows nothing is not.
 */
export function NotBuiltYet({
  title,
  href,
  session,
  summary,
}: {
  title: string;
  href: string;
  session: string;
  summary: string;
}) {
  return (
    <main className="term-panel" style={{ padding: "var(--space-4)" }}>
      <Masthead active={href} />
      <h2
        style={{
          fontFamily: "var(--font)",
          fontSize: "1.6rem",
          margin: "0.5rem 0 1rem",
        }}
      >
        {title}
      </h2>
      <p style={{ color: "var(--muted)", maxWidth: "44rem", lineHeight: 1.6 }}>
        Not built yet — {session}. {summary}
      </p>
    </main>
  );
}
