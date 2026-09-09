import Image from "next/image";

import { Globe } from "@/components/Globe";
import {
  fetchFigures,
  fetchPosts,
  formatDate,
  formatNumber,
  formatSigned,
} from "@/lib/content";
import { fetchVesselPoints } from "@/lib/vessels";

/**
 * kardamow.com — the landing page.
 *
 * Every line of copy here is the author's own, taken from the publication's About page
 * rather than written for it. That matters more than it sounds: a portfolio for a writer
 * whose whole argument is primary sources cannot open with copy invented by someone else,
 * and the About page already says it better than a rewrite would.
 *
 * The figures, the vessel positions and the post list are all live. Nothing on the page is
 * a placeholder.
 */
export const revalidate = 3600;

const EMAIL = "riko@kardamow.com";

/**
 * The three areas, condensed from the About page's own descriptions.
 *
 * Each keeps the line that states the mechanism rather than the subject, because that is
 * what distinguishes this from a topic list: "a refiner who pulls throughput has voted
 * with a plant, not a forecast" says what the work does.
 */
const COVERAGE = [
  {
    title: "Energy fundamentals and physical markets",
    body: "The crude curve first — backwardation, contango, and the term-structure dislocations that signal where the physical market disagrees with paper — then LNG and gas across JKM, TTF and Henry Hub, and the cargo routing that shows where tightness is real and where it is only narrative.",
    line: "Crack spreads tell you what the market expects; run cuts tell you what refiners actually believe. When the two detach, take the run cut — a refiner who pulls throughput has voted with a plant, not a forecast.",
  },
  {
    title: "Geopolitics, trade and macro",
    body: "Sanctions architecture and the enforcement gaps beneath it. Sovereign risk and the chain that carries a basis-point move in Treasuries through the dollar, through EM currencies, through import economics, and into physical demand.",
    line: "Policy moves the molecule on a lag and the market prices the policy on the day. The gap between those two clocks is where a sanctions regime is either enforced or quietly routed around — so track the workaround, not the designation.",
  },
  {
    title: "Infrastructure and the transition",
    body: "Pipeline and export-terminal capacity, and the basis differentials that throughput constraints create when ambition outruns steel. Dark spreads, spark spreads and dispatch order — which fuel actually clears the merit order.",
    line: "Steel is slower than capital and capital is slower than belief, so every transition story eventually becomes a bottleneck story — and the bottleneck, once it binds, sets the price for everything queued behind it.",
  },
];

/** Real, attributed, from the publication's own page. Nothing paraphrased. */
const TESTIMONIALS = [
  {
    quote:
      "Kardamow maps where energy, geopolitics, and finance intersect before the market prices it in. Riko tracks the structural imbalances most analysts miss — sanctions gaps, cargo routing decisions, the lag between policy and physical trade.",
    name: "Quy Ma",
    outlet: "The Marketplace by Quy Ma",
  },
  {
    quote:
      "Real primary-source work — built the Kharg loading data himself and got the corridor argument right before most people had the numbers.",
    name: "William David",
    outlet: "The Chokepoint",
  },
  {
    quote:
      "A sharp, independent Substack exploring the crossroads of energy markets, finance, and geopolitics. Clear-eyed analysis of how power, capital, and resources shape the global economic landscape.",
    name: "Panda Perspectives",
    outlet: "Panda Perspectives",
  },
];

const TIERS = [
  {
    name: "Free",
    price: "€0",
    body: "Previews of every piece, and the occasional one unlocked in full — enough to judge the method on the mechanism rather than the marketing.",
  },
  {
    name: "Kardamow Pro",
    price: "€25/month",
    note: "or €250/year",
    body: "Every publication and the complete archive back to 2024, including the long-form synthesis behind the weekday work.",
    featured: true,
  },
  {
    name: "Kardamowians",
    price: "€500/year",
    body: "The founding tier. Everything in Pro, plus a direct line — one-to-one on the markets, and the questions that do not fit a comment thread.",
  },
];

export default async function Home() {
  const [figures, posts, vessels] = await Promise.all([
    fetchFigures(),
    fetchPosts(5),
    fetchVesselPoints(),
  ]);

  return (
    <main>
      {/* -- Bar ---------------------------------------------------------------- */}
      <header
        style={{
          borderBottom: "1px solid var(--border)",
          position: "sticky",
          top: 0,
          background: "rgba(255,255,255,0.85)",
          backdropFilter: "blur(10px)",
          zIndex: 20,
        }}
      >
        <div
          className="measure"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "1.5rem",
            paddingTop: "0.9rem",
            paddingBottom: "0.9rem",
          }}
        >
          <span
            style={{
              fontWeight: 600,
              letterSpacing: "-0.03em",
              fontSize: "1.1rem",
            }}
          >
            Kardamow
          </span>
          <nav style={{ display: "flex", gap: "1.5rem", marginLeft: "auto" }}>
            {[
              ["Writing", "#writing"],
              ["Coverage", "#coverage"],
              ["About", "#about"],
              ["Data", "https://data.kardamow.com"],
            ].map(([label, href]) => (
              <a
                key={label}
                href={href}
                style={{
                  fontSize: "0.9rem",
                  color: "var(--muted)",
                  fontWeight: 500,
                }}
              >
                {label}
              </a>
            ))}
          </nav>
          <a className="btn btn-solid" href="https://kardamow.substack.com">
            Subscribe
          </a>
        </div>
      </header>

      {/* -- Hero --------------------------------------------------------------- */}
      <section
        className="measure"
        style={{ paddingTop: "5rem", paddingBottom: "3rem" }}
      >
        <div className="rise" style={{ marginBottom: "1.6rem" }}>
          <span className="eyebrow">Independent research</span>
          <span
            style={{
              marginLeft: "0.8rem",
              fontSize: "0.88rem",
              color: "var(--muted)",
            }}
          >
            Energy, macro and geopolitics · published most days
          </span>
        </div>

        <h1
          className="rise"
          style={{
            fontSize: "clamp(2.6rem, 6vw, 4.6rem)",
            maxWidth: "20ch",
            marginBottom: "1.4rem",
            animationDelay: "60ms",
          }}
        >
          It writes the mechanism, not the event.
        </h1>

        <p
          className="rise"
          style={{
            fontSize: "clamp(1.05rem, 1.5vw, 1.2rem)",
            color: "var(--muted)",
            maxWidth: "62ch",
            marginBottom: "2.2rem",
            animationDelay: "120ms",
          }}
        >
          Independent research on the seam where energy, finance and geopolitics
          meet — the tanker rerouted in the night, the refinery run cut nobody
          reported, the central-bank decision that will move a cargo three weeks
          from now, sitting quietly unpriced while the rest of the feed reads
          yesterday&rsquo;s headline.
        </p>

        <div
          className="rise"
          style={{
            display: "flex",
            gap: "0.7rem",
            flexWrap: "wrap",
            animationDelay: "180ms",
          }}
        >
          <a className="btn btn-solid" href="https://kardamow.substack.com">
            Read the research
          </a>
          <a className="btn btn-ghost" href="https://data.kardamow.com">
            Explore the data
          </a>
        </div>
      </section>

      {/* -- The visual: live figures beside the globe --------------------------- */}
      <section className="measure" style={{ paddingBottom: "5rem" }}>
        <div
          className="frame rise"
          style={{
            display: "grid",
            gridTemplateColumns: "1fr",
            animationDelay: "240ms",
          }}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit, minmax(min(100%, 22rem), 1fr))",
              alignItems: "center",
              gap: "2rem",
              padding: "clamp(1.5rem, 4vw, 3rem)",
            }}
          >
            <div>
              <p
                style={{
                  fontSize: "0.74rem",
                  letterSpacing: "0.09em",
                  textTransform: "uppercase",
                  color: "var(--faint)",
                  marginBottom: "1.4rem",
                }}
              >
                Live from the working data
              </p>

              {figures.length > 0 ? (
                <div
                  style={{
                    display: "grid",
                    gap: "0.9rem",
                    marginBottom: "1.6rem",
                  }}
                >
                  {figures.map((f) => (
                    <div
                      key={f.label}
                      style={{
                        display: "flex",
                        alignItems: "baseline",
                        justifyContent: "space-between",
                        gap: "1rem",
                        paddingBottom: "0.9rem",
                        borderBottom: "1px solid var(--border)",
                      }}
                    >
                      <span
                        style={{ fontSize: "0.92rem", color: "var(--muted)" }}
                      >
                        {f.label}
                      </span>
                      <span
                        style={{
                          display: "flex",
                          alignItems: "baseline",
                          gap: "0.55rem",
                        }}
                      >
                        <span
                          className="tabular"
                          style={{ fontSize: "1.5rem", fontWeight: 600 }}
                        >
                          {formatNumber(f.value, f.digits)}
                        </span>
                        <span
                          style={{ fontSize: "0.74rem", color: "var(--faint)" }}
                        >
                          {f.unit ?? ""}
                        </span>
                        {f.change !== null ? (
                          <span
                            className="tabular"
                            style={{
                              fontSize: "0.8rem",
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
                          </span>
                        ) : null}
                      </span>
                    </div>
                  ))}
                </div>
              ) : null}

              <p
                style={{
                  fontSize: "0.82rem",
                  color: "var(--faint)",
                  maxWidth: "40ch",
                }}
              >
                {vessels.length > 0
                  ? `${vessels.length.toLocaleString("en-GB")} vessel positions from the latest AIS capture, and prices from the same published data behind data.kardamow.com. Terrestrial AIS, so empty ocean means no receiver rather than no ships.`
                  : "Prices from the same published data behind data.kardamow.com."}
              </p>
            </div>

            {vessels.length > 0 ? <Globe points={vessels} /> : null}
          </div>
        </div>
      </section>

      {/* -- Writing ------------------------------------------------------------ */}
      {posts.length > 0 ? (
        <section
          id="writing"
          className="measure"
          style={{ paddingTop: "1rem", paddingBottom: "5rem" }}
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
            <h2 style={{ fontSize: "clamp(1.7rem, 3vw, 2.4rem)" }}>
              Recent writing
            </h2>
            <a
              href="https://kardamow.substack.com/archive"
              style={{
                fontSize: "0.9rem",
                color: "var(--accent)",
                fontWeight: 500,
              }}
            >
              Full archive →
            </a>
          </div>

          <div>
            {posts.map((post) => (
              <a
                key={post.url}
                href={post.url}
                className="row"
                style={{
                  display: "grid",
                  gridTemplateColumns: "minmax(0, 1fr) auto",
                  gap: "1.5rem",
                  alignItems: "start",
                  padding: "1.3rem 0.6rem",
                }}
              >
                <span>
                  <span
                    style={{
                      display: "block",
                      fontSize: "1.1rem",
                      fontWeight: 600,
                      letterSpacing: "-0.02em",
                      marginBottom: "0.35rem",
                    }}
                  >
                    {post.title}
                  </span>
                  {post.dek ? (
                    <span
                      style={{
                        display: "block",
                        fontSize: "0.92rem",
                        color: "var(--muted)",
                        maxWidth: "78ch",
                      }}
                    >
                      {post.dek}
                    </span>
                  ) : null}
                </span>
                <span
                  className="tabular"
                  style={{
                    fontSize: "0.8rem",
                    color: "var(--faint)",
                    whiteSpace: "nowrap",
                    paddingTop: "0.25rem",
                  }}
                >
                  {formatDate(post.date)}
                </span>
              </a>
            ))}
          </div>
        </section>
      ) : null}

      {/* -- Coverage ----------------------------------------------------------- */}
      <section
        id="coverage"
        style={{
          background: "var(--ground)",
          borderTop: "1px solid var(--border)",
        }}
      >
        <div
          className="measure"
          style={{ paddingTop: "5rem", paddingBottom: "5rem" }}
        >
          <h2
            style={{
              fontSize: "clamp(1.7rem, 3vw, 2.4rem)",
              marginBottom: "0.9rem",
            }}
          >
            What it covers
          </h2>
          <p
            style={{
              color: "var(--muted)",
              maxWidth: "64ch",
              marginBottom: "2.5rem",
            }}
          >
            Three areas, each the same question asked of a different set of
            pipes: where does the physical market quietly disagree with the
            paper one, and how long before the paper is forced to notice?
          </p>

          <div style={{ display: "grid", gap: "1rem" }}>
            {COVERAGE.map((area) => (
              <div
                key={area.title}
                className="card"
                style={{
                  padding: "clamp(1.4rem, 3vw, 2rem)",
                  display: "grid",
                  gridTemplateColumns:
                    "repeat(auto-fit, minmax(min(100%, 24rem), 1fr))",
                  gap: "1.5rem",
                }}
              >
                <div>
                  <h3 style={{ fontSize: "1.15rem", marginBottom: "0.7rem" }}>
                    {area.title}
                  </h3>
                  <p style={{ fontSize: "0.94rem", color: "var(--muted)" }}>
                    {area.body}
                  </p>
                </div>
                <p
                  style={{
                    fontSize: "0.98rem",
                    borderLeft: "2px solid var(--accent)",
                    paddingLeft: "1.1rem",
                    alignSelf: "center",
                  }}
                >
                  {area.line}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* -- About -------------------------------------------------------------- */}
      <section
        id="about"
        className="measure"
        style={{ paddingTop: "5rem", paddingBottom: "4rem" }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns:
              "repeat(auto-fit, minmax(min(100%, 26rem), 1fr))",
            gap: "clamp(2rem, 5vw, 4rem)",
          }}
        >
          <div>
            <h2
              style={{
                fontSize: "clamp(1.7rem, 3vw, 2.4rem)",
                marginBottom: "1.2rem",
              }}
            >
              Who writes this
            </h2>
            <p style={{ color: "var(--muted)", marginBottom: "1rem" }}>
              I write under a pen name, and I work the seam between two desks
              that, in most institutions, barely speak to each other. I came up
              through fixed income — the whole life of a trade, from execution
              through settlement to the risk numbers behind it — and carried
              that into energy economics.
            </p>
            <p style={{ color: "var(--muted)", marginBottom: "1.6rem" }}>
              I put the two together because the questions worth asking kept
              living in the space between them, and because the settlement side
              is where I learned to see that transmission first: a trade that
              fails to settle, a margin call that lands a day early, a letter of
              credit that stops clearing all show up in the back office weeks
              before they show up in a price.
            </p>
            <p style={{ fontSize: "1.05rem", fontWeight: 500 }}>
              I learned the plumbing of both markets from the back office
              forward, which is the direction in which the plumbing actually
              leaks.
            </p>
          </div>

          <div>
            <h3
              style={{
                fontSize: "0.74rem",
                letterSpacing: "0.09em",
                textTransform: "uppercase",
                color: "var(--faint)",
                marginBottom: "1.2rem",
              }}
            >
              The frame
            </h3>
            <p style={{ color: "var(--muted)", marginBottom: "1rem" }}>
              The work rests on two foundations and refuses to choose between
              them. Reflexivity — that what participants believe feeds back into
              the thing they imagine they are merely measuring — and the
              physical mechanics of the trade: the cargo, the freight, the
              war-risk premium, the regasification slot, the breakeven at which
              floating storage stops paying its carry.
            </p>
            <p style={{ color: "var(--muted)" }}>
              Reflexivity with no contact with the molecule is a seminar. A flow
              desk with no model of why beliefs move is a price feed with no
              memory. Kardamow lives at the join — close enough to know how a
              barrel actually moves, far enough back to see the belief that is
              moving it.
            </p>
          </div>
        </div>
      </section>

      {/* -- The Red Boy -------------------------------------------------------- */}
      <section
        style={{
          background: "var(--ground)",
          borderTop: "1px solid var(--border)",
        }}
      >
        <div
          className="measure"
          style={{ paddingTop: "5rem", paddingBottom: "5rem" }}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit, minmax(min(100%, 20rem), 1fr))",
              gap: "clamp(2rem, 5vw, 4rem)",
              alignItems: "center",
            }}
          >
            {/* Goya, "Manuel Osorio Manrique de Zuniga", 1787-88. The Met, 49.7.41, and in
                the public domain -- released CC0 under the museum's Open Access policy,
                which is why it can sit on a page that sells subscriptions. */}
            <figure style={{ margin: 0 }}>
              <Image
                src="/red-boy.jpg"
                alt={
                  "Goya's portrait of Manuel Osorio Manrique de Zuniga: a child in red " +
                  "silk holding a string tied to a magpie, with a cage of finches beside " +
                  "him and three cats watching the bird from the shadows."
                }
                width={900}
                height={1200}
                priority={false}
                style={{
                  width: "100%",
                  height: "auto",
                  borderRadius: "var(--r-md)",
                  border: "1px solid var(--border)",
                  display: "block",
                }}
              />
              <figcaption
                style={{
                  marginTop: "0.8rem",
                  fontSize: "0.76rem",
                  color: "var(--faint)",
                  lineHeight: 1.5,
                }}
              >
                Francisco de Goya, <em>Manuel Osorio Manrique de Zuñiga</em>,
                1787&ndash;88. The Metropolitan Museum of Art, 49.7.41. Public
                domain.
              </figcaption>
            </figure>

            <div>
              <h2
                style={{
                  fontSize: "clamp(1.7rem, 3vw, 2.4rem)",
                  marginBottom: "1.2rem",
                }}
              >
                Why the Red Boy
              </h2>
              <p style={{ color: "var(--muted)", marginBottom: "1rem" }}>
                A child in scarlet silk stands at the centre of the canvas,
                perfectly composed, holding a string tied to a tame magpie.
                Around him sit a cage of finches and three cats, and the cats
                are watching the bird with the particular stillness of things
                that have decided to wait.
              </p>
              <p style={{ color: "var(--muted)", marginBottom: "1rem" }}>
                At first glance it is a portrait of innocence. Look a second
                longer and it becomes a study in power, fragility and risk —
                apparent stability inside a complex system, holding only for as
                long as nothing at the edge of the frame decides to move.
              </p>
              <p style={{ color: "var(--muted)", marginBottom: "1.6rem" }}>
                That is the whole of how commodity markets work, compressed into
                a single painting: a calm that is real while it lasts and
                entirely conditional, resting on the standing assumption that
                the other party will not act — that the cats will go on waiting
                — even as the conditions keeping them still are quietly
                changing.
              </p>
              <p
                style={{
                  fontSize: "1.1rem",
                  fontWeight: 500,
                  borderLeft: "2px solid var(--accent)",
                  paddingLeft: "1.1rem",
                }}
              >
                The most dangerous moment in any market is the one that looks
                most like safety. Everything published here is an attempt to
                keep watching the cats.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* -- Testimonials ------------------------------------------------------- */}
      <section className="measure" style={{ paddingBottom: "5rem" }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns:
              "repeat(auto-fit, minmax(min(100%, 19rem), 1fr))",
            gap: "1rem",
          }}
        >
          {TESTIMONIALS.map((t) => (
            <figure
              key={t.name}
              className="card"
              style={{ padding: "1.5rem", margin: 0 }}
            >
              <blockquote
                style={{ margin: 0, fontSize: "0.95rem", lineHeight: 1.6 }}
              >
                &ldquo;{t.quote}&rdquo;
              </blockquote>
              <figcaption
                style={{
                  marginTop: "1.1rem",
                  fontSize: "0.85rem",
                  color: "var(--faint)",
                }}
              >
                <span style={{ color: "var(--text)", fontWeight: 600 }}>
                  {t.name}
                </span>{" "}
                · {t.outlet}
              </figcaption>
            </figure>
          ))}
        </div>
      </section>

      {/* -- Tiers -------------------------------------------------------------- */}
      <section
        style={{
          background: "var(--ground)",
          borderTop: "1px solid var(--border)",
        }}
      >
        <div
          className="measure"
          style={{ paddingTop: "5rem", paddingBottom: "5rem" }}
        >
          <h2
            style={{
              fontSize: "clamp(1.7rem, 3vw, 2.4rem)",
              marginBottom: "0.9rem",
            }}
          >
            What it costs
          </h2>
          <p
            style={{
              color: "var(--muted)",
              maxWidth: "58ch",
              marginBottom: "2.5rem",
            }}
          >
            Each note is built to do one thing: make the rest of your morning
            feed redundant.
          </p>

          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit, minmax(min(100%, 17rem), 1fr))",
              gap: "1rem",
            }}
          >
            {TIERS.map((tier) => (
              <div
                key={tier.name}
                className="card"
                style={{
                  padding: "1.6rem",
                  borderColor: tier.featured ? "var(--text)" : "var(--border)",
                }}
              >
                <div
                  style={{
                    fontSize: "0.95rem",
                    fontWeight: 600,
                    marginBottom: "0.6rem",
                  }}
                >
                  {tier.name}
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    gap: "0.5rem",
                  }}
                >
                  <span
                    className="tabular"
                    style={{
                      fontSize: "1.8rem",
                      fontWeight: 600,
                      letterSpacing: "-0.03em",
                    }}
                  >
                    {tier.price}
                  </span>
                  {tier.note ? (
                    <span style={{ fontSize: "0.8rem", color: "var(--faint)" }}>
                      {tier.note}
                    </span>
                  ) : null}
                </div>
                <p
                  style={{
                    fontSize: "0.9rem",
                    color: "var(--muted)",
                    marginTop: "0.9rem",
                  }}
                >
                  {tier.body}
                </p>
              </div>
            ))}
          </div>

          <p
            style={{
              fontSize: "0.85rem",
              color: "var(--faint)",
              marginTop: "1.5rem",
            }}
          >
            Group access runs at twenty-five per cent off for four or more seats
            — built for desks, funds and family offices. For institutional
            terms,{" "}
            <a href={`mailto:${EMAIL}`} style={{ color: "var(--accent)" }}>
              {EMAIL}
            </a>
            .
          </p>
        </div>
      </section>

      {/* -- Contact ------------------------------------------------------------ */}
      <section
        className="measure"
        style={{ paddingTop: "5rem", paddingBottom: "4rem" }}
      >
        <h2
          style={{
            fontSize: "clamp(1.7rem, 3vw, 2.4rem)",
            marginBottom: "0.9rem",
          }}
        >
          Get in touch
        </h2>
        <p
          style={{
            color: "var(--muted)",
            maxWidth: "52ch",
            marginBottom: "1.8rem",
          }}
        >
          For inquiries, collaboration, or a good-faith exchange of ideas —
          including a good-faith disagreement worth having.
        </p>
        <div style={{ display: "flex", gap: "0.7rem", flexWrap: "wrap" }}>
          <a className="btn btn-solid" href={`mailto:${EMAIL}`}>
            {EMAIL}
          </a>
          <a className="btn btn-ghost" href="https://kardamow.substack.com">
            Subscribe
          </a>
        </div>

        <footer
          style={{
            marginTop: "4rem",
            paddingTop: "1.5rem",
            borderTop: "1px solid var(--border)",
            display: "flex",
            flexWrap: "wrap",
            gap: "1rem",
            justifyContent: "space-between",
            fontSize: "0.82rem",
            color: "var(--faint)",
          }}
        >
          <span>© {new Date().getFullYear()} Riko Kardamow</span>
          <span style={{ display: "flex", gap: "1.4rem" }}>
            <a href="https://kardamow.substack.com">Substack</a>
            <a href="https://data.kardamow.com">Data</a>
            <a href={`mailto:${EMAIL}`}>Email</a>
          </span>
        </footer>

        <p
          style={{
            marginTop: "2rem",
            fontSize: "0.76rem",
            color: "var(--faint)",
            maxWidth: "78ch",
            lineHeight: 1.6,
          }}
        >
          Everything published by Kardamow is for informational purposes only
          and reflects the author&rsquo;s own views. Not a licensed investment
          professional, a registered adviser or a broker-dealer; nothing here is
          financial advice, a recommendation to enter any trade, or a
          solicitation to buy or sell any asset.
        </p>
      </section>
    </main>
  );
}
