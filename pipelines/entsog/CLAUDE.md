# pipelines/entsog — Claude Code Guide

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

## Corridor → pointKey table (Session A; RU_UA_TRANSIT/LNG_ENTRY come in Session B)
All found live via `GET /operatorpointdirections.json`, not guessed:

| Corridor | pointKey | direction | from_node | to_node | label |
|---|---|---|---|---|---|
| NO_EXPORTS | `ITP-00105` | entry | NO | DE | Emden EPT1 (Thyssengas) |
| NO_EXPORTS | `ITP-00075` | entry | NO | DE | Emden NPT (Thyssengas) |
| NO_EXPORTS | `ITP-00126` | entry | NO | DE | Dornum (Open Grid Europe) |
| NO_EXPORTS | `ITP-00106` | entry | NO | BE | Zeebrugge ZPT |
| NO_EXPORTS | `ITP-00519` | entry | NO | FR | Dunkerque DKB |
| NO_EXPORTS | `ITP-00091` | entry | NO | GB | Easington |
| NO_EXPORTS | `ITP-00022` | entry | NO | GB | St. Fergus |
| TAP | `ITP-00008` | entry | TAP | IT | Melendugno |
| TURKSTREAM_EU | `ITP-00549` | entry | TURKSTREAM | BG | Strandzha 2 / Malkoclar |
| ES_FR | `ITP-00304` | entry | FR | ES | VIP Pirineos (Enagas side) |
| UK_BE | `ITP-00005` | entry | BE | GB | Bacton (IUK) |
| GB_IE | `ITP-00495` | entry | GB | IE | Moffat (IE) |

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
