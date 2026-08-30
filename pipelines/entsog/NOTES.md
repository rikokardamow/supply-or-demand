# pipelines/entsog — notes

## Auth
None — ENTSOG's Transparency Platform is a fully public API. No key, no header.

## Pagination — `limit=-1`, not offset looping
Both endpoints used here default to a confusing ~100-row page (the directory endpoint's
default even applies an opaque internal `virtualPointKey` filter you didn't ask for).
**`limit=-1` returns everything in a single call** — confirmed live: 2,253 directory rows,
and a 393-day physical-flow range returning in one request instead of ~4 pages. Always pass
`limit=-1`; don't build an offset-increment loop like `pipelines/eia`/`pipelines/gie` use for
their paginated endpoints — it isn't needed here and would just be slower.

## Units — kWh/d, convert with ÷1,000,000
Physical Flow values arrive in `kWh/d`. GWh/d = kWh/d ÷ 1,000,000 (not ÷1,000 — that would be
1000x too large). Confirmed against a real value: Emden EPT1 (`ITP-00105`) on 2026-08-25 was
287,678,693 kWh/d = 287.68 GWh/d, a plausible single-point flow rate.

## Timestamps — take the date, don't resolve the timezone
`periodFrom` is the gas-day label at a fixed local time with a real UTC offset
(`"2026-08-01T06:00:00+02:00"` in August, `"...T06:00:00+01:00"` in March) — the offset
shifts across DST. Parsing the full ISO string with `pd.to_datetime` over a multi-year range
mixes `+01:00`/`+02:00` and **raises** (`ValueError: Mixed timezones detected`) — hit live
running Session B's 2-year pull, not something a 30-day Session A test window surfaces. Only
the calendar date matters for a daily series (same plain-date convention as
`pipelines/eia`/`pipelines/gie`), so `ENTSOGClient._get_indicator_data` takes the date
substring (`periodFrom[:10]`) rather than resolving a timezone.

## Multiple operators per point — pass `operator_key` where it matters
Several points in the directory are registered to **more than one operator** — confirmed
live by checking every corridor point's `(pointKey, directionKey)` against the directory.
Most of these are harmless (the second operator's rows come back with `value=""` for the
indicator actually being pulled, already dropped by the existing empty-string handling). Two
are not, and would silently double-count if left unfiltered:
- **`ITP-00304` (VIP Pirineos, ES_FR)** — both `ES-TSO-0006` (Enagas) and `FR-TSO-0002`
  (Terega) report real, materially different "entry" values for **both** Physical Flow and
  Nomination (confirmed live: Enagas ~1.3–7M kWh/d, Terega ~16–34k kWh/d, same days).
- **`ITP-00008` (TAP Melendugno)** — `AL-TSO-0001` (TAP AG)'s Physical Flow rows are empty
  (harmless), but its **Nomination** rows are real, alongside `IT-TSO-0001` (Snam Rete Gas)'s
  — doubles nomination row counts (1458 vs. the expected ~729) if unfiltered.

Fix: `client.get_physical_flow`/`get_nomination` accept an optional `operator_key`, added to
the request params (`operatorKey` — a real, documented ENTSOG filter param, confirmed live to
filter server-side). `corridors.py`'s `PointSpec.operator_key` carries it for these two
points, pinned to the **receiving side** per the existing entry/exit convention below. Every
other point's ambiguity was checked and found harmless before deciding not to pin it —
don't assume a second operator is always safe to ignore; check the actual values first.

## Direction convention — always the receiving TSO's "entry"
Every cross-border point appears twice in the directory: the sending country's TSO reports
`"exit"`, the receiving country's TSO reports `"entry"` for the same physical flow. This
project always uses the **receiving side's `"entry"`** row (e.g. Emden: Thyssengas/DE
`entry`, not Gassco/NO `exit`) — consistent across every corridor below.

## `from_node`/`to_node` convention
- Point-to-point (Norwegian landing points, interconnectors): the two adjacent ISO country
  codes, e.g. `NO`→`DE`, `FR`→`ES`.
- Multi-country transit routes where no single upstream country is clearly "the" source
  (TAP: Azerbaijan via Georgia/Turkey/Greece/Albania; TurkStream: Russia via Turkey):
  `from_node` names the **pipeline itself** (`"TAP"`, `"TURKSTREAM"`) rather than guessing a
  country code that isn't clearly correct.

## Corridor → pointKey table (final — 8 corridors, 21 points, Sessions A+B)
All found live via `GET /operatorpointdirections.json`, not guessed:

| Corridor | pointKey | direction | operator_key | from_node | to_node | label |
|---|---|---|---|---|---|---|
| NO_EXPORTS | `ITP-00105` | entry | — | NO | DE | Emden EPT1 (Thyssengas) |
| NO_EXPORTS | `ITP-00075` | entry | — | NO | DE | Emden NPT (Thyssengas) |
| NO_EXPORTS | `ITP-00126` | entry | — | NO | DE | Dornum (Open Grid Europe) |
| NO_EXPORTS | `ITP-00106` | entry | — | NO | BE | Zeebrugge ZPT |
| NO_EXPORTS | `ITP-00519` | entry | — | NO | FR | Dunkerque DKB |
| NO_EXPORTS | `ITP-00091` | entry | — | NO | GB | Easington |
| NO_EXPORTS | `ITP-00022` | entry | — | NO | GB | St. Fergus |
| TAP | `ITP-00008` | entry | `IT-TSO-0001` | TAP | IT | Melendugno |
| TURKSTREAM_EU | `ITP-00549` | entry | — | TURKSTREAM | BG | Strandzha 2 / Malkoclar |
| ES_FR | `ITP-00304` | entry | `ES-TSO-0006` | FR | ES | VIP Pirineos (Enagas side) |
| UK_BE | `ITP-00005` | entry | — | BE | GB | Bacton (IUK) |
| GB_IE | `ITP-00495` | entry | — | GB | IE | Moffat (IE) |
| RU_UA_TRANSIT | `ITP-00184` | entry | — | RU | UA | Sudzha (Gas TSO UA side) |
| LNG_ENTRY | `LNG-00027` | entry | — | LNG | NL | Gate Terminal |
| LNG_ENTRY | `LNG-00017` | entry | — | LNG | BE | Zeebrugge LNG |
| LNG_ENTRY | `LNG-00024` | entry | — | LNG | FR | Montoir de Bretagne |
| LNG_ENTRY | `LNG-00029` | entry | — | LNG | FR | Fos (Tonkin/Cavaou) |
| LNG_ENTRY | `LNG-00012` | entry | — | LNG | ES | Barcelona |
| LNG_ENTRY | `LNG-00006` | entry | — | LNG | PL | Świnoujście |
| LNG_ENTRY | `LNG-00004` | entry | — | LNG | IT | OLT LNG / Livorno |
| LNG_ENTRY | `LNG-00026` | entry | — | LNG | PT | Sines |

RU_UA_TRANSIT is genuinely thin history (456/731 days in the 2-year pull) — Ukraine transit
via Sudzha stopped partway through the window, kept per the spec's "may be zero/dormant,
keep for history". LNG_ENTRY picks one representative terminal per major EU LNG-importing
country from the directory's `pointType == "LNG Entry point"` rows, not every terminal
ENTSOG tracks — `from_node="LNG"` since it's ship-borne, no single upstream country, same
convention as TAP/TURKSTREAM_EU.

Note some names have multiple candidate points (e.g. Dornum has 3: `ITP-00188` Gasunie
Deutschland, `ITP-00126` Open Grid Europe, `ITP-00525` GASPOOL) — `ITP-00126` was picked as
the primary one; worth revisiting if Session B's totals don't reconcile against the TP
website within a few %.

**2 of the 7 `NO_EXPORTS` points have no usable data**, discovered live running the actual
pull (not something a schema check would catch):
- `ITP-00075` (Emden NPT) — the API returns **404 `{"message": "No result found"}`** for any
  date range tried (even full-year 2026), despite the directory marking it `hasData: true`.
  `ENTSOGClient.get_physical_flow` treats this specific message as "no data", not fatal —
  but a *different* 404 message exists too (`"Data on the TP is archived..."`, triggered by
  requesting >5 years back) which is a real error and still raises. Match on message text,
  don't blanket-swallow every 404.
- `ITP-00519` (Dunkerque DKB) — returns a row **per day** but with `"value": ""` for every
  single day in a real 31-day range, rather than omitting the day. The client drops rows
  where `value` is `""`/`None` before the `float()` conversion (same missing-value pattern as
  GIE's `"-"` handling).

`pull_no_exports.py` therefore only writes 5 of the 7 points' data — confirmed correct: the
combined total across those 5 (2,535.03 GWh/d for 2026-08-28) matched an independent live
sum exactly.

## Data model — `flows`, at point level (not a corridor-aggregated total)
Each point is written as its own `flows` row (`from_node`/`to_node` per the point, not a
shared corridor-level node). Corridor totals (e.g. "NO_EXPORTS" summed across all 7 points)
are computed at read/analysis time — not baked into what gets stored, per the spec's own
"flows at point level, plus a corridor-aggregated materialised view" data model.

**`(from_node, to_node, ts)` is *not* a unique key** — multiple distinct physical points can
share the same country pair (NO_EXPORTS alone has 2 separate DE-bound points: Emden EPT1 and
Dornum, both legitimately kept as separate rows with different values for the same day). A
`GROUP BY from_node, to_node, ts HAVING COUNT(*) > 1` query will flag these as "duplicates" —
they aren't; the schema has no per-point identifier column, so don't use that grouping to
check pull idempotency. **Check total row count instead**: re-running `pull_no_exports.py`
twice in a row left the row count unchanged (151 both times) — that's the real idempotency
signal here, not a from_node/to_node/ts uniqueness check.

## Directory caching
`pipelines/entsog/directory.py`'s `load_directory()` caches the full directory as Parquet at
`data/raw/entsog/operatorpointdirections.parquet` (git-ignored), refreshing only if the
cache file is older than 30 days — the directory rarely changes and the full fetch is one
sizeable call, no need to repeat it on every pull.

## revision_date
`flows` (per `core/schemas.py`) has no `revision_date` column, unlike `ts_long` — `write_flows`
does plain full-row de-dup, not revision-aware de-dup. The API does provide a real
`lastUpdateDateTime` per row (same idea as GIE's `updatedAt`), currently unused since nothing
consumes it yet — Session D's "15-day revision window" (re-pull trailing gas-days) may need to
either extend the `flows` schema or handle revision logic entirely in the pull script instead
of relying on storage-level de-dup; decide then, don't guess now.

**Re-pulling a corrected historical backfill**: `write_flows`'s de-dup is exact-row-match, not
an overwrite — re-running `pull_flows.py` after a client/corridor fix does *not* remove old
wrong rows already on disk if their values differ from the corrected ones (they just sit
alongside as extra rows forever). Hit this directly fixing the operator-disambiguation bug
above — had to delete `data/lake/flows/source=entsog/` before re-running once the fix
landed. `data/` is git-ignored pipeline output, safe to clear and regenerate; do the same for
any future correction to a full-backfill script.

## Session B — nominations, corridor aggregation, and the page
`pull_flows.py` (supersedes Session A's `pull_no_exports.py`) pulls the full 2-year window
for every point in every corridor, for **both** indicators: Physical Flow → `flows` with
`mode="pipeline"`, Nomination → `flows` with `mode="nomination"` (per the spec's data model).
14,311 physical-flow rows + a comparable nomination count across the 21 points, confirmed
correct after the operator-disambiguation fix (re-run showed ES_FR/TAP row counts back to
~1/day instead of ~2/day).

`transforms.py::corridor_aggregate(flows_df, CORRIDORS, mode="pipeline")` sums point-level
rows into one (corridor, day) total. This works from `(from_node, to_node)` pairs alone — the
`flows` schema has no point-identifier column — which is safe here because no two corridors
in `CORRIDORS` share a pair (checked, not assumed).

Page `03_eu_gas_flows.py` (Session B scope: Sankey + corridor small multiples only — the
directional map is Session C, the physical-vs-nomination gap chart is Session D):
- **Sankey**: built from the *raw* point-level `(from_node, to_node)` pairs (not
  corridor-collapsed), averaged over the trailing 7 days — this is what makes "Sankey totals
  reconcile with corridor time-series totals" a real, checkable equality rather than an
  approximation: summing every Sankey link that belongs to a given corridor (by the same
  `(from_node, to_node)` membership `corridor_aggregate` uses) equals that corridor's own
  aggregated total for the same window, because both are the same sum over the same rows.
  A country code can legitimately appear as both a Sankey source and target (e.g. `FR`
  receives from `NO_EXPORTS` and separately feeds `ES` via `ES_FR`) — that's a real hub
  re-export relationship, not a bug.
- **Corridor time series**: `core.theme.current_vs_prior_year_chart` (new — navy current
  year vs. grey prior year), not `seasonal_range_chart`, because ENTSOG only has ~2 years of
  history, nowhere near the 5-year corridor `core.seasonal` needs. Since the 2-year pull is a
  rolling window rather than calendar years, both years are indexed by "days since window
  start" rather than day-of-year, so they overlay regardless of calendar alignment.
