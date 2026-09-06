# EIA Price Coverage (Spec 30) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the four missing EIA price families — refiner acquisition cost by grade, retail pump prices, gas citygate/sectoral prices, and generator delivered fuel cost — as new routes on the existing `EIAClient`.

**Architecture:** One new module, `pipelines/eia/pull_prices.py`, following `pull_wpsr.py`'s shape exactly: series-code constants, a list of `(route, series, frequency)` groups, one `write_ts_long(df, source="eia")`. No new client, no new pipeline package, no schema change. Two page sections consume the result.

**Tech Stack:** Python 3.12, existing `pipelines/eia/client.py` (`EIAClient.list_series`, `.get_series`), `core.storage.write_ts_long`, `core.failures`, pandas, plotly, streamlit. Tests: pytest + vcrpy cassettes.

**Spec:** `specs/30_eia-price-coverage.md`

## Global Constraints

Copied from the spec and root `CLAUDE.md`. Every task's requirements implicitly include this section.

- **Never guess a series ID.** Every code must come from `EIAClient.list_series(route)` (the `facet/series` endpoint). A code copied from a `dnav` page URL is a plan failure. This is the discipline that caught the real `SEPL`→`SEPLAT` error in Spec 17.
- **Series IDs stay in EIA's native form** (`R0000____3`, `EMM_EPM0_PTE_NUS_DPG` style), matching the eleven routes already in `pipelines/eia/`. **Not** the dotted style of Specs 17–29. The spec records why.
- **Units are stored exactly as EIA publishes them and never converted at ingest.** `$/bbl`, `$/gal`, `$/Mcf`, `$/MMBtu`. Conversion belongs in `core/`, never in a pipeline.
- **No new schema.** `core/schemas.py` is not touched. Everything is `ts_long`.
- **No new pipeline package.** Everything lands in the existing `pipelines/eia/`.
- `source="eia"` on every row. `freq` as published. `geo` carries the PADD, state or city code.
- **PMM and EPM revise prior months.** `revision_date = ingested_at`; `write_ts_long`'s dedup on `(series_id, ts)` sorted by `revision_date` keeps the latest. A changed historical value is expected, not a bug.
- Per-route resilience via `core.failures` (`record_failure` / `failure_scope`), matching `pipelines/adanos/pull_adanos.py`. One failing route must not abort the others, and a run where every route failed must raise so the exit status is honest.
- **Never pass `use_container_width`** to `st.plotly_chart` — root `CLAUDE.md` prohibits it; the default is already stretch.
- Charts use `core.theme` colours only. Every chart wrapped in `card(...)`. British English in all prose, labels and docstrings.
- `from __future__ import annotations` at the top of every module. Typed throughout.
- Use the repo venv: `.venv/Scripts/python.exe`, `.venv/Scripts/pytest.exe`, `.venv/Scripts/ruff.exe`, `.venv/Scripts/mypy.exe`. Bare commands are **not** on PATH.
- Another session works in this repo. **Never `git add -A` or `git add .`** — stage explicit paths, `git status` first. Do not run the full suite except in the final task.

---

### Task 0: Discover the real series codes — no pull code

The spec makes this mandatory and it is not ceremony. `EIAClient.list_series(route)` exists precisely so codes are discovered rather than guessed, and every guessed identifier this project has shipped has been wrong at least once.

**Files:**
- Modify: `pipelines/eia/CLAUDE.md` (append a "Spec 30 price routes" section)

**Interfaces:**
- Consumes: `EIAClient.list_series(route) -> list[dict[str, str]]` (already exists).
- Produces: the real series codes that Tasks 1 and 2 code against.

- [ ] **Step 1: Walk every candidate route and dump what it actually offers**

Run this as a throwaway script (do **not** commit it):

```python
from pipelines.eia.client import EIAClient

ROUTES = [
    "petroleum/pri/rac2",
    "petroleum/pri/gnd",
    "natural-gas/pri/sum",
    "natural-gas/pri/rescom",
    "natural-gas/pri/fut",
    "electricity/electric-power-operational-data",
]

client = EIAClient()
for route in ROUTES:
    try:
        facets = client.list_series(route)
    except Exception as exc:
        print(f"\n== {route}: FAILED {type(exc).__name__}: {exc}")
        continue
    print(f"\n== {route}: {len(facets)} series")
    for f in facets[:40]:
        print("   ", f.get("id"), "|", f.get("name"))
```

Record the real counts. A route that fails or returns nothing is a **finding**, not something to work around.

- [ ] **Step 2: Choose the codes for each family and write down why**

From the dumps, pick:

- **Refiner acquisition cost** (`petroleum/pri/rac2`): composite, domestic and imported, at US level and per PADD.
- **Retail gasoline & diesel** (`petroleum/pri/gnd`): US all-grades regular gasoline and No. 2 diesel, plus the five PADD equivalents.
- **Gas citygate and sectoral** (`natural-gas/pri/sum`, `pri/rescom`): US citygate, residential, commercial and industrial delivered price.
- **Generator fuel cost** (`electricity/electric-power-operational-data`): the receipts/cost facet carrying average cost of natural gas delivered to electric generators, plus gas consumption for generation.

Keep each list to **at most 12 codes** per family. This spec is about closing a gap, not maximising row count.

- [ ] **Step 3: Resolve the `natural-gas/pri/fut` question explicitly**

The spec leaves this open on purpose. Compare what that route offers against what Spec 18 already ingests (read `specs/18_curve-market-structure.md` and `pipelines/futures/`). **Decide, and record the decision with its reason.** If it duplicates Spec 18's futures, do not ingest it — ingesting the same futures twice under two conventions is exactly the kind of thing that looks fine and quietly corrupts a comparison.

- [ ] **Step 4: Check the frequency each route actually accepts**

`get_series` passes `frequency` straight through. Confirm live which value each route wants (`monthly`, `weekly`, `annual`) — a wrong frequency returns an empty result rather than an error, which is the same silent-success trap Polymarket's ignored `search` parameter set in Spec 29.

- [ ] **Step 5: Append the findings to `pipelines/eia/CLAUDE.md`**

Follow that file's existing style — state what was confirmed live versus what is only documented, and record negatives. Include:

```markdown
## Spec 30 price routes — confirmed live [DATE]

| Route | Series discovered | Codes used | Frequency | Notes |
|---|---|---|---|---|
| petroleum/pri/rac2 | [N] | [list] | monthly | |
| petroleum/pri/gnd | [N] | [list] | weekly | |
| natural-gas/pri/sum | [N] | [list] | monthly | |
| natural-gas/pri/rescom | [N] | [list] | monthly | |
| electricity/electric-power-operational-data | [N] | [list] | monthly | |

**natural-gas/pri/fut decision:** [ingested / not ingested] because [reason].

**Routes that returned nothing or failed:** [real list, or "none"]
```

Replace every bracket with a real value. A committed `[DATE]` or `[N]` is a task failure.

- [ ] **Step 6: Commit**

```bash
git add pipelines/eia/CLAUDE.md
git commit -m "docs(eia): live-discovered series codes for Spec 30 price routes"
```

---

### Task 1: Petroleum price pulls

**Files:**
- Create: `pipelines/eia/pull_prices.py`
- Test: `tests/test_eia_prices.py`

**Interfaces:**
- Consumes: `EIAClient.get_series(route, series, frequency) -> pd.DataFrame` (exists); Task 0's discovered codes.
- Produces: `RAC`, `RETAIL` (`list[str]` constants), `PETROLEUM_GROUPS: list[tuple[str, list[str], str]]`, and `pull_group(client, route, series, frequency) -> pd.DataFrame`. Task 2 extends the same module and reuses `pull_group`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eia_prices.py
from __future__ import annotations

import pandas as pd
import pytest
import requests
from core.schemas import validate_ts_long
from pipelines.eia import pull_prices


@pytest.mark.vcr
def test_refiner_acquisition_cost_returns_valid_ts_long() -> None:
    df = pull_prices.pull_group(
        pull_prices.EIAClient(), "petroleum/pri/rac2", pull_prices.RAC, "monthly"
    )

    validate_ts_long(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    assert set(df["series_id"]).issubset(set(pull_prices.RAC))
    # Units are stored exactly as EIA publishes them, never converted at ingest.
    assert all("$" in u for u in df["unit"].unique())


@pytest.mark.vcr
def test_retail_prices_are_weekly_and_dollars_per_gallon() -> None:
    df = pull_prices.pull_group(
        pull_prices.EIAClient(), "petroleum/pri/gnd", pull_prices.RETAIL, "weekly"
    )

    validate_ts_long(df)
    assert not df.empty
    assert set(df["freq"]) == {"weekly"}


def test_one_failing_route_does_not_abort_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    # The pattern pipelines/adanos/pull_adanos.py established: per-route resilience,
    # not just per-request retry. One dead route must never cost the rest of the pull.
    calls: list[str] = []

    def fake_get_series(self, route, series, frequency, geo_map=None):  # type: ignore[no-untyped-def]
        calls.append(route)
        if route == "petroleum/pri/gnd":
            raise requests.exceptions.ConnectionError("gnd down")
        return pd.DataFrame(
            {
                "series_id": ["X"], "source": ["eia"], "ts": [pd.Timestamp("2026-01-01")],
                "value": [1.0], "unit": ["$/bbl"], "geo": ["US"], "freq": [frequency],
                "revision_date": [pd.Timestamp("2026-01-02")],
            }
        )

    monkeypatch.setattr(pull_prices.EIAClient, "get_series", fake_get_series)

    frames = pull_prices.pull_all(
        [("petroleum/pri/rac2", ["A"], "monthly"), ("petroleum/pri/gnd", ["B"], "weekly")]
    )

    assert len(calls) == 2, "the second route must still be attempted"
    assert len(frames) == 1, "only the surviving route yields a frame"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/pytest.exe tests/test_eia_prices.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipelines.eia.pull_prices'`

- [ ] **Step 3: Write `pipelines/eia/pull_prices.py`**

Replace the placeholder code lists with Task 0's real discovered codes.

```python
"""Spec 30: the price families the lake was missing. Volumes were everywhere and
prices almost nowhere -- one gas price (fred.dhhngsp), no retail pump prices at all,
and no grade-differentiated crude price beneath Spec 19's quality-mismatch work or
Spec 20's crack VECM.

Series codes were discovered live via EIAClient.list_series, never guessed from a
dnav URL -- see pipelines/eia/CLAUDE.md for the real dumps and counts.

Units are written exactly as EIA publishes them and are never converted here;
conversion belongs in core/, not in a pipeline."""

from __future__ import annotations

import pandas as pd
from core.failures import failure_scope, record_failure
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient

# Refiner acquisition cost of crude oil -- composite, domestic and imported.
# The price refiners actually paid, as opposed to what the benchmark printed.
RAC: list[str] = ["R0000____3", "R0000____1", "R0000____2"]

# Retail gasoline (all grades, regular) and No. 2 diesel, US and PADD level.
RETAIL: list[str] = ["EMM_EPM0_PTE_NUS_DPG", "EMD_EPD2D_PTE_NUS_DPG"]

PETROLEUM_GROUPS: list[tuple[str, list[str], str]] = [
    ("petroleum/pri/rac2", RAC, "monthly"),
    ("petroleum/pri/gnd", RETAIL, "weekly"),
]


def pull_group(
    client: EIAClient, route: str, series: list[str], frequency: str
) -> pd.DataFrame:
    """One route's worth of rows. Kept separate from pull_all so a single route can be
    exercised directly by a cassette test."""
    return client.get_series(route=route, series=series, frequency=frequency)


def pull_all(groups: list[tuple[str, list[str], str]]) -> list[pd.DataFrame]:
    """Per-route resilience, matching pipelines/adanos/pull_adanos.py: one route
    failing is recorded and skipped, never raised here, so the rest of the pull still
    runs. failure_scope in main() turns any recorded failure into a non-zero exit."""
    client = EIAClient()
    frames: list[pd.DataFrame] = []
    for route, series, frequency in groups:
        try:
            df = pull_group(client, route, series, frequency)
        except Exception as exc:  # noqa: BLE001 - one route must never abort the rest
            record_failure(f"eia prices {route}", exc)
            continue
        print(f"eia prices {route}: {len(df)} rows", flush=True)
        frames.append(df)
    return frames


def main() -> None:
    with failure_scope("eia.pull_prices"):
        frames = pull_all(PETROLEUM_GROUPS)
        if not frames:
            print("no EIA price rows pulled", flush=True)
            return
        df = pd.concat(frames, ignore_index=True)
        write_ts_long(df, source="eia")
        print(f"wrote {len(df)} EIA price rows", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Record cassettes and run green**

Run: `.venv/Scripts/pytest.exe tests/test_eia_prices.py -v --record-mode=once`
Then replay: `.venv/Scripts/pytest.exe tests/test_eia_prices.py -v`
Expected: 3 passed.

**Inspect the cassettes before committing.** EIA authenticates by `api_key` **query parameter** and echoes it back in the response body; `tests/conftest.py` scrubs both. Confirm no real key survives in either place — grep the cassette for the first six characters of the live key.

- [ ] **Step 5: Commit**

```bash
git add pipelines/eia/pull_prices.py tests/test_eia_prices.py tests/cassettes/test_eia_prices/
git commit -m "feat(eia): refiner acquisition cost and retail pump prices"
```

---

### Task 2: Gas and generator fuel-cost pulls, plus scheduling

**Files:**
- Modify: `pipelines/eia/pull_prices.py`
- Modify: `tests/test_eia_prices.py`
- Create: `pipelines/eia/pull_prices_weekly.py`
- Modify: `infra/run_scheduled.py`

**Interfaces:**
- Consumes: `pull_group`, `pull_all`, `PETROLEUM_GROUPS` from Task 1.
- Produces: `GAS`, `GENERATOR_FUEL` constants; `MONTHLY_GROUPS` and `WEEKLY_GROUPS` replacing `PETROLEUM_GROUPS`; `main()` (monthly) and a thin `pull_prices_weekly.main` re-export.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_eia_prices.py`:

```python
@pytest.mark.vcr
def test_gas_prices_carry_dollar_units_and_state_or_national_geo() -> None:
    df = pull_prices.pull_group(
        pull_prices.EIAClient(), "natural-gas/pri/sum", pull_prices.GAS, "monthly"
    )

    validate_ts_long(df)
    assert not df.empty
    assert all("$" in u for u in df["unit"].unique())
    assert df["geo"].notna().all()


@pytest.mark.vcr
def test_generator_fuel_cost_returns_valid_ts_long() -> None:
    df = pull_prices.pull_group(
        pull_prices.EIAClient(),
        "electricity/electric-power-operational-data",
        pull_prices.GENERATOR_FUEL,
        "monthly",
    )

    validate_ts_long(df)
    assert not df.empty


def test_monthly_and_weekly_groups_are_disjoint() -> None:
    # A route pulled on both cadences would write the same rows twice under two
    # revision_dates -- harmless to the lake's dedup, but a real sign of confusion.
    monthly = {route for route, _, _ in pull_prices.MONTHLY_GROUPS}
    weekly = {route for route, _, _ in pull_prices.WEEKLY_GROUPS}
    assert monthly.isdisjoint(weekly)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/pytest.exe tests/test_eia_prices.py -v -k "gas_prices or generator or disjoint"`
Expected: FAIL with `AttributeError: module 'pipelines.eia.pull_prices' has no attribute 'GAS'`

- [ ] **Step 3: Extend `pull_prices.py`**

Replace the placeholder codes with Task 0's real discoveries. Delete the `PETROLEUM_GROUPS` constant and its use, replacing it with the two cadence groups.

```python
# Citygate and sectoral delivered gas prices. The lake holds one gas price
# (fred.dhhngsp, Henry Hub spot) and nothing to locate it against, so basis is
# uncomputable today.
GAS: list[str] = ["N3050US3", "N3010US3", "N3020US3", "N3035US3"]

# EPM Table 4.13 -- average cost of natural gas delivered to electric generators
# ($/MMBtu) -- plus Table 2.4's gas burn. The direct gas-to-power bridge.
GENERATOR_FUEL: list[str] = ["ELEC.RECEIPTS_BTU.NG-US-99.M", "ELEC.CONS_TOT_BTU.NG-US-99.M"]

MONTHLY_GROUPS: list[tuple[str, list[str], str]] = [
    ("petroleum/pri/rac2", RAC, "monthly"),
    ("natural-gas/pri/sum", GAS, "monthly"),
    ("electricity/electric-power-operational-data", GENERATOR_FUEL, "monthly"),
]

WEEKLY_GROUPS: list[tuple[str, list[str], str]] = [
    ("petroleum/pri/gnd", RETAIL, "weekly"),
]
```

Change `main()` to use `MONTHLY_GROUPS`, and add:

```python
def main_weekly() -> None:
    with failure_scope("eia.pull_prices_weekly"):
        frames = pull_all(WEEKLY_GROUPS)
        if not frames:
            print("no weekly EIA price rows pulled", flush=True)
            return
        df = pd.concat(frames, ignore_index=True)
        write_ts_long(df, source="eia")
        print(f"wrote {len(df)} weekly EIA price rows", flush=True)
```

- [ ] **Step 4: Create `pipelines/eia/pull_prices_weekly.py`**

```python
"""Thin re-export so infra/run_scheduled.py can address the weekly cadence by the same
pull_<cadence> convention every other pipeline uses -- the precedent is
pipelines/adanos/pull_weekly.py."""

from __future__ import annotations

from pipelines.eia.pull_prices import main_weekly as main

__all__ = ["main"]
```

- [ ] **Step 5: Register both cadences**

In `infra/run_scheduled.py`, add `("eia_prices_weekly", "pipelines.eia.pull_prices_weekly")` to the `weekly_fri` group and `("eia_prices", "pipelines.eia.pull_prices")` to the monthly group.

**Check `git status` first** — a concurrent session owns the rest of that file. Add only your two lines. If their edit conflicts, **report it rather than resolving it**.

- [ ] **Step 6: Record cassettes and run green**

Run: `.venv/Scripts/pytest.exe tests/test_eia_prices.py -v --record-mode=once` then replay.
Also run: `.venv/Scripts/pytest.exe tests/test_run_scheduled.py -q`
Expected: all pass. Inspect the new cassettes for a leaked key as in Task 1.

- [ ] **Step 7: Commit**

```bash
git add pipelines/eia/pull_prices.py pipelines/eia/pull_prices_weekly.py infra/run_scheduled.py tests/test_eia_prices.py tests/cassettes/test_eia_prices/
git commit -m "feat(eia): gas citygate/sectoral and generator delivered fuel cost"
```

---

### Task 3: Crude acquisition cost section on `20_cracks.py`

**Files:**
- Modify: `apps/dashboard/pages/20_cracks.py`

**Interfaces:**
- Consumes: `read_ts_long` (already imported on that page); `RAC`, `RETAIL` from `pipelines.eia.pull_prices`.
- Produces: nothing consumed downstream.

- [ ] **Step 1: Add the section functions**

Place after the existing crack sections, before the model-card section. Match the page's existing idiom exactly — `card(...)`, `core.theme` colours, no `use_container_width`.

```python
def _acquisition_cost_section() -> None:
    """What refiners actually paid, against what the benchmark printed. Spec 19's
    quality-mismatch work and Spec 20's VECM both reason about crude grades; until
    Spec 30 the lake held no grade-differentiated price at all."""
    df = read_ts_long(series_ids=list(RAC))
    if df.empty:
        st.info("No refiner acquisition cost yet — run `pipelines/eia/pull_prices.py`.")
        return

    fig = go.Figure()
    for series_id, colour in zip(RAC, (NAVY, LIGHT_BLUE, RED), strict=False):
        s = df[df["series_id"] == series_id].sort_values("ts")
        if s.empty:
            continue
        fig.add_trace(
            go.Scatter(x=s["ts"], y=s["value"], name=series_id, mode="lines",
                       line={"color": colour, "width": 2})
        )
    wti = read_ts_long(series_ids=["fred.dcoilwtico"]).sort_values("ts")
    if not wti.empty:
        fig.add_trace(
            go.Scatter(x=wti["ts"], y=wti["value"], name="WTI spot", mode="lines",
                       line={"color": GREY, "width": 1, "dash": "dot"})
        )
    fig.update_layout(title="Refiner acquisition cost vs WTI spot", yaxis_title="$/bbl")
    with card("Crude acquisition cost"):
        st.plotly_chart(fig)
        st.caption(
            "Composite, domestic and imported acquisition cost is what refiners paid; "
            "the dotted line is the benchmark print. The gap between them is the part "
            "a spot-only crack cannot see."
        )


def _retail_margin_section() -> None:
    df = read_ts_long(series_ids=list(RETAIL))
    if df.empty:
        st.info("No retail price data yet — run `pipelines/eia/pull_prices_weekly.py`.")
        return

    fig = go.Figure()
    for series_id, colour in zip(RETAIL, (NAVY, LIGHT_BLUE), strict=False):
        s = df[df["series_id"] == series_id].sort_values("ts")
        if s.empty:
            continue
        fig.add_trace(
            go.Scatter(x=s["ts"], y=s["value"], name=series_id, mode="lines",
                       line={"color": colour, "width": 2})
        )
    fig.update_layout(title="Retail gasoline and diesel", yaxis_title="$/gal")
    with card("Retail pump prices"):
        st.plotly_chart(fig)
        st.caption(
            "Shown beneath the wholesale crack deliberately — the interesting quantity "
            "is the retail-to-wholesale margin, not the pump price alone."
        )
```

- [ ] **Step 2: Add imports and call sites**

Add to the page's import block:

```python
from pipelines.eia.pull_prices import RAC, RETAIL
```

Confirm `NAVY`, `LIGHT_BLUE`, `RED`, `GREY` are already imported from `core.theme` on this page; add any that are missing. Then add, after the existing crack sections:

```python
st.subheader("Crude acquisition cost")
_acquisition_cost_section()
_retail_margin_section()
```

- [ ] **Step 3: Verify the page still loads**

Run: `.venv/Scripts/pytest.exe tests/test_pages_smoke.py -k 20_cracks -q`
Expected: 1 passed. It must pass **with an empty lake** too — the `st.info` branches are what that proves.

Then: `.venv/Scripts/ruff.exe check apps/` and `.venv/Scripts/mypy.exe core pipelines infra`

- [ ] **Step 4: Commit**

```bash
git add apps/dashboard/pages/20_cracks.py
git commit -m "feat(page20): crude acquisition cost and retail pump prices"
```

---

### Task 4: Delivered fuel cost section on `05_us_gas_power.py`

**Files:**
- Modify: `apps/dashboard/pages/05_us_gas_power.py`

**Interfaces:**
- Consumes: `GENERATOR_FUEL` from `pipelines.eia.pull_prices`; `read_ts_long`; the page's existing `card`, `core.theme` imports.
- Produces: nothing consumed downstream.

- [ ] **Step 1: Add the section function**

```python
def _delivered_fuel_cost_section() -> None:
    """The gas-to-power bridge: what generators pay above Henry Hub is where fuel
    switching economics actually bite. Spec 30 supplies the cost leg; fred.dhhngsp
    was already in the lake as the benchmark."""
    cost_id = GENERATOR_FUEL[0]
    cost = read_ts_long(series_ids=[cost_id]).sort_values("ts")
    hh = read_ts_long(series_ids=["fred.dhhngsp"]).sort_values("ts")
    if cost.empty:
        st.info("No generator fuel cost yet — run `pipelines/eia/pull_prices.py`.")
        return

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=cost["ts"], y=cost["value"], name="Delivered to generators",
                   mode="lines", line={"color": NAVY, "width": 2})
    )
    if not hh.empty:
        fig.add_trace(
            go.Scatter(x=hh["ts"], y=hh["value"], name="Henry Hub spot", mode="lines",
                       line={"color": LIGHT_BLUE, "width": 2})
        )
    fig.update_layout(
        title="Cost of natural gas delivered to generators vs Henry Hub",
        yaxis_title="$/MMBtu",
    )
    with card("Delivered fuel cost"):
        st.plotly_chart(fig)
        st.caption(
            "Delivered cost sits above the benchmark by transport and contract terms. "
            "Widening spread raises the gas price generators actually face, which is "
            "what moves the coal-to-gas switching point — not the hub price alone."
        )
```

- [ ] **Step 2: Add imports and the call site**

```python
from pipelines.eia.pull_prices import GENERATOR_FUEL
```

Confirm `NAVY` and `LIGHT_BLUE` are imported from `core.theme` on this page. Add, near the existing gas sections:

```python
st.subheader("Delivered fuel cost")
_delivered_fuel_cost_section()
```

- [ ] **Step 3: Verify**

Run: `.venv/Scripts/pytest.exe tests/test_pages_smoke.py -k 05_us_gas_power -q`
Expected: 1 passed, including with an empty lake.

Then: `.venv/Scripts/ruff.exe check apps/` and `.venv/Scripts/mypy.exe core pipelines infra`

- [ ] **Step 4: Commit**

```bash
git add apps/dashboard/pages/05_us_gas_power.py
git commit -m "feat(page05): delivered gas cost to generators vs Henry Hub"
```

---

### Task 5: Revision behaviour, full green, and the record

**Files:**
- Modify: `tests/test_eia_prices.py`
- Modify: `pipelines/eia/CLAUDE.md`
- Modify: `specs/00_INDEX.md`

- [ ] **Step 1: Write the revision test**

The spec makes this an acceptance criterion. PMM and EPM revise prior months, and the lake must keep the latest rather than duplicating.

```python
def test_a_revised_value_replaces_its_predecessor(tmp_path, monkeypatch) -> None:
    # PMM and EPM both restate prior months. write_ts_long dedups on
    # (series_id, ts) sorted by revision_date, so the later pull must win --
    # not produce two rows for the same month.
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)

    def row(value: float, revised: str) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "series_id": ["R0000____3"], "source": ["eia"],
                "ts": [pd.Timestamp("2026-01-01")], "value": [value],
                "unit": ["$/bbl"], "geo": ["US"], "freq": ["monthly"],
                "revision_date": [pd.Timestamp(revised)],
            }
        )

    storage.write_ts_long(row(70.0, "2026-02-01"), source="eia")
    storage.write_ts_long(row(72.5, "2026-03-01"), source="eia")

    got = storage.read_ts_long(series_ids=["R0000____3"])
    assert len(got) == 1, "a revision must replace, not duplicate"
    assert got.iloc[0]["value"] == 72.5
```

If `LAKE_ROOT` is not monkeypatchable that way, read `core/storage.py` and use whatever isolation the existing storage tests use — **do not write to the real lake from a test.**

- [ ] **Step 2: Run the full suite**

Run: `.venv/Scripts/pytest.exe`
Expected: all pass. A concurrent session works in this repo; if a test fails in a file this plan never touched, **report it, do not fix it.**

- [ ] **Step 3: Lint and typecheck**

Run: `.venv/Scripts/ruff.exe check .` then `.venv/Scripts/mypy.exe core pipelines infra`

- [ ] **Step 4: Record the real outcome**

Update `pipelines/eia/CLAUDE.md` with what the first real pulls actually produced — row counts per route, the frequency each route accepted, and any route that returned nothing. Then change `specs/00_INDEX.md`'s Spec 30 status from `not started` to a plain-spoken summary in the register the Spec 18–21 rows use: what shipped, the `natural-gas/pri/fut` decision and its reason, and anything that did not work.

- [ ] **Step 5: Commit**

```bash
git add tests/test_eia_prices.py pipelines/eia/CLAUDE.md specs/00_INDEX.md
git commit -m "docs(spec30): record real implementation outcomes"
```

---

## Self-Review

**Spec coverage:** Session A's live verification → Task 0. The four price families → Tasks 1 and 2. The `natural-gas/pri/fut` decision → Task 0 Step 3. Scheduling → Task 2 Step 5. The three charts the spec's visualisation section names → Tasks 3 and 4. Revision behaviour → Task 5 Step 1. Native series IDs, unconverted units, no new schema → Global Constraints, enforced by `validate_ts_long` in every test.

**Known gap, deliberate:** the spec names "landed cost by API gravity band" as chart 2 on `20_cracks.py`. Task 0 must first establish whether `petroleum/pri/rac2` or a sibling route actually carries a gravity-banded series. If it does not, that chart is dropped and the finding recorded — building a gravity chart from a route that has no gravity facet would be inventing data. Task 3 ships the two charts that are certain.

**Type consistency:** `pull_group(client, route, series, frequency) -> pd.DataFrame` and `pull_all(groups) -> list[pd.DataFrame]` keep the same signatures in Tasks 1, 2 and their tests. `RAC`, `RETAIL`, `GAS`, `GENERATOR_FUEL` are all `list[str]` and are the names Tasks 3 and 4 import.

**Risk to watch:** every series code in Tasks 1 and 2 is a **placeholder**. Task 0 replaces them with live discoveries, and its findings take precedence over anything written here.
