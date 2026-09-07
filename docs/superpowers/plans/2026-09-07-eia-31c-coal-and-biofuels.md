# Spec 31C — Coal and Biofuels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close Spec 31's three remaining coverage gaps — weekly ethanol production, biofuels capacity and feedstocks, and power-sector coal — the last of which creates `pipelines/coal/`, the first new pipeline package since Spec 29.

**Architecture:** Items 6 and 5 are ordinary series-based routes on the existing `EIAClient.get_series`, so they are two small `pull_*.py` modules in `pipelines/eia/` following `pull_gas_consumption.py`'s shape. Item 4 is different in three ways at once — it is **not** series-based, it is the first `source="coal"` dataset, and it is the first member of a new package — so it comes last and carries its own `CLAUDE.md`. No schema change.

**Tech Stack:** Python 3.12, `pipelines/eia/client.py`, `core.storage.write_ts_long`, `core.failures`, pandas. Tests: pytest + vcrpy cassettes.

**Spec:** `specs/31_eia-coverage-extensions.md` (items 4, 5 and 6)

**Scope note:** This plan covers items **4, 5 and 6**. Items 1 and 3 shipped in plan 31A; item 2 is plan 31B. Every item in Spec 31 is independent by design.

---

## Build order, and the one cross-plan dependency

**The tasks are ordered easiest-and-most-independent first, deliberately.** Items 6 and 5
use `get_series`, which has existed since Spec 02 and needs nothing new. Item 4 needs a
query shape that does not exist yet.

> **Task 3 (coal) depends on plan 31B's Task 1**, which adds
> `EIAClient.get_facet_series` — the generalised facet-dict query path.
> `coal/consumption-and-quality` is the **fourth** non-series route (400 on `facet/series`,
> confirmed live by plan 31A's Task 0), alongside the three `electricity/rto/*` routes.
>
> **If plan 31B has not landed when you reach Task 3, do not build a second, parallel
> facet-dict method here.** Two near-identical private fetchers on one client is exactly
> the duplication the review rubric calls an Important finding. Either run 31B's Task 1
> first, or stop after Task 2 and report that items 5 and 6 shipped and item 4 is waiting
> on the shared client work.
>
> **Tasks 1 and 2 have no such dependency and ship on their own.** That is why they come
> first: this plan delivers two of its three items even if the coal task never runs.

---

## What plan 31A's Task 0 already established — binding, do not re-derive

Recorded in `pipelines/eia/CLAUDE.md` under "Spec 31 routes — confirmed live 2026-09-06":

| Route | Series facet? | Count | Frequency | geo | Item |
|---|---|---|---|---|---|
| `petroleum/pnp/wprode` | yes | **6** | `weekly` (confirmed live), also `four-week-average` | `US` clean on the sample checked | 6 |
| `petroleum/pnp/capbio` | yes | **3** | `monthly` only | `US` clean, all national | 5 |
| `petroleum/pnp/feedbiofuel` | yes | **26** | `monthly` only | `US` clean, all national | 5 |
| `coal/consumption-and-quality` | **no — 400** | n/a | `quarterly` / `annual` only | not checked | 4 |

Three specifics that shape this plan:

1. **`wprode` carries all five PADDs, not four.** The spec originally said "National and
   PADD1–4"; plan 31A corrected it live — 6 series, `W_EPOOXE_YOP_NUS_MBBLD` plus `_R10_`
   through `_R50_`. **The spec text is already corrected**; this plan must ingest all six.
   Under-ingesting PADD5 was the exact cost 31A's Task 0 flagged for this plan.

2. **Only `wprode`'s *national* code had its `geo` checked.** The five PADD codes were
   never sampled. `_normalise_geo` maps `"PADD 1"` → `"PADD1"`, so they are *expected* to
   resolve cleanly with no `geo_map` — but "expected" is what plan 31A's Task 0 refused to
   accept about `stor/cap`, and it was right to (that route returns the literal `"NA"`).
   **Task 0 of this plan checks the PADD codes.**

3. **`coal/consumption-and-quality` has facets `location`+`sector` and seven data keys** —
   `receipts`, `consumption`, `stocks`, `price`, `heat-content`, `sulfur-content`,
   `ash-content`. The spec wants power-sector coal specifically, so `sector` is filtered,
   not enumerated.

---

## Global Constraints

Copied from the spec, plan 31A and root `CLAUDE.md`. Every task's requirements implicitly
include this section.

- **Never guess a series code or a facet value.** Discover every one live in Task 0. Spec
  30's discovery found a route its own plan had written off; Spec 17 shipped a wrong ticker
  that only a live lookup caught; plan 31A's Task 0 found two errors in the spec itself.
- **A wrong `frequency` returns empty, not an error** on some routes. `weekly` for
  `wprode`, `monthly` for `capbio`/`feedbiofuel`, `quarterly` for coal — all confirmed or
  to be confirmed live.
- **EIA publishes real `value: null` rows.** `get_series` and `get_facet_series` skip them
  and print the dropped count. Do not reintroduce an unconditional `float()`.
- **Units stored exactly as EIA publishes them, never converted at ingest** — `$/short
  ton`, `MMBtu`, `thousand barrels per day`, `Mgal`, `Mlbs`. Conversion belongs in `core/`.
  This matters more here than anywhere else in Spec 31: coal alone carries five different
  units across its seven data keys.
- **Series IDs stay in EIA's native form** (`W_EPOOXE_YOP_NUS_MBBLD` style) for items 5 and
  6. Coal's route supplies none, so this plan **mints them deterministically and documents
  the scheme** — precedent: `get_operational_series`'s
  `ELEC.<DATA_KEY>.<fueltypeid>-<location>-<sectorid>.<freq>` and `generator_fuel_series_id`
  in `pipelines/eia/pull_prices.py`. **A minted id is permanent once written.**
- **Never select a series by list index.** Spec 30 shipped `GENERATOR_FUEL[0]`, where
  reordering a constant would have plotted the wrong unit against a price axis, raising
  nothing. Use named constants.
- **Never read the lake unbounded.** `read_ts_long` takes `source` and `series_prefix`;
  `source` narrows the parquet glob itself. An unbounded read grew until it failed as a
  `pickle.dumps` error inside `st.cache_data`, pointing nowhere near the read.
- **Cycle a palette by index, never `zip(..., strict=False)`** against a fixed tuple.
- `source="eia"` for items 5 and 6. **Item 4 uses `source="coal"`** — see Task 3's
  Decision C, which is not a formality: the client currently hardcodes the source column.
- Per-route resilience via `core.failures`; a wholly failed run must raise so the exit
  status is honest.
- British English; `from __future__ import annotations`; typed throughout.
- Repo venv: `.venv/Scripts/python.exe`, `pytest.exe`, `ruff.exe`, `mypy.exe`. Bare
  commands are **not** on PATH.
- **`apps/dashboard/**` and `core/theme.py` belong to a concurrent design session.** This
  plan contains no dashboard task — see "Page sections" at the foot of this plan.
- **Stage explicitly, never `git add -A`.** Name every file on the `git add` line.

---

### Task 0: Discover the real codes and the coal query shape — no pull code

**No pull code, no tests** — the deliverable is recorded findings.

**Files:**
- Modify: `pipelines/eia/CLAUDE.md` (append a "Spec 31C routes" section)

**Interfaces:**
- Consumes: `EIAClient.list_series(route)` (exists).
- Produces: the real series codes and facet values Tasks 1–3 code against.

- [ ] **Step 1: Dump the three series-based routes in full**

Throwaway script, do **not** commit. All three are small enough to print entirely — 3, 26
and 6 series — so print them all rather than a head slice.

```python
from pipelines.eia.client import EIAClient

client = EIAClient()
for route in ("petroleum/pnp/capbio", "petroleum/pnp/feedbiofuel", "petroleum/pnp/wprode"):
    facets = client.list_series(route)
    print(f"\n== {route}: {len(facets)} series")
    for f in facets:
        print("   ", f.get("id"), "|", f.get("name"))
```

Record every id and name. Plan 31A counted 3 / 26 / 6; **if a count differs now, that is a
finding** — record the new count and use it.

- [ ] **Step 2: Check the `wprode` PADD codes' `geo` — the one thing 31A did not verify**

Plan 31A sampled only the national code. Confirm all six.

```python
df = client.get_series(
    route="petroleum/pnp/wprode",
    series=[<all six ids from Step 1>],
    frequency="weekly",
)
print("distinct geo:", sorted(set(df["geo"])))
print("rows per series:")
print(df.groupby("series_id").size())
print("units:", set(df["unit"]))
print(df[["series_id", "ts", "value", "unit", "geo"]].head())
```

**Expected:** `{'US', 'PADD1', ..., 'PADD5'}` via `_normalise_geo`'s existing `"PADD "`
prefix rule, so **no `geo_map`**. **If any comes back as the literal `"NA"`**, this route
has the same quirk `natural-gas/stor/cap` and `petroleum/pri/land3` have, and Task 1 needs
an explicit `geo_map` — record which. Record the answer either way, including the negative.

- [ ] **Step 3: Sample `capbio` and `feedbiofuel`**

```python
for route in ("petroleum/pnp/capbio", "petroleum/pnp/feedbiofuel"):
    df = client.get_series(route=route, series=[<two ids from Step 1>], frequency="monthly")
    print(f"\n== {route}: {len(df)} rows, geo={sorted(set(df['geo']))}, units={set(df['unit'])}")
    print("span:", df["ts"].min(), "->", df["ts"].max())
```

Record row counts, spans, units and geo for each. **`feedbiofuel`'s 26 series carry
different feedstocks in different units** (soybean oil, corn oil, used cooking oil, tallow,
canola) — record the distinct unit set, because a chart that plots them on one axis without
checking is the mistake this record exists to prevent.

- [ ] **Step 4: Establish the coal route's facet values and data keys**

This is the route with no `series` facet, so it needs the facet-dict treatment.

```python
import requests
from core.config import settings

BASE = "https://api.eia.gov/v2"
ROUTE = "coal/consumption-and-quality"

meta = requests.get(f"{BASE}/{ROUTE}", params={"api_key": settings.eia_api_key}, timeout=30)
meta.raise_for_status()
body = meta.json()["response"]
print("frequencies:", [f["id"] for f in body.get("frequency", [])])
print("data keys:  ", list(body.get("data", {})))
print("facets:     ", [f["id"] for f in body.get("facets", [])])

for name in ("location", "sector"):
    resp = requests.get(
        f"{BASE}/{ROUTE}/facet/{name}", params={"api_key": settings.eia_api_key}, timeout=30
    )
    resp.raise_for_status()
    facets = resp.json()["response"]["facets"]
    print(f"\n{name}: {len(facets)} values")
    for f in facets[:60]:
        print("   ", f.get("id"), "|", f.get("name"))
```

**Identify the electric-power sector code specifically.** The spec scopes item 4 to "power
sector only" — coal-to-gas switching in US power generation is the single channel by which
coal matters to this book. A sector code that is not the power sector is out of scope.

- [ ] **Step 5: Confirm the coal response's field names on a real data call**

```python
params = {
    "api_key": settings.eia_api_key,
    "frequency": "quarterly",
    "data[0]": "price",
    "facets[location][]": ["US"],
    "facets[sector][]": [<the power-sector code from Step 4>],
    "length": 5,
}
resp = requests.get(f"{BASE}/{ROUTE}/data/", params=params, timeout=30)
resp.raise_for_status()
for row in resp.json()["response"]["data"]:
    print(row)
```

Record verbatim: every key in a row; what holds the number and what holds its unit
(`price-units`? `units`?); the `period` format for quarterly; whether `location` and
`sector` come back on each row (Task 3 mints series ids from them, so a missing one is a
blocker); and the **unit string for each of the seven data keys** — run the call once per
key, or once with several `data[N]` params, and record all seven.

**Also confirm `US` is a real `location` value.** If the route is state-only with no
national roll-up, Task 3's scope changes and that must be known now.

- [ ] **Step 6: Record the findings**

Append to `pipelines/eia/CLAUDE.md`, following that file's existing style — state what was
confirmed live versus declared, and record negatives:

```markdown
## Spec 31C routes — confirmed live [DATE]

| Route | Series facet? | Count | Codes used | Frequency | geo quirk | Item |
|---|---|---|---|---|---|---|
| petroleum/pnp/wprode | | | | | | 6 |
| petroleum/pnp/capbio | | | | | | 5 |
| petroleum/pnp/feedbiofuel | | | | | | 5 |
| coal/consumption-and-quality | | | | | | 4 |

**wprode PADD geo resolution:** [the distinct geo set, and whether a geo_map is needed]
**feedbiofuel distinct units across all 26 series:** [real set]
**coal facets:** location=[n values, US present? yes/no], sector=[n values]
**coal power-sector code:** [the real code, and its name]
**coal data keys and their unit strings:** [all seven, verbatim]
**coal row field names:** [verbatim key list]  **Value column:** [name]  **Unit column:** [name]
**coal period format:** [e.g. 2026-Q2]
**Routes that failed or returned nothing:** [real list, or "none"]
```

Every bracket replaced with a real value. A committed `[DATE]` is a task failure.

- [ ] **Step 7: Commit**

```bash
git add pipelines/eia/CLAUDE.md
git commit -m "docs(eia): live-discovered routes for Spec 31C"
```

---

### Task 1: Weekly ethanol production — all five PADDs

**Files:**
- Create: `pipelines/eia/pull_ethanol_weekly.py`
- Test: `tests/test_eia_ethanol_weekly.py`
- Modify: `infra/run_scheduled.py`

**Interfaces:**
- Consumes: `EIAClient.get_series(route, series, frequency, geo_map=None) -> pd.DataFrame`; Task 0's codes.
- Produces: `ETHANOL: list[str]`, named per-region constants, `pull_ethanol(client: EIAClient) -> pd.DataFrame`, `main() -> None`.

**Why this is first:** it is the smallest item in Spec 31, uses only what already exists,
and shares the WPSR cadence — so it slots into an existing pull rhythm rather than
inventing one.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eia_ethanol_weekly.py
from __future__ import annotations

import pytest
from core.schemas import validate_ts_long

from pipelines.eia import pull_ethanol_weekly


@pytest.mark.vcr
def test_ethanol_returns_valid_ts_long_for_every_region() -> None:
    df = pull_ethanol_weekly.pull_ethanol(pull_ethanol_weekly.EIAClient())

    validate_ts_long(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    assert set(df["freq"]) == {"weekly"}
    # Every requested region must return rows. A region that silently returns nothing
    # would leave a hole in the blending picture that no error reports.
    assert set(df["series_id"]) == set(pull_ethanol_weekly.ETHANOL)


@pytest.mark.vcr
def test_all_five_padds_are_covered_not_four() -> None:
    # Plan 31A's Task 0 corrected the spec on exactly this: the route carries PADD1-5,
    # and an earlier draft said PADD1-4. Under-ingesting PADD5 (the West Coast) was the
    # named cost of getting this wrong.
    df = pull_ethanol_weekly.pull_ethanol(pull_ethanol_weekly.EIAClient())

    assert len(pull_ethanol_weekly.ETHANOL) == 6, "US plus PADD1-5"
    geos = set(df["geo"])
    for padd in ("PADD1", "PADD2", "PADD3", "PADD4", "PADD5"):
        assert padd in geos, f"{padd} missing -- geo resolved to {sorted(geos)}"
    # Never the literal "NA" this route family returns in area-name on some routes.
    assert "NA" not in geos


def test_regions_are_named_constants_not_positional() -> None:
    # Spec 30 shipped GENERATOR_FUEL[0]; reordering that list would have plotted the
    # wrong unit against a price axis, raising nothing.
    assert pull_ethanol_weekly.US in pull_ethanol_weekly.ETHANOL
    assert pull_ethanol_weekly.PADD5 in pull_ethanol_weekly.ETHANOL
    assert len(set(pull_ethanol_weekly.ETHANOL)) == len(pull_ethanol_weekly.ETHANOL)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/pytest.exe tests/test_eia_ethanol_weekly.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipelines.eia.pull_ethanol_weekly'`

- [ ] **Step 3: Write `pipelines/eia/pull_ethanol_weekly.py`**

Replace the placeholder codes with Task 0's real discoveries. Add a `geo_map` **only if**
Task 0 Step 2 found the `"NA"` quirk; if `area-name` resolves properly, omit it and say so
in the docstring.

```python
"""Spec 31 item 6: weekly ethanol production, national and all five PADDs.

The best trading-frequency proxy for ethanol blending economics, and weekly -- the same
cadence as the WPSR series already in the lake, so it registers in the existing "wpsr"
scheduler group rather than needing a new rhythm.

Plan 31A's Task 0 corrected the spec here, live: this route carries PADD1 THROUGH PADD5
(6 series in total), not PADD1-4 as an earlier draft said. All six are ingested; omitting
PADD5 would silently lose the West Coast. See pipelines/eia/CLAUDE.md."""

from __future__ import annotations

import pandas as pd
from core.failures import failure_scope
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient

# Named, never selected by index -- see this module's test.
US = "W_EPOOXE_YOP_NUS_MBBLD"
PADD1 = "W_EPOOXE_YOP_R10_MBBLD"
PADD2 = "W_EPOOXE_YOP_R20_MBBLD"
PADD3 = "W_EPOOXE_YOP_R30_MBBLD"
PADD4 = "W_EPOOXE_YOP_R40_MBBLD"
PADD5 = "W_EPOOXE_YOP_R50_MBBLD"

ETHANOL: list[str] = [US, PADD1, PADD2, PADD3, PADD4, PADD5]

ETHANOL_ROUTE = "petroleum/pnp/wprode"
# `weekly` confirmed live; the route also declares `four-week-average` and nothing else.
# A wrong frequency here returns empty rather than erroring.
ETHANOL_FREQUENCY = "weekly"


def pull_ethanol(client: EIAClient) -> pd.DataFrame:
    """One route's rows. Separate from main so a cassette test can exercise it directly."""
    return client.get_series(
        route=ETHANOL_ROUTE, series=ETHANOL, frequency=ETHANOL_FREQUENCY
    )


def main() -> None:
    with failure_scope("eia.pull_ethanol_weekly"):
        df = pull_ethanol(EIAClient())
        if df.empty:
            print("no ethanol rows pulled", flush=True)
            return
        write_ts_long(df, source="eia")
        print(
            f"wrote {len(df)} weekly ethanol rows across {df['geo'].nunique()} regions",
            flush=True,
        )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Register in the `wpsr` cadence group**

`infra/run_scheduled.py` has a dedicated `wpsr` group — the spec's "slots into an existing
pull rhythm" means this group, not `weekly_fri`. Add:

```python
        ("eia_ethanol_weekly", "pipelines.eia.pull_ethanol_weekly"),
```

**Add it after `derived_cushing`, not between `eia_wpsr` and `derived_cushing`.** That
group's ordering is load-bearing and commented as such — `derived_cushing` reads the
Cushing stocks row `eia_wpsr` just wrote. This pull is independent of both, so it goes last
and disturbs nothing.

**Check `git status` first** — a concurrent session may own other parts of that file. Add
only this line. If their edit conflicts, **report it rather than resolving it.**

- [ ] **Step 5: Record the cassette and run green**

Run: `.venv/Scripts/pytest.exe tests/test_eia_ethanol_weekly.py -v --record-mode=once`
Then replay: `.venv/Scripts/pytest.exe tests/test_eia_ethanol_weekly.py -v`
Also run: `.venv/Scripts/pytest.exe tests/test_run_scheduled.py -q`
Expected: all pass.

**Inspect the cassette before committing.** EIA authenticates by `api_key` query parameter
**and echoes it back in response bodies**; `tests/conftest.py` scrubs both. Confirm no real
key survives in either place.

- [ ] **Step 6: Commit**

```bash
git add pipelines/eia/pull_ethanol_weekly.py tests/test_eia_ethanol_weekly.py tests/cassettes/test_eia_ethanol_weekly/ infra/run_scheduled.py
git commit -m "feat(eia): weekly ethanol production, national and all five PADDs"
```

---

### Task 2: Biofuels capacity and feedstocks

**Files:**
- Create: `pipelines/eia/pull_biofuels.py`
- Test: `tests/test_eia_biofuels.py`
- Modify: `infra/run_scheduled.py`

**Interfaces:**
- Consumes: `EIAClient.get_series`; Task 0's codes.
- Produces: `CAPACITY: list[str]`, `FEEDSTOCKS: list[str]`, named constants for the three capacity series, `pull_capacity(client: EIAClient) -> pd.DataFrame`, `pull_feedstocks(client: EIAClient) -> pd.DataFrame`, `main() -> None`.

**One module, two routes, deliberately.** `capbio` (capacity) and `feedbiofuel`
(feedstocks) are the spec's single item 5 and are read together — capacity displacing
petroleum diesel demand is only interpretable alongside what is being fed into it. Two
`pull_*` functions keep them separately testable and separately resilient.

**Name collision warning:** `pipelines/eia/pull_gas_capacity.py` already defines a
`pull_capacity`. These are different modules so there is no import conflict, but a reader
grepping for `pull_capacity` will find both. Keep this module's docstring explicit about
which capacity it means.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eia_biofuels.py
from __future__ import annotations

import pytest
from core.schemas import validate_ts_long

from pipelines.eia import pull_biofuels


@pytest.mark.vcr
def test_capacity_returns_valid_ts_long_for_every_fuel() -> None:
    df = pull_biofuels.pull_capacity(pull_biofuels.EIAClient())

    validate_ts_long(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    assert set(df["geo"]) == {"US"}
    assert set(df["series_id"]) == set(pull_biofuels.CAPACITY)


@pytest.mark.vcr
def test_renewable_diesel_capacity_is_present_and_named() -> None:
    # Renewable diesel capacity displacing petroleum diesel demand is the signal the
    # spec names for this item. Selected by name, never by index.
    df = pull_biofuels.pull_capacity(pull_biofuels.EIAClient())
    assert pull_biofuels.RENEWABLE_DIESEL in set(df["series_id"])


@pytest.mark.vcr
def test_feedstocks_return_valid_ts_long_for_every_series() -> None:
    df = pull_biofuels.pull_feedstocks(pull_biofuels.EIAClient())

    validate_ts_long(df)
    assert not df.empty
    # A feedstock that silently returns nothing would understate feedstock competition,
    # which is the entire point of ingesting 26 series rather than a headline number.
    assert set(df["series_id"]) == set(pull_biofuels.FEEDSTOCKS)


def test_feedstock_list_is_the_full_set_and_has_no_duplicates() -> None:
    assert len(set(pull_biofuels.FEEDSTOCKS)) == len(pull_biofuels.FEEDSTOCKS)
    assert len(pull_biofuels.FEEDSTOCKS) == pull_biofuels.EXPECTED_FEEDSTOCK_COUNT
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/pytest.exe tests/test_eia_biofuels.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipelines.eia.pull_biofuels'`

- [ ] **Step 3: Write `pipelines/eia/pull_biofuels.py`**

**Replace every code below with Task 0's real dump**, including the full 26-entry feedstock
list. Set `EXPECTED_FEEDSTOCK_COUNT` to the count Task 0 actually found — if the route no
longer returns 26, use the real number and note the change in the commit message.

```python
"""Spec 31 item 5: biofuels production capacity and the feedstocks fed into it.

Two routes, one item, because they are only interpretable together. petroleum/pnp/capbio
is monthly national capacity for biodiesel, renewable diesel and fuel ethanol -- the
signal for renewable diesel capacity displacing petroleum diesel demand.
petroleum/pnp/feedbiofuel carries the monthly feedstock inputs (soybean oil, corn oil,
used cooking oil, tallow, canola), which is what QUANTIFIES feedstock competition rather
than merely asserting it.

Note this module's pull_capacity() is BIOFUEL production capacity. pipelines/eia/
pull_gas_capacity.py has a same-named function for natural gas STORAGE capacity; they are
unrelated. Both are national and monthly; neither needs a geo_map (area-name resolves to
"U.S." cleanly on both routes -- confirmed live). See pipelines/eia/CLAUDE.md."""

from __future__ import annotations

import pandas as pd
from core.failures import failure_scope
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient

# capbio -- 3 series, all US national. Named, never selected by index.
BIODIESEL = "M_EPOOXE_8BDPC_NUS_MMGL"
RENEWABLE_DIESEL = "M_EPOORDO_8RDPC_NUS_MMGL"
FUEL_ETHANOL = "M_EPOOXE_8FEPC_NUS_MMGL"

CAPACITY: list[str] = [BIODIESEL, RENEWABLE_DIESEL, FUEL_ETHANOL]

# feedbiofuel -- REPLACE WITH TASK 0's FULL DUMP. All US national, monthly.
FEEDSTOCKS: list[str] = [
    "M_EPOOBDSO_YIFBP_NUS_MMLB",
    # ... every remaining id from Task 0 Step 1, in the order the route returns them.
]

# Guards against a silently truncated paste of the list above. Task 0 counted this;
# a mismatch means the constant is incomplete, not that the route changed.
EXPECTED_FEEDSTOCK_COUNT = 26

CAPACITY_ROUTE = "petroleum/pnp/capbio"
FEEDSTOCK_ROUTE = "petroleum/pnp/feedbiofuel"
# Both routes declare `monthly` only -- confirmed live. A wrong frequency returns empty.
BIOFUEL_FREQUENCY = "monthly"


def pull_capacity(client: EIAClient) -> pd.DataFrame:
    """Biofuel PRODUCTION capacity -- not natural gas storage capacity."""
    return client.get_series(
        route=CAPACITY_ROUTE, series=CAPACITY, frequency=BIOFUEL_FREQUENCY
    )


def pull_feedstocks(client: EIAClient) -> pd.DataFrame:
    return client.get_series(
        route=FEEDSTOCK_ROUTE, series=FEEDSTOCKS, frequency=BIOFUEL_FREQUENCY
    )


def main() -> None:
    # Two separate failure scopes: a feedstock outage must not cost us the capacity
    # data, and vice versa. Per-route resilience is the project's standing rule.
    with failure_scope("eia.pull_biofuels.capacity"):
        capacity = pull_capacity(EIAClient())
        if capacity.empty:
            print("no biofuel capacity rows pulled", flush=True)
        else:
            write_ts_long(capacity, source="eia")
            print(f"wrote {len(capacity)} biofuel capacity rows", flush=True)

    with failure_scope("eia.pull_biofuels.feedstocks"):
        feedstocks = pull_feedstocks(EIAClient())
        if feedstocks.empty:
            print("no biofuel feedstock rows pulled", flush=True)
        else:
            write_ts_long(feedstocks, source="eia")
            print(
                f"wrote {len(feedstocks)} biofuel feedstock rows across "
                f"{feedstocks['series_id'].nunique()} feedstocks",
                flush=True,
            )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Register in the monthly group**

In `infra/run_scheduled.py`, add to the `monthly` group, after `eia_gas_consumption`:

```python
        ("eia_biofuels", "pipelines.eia.pull_biofuels"),
```

**Check `git status` first.** Add only this line; report conflicts rather than resolving
them.

- [ ] **Step 5: Record the cassette and run green**

Run: `.venv/Scripts/pytest.exe tests/test_eia_biofuels.py -v --record-mode=once` then replay.
Also run: `.venv/Scripts/pytest.exe tests/test_run_scheduled.py -q`
Expected: all pass. Inspect the cassette for a leaked key as in Task 1.

- [ ] **Step 6: Commit**

```bash
git add pipelines/eia/pull_biofuels.py tests/test_eia_biofuels.py tests/cassettes/test_eia_biofuels/ infra/run_scheduled.py
git commit -m "feat(eia): biofuels capacity and feedstock inputs"
```

---

### Task 3: Power-sector coal — the new `pipelines/coal/` package

> **PREREQUISITE: plan 31B's Task 1 must have landed `EIAClient.get_facet_series`.**
> If it has not, stop here and report that items 5 and 6 shipped and item 4 awaits the
> shared client work. **Do not write a second facet-dict fetcher.**

**Files:**
- Create: `pipelines/coal/__init__.py`
- Create: `pipelines/coal/pull_coal.py`
- Create: `pipelines/coal/CLAUDE.md`
- Modify: `pipelines/eia/client.py` (one parameter — see Decision C)
- Test: `tests/test_coal.py`
- Modify: `infra/run_scheduled.py`

**Interfaces:**
- Consumes: `EIAClient.get_facet_series(route, data_key, facets, frequency, series_id, geo, start=None, end=None, source="eia")` (plan 31B Task 1, plus this task's `source` parameter).
- Produces: `COAL_SOURCE: str`, `POWER_SECTOR: str`, `DATA_KEYS: list[str]` with named members, `coal_series_id(data_key, row) -> str`, `pull_coal(client: EIAClient) -> pd.DataFrame`, `main() -> None`.

#### Decision C — the client must stamp the source, because coal is the first non-`eia` route on it

`get_series`, `get_operational_series` and (as 31B writes it) `get_facet_series` all
**hardcode `"source": "eia"`** in the DataFrame they build. That was correct while every
route on this client was an EIA-sourced dataset. Item 4 breaks that: the spec says
**`source="coal"`**, so `read_ts_long(source="coal")` is meaningful for the new package.

`core.storage.write_ts_long(df, source=...)` uses its `source` argument to choose the
**partition directory only** — it does not rewrite the frame's `source` column. So passing
`source="coal"` to the writer while the client stamped `"eia"` produces rows filed under
`coal/` whose own `source` column reads `eia`. Nothing raises. `read_ts_long(source="coal")`
returns them, and every freshness query that groups by the column reports them as `eia`.
**That is a silent, self-inflicted data-integrity bug of exactly the shape this project
keeps catching**, so it is fixed at the client rather than patched after the fact.

**Add a `source: str = "eia"` parameter to `get_facet_series`.** The default keeps every
plan 31B caller byte-identical; only coal passes anything else.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_coal.py
from __future__ import annotations

import pytest
from core.schemas import validate_ts_long

from pipelines.coal import pull_coal


@pytest.mark.vcr
def test_coal_returns_valid_ts_long_under_its_own_source() -> None:
    df = pull_coal.pull_coal(pull_coal.EIAClient())

    validate_ts_long(df)
    assert not df.empty
    # The whole reason item 4 gets its own source: read_ts_long(source="coal") must be
    # meaningful. If the client's hardcoded "eia" leaked through, these rows would be
    # filed under coal/ while claiming to be eia -- nothing raises, and every freshness
    # query misreports them.
    assert set(df["source"]) == {"coal"}


@pytest.mark.vcr
def test_price_and_heat_content_both_arrive_with_their_own_units() -> None:
    # A switching calculation needs price AND heat content together; that they share one
    # route is the spec's stated reason for choosing it. They are in different units, and
    # units are stored exactly as published -- so a single unit across both would mean
    # one of them was overwritten.
    df = pull_coal.pull_coal(pull_coal.EIAClient())

    price = df[df["series_id"].str.contains(".PRICE.", regex=False)]
    heat = df[df["series_id"].str.contains(".HEAT_CONTENT.", regex=False)]
    assert not price.empty, "no price rows -- a switching calculation needs them"
    assert not heat.empty, "no heat-content rows -- a switching calculation needs them"
    assert set(price["unit"]) != set(heat["unit"]), (
        "price and heat content share a unit -- one has overwritten the other"
    )


@pytest.mark.vcr
def test_every_requested_data_key_produced_rows() -> None:
    df = pull_coal.pull_coal(pull_coal.EIAClient())
    for key in pull_coal.DATA_KEYS:
        marker = f".{key.upper().replace('-', '_')}."
        assert any(marker in sid for sid in df["series_id"]), f"no rows for {key}"


def test_data_keys_are_named_constants_not_positional() -> None:
    assert pull_coal.PRICE in pull_coal.DATA_KEYS
    assert pull_coal.HEAT_CONTENT in pull_coal.DATA_KEYS
    assert len(set(pull_coal.DATA_KEYS)) == len(pull_coal.DATA_KEYS)


def test_coal_series_ids_are_deterministic() -> None:
    row = {"location": "US", "sector": "1"}
    minted = pull_coal.coal_series_id(pull_coal.PRICE, row)
    assert minted == "COAL.PRICE.US-1.Q"
    # Permanent once written: the same row must always mint the same id.
    assert minted == pull_coal.coal_series_id(pull_coal.PRICE, dict(row))
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/pytest.exe tests/test_coal.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipelines.coal'`

- [ ] **Step 3: Add the `source` parameter to `get_facet_series`**

In `pipelines/eia/client.py`, change the signature and the one line that uses it:

```python
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
        source: str = "eia",
    ) -> pd.DataFrame:
```

and inside the returned frame:

```python
                "source": source,
```

**`source` defaults to `"eia"`, so every existing caller is unchanged.** The docstring
gains one line: coal/consumption-and-quality is the first route on this client whose rows
are not an `eia`-sourced dataset — `core.storage.write_ts_long`'s `source` argument picks
the partition directory but does not rewrite this column, so the two must agree or rows
land under one source claiming to be another.

- [ ] **Step 4: Write the package**

`pipelines/coal/__init__.py` — empty, matching the other pipeline packages.

`pipelines/coal/pull_coal.py`. **Replace the sector code, location list, data keys and
frequency with Task 0 Step 4/5's real values.**

```python
"""Spec 31 item 4: power-sector coal -- receipts, consumption, stocks, price, heat content.

Coal matters to this book through exactly one channel: coal-to-gas switching in US power
generation, which sets a floor and ceiling on gas demand. coal/consumption-and-quality
carries everything a switching calculation needs -- quantity, price ($/short ton) and heat
content -- in ONE route, which is why the spec chose it over the alternatives.

Deliberately excluded, and these are findings rather than omissions: Coal Markets basin
spot prices (Powder River, Illinois, Appalachia) are S&P Global proprietary per EIA's own
notice, with no bulk history anywhere -- a chart built on them would be empty for months.
API2 and API4, the seaborne thermal benchmarks that actually matter for European gas
substitution, are NEVER published by EIA at all; no amount of EIA work closes that gap.
There is no weekly coal data on the API at any route.

This route has NO `series` facet (400 on facet/series, confirmed live) -- rows are selected
by location+sector and the series id is minted here. A minted id is PERMANENT once written.
source="coal", not "eia": this is the first member of pipelines/coal/, and giving it its
own source keeps read_ts_long(source="coal") meaningful. See pipelines/coal/CLAUDE.md."""

from __future__ import annotations

import pandas as pd
from core.failures import failure_scope
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient

COAL_SOURCE = "coal"

COAL_ROUTE = "coal/consumption-and-quality"
# `quarterly` and `annual` are the only declared frequencies -- confirmed live. There is
# no monthly or weekly coal data on this API at all.
COAL_FREQUENCY = "quarterly"
_FREQ_SUFFIX = "Q"

# REPLACE WITH TASK 0 Step 4's real power-sector code. The spec scopes this item to the
# power sector only -- coal-to-gas switching is the single channel that matters here.
POWER_SECTOR = "1"

# REPLACE WITH TASK 0 Step 4's real location values. US is the minimum useful cut.
LOCATIONS: list[str] = ["US"]

# Named, never selected by index.
RECEIPTS = "receipts"
CONSUMPTION = "consumption"
STOCKS = "stocks"
PRICE = "price"
HEAT_CONTENT = "heat-content"

# Sulfur and ash content are available on this route but deliberately not ingested: they
# describe coal quality for emissions purposes, not the switching economics this item
# exists for. Add them only with a reason.
DATA_KEYS: list[str] = [RECEIPTS, CONSUMPTION, STOCKS, PRICE, HEAT_CONTENT]


def coal_series_id(data_key: str, row: dict[str, object]) -> str:
    """COAL.<DATA_KEY>.<location>-<sector>.Q -- e.g. COAL.PRICE.US-1.Q.

    Deterministic from the row's own facets, following get_operational_series's
    ELEC.<KEY>.<facets>.<freq> precedent. Permanent once written to the lake: changing
    this scheme later orphans every row already stored under the old one."""
    key_id = data_key.upper().replace("-", "_")
    return f"COAL.{key_id}.{row['location']}-{row['sector']}.{_FREQ_SUFFIX}"


def pull_coal(client: EIAClient) -> pd.DataFrame:
    """One frame across every data key. get_facet_series takes a single data_key, so this
    loops -- the same shape get_operational_series uses for its own data_keys list.

    Each key carries its OWN unit ($/short ton for price, MMBtu for heat content, short
    tons for the quantities), stored exactly as published. Never reconcile them here."""
    frames = [
        client.get_facet_series(
            route=COAL_ROUTE,
            data_key=key,
            facets={"location": LOCATIONS, "sector": [POWER_SECTOR]},
            frequency=COAL_FREQUENCY,
            series_id=lambda row, key=key: coal_series_id(key, row),
            geo=lambda row: str(row["location"]),
            source=COAL_SOURCE,
        )
        for key in DATA_KEYS
    ]
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    with failure_scope("coal.pull_coal"):
        df = pull_coal(EIAClient())
        if df.empty:
            print("no coal rows pulled", flush=True)
            return
        write_ts_long(df, source=COAL_SOURCE)
        print(
            f"wrote {len(df)} coal rows across {df['series_id'].nunique()} series",
            flush=True,
        )


if __name__ == "__main__":
    main()
```

**Note the `key=key` default-argument binding in the lambda.** Without it, every lambda in
that comprehension closes over the *final* value of `key` and all five data keys would mint
ids under one name — a classic late-binding bug that raises nothing and silently collapses
the dataset. `test_every_requested_data_key_produced_rows` is what catches it.

- [ ] **Step 5: Write `pipelines/coal/CLAUDE.md`**

The spec requires the new package to carry its own `CLAUDE.md`. Follow
`pipelines/eia/CLAUDE.md`'s style — what was confirmed live, what was excluded and why.
It must record, with real values from Task 0:

- the route, its facets, and that it has **no series facet** (400 on `facet/series`);
- the minted series-id scheme `COAL.<DATA_KEY>.<location>-<sector>.Q`, and that it is
  **permanent once written**;
- **why `source="coal"` and not `"eia"`**, including the `write_ts_long` partition-vs-column
  distinction that made the client's `source` parameter necessary;
- the unit string for every data key ingested;
- the three deliberate exclusions, with their reasons: **Coal Markets basin spot prices**
  (S&P Global proprietary, no bulk history), **API2/API4** (never published by EIA at all —
  a vendor gap, not a backlog item), and **weekly coal production** (no API route; would
  need scraping);
- that `sulfur-content` and `ash-content` exist on the route and were deliberately not
  ingested.

- [ ] **Step 6: Register in the monthly group**

Coal is quarterly; the scheduler's slowest group is `monthly`, which is the right home — a
quarterly series simply re-writes unchanged rows on two runs in three, and `write_ts_long`
de-duplicates. Add to `monthly`:

```python
        ("coal", "pipelines.coal.pull_coal"),
```

**Check `git status` first.** Add only this line; report conflicts rather than resolving.

- [ ] **Step 7: Record the cassette and run green**

Run: `.venv/Scripts/pytest.exe tests/test_coal.py -v --record-mode=once` then replay.
Also run: `.venv/Scripts/pytest.exe tests/test_run_scheduled.py tests/test_eia_client_facets.py -q`
— the second confirms the new `source` parameter did not disturb plan 31B's callers.
Expected: all pass. Inspect the cassette for a leaked key as in Task 1.

- [ ] **Step 8: Commit**

```bash
git add pipelines/coal/ tests/test_coal.py tests/cassettes/test_coal/ pipelines/eia/client.py infra/run_scheduled.py
git commit -m "feat(coal): power-sector coal receipts, consumption, stocks, price and heat content"
```

---

### Task 4: Final gate

**Files:** none created; this task verifies and records.

- [ ] **Step 1: Run the real pulls**

```
.venv/Scripts/python.exe -m pipelines.eia.pull_ethanol_weekly
.venv/Scripts/python.exe -m pipelines.eia.pull_biofuels
.venv/Scripts/python.exe -m pipelines.coal.pull_coal
```

Record the real row counts. A route failing is a finding to record, not to hide. `main()`
raises `PartialFailureError` on any recorded failure, so a non-zero exit with rows written
is legitimate.

- [ ] **Step 2: Confirm the coal source is genuinely its own**

The single most important check in this plan, because the failure it guards is silent.

```python
from core.storage import read_ts_long

coal = read_ts_long(source="coal")
print("coal rows:", len(coal))
print("source column values:", set(coal["source"]))
print("series:", sorted(set(coal["series_id"])))
print("units by series:")
print(coal.groupby("series_id")["unit"].unique())
```

**`set(coal["source"])` must be exactly `{"coal"}`.** If it contains `"eia"`, Decision C's
fix did not take and the rows are filed under one source while claiming another — report
it. Note the read is narrowed by `source=`, per the global constraints.

- [ ] **Step 3: Confirm each item's data answers its question**

```python
from core.storage import read_ts_long
from pipelines.eia.pull_biofuels import CAPACITY, FEEDSTOCKS, RENEWABLE_DIESEL
from pipelines.eia.pull_ethanol_weekly import ETHANOL

eth = read_ts_long(series_ids=ETHANOL, source="eia")
print("ethanol rows:", len(eth), "| regions:", sorted(set(eth["geo"])))
print("  PADD5 present:", "PADD5" in set(eth["geo"]))

cap = read_ts_long(series_ids=CAPACITY, source="eia")
feed = read_ts_long(series_ids=FEEDSTOCKS, source="eia")
print("biofuel capacity rows:", len(cap), "| feedstock rows:", len(feed))
print("  renewable diesel rows:", len(cap[cap["series_id"] == RENEWABLE_DIESEL]))
print("  distinct feedstock units:", sorted(set(feed["unit"])))
```

**PADD5 must be present** — under-ingesting the West Coast is the specific cost plan 31A's
Task 0 flagged for this plan. **Record the distinct feedstock unit set**: if it holds more
than one unit, say so plainly, because anything that later plots those 26 series together
must convert first.

- [ ] **Step 4: Full suite, lint, typecheck**

`.venv/Scripts/pytest.exe`, then `.venv/Scripts/ruff.exe check .` and
`.venv/Scripts/mypy.exe core pipelines infra`.

**`mypy` now covers `pipelines/coal/` for the first time** — it is a new package under an
already-checked path. If it reports errors there, fix them; they are this plan's.

A concurrent session works in this repo. If a test fails in a file this plan never touched,
**report it, do not fix it.**

- [ ] **Step 5: Record real outcomes**

Append the real row counts and the checks above to `pipelines/eia/CLAUDE.md` (items 5 and
6) and `pipelines/coal/CLAUDE.md` (item 4).

Update `specs/00_INDEX.md`'s Spec 31 row to record that items 4, 5 and 6 shipped, what did
not work, and — if plan 31B has also landed — that Spec 31 is complete. **Add `pipelines/coal/`
to the index wherever it lists pipeline packages**: the spec notes there is no coal
reference anywhere in `specs/00_INDEX.md` today, and this item creates the package. Use the
plain-spoken register the Spec 18–21 rows use.

- [ ] **Step 6: Commit**

```bash
git add pipelines/eia/CLAUDE.md pipelines/coal/CLAUDE.md specs/00_INDEX.md
git commit -m "docs(spec31c): record real outcomes for coal, biofuels and ethanol"
```

---

## Page sections — deliberately not a task in this plan

Spec 31 says its items feed "sections on existing pages; no new page". **This plan contains
no dashboard task, by decision** — the same decision plan 31B records, for the same reason.

`apps/dashboard/**` belongs to a concurrent design session migrating all 16 pages to a new
section kit. Plan 31A tried to land one additive section during that migration; the lane
owner declined, correctly — an additive `card(...)` section would have collided with a
full-file rewrite, and a new chart backed by a computed ratio is a *feature* being reviewed
inside a pure-restyle diff where nobody would look for numeric errors.

The sections worth building from this plan's data, once the migration has landed:

- **Coal-to-gas switching economics** — `COAL.PRICE.US-1.Q` and `COAL.HEAT_CONTENT.US-1.Q`
  converted to $/MMBtu against the Henry Hub gas price already in the lake. **The
  conversion belongs in `core/`, not the page**, and it is the whole analytical point of
  item 4. Anything that plots coal price against gas price without dividing by heat content
  is comparing $/short ton to $/MMBtu and is simply wrong.
- **Ethanol production by PADD** — the six `wprode` series, weekly, alongside the WPSR
  series they share a cadence with.
- **Renewable diesel capacity against feedstock inputs** — item 5's two routes together,
  which is the pairing that makes either interpretable. **Check the feedstock units first**
  (Task 4 Step 3 records them); more than one unit across the 26 series means they cannot
  share an axis unconverted.

Hand these descriptions to whoever owns `apps/dashboard/**` at the time rather than
building them here.

---

## Self-Review

**Spec coverage:** item 6 (weekly ethanol, all five PADDs) → Task 1; item 5 (`capbio` +
`feedbiofuel`) → Task 2; item 4 (power-sector coal, new `pipelines/coal/`, `source="coal"`,
its own `CLAUDE.md`) → Task 3; "live route verification before pull code" → Task 0;
scheduling → Task 1 Step 4, Task 2 Step 4, Task 3 Step 6; acceptance criteria → Task 4. The
spec's three named coal exclusions (Coal Markets spot prices, API2/API4, weekly coal
production) are carried into `pipelines/coal/CLAUDE.md` by Task 3 Step 5 rather than being
silently dropped. Item 2 is plan 31B; items 1 and 3 shipped in 31A.

**Deliberate gaps:** the page sections, argued above; and `sulfur-content` / `ash-content`
on the coal route, which describe emissions quality rather than switching economics — named
in the code and in `CLAUDE.md` rather than omitted silently.

**Cross-plan dependency:** Task 3 requires plan 31B's Task 1. Stated at the top of this
plan and again on the task itself, with an explicit instruction not to duplicate the
fetcher and an explicit fallback (ship items 5 and 6, report item 4 as waiting). Tasks 1
and 2 are free of it, which is why they come first.

**Type consistency:** `pull_ethanol`, `pull_capacity`, `pull_feedstocks` and `pull_coal` are
all `(client: EIAClient) -> pd.DataFrame`, matching plan 31A's `pull_capacity` /
`pull_consumption` shape; every `main()` is `() -> None`, as `infra/run_scheduled.py`
requires. `coal_series_id(data_key: str, row: dict[str, object]) -> str` is adapted to
`get_facet_series`'s `Callable[[dict[str, Any]], str]` by the `lambda row, key=key:` in
`pull_coal` — the default-argument binding is load-bearing, not stylistic. The `source`
parameter added to `get_facet_series` defaults to `"eia"`, so plan 31B's three callers are
unaffected.

**Naming collision, known and handled:** `pull_biofuels.pull_capacity` and
`pull_gas_capacity.pull_capacity` share a function name in different modules. No import
conflict exists, and both docstrings say which capacity they mean.

**Risk to watch:** the feedstock list in Task 2 is a **26-entry placeholder** and the coal
sector/location codes in Task 3 are **placeholders**. Task 0 replaces them, and its findings
take precedence over anything written here — the same discipline that caught three plan
defects in Spec 30 and two spec errors in 31A. `EXPECTED_FEEDSTOCK_COUNT` exists precisely
because a truncated paste of a 26-item list is the most likely way this plan ships
incomplete data without anything raising.
