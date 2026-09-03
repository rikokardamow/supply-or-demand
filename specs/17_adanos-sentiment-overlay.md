# Spec 17 — Adanos Market-Sentiment Overlay (Energy Complex)

**Est. 2–3 h · Prereq: Spec 00. Independent — new `pipelines/adanos/`, feeds a new
section on page `10_macro.py`. No new schema needed.**

## Objective & alpha question
Reddit/X/News/Polymarket buzz and sentiment scores for a broad, curated basket of
energy-sector tickers, as a market-attention overlay. Question: *does retail/social
attention on energy equities lead or merely echo what the physical fundamentals
(stocks, flows, cracks, macro) this dashboard already tracks are showing?* Framed
throughout as attention/flow data, never as a trading signal — see the Honesty rule
below.

## What Adanos is, and the real limits on the free tier
A commercial API (`api.adanos.org`) giving buzz/attention and sentiment scores for
stock tickers across four independent platform perspectives (Reddit, X/Twitter, News,
Polymarket prediction markets), plus a separate Reddit-crypto product this spec does
not use. From the vendor's own published API reference (pasted into this project by
the operator; **treat every field name and limit below as vendor-documented, not yet
confirmed against this project's own key** — the first implementation step is a real
verification pull):
- **Free tier**: 250 requests/month, 30-day historical lookback, 100 req/min burst
  cap, no commercial-use licence, no raw-mentions or text-sentiment-analysis
  endpoints (Professional-only).
- `/{platform}/stocks/v1/compare?tickers=A,B,C...` — up to 10 tickers per call,
  returns `buzz_score` (0–100), `trend`, `sentiment_score` (−1.0 to +1.0, nullable),
  `bullish_pct`/`bearish_pct`, plus platform-specific volume fields
  (mentions/unique_posts/subreddit_count for Reddit, trade_count/market_count for
  Polymarket, etc.).
- `/reddit/stocks/v1/trending/sectors` — sector-level buzz, no ticker filter; this
  project filters to the "Energy" sector row in code since the endpoint itself takes
  no sector parameter.
- Auth: `X-API-Key` header. A real key exists in `.env` (`settings.adanos_api_key`).
- Successful responses include `X-RateLimit-Remaining-Monthly` — **log this after
  every call** so real usage against the 250/month budget is always visible, not
  discovered only when calls start failing.

## The curated ticker universe — 57 tickers, organised by segment and geography
Not the full 35,000-ticker universe — a hand-curated basket giving broad energy-
complex and geographic coverage while keeping `/compare` call volume small (10
tickers per call). Every symbol below is a real, currently-tradable ticker to the
best of this project's knowledge as of the spec being written — **every one still
needs a live `/search` or `/compare` existence check as the mandatory first
implementation step, before any pull code is written against it** (`pipelines/
adanos/tickers.py` is not populated by copying this table blindly — verify, then
drop/replace whatever doesn't resolve, and record the real outcome in `pipelines/
adanos/CLAUDE.md`).

| Segment | Tickers | Count |
|---|---|---|
| US integrated majors / large independents | XOM, CVX, COP, OXY, FANG | 5 |
| US E&P | DVN, EOG | 2 |
| US refiners | VLO, MPC, PSX, PBF | 4 |
| US midstream / pipelines | KMI, WMB, OKE, ET, EPD | 5 |
| Oilfield services | SLB, HAL, BKR, NOV | 4 |
| Gas / LNG | LNG, AR, EQT | 3 |
| Coal | BTU | 1 |
| Uranium / nuclear fuel | CCJ, UEC, UUUU | 3 |
| Renewables | NEE, FSLR, ENPH, BEP | 4 |
| International majors / ADRs (UK, NL, FR, Norway, Italy, Brazil, Canada) | SHEL, BP, TTE, EQNR, E, PBR, SU, CNQ, CVE | 9 |
| Asia-Pacific | WDS | 1 |
| Energy-complex ETFs (broad + thematic + regional) | XLE, VDE, IXC, USO, UNG, XOP, OIH, AMLP, TAN, ICLN, URA | 11 |
| **OPEC / OPEC+ geographic exposure** | GENL, GKP, SEPL, OANDO, ARADEL | 5 |
| **Total** | | **57** |

### Why 57, and why these specific tickers
**Deliberately excludes several plausible-looking tickers** whose real 2024–2025
M&A activity makes their current listing status uncertain: `MRO` (Marathon Oil,
acquired by ConocoPhillips), `PXD` (Pioneer Natural Resources, acquired by
ExxonMobil), `HES` (Hess, acquired by Chevron), `CHK`/`CEIX` (Chesapeake and CONSOL
both went through 2024–2025 mergers under different resulting tickers — Expand
Energy and Core Natural Resources respectively, exact new tickers not confirmed here
deliberately rather than guessed). Noted explicitly so a future session doesn't
wonder why an "obvious" ticker is missing.

**OPEC/OPEC+ geographic exposure, added per explicit request**: Libya, Nigeria,
Iraq, and Venezuela's own national oil companies (NOC Libya, NNPC, SOMO, PDVSA
respectively) are all wholly state-owned with **no publicly-traded shares at all** —
there is no honest direct ticker for them, and none is invented here. Real,
currently-listed pure-plays give genuine indirect exposure instead:
- **Iraq (Kurdistan region)** — `GENL` (Genel Energy, London Stock Exchange) and
  `GKP` (Gulf Keystone Petroleum, LSE), both real standalone Kurdistan-focused E&P
  companies.
- **Nigeria** — `SEPL` (Seplat Energy, dual LSE/NGX-listed indigenous major),
  `OANDO` (Oando, Nigerian Exchange), `ARADEL` (Aradel Holdings, NGX, a 2024 IPO).
- **Libya and Venezuela specifically**: no credible standalone listed pure-play was
  identified for either. Their real exposure in this basket is indirect only,
  through majors already listed above with actual on-the-ground operations — `E`
  (Eni) and `TTE` (TotalEnergies) both have real Libya joint-venture operations;
  `CVX` (Chevron) holds the only major Western oil company's active licensed joint
  venture in Venezuela. Stated here explicitly rather than silently omitted.

**The 5 OPEC/OPEC+-exposure tickers are the most likely to fail the existence
check**: Adanos's whole product is framed around Reddit/X *retail* sentiment, which
is overwhelmingly a US-market phenomenon, and `GENL`/`GKP`/`SEPL`/`OANDO`/`ARADEL`
are LSE/NGX-listed, not NYSE/NASDAQ. Verify each individually against `/search` or
`/compare` and drop any that don't resolve — do not assume Adanos's own "35,000+
tickers" marketing claim extends to these specific foreign listings.

### Budget arithmetic
57 tickers ÷ 10-per-`/compare`-call = 6 batched calls per platform × 4 platforms
(Reddit, X, News, Polymarket) = 24, + 1 `/trending/sectors` (Reddit, filtered to
Energy) call = **25 calls per weekly pull** ≈ 108 calls/month at 4.33 weeks/month —
**43% of the 250/month free-tier cap**. Deliberately mid-range: broad real coverage
across the energy complex and its major producing geographies, with comfortable
headroom left over for the implementation-time verification calls above and any
future manual `/search` exploration, without spending the whole monthly budget on
one weekly job.

## Data model — fits the existing `ts_long` schema, no new schema needed
Per ticker × platform × date, two series: `series_id =
adanos.{platform}.{ticker_lower}.buzz_score` and
`adanos.{platform}.{ticker_lower}.sentiment_score` — e.g.
`adanos.reddit.xom.buzz_score`, `adanos.news.shel.sentiment_score`. `source="adanos"`,
`geo="US"` for US-listed tickers, the real listing country's 2-letter code for the
international/OPEC-exposure names (e.g. `geo="GB"` for `GENL`/`GKP`/`SEPL`,
`geo="NG"` for `OANDO`/`ARADEL`), `unit="score_0_100"` for buzz /
`"score_neg1_to_1"` for sentiment, `freq="D"`. Sector trend →
`adanos.reddit.sector_energy.buzz_score` (`geo="US"`, Adanos's own sector rollup is
itself US-market-centric).

## Claude Code session (weekday, 1.5–2 h)
> Read CLAUDE.md, specs/17_adanos-sentiment-overlay.md. Live-verify the ticker
> universe (via batched `/compare` calls — this doubles as the real field-shape
> confirmation for `/compare` and `/trending/sectors`); drop/replace anything that
> doesn't resolve, record the real final list and outcome in `pipelines/adanos/
> CLAUDE.md`. Build `pipelines/adanos/client.py` (`.compare(tickers, platform)`,
> `.trending_sectors(platform="reddit")`, `X-API-Key` auth, no client-side retry —
> matches `pipelines/macro/frankfurter_client.py`'s plain single-request style),
> `tickers.py`, `pull_adanos.py` (batches of ≤10 tickers per `/compare` call, one
> call per platform, per-platform `requests.exceptions.RequestException` resilience
> matching `pipelines/macro/pull_macro.py`'s established pattern, `ts_long` mapping
> per the series_id convention above, logs `X-RateLimit-Remaining-Monthly` after
> every call), `pull_weekly.py` (thin re-export of `pull_adanos.main`, matching
> `pipelines/macro/pull_weekly.py`'s precedent). Add `X-API-Key` to `tests/
> conftest.py`'s `filter_headers`. Cassette tests for `client.py`; a resilience test
> proving one platform's `RequestException` doesn't abort the other three.

## Visualisation spec — extends page `10_macro.py`, no new page needed
A new subheader "Energy-sector sentiment (Adanos)" with three visuals:
1. **Buzz-by-platform** — the ticker basket's mean `buzz_score` per platform per
   day, one line per platform (Reddit/X/News/Polymarket), plotted via a plain inline
   `go.Figure`/`go.Scatter` (no new `core/theme.py` primitive — matches this page's
   own existing precedent, which already builds a bespoke inline multi-line figure
   for the real-vs-nominal section rather than extending `theme.py` for a one-off
   shape). House colours: `NAVY`/`LIGHT_BLUE`/`RED`/`GREY`, one per platform.
2. **Latest sentiment by ticker, across platforms** — a plain inline grouped
   `go.Bar`, one bar-group per ticker (or a representative subset if 57 tickers is
   too dense to read — use judgement at implementation time, e.g. the basket's
   top-N by buzz_score that week), one bar per platform per group, same house
   colours as above.
3. **Sector buzz trend** — the Reddit energy-sector trend line, via the existing
   `core.theme.simple_time_series_chart` directly (single series, no new primitive
   needed).

**Honesty rule** (mirrors Spec 14 §0.6's own convention): a `kardamow_take(...)`
caption on this section states explicitly that this measures how much people are
talking and how they feel, not whether they're right — attention/flow data, not a
trading signal. Never let chart titles or captions imply predictive power this data
doesn't have.

## Definition of Done
- Real ticker universe live-verified and finalised (documented in `pipelines/adanos/
  CLAUDE.md`, including any dropped/replaced symbols and why).
- A real weekly pull writes `ts_long` rows for all 4 platforms plus the sector
  trend, within the documented ~25-call/~108-call-per-month budget —
  `X-RateLimit-Remaining-Monthly` logged and sane after a real run.
- Three visuals live on page 10, each carrying the honesty-rule caption.
- Tests green, ruff/mypy clean, no secret in any committed cassette.

## Stretch
- Once/if a paid tier is purchased: add the `/mentions` raw-mention endpoints and
  cross-reference sentiment spikes against the existing GDELT/Guardian event log
  (Spec 09) for the same tickers' underlying commodity or producing country.
- Extend the OPEC/OPEC+ geographic-exposure set further (e.g. Kazakhstan, Angola,
  Algeria pure-plays) if genuine standalone listed candidates are identified later —
  same verify-before-adding discipline as this spec's own initial 5.
