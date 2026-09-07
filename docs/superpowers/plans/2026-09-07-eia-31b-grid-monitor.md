# Spec 31B — Grid Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reach ERCOT and PJM — the two markets that move the US gas book most and the two `pipelines/gridstatus_iso/` cannot see — by ingesting EIA's Grid Monitor: hourly demand, generation by fuel type, and inter-BA interchange.

**Architecture:** All three routes are **non-series-based** (confirmed live: `400` on `facet/series`) and none matches the existing `get_operational_series` signature. So this plan adds one generalised facet-dict query path to `pipelines/eia/client.py`, a small `pipelines/eia/rto.py` holding the balancing-authority constants and the minted series-id scheme, and three thin `pull_*.py` modules. Demand and fuel mix go to `ts_long`; interchange goes to `flows`. No new schema, no new pipeline package.

**Tech Stack:** Python 3.12, `pipelines/eia/client.py`, `core.storage.write_ts_long` / `write_flows`, `core.failures`, pandas. Tests: pytest + vcrpy cassettes.

**Spec:** `specs/31_eia-coverage-extensions.md` (item 2)

**Scope note:** This plan covers item **2 only**. Items 1 and 3 shipped in plan 31A; items 4, 5 and 6 are plan 31C. Every item in Spec 31 is independent by design.

---

## What plan 31A's Task 0 already established — binding, do not re-derive

Plan 31A's Task 0 walked all six items' routes. Its findings are recorded in
`pipelines/eia/CLAUDE.md` under "Spec 31 routes — confirmed live 2026-09-06" and they
**bind this plan**. The three that matter most here:

1. **All three `electricity/rto/*` routes return `400 Bad Request` on `facet/series`.**
   That is a route *shape*, not a failure — the same shape
   `electricity/electric-power-operational-data` has. `get_series` / `_fetch_rows` cannot
   reach these routes at all. **Do not call `list_series` on them.**

2. **They are three *different* non-series shapes, and none matches
   `get_operational_series`'s `{fueltypeid, sectorid, location}` signature:**

   | Route | Facets | Data key | Target schema |
   |---|---|---|---|
   | `electricity/rto/region-data` | `respondent`, `type` | one `value` | `ts_long` |
   | `electricity/rto/fuel-type-data` | `respondent`, `fueltype` | one `value` | `ts_long` |
   | `electricity/rto/interchange-data` | `fromba`, `toba` (no type/fueltype at all) | one `value` | **`flows`** |

3. **Grid Monitor is hourly-only.** All three declare only `hourly` and `local-hourly`
   (confirmed live via each route's own metadata endpoint, `GET /v2/{route}` with no
   `/data` or `/facet` suffix). **There is no daily or monthly rollup to fall back to.**
   Combined with the spec's "all 65 Lower-48 balancing authorities", a naive full pull is
   hourly × 65 BAs × three datasets — several orders of magnitude more rows than any other
   route in `pipelines/eia/`.

## The two decisions this plan makes up front, because Task 0 said to decide them before writing pull code

### Decision A — row volume: a named BA subset and a trailing window, not "all 65 BAs, all history"

A back-of-envelope on the spec's literal scope: 65 respondents × ~4 `type` codes × 8,760
hours ≈ **2.3 M rows per year for `region-data` alone**; fuel mix is larger again; the
three together are roughly **8 M rows/year**. Ingesting that would dominate the lake with
load-research granularity the spec explicitly rejects ("**Do not** ingest sub-regional
demand ... it is granular load research, not gas-demand signal").

**This plan therefore scopes to gas-relevant markets and a trailing window:**

- **BA subset** (`RTO_RESPONDENTS` in `rto.py`): `ERCO` (ERCOT), `PJM`, `MISO`, `SWPP`
  (SPP), `CISO`, `NYIS`, `ISNE`, plus the `US48` Lower-48 aggregate for context — 8
  respondents, not 65. **ERCO and PJM are the whole justification for this item** (the
  spec: they are "precisely the two the existing pipeline cannot see"); the rest are the
  other large gas-burning markets, and `US48` gives a national denominator.
- **Trailing window**: `main()` pulls the last `TRAILING_DAYS = 3` days on every run, so a
  daily schedule keeps the series current and re-pulls two days of revisions. A one-off
  backfill is `--days N` on the command line.

At that scope a 90-day backfill is roughly 8 × 4 × 24 × 90 ≈ **69 k** demand rows, ≈ 138 k
fuel-mix rows, and ≈ 65 k interchange rows — comfortably in the lake's existing range.

**Widening the subset later is a constant edit, not a rewrite.** Record the number of BAs
actually ingested in `CLAUDE.md` so a future reader knows the coverage is deliberate.

### Decision B — cadence: the `daily` group, because the scheduler has no hourly group

`infra/run_scheduled.py`'s `CADENCE_GROUPS` are `daily`, `weekly_fri` and `monthly`. There
is no hourly cadence and this plan does not add one — hourly *data* on a daily *pull* is
the right trade here (the gas-demand signal is read as a daily shape, and EIA's own
publication lags real time anyway). All three pulls register in `daily`.

---

## Global Constraints

Copied from the spec, plan 31A and root `CLAUDE.md`. Every task's requirements implicitly
include this section.

- **Never guess a series code or a facet value.** Every `respondent`, `type`, `fueltype`
  and BA pair used here is discovered live in Task 0. Spec 30's discovery found a route its
  own plan had written off; Spec 17 shipped a wrong ticker that only a live lookup caught.
- **These routes have no `series` facet.** `400` on `facet/series` is the expected shape,
  not an error to work around.
- **A wrong `frequency` returns empty, not an error.** `hourly` is the value confirmed live.
- **EIA publishes real `value: null` rows.** The existing fetchers skip them and print the
  dropped count. Do not reintroduce an unconditional `float()`.
- **Units stored exactly as EIA publishes them, never converted at ingest**
  (`megawatthours`). Conversion belongs in `core/`.
- **Series IDs stay in EIA's native form where one exists.** These routes supply none, so
  this plan **mints them deterministically and documents the scheme** — the precedent is
  `get_operational_series`'s `ELEC.<DATA_KEY>.<fueltypeid>-<location>-<sectorid>.<freq>`
  and `generator_fuel_series_id` in `pipelines/eia/pull_prices.py`. **A minted id is
  permanent once written**: changing a scheme later orphans every row already stored.
- **Never select a series by list index.** Spec 30 shipped `GENERATOR_FUEL[0]`, where
  reordering a constant would have plotted the wrong unit against a price axis, raising
  nothing. Use named constants.
- **Never read the lake unbounded.** `read_ts_long` takes `source` and `series_prefix`;
  `source` narrows the parquet glob itself. An unbounded read grew until it failed as a
  `pickle.dumps` error inside `st.cache_data`, pointing nowhere near the read.
- **Cycle a palette by index, never `zip(..., strict=False)`** against a fixed tuple.
- `source="eia"`, `freq="hourly"`, no new schema, no new pipeline package.
- Per-route resilience via `core.failures`; a wholly failed run must raise so the exit
  status is honest.
- British English; `from __future__ import annotations`; typed throughout.
- Repo venv: `.venv/Scripts/python.exe`, `pytest.exe`, `ruff.exe`, `mypy.exe`. Bare
  commands are **not** on PATH.
- **`apps/dashboard/**` and `core/theme.py` belong to a concurrent design session** which
  is mid-migration of all 16 pages to a new section kit. **This plan contains no dashboard
  task** — see "Page sections" at the foot of this plan.
- **Stage explicitly, never `git add -A`.** Name every file on the `git add` line.

---

### Task 0: Discover the real facet values — no pull code

Plan 31A's Task 0 established these routes' *shapes*. It deliberately did **not** select
facet values ("not selected — plan 31B scope"). This task does that, and nothing else.
**No pull code, no tests** — the deliverable is recorded findings.

**Files:**
- Modify: `pipelines/eia/CLAUDE.md` (append a "Spec 31B — Grid Monitor facet values" section)

**Interfaces:**
- Consumes: `EIAClient` (exists), and the route shapes recorded in `CLAUDE.md`.
- Produces: the real facet values and response field names Tasks 1–5 code against.

- [ ] **Step 1: Dump each route's facet values**

Throwaway script, do **not** commit. Note this queries `facet/<name>`, **not**
`facet/series` — the latter is the one that 400s.

```python
import requests
from core.config import settings

BASE = "https://api.eia.gov/v2"
ROUTES = {
    "electricity/rto/region-data": ["respondent", "type"],
    "electricity/rto/fuel-type-data": ["respondent", "fueltype"],
    "electricity/rto/interchange-data": ["fromba", "toba"],
}

for route, facet_names in ROUTES.items():
    print(f"\n===== {route}")
    meta = requests.get(f"{BASE}/{route}", params={"api_key": settings.eia_api_key}, timeout=30)
    meta.raise_for_status()
    body = meta.json()["response"]
    print("  frequencies:", [f["id"] for f in body.get("frequency", [])])
    print("  data keys:  ", list(body.get("data", {})))
    for name in facet_names:
        resp = requests.get(
            f"{BASE}/{route}/facet/{name}", params={"api_key": settings.eia_api_key}, timeout=30
        )
        resp.raise_for_status()
        facets = resp.json()["response"]["facets"]
        print(f"  {name}: {len(facets)} values")
        for f in facets[:70]:
            print("     ", f.get("id"), "|", f.get("name"))
```

Record, for each route: the exact `type` codes on `region-data` (expect a demand code, a
day-ahead demand forecast code, a net-generation code and a total-interchange code — but
**use whatever the dump actually returns**), the exact `fueltype` codes on
`fuel-type-data`, and whether the 8 respondents this plan wants are all present under the
ids `ERCO`, `PJM`, `MISO`, `SWPP`, `CISO`, `NYIS`, `ISNE`, `US48`.

**A respondent id that is not in the dump is a finding.** Correct the constant to the real
id; do not invent one.

- [ ] **Step 2: Confirm the response field names on a real data call**

The three pull tasks build DataFrames out of these field names, so they must be read from a
real response, not assumed. `get_operational_series` learned the hard way that the value
column is named after the requested data key and the unit column is `<key>-units`; confirm
whether that holds here, where the key is literally `value`.

```python
params = {
    "api_key": settings.eia_api_key,
    "frequency": "hourly",
    "data[0]": "value",
    "facets[respondent][]": ["ERCO"],
    "facets[type][]": [<a real type code from Step 1>],
    "start": "2026-09-01T00",
    "end": "2026-09-02T00",
    "length": 5,
}
resp = requests.get(f"{BASE}/electricity/rto/region-data/data/", params=params, timeout=30)
resp.raise_for_status()
for row in resp.json()["response"]["data"]:
    print(row)
```

Record verbatim: **every key present in a row**, and specifically —
- what holds the number, and what holds its unit (`value-units`? `units`?);
- the exact `period` format for hourly (expect `YYYY-MM-DDTHH`, confirm it);
- whether `respondent` / `type` / `fueltype` / `fromba` / `toba` come back on each row
  (Tasks 3–5 mint series ids out of these, so a missing one is a blocker);
- whether `start`/`end` are accepted in `YYYY-MM-DDTHH` form and actually narrow the
  response.

Repeat the same call shape once for `fuel-type-data` (facets `respondent`+`fueltype`) and
once for `interchange-data` (facets `fromba`+`toba`).

- [ ] **Step 3: Establish the real row volume for this plan's chosen scope**

Decision A's arithmetic is an estimate. Measure it: request one full day of `region-data`
for all 8 respondents and count the rows.

```python
params = {
    "api_key": settings.eia_api_key, "frequency": "hourly", "data[0]": "value",
    "facets[respondent][]": ["ERCO", "PJM", "MISO", "SWPP", "CISO", "NYIS", "ISNE", "US48"],
    "start": "2026-09-01T00", "end": "2026-09-02T00", "length": 5000,
}
resp = requests.get(f"{BASE}/electricity/rto/region-data/data/", params=params, timeout=30)
body = resp.json()["response"]
print("rows for one day, 8 respondents, all types:", len(body["data"]))
print("total available:", body.get("total"))
```

**If one day exceeds `PAGE_SIZE` (5000), say so explicitly** — the paging loop handles it,
but a 90-day backfill would then be >90 requests per route and Task 6's backfill guidance
needs to reflect the real number.

- [ ] **Step 4: Discover which interchange pairs actually exist for the chosen BAs**

`interchange-data`'s facets are `fromba` and `toba`, and not every pair of BAs is
physically connected. Requesting a non-existent pair returns nothing rather than erroring,
which would silently produce an empty corridor.

```python
params = {
    "api_key": settings.eia_api_key, "frequency": "hourly", "data[0]": "value",
    "facets[fromba][]": ["ERCO", "PJM"],
    "start": "2026-09-01T00", "end": "2026-09-01T05", "length": 5000,
}
resp = requests.get(f"{BASE}/electricity/rto/interchange-data/data/", params=params, timeout=30)
pairs = sorted({(r["fromba"], r["toba"]) for r in resp.json()["response"]["data"]})
print(len(pairs), "real pairs out of ERCO/PJM:", pairs)
```

Record the **real** pair list for the 8 chosen respondents. Task 5 relies on each row
naming its own corridor, so this is a coverage check rather than a lookup table — but an
empty result for ERCO would mean the whole interchange task has nothing to ingest, and
that must be known before the pull code is written.

- [ ] **Step 5: Record the findings**

Append to `pipelines/eia/CLAUDE.md`, following that file's existing style — state what was
confirmed live versus declared, and record negatives:

```markdown
## Spec 31B — Grid Monitor facet values, confirmed live [DATE]

| Route | Facet | Values used | Total available |
|---|---|---|---|
| electricity/rto/region-data | respondent | | |
| electricity/rto/region-data | type | | |
| electricity/rto/fuel-type-data | fueltype | | |
| electricity/rto/interchange-data | fromba/toba pairs | | |

**Row field names on a real hourly response:** [verbatim key list]
**Value column:** [name]  **Unit column:** [name]  **Unit string:** [e.g. megawatthours]
**Period format:** [e.g. 2026-09-01T00]
**start/end accepted as:** [format, and whether they narrowed the response]
**Rows for one day x 8 respondents (region-data):** [real number]
**Real interchange pairs among the chosen BAs:** [real list]
**Respondent ids requested but NOT found:** [real list, or "none"]
```

Every bracket replaced with a real value. A committed `[DATE]` is a task failure.

- [ ] **Step 6: Commit**

```bash
git add pipelines/eia/CLAUDE.md
git commit -m "docs(eia): live-discovered Grid Monitor facet values for Spec 31B"
```

---

### Task 1: A generalised facet-dict query path on the client

**Files:**
- Modify: `pipelines/eia/client.py`
- Test: `tests/test_eia_client_facets.py`

**Interfaces:**
- Consumes: the existing `_fetch_rows` / `_fetch_operational_rows` paging idiom, `raise_sanitised`, `PAGE_SIZE`, `BASE_URL`.
- Produces:
  - `EIAClient._fetch_facet_rows(route: str, data_key: str, facets: dict[str, list[str]], frequency: str, start: str | None = None, end: str | None = None) -> list[dict[str, Any]]`
  - `EIAClient.get_facet_series(route: str, data_key: str, facets: dict[str, list[str]], frequency: str, series_id: Callable[[dict[str, Any]], str], geo: Callable[[dict[str, Any]], str], start: str | None = None, end: str | None = None) -> pd.DataFrame`
  - `EIAClient.get_facet_flows(route: str, data_key: str, facets: dict[str, list[str]], frequency: str, mode: str, start: str | None = None, end: str | None = None) -> pd.DataFrame`

  Tasks 3 and 4 call `get_facet_series`; Task 5 calls `get_facet_flows`. **Plan 31C's coal
  task also depends on `get_facet_series`** — `coal/consumption-and-quality` is the fourth
  non-series route.

**Why callables:** the three routes mint their series ids from *different* facet fields
(`respondent`+`type` vs `respondent`+`fueltype`), so the id scheme cannot live in the
client the way `get_operational_series`'s does. Passing a small typed function keeps the
paging, null-dropping and DataFrame assembly in one place — the alternative is returning
raw rows and duplicating that assembly across four pull modules.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_eia_client_facets.py
from __future__ import annotations

from typing import Any

import pytest
from core.schemas import validate_flows, validate_ts_long

from pipelines.eia.client import EIAClient


def _fake_rows() -> list[dict[str, Any]]:
    return [
        {"period": "2026-09-01T00", "respondent": "ERCO", "type": "D",
         "value": 45000, "value-units": "megawatthours"},
        {"period": "2026-09-01T01", "respondent": "ERCO", "type": "D",
         "value": None, "value-units": "megawatthours"},
        {"period": "2026-09-01T01", "respondent": "PJM", "type": "D",
         "value": 88000, "value-units": "megawatthours"},
    ]


def test_get_facet_series_builds_ts_long_and_drops_null_values(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = EIAClient(api_key="test")
    monkeypatch.setattr(EIAClient, "_fetch_facet_rows", lambda *a, **k: _fake_rows())

    df = client.get_facet_series(
        route="electricity/rto/region-data",
        data_key="value",
        facets={"respondent": ["ERCO", "PJM"], "type": ["D"]},
        frequency="hourly",
        series_id=lambda row: f"RTO.REGION.{row['respondent']}.{row['type']}.H",
        geo=lambda row: str(row["respondent"]),
    )

    validate_ts_long(df)
    # The null-value row must be dropped, not turned into NaN and not crash float().
    assert len(df) == 2
    assert list(df["series_id"]) == ["RTO.REGION.ERCO.D.H", "RTO.REGION.PJM.D.H"]
    assert set(df["geo"]) == {"ERCO", "PJM"}
    assert set(df["unit"]) == {"megawatthours"}
    assert set(df["source"]) == {"eia"}
    # A dropped row must be reported, never swallowed -- the convention every other
    # fetcher in this client follows.
    assert "dropped 1 row" in capsys.readouterr().out


def test_get_facet_flows_builds_flows_rows_from_fromba_toba(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = EIAClient(api_key="test")
    monkeypatch.setattr(
        EIAClient,
        "_fetch_facet_rows",
        lambda *a, **k: [
            {"period": "2026-09-01T00", "fromba": "ERCO", "toba": "SWPP",
             "value": 120, "value-units": "megawatthours"},
            {"period": "2026-09-01T01", "fromba": "ERCO", "toba": "SWPP",
             "value": None, "value-units": "megawatthours"},
        ],
    )

    df = client.get_facet_flows(
        route="electricity/rto/interchange-data",
        data_key="value",
        facets={"fromba": ["ERCO"]},
        frequency="hourly",
        mode="grid_interchange",
    )

    validate_flows(df)
    assert len(df) == 1
    assert df["from_node"].iloc[0] == "ERCO"
    assert df["to_node"].iloc[0] == "SWPP"
    assert df["mode"].iloc[0] == "grid_interchange"


def test_fetch_facet_rows_sends_one_repeated_param_per_facet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The whole point of this method: an arbitrary facet dict becomes facets[<name>][]
    # params. get_operational_series hardcodes three facet names and cannot express
    # respondent+type or fromba+toba at all.
    captured: dict[str, Any] = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"response": {"data": []}}

    def _fake_get(url: str, params: dict[str, Any], timeout: int) -> _Resp:
        captured.update(params)
        return _Resp()

    monkeypatch.setattr("pipelines.eia.client.requests.get", _fake_get)

    EIAClient(api_key="test")._fetch_facet_rows(
        route="electricity/rto/region-data",
        data_key="value",
        facets={"respondent": ["ERCO", "PJM"], "type": ["D"]},
        frequency="hourly",
        start="2026-09-01T00",
        end="2026-09-02T00",
    )

    assert captured["facets[respondent][]"] == ["ERCO", "PJM"]
    assert captured["facets[type][]"] == ["D"]
    assert captured["data[0]"] == "value"
    assert captured["start"] == "2026-09-01T00"
    assert captured["end"] == "2026-09-02T00"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/pytest.exe tests/test_eia_client_facets.py -v`
Expected: FAIL with `AttributeError: 'EIAClient' object has no attribute '_fetch_facet_rows'`

- [ ] **Step 3: Add the methods to `pipelines/eia/client.py`**

Add `from collections.abc import Callable` to the imports. Place these after
`get_operational_series` and before `list_series`.

```python
    def _fetch_facet_rows(
        self,
        route: str,
        data_key: str,
        facets: dict[str, list[str]],
        frequency: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict[str, Any]]:
        """Third sibling to `_fetch_rows` and `_fetch_operational_rows`, for routes with
        no `series` facet whose facet NAMES vary by route. Confirmed live: the three
        electricity/rto/* routes all 400 on facet/series, and each uses a different facet
        pair -- respondent+type, respondent+fueltype, and fromba+toba -- so
        `_fetch_operational_rows`'s hardcoded {fueltypeid, sectorid, location} cannot
        express any of them. `facets` is {facet_name: [values]}; each becomes a repeated
        `facets[<name>][]` parameter, the same repeated-value form `facets[series][]` and
        `facets[location][]` already use.

        `start`/`end` bound the window. The rto/* routes are hourly with no monthly
        rollup to fall back on, so an unbounded pull is the whole row-volume problem --
        see plan 31B's Decision A. Omitted, they return the route's full history."""
        rows: list[dict[str, Any]] = []
        offset = 0

        while True:
            params: dict[str, Any] = {
                "api_key": self._api_key,
                "frequency": frequency,
                "data[0]": data_key,
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
                "offset": offset,
                "length": PAGE_SIZE,
            }
            for facet_name, values in facets.items():
                params[f"facets[{facet_name}][]"] = values
            if start is not None:
                params["start"] = start
            if end is not None:
                params["end"] = end

            response = requests.get(f"{BASE_URL}/{route}/data/", params=params, timeout=30)
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise_sanitised(exc)
            page = response.json()["response"]["data"]
            rows.extend(page)

            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        return rows

    def _drop_null_values(
        self, rows: list[dict[str, Any]], route: str, data_key: str
    ) -> list[dict[str, Any]]:
        """EIA publishes real null values; float(None) would crash the pull outright.
        Dropped rows are named in the run log, never swallowed -- the same rule
        core.storage._drop_rows_with_no_value applies on the write side."""
        kept = [row for row in rows if row.get(data_key) is not None]
        dropped = len(rows) - len(kept)
        if dropped:
            print(f"{route} ({data_key}): dropped {dropped} row(s) with no value", flush=True)
        return kept

    def get_facet_series(
        self,
        route: str,
        data_key: str,
        facets: dict[str, list[str]],
        frequency: str,
        series_id: Callable[[dict[str, Any]], str],
        geo: Callable[[dict[str, Any]], str],
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """`ts_long` rows from a facet-dict route. EIA supplies no series id for these
        routes at all, and they mint theirs from different facet fields, so the caller
        passes `series_id` and `geo` as small functions of the raw row rather than this
        method hardcoding one scheme. See pipelines/eia/rto.py for the schemes actually
        used, and pipelines/eia/CLAUDE.md for why a minted id is permanent."""
        rows = self._drop_null_values(
            self._fetch_facet_rows(route, data_key, facets, frequency, start, end),
            route,
            data_key,
        )
        pulled_at = datetime.now(UTC)
        return pd.DataFrame(
            {
                "series_id": [series_id(row) for row in rows],
                "source": "eia",
                "ts": pd.to_datetime([row["period"] for row in rows]),
                "value": [float(row[data_key]) for row in rows],
                "unit": [row[f"{data_key}-units"] for row in rows],
                "geo": [geo(row) for row in rows],
                "freq": frequency,
                "revision_date": pulled_at,
            }
        )

    def get_facet_flows(
        self,
        route: str,
        data_key: str,
        facets: dict[str, list[str]],
        frequency: str,
        mode: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """`flows` rows from a facet-dict route. Unlike `get_flows`, which maps a known
        series id to a corridor, interchange-data carries `fromba`/`toba` on every row
        already -- so the corridor is read off the row rather than looked up."""
        rows = self._drop_null_values(
            self._fetch_facet_rows(route, data_key, facets, frequency, start, end),
            route,
            data_key,
        )
        return pd.DataFrame(
            {
                "source": "eia",
                "from_node": [row["fromba"] for row in rows],
                "to_node": [row["toba"] for row in rows],
                "value": [float(row[data_key]) for row in rows],
                "unit": [row[f"{data_key}-units"] for row in rows],
                "ts": pd.to_datetime([row["period"] for row in rows]),
                "mode": mode,
            }
        )
```

**If Task 0 Step 2 found the value or unit column is named something other than
`<data_key>` / `<data_key>-units`, correct these methods to match the real response and say
so in the commit message.** Task 0's findings take precedence over this code.

- [ ] **Step 4: Run green**

Run: `.venv/Scripts/pytest.exe tests/test_eia_client_facets.py -v`
Expected: 3 passed.

Then confirm nothing else on the client regressed:
Run: `.venv/Scripts/pytest.exe tests/ -k eia -q`

- [ ] **Step 5: Commit**

```bash
git add pipelines/eia/client.py tests/test_eia_client_facets.py
git commit -m "feat(eia): generalised facet-dict query path for the Grid Monitor routes"
```

---

### Task 2: Balancing-authority constants and the minted series-id scheme

**Files:**
- Create: `pipelines/eia/rto.py`
- Test: `tests/test_eia_rto.py`

**Interfaces:**
- Consumes: nothing but Task 0's discovered facet values.
- Produces: `RTO_RESPONDENTS: list[str]`, named per-BA constants (`ERCOT`, `PJM`, `MISO`, `SPP`, `CAISO`, `NYISO`, `ISNE`, `LOWER_48`), `REGION_TYPES: list[str]` with named members, `FUEL_TYPES: list[str]` with named members, `region_series_id(row: dict[str, Any]) -> str`, `fuel_series_id(row: dict[str, Any]) -> str`, `respondent_geo(row: dict[str, Any]) -> str`, `HOURLY: str`, `INTERCHANGE_MODE: str`. Tasks 3, 4 and 5 all import from here.

Separating this from the pull modules is deliberate: three pulls share one BA list, and a
minted series id is permanent once written to the lake, so its scheme deserves its own
tested unit rather than being inlined three times.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eia_rto.py
from __future__ import annotations

from pipelines.eia import rto


def test_the_two_markets_this_item_exists_for_are_present() -> None:
    # The spec's entire justification for item 2: gridstatus reaches CAISO and NYISO
    # only -- ERCOT is blocked by Incapsula (confirmed live 403) and PJM needs a Data
    # Miner 2 key the project does not hold. If these two are missing, this pipeline
    # has no reason to exist.
    assert rto.ERCOT in rto.RTO_RESPONDENTS
    assert rto.PJM in rto.RTO_RESPONDENTS


def test_respondents_are_named_constants_and_unique() -> None:
    # Spec 30 shipped GENERATOR_FUEL[0]; reordering that list would have plotted the
    # wrong unit against a price axis, raising nothing. Selected by name, never index.
    assert len(set(rto.RTO_RESPONDENTS)) == len(rto.RTO_RESPONDENTS)
    for name in (rto.ERCOT, rto.PJM, rto.MISO, rto.SPP, rto.CAISO, rto.NYISO, rto.ISNE):
        assert name in rto.RTO_RESPONDENTS


def test_region_series_id_is_deterministic_and_carries_both_facets() -> None:
    row = {"respondent": "ERCO", "type": "D", "period": "2026-09-01T00"}
    assert rto.region_series_id(row) == "RTO.REGION.ERCO.D.H"
    # Deterministic: the same row must always mint the same id, because the id is
    # permanent once written to the lake.
    assert rto.region_series_id(row) == rto.region_series_id(dict(row))


def test_fuel_series_id_is_distinct_from_region_series_id() -> None:
    # Both routes carry a `respondent`, and `type=NG` (net generation) is the same two
    # characters as `fueltype=NG` (natural gas). If the two schemes collided, a
    # fuel-mix value would overwrite a net-generation value in the lake, silently.
    region = rto.region_series_id({"respondent": "PJM", "type": "NG"})
    fuel = rto.fuel_series_id({"respondent": "PJM", "fueltype": "NG"})
    assert region != fuel
    assert fuel == "RTO.FUEL.PJM.NG.H"


def test_natural_gas_fuel_type_is_named() -> None:
    # Gas-fired generation is the whole gas-demand signal this item feeds.
    assert rto.NATURAL_GAS in rto.FUEL_TYPES
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/pytest.exe tests/test_eia_rto.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipelines.eia.rto'`

- [ ] **Step 3: Write `pipelines/eia/rto.py`**

**Replace every `type` and `fueltype` code below with Task 0's live-discovered values.**
They are placeholders here; Task 0 Step 1 dumps the real ones.

```python
"""Spec 31 item 2: balancing-authority constants and the minted series-id scheme for
EIA's Grid Monitor.

Why this exists at all: pipelines/gridstatus_iso/ reaches CAISO and NYISO only. ERCOT is
blocked by Incapsula/Imperva bot protection (confirmed live 403) and PJM requires a Data
Miner 2 key this project does not hold -- and those two are precisely the markets where
gas-fired generation most moves the gas book. EIA's RTO routes cover both.

The three rto/* routes supply NO series id of any kind (they have no `series` facet at
all -- confirmed live, 400 on facet/series). This module mints one per row instead, the
same way get_operational_series mints ELEC.<KEY>.<facets>.<freq>. A minted id is
PERMANENT once written to the lake: changing a scheme later orphans every row already
stored under the old one. See pipelines/eia/CLAUDE.md."""

from __future__ import annotations

from typing import Any

# Balancing authorities, named -- never selected by index.
ERCOT = "ERCO"
PJM = "PJM"
MISO = "MISO"
SPP = "SWPP"
CAISO = "CISO"
NYISO = "NYIS"
ISNE = "ISNE"
LOWER_48 = "US48"

# Deliberately 8 of EIA's 65 Lower-48 balancing authorities, not all of them. Hourly data
# has no daily or monthly rollup on these routes, so 65 BAs x 3 datasets is roughly 8M
# rows a year -- load-research granularity the spec explicitly rejects ("Do not ingest
# sub-regional demand ... it is granular load research, not gas-demand signal"). These
# are the large gas-burning markets plus a national aggregate. Widening this list is a
# constant edit; record the change in CLAUDE.md so coverage stays legible.
RTO_RESPONDENTS: list[str] = [ERCOT, PJM, MISO, SPP, CAISO, NYISO, ISNE, LOWER_48]

# region-data `type` codes -- REPLACE WITH TASK 0's DUMP.
DEMAND = "D"
DEMAND_FORECAST = "DF"
NET_GENERATION = "NG"
TOTAL_INTERCHANGE = "TI"
REGION_TYPES: list[str] = [DEMAND, DEMAND_FORECAST, NET_GENERATION, TOTAL_INTERCHANGE]

# fuel-type-data `fueltype` codes -- REPLACE WITH TASK 0's DUMP.
NATURAL_GAS = "NG"
COAL = "COL"
NUCLEAR = "NUC"
WIND = "WND"
SOLAR = "SUN"
HYDRO = "WAT"
OTHER = "OTH"
FUEL_TYPES: list[str] = [NATURAL_GAS, COAL, NUCLEAR, WIND, SOLAR, HYDRO, OTHER]

HOURLY = "hourly"
_FREQ_SUFFIX = "H"

INTERCHANGE_MODE = "grid_interchange"


def region_series_id(row: dict[str, Any]) -> str:
    """RTO.REGION.<respondent>.<type>.H -- e.g. RTO.REGION.ERCO.D.H."""
    return f"RTO.REGION.{row['respondent']}.{row['type']}.{_FREQ_SUFFIX}"


def fuel_series_id(row: dict[str, Any]) -> str:
    """RTO.FUEL.<respondent>.<fueltype>.H -- e.g. RTO.FUEL.PJM.NG.H.

    The REGION/FUEL segment is what keeps these apart from region_series_id's output:
    both routes carry a `respondent`, and `type=NG` (net generation) collides with
    `fueltype=NG` (natural gas) on the raw facet values alone. Without the segment a
    fuel-mix value would overwrite a net-generation value in the lake, silently."""
    return f"RTO.FUEL.{row['respondent']}.{row['fueltype']}.{_FREQ_SUFFIX}"


def respondent_geo(row: dict[str, Any]) -> str:
    """The balancing authority is the geography for these routes -- there is no
    `area-name` field to normalise, so `_normalise_geo` is never involved."""
    return str(row["respondent"])
```

- [ ] **Step 4: Run green**

Run: `.venv/Scripts/pytest.exe tests/test_eia_rto.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pipelines/eia/rto.py tests/test_eia_rto.py
git commit -m "feat(eia): balancing-authority constants and minted RTO series-id scheme"
```

---

### Task 3: Hourly demand and net generation by region

**Files:**
- Create: `pipelines/eia/pull_rto_demand.py`
- Test: `tests/test_eia_rto_demand.py`

**Interfaces:**
- Consumes: `EIAClient.get_facet_series` (Task 1); `RTO_RESPONDENTS`, `REGION_TYPES`, `region_series_id`, `respondent_geo`, `HOURLY` (Task 2).
- Produces: `TRAILING_DAYS: int`, `pull_demand(client: EIAClient, days: int = TRAILING_DAYS) -> pd.DataFrame`, `run(days: int) -> None`, `main() -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eia_rto_demand.py
from __future__ import annotations

import pytest
from core.schemas import validate_ts_long

from pipelines.eia import pull_rto_demand
from pipelines.eia.rto import ERCOT, PJM


@pytest.mark.vcr
def test_demand_returns_valid_ts_long_for_the_two_blocked_markets() -> None:
    df = pull_rto_demand.pull_demand(pull_rto_demand.EIAClient(), days=2)

    validate_ts_long(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    assert set(df["freq"]) == {"hourly"}
    # ERCOT and PJM are the entire justification for this pipeline -- gridstatus cannot
    # reach either. If they come back empty the pull is pointless, and an empty frame
    # would otherwise pass every other assertion here.
    assert ERCOT in set(df["geo"])
    assert PJM in set(df["geo"])


@pytest.mark.vcr
def test_series_ids_are_minted_from_the_row_not_guessed() -> None:
    df = pull_rto_demand.pull_demand(pull_rto_demand.EIAClient(), days=2)

    assert all(sid.startswith("RTO.REGION.") for sid in df["series_id"])
    # Every row's id must be reconstructible from its own geo -- proving the id was
    # minted from the row and not from a positional guess.
    for _, row in df.head(50).iterrows():
        assert row["series_id"].split(".")[2] == row["geo"]


def test_trailing_window_is_bounded() -> None:
    # Hourly routes have no monthly rollup to fall back on, so an unbounded pull is the
    # row-volume problem plan 31B's Decision A exists to prevent. main() must never
    # request full history.
    assert pull_rto_demand.TRAILING_DAYS <= 7
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/pytest.exe tests/test_eia_rto_demand.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipelines.eia.pull_rto_demand'`

- [ ] **Step 3: Write `pipelines/eia/pull_rto_demand.py`**

```python
"""Spec 31 item 2: hourly demand, demand forecast, net generation and total interchange
by balancing authority.

ERCOT and PJM are the point. pipelines/gridstatus_iso/ cannot reach either -- ERCOT is
behind Incapsula bot protection and PJM needs a Data Miner 2 key -- and they are the two
markets where gas-fired generation most moves the gas book.

electricity/rto/region-data has no `series` facet (400 on facet/series, confirmed live),
so this uses the client's facet-dict path and mints its own series ids via
pipelines/eia/rto.py. Hourly only: no daily or monthly rollup exists, so every run is
bounded to a trailing window."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

import pandas as pd
from core.failures import failure_scope
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient
from pipelines.eia.rto import (
    HOURLY,
    REGION_TYPES,
    RTO_RESPONDENTS,
    region_series_id,
    respondent_geo,
)

REGION_ROUTE = "electricity/rto/region-data"
DATA_KEY = "value"

# A daily schedule re-pulls three days so the previous two days' revisions land too.
# write_ts_long de-duplicates on revision_date, so re-pulling an unchanged day is a
# no-op rather than a duplicate -- unlike flows, which needs an explicit replace_window
# (see pull_rto_interchange.py).
TRAILING_DAYS = 3


def _hour_bounds(days: int) -> tuple[str, str]:
    """EIA's hourly routes take start/end as YYYY-MM-DDTHH (confirmed live, Task 0)."""
    now = datetime.now(UTC)
    return (now - timedelta(days=days)).strftime("%Y-%m-%dT%H"), now.strftime("%Y-%m-%dT%H")


def pull_demand(client: EIAClient, days: int = TRAILING_DAYS) -> pd.DataFrame:
    """One route's rows. Separate from main so a cassette test can exercise it directly."""
    start, end = _hour_bounds(days)
    return client.get_facet_series(
        route=REGION_ROUTE,
        data_key=DATA_KEY,
        facets={"respondent": RTO_RESPONDENTS, "type": REGION_TYPES},
        frequency=HOURLY,
        series_id=region_series_id,
        geo=respondent_geo,
        start=start,
        end=end,
    )


def run(days: int) -> None:
    with failure_scope("eia.pull_rto_demand"):
        df = pull_demand(EIAClient(), days=days)
        if df.empty:
            print("no RTO region rows pulled", flush=True)
            return
        write_ts_long(df, source="eia")
        print(
            f"wrote {len(df)} RTO region rows across {df['geo'].nunique()} "
            f"balancing authorities ({days}d window)",
            flush=True,
        )


def main() -> None:
    run(TRAILING_DAYS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pull EIA Grid Monitor region data.")
    parser.add_argument(
        "--days",
        type=int,
        default=TRAILING_DAYS,
        help=f"trailing window in days (default {TRAILING_DAYS}); pass a larger value "
        "once, to backfill",
    )
    run(parser.parse_args().days)
```

**`main()` must take no arguments** — `infra/run_scheduled.py` imports the module and calls
`main()` with none. A previous EIA pull (`pull_prices_weekly.py`) silently no-opped when
run as a module because of exactly this; keep `run(days)` as the parameterised entry point
and `main()` as the zero-argument scheduler entry.

- [ ] **Step 4: Record the cassette and run green**

Run: `.venv/Scripts/pytest.exe tests/test_eia_rto_demand.py -v --record-mode=once`
Then replay: `.venv/Scripts/pytest.exe tests/test_eia_rto_demand.py -v`
Expected: 3 passed.

**Inspect the cassette before committing.** EIA authenticates by `api_key` query parameter
**and echoes it back in response bodies**; `tests/conftest.py` scrubs both. Confirm no real
key survives in either place.

**Expect a replay failure on the first try, and fix it in the test, not the module.**
`_hour_bounds` calls `datetime.now`, so the recorded request URL carries fixed timestamps
that will not match on replay. Fix by relaxing this cassette's vcr `match_on` to method and
path (dropping the query string), or by freezing time in the test — and write a one-line
comment in the test saying which and why. Do not make the pull module take a clock
parameter purely to satisfy a cassette.

- [ ] **Step 5: Commit**

```bash
git add pipelines/eia/pull_rto_demand.py tests/test_eia_rto_demand.py tests/cassettes/test_eia_rto_demand/
git commit -m "feat(eia): hourly demand and net generation by balancing authority"
```

---

### Task 4: Hourly generation by fuel type

**Files:**
- Create: `pipelines/eia/pull_rto_fuel_mix.py`
- Test: `tests/test_eia_rto_fuel_mix.py`

**Interfaces:**
- Consumes: `EIAClient.get_facet_series` (Task 1); `RTO_RESPONDENTS`, `FUEL_TYPES`, `NATURAL_GAS`, `fuel_series_id`, `respondent_geo`, `HOURLY` (Task 2).
- Produces: `TRAILING_DAYS: int`, `pull_fuel_mix(client: EIAClient, days: int = TRAILING_DAYS) -> pd.DataFrame`, `run(days: int) -> None`, `main() -> None`.

**Declare `_hour_bounds` locally rather than importing Task 3's private helper.** A
leading-underscore name is module-private by convention here; cross-importing one couples
two pull modules that are otherwise independent, and the function is three lines.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eia_rto_fuel_mix.py
from __future__ import annotations

import pytest
from core.schemas import validate_ts_long

from pipelines.eia import pull_rto_fuel_mix
from pipelines.eia.rto import ERCOT, NATURAL_GAS, PJM


@pytest.mark.vcr
def test_fuel_mix_returns_valid_ts_long() -> None:
    df = pull_rto_fuel_mix.pull_fuel_mix(pull_rto_fuel_mix.EIAClient(), days=2)

    validate_ts_long(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    assert ERCOT in set(df["geo"])
    assert PJM in set(df["geo"])


@pytest.mark.vcr
def test_gas_fired_generation_is_present_for_both_target_markets() -> None:
    # Gas-fired generation in ERCOT and PJM is the actual gas-demand signal this whole
    # item exists to capture. Everything else here is context.
    df = pull_rto_fuel_mix.pull_fuel_mix(pull_rto_fuel_mix.EIAClient(), days=2)

    gas_ids = {f"RTO.FUEL.{ba}.{NATURAL_GAS}.H" for ba in (ERCOT, PJM)}
    assert gas_ids <= set(df["series_id"]), (
        f"missing gas-fired generation for: {gas_ids - set(df['series_id'])}"
    )


@pytest.mark.vcr
def test_fuel_ids_never_collide_with_region_ids() -> None:
    # `type=NG` (net generation) and `fueltype=NG` (natural gas) are the same two
    # characters on different routes. Without the FUEL/REGION segment one would
    # overwrite the other in the lake with nothing raised.
    df = pull_rto_fuel_mix.pull_fuel_mix(pull_rto_fuel_mix.EIAClient(), days=2)
    assert all(sid.startswith("RTO.FUEL.") for sid in df["series_id"])
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/pytest.exe tests/test_eia_rto_fuel_mix.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipelines.eia.pull_rto_fuel_mix'`

- [ ] **Step 3: Write `pipelines/eia/pull_rto_fuel_mix.py`**

```python
"""Spec 31 item 2: hourly generation by fuel type, per balancing authority.

Gas-fired generation in ERCOT and PJM is the gas-demand signal this item exists for --
coal-to-gas switching sets a floor and ceiling on power-sector gas burn, and these are the
two markets pipelines/gridstatus_iso/ cannot reach.

electricity/rto/fuel-type-data has no `series` facet (400 on facet/series, confirmed
live); facets are respondent+fueltype. Hourly only, so every run is bounded."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

import pandas as pd
from core.failures import failure_scope
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient
from pipelines.eia.rto import (
    FUEL_TYPES,
    HOURLY,
    RTO_RESPONDENTS,
    fuel_series_id,
    respondent_geo,
)

FUEL_ROUTE = "electricity/rto/fuel-type-data"
DATA_KEY = "value"
TRAILING_DAYS = 3


def _hour_bounds(days: int) -> tuple[str, str]:
    """EIA's hourly routes take start/end as YYYY-MM-DDTHH (confirmed live, Task 0)."""
    now = datetime.now(UTC)
    return (now - timedelta(days=days)).strftime("%Y-%m-%dT%H"), now.strftime("%Y-%m-%dT%H")


def pull_fuel_mix(client: EIAClient, days: int = TRAILING_DAYS) -> pd.DataFrame:
    start, end = _hour_bounds(days)
    return client.get_facet_series(
        route=FUEL_ROUTE,
        data_key=DATA_KEY,
        facets={"respondent": RTO_RESPONDENTS, "fueltype": FUEL_TYPES},
        frequency=HOURLY,
        series_id=fuel_series_id,
        geo=respondent_geo,
        start=start,
        end=end,
    )


def run(days: int) -> None:
    with failure_scope("eia.pull_rto_fuel_mix"):
        df = pull_fuel_mix(EIAClient(), days=days)
        if df.empty:
            print("no RTO fuel-mix rows pulled", flush=True)
            return
        write_ts_long(df, source="eia")
        print(
            f"wrote {len(df)} RTO fuel-mix rows across {df['geo'].nunique()} "
            f"balancing authorities ({days}d window)",
            flush=True,
        )


def main() -> None:
    run(TRAILING_DAYS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pull EIA Grid Monitor fuel-type data.")
    parser.add_argument("--days", type=int, default=TRAILING_DAYS)
    run(parser.parse_args().days)
```

- [ ] **Step 4: Record the cassette and run green**

Run: `.venv/Scripts/pytest.exe tests/test_eia_rto_fuel_mix.py -v --record-mode=once` then replay.
Expected: 3 passed. Same cassette caveats as Task 3 Step 4 (key scrub, and the
`datetime.now` query mismatch).

- [ ] **Step 5: Commit**

```bash
git add pipelines/eia/pull_rto_fuel_mix.py tests/test_eia_rto_fuel_mix.py tests/cassettes/test_eia_rto_fuel_mix/
git commit -m "feat(eia): hourly generation by fuel type per balancing authority"
```

---

### Task 5: Inter-BA interchange into the `flows` schema

**Files:**
- Create: `pipelines/eia/pull_rto_interchange.py`
- Test: `tests/test_eia_rto_interchange.py`

**Interfaces:**
- Consumes: `EIAClient.get_facet_flows` (Task 1); `RTO_RESPONDENTS`, `INTERCHANGE_MODE`, `HOURLY` (Task 2); `core.storage.write_flows`.
- Produces: `TRAILING_DAYS: int`, `pull_interchange(client: EIAClient, days: int = TRAILING_DAYS) -> pd.DataFrame`, `run(days: int) -> None`, `main() -> None`.

**This is the task with the subtle failure mode.** `flows` has no `revision_date` column,
so plain de-dup cannot tell a revised value from a genuinely new row — both differ, so both
are kept, **silently double-counting downstream**. A trailing-window re-pull therefore MUST
pass `replace_window`. `write_ts_long` does not have this problem, which is why Tasks 3 and
4 say nothing about it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eia_rto_interchange.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import pytest
from core.schemas import validate_flows

from pipelines.eia import pull_rto_interchange
from pipelines.eia.rto import ERCOT


@pytest.mark.vcr
def test_interchange_returns_valid_flows_rows() -> None:
    df = pull_rto_interchange.pull_interchange(pull_rto_interchange.EIAClient(), days=2)

    validate_flows(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    assert set(df["mode"]) == {"grid_interchange"}
    # Corridors are read off each row's own fromba/toba, so from and to must differ.
    assert not (df["from_node"] == df["to_node"]).any()


@pytest.mark.vcr
def test_ercot_appears_as_a_real_corridor_endpoint() -> None:
    df = pull_rto_interchange.pull_interchange(pull_rto_interchange.EIAClient(), days=2)
    assert ERCOT in set(df["from_node"]) | set(df["to_node"])


def test_run_passes_a_replace_window_to_write_flows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The load-bearing test of this task. flows has no revision_date, so a re-pulled
    # trailing window that does NOT replace its old rows keeps both the old and the
    # revised value -- they differ, so de-dup keeps both -- and every downstream sum
    # double-counts, with nothing raised anywhere. Assert the window is actually passed.
    captured: dict[str, Any] = {}

    def _fake_write(df: pd.DataFrame, source: str, replace_window: Any = None) -> None:
        captured["source"] = source
        captured["replace_window"] = replace_window

    monkeypatch.setattr(pull_rto_interchange, "write_flows", _fake_write)
    monkeypatch.setattr(
        pull_rto_interchange,
        "pull_interchange",
        lambda client, days: pd.DataFrame(
            {
                "source": ["eia"],
                "from_node": ["ERCO"],
                "to_node": ["SWPP"],
                "value": [120.0],
                "unit": ["megawatthours"],
                "ts": pd.to_datetime([datetime.now(UTC).replace(tzinfo=None)]),
                "mode": ["grid_interchange"],
            }
        ),
    )

    pull_rto_interchange.run(days=3)

    assert captured["source"] == "eia"
    window = captured["replace_window"]
    assert window is not None, "a flows re-pull without a replace_window double-counts"
    start, end = window
    assert end - start >= timedelta(days=3)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/pytest.exe tests/test_eia_rto_interchange.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipelines.eia.pull_rto_interchange'`

- [ ] **Step 3: Write `pipelines/eia/pull_rto_interchange.py`**

```python
"""Spec 31 item 2: hourly interchange between balancing authorities, as `flows` rows.

The spec calls this out specifically: interchange-data maps onto the `flows` schema and
the corridor pattern pipelines/eia/corridors.py already establishes. Unlike the crude PADD
corridors, though, the corridor is not looked up from a series id -- this route carries
`fromba` and `toba` on every row, so each row names its own corridor.

electricity/rto/interchange-data has no `series` facet (400 on facet/series, confirmed
live) and, uniquely among the three rto/* routes, no `type` or `fueltype` facet either --
just fromba+toba."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

import pandas as pd
from core.failures import failure_scope
from core.storage import write_flows

from pipelines.eia.client import EIAClient
from pipelines.eia.rto import HOURLY, INTERCHANGE_MODE, RTO_RESPONDENTS

INTERCHANGE_ROUTE = "electricity/rto/interchange-data"
DATA_KEY = "value"
TRAILING_DAYS = 3


def _window(days: int) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    return now - timedelta(days=days), now


def _hour_bounds(days: int) -> tuple[str, str]:
    start, end = _window(days)
    return start.strftime("%Y-%m-%dT%H"), end.strftime("%Y-%m-%dT%H")


def pull_interchange(client: EIAClient, days: int = TRAILING_DAYS) -> pd.DataFrame:
    """Filtered by `fromba` only. Every corridor OUT of the chosen BAs is returned, and
    each row names its own counterparty in `toba` -- so a corridor to a BA outside
    RTO_RESPONDENTS is still captured, which is wanted: ERCOT's ties to its neighbours
    are part of the ERCOT picture even when the neighbour is not itself ingested."""
    start, end = _hour_bounds(days)
    return client.get_facet_flows(
        route=INTERCHANGE_ROUTE,
        data_key=DATA_KEY,
        facets={"fromba": RTO_RESPONDENTS},
        frequency=HOURLY,
        mode=INTERCHANGE_MODE,
        start=start,
        end=end,
    )


def run(days: int) -> None:
    with failure_scope("eia.pull_rto_interchange"):
        df = pull_interchange(EIAClient(), days=days)
        if df.empty:
            print("no RTO interchange rows pulled", flush=True)
            return
        # REQUIRED, not optional. flows has no revision_date column, so write_flows
        # cannot tell a revised value from a new row -- it would keep both, and every
        # downstream sum would double-count, silently. Pass the exact window re-pulled
        # so its stale rows are replaced outright. write_flows scopes the replacement to
        # this frame's own pairs, so a pair that failed this run keeps its prior data.
        window_start, window_end = _window(days)
        write_flows(
            df,
            source="eia",
            replace_window=(
                window_start.replace(tzinfo=None),
                window_end.replace(tzinfo=None),
            ),
        )
        pairs = df[["from_node", "to_node"]].drop_duplicates()
        print(
            f"wrote {len(df)} RTO interchange rows across {len(pairs)} corridors "
            f"({days}d window)",
            flush=True,
        )


def main() -> None:
    run(TRAILING_DAYS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pull EIA Grid Monitor interchange data.")
    parser.add_argument("--days", type=int, default=TRAILING_DAYS)
    run(parser.parse_args().days)
```

**On the `tzinfo=None`:** `core.storage._normalise_datetime_tz` normalises the frame's own
`ts` column, and `replace_window` is then compared against those normalised timestamps.
**Verify this when you implement it** — if the comparison raises a tz-aware/tz-naive
mismatch, that is this line, and the fix belongs here, not in `core/storage.py`, which
`pipelines/entsog/` and `pipelines/entsoe/` also depend on.

- [ ] **Step 4: Record the cassette and run green**

Run: `.venv/Scripts/pytest.exe tests/test_eia_rto_interchange.py -v --record-mode=once` then replay.
Expected: 3 passed. Same cassette caveats as Task 3 Step 4.

- [ ] **Step 5: Commit**

```bash
git add pipelines/eia/pull_rto_interchange.py tests/test_eia_rto_interchange.py tests/cassettes/test_eia_rto_interchange/
git commit -m "feat(eia): inter-BA interchange as flows rows"
```

---

### Task 6: Schedule, backfill, and the final gate

**Files:**
- Modify: `infra/run_scheduled.py`
- Modify: `pipelines/eia/CLAUDE.md`
- Modify: `specs/00_INDEX.md`

- [ ] **Step 1: Register all three pulls in the daily group**

In `infra/run_scheduled.py`, add to the `daily` group:

```python
        ("eia_rto_demand", "pipelines.eia.pull_rto_demand"),
        ("eia_rto_fuel_mix", "pipelines.eia.pull_rto_fuel_mix"),
        ("eia_rto_interchange", "pipelines.eia.pull_rto_interchange"),
```

**Check `git status` first** — a concurrent session may own other parts of that file. Add
only these three lines. If their edit conflicts, **report it rather than resolving it.**

Run: `.venv/Scripts/pytest.exe tests/test_run_scheduled.py -q`

- [ ] **Step 2: Backfill once, for real**

```
.venv/Scripts/python.exe -m pipelines.eia.pull_rto_demand --days 90
.venv/Scripts/python.exe -m pipelines.eia.pull_rto_fuel_mix --days 90
.venv/Scripts/python.exe -m pipelines.eia.pull_rto_interchange --days 90
```

Record the **real** row counts and roughly how long each took. `main()` raises
`PartialFailureError` on any recorded failure, so a non-zero exit with rows written is
legitimate — note it rather than hiding it.

**If any of the three takes more than a few minutes or writes far more rows than Task 0
Step 3 predicted, stop and report it.** Decision A's whole purpose is that this stays
proportionate; a backfill that blows past the estimate means the scope needs narrowing
before it is scheduled, not after.

- [ ] **Step 3: Confirm the data answers the question the item exists for**

```python
from core.storage import read_flows, read_ts_long
from pipelines.eia.rto import ERCOT, NATURAL_GAS, PJM

for ba in (ERCOT, PJM):
    gas = read_ts_long(series_ids=[f"RTO.FUEL.{ba}.{NATURAL_GAS}.H"], source="eia")
    region = read_ts_long(series_prefix=f"RTO.REGION.{ba}.", source="eia")
    print(ba, "gas-fired rows:", len(gas), "| region rows:", len(region))
    if not gas.empty:
        print("   gas burn span:", gas["ts"].min(), "->", gas["ts"].max(),
              "| unit:", set(gas["unit"]))

flows = read_flows(source="eia")
grid = flows[flows["mode"] == "grid_interchange"]
print("interchange rows:", len(grid), "| corridors:",
      len(grid[["from_node", "to_node"]].drop_duplicates()))
```

**ERCOT and PJM gas-fired generation must both be non-empty.** They are the entire
justification for this item; if either is empty, that is the one outcome that makes this
plan pointless — report it rather than papering over it. Note the reads are narrowed by
`source=` and `series_prefix=`, per the global constraints.

- [ ] **Step 4: Re-run the interchange pull and prove it did not double-count**

The single highest-value check in this plan, because the failure it guards is silent.

```python
from core.storage import read_flows
print("rows before:", len(read_flows(source="eia")))
# now re-run: .venv/Scripts/python.exe -m pipelines.eia.pull_rto_interchange --days 3
print("rows after :", len(read_flows(source="eia")))
```

Run the pull twice in a row over the same window. **The row count must not grow by the size
of the window on the second run.** A small delta from genuinely new hours is expected; a
delta equal to three days of corridors means `replace_window` is not working and Task 5's
guard has failed.

- [ ] **Step 5: Full suite, lint, typecheck**

`.venv/Scripts/pytest.exe`, then `.venv/Scripts/ruff.exe check .` and
`.venv/Scripts/mypy.exe core pipelines infra`.

A concurrent session works in this repo. If a test fails in a file this plan never touched,
**report it, do not fix it.**

- [ ] **Step 6: Record real outcomes**

Append to `pipelines/eia/CLAUDE.md`: the real backfill row counts, the BA coverage actually
ingested (8 of 65, and why), the minted series-id schemes verbatim (`RTO.REGION.*` and
`RTO.FUEL.*`) with the note that they are **permanent once written**, the `NG` collision
and how the REGION/FUEL segment prevents it, the real interchange corridor list, and the
double-count check's result.

Update `specs/00_INDEX.md`'s Spec 31 row to record that item 2 shipped, what its coverage
is and is not, and that items 4, 5 and 6 remain — in the plain-spoken register the Spec
18–21 rows use.

- [ ] **Step 7: Commit**

```bash
git add infra/run_scheduled.py pipelines/eia/CLAUDE.md specs/00_INDEX.md
git commit -m "docs(spec31b): schedule the Grid Monitor pulls and record real outcomes"
```

---

## Page sections — deliberately not a task in this plan

Spec 31 says its items feed "sections on existing pages; no new page". **This plan contains
no dashboard task, by decision.**

`apps/dashboard/**` belongs to a concurrent design session migrating all 16 pages to a new
section kit (`card(...)` → `section(...)`, empty branches → `empty_state(...)`, in-page
figure `title=` promoted into the section heading). Plan 31A tried to land one additive
section on `02_gas_storage.py` during that migration; the lane owner declined, correctly —
an additive `card(...)` section would have collided with a full-file rewrite, and a new
chart backed by a computed ratio is a *feature* being reviewed inside a pure-restyle diff
where nobody would think to look for numeric errors.

**The right sequence is: data first, page section after the migration, built with the
section kit.** The data reaching the lake is independently valuable — the same "known gap,
deliberate" shape 31A shipped under.

When the migration has landed, the section worth building from this plan's data is a
**gas-fired generation panel for ERCOT and PJM**: `RTO.FUEL.{ERCO,PJM}.NG.H` against net
generation from `RTO.REGION.{ERCO,PJM}.NG.H`, giving gas's share of the stack in the two
markets the rest of the lake cannot see. Hand that description to whoever owns
`apps/dashboard/**` at the time rather than building it here.

---

## Self-Review

**Spec coverage (item 2):** "ingest demand, generation-by-fuel and interchange" → Tasks 3,
4 and 5 respectively. "Verify which shape each `electricity/rto/*` route uses before writing
pull code" → plan 31A's Task 0 established the shapes; this plan's Task 0 establishes the
facet values, and Task 1 builds the query path those shapes require. "`interchange-data`
also maps onto the `flows` schema and the `get_flows` corridor pattern" → Task 5, via
`get_facet_flows`. "**Do not** ingest sub-regional demand for the 8 BAs that offer it" →
honoured: no sub-regional facet is ever requested, and Decision A scopes to 8 whole BAs.
"Register at the cadence the data actually supports" → Decision B and Task 6 Step 1.
Acceptance criteria (live verification first, cassette tests per route, no guessed codes,
units unconverted, reads narrowed, `core/schemas.py` unchanged, session ends green) →
Task 0, Tasks 3–5, and Task 6 Steps 3 and 5.

**Deliberate gap:** the page section, argued above.

**Type consistency:** `get_facet_series` and `get_facet_flows` both take
`facets: dict[str, list[str]]` and `data_key: str`, and both delegate to
`_fetch_facet_rows` with the same signature. `region_series_id`, `fuel_series_id` and
`respondent_geo` are all `(dict[str, Any]) -> str`, matching the
`Callable[[dict[str, Any]], str]` that `get_facet_series` declares. `TRAILING_DAYS` is an
`int` in all three pull modules, and `pull_*(client, days: int = TRAILING_DAYS) ->
pd.DataFrame`, `run(days: int) -> None`, `main() -> None` is one shape across all three —
`main()` deliberately zero-argument because `infra/run_scheduled.py` calls it that way.

**Risk to watch:** every `type` and `fueltype` code in Task 2 is a **placeholder**. Task 0
replaces them, and its findings take precedence over anything written here — the same
discipline that caught three plan defects in Spec 30 and two spec errors in 31A. The second
risk is the cassette/`datetime.now` interaction flagged in Task 3 Step 4: it will bite on
first replay, and the fix belongs in the test's vcr configuration, not in the pull module.
