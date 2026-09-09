import {
  fetchFigures,
  fetchPosts,
  formatDate,
  formatNumber,
  formatSigned,
} from "@/lib/content";

/**
 * kardamow.com — the landing page.
 *
 * Built from the references supplied: a dark cinematic ground, one oversized display line,
 * glass cards floating over the lighting, pill buttons. The difference from those
 * references is that the floating stat cards hold **real, current figures** rather than
 * mocked percentages, and the writing list is the actual Substack feed. On a research
 * site, a landing page that invents its own numbers has lost the argument on the first
 * screen.
 *
 * Revalidated hourly. Both sources are cheap and neither changes faster than that.
 */
export const revalidate = 3600;

const CAPABILITIES = [
  {
    title: "Physical oil",
    body: "Crude and product balances, refinery economics, inter-regional movements, and the arithmetic that connects a cargo to a price.",
  },
  {
    title: "Gas and LNG",
    body: "European storage against its own history, send-out and inventory, and the contract structures that decide where a cargo actually goes.",
  },
  {
    title: "Sanctions and flows",
    body: "OFAC listings, vessel movements and the gap between a policy taking effect and a barrel changing course.",
  },
  {
    title: "Positioning",
    body: "What managed money is holding, as a share of the open interest it sits in — read against the physical picture, not instead of it.",
  },
];

export default async function Home() {
  const [figures, posts] = await Promise.all([fetchFigures(), fetchPosts(5)]);

  return (
    <main>
      {/* -- Bar ---------------------------------------------------------------- */}
      <header className="measure" style={{ paddingTop: "1.75rem", paddingBottom: "1rem" }}>
        <nav style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <span style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
            <span
              aria-hidden
              style={{
                width: 26,
                height: 26,
                borderRadius: 8,
                background: "linear-gradient(140deg, #6366f1, #0ea5e9)",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "0.82rem",
                fontWeight: 700,
              }}
            >
              K
            </span>
            <span style={{ fontWeight: 600, letterSpacing: "-0.02em" }}>Kardamow</span>
          </span>

          <span style={{ marginLeft: "auto", display: "flex", gap: "1.5rem" }}>
            <a href="#writing" style={{ fontSize: "0.9rem", color: "var(--muted)" }}>
              Writing
            </a>
            <a href="#work" style={{ fontSize: "0.9rem", color: "var(--muted)" }}>
              Work
            </a>
            <a
              href="https://data.kardamow.com"
              style={{ fontSize: "0.9rem", color: "var(--muted)" }}
            >
              Data
            </a>
          </span>
        </nav>
      </header>

      {/* -- Hero --------------------------------------------------------------- */}
      <section
        className="measure"
        style={{ paddingTop: "clamp(3rem, 9vw, 7rem)", paddingBottom: "4rem" }}
      >
        <p
          className="rise"
          style={{
            fontSize: "0.78rem",
            letterSpacing: "0.16em",
            textTransform: "uppercase",
            color: "var(--faint)",
            marginBottom: "1.6rem",
          }}
        >
          Independent research · Energy, macro, geopolitics
        </p>

        <h1
          className="rise"
          style={{
            fontSize: "clamp(2.7rem, 7.5vw, 5.4rem)",
            maxWidth: "16ch",
            marginBottom: "1.6rem",
            animationDelay: "80ms",
          }}
        >
          The structural imbalances most analysts miss.
        </h1>

        <p
          className="rise"
          style={{
            fontSize: "clamp(1rem, 1.5vw, 1.15rem)",
            color: "var(--muted)",
            maxWidth: "52ch",
            marginBottom: "2.4rem",
            animationDelay: "160ms",
          }}
        >
          Sanctions enforcement gaps, shipping routes that stop making sense, and the lag
          between a policy taking effect and a barrel changing course — worked from primary
          sources, before the price reflects any of it.
        </p>

        <div
          className="rise"
          style={{
            display: "flex",
            gap: "0.8rem",
            flexWrap: "wrap",
            animationDelay: "240ms",
          }}
        >
          <a className="btn btn-solid" href="https://kardamow.substack.com">
            Read the research
          </a>
          <a className="btn btn-ghost" href="https://data.kardamow.com">
            Explore the data →
          </a>
        </div>

        {/* The floating figures. Real, current, and each one is a number the research
            actually argues from. */}
        {figures.length > 0 ? (
          <div
            className="rise"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))",
              gap: "1rem",
              marginTop: "4rem",
              maxWidth: "44rem",
              animationDelay: "320ms",
            }}
          >
            {figures.map((f) => (
              <a
                key={f.label}
                href="https://data.kardamow.com"
                className="glass glass-link"
                style={{ padding: "1.1rem 1.2rem", display: "block" }}
              >
                <div
                  style={{
                    fontSize: "0.7rem",
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    color: "var(--faint)",
                    marginBottom: "0.7rem",
                  }}
                >
                  {f.label}
                </div>
                <div style={{ display: "flex", alignItems: "baseline", gap: "0.4rem" }}>
                  <span
                    className="tabular"
                    style={{ fontSize: "1.75rem", fontWeight: 600, letterSpacing: "-0.03em" }}
                  >
                    {formatNumber(f.value, f.digits)}
                  </span>
                  <span style={{ fontSize: "0.72rem", color: "var(--faint)" }}>
                    {f.unit ?? ""}
                  </span>
                </div>
                {f.change !== null ? (
                  <div
                    className="tabular"
                    style={{
                      marginTop: "0.5rem",
                      fontSize: "0.78rem",
                      fontWeight: 600,
                      color:
                        f.change === 0
                          ? "var(--faint)"
                          : f.change > 0
                            ? "var(--up)"
                            : "var(--down)",
                    }}
                  >
                    {formatSigned(f.change, f.digits)}
                  </div>
                ) : null}
              </a>
            ))}
          </div>
        ) : null}

        <p style={{ marginTop: "1.1rem", fontSize: "0.76rem", color: "var(--faint)" }}>
          Live from the same published data behind data.kardamow.com.
        </p>
      </section>

      {/* -- Writing ------------------------------------------------------------ */}
      {posts.length > 0 ? (
        <section
          id="writing"
          className="measure"
          style={{ paddingTop: "4rem", paddingBottom: "4rem" }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              gap: "1rem",
              marginBottom: "2rem",
            }}
          >
            <h2 style={{ fontSize: "clamp(1.5rem, 3vw, 2.1rem)" }}>Recent writing</h2>
            <a
              href="https://kardamow.substack.com"
              style={{ fontSize: "0.86rem", color: "var(--muted)" }}
            >
              All posts →
            </a>
          </div>

          <div style={{ display: "grid", gap: "0.7rem" }}>
            {posts.map((post) => (
              <a
                key={post.url}
                href={post.url}
                className="glass glass-link"
                style={{
                  padding: "1.1rem 1.3rem",
                  display: "flex",
                  alignItems: "baseline",
                  justifyContent: "space-between",
                  gap: "1.5rem",
                }}
              >
                <span style={{ fontSize: "1.02rem", fontWeight: 500 }}>{post.title}</span>
                <span
                  className="tabular"
                  style={{
                    fontSize: "0.76rem",
                    color: "var(--faint)",
                    whiteSpace: "nowrap",
                  }}
                >
                  {formatDate(post.date)}
                </span>
              </a>
            ))}
          </div>
        </section>
      ) : null}

      {/* -- Work --------------------------------------------------------------- */}
      <section
        id="work"
        className="measure"
        style={{ paddingTop: "4rem", paddingBottom: "4rem" }}
      >
        <h2 style={{ fontSize: "clamp(1.5rem, 3vw, 2.1rem)", marginBottom: "1rem" }}>
          What the work covers
        </h2>
        <p style={{ color: "var(--muted)", maxWidth: "56ch", marginBottom: "2rem" }}>
          Every claim is built from a source that can be checked, and the working data is
          published rather than described.
        </p>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(255px, 1fr))",
            gap: "1rem",
          }}
        >
          {CAPABILITIES.map((c) => (
            <div key={c.title} className="glass" style={{ padding: "1.4rem" }}>
              <h3 style={{ fontSize: "1.05rem", marginBottom: "0.6rem" }}>{c.title}</h3>
              <p style={{ fontSize: "0.9rem", color: "var(--muted)" }}>{c.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* -- Contact ------------------------------------------------------------ */}
      <section className="measure" style={{ paddingTop: "3rem", paddingBottom: "5rem" }}>
        <div
          className="glass"
          style={{
            padding: "clamp(1.8rem, 4vw, 3rem)",
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "1.5rem",
          }}
        >
          <div>
            <h2 style={{ fontSize: "clamp(1.4rem, 2.6vw, 1.9rem)", marginBottom: "0.6rem" }}>
              Get in touch
            </h2>
            <p style={{ color: "var(--muted)", maxWidth: "42ch" }}>
              For research, commissioned work, or a question about something published here.
            </p>
          </div>
          <a className="btn btn-solid" href="https://kardamow.substack.com">
            Subscribe
          </a>
        </div>

        <footer
          style={{
            marginTop: "3rem",
            paddingTop: "1.5rem",
            borderTop: "1px solid var(--edge)",
            display: "flex",
            flexWrap: "wrap",
            gap: "1rem",
            justifyContent: "space-between",
            fontSize: "0.8rem",
            color: "var(--faint)",
          }}
        >
          <span>© {new Date().getFullYear()} Kardamow</span>
          <span style={{ display: "flex", gap: "1.25rem" }}>
            <a href="https://kardamow.substack.com">Substack</a>
            <a href="https://data.kardamow.com">Data</a>
          </span>
        </footer>
      </section>
    </main>
  );
}
