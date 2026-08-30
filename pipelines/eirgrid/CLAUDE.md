# pipelines/eirgrid — Claude Code Guide

## Client
Public, undocumented JSON API — `GET https://www.smartgriddashboard.com/DashboardService.svc/data`,
params `area`/`region`/`datefrom`/`dateto` (`%d-%b-%Y %H:%M`). No key required, so none of
`pipelines/entsoe`'s "never print a raw exception" concern applies here — nothing in this
client's URL is secret.

Per the spec's own instruction ("wrap the response shape in one adapter function so a format
change breaks exactly one file"), every call goes through `EirGridClient._fetch_rows` — the
only place that knows the response is `{"ErrorMessage": ..., "Rows": [{"EffectiveTime",
"FieldName", "Region", "Value"}]}`.

## Confirmed field name → concept mapping (live queries, ROI region)
| `area` param | `FieldName` in response | Concept | Unit |
|---|---|---|---|
| `demandactual` | `SYSTEM_DEMAND` | ROI demand | MW |
| `generationactual` | `GEN_EXP` | ROI generation | MW |
| `windactual` | `WIND_ACTUAL` | ROI wind | MW |
| `co2intensity` | `CO2_INTENSITY` | Grid CO2 intensity | gCO2/kWh |
| `interconnection` | `INTER_EWIC`, `INTER_GRNLK`, `INTER_NET_ROI` | Interconnector flows (3 fields per call) | MW |

## No solar-specific area exists — a correction to the spec's own formula
`area=solaractual` returns a clean, genuine error (`{"ErrorMessage": "Invalid Area:
'solaractual'.", "Rows": []}`) — confirmed live, not flakiness. EirGrid doesn't track ROI
solar as a distinct series. The spec's SNSP formula `(wind + solar + HVDC imports) / demand`
is implemented in `transforms.py::snsp_proxy` **without the solar term** — there's nothing to
sum. If EirGrid ever adds a solar area, add it as a third positional/optional argument to
`snsp_proxy` rather than reworking its signature.

## A correction to the spec's interconnector list: EWIC/Greenlink, not EWIC/Celtic/Moyle
The spec's text says "interconnector flows (EWIC/Celtic/Moyle)" — confirmed live this is
wrong for the ROI region. The `interconnection` area returns exactly `INTER_EWIC` and
`INTER_GRNLK` (Greenlink, commissioned 2024) for `region=ROI`. Celtic (Ireland-France) isn't
present in this API at all; Moyle connects Northern Ireland, which is a different `region`
value, not ROI. The Ireland panel plots EWIC and Greenlink only.

## Sign convention — confirmed live, positive = import into ROI
`INTER_NET_ROI == INTER_EWIC + INTER_GRNLK` exactly, checked across multiple timestamps
(e.g. 922=408+514, 846=333+513). Cross-checked independently against
`generation + net_import ≈ demand` (e.g. 2586+922=3508 vs demand=3726 — a reasonable gap for
a transmission-level proxy, likely embedded/distribution generation not captured in
`GEN_EXP`). `snsp_proxy` clips `net_interconnection` to `>= 0` so export periods (negative
net) contribute zero non-synchronous import rather than a negative one.

## Timestamps are Ireland local time, not UTC
Confirmed live: the response's own `LastUpdated` field was exactly 1 hour ahead of
`datetime.now(UTC)` during BST. `EirGridClient.get_series` localizes `EffectiveTime` to
`Europe/Dublin` (`ambiguous="NaT", nonexistent="NaT"` across the DST transition) then converts
to naive UTC, matching every other pipeline's `ts_long` convention.

## Future timestamps within a requested window return `Value: null`
Confirmed live (e.g. querying "today" through 23:59 returns a row for a not-yet-occurred
15-min slot with `Value: None`). `get_series` filters these out before `float()` conversion —
crashing on `float(None)` would otherwise abort the whole pull for one harmless trailing row.

## Confirmed real ~30-day max range per call — not flakiness, a genuine server-side limit
Diagnosed by testing 30/45/60/75/90-day ranges for the same area: 30 days succeeded cleanly,
45+ days failed with a real (non-503) error body (`"An error has occured during the call to
the dashboard, please try again"`), 90 days got a raw 503 instead. `EirGridClient.get_series`
transparently chunks any wider request into `MAX_RANGE_DAYS = 30`-day windows. Each chunk's
range is inclusive on both ends, so consecutive chunks both return the boundary timestamp —
deduplicated via a `(EffectiveTime, FieldName)` `seen` set before parsing, rather than relying
on `write_ts_long`'s storage-level dedup alone, since callers may use the returned DataFrame
directly.

## The API is also genuinely flaky, separately from the range limit
Matches the spec's own "treat as fragile: cache aggressively, be gentle" instruction — 503s
on a fair share of calls, clearing on retry. `_fetch_rows` retries up to `MAX_RETRIES = 5`
with exponential backoff (capped 60s), plus a flat `PACING_SECONDS = 1.0` courtesy delay
before every request, same idea as `pipelines/gie`'s pacing delay. A 503 here returns an HTML
error page, not JSON — caught via `ValueError` (covers `JSONDecodeError`) alongside
`requests.exceptions.RequestException`.

## Series id convention
`eirgrid.ROI.{field}` — `demand`, `generation`, `wind`, `co2_intensity`, `inter_ewic`,
`inter_greenlink`, `inter_net` — `freq="15T"`, `geo="ROI"`, matching the `{source}.{geo}.{field}`
pattern used by `pipelines/gie`/`pipelines/entsoe`.

## Verified (Session C)
90-day ROI pull: 60,487 rows across 7 series, zero failures on the run after the chunking
fix (`demandactual`/`generationactual`/`windactual`/`co2intensity`: 8,641 rows each;
`interconnection`: 25,923 rows for its 3 fields). Acceptance criterion met: the lake's latest
ROI demand values matched a fresh, independent `EirGridClient.get_series` call exactly
(3595.0/3549.0/3513.0 MW across the last 3 timestamps, zero diff).

## Ireland panel (`apps/dashboard/pages/04_eu_power.py`)
Dual-axis demand-vs-wind chart (`core.theme.dual_axis_chart`), an SNSP proxy gauge
(`core.theme.gauge_chart`, new — a `go.Indicator` gauge with green/orange/red bands split at
`(50.0, 75.0)`, chosen as a reasonable approximation of Ireland's well-known ~75% SNSP
operational limit terminology, not a live-verified exact current policy figure since that's a
grid-operator policy limit, not a queryable data series), and an EWIC/Greenlink
interconnector flow chart.
