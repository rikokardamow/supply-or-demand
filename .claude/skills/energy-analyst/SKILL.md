---
name: energy-analyst
description: Use when working with any oil, gas, LNG, power or refined-product data in this repo — converting units, labelling price series, computing or reading spreads and cracks, parsing OPEC/MOMR or macro releases, interpreting curve shape, storage, freight, AIS or vessel data, judging whether a price move has a supply or demand cause, or evaluating a forecast before it reaches a chart.
---

# Energy Analyst

## Overview

Domain reference for the petroleum, gas and power complex, distilled from a corpus of ~90
trading manuals, textbooks and journal articles. It exists because most errors in this repo's
energy work are **domain errors, not code errors**: a unit left unconverted, two price series
joined that were never comparable, a spread labelled as an arbitrage, a forecast scored against
nothing.

**How to use this file.** It is a reference, not a procedure. Jump to the section for the thing
you are touching. Two rules apply everywhere:

1. **Fix units and semantics at ingest, in the pipeline — never in the chart.** A chart that
   corrects for a unit is a chart that will be wrong the next time someone reuses the series.
2. **Where sources disagreed, the disagreement is recorded here rather than resolved.** If a
   section says "sources disagree", do not pick a side silently in code — state the convention
   you used in the docstring.

Repo golden rule 4 (**exclude 2020**) applies to every seasonal construct in this file.

---

## 1. Units and conversions

| Instrument | Native unit | Convert to $/bbl by |
|---|---|---|
| WTI (`CL`), Brent (`BZ`) | $/bbl | — |
| RBOB (`RB`), ULSD / heating oil (`HO`) | $/US gallon | × 42 |
| ICE low sulphur gasoil (`G`) | $/tonne | ÷ 7.45 |
| Naphtha (Asia) | $/tonne | ÷ 9 |
| Crude, generic mass→volume | $/tonne | ÷ ~7.33 (density-dependent) |
| Henry Hub (`NG`) | $/MMBtu | contract = 10,000 MMBtu |

- 1 barrel = 42 US gallons = 35 imperial gallons = 159 litres = 5.6146 ft³.
- Rule of thumb: **7 barrels ≈ 1 tonne** of crude.
- 1 toe ≈ 10 Mkcal ≈ 42 GJ ≈ 40 MMBtu ≈ 1.5 t hard coal ≈ 3 t lignite ≈ 12 MWh.
- 1 Mtoe = 3.968×10⁷ MMBtu = 860 Gcal. 1 GWh = 3,412 MMBtu = 238.8 Gcal. 1 TJ = 947.8 MMBtu.
- 1 EJ ≈ 948 trillion Btu ≈ 278 TWh.
- 1 t ethanol = 0.68 toe; 1 t biodiesel = 0.88 toe; 1 bbl ethanol = 0.58 boe; 1 bbl biodiesel = 0.86 boe.
- CO₂ intensity: gas 56.1, oil 73.3, coal 94.6 tCO₂/TJ — gas ≈30% below oil, ≈70% below coal.

**The tonne factors are product-specific and follow density.** Never apply one factor across
products, and never apply a crude factor to a product. Store the factor used alongside the
series instead of inlining a magic number.

**Sanity check:** converted products must land in a $50–200/bbl range. $2 means you skipped the
×42; $4,000 means you applied it twice.

---

## 2. The physical chain — title, custody, optionality

- **Bill of Lading** confers title to goods in transit. Whoever holds the endorsed B/L holds
  title, and it can be re-endorsed down a chain of buyers before final delivery.
- **FOB** — title passes at the loading port; buyer carries freight and insurance from there.
  **CIF/CFR** — seller carries cost, insurance and freight to the named destination.
  **DES** (delivered ex-ship) shifts even L/C timing to the receiving end.
- **US pipeline crude** trades "fip" (free in pipeline) at the wellhead or a hub — Cushing OK,
  Midland TX, St James LA — and is sold **rateable**: a flat x b/d over the month, so refiners
  run as received and hold less storage.
- **Waterborne crude** trades as discrete priced parcels, FOB at load port or CIF/out-turn at
  discharge. Rateable and parcel barrels are *not* the same kind of series — do not pool them.
- **Posted prices** — a refiner or gatherer posts a wellhead price for a grade, historically the
  market price less gathering and transport back to the wellhead. Koch's postings anchor the
  "postings-plus" (P-plus) market; the P-plus differential is benchmarked against the gap
  between Koch's posting and nearby NYMEX WTI.
- Posted prices matter historically too: the divergence between a *fixed* posted price used to
  compute producing-country tax and royalty take and a *falling* market price is the revenue
  mechanism that underlies OPEC's formation, and still echoes in today's OSP systems.

**Oil has no true instantaneous spot market.** Commercial-quantity oil trades forward to a
specified delivery location and time. Industry "spot price" means near-dated forward. Treat any
series labelled spot as a short-dated forward with a delivery point.

**Real-option framing** (source's own model, stated as fact in the text): pipelines and tankers
are options on locational spreads; storage is an option on time; a refinery is an option on the
crack. Infrastructure is built "just enough" rather than with slack — which is why the system
shows episodic extreme volatility rather than smooth adjustment.

Scale: world consumption ≈100 mb/d against >2 billion "paper barrels"/day in WTI + Brent
futures alone; all petroleum derivatives together trade ≈50× physical daily consumption.

---

## 3. Crude quality

- **API gravity** = (141.5 / SG@60°F) − 131.5. Inversely related to specific gravity.
- Light crude ≈ **≥37° API**; heavy crude ≈ **≤30° API**.
- **API alone is an unreliable yield predictor** across dissimilar crudes — it correlates well
  only within a crude "family". The **assay** is the reliable yield guide, and once made it
  stands as the reference for that grade for years.
- Sulphur ranges ~0.1–3.0% by weight; heavier fractions of the same crude carry more sulphur.
- **High-TAN** (total acid number) crudes trade at a discount because they corrode equipment —
  refineries built for them exploit that as a cheap feedstock advantage.
- **High-asphaltene** (heavy / tar-sand) crude discounts to ASCI/Brent/WTI; cokers and
  flexi-cokers are the units that process it.

---

## 4. Benchmarks and price reporting agencies

### Assessed prices are not observed prices

A PRA assessment is the output of a **methodology**. Two series with the same commodity name can
be built on incompatible principles.

- **Platts market-on-close (MOC)**, introduced 1992 — assessment standardised around a single
  30-minute window; the last visible price sets the assessment. Precise timestamp.
- **Argus and others** have favoured all-day volume-weighted averages. Covers a whole day.

Platts states the conflict explicitly: *"price is a function of time. An average is an artificial
mathematical construction that does not reflect actual market activity."*

**Consequences:** never average an MOC series with a VWA series; never splice one onto the other
to extend history; do not join them to intraday data as though they shared time semantics. A
mid-series methodology change is a **structural break** — flag it, don't smooth it.

**Fallback methodologies create silent regime changes.** Many assessments switch automatically to
a survey or panel when too few deals print, and the published series does not flag which mode
produced a given day. Treat holidays and disrupted markets as suspect for assessed series.

### Dated Brent is a composite, not a price

Assessed from four pillars: physical value of the **BFOET** basket; the forward curve from the
Dated swaps market; the fixed price of forward/futures Brent; and **quality premiums** for
non-Brent/Forties grades in the basket.

Physical Brent cargoes trade *as a differential to Dated Brent itself*. That circularity is
resolved by **CFDs** — weekly swaps converting Forward Brent into Dated Brent plus a
differential and back. CFDs trade 2–8 weeks forward and are what builds the Dated forward curve.

So Dated Brent is a **basket outcome whose grade composition has changed repeatedly**. Charting a
long history as one unbroken line misrepresents it; annotate composition changes.

### Other benchmarks

- **Dubai** — 500,000 bbl ±5% FOB Fateh; only ~12–15 physical cargoes/month but 5–10 paper
  trades per day. **Tapis** — 600,000 bbl ±5% FOB Kerteh.
- **OSPs** (Saudi, ADNOC) are historically set as a differential to Dubai. **Murban**'s futures
  contract instead sets its OSP off exchange settlement — becoming a benchmark rather than a
  benchmark-taker.
- **Cash WTI** is fixed-price or, more often, a differential to NYMEX WTI; most liquid in the
  Platts window between NYMEX close and the Access session open.
- PRAs publish differentials for Urals, West African, Mediterranean, North Sea and Asia-Pacific
  sweet grades against Forward Dated Brent, so refiners can compare relative crude value on one
  benchmark.
- Outright forward trades are **under one-third** of paper crude activity; most of it is grade
  and time spreads.

### What a benchmark actually is — and why it matters for the lake

Thousands of PRA prices are published daily; **only those used as a reference price in contracts
are benchmarks.** A handful are "super-benchmarks" whose influence reaches beyond their own
market: Brent, WTI, the London gold and silver fixes, and in finance LIBOR/EURIBOR.

Two reasons commodity markets lean on them so heavily:

1. **Deal heterogeneity.** Size, quality, delivery, timing and payment terms all vary. Rather than
   negotiate every price from scratch, participants link to a benchmark and negotiate only the
   *difference*. Energy markets made this shift in the 1970s; iron ore only from 2010.
2. **Volatility.** Traders cannot agree on where the flat price is going, so they agree on an index
   that captures the move and argue about the premium instead.

**The consequence that matters here: the flat price is outsourced, and the negotiated component is
the premium or discount.** A deal is struck as "Platts assessment ± 35¢", and at delivery the
assessment is looked up and the differential applied. Both sides are equally exposed to an index
neither controls.

So **the differential is where the market information lives, not the assessment.** A dashboard that
charts only flat prices is showing the part of the deal nobody negotiated. Where we hold
differentials, they deserve equal billing.

**The averaging window is contract-specific, and this is a real join hazard.** An Asian gasoline
cargo typically prices off ~**5 days** of Platts assessments; an Asian crude cargo off the average
of **all assessments in a specified month**. Two series both described as "Platts-linked" can rest
on entirely different windows — record the window, not just the PRA.

Chains deliberately stick to **one** benchmark end to end (refiner → trading house → importer →
distributor) precisely to avoid generating basis risk at each hop. If our pipeline mixes benchmarks
across a chain, we are manufacturing basis risk the market took care to avoid.

Which PRA becomes *the* benchmark is substantially **habit and first-mover advantage**, not
methodological superiority — usually whoever assessed the commodity first. Both sides must also
believe the PRA favours neither producers nor buyers. **IOSCO Principles** are the recognised
gold standard for PRA practice; whether a series comes from an IOSCO-compliant assessment is worth
recording.

### Checklist before joining any two assessed series

Same PRA? Same methodology family (MOC / VWA / survey / panel)? Same timestamp convention and
time zone? Same units and grade basket? Any methodology change inside the window?

Record the answers in the pipeline module's docstring, not a chart footnote where they get lost.
If the PRAs differ, part of the differential between two series is methodology, not market.

---

## 5. Curve structure and storage economics

- **Contango** — forward above prompt. Weak prompt demand, oversupply, storage filling. Storage
  economics turn positive and the carry can be locked in.
- **Backwardation** — prompt above forward. Tight prompt market; storage empties, buyers delay
  and sellers sell early.

Curve shape is a **state variable**, the cleanest single read on whether inventories are
comfortable or tight. Plot the M1–M2 spread alongside stocks, never in isolation.

### The asymmetry that matters

**Cash-and-carry caps contango but nothing caps backwardation.** Buy prompt, take delivery, pay
storage + insurance + interest, sell forward: this bounds contango at the cost of carry, *at
least until storage is full*. There is no equivalent ceiling on backwardation, because
commodities cannot be reliably short-sold by borrowing the way equities can. Any model that
treats the two tails symmetrically is wrong.

Worked example: buy March heating oil at 74.00¢/gal, six weeks' storage 2.30¢, interest and
losses 0.25¢ → breakeven 76.55¢ against an April sale at 77.00¢.

### The storage cost ladder

Contango has to widen progressively to pull in each costlier tier:

1. Pipeline-connected tank — cheapest, fills first.
2. Rail, then truck — each raising the contango needed to justify storing.
3. **Floating storage** — idle tankers, the storage of last resort once land tanks are full, and
   markedly more expensive because it must outbid the tanker's normal freight earnings.

Salt caverns are the cheapest form (used for the US SPR) but are poorly suited to frequent
commercial cycling; commercial operators use aboveground tanks at pipeline-connected hubs.

*Era-specific 2001 figures, for scale only:* floating storage ≈$0.30–0.50/bbl/month; lightering
≈$2.10/bbl over a 12-day operation; LOOP on-shipment $0.30–0.60/bbl over a ~$1.70/bbl base.

### Storage is an option, and its term structure runs backwards

Storage capacity is not a cost line — it is an **option on the calendar spread**, and it is priced
and traded as one. Practitioners buy the *right* to use a tank rather than the tank itself
("synthetic storage"), which makes a storage position economically equivalent to a strip of
inter-month spread options.

**Storage rates fall as commitment lengthens** — the opposite of most term structures. Providers
pay for certainty of utilisation. Illustrative shape: ~40¢/bbl/month for a 3-month commitment,
~35¢ for 6 months, ~30¢ for a year or more. Any model that assumes a flat per-month storage cost
across tenors will misprice the long end.

**A modelling caveat worth carrying.** A widely used commercial storage-option model valued storage
at 20¢/bbl against ~30¢ from a correct valuation. The cause was a **hard-coded cap of 400
iterations**; allowing ~4,000 iterations converged to the higher figure. An entire industry
underpriced storage optionality for years because of a silent convergence limit. **Check that any
iterative valuation in this repo has actually converged rather than hit a default iteration cap** —
report the iteration count alongside the value.

### Convenience yield

F = S·e^((r + u − y)(T−t)), where **u** = marginal storage cost rate and **y** = marginal
convenience yield — the benefit of holding physical barrels beyond storage-cost savings
(Kaldor, 1939). Storage economics set the floor under how deep backwardation can trade.

---

## 6. Spread taxonomy

Name spreads by type — mixing them in one series or one chart is a category error:

- **Time (calendar)** — same grade, different months. M1–M2, M1–M12. **Least volatile.**
- **Location** — same product, different place. Brent–WTI, gasoil–heating oil.
- **Quality / product** — different products. Cracks, fuel oil cuts. **Most volatile.**

Because time spreads are structurally the quietest, **a time spread moving as hard as a product
spread is itself the signal** — check for a data error first, then a genuine dislocation.

**Brent–WTI is mostly logistics, not quality.** WTI's landlocked Cushing delivery point
decouples it from waterborne markets and pushes it toward contango when US inventories build.
The spread is bounded by physical shipping-cost arbitrage *only when trade flows are
unconstrained* — the US crude export ban (lifted Dec 2015) decoupled the two benchmarks
entirely by blocking the arbitrage. Regulation and infrastructure, not economics, set the bound.

**What physical traders actually arbitrage:**
- **Location** — the "arb" between two hubs (ARA vs USGC). An *open* arb pulls cargoes toward the
  higher-priced region until flows narrow the gap; a *closed* arb halts flow.
- **Blending** — the core value-add: blending Basrah light + heavy to proxy Urals, or butane into
  surplus summer gasoline to make winter spec cheaply.
- **Quality/netback** — e.g. Indonesian LSWR valued by netback from Japanese burning-market spot.
- **Paper arbitrage** mimics this in futures without delivery, and works *only as long as the
  real physical arbitrage flows are uninterrupted* — only the physical trader holds an actual
  delivery hedge.

---

## 7. Refining

### Configuration ladder

| Configuration | Units | Conversion |
|---|---|---|
| Hydroskimming | CDU + hydrotreating + platforming, no residue conversion | none |
| Semi-complex | + thermal cracker (visbreaker) on long residue | ≤25%, poor distillate quality |
| FCC | vacuum gasoil feed (not whole residue — metals/asphaltenes poison catalyst) | ≤75% to gasoline-range, ~90–91 RON, needs downstream hydrotreating |
| Hydrocracking | adds hydrogen rather than rejecting carbon | ≈100% to distillates, near sulphur-free; 2–4% wt H₂ on feed |

- Atmospheric distillation caps near **370°C** (higher cracks the feed); heavier crude leaves
  more long residue. Vacuum distillation (30–40 mmHg, ~390–400°C) recovers vacuum gasoil, leaving
  short residue that concentrates asphaltenes and metals.
- Typical capacity: FCC 5,000–10,000 t/day; hydrocracker 2,000–6,000 t/day.
- **GRM** = product value − crude cost, measured *at the refinery fence*, with fuel
  self-consumption conventionally treated as a **yield loss, not a cost line**.
- Complex-refinery margins run persistently above hydroskimming margins, and the gap widens at
  times. Never compare a margin series across configurations without saying which.

### Reading the crack

**Never say "buy the crack" — name the legs.** Published papers and trading manuals use opposite
conventions for the same trade. Unambiguous only in terms of legs:

- A refiner is **naturally long the margin** (buys crude, sells products).
- The futures hedge that locks it in is **long crude, short products**.

A page labelled "refiner short the crack" will be read backwards by half its audience.

**Ratio.** 3-2-1 (3 crude : 2 gasoline : 1 distillate) is the default and roughly matches a US
refinery's yield; 5-3-2 is the common alternative. A fixed 3-2-1 is a **convention, not an
optimum** — optimal hedge proportions beat it, and the gap widens when the cross-dependence
between crude and product returns is itself moving (Liu, Vedenov & Power, 2017). Publish 3-2-1
because it is the market's shared reference; treat divergence between 3-2-1 and single-product
cracks as the signal about yield economics.

**Interpreting moves.** Short run, crude and product prices co-move strongly — symmetric to the
*sign* of shocks but asymmetric to their *size*: large shocks widen or narrow the spread, small
ones mostly pass through. Long run, co-movement approaches perfect and the Law of One Price binds
(Fousekis & Grigoriadis, 2017). So **cracks mean-revert**: a wide crack is information about
duration and cause, not a level to extrapolate. Pair it with utilisation and stocks — Spec 07's
margin-versus-utilisation scatter exists to separate those channels.

Distillate and gasoline cracks peak in different seasons. Build seasonal corridors **per
product**, never across blended cracks, and exclude 2020.

**Hedge-ratio modelling — don't.** GARCH and other time-varying hedge-ratio models deliver
variance reduction statistically and economically indistinguishable from the naive one-for-one
hedge, while generating substantially higher margin and transaction costs (Alexander, Prokopczuk
& Sumawong, 2013). Use the naive ratio absent a demonstrated, cost-inclusive reason.

---

## 8. OPEC and global supply

### Two production numbers, never one

The MOMR publishes OPEC+ crude production twice, and they disagree:

- **Table 5-7 — secondary sources.** Independent assessments (Argus, Platts, IEA, consultancies)
  averaged by the Secretariat. This is what quota compliance is measured against and what the
  market trades.
- **Table 5-8 — direct communication.** Self-reported by member countries.

Ingest both; never silently pick one. **The gap between them is itself a series worth plotting**
— it widens when reported compliance diverges from what outside observers can see, which is
exactly when the number matters.

### Track vintages, not levels

Demand and non-OPEC supply forecasts are revised monthly, and the market underweights the
**revision path**: three consecutive downward demand revisions say more than any single balance.
Spec 06 stamps `revision_date` with the publication month so vintages coexist and can be
differenced. **Never overwrite a prior vintage.**

### Spare capacity is a regime variable

Spare capacity is the buffer that removes the need for expensive precautionary inventories. Ample
→ inventories sit comfortably; thin → the market bids for prompt barrels.

Concretely, on EIA monthly data since 1995: once OPEC spare capacity fell **below ~1.8 mb/d for
longer than a quarter**, the Brent front-to-back spread traded in **contango on average over the
following two years** (Till, EDHEC, 2014).

Three caveats from the source itself:
- Definitions of spare capacity — especially "effective" spare capacity — differ by agency, and
  effective spare is concentrated in Saudi Arabia and disruption-prone. **Record which source a
  spare-capacity series came from; it is not comparable across providers.**
- The result is back-tested and predates the 2014 paper. Treat it as a hypothesis to re-test on
  our own lake, not a rule to hard-code.
- Transient month-to-month factors also drive curve shape. Spare capacity is the slow variable.

**Known counter-episode:** 2004–mid-2008, WTI and Brent traded in contango 68% / 65% of the time
*despite record spot prices*, breaking the historical high-price-equals-backwardation pattern.

### Stocks: use days of cover

The MOMR reports OECD commercial stocks in both million barrels and **days of forward cover**.
Absolute levels drift with structural demand growth; days of cover normalises for it and is the
comparable series through time. Chart days of cover as the headline, barrels as support.

---

## 9. Gas price formation

### The three mechanisms (IGU taxonomy)

**Oil price escalation** (oil indexation), **gas-to-gas competition** (hub indexation), and
**bilateral monopoly** (negotiated, government-to-government, mainly FSU/Middle East). Domestic
sales add netback-from-final-product and regulated pricing (cost-of-service, social/political,
below-cost, no-price).

- **European oil-indexed formula:** Pt = P0 + weighted pass-through of gasoil and heavy fuel oil
  price changes against a base period, with **80–90% pass-through**. Generally as
  Pn = P0 × (W₁·F₁/F₁,₀ + W₂·F₂/F₂,₀ + …) — base price adjusted by weighted **percentage
  changes**, not levels, in a basket of competing fuels.
- **Asian LNG formula:** linear indexation to crude with an **oil slope ≈14.85%** (the
  Pertamina–Japan benchmark), historically 10–17%, with **S-curves** softening pricing at price
  extremes.

### Why oil indexation existed, and why it broke

Gas markets were immature, illiquid and manipulable while oil was global and liquid; gas and oil
were substitutes in heating and industry. Transaction Cost Economics (Williamson) explains the
long-term contract as governance for idiosyncratic, sunk, uncertain investment — **pipelines are
immobile and fully asset-specific; LNG is reroutable**. Long-term contracts and oil indexation
formed an inseparable package allocating **price risk to exporters and volume risk to importers**.

It broke on falling asset specificity (amortised infrastructure, cheaper modular LNG), growth in
flexible LNG, liberalisation (US → UK → Europe → Japan/China), and the **2008–09 oversupply
shock**, where mid-streamers held oil-indexed take-or-pay gas they could not resell at collapsed
hub prices — triggering renegotiation and arbitration against Gazprom, Sonatrach and Qatar.

Quantified shift 2005→2018 (IGU Wholesale Pricing Survey, global consumption): hub indexation
**+16pp**, oil indexation −5pp, bilateral monopoly −2.5pp, regulated cost-of-service +9pp,
social/political +3pp, regulated-below-cost **−~20pp**.

2018 regional shares: Europe ~75% hub / ~25% oil-indexed (Iberia, SE/NE Europe); North America
100% hub since inception; Asia oil indexation **rising** as it replaces regulated pricing in
China, Indonesia and Malaysia; Middle East ~76% regulated social/political; Latin America hub
indexation 4%→17%.

**By trade type, hub indexation dominates piped gas and oil indexation dominates LNG** — because
~three-quarters of LNG goes to Asia. That is not a contradiction with LNG's flexibility:
destination flexibility and pricing mechanism are separate dimensions. Hybrid formulae are common,
combining both via pricing corridors that switch mechanism by price level.

Gas prices remain structurally **regional and fragmented** — infrastructure bottlenecks,
location-specific regulation, and increasingly politicisation (LNG tariffs). Flexible LNG is the
main convergence force, via arbitrage.

Worth noting: Hafner and Luciani argue it would now make more economic sense to index gas to
**coal** than to oil, since gas and coal still compete directly in power generation while gas and
oil largely no longer compete. The historical justification for oil indexation has weakened.

### Contract machinery

- **Take-or-pay:** buyer pays for a Minimum Contracted Quantity even if not lifted, typically
  **75–85% of the Annual Contracted Quantity**, with make-up rights below ACQ and optional
  upward flexibility above. Originated in the Dutch gas industry in the 1960s.
- **Review clauses** (originally ~every 3 years) allow renegotiation if the formula becomes
  unprofitable for either side.
- **90% of 2019-vintage long-term LNG SPAs had no destination restriction** — destination
  flexibility is now standard.

### Hubs

Henry Hub (NYMEX-listed 1989, after the 1978 NGPA and 1989 Wellhead Decontrol Act), NBP (UK),
TTF (Netherlands), and **JKM — a Platts-calculated proxy, not a true hub.** HH and NBP/TTF are
genuine gas-on-gas markets, with oil–gas decoupling confirmed by the absence of spot spillovers.

**JCC** ("Japan Crude Cocktail") is the Japan Customs Cleared price: a monthly government-compiled
average of >200 crude and semi-finished oil import types across ~30 countries, total import
revenue ÷ total volume. Highly manipulation-resistant. LNG formulae use **lagged averaging of
several preceding months' JCC**, which delays and smooths oil pass-through. Indonesian LNG indexes
to ICP instead. JKM is increasingly proposed as the Asian replacement and is empirically more
efficient (better risk-sharing and hedging) than oil-indexed long-term pricing under low risk
aversion — and whether it is priced CIF or FOB barely matters.

---

## 10. LNG chain, cost stack and arbitrage

### Physical chain

Production/gathering → liquefaction → shipping → regasification, historically linked by 20+ year
take-or-pay contracts (the "floating pipeline" model).

- Liquefaction cools gas to **−163°C / −260°F** at atmospheric pressure, cutting volume **~600×**.
  Gas is pretreated to strip CO₂, sulphur, mercury, water and heavier hydrocarbons first.
- **Trains:** ~1 MMt/y (1.4 Bcm/y — early Libya/Algeria/Alaska/Brunei) → ~8 MMt/y (11+ Bcm/y,
  Qatar). 1990s trains capped near 2.5 Mtpa by compressor limits; 2014–18 builds mostly 4.5–5 Mtpa.
- **Ships:** 154,500 m³ standard; 209,000–266,000 m³ Q-flex/Q-max built for Qatari trade. Average
  carrier grew from <125,000 m³ (1980s) to 151,000 m³ (2007). Ship life 40+ years; **no LNG cargo
  has ever been lost or spilled.**
- **Boil-off:** ≤**0.15%/day** of cargo on modern ships, normally burned as ship fuel.
- **Heel:** a small volume retained on the ballast return voyage to keep tanks cold — colder tanks
  mean less boil-off on reload; warm tanks need a slow cooldown.
- **Storage tanks:** 50,000 → 200,000 m³ at liquefaction/regas sites; terminals range 35,000 to
  2,000,000+ m³.

### Cost stack ($/MMBtu)

| Component | Cost |
|---|---|
| **Total chain, wellhead → terminal** | **$2.00–3.50** |
| Liquefaction | largest single component |
| Shipping, short-haul (Algeria–Europe, Sakhalin–Japan) | $0.25–0.30 |
| Shipping, long-haul (Middle East–US, Qatar–USGC) | $1.50–1.60 |
| Regas terminal incl. capital recovery | $0.35–1.00 |
| Pipeline tie-in | $0.05–0.10 |

- Vaporizer fuel ≈**1.5–1.75% of terminal throughput** — the single largest US terminal opex item,
  because US terminals use gas-fired vaporizers while the Far East uses open-rack seawater.
- Terminal capex ≥**$500M** for 200–300k m³ storage (excluding land and pipeline); O&M, insurance
  and security ~3–4% of capex/yr.
- Ship opex ~$2M/yr maintenance + ~$2M/yr insurance per vessel on owner's account; bunkers, port
  charges, canal tolls and boil-off are the charterer's.
- Spot charter day rates $25,000–$125,000+/day normally; **$120,000–450,000/day** in the extreme
  2022 West-of-Suez crisis. Up to 20 ships have been idled awaiting cargoes.
- Q-flex/Q-max cut the long-haul rate by ~20%.

### A spread is not an arbitrage

Arbitrage means a cargo **contractually committed to a different market** is diverted. That
implies more than two parties — seller, initial buyer, end buyer, often an intermediary — and the
margin is **shared, not captured**, split by negotiation. The diverted cargo usually has to be
**replaced** from spot or the local gas market, and that replacement cost is part of the economics.

The viability condition is not "Asia above Europe". It is the end-buyer price exceeding **both**
the spot price **and** the local gas market price of the replacement, by enough to cover
transaction costs (shipping + quality correction + regas/reloading).

| Model | Initiator | Key constraint |
|---|---|---|
| Seller-arbitrageur | Seller offers the initial buyer a share to forfeit | **Initial buyer has a destination veto** |
| Buyer-arbitrageur | Initial buyer diverts and replaces the cargo itself | Blocked by a destination clause in the SPA |
| Trader-arbitrageur | Independent trader buys the cargo or the diversion right | Entirely bilateral |

*Worked case:* Oman diverted a Spain-committed cargo to Asia in March 2008, offering to share the
profit with the Spanish buyers.

The recurring barriers are **contractual, not economic**: destination clauses, veto rights,
replacement obligations. The single most cited barrier is simply "price differential not great
enough", followed by cargo availability — a tight market kills arbitrage even with wide spreads.
A **divertible cargo** is one not bound by a destination clause and not on DES terms; FOB cargoes
are inherently more divertible because the buyer controls shipping and title passes at loading.
Historically SPAs had <10% off-take flexibility and no destination flexibility; plants running up
to 40% above nameplate offered the spare volumes to existing buyers under right-of-first-refusal.

Price differentials have persistently existed **without** producing convergence between basins —
arbitrage volume has been too constrained to close them.

**Rule for the dashboard: never label a spread chart "arbitrage".** Label it a spread, and treat
any inference about diversions as a hypothesis needing corroborating cargo evidence.

### Freight rate seasonality

- Seasonality is **deterministic, not stochastic** — so it belongs in a seasonal corridor, not a
  stochastic model term.
- Spot rates rise in **June, October and November**. October ≈**+35%** spot vs +1.06% on 1yr TC
  and +0.36% on 3yr TC; June ≈+21.5% spot; November ≈+22.45% spot.
- Monthly return range: spot −17% to +35%; 1yr TC −1% to +1%; 3yr TC narrower still.
- **Amplitude is larger in contractions than expansions** — the October spot increase reaches
  **142%** in a contraction phase against the ~35% all-regime average. This is the opposite of the
  tanker-market literature. A single all-history corridor understates weak markets and overstates
  strong ones; split by regime if the chart is load-bearing.
- Spot vs 1yr TC Spearman 73%; spot vs 3yr TC 63%. Longer duration, lower volatility. In 2015
  ~70% of carriers were on period contracts, ~30% spot.
- Patterns are broadly similar across routes — that similarity is a finding, not a bug.

**Freight is derived demand.** It follows gas market economics and trade flows, not the reverse.
Do not read a freight move as a primary signal about gas. In the freight/price system,
**short-term connectedness dominates** and the multi-month term rate is the key transmission node
onward to gas futures. Geopolitical-risk → freight spillover is short-term and small; importer-country
GPR transmits most short-term shocks, exporter-country GPR most medium-term. Since EU-ETS Phase 4,
**carbon price has become a net transmitter of shocks to LNG freight rates.**

---

## 11. US gas market structure and storage

- **Henry Hub** (southern Louisiana) interconnects 13 intra- and interstate pipelines — that
  interconnectedness is why NYMEX chose it. Contract = 10,000 MMBtu. Chicago Citygate, Dawn,
  AECO, SoCal, PG&E Citygate/Malin, Waha, Transco zones and Dominion South trade comparable or
  greater volume than HH itself.
- **A liquid spot market forms where the pipeline interconnections are** — more buyers and
  sellers. That is the structural reason HH became the benchmark, not anything about Louisiana gas.
- **Basis swap** pays NYMEX HH ± a fixed differential to settle at another index point. Basis is a
  direct readout of **regional pipeline capacity and takeaway constraints**: Marcellus growth
  required new Northeast pipe while displacing utilisation on long-haul lines from the Gulf Coast
  and Canada.
- **Spot market** = delivery ≤30 days, traded daily. **Bid week** = the last 5 business days of the
  month, when monthly physical deals and pipeline nominations are arranged.

**Storage.** Inject in warm/low-demand periods, withdraw at peak. LDCs inject and withdraw for
reliability obligations **independent of price signals**, unlike merchant and producer storage
which responds to spreads — so do not read aggregate storage as a pure price-response series.
Low storage entering autumn → the market pays up for winter (bullish); unexpectedly high storage
or warm weather → bearish.

**Deliverability (rate) is a separate constraint from capacity (working gas volume).** Seasonal
storage smooths gradual, predictable winter withdrawal; peak-load storage serves sudden surges
and needs fast deliverability. *Corpus gap: no cushion-gas/working-gas ratios or deliverability
curves were found — source these from AGSI+/ALSI+ or operator documentation.*

Gas is more storable than power — pressure variation in the pipeline network itself buffers daily
swings — which is why gas has no intraday peak/off-peak structure the way power does. UK daily
peak demand ≈1.5× average and ≈4× minimum.

---

## 12. Power, spark and dark spreads

- **Spark spread** = P_electricity − (P_gas × heat rate), in $/MWh.
- **Heat rate** K_H = Btu of fuel consumed per kWh generated — a physical efficiency measure.

| Unit | Heat rate (Btu/kWh) |
|---|---|
| Efficient | 7,500 |
| Average | 10,000 |
| Inefficient | 15,000 |

Spread > 0 → economical to run (buy gas, sell power). Spread < 0 → cheaper to buy power off the
grid than generate. It must also cover O&M, capital and financing; a persistently small spread
defers generation. The basic formula assumes the turbine is co-located with switchyard and
pipeline at zero transport cost — **real locational and transport costs are basis risk layered on
top.**

- **Spark-spread option:** European call payoff max(S_E,T − K_H·S_G,T, 0). Pricing needs stochastic
  models for both power and gas *plus their correlation*, typically mean-reverting with seasonal
  trend. A **strip of spark-spread options approximates the real-option value of owning the plant**
  and exceeds simple DCF, because it captures the option to shut down when spreads are unfavourable.
- **Dark spread** = P_electricity − P_coal (the coal analogue). "Dirty" excludes carbon.
- **Clean dark spread** = dirty dark spread − (carbon price × coal CO₂ emissions factor).

### Why power is not like oil

- **Non-storability.** Value is tied to real-time balance. Prices show large skew against
  lognormal and can jump $50 → $1,000 → $50/MWh within days. Black-Scholes-style random walks do
  not fit.
- Normal marginal cost < $100/MWh, but **scarcity prices run $1,000–$10,000/MWh**; every
  deregulated market (Australia, Chile, NZ, Canada, US) has seen spikes above $1,000.
- **Locational.** Transmission constraints make value time- and place-specific — there is
  virtually no flow between the US Eastern and Western interconnects. Crude, being transportable,
  is globally correlated instead.
- **Regional behaviour is not transferable.** Midwest 1998 spikes were short-lived (outages plus
  heat); Western US hydro-dependent markets instead show sustained high plateaus in dry years
  until reservoirs refill. A model calibrated on one region does not apply to another.
- Unlike mature commodity markets where financial volume runs ~10× physically delivered volume,
  **the vast majority of power trades still settle physically.**

Price model ladder, increasing realism: random-walk jump-diffusion (Merton 1976 — ignores mean
reversion) → Ornstein-Uhlenbeck/Vasicek dS = κ(θ − S)dt + σdW, κ the mean-reversion speed and θ
the equilibrium set by production cost and demand → Schwartz Type-1 (mean reversion in log price)
→ mean reversion with jumps, capturing normal peaks and abnormal spikes plus seasonality together.

---

## 13. Risk: basis, volumetric, credit

### Basis

**Basis = futures price − spot (physical) price.** Basis risk is the risk that a hedge and the
exposure do not move in offsetting directions. As futures approach maturity basis tends to zero —
that convergence is what makes futures hedges work, and its failure is the hedging failure mode.

**Decomposition for a storable commodity:** basis = **time** (storage cost) + **space**
(transportation cost) + **form** (quality cost) + **uncertainty of physical supply** (convenience
yield). When a basis moves, ask which of the four changed.

- Short hedger (producer) bears the risk basis **rises**; long hedger (processor) bears the risk it
  **falls**. Net price to the short hedger = futures selling price − actual basis.
- **Cash/futures basis converges** by termination via arbitrage. **Location basis does not.** Two
  different animals; do not model them the same way.
- **US gas trading is basis trading**: regional prices are quoted as a differential off Henry Hub,
  and CME/ICE basis futures pay (Inside FERC monthly index at location) − (HH futures settlement).
- **Jet fuel has no futures market** — hedgers proxy with gasoil or crude, creating explicit
  jet/gasoil and jet/crude basis. Airline hedge-ratio ladder: ≤75% (yr 1), ≤50% (yr 2), ≤35%
  (yr 3), ≤25% (yr 4+) of forecast consumption; a "large" hedging desk starts around 500,000 t/yr.
- **Weather/HDD** derivatives are a proxy for uncertain consumption, so a residual always remains —
  this happens *every time* an exposure is hedged with a derivative on a different underlying.

*Worked case:* a generator sells COB futures at $18/MWh expecting to sell Denver spot in six
months. At delivery Denver spot = $25 and COB = $28. It sells physical at $25 and loses $10 on
the futures leg → **$15/MWh net, against $18 expected.** The fix is a locational basis swap.

### Volumetric risk

Utilities face unexpected changes in **volume**, not just price: wholesale contracts are
fixed-volume but retail customers hold an unlimited call at a fixed price. A utility that buys
only expected load covers shortfalls at spot — and everyone is buying at once, pushing price
further up. **Price risk and volumetric risk are highly correlated in power.**

An unscheduled **500 MW outage in a 10,000 MW market** can move power prices more than the Gulf
War's loss of Kuwaiti and Iraqi oil production moved oil prices.

**Standard VaR excludes volumetric risk** — it assumes fixed volumes and models only price. Total
utility risk is understated unless volumetric risk is modelled separately.

### The general taxonomy

Five classes: **credit, liquidity, market, operational, political.** Operational (Basel II: loss
from failed internal processes, people, systems or external events) decomposes into fuel prices,
geopolitical risk, acts of God, basis, delivery, generation, storage, capacity, correlation,
consumption, safety, compliance, vendor and reputation risk.

---

## 14. Volatility structure

- **Samuelson effect** — implied and futures volatility decline with time to maturity, across oil
  (WTI), metals (LME) and gas. Cause: short-term "viscosity" of supply and demand — shocks hit the
  front of the curve hard, longer maturities adjust slowly. Spot volatility is very high near-term
  and stabilises at an equilibrium level further out.
- **Gas is distinctive:** it shows the Samuelson decline **plus superimposed annual winter peaks in
  implied vol** — a seasonal component absent from oil and equity vol surfaces.
- **Gas and commodity options show positive skew (an "inverse leverage effect")**: OTM calls trade
  at higher implied vol than ATM — the **opposite** of equities, where OTM puts are bid up. Rising
  commodity prices themselves raise volatility and economic concern; falling equity prices raise
  fear. Never port an equity vol-surface intuition onto gas.
- Standard stylised facts hold: volatility clustering, leptokurtosis, heteroscedasticity — hence
  GARCH-family models.
- Energy commodities carry higher volatility than other commodities (e.g. gold) and **the highest
  volatility of any commodity class during recessions.**
- Gas is a consumption good with **strong** demand seasonality; crude has **very weak** seasonality
  in both demand and supply. That difference is why they need different term-structure models. The
  most liquid European gas option is a **seasonal option** — a strip of six monthly options.

---

## 15. Empirical price dynamics

### Why oil is structurally prone to boom and bust

**The single most useful frame for reading any oil price chart.** Extreme volatility is an
*intrinsic* feature of oil, not an anomaly to be explained away. Both supply and demand are
"sticky" — they do not adjust quickly to price — so even a small imbalance requires a large price
move to clear the market.

| Elasticity | Short run | Long run |
|---|---|---|
| Crude oil demand | **−0.06** | −0.2 to −0.3 |
| Crude oil supply | **0.04** | 0.35 |
| Income (GDP) elasticity of oil demand | ≈**1.0** (0.55 advanced, ~1.1 fast-growing) | |

For contrast, restaurant meals price-elasticity ≈ −2.3 and fresh tomatoes ≈ −4.6. **A 5% supply
loss requires a ~85% crude price rise to clear, against ~1% for tomatoes.** That single comparison
explains most of what looks inexplicable on an oil chart.

*Note the scope difference:* these are **crude** elasticities. The refined-product elasticities in
§16 (gasoline −0.293 short-run) are larger because they are measured at the pump, where taxes and
margins damp the pass-through. Do not mix the two sets.

**Why supply is sticky.** The industry is capital-intensive with low variable costs, and its
equipment is single-purpose — a rig, a pipeline, a tanker is good for nothing but oil. Once capital
is sunk, producers produce as long as price covers variable cost, and **operating costs for major
sources run $5–30/bbl**. Midstream and refining have the same incentive to run flat out. Supply
does respond, but with a **multi-year lag** — so today's cancelled projects become tomorrow's
shortage. *Price crashes today sow the seeds of price booms later.* This is the self-reinforcing
mechanism, not a coincidence of cycles.

**Why demand is sticky.** No short-run substitute for gasoline and diesel; transport is ~55% of
world consumption. Fuel cost is small against the up-front cost of the vehicle. US demand has grown
*stickier* between 1980 and 2007 as oil concentrated into transport and fell as a share of consumer
spending. Where taxes and subsidies buffer pass-through, inelasticity is more pronounced still.
**Rising prices do not kill oil demand — recessions do.**

### Stability is a regime, and regimes have a controller

Historically, oil has alternated between multi-decade eras of relative stability and wild boom-bust.
**Stability has always depended on someone regulating supply** — through mandatory production
quotas, a cartel, or both:

| Era | Controller | Character |
|---|---|---|
| 1859–1879 | none | boom-bust |
| 1880–1911 | Standard Oil refining monopoly + rail/pipeline integration | stable |
| 1911–1931 | none (post-dissolution) | boom-bust |
| 1932–1972 | US state prorationing (Texas Railroad Commission) + international cartel | **most stable era** |
| 1973–~2008 | OPEC | managed |
| ~2008– | none | boom-bust returned |

Since 2008, monthly crude price changes have averaged roughly **33–38%** — on par with the
1911–1931 boom-bust era. The argument is that we exited seven decades of public-private production
control and re-entered a market-driven regime.

**With no supply regulator, price oscillates between a floor set by the cost of production and a
ceiling set by economic pain** — historically a range from well below $30 to above $100. Periods of
calm (2010–2013) are the anomaly within a boom-bust era, not evidence the era ended.

**Dashboard consequences:**
- **Do not treat a volatile stretch as a data problem or a regime break to be smoothed.** Volatility
  is the base case; stability is what needs explaining.
- Any long-history seasonal or volatility corridor spans multiple *control regimes*. Fitting one
  corridor across 1970–today mixes OPEC-managed and market-driven eras. Split by regime, the same
  way §10 splits LNG freight corridors by market phase.
- Cartels are "children of distress" — they form during ruinous price competition and need few
  producers, high entry barriers and a disposition to collective action. Where those conditions are
  absent, expect cheating and failure, which is the historical record of most producer cartels.

### Shock decomposition — the single most important frame

Kilian-style three-way identification: **oil supply**, **global aggregate demand**, and
**oil-specific (precautionary) demand**. Short-run oil supply elasticity is empirically ≈zero even
under agnostic identification.

| Sample | Supply share of *price* variance |
|---|---|
| Pre-2007, medium run | **~0.02%** (while explaining >80% of *production* variance) |
| Full sample 1973–2021 | ~5% |
| 2008–2021 | >20% initially, ~10% medium-term |

**Supply explains production, demand explains price.** Post-crisis, supply's share roughly
quadrupled — but it is still the minority driver.

Impulse responses: a supply shock cuts production ~1.5% on impact and is still −0.5% at 20 months,
with a small, short-lived price effect (max ~+1%) pre-2007, becoming more persistent and briefly
dominant in the short run post-2008. An aggregate demand shock shows a delayed (~5 month)
production response and a persistent price rise to ~+5% by month 20 pre-crisis, plateauing lower
post-crisis. An oil-specific demand shock has no production effect and an impact price response
**>7%**, decaying faster.

**Historical episodes — only 2 of 6 show supply as a significant price driver:**

| Episode | Attribution |
|---|---|
| Iranian Revolution 1979–80 (price ×2) | ~70% oil-specific demand |
| Gulf War 1990 (price ×2) | 85% oil-specific demand, 15% supply |
| 2007–08 surge (price ×2) | 75% oil-specific / 25% aggregate demand; supply insignificant |
| 2008 crash | 80/20 oil-specific / aggregate demand |
| COVID crash Jan–Apr 2020 (price to ¼) | 80% oil-specific, 20% aggregate demand; supply negligible |
| COVID rebound Nov 2020–Oct 2021 (price ×2) | mainly oil-specific demand |

**Dashboard rule: never narrate a price move as "supply-driven" without the decomposition.** The
prior is overwhelmingly demand.

*Acknowledged tension:* zero short-run supply elasticity is robust across specifications but
contradicts micro/shale-well studies (Bjørnland et al.; Aastveit et al.) finding non-zero
elasticity. Unresolved in the literature — do not present either as settled.

### Transmission to macro and markets

- **Inflation.** Oil "jump tail risk" (the discontinuous intraday RV component) raises US headline
  and core CPI; headline rises ~5bp to a 1-s.d. sign-jump shock, significant 1–3 months. Materially
  stronger since COVID. Plain WTI returns in a Phillips curve show a significant *negative* effect
  on headline only at h=12 (base effects) and none on core — no second-round pass-through detected.
  **Caveat: tail-risk measures give no out-of-sample improvement over an AR benchmark in normal
  times** — they only help inflation-at-risk forecasts during crises. Authors also flag conflicting
  literature (Wong 2015; Kilian & Zhou 2022) finding pass-through has become limited and short-run.
- **Equities.** A fall in this month's oil price predicts higher stock returns next month across
  developed markets — economically large (Driesprong et al.). 1986: WTI −25.5% while S&P +13.2%
  over T-bills. Oil declines act like a tax cut. In a GVAR (1979Q2–2023Q3), a 1% oil *risk* shock
  gives the largest negative equity impact of any shock type (−12.1% short-term, "rest of world");
  a 1% supply shock only −0.3%, Asia only. Geopolitical *acts* hit harder than *threats* (−0.6% vs
  −0.02% Euro/UK). **US equities are most resilient; Asia and "rest of world" most exposed.**
- **EM sovereign spreads.** Oil-specific demand shocks compress spreads significantly (coefficient
  ≈ −2.0 to −2.6, p<0.01), aggregate demand weaker (≈ −1.3 to −1.6, p<0.10), **supply shocks
  insignificant**. Confirms "not all oil shocks are alike" outside the oil market itself.

### Tail behaviour and contagion

- Energy commodities and precious metals show **larger average downside tail risk than equities**.
- Downside tail-risk spillovers are driven mainly by external ("from others") contributions and are
  **most pronounced when tail risk is at its lowest** — contagion susceptibility is not confined to
  turmoil.
- Equities are the primary transmitter across all quantiles. **WTI is a net receiver in the lower
  quantile but a transmitter in the middle quantile** — its role flips by quantile.
- **Asymmetry:** tail-risk spreads widen during *financial* crises but **not** during pandemics or
  geopolitical events. Do not make a blanket "crisis raises contagion" claim.
- Tail risk of crude and precious metals *falls* during crises (2008, 2015) — **but not during
  COVID-19**, an explicit exception. Extreme systemic risk (tail-β) declines in crises, supporting
  diversification value exactly when equity risk peaks.

### FX and the non-dollar consumer

China's FX-adjusted oil price spread shows **strong long-term memory (Hurst ≈0.95–0.96)** across
Russia/Dubai/Oman/WTI/Brent import channels — spread shocks are persistent, not mean-reverting.
Memory cycle: WTI ~120 days, Brent ~100, Russia/Dubai/Oman ~90 — the globally-referenced benchmarks
have longer, more stable memory. Time-varying Hurst gives early warning of reversals 10–20 days
ahead, and 30–70 days for sharp reversals in WTI/Brent. An "Asian premium" was pronounced Oct 2014
– May 2015 and weakened afterwards.

### Retail and downstream

~35% of US gasoline stations are **"cyclers"** (Edgeworth cycles: sharp jump, slow decline),
roughly biweekly. **Cyclers charge ~3.5¢/gal *lower* on average** than non-cyclers in the same
brand, city and ZIP — asymmetric cycling is a discount strategy, not gouging. Regional dispersion
is wide: Midwest ~62% cyclers vs 17–30% in West/South/Northeast, and cycling status is spatially
clustered with nearest neighbours.

---

## 16. Demand structure and elasticities

**Oil demand is S-shaped/kinked** — highly inelastic across a wide "normal" price range (capital
stock is fixed; only capacity utilisation adjusts), turning elastic at very high prices
(substitutes appear) and very low prices (oil displaces other fuels). Transport demand is
structurally **captive**, which is what OPEC production strategy relies on.

| Fuel | Short-run | Long-run |
|---|---|---|
| Heating oil | −0.017 | −0.185 |
| Electricity | −0.126 | −0.365 |
| Diesel | −0.153 | −0.443 |
| Natural gas | −0.180 | −0.684 |
| Gasoline | −0.293 | −0.773 |

*(Labandeira et al. 2017 meta-analysis.)* **Long-run ≈3× short-run**, because capital stock
adjusts. These are **product** elasticities measured at the pump; the **crude** elasticities in §15
(demand −0.06, supply 0.04 short-run) are far smaller because taxes and refining margins damp the
pass-through to consumers. Use the crude figures when reasoning about the crude balance and these
when reasoning about end-use demand — never interchange them. Low short-run elasticity is why price shocks pass so fully into GDP:
%ΔGDP = −%ΔPrice × (1 − elasticity) × (net imports / GDP).

- OECD was >70% of global oil demand in 1965 and the US alone ~20% by 2018; China's share of world
  demand rose 33%→42% between 2000 and 2009.
- Gas end-use (2016, global): power generation ~29% (OECD 30%, non-OECD Asia 33%, **Japan 73%**);
  industry ~18%; residential/commercial ~20%; remainder petrochemicals, fertiliser and losses.
- EV transition (Cherif et al. 2017): fast adoption → OECD oil demand −21 mb/d and non-OECD
  −7 mb/d by 2040; slow adoption → OECD −5, non-OECD +4 (net −1 mb/d).
- Coal/oil→gas switching in power was the major 1990s trend, enabled by deregulation plus
  combined-cycle efficiency. US coal→gas switching cut NOx >40% and SO₂ 44% by 2012 vs 1997.
- Capital-intensive energy assets have a high sunk-cost share, so marginal-cost pricing causes
  losses and firms run flat out treating fixed cost as sunk — **a structural tendency to oversupply.**

---

## 17. Macro indicator releases

Macro series are estimates that get rewritten. Spec 10 pulls from FRED, which serves the **current
vintage** — so a chart built today shows numbers that were never on screen when the market traded.

**The revision cascade.** US GDP publishes as an advance estimate then revises in successive
months, releasing at **8:30 a.m. ET**. Beyond the monthly sequence: **annual revisions each July**
revise the previous **three years (twelve quarters)**; **benchmark revisions roughly every five
years** can change definitions and methodology, not just values. Industrial production, capacity
utilisation, factory orders, employment and sentiment indices each carry their own schedules, and
index components are revised too, forcing commensurate index revisions.

**Rules:**
- Stamp every macro row's `revision_date`. A macro series without a vintage cannot be audited.
- **Never explain a historical market move with the current vintage.** If oil sold off on a
  payrolls print, the relevant number is the first print, not today's twice-revised value.
- A series that "changed history" between two pipeline runs is usually a revision, not a bug.
- **Lower revision magnitude = more tradeable.** Prefer a stable indicator over a comprehensive
  one that gets rewritten, for anything a chart conclusion rests on.

**Classify before charting** — the class determines what the series can argue:

- **Leading** — sentiment surveys (ESI), new orders, rig counts against later production.
- **Coincident** — industrial production, real activity.
- **Lagging** — **the labour market.** Employment turns *after* the cycle, so a strong labour print
  is not evidence that a demand-driven energy move is sustainable.

A lagging indicator on the same axis as a price invites a wrong causal read. Where the chart
implies causation, put the lead/lag in the annotation.

Cross-reference the release calendar in `specs/CLAUDE.md`; schedule pulls after release allowing
for publication lag (often two to six weeks after the reference month), so a "missing" latest
month is usually the calendar, not a failure.

---

## 18. Forecast evaluation

Energy price forecasting has an enormous published literature and a poor out-of-sample record. The
failure mode is not bad modelling — it is **good in-sample fit presented as predictive power.**

**1. Beat a named benchmark, not nothing.** For a return forecast the benchmark is the historical
mean or a random walk. Report **Campbell–Thompson out-of-sample R²** against it. Of 23 competing
predictors of crude oil returns, **19 failed to beat the benchmark** at monthly horizon. Assume
yours is in the 19 until shown otherwise.

**2. Out-of-sample or it did not happen.** Excellent in-sample fit does not survive translation
(Welch & Goyal, 2008). Use a **recursive (expanding) window**: estimate to *t*, forecast *t+1*,
roll. Any parameter, feature or hyperparameter selected on the full sample has leaked the future.

**3. Test the difference, don't eyeball it.** Two RMSEs are not distinguishable until tested. Use
**Diebold–Mariano** on the loss differential.

**4. Check stability, not just the average.** Plot the cumulative loss differential over time. A
model that earned its edge in one regime and none since is a historical observation, not a forecast.
VIX is a documented example of in-sample strength that is unstable out-of-sample.

**Metric traps.**
- **MAPE on price levels flatters everything.** Oil is near-random-walk, so a persistent forecast
  scores a low MAPE carrying no information. Published crude MAPEs of 2–3% are unremarkable.
  Evaluate on **returns or direction**, against the random walk on the same sample.
- **Volatility and VaR need their own backtests** — report **unconditional coverage (Kupiec)** and
  conditional coverage. The question is whether violations occur at the stated rate and
  independently, not whether the band looks reasonable.

**Presenting on a page.** Show the benchmark's forecast on the same chart — a forecast without its
benchmark is a claim without evidence. Show intervals, not just a path. State the evaluation window
and metric in the caption. Exclude 2020 from any seasonal component.

**Chronos.** The default forecasting library here. Being pretrained changes nothing about the bar
above: zero-shot forecasts still need the random-walk comparison, the recursive window and the DM
test. Its pretraining corpus is an **unknown-overlap risk** with public energy series — treat any
evaluation period that could plausibly sit inside pretraining as in-sample.

---

## 19. Spot–futures relationships

Integrated grey correlation (1990s–2023): **natural gas 0.93 (lowest) < gasoline 0.94 < heating oil
0.97 < crude oil 0.98 (highest)**. Gas offers the best diversification of the group; crude the least.

- **Natural gas** shows stable, similar-magnitude **bidirectional** causality throughout. Its
  spot–futures correlation spiked to ~0.74 around the 2003 Iraq invasion and the March 2022
  Russia–Ukraine shock, and troughed near 0.01–0.02 in mid-2003 — low correlation does not mean
  immunity to international shocks.
- **Crude and heating oil:** futures→spot causality dominates; highest, most stable correlations.
- **Gasoline:** far more volatile causality over time, predominantly unidirectional.
- **Across all four, the spot–futures linkage weakens during crises** (COVID, GFC, Russia–Ukraine,
  Arab Spring, dot-com) — a breakdown in rational expectations under short-term adversity. Any
  model assuming a stable spot–futures relation will fail exactly when it matters.

**Settlement.** Exchanges prefer cash settlement because physical delivery is operationally hard,
and most futures never reach delivery — but NYMEX energy contracts still rely on the physical
delivery mechanism as the backstop. The convergence assumption ("futures price converges to spot as
delivery approaches") is what makes hedges work; **non-convergence is explicitly a hedging risk.**

---

## 20. Sanctions, dark fleet and AIS

Relevant because **Spec 11 treats AIS gaps as a signal.** They are not automatically a coverage
problem. The taxonomy of why AIS coverage goes dark:

- **Vessel-identity manipulation.**
- **Ship-to-ship (STS) transfers** in open water — routine cargo operations that become an evasion
  tool.
- **Deliberate transponder disabling or spoofing.**

The IMO "shadow/dark fleet" concept names the durable mechanism by which sanctioned crude reaches
market. **Rule: an AIS gap is a hypothesis with at least two explanations — coverage and
concealment — and the dashboard must not collapse them into one.** Flag the gap; do not label it.

### The third explanation: vessel movements are not intent

There is a documented failure mode in the opposite direction — reading a vessel movement as
evidence of an arbitrage that was never there.

*The "false arbitrage" case (Texaco, 1998).* With the market awash and freight cheap, a trader
dredged the Milford Haven Waterway (~$300k) so a **VLCC** — 2 million bbl — could discharge at
Pembroke, purely to capture **economies of scale on shipping to the firm's own refinery**. The
market saw a VLCC go "on subs" in the North Sea and read it as the only thing a VLCC there could
mean: crude leaving Europe for the US, i.e. an open arb. Traders refused to believe the real
explanation even when told it directly. The charter moved Dated Brent; the desk had pre-bought
**4 million bbl of CFDs** precisely because it knew the market would misread the signal.

**The generalisation for Spec 11: a vessel movement is evidence about logistics, not about
intent.** The same charter is consistent with an export arbitrage, a scale play on internal
freight, a repositioning, or storage. Three distinct reasons a vessel signal misleads:

1. **Concealment** — identity manipulation, STS, transponder disabling (above).
2. **Coverage** — terrestrial/satellite AIS reception gaps.
3. **Ambiguity of purpose** — the movement is real and fully visible, and still does not mean what
   the obvious reading suggests.

Only the third is invisible to data-quality checks, which makes it the one most likely to reach a
chart. **Never let the dashboard narrate a cargo movement as an arbitrage without corroborating
price and contractual evidence** — the same rule as §10, arrived at from the opposite direction.

---

## 21. Common mistakes

| Mistake | Fix |
|---|---|
| Multiplying RBOB/ULSD by 42 twice, or not at all | Sanity-check the $50–200/bbl range |
| Charting a spread with a `$/bbl` axis when legs were never converted | Convert at ingest |
| Treating Brent–WTI as a quality spread | It is mostly logistics and regulation |
| Averaging or splicing MOC and VWA series | Structural break — flag it |
| Presenting Dated Brent as one physical commodity | Annotate basket composition changes |
| Labelling an inter-basin spread "arbitrage" | It is a spread until cargo evidence says otherwise |
| Picking one MOMR production table | Ingest both; plot the gap |
| Overwriting a prior forecast vintage | Vintages must coexist to be differenced |
| Explaining a historical move with the current macro vintage | Use the first print |
| One seasonal corridor across blended cracks | Per product, and exclude 2020 |
| One all-history LNG freight corridor | Split by market regime |
| "Refiner short the crack" | Name the legs |
| Reading a freight move as a gas signal | Freight is derived demand |
| Calling a price move supply-driven | The prior is demand; run the decomposition |
| Porting equity vol-skew intuition to gas | Gas skew is positive, the inverse of equities |
| Standard VaR as total utility risk | It excludes volumetric risk |
| A model calibrated on one power region applied to another | Regional behaviour is not transferable |
| MAPE on price levels as evidence of skill | Returns or direction, against a random walk |
| Treating a volatile stretch as a data fault | Volatility is oil's base case; stability needs the explanation |
| One seasonal/vol corridor across 1970–today | It spans different supply-control regimes — split them |
| Mixing crude and pump-level elasticities | −0.06 crude vs −0.293 gasoline measure different things |
| Charting flat prices only | The negotiated differential is where the information is |
| Joining two "Platts-linked" series | Averaging windows differ (5-day vs full-month) — record the window |
| Mixing benchmarks along one supply chain | That manufactures the basis risk the market avoids |
| Flat per-month storage cost across tenors | Storage rates *fall* with commitment length |
| Trusting an iterative valuation's output | Confirm convergence — a default iteration cap silently underprices |
| Reading a vessel movement as intent | Logistics, storage and repositioning look identical to an arb |

---

## Sources and provenance

Distilled from a corpus of 89 PDFs (85 unique documents) — trading manuals, energy economics
textbooks, risk and derivatives texts, and ~30 journal articles. Principal sources:

- **Oil market structure** — Long, *Oil Trading Manual* (2003); Imsirovic, *Trading and Price
  Discovery for Crude Oils*; Trafigura, *Commodities Demystified* (2018); Bouchouev, *Virtual
  Barrels*; Newman, *World of Oil Derivatives*; van Woenzel, *The Oil Traders' Word(s)* (2012).
- **Benchmarks/PRAs** — Owain Johnson, *The Price Reporters* (Routledge, 2017), incl. ch. 3 on how
  benchmarks work.
- **Price regimes and volatility structure** — Robert McNally, *Crude Volatility: The History and
  the Future of Boom-Bust Oil Prices* (Columbia UP / Center on Global Energy Policy), esp. ch. 3
  and ch. 10.
- **Trade mechanics** — Owain Johnson, *40 Classic Crude Oil Trades* (Routledge, 2022): ch. 4
  "A false arbitrage" (Adi Imsirovic) and ch. 39 "The invention of synthetic storage"
  (Ilia Bouchouev).
- **OPEC/supply** — OPEC MOMR (table structure only); Till, *OPEC Spare Capacity and the Term
  Structure of Oil Futures Prices* (EDHEC, 2014).
- **Gas and LNG** — Hafner & Luciani, ch. 20; Bhattacharyya; *LNG — A Nontechnical Guide*;
  Zhuravleva, *The Nature of LNG Arbitrage* (OIES NG31, 2009); US gas primer; JKM equilibrium
  pricing study; LNG freight seasonality study (Dec 2010–Jun 2023).
- **Risk and derivatives** — energy risk-management texts covering spark/dark spreads, basis
  decomposition, volumetric risk and the Samuelson effect.
- **Empirical dynamics** — Kilian-style shock decomposition studies (1973–2021); oil tail-risk and
  inflation; GVAR equity study (1979Q2–2023Q3); EM sovereign spread study; tail-risk spillover and
  EVT studies; China FX-spread Hurst study; US gasoline Edgeworth-cycle study.
- **Refining margins** — Fousekis & Grigoriadis (2017); Alexander, Prokopczuk & Sumawong (2013);
  Liu, Vedenov & Power (2017).
- **Macro** — *The Trader's Guide to Key Economic Indicators*; *International Economic Indicators
  and Central Banks*. US conventions — verify current dates against the issuing agency.

Source PDFs are **not** in the repo; they live in `~/Desktop/skill-pdfs`, with extracted text
retained under `~/Documents/claude-recovery-35044e9a/pdf-text/`.

**Deliberately excluded:** dated market reports (MOMR values, Vitol outlook, bank commodity
updates) — these are *data to ingest, not knowledge to encode*. Also narrative histories, trader
memoirs and forecasting-paper content already covered by section 18.

**Known gaps.** No cushion-gas/working-gas ratios or storage deliverability curves — the corpus
does not quantify them; source from AGSI+/ALSI+ or operator documentation. No EIA WPSR parsing
conventions — no methodology document in the corpus. EU gas storage and flows (Specs 02/03/05) are
under-served: the only gas-fundamentals candidate was 2013-vintage and US shale-focused; prefer
AGSI+/ALSI+ and ENTSOG methodology documentation.

**Corpus coverage is now complete.** The 11 files lost to a session crash during the original pass
were re-mined and folded in: McNally's *Crude Volatility* (§15 price regimes and elasticities),
*40 Classic Crude Oil Trades* (§5 storage optionality, §20 false arbitrage), and *The Price
Reporters* ch. 3 (§4 benchmark ecosystem). Five of the eleven were confirmed as **dated market
reports** — an OPEC MOMR (June 2026), a bank oil-market note (May 2023), a research note
(Sept 2024), a short market commentary, and a gasoline-crack trade recommendation — and are
excluded under the standing rule that dated reports are *data to ingest, not knowledge to encode*.
Two more (equity volatility-arbitrage papers) carry no energy content. Vitol's *Long Term Oil
Demand Outlook* (Feb 2025) is likewise a forward-looking forecast rather than mechanism; its one
durable methodological point is retained — a **15-year horizon** is chosen because it matches
technological cycles and vehicle-fleet turnover, beyond which uncertainty rises sharply.
