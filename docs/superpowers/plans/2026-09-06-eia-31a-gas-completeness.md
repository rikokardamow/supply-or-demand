# Spec 31A — Gas Completeness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the lake the two things its gas coverage is missing — storage **capacity**, so weekly volumes can finally be expressed as percent full, and **consumption by sector**, so the gas pipeline carries demand as well as supply.

**Architecture:** Two new routes on the existing `EIAClient`, each a small `pull_*.py` in `pipelines/eia/` following `pull_gas_storage.py`'s shape. No new client, no new package, no schema change. One page section reuses the fullness treatment `02_gas_storage.py` already applies to European AGSI+ data.

**Tech Stack:** Python 3.12, `pipelines/eia/client.py` (`list_series`, `get_series`), `core.storage.write_ts_long`, `core.failures`, pandas, plotly, streamlit. Tests: pytest + vcrpy cassettes.

**Spec:** `specs/31_eia-coverage-extensions.md` (items 1 and 3)

**Scope note:** Spec 31 has six independent items. This plan covers items **1 (storage capacity)** and **3 (consumption by sector)** only — the two that share a route family and a page. Items 2, 4, 5 and 6 get their own plans, written after Task 0's discovery, because Spec 30 proved that plans written before discovery get invalidated by it.

## Global Constraints

Copied from the spec and root `CLAUDE.md`. Every task's requirements implicitly include this section.

- **Never guess a series code.** Discover every one via `EIAClient.list_series(route)` (`facet/series`). Spec 30's discovery found a route its own plan had written off; Spec 17 shipped a wrong ticker that only a live lookup caught.
- **Some routes have no `series` facet.** `electricity/electric-power-operational-data` returns 400 there and needs `get_operational_series` instead. **Verify which shape each route uses** — assume neither.
- **A wrong `frequency` returns empty, not an error** on some routes. Confirm accepted values live.
- **EIA publishes real `value: null` rows.** `get_series`, `get_operational_series` and `get_flows` now skip them and print the dropped count. Do not reintroduce an unconditional `float()`.
- **Units stored exactly as EIA publishes them, never converted at ingest** — `Bcf`, `MMcf`. Conversion belongs in `core/`.
- **Series IDs stay in EIA's native form** (`NW2_EPG0_SWO_R48_BCF` style), matching the existing routes in `pipelines/eia/`. Not the dotted style of Specs 17–29.
- **Never select a series by list index.** Spec 30 shipped `GENERATOR_FUEL[0]`, where reordering a constant would have plotted the wrong unit against a price axis, raising nothing. Use named constants.
- **Never read the lake unbounded.** `read_ts_long` takes `source` and `series_prefix`; `source` narrows the parquet glob itself. An unbounded read grew until it failed as a `pickle.dumps` error inside `st.cache_data`, pointing nowhere near the read.
- **Cycle a palette by index, never `zip(..., strict=False)`** against a fixed tuple — it silently drops series past the tuple's length.
- `source="eia"`, `freq` as published, no new schema, no new pipeline package.
- Per-route resilience via `core.failures`; a wholly failed run must raise so the exit status is honest.
- British English; `from __future__ import annotations`; typed throughout.
- Repo venv: `.venv/Scripts/python.exe`, `pytest.exe`, `ruff.exe`, `mypy.exe`. Bare commands are **not** on PATH.
- **`apps/dashboard/**` and `core/theme.py` belong to a concurrent design session.** Task 3 requires their permission and is blocked until granted. Never `git add -A`.

---

### Task 0: Discover every route this spec needs — all six items, no pull code

Discovery is cheap and shared. Walking all six items' routes now de-risks the two later plans as well as this one. **No pull code, no tests** — the deliverable is recorded findings.

**Files:**
- Modify: `pipelines/eia/CLAUDE.md` (append a "Spec 31 routes" section)

**Interfaces:**
- Consumes: `EIAClient.list_series(route) -> list[dict[str, str]]` (exists).
- Produces: the real series codes and query shapes Tasks 1–2 and the later 31B/31C plans code against.

- [ ] **Step 1: Walk every candidate route**

Throwaway script, do **not** commit:

```python
from pipelines.eia.client import EIAClient

ROUTES = [
    "natural-gas/stor/cap",            # item 1 — this plan
    "natural-gas/cons/sum",            # item 3 — this plan
    "electricity/rto/region-data",     # item 2 — plan 31B
    "electricity/rto/fuel-type-data",  # item 2 — plan 31B
    "electricity/rto/interchange-data",# item 2 — plan 31B
    "coal/consumption-and-quality",    # item 4 — plan 31C
    "petroleum/pnp/capbio",            # item 5 — plan 31C
    "petroleum/pnp/feedbiofuel",       # item 5 — plan 31C
    "petroleum/pnp/wprode",            # item 6 — plan 31C
]

client = EIAClient()
for route in ROUTES:
    try:
        facets = client.list_series(route)
    except Exception as exc:
        print(f"\n== {route}: NO SERIES FACET / FAILED — {type(exc).__name__}: {exc}")
        continue
    print(f"\n== {route}: {len(facets)} series")
    for f in facets[:25]:
        print("   ", f.get("id"), "|", f.get("name"))
```

**A route that raises here is a finding, not a failure** — it means the route is not series-based and needs `get_operational_series`'s facet shape instead, exactly as `electricity/electric-power-operational-data` did in Spec 30. Record which shape each route uses.

- [ ] **Step 2: For the two routes this plan uses, pick the codes**

- **`natural-gas/stor/cap`** — working gas capacity at the same regions `pull_gas_storage.py` already ingests: L48, East, Midwest, South Central (plus salt/nonsalt if published), Mountain, Pacific. **Match the existing regions** so the fullness ratio has a denominator for every numerator already in the lake.
- **`natural-gas/cons/sum`** — US national residential, commercial, industrial and electric-power deliveries. National only; state-level is out of scope for this plan.

At most 12 codes per route.

- [ ] **Step 3: Check the `area-name` quirk and the accepted frequency**

`pull_gas_storage.py` passes an explicit `geo_map` because `natural-gas/stor/wkly` returns `area-name` as the literal string `"NA"` for every row. `petroleum/pri/land3` had the same quirk.

**Check both routes.** Pull one series from each and inspect the `geo` column:

```python
df = client.get_series(route="natural-gas/stor/cap", series=[<one code>], frequency="monthly")
print(df[["series_id", "ts", "value", "unit", "geo"]].head())
print("distinct geo:", sorted(set(df["geo"])))
```

If `geo` comes back `"NA"`, that route needs an explicit `geo_map`. Also confirm which `frequency` each route accepts — a wrong one returns empty rather than erroring.

- [ ] **Step 4: Record the findings**

Append to `pipelines/eia/CLAUDE.md`, following that file's existing style — state what was confirmed live versus documented, and record negatives:

```markdown
## Spec 31 routes — confirmed live [DATE]

| Route | Series facet? | Count | Codes used | Frequency | geo quirk | Item |
|---|---|---|---|---|---|---|
| natural-gas/stor/cap | | | | | | 1 (31A) |
| natural-gas/cons/sum | | | | | | 3 (31A) |
| electricity/rto/region-data | | | | | | 2 (31B) |
| electricity/rto/fuel-type-data | | | | | | 2 (31B) |
| electricity/rto/interchange-data | | | | | | 2 (31B) |
| coal/consumption-and-quality | | | | | | 4 (31C) |
| petroleum/pnp/capbio | | | | | | 5 (31C) |
| petroleum/pnp/feedbiofuel | | | | | | 5 (31C) |
| petroleum/pnp/wprode | | | | | | 6 (31C) |

**Routes with no series facet (need get_operational_series):** [real list, or "none"]
**Routes that failed or returned nothing:** [real list, or "none"]
```

Every bracket replaced with a real value. A committed `[DATE]` is a task failure.

- [ ] **Step 5: Commit**

```bash
git add pipelines/eia/CLAUDE.md
git commit -m "docs(eia): live-discovered routes for Spec 31"
```

---

### Task 1: Storage capacity pull

**Files:**
- Create: `pipelines/eia/pull_gas_capacity.py`
- Test: `tests/test_eia_gas_capacity.py`

**Interfaces:**
- Consumes: `EIAClient.get_series(route, series, frequency, geo_map=None) -> pd.DataFrame`; Task 0's codes.
- Produces: `CAPACITY_GEO_MAP: dict[str, str]` and `main() -> None`. Task 3's page section reads the resulting series.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eia_gas_capacity.py
from __future__ import annotations

import pytest
from core.schemas import validate_ts_long
from pipelines.eia import pull_gas_capacity


@pytest.mark.vcr
def test_capacity_returns_valid_ts_long_with_real_regions() -> None:
    df = pull_gas_capacity.pull_capacity(pull_gas_capacity.EIAClient())

    validate_ts_long(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    # geo must be a real region label, never the literal "NA" this route family
    # returns in area-name (the quirk pull_gas_storage.py already works around).
    assert "NA" not in set(df["geo"])
    assert set(df["geo"]).issubset(set(pull_gas_capacity.CAPACITY_GEO_MAP.values()))


@pytest.mark.vcr
def test_every_capacity_region_has_a_matching_storage_region() -> None:
    # The whole point of this pull is to give the storage volumes already in the
    # lake a denominator. A capacity region with no storage counterpart cannot be
    # turned into a fullness ratio, so the two maps must line up.
    from pipelines.eia.pull_gas_storage import STORAGE_GEO_MAP

    capacity_regions = set(pull_gas_capacity.CAPACITY_GEO_MAP.values())
    storage_regions = set(STORAGE_GEO_MAP.values())
    assert capacity_regions <= storage_regions, (
        f"capacity regions with no storage counterpart: {capacity_regions - storage_regions}"
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/pytest.exe tests/test_eia_gas_capacity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipelines.eia.pull_gas_capacity'`

- [ ] **Step 3: Write `pipelines/eia/pull_gas_capacity.py`**

Replace the placeholder codes and labels with Task 0's real discoveries. Include `geo_map` only if Task 0 found the `"NA"` quirk on this route; if `area-name` is genuinely populated, drop it and say so in the docstring.

```python
"""Spec 31 item 1: working gas storage capacity, the denominator the lake was missing.

pipelines/eia/pull_gas_storage.py ingests weekly working gas in storage, so the lake
can report Bcf but not percent full -- and heading into winter the fullness ratio is
the number that matters. This pull supplies capacity for the same regions.

Region labels deliberately match STORAGE_GEO_MAP's, so every stored volume has a
capacity to divide by. See pipelines/eia/CLAUDE.md for the live-confirmed codes."""

from __future__ import annotations

from core.failures import failure_scope
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient

CAPACITY_GEO_MAP: dict[str, str] = {
    "NGSCPF00_NUS_MMCF_M": "L48",
    "NGSCPF00_R31_MMCF_M": "East",
    "NGSCPF00_R32_MMCF_M": "Midwest",
    "NGSCPF00_R33_MMCF_M": "SouthCentral",
    "NGSCPF00_R34_MMCF_M": "Mountain",
    "NGSCPF00_R35_MMCF_M": "Pacific",
}

CAPACITY_ROUTE = "natural-gas/stor/cap"
CAPACITY_FREQUENCY = "monthly"


def pull_capacity(client: EIAClient):
    """One route's rows. Separate from main so a cassette test can exercise it directly."""
    return client.get_series(
        route=CAPACITY_ROUTE,
        series=list(CAPACITY_GEO_MAP),
        frequency=CAPACITY_FREQUENCY,
        geo_map=CAPACITY_GEO_MAP,
    )


def main() -> None:
    with failure_scope("eia.pull_gas_capacity"):
        df = pull_capacity(EIAClient())
        if df.empty:
            print("no gas capacity rows pulled", flush=True)
            return
        write_ts_long(df, source="eia")
        print(f"wrote {len(df)} gas capacity rows across {df['geo'].nunique()} regions", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Record the cassette and run green**

Run: `.venv/Scripts/pytest.exe tests/test_eia_gas_capacity.py -v --record-mode=once`
Then replay: `.venv/Scripts/pytest.exe tests/test_eia_gas_capacity.py -v`
Expected: 2 passed.

**Inspect the cassette before committing.** EIA authenticates by `api_key` query parameter **and echoes it back in response bodies**; `tests/conftest.py` scrubs both. Confirm no real key survives in either place.

- [ ] **Step 5: Commit**

```bash
git add pipelines/eia/pull_gas_capacity.py tests/test_eia_gas_capacity.py tests/cassettes/test_eia_gas_capacity/
git commit -m "feat(eia): working gas storage capacity, the fullness denominator"
```

---

### Task 2: Gas consumption by sector, and scheduling

**Files:**
- Create: `pipelines/eia/pull_gas_consumption.py`
- Test: `tests/test_eia_gas_consumption.py`
- Modify: `infra/run_scheduled.py`

**Interfaces:**
- Consumes: `EIAClient.get_series`; Task 0's codes.
- Produces: `CONSUMPTION: list[str]`, named per-sector constants, and `main() -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eia_gas_consumption.py
from __future__ import annotations

import pytest
from core.schemas import validate_ts_long
from pipelines.eia import pull_gas_consumption


@pytest.mark.vcr
def test_consumption_returns_valid_ts_long_for_every_sector() -> None:
    df = pull_gas_consumption.pull_consumption(pull_gas_consumption.EIAClient())

    validate_ts_long(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    # Every requested sector must come back with rows. A sector that silently
    # returns nothing would leave a gap in the demand picture that no error reports.
    assert set(df["series_id"]) == set(pull_gas_consumption.CONSUMPTION)


def test_sectors_are_named_constants_not_positional() -> None:
    # Spec 30 shipped GENERATOR_FUEL[0]; reordering that list would have plotted the
    # wrong unit against a price axis, raising nothing. Sectors are selected by name.
    assert pull_gas_consumption.RESIDENTIAL in pull_gas_consumption.CONSUMPTION
    assert pull_gas_consumption.ELECTRIC_POWER in pull_gas_consumption.CONSUMPTION
    assert len(set(pull_gas_consumption.CONSUMPTION)) == len(pull_gas_consumption.CONSUMPTION)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/pytest.exe tests/test_eia_gas_consumption.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipelines.eia.pull_gas_consumption'`

- [ ] **Step 3: Write `pipelines/eia/pull_gas_consumption.py`**

Replace placeholder codes with Task 0's real discoveries.

```python
"""Spec 31 item 3: natural gas consumption by sector -- the demand side.

The gas pipeline carries supply (production, storage, exports) and no demand at all.
Residential, commercial, industrial and electric-power deliveries complete the balance.
National only; state-level is deferred. See pipelines/eia/CLAUDE.md for live-confirmed codes."""

from __future__ import annotations

from core.failures import failure_scope
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient

# Named, never selected by index -- see this module's test.
RESIDENTIAL = "N3010US2"
COMMERCIAL = "N3020US2"
INDUSTRIAL = "N3035US2"
ELECTRIC_POWER = "N3045US2"

CONSUMPTION: list[str] = [RESIDENTIAL, COMMERCIAL, INDUSTRIAL, ELECTRIC_POWER]

CONSUMPTION_ROUTE = "natural-gas/cons/sum"
CONSUMPTION_FREQUENCY = "monthly"


def pull_consumption(client: EIAClient):
    return client.get_series(
        route=CONSUMPTION_ROUTE, series=CONSUMPTION, frequency=CONSUMPTION_FREQUENCY
    )


def main() -> None:
    with failure_scope("eia.pull_gas_consumption"):
        df = pull_consumption(EIAClient())
        if df.empty:
            print("no gas consumption rows pulled", flush=True)
            return
        write_ts_long(df, source="eia")
        print(f"wrote {len(df)} gas consumption rows", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Register both pulls in the scheduler**

In `infra/run_scheduled.py`, add to the monthly group:

```python
        ("eia_gas_capacity", "pipelines.eia.pull_gas_capacity"),
        ("eia_gas_consumption", "pipelines.eia.pull_gas_consumption"),
```

**Check `git status` first** — a concurrent session owns the rest of that file. Add only these two lines. If their edit conflicts, **report it rather than resolving it**.

- [ ] **Step 5: Record the cassette and run green**

Run: `.venv/Scripts/pytest.exe tests/test_eia_gas_consumption.py -v --record-mode=once` then replay.
Also run: `.venv/Scripts/pytest.exe tests/test_run_scheduled.py -q`
Expected: all pass. Inspect the cassette for a leaked key as in Task 1.

- [ ] **Step 6: Commit**

```bash
git add pipelines/eia/pull_gas_consumption.py tests/test_eia_gas_consumption.py tests/cassettes/test_eia_gas_consumption/ infra/run_scheduled.py
git commit -m "feat(eia): natural gas consumption by sector, and schedule both gas pulls"
```

---

### Task 3: US storage fullness section — BLOCKED until the design session grants a window

**Do not start this task without confirming the window is open.** `apps/dashboard/**` belongs to a concurrent design session mid-restyle. They have granted narrow windows before, on these terms: land before their Task 10 (which deletes `card()`), use the current `card(...)` idiom rather than the `section()` they are migrating to, keep changes additive, and report the exact `card(...)` and `title=` strings afterwards.

**The controller must obtain that window before dispatching this task.**

**Files:**
- Modify: `apps/dashboard/pages/02_gas_storage.py`

**Interfaces:**
- Consumes: `CAPACITY_GEO_MAP` from `pipelines.eia.pull_gas_capacity`; `STORAGE_GEO_MAP` from `pipelines.eia.pull_gas_storage`; `read_ts_long`, `card`, and the page's existing imports.

- [ ] **Step 1: Read how the page already does this for Europe**

`_fullness_bars_section(geo)` at `apps/dashboard/pages/02_gas_storage.py:113` builds Current / M-1 / Y-1 rows and passes them to `core.theme.fullness_comparison_bars(rows, unit_abs, date_label, title)`. It works because AGSI+ publishes `full_pct` and `working_gas_volume` directly.

**Mirror that treatment for US regions**, computing the percentage yourself from storage ÷ capacity. Do not invent a new chart style — the page already has one for exactly this idea, and matching it is both less work and more consistent.

- [ ] **Step 2: Add the section**

**A final-review correction to this sketch, made before Task 3 is picked up (it is
currently deferred and blocked — see below): the original code divided storage (Bcf) by
capacity (MMcf) directly, and it divided every historical row by TODAY's capacity.**
Both are wrong and both are fixed in the corrected sketch below.

1. **Unit conversion.** Storage is Bcf, capacity is MMcf (1 Bcf = 1,000 MMcf) —
   `pipelines/eia/pull_gas_capacity.py::fullness_pct(storage_bcf, capacity_mmcf)` is the
   presentation-time helper that now exists for exactly this; call it instead of dividing
   inline. The original inline `stored / capacity * 100` divides Bcf by MMcf directly and
   would render roughly 0.07% where the truth is roughly 70%.
2. **As-of capacity join for M-1/Y-1.** Capacity is monthly and gets revised upward over
   time (see `pipelines/eia/CLAUDE.md`'s Task 1 note), so a year-ago fullness figure must
   be divided by the capacity **in force at that time**, not today's `iloc[-1]` value —
   otherwise a real past fullness is silently and plausibly understated by however much
   capacity has grown since. The fix is a second `nearest_value_at_offset` call against
   the capacity series at the same as-of timestamp, not a single `latest_capacity` reused
   for every row.

```python
def _us_fullness_section(region: str) -> None:
    """US storage as percent of working gas capacity. AGSI+ publishes full_pct for
    Europe directly; EIA publishes volume (Bcf) and capacity (MMcf) separately, so the
    ratio is computed here via fullness_pct, which also applies the MMcf->Bcf conversion.

    SouthCentral_Salt and SouthCentral_Nonsalt have no capacity denominator at all (see
    pipelines/eia/CLAUDE.md) -- capacity_id resolves to None for both, and the section
    must show its "no pair" message rather than error or fall back to a guessed figure."""
    storage_id = next(
        (code for code, geo in STORAGE_GEO_MAP.items() if geo == region), None
    )
    capacity_id = next(
        (code for code, geo in CAPACITY_GEO_MAP.items() if geo == region), None
    )
    if storage_id is None or capacity_id is None:
        st.info(f"No US storage/capacity pair for {region}.")
        return

    stored = _series_by_ts(storage_id)
    capacity = _series_by_ts(capacity_id)
    if stored.empty or capacity.empty:
        st.info("No US capacity yet — run `pipelines/eia/pull_gas_capacity.py`.")
        return

    latest_ts = stored.index.max()
    latest_capacity = float(capacity.iloc[-1])
    if latest_capacity <= 0:
        st.info(f"No usable capacity figure for {region}.")
        return

    rows = [
        ("Current", fullness_pct(float(stored.iloc[-1]), latest_capacity), float(stored.iloc[-1]))
    ]
    for label, days_back in [("M-1", 30), ("Y-1", 365)]:
        as_of = latest_ts - pd.Timedelta(days=days_back)
        prior = nearest_value_at_offset(stored, as_of)
        # Capacity is revised and grows over time -- join the capacity row IN FORCE AT
        # THIS AS-OF MONTH, not today's latest_capacity. Reusing latest_capacity here
        # would silently understate every historical fullness figure by however much
        # capacity has grown since that date.
        prior_capacity = nearest_value_at_offset(capacity, as_of)
        if prior is not None and prior_capacity is not None and prior_capacity > 0:
            rows.append((label, fullness_pct(prior, prior_capacity), prior))

    fig = fullness_comparison_bars(
        rows,
        unit_abs="Bcf",
        date_label=latest_ts.strftime("%d-%b-%Y"),
        title=f"US {region} Storage Fullness",
    )
    with card(f"US {region} Storage Fullness"):
        st.plotly_chart(fig)
        st.caption(
            "Percent of working gas capacity. Capacity is reported monthly and revised "
            "occasionally, so the denominator moves in steps rather than continuously."
        )
```

Add the imports it needs (`CAPACITY_GEO_MAP`, `STORAGE_GEO_MAP`, `fullness_pct` from
`pipelines.eia.pull_gas_capacity`) and a call site under a `st.subheader("US storage")`,
placed **after** the existing European sections so nothing pre-existing moves.

- [ ] **Step 3: Verify**

Run: `.venv/Scripts/pytest.exe tests/test_pages_smoke.py -k 02_gas_storage -q`
Expected: 1 passed — including with no capacity data in the lake, which the `st.info` branches prove.

Then `.venv/Scripts/ruff.exe check apps/` and `.venv/Scripts/mypy.exe core pipelines infra`.

- [ ] **Step 4: Commit and report the strings**

```bash
git add apps/dashboard/pages/02_gas_storage.py
git commit -m "feat(page02): US storage as percent of working gas capacity"
```

Report the exact `card(...)` string and chart `title=` string to the controller, who owes them to the design session.

---

### Task 4: Final gate

**Files:** none created; this task verifies and records.

- [ ] **Step 1: Run the real pulls**

```
.venv/Scripts/python.exe -m pipelines.eia.pull_gas_capacity
.venv/Scripts/python.exe -m pipelines.eia.pull_gas_consumption
```

Record the real row counts. A route failing is a finding to record, not to hide. Note that `main()` raises `PartialFailureError` on any recorded failure, so a non-zero exit with rows written is legitimate.

- [ ] **Step 2: Confirm the fullness ratio is actually computable**

```python
from core.storage import read_ts_long
from pipelines.eia.pull_gas_capacity import CAPACITY_GEO_MAP
from pipelines.eia.pull_gas_storage import STORAGE_GEO_MAP

for code, geo in CAPACITY_GEO_MAP.items():
    storage_code = next((c for c, g in STORAGE_GEO_MAP.items() if g == geo), None)
    cap = read_ts_long(series_ids=[code], source="eia")
    sto = read_ts_long(series_ids=[storage_code], source="eia") if storage_code else None
    print(geo, "capacity rows:", len(cap), "storage rows:", 0 if sto is None else len(sto))
```

Every region with capacity must have storage, and vice versa. **A mismatch is the one outcome that makes this whole plan pointless** — report it rather than papering over it. Note the reads are narrowed by `source=`, per the global constraints.

- [ ] **Step 3: Full suite, lint, typecheck**

`.venv/Scripts/pytest.exe`, then `.venv/Scripts/ruff.exe check .` and `.venv/Scripts/mypy.exe core pipelines infra`.

A concurrent session works in this repo. If a test fails in a file this plan never touched, **report it, do not fix it**.

- [ ] **Step 4: Record real outcomes**

Append the real row counts and the fullness-pairing result to `pipelines/eia/CLAUDE.md`. Update `specs/00_INDEX.md`'s Spec 31 row to record what shipped for items 1 and 3, that items 2, 4, 5 and 6 remain, and anything that did not work — in the plain-spoken register the Spec 18–21 rows use.

- [ ] **Step 5: Commit**

```bash
git add pipelines/eia/CLAUDE.md specs/00_INDEX.md
git commit -m "docs(spec31a): record real outcomes for gas capacity and consumption"
```

---

## Self-Review

**Spec coverage:** item 1 → Tasks 1 and 3; item 3 → Task 2; the spec's "live route verification before pull code" → Task 0; scheduling → Task 2 Step 4; acceptance criteria → Task 4. Items 2, 4, 5 and 6 are explicitly out of this plan and named as such.

**Known gap, deliberate:** Task 3 is blocked on another session's permission and may not land in this plan's run. Tasks 1, 2 and 4 are independently valuable — the capacity and consumption data reach the lake regardless, and the chart follows when the window opens. The plan must not stall on it.

**Type consistency:** `CAPACITY_GEO_MAP: dict[str, str]` and `STORAGE_GEO_MAP: dict[str, str]` map code → region label in the same direction, which Task 1's pairing test and Task 3's lookups both rely on. `pull_capacity(client)` and `pull_consumption(client)` take the same single argument.

**Risk to watch:** every series code in Tasks 1 and 2 is a **placeholder**. Task 0 replaces them, and its findings take precedence over anything written here — the same discipline that caught three plan defects in Spec 30.
