# Oil Demand Elasticity Port — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refit the demand half of the `oil_demand.xlsx` workbook — the GDP elasticity of oil
demand for the US, China and the euro area — on confirmed public data, with and without the
pandemic, and show it on a page with a full model card.

**Architecture:** Two keyless ingests (JODI's secondary table for monthly country demand, the
OECD's Quarterly National Accounts for real GDP growth), pure regression arithmetic in
`core/oil_demand.py`, a derived pipeline writing `derived.oil_demand.*`, and one page. The
forward path is a committed CSV of user-set GDP assumptions, written to the lake under a
`.scenario` id so it can never be read as an observation.

**Tech Stack:** Python 3.12, pandas, statsmodels (already a dependency), duckdb, requests,
pytest + vcrpy cassettes, streamlit, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-10-10-oil-demand-model-mapping.md` — read its "Routes
confirmed live, 2026-10-10" section before Task 1. Every URL, key, column name and country
code in this plan was read from a live response on that date.

**What was measured before this plan was written.** The arithmetic in Task 3 was run on the
real 2012–2026 panel on 2026-10-10. The results shape the plan, so they are stated here; they
are this repo's own estimates on public data, not workbook figures.

| Block | n | Slope, full panel | R² | Slope, ex-pandemic | R² | Out-of-sample vs no-change |
|---|---|---|---|---|---|---|
| US | 54 | 2.43 | 0.88 | 1.70 | 0.26 | pass, 2 exceptions in 8 |
| China | 54 | 0.52 (p = 0.17) | 0.04 | 0.97 (p = 0.20) | 0.04 | pass, 5 exceptions in 8 |
| Euro area ex Malta | 54 | 1.40 | 0.78 | 1.73 | 0.48 | — |

Three things follow, and the page must say all three:

1. **The US fit is mostly the pandemic.** R² falls from 0.88 to 0.26 when 2020–2021 leaves
   the panel. The spec predicted exactly this.
2. **China has no statistically significant elasticity on public data**, in either panel.
   That is a finding, not a bug to tune away. Publish the fit with its p-value and do not
   offer a China scenario path from it without that caveat on the same exhibit.
3. **The euro area needs a fixed basket.** Malta is missing seven months (2015-09 → 2016-01,
   2017-05, 2026-07) and is 0.29 % of the twenty-member sum. With Malta in, the completeness
   rule discards eight quarters of regression panel; with Malta out, none. The model basket is
   the nineteen other members, labelled "euro area ex Malta" wherever it appears.

## Global Constraints

- Python 3.12. Ask before adding any dependency. Nothing here needs one.
- All scalar series conform to `ts_long(series_id, source, ts, value, unit, geo, freq, revision_date)` — `core/schemas.py`. Do not change the schema.
- Neither route needs a key. Add nothing to `core.settings` or `.env`.
- `core/` modules never touch DuckDB. Pipelines write the lake; pages read it and never call an API.
- **No data is not zero.** An absent input yields NaN and writes no row. A degenerate input fails loudly and visibly.
- **A partial aggregate is no observation.** A euro-area quarter with any basket member missing any month is NaN, never a smaller sum.
- **An assumption is never an observation.** Rows derived from the user's GDP assumptions carry `.scenario` in the series id. No other id may hold them.
- The pandemic window is **2020-Q1 to 2021-Q4 inclusive**, defined once as `core.oil_demand.PANDEMIC_WINDOW`. A year-on-year change for a 2021 quarter is measured against 2020, so dropping 2020 alone leaves its base effect in.
- The specification is year-on-year percentage change on both sides, for every block. It is **not** the workbook's, whose USA block regresses on a level change in US$bn. Workbook coefficients are a diagnostic shown beside ours, never a target.
- Licensed workbook figures never enter a tracked file — no coefficient, R², p-value or panel value from `oil_demand.xlsx`, in code, tests, docs or commit messages. Every test figure is synthetic.
- `freq` uses pandas aliases: `"M"` and `"Q"`. `ts` is the period start.
- Series ids are lowercase and dotted. `geo` is ISO 3166-1 alpha-2, plus `EA`.
- British English in all prose, labels and docstrings.
- Charts use `core.theme`; no ad-hoc colours. Pages use `components.section`. No `fig.update_layout(title=...)`, no `use_container_width`.
- Nothing in this plan is registered in `infra/run_scheduled.py`. Run by hand. (JODI's closed years are 27 MB each; an unattended first run downloads about 380 MB.)
- End green: `ruff check .`, `mypy core pipelines infra apps`, `pytest`.

## Review Focus

Inputs the spec implies and a person will hit, most likely first. Each has a test in the task
that owns the code.

1. **The latest JODI month has a euro-area member missing** (true today: Croatia and Greece lag a month). Expected: that quarter is absent from the lake, not understated. → Task 3, `test_a_quarter_with_any_member_missing_any_month_is_no_observation`; Task 4, `test_an_incomplete_latest_quarter_writes_no_row`.
2. **An OECD area code that does not exist is requested alongside valid ones** (`EA19` beside `CHN` returns HTTP 200 and silently omits it). Expected: a loud error naming the missing area. → Task 2, `test_a_requested_area_missing_from_the_response_raises`.
3. **A quarter is missing mid-panel.** Expected: its year-on-year change and the one a year later are NaN, not a change measured across the gap. → Task 3, `test_yoy_does_not_compare_across_a_missing_quarter`.
4. **Too few overlapping quarters, or GDP growth that does not vary.** Expected: a refusal to fit, with the count, not a slope. → Task 3, `test_fit_refuses_a_short_panel` and `test_fit_refuses_a_regressor_with_no_variation`.
5. **The assumptions file has a blank cell or names a block with no fit.** Expected: the blank writes no scenario row; the unknown block raises. → Task 4, `test_a_blank_assumption_writes_no_scenario_row` and `test_an_assumption_for_an_unknown_block_raises`.

---

### Task 1: JODI secondary table — client variant and the demand pull

**Files:**
- Modify: `pipelines/jodi/client.py`
- Create: `pipelines/jodi/pull_demand.py`
- Modify: `pipelines/jodi/CLAUDE.md`
- Test: `tests/test_jodi_client.py` (add), `tests/test_jodi_demand.py` (create)

**Interfaces:**
- Consumes: `core.storage.write_ts_long`
- Produces: `client.download_annual_csv(year: int, is_current_year: bool, table: str = "primary") -> pd.DataFrame`;
  `pull_demand.EURO_AREA_20: list[str]`, `pull_demand.DEMAND_COUNTRIES: list[str]`,
  `pull_demand.filter_and_transform(raw: pd.DataFrame, revision_date: datetime) -> pd.DataFrame`;
  lake series `jodi.total_demand.<cc>` — monthly, `kb/d`, `source="jodi"`, `freq="M"`

**Why a `table` argument and not a second function:** the two tables share the host, the
seven columns, and the closed-year / current-year filename split. Only the path segment
differs. The default keeps every existing caller and test unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_jodi_client.py`:

```python
def test_download_annual_csv_reads_the_secondary_table_under_its_own_url_and_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Same filename split as the primary table, different path segment -- confirmed live
    2026-10-10. The cache name must differ too, or a secondary file would be served to a
    primary caller for the same year."""
    calls: list[str] = []

    def fake_get(url: str, timeout: int) -> _FakeResponse:
        calls.append(url)
        return _FakeResponse(_SAMPLE_CSV)

    monkeypatch.setattr(client.requests, "get", fake_get)

    client.download_annual_csv(2025, is_current_year=False, table="secondary")
    client.download_annual_csv(2026, is_current_year=True, table="secondary")
    client.download_annual_csv(2025, is_current_year=False)

    base = "https://www.jodidata.org/_resources/files/downloads/oil-data/annual-csv"
    assert calls == [
        f"{base}/secondary/2025.csv",
        f"{base}/secondary/secondaryyear2026.csv",
        f"{base}/primary/2025.csv",
    ]
    assert (tmp_path / "jodi-secondary-2025.csv").exists()
    assert (tmp_path / "jodi-primary-2025.csv").exists()


def test_download_annual_csv_rejects_an_unknown_table() -> None:
    with pytest.raises(ValueError, match="tertiary"):
        client.download_annual_csv(2025, is_current_year=False, table="tertiary")
```

Create `tests/test_jodi_demand.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from core.schemas import validate_ts_long
from pipelines.jodi.pull_demand import (
    DEMAND_COUNTRIES,
    EURO_AREA_20,
    filter_and_transform,
)

REVISION_DATE = datetime(2026, 10, 10, tzinfo=UTC)


def _row(
    ref_area: str,
    value: str,
    period: str = "2026-06",
    flow: str = "TOTDEMO",
    product: str = "TOTPRODS",
    unit: str = "KBD",
) -> dict[str, str]:
    return {
        "REF_AREA": ref_area,
        "TIME_PERIOD": period,
        "ENERGY_PRODUCT": product,
        "FLOW_BREAKDOWN": flow,
        "UNIT_MEASURE": unit,
        "OBS_VALUE": value,
        "ASSESSMENT_CODE": "3",
    }


def test_the_country_list_is_the_three_blocks() -> None:
    assert len(EURO_AREA_20) == 20
    assert len(set(EURO_AREA_20)) == 20
    assert DEMAND_COUNTRIES == ["US", "CN", *EURO_AREA_20]


def test_filter_and_transform_keeps_total_product_demand_in_kbd_only() -> None:
    raw = pd.DataFrame(
        [
            _row("US", "20000.0000"),
            _row("US", "9000.0000", product="GASOLINE"),  # one product, not the total
            _row("US", "600000.0000", unit="KBBL"),  # a volume, not a rate
            _row("US", "17000.0000", flow="REFGROUT"),  # refinery output, not demand
            _row("CN", "14000.0000"),
            _row("DE", "2000.0000"),
            _row("RU", "3500.0000"),  # not one of the three blocks
        ]
    )

    df = filter_and_transform(raw, REVISION_DATE)

    validate_ts_long(df)
    assert set(df["series_id"]) == {
        "jodi.total_demand.us",
        "jodi.total_demand.cn",
        "jodi.total_demand.de",
    }
    assert (df["unit"] == "kb/d").all()
    assert (df["freq"] == "M").all()
    assert (df["source"] == "jodi").all()
    us = df[df["series_id"] == "jodi.total_demand.us"].iloc[0]
    assert us["value"] == 20000.0
    assert us["ts"] == pd.Timestamp("2026-06-01")
    assert us["geo"] == "US"


def test_filter_and_transform_drops_not_reported_markers_rather_than_zeroing_them() -> None:
    """`-` is "not reported". Written as 0.0 it would read as a country consuming no oil."""
    raw = pd.DataFrame([_row("HR", "-"), _row("MT", "x"), _row("GR", "250.0000")])

    df = filter_and_transform(raw, REVISION_DATE)

    assert list(df["series_id"]) == ["jodi.total_demand.gr"]


def test_filter_and_transform_returns_an_empty_conformant_frame_when_nothing_matches() -> None:
    df = filter_and_transform(pd.DataFrame([_row("RU", "3500.0000")]), REVISION_DATE)

    assert df.empty
    assert list(df.columns) == [
        "series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"
    ]  # fmt: skip
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_jodi_client.py tests/test_jodi_demand.py -v`
Expected: FAIL — `TypeError: download_annual_csv() got an unexpected keyword argument 'table'`
and `ModuleNotFoundError: No module named 'pipelines.jodi.pull_demand'`.

- [ ] **Step 3: Widen the client**

In `pipelines/jodi/client.py`, replace `BASE_URL`, `_csv_url` and the body of
`download_annual_csv` (keep the existing docstring's text about `OBS_VALUE` and caching, and
keep `requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)` exactly — existing tests fake that
call signature):

```python
BASE_URL = "https://www.jodidata.org/_resources/files/downloads/oil-data/annual-csv"
TABLES = ("primary", "secondary")
CACHE_DIR = Path("data/raw/jodi")
REQUEST_TIMEOUT_SECONDS = 60


def _csv_url(year: int, is_current_year: bool, table: str = "primary") -> str:
    # Confirmed live for both tables: the current (still-in-progress) year's file is
    # "{table}year{year}.csv", prior closed years are "{year}.csv" -- not one guessable
    # pattern.
    name = f"{table}year{year}.csv" if is_current_year else f"{year}.csv"
    return f"{BASE_URL}/{table}/{name}"


def download_annual_csv(
    year: int, is_current_year: bool, table: str = "primary"
) -> pd.DataFrame:
    if table not in TABLES:
        raise ValueError(f"unknown JODI table {table!r}; expected one of {TABLES}")
    cache_path = CACHE_DIR / f"jodi-{table}-{year}.csv"
    if is_current_year or not cache_path.exists():
        url = _csv_url(year, is_current_year, table)
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(response.content)

    return pd.read_csv(cache_path, dtype={"OBS_VALUE": str})
```

Rewrite the module docstring's last sentence: the secondary table is no longer "out of scope
here" — it is read by `pull_demand.py` for total product demand.

- [ ] **Step 4: Write the demand pull**

```python
# pipelines/jodi/pull_demand.py
"""Pulls JODI-Oil total product demand for the US, China and the euro-area members into
ts_long -- the consumption side of the oil-demand elasticity (core/oil_demand.py).

Reads the SECONDARY table (refined products), not the primary one pull_jodi.py reads.
`FLOW_BREAKDOWN=TOTDEMO` + `ENERGY_PRODUCT=TOTPRODS` + `UNIT_MEASURE=KBD` is total oil
product demand per country per month, in thousand barrels a day -- confirmed live
2026-10-10, complete for the US, China and all twenty euro-area members in 2013 and 2020.

All twenty members are ingested, including Malta, whose reporting has gaps. Which members
form the model's basket is the model's decision (core.oil_demand.EURO_AREA_BASKET), not
the ingest's: the lake holds what JODI published.

Run by hand: `python -m pipelines.jodi.pull_demand`. Not registered in
infra/run_scheduled.py -- closed years are about 27 MB each and are cached after the first
run, which downloads roughly 380 MB.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
from core.storage import write_ts_long

from pipelines.jodi.client import download_annual_csv

EURO_AREA_20 = [
    "AT", "BE", "HR", "CY", "EE", "FI", "FR", "DE", "GR", "IE",
    "IT", "LV", "LT", "LU", "MT", "NL", "PT", "SK", "SI", "ES",
]  # fmt: skip

DEMAND_COUNTRIES = ["US", "CN", *EURO_AREA_20]

# The regression panel opens 1Q 2013 and is in year-on-year changes, so levels are needed
# from a year earlier.
START_YEAR = 2012

_TS_LONG_COLUMNS = [
    "series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"
]  # fmt: skip


def filter_and_transform(raw: pd.DataFrame, revision_date: datetime) -> pd.DataFrame:
    """One year's raw secondary-table CSV -> ts_long rows of total product demand.

    `-` (not reported) and `x` (confidential / not applicable) are dropped, never zeroed:
    a zero would read as a country consuming no oil that month.
    """
    keep = (
        raw["REF_AREA"].isin(DEMAND_COUNTRIES)
        & (raw["FLOW_BREAKDOWN"] == "TOTDEMO")
        & (raw["ENERGY_PRODUCT"] == "TOTPRODS")
        & (raw["UNIT_MEASURE"] == "KBD")
        & ~raw["OBS_VALUE"].isin(["-", "x"])
    )
    subset = raw[keep]
    if subset.empty:
        return pd.DataFrame(columns=_TS_LONG_COLUMNS)
    return pd.DataFrame(
        {
            "series_id": "jodi.total_demand." + subset["REF_AREA"].str.lower(),
            "source": "jodi",
            "ts": pd.to_datetime(subset["TIME_PERIOD"], format="%Y-%m"),
            "value": pd.to_numeric(subset["OBS_VALUE"]),
            "unit": "kb/d",
            "geo": subset["REF_AREA"],
            "freq": "M",
            "revision_date": revision_date,
        }
    ).reset_index(drop=True)


def main() -> None:
    end_year = date.today().year
    pulled_at = datetime.now(UTC)

    frames = []
    for year in range(START_YEAR, end_year + 1):
        raw = download_annual_csv(year, is_current_year=(year == end_year), table="secondary")
        transformed = filter_and_transform(raw, pulled_at)
        print(
            f"{year}: {len(transformed)} rows across "
            f"{transformed['geo'].nunique() if not transformed.empty else 0} countries",
            flush=True,
        )
        if not transformed.empty:
            frames.append(transformed)

    if not frames:
        raise RuntimeError(
            "JODI secondary returned no total-demand rows for any year -- the flow, product "
            "or unit code has changed. Check the columns of the downloaded file."
        )
    df = pd.concat(frames, ignore_index=True)
    write_ts_long(df, source="jodi")
    print(f"wrote {len(df)} rows across {df['series_id'].nunique()} series", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_jodi_client.py tests/test_jodi_demand.py tests/test_jodi_pull.py -v`
Expected: PASS, including every pre-existing JODI test.

- [ ] **Step 6: Correct `pipelines/jodi/CLAUDE.md`**

The heading "Two annual tables exist — … only "primary" is needed here" and its closing
sentence ("the secondary table is out of scope for this pipeline") are now wrong, and a
session that reads only this file concludes no regional consumption history exists. Rename
the heading to "Two annual tables exist — "primary" and "secondary" — both are read", and
replace that closing sentence with:

```markdown
`pull_jodi.py` reads the primary table for crude. `pull_demand.py` reads the **secondary**
table for total product demand — `TOTDEMO` / `TOTPRODS` / `KBD`, monthly per country,
confirmed live 2026-10-10 — for the US, China and the twenty euro-area members, from 2012.
It is the consumption side of `core/oil_demand.py`. In that slice the only non-numeric
marker seen is `-`. Malta has gaps (2015-09 → 2016-01, 2017-05); the latest month is
routinely missing one or two smaller members.
```

- [ ] **Step 7: Run the pull for real, once**

Run: `.venv/Scripts/python.exe -m pipelines.jodi.pull_demand`
Expected: one line per year 2012 → the current year, each closed year reporting 22 countries
and 260–264 rows, then `wrote … rows across 22 series`. This writes the real lake under
`source=jodi`; it adds series and touches no existing one. If another session is refreshing
the lake, wait for it.

- [ ] **Step 8: Commit**

```bash
git add pipelines/jodi/client.py pipelines/jodi/pull_demand.py pipelines/jodi/CLAUDE.md tests/test_jodi_client.py tests/test_jodi_demand.py
git commit -m "feat(jodi): total product demand from the secondary table"
```

---

### Task 2: OECD Quarterly National Accounts — real GDP growth

**Files:**
- Create: `pipelines/oecd/__init__.py` (empty), `pipelines/oecd/client.py`, `pipelines/oecd/pull_gdp.py`, `pipelines/oecd/CLAUDE.md`
- Modify: `core/freshness.py` (one line)
- Test: `tests/test_oecd_client.py`, `tests/test_oecd_pull.py`

**Interfaces:**
- Consumes: `core.storage.write_ts_long`
- Produces: `client.fetch_real_gdp_growth(areas: list[str], start_period: str = "2012-Q1") -> pd.DataFrame`
  with columns `REF_AREA`, `TIME_PERIOD`, `OBS_VALUE` (float), `OBS_STATUS`;
  `pull_gdp.AREA_GEO: dict[str, str]`; `pull_gdp.to_ts_long(raw: pd.DataFrame, revision_date: datetime) -> pd.DataFrame`;
  lake series `oecd.gdp_real_yoy.{us,cn,ea}` — quarterly, `% y/y`, `source="oecd"`, `freq="Q"`,
  `ts` = quarter start

**The trap this task exists to close:** an area code that does not exist returns HTTP 404
`NoRecordsFound` on its own, but HTTP **200 with that area silently omitted** when requested
beside a valid one. `EA19`, `EA20` and `EU27_2020` are all such codes; the euro area is `EA`.
The client must compare what it asked for with what came back.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_oecd_client.py
from __future__ import annotations

import pandas as pd
import pytest
from pipelines.oecd import client

_HEADER = (
    "DATAFLOW,FREQ,ADJUSTMENT,REF_AREA,SECTOR,COUNTERPART_SECTOR,TRANSACTION,INSTR_ASSET,"
    "ACTIVITY,EXPENDITURE,UNIT_MEASURE,PRICE_BASE,TRANSFORMATION,TABLE_IDENTIFIER,"
    "TIME_PERIOD,OBS_VALUE,REF_YEAR_PRICE,BASE_PER,CONF_STATUS,DECIMALS,OBS_STATUS,"
    "UNIT_MULT,CURRENCY\n"
)


def _line(area: str, period: str, value: str) -> str:
    return (
        f"OECD.SDD.NAD:DSD_NAMAIN1@DF_QNA(1.1),Q,Y,{area},S1,S1,B1GQ,_Z,_Z,_Z,PC,L,GY,"
        f"T0102,{period},{value},,,F,1,A,0,_Z\n"
    )


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise client.requests.HTTPError(f"{self.status_code}")


def test_the_key_asks_for_seasonally_adjusted_real_growth_on_a_year_earlier() -> None:
    """Q = quarterly, Y = seasonally adjusted, B1GQ = GDP, L = chain-linked volume (real),
    GY = growth on the same quarter a year earlier. Read off a live response 2026-10-10."""
    assert client.real_gdp_growth_key(["CHN", "USA", "EA"]) == "Q.Y.CHN+USA+EA...B1GQ.....L.GY."


def test_fetch_parses_the_sdmx_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_get(url: str, params: dict[str, str], timeout: int) -> _FakeResponse:
        seen["url"] = url
        seen["params"] = params
        return _FakeResponse(
            _HEADER + _line("CHN", "2026-Q1", "5") + _line("CHN", "2026-Q2", "4.3")
        )

    monkeypatch.setattr(client.requests, "get", fake_get)

    df = client.fetch_real_gdp_growth(["CHN"], start_period="2026-Q1")

    assert seen["url"] == f"{client.BASE_URL}/Q.Y.CHN...B1GQ.....L.GY."
    assert seen["params"] == {"startPeriod": "2026-Q1", "format": "csvfile"}
    assert list(df.columns) == ["REF_AREA", "TIME_PERIOD", "OBS_VALUE", "OBS_STATUS"]
    assert df["OBS_VALUE"].tolist() == [5.0, 4.3]
    assert pd.api.types.is_float_dtype(df["OBS_VALUE"])


def test_a_requested_area_missing_from_the_response_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EA19 beside CHN returns HTTP 200 and just leaves EA19 out -- confirmed live. Without
    this check the euro area vanishes from the lake and nothing fails."""
    monkeypatch.setattr(
        client.requests,
        "get",
        lambda url, params, timeout: _FakeResponse(_HEADER + _line("CHN", "2026-Q2", "4.3")),
    )

    with pytest.raises(ValueError, match="EA19"):
        client.fetch_real_gdp_growth(["CHN", "EA19"])


def test_a_response_that_is_not_the_expected_csv_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        client.requests, "get", lambda url, params, timeout: _FakeResponse("<html>busy</html>")
    )

    with pytest.raises(ValueError, match="REF_AREA"):
        client.fetch_real_gdp_growth(["CHN"])


@pytest.mark.vcr
def test_fetch_real_gdp_growth_live_shape() -> None:
    """Recorded once against the real service. Pins the three area codes the model uses --
    above all that the euro area is `EA`."""
    df = client.fetch_real_gdp_growth(["CHN", "USA", "EA"], start_period="2024-Q1")

    assert set(df["REF_AREA"]) == {"CHN", "USA", "EA"}
    assert df["TIME_PERIOD"].str.fullmatch(r"\d{4}-Q[1-4]").all()
    assert df["OBS_VALUE"].between(-30, 30).all(), "a growth rate, not a level"
    assert not df.duplicated(["REF_AREA", "TIME_PERIOD"]).any()
```

```python
# tests/test_oecd_pull.py
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from core.schemas import validate_ts_long
from pipelines.oecd.pull_gdp import AREA_GEO, to_ts_long

REVISION_DATE = datetime(2026, 10, 10, tzinfo=UTC)


def test_area_codes_map_to_the_lakes_geo_codes() -> None:
    assert AREA_GEO == {"USA": "US", "CHN": "CN", "EA": "EA"}


def test_to_ts_long_stamps_the_quarter_start_and_the_real_yoy_unit() -> None:
    raw = pd.DataFrame(
        {
            "REF_AREA": ["CHN", "CHN", "EA"],
            "TIME_PERIOD": ["2026-Q1", "2026-Q2", "2025-Q4"],
            "OBS_VALUE": [5.0, 4.3, 1.2],
            "OBS_STATUS": ["A", "A", "A"],
        }
    )

    df = to_ts_long(raw, REVISION_DATE)

    validate_ts_long(df)
    cn = df[df["series_id"] == "oecd.gdp_real_yoy.cn"].sort_values("ts")
    assert cn["ts"].tolist() == [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-01")]
    assert cn["value"].tolist() == [5.0, 4.3]
    ea = df[df["series_id"] == "oecd.gdp_real_yoy.ea"].iloc[0]
    assert ea["ts"] == pd.Timestamp("2025-10-01")
    assert ea["geo"] == "EA"
    assert (df["unit"] == "% y/y").all()
    assert (df["freq"] == "Q").all()
    assert (df["source"] == "oecd").all()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_oecd_client.py tests/test_oecd_pull.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipelines.oecd'`.

- [ ] **Step 3: Write the client**

Create an empty `pipelines/oecd/__init__.py`, then:

```python
# pipelines/oecd/client.py
"""OECD Quarterly National Accounts client -- keyless SDMX, CSV out.

Confirmed live 2026-10-10. The one series this client fetches is seasonally adjusted real
GDP growth on the same quarter a year earlier:

    Q . Y . {areas} ... B1GQ ..... L . GY .
    |   |               |          |   `- TRANSFORMATION: growth on a year earlier
    |   |               |          `----- PRICE_BASE: chain-linked volume, i.e. real
    |   |               `---------------- TRANSACTION: gross domestic product
    |   `-------------------------------- ADJUSTMENT: seasonally adjusted
    `------------------------------------ FREQ: quarterly

China publishes no chain-linked LEVEL on this dataflow -- only nominal levels and the two
growth transformations -- so growth is the only real China series available here.

An unknown area code is the trap. Alone it returns HTTP 404 `NoRecordsFound`; beside a
valid code it returns HTTP 200 with that area silently left out. `EA19`, `EA20` and
`EU27_2020` -- the codes Eurostat and FRED use -- are all unknown here. The euro area is
`EA`. `fetch_real_gdp_growth` therefore checks that every area it asked for came back.
"""

from __future__ import annotations

import io

import pandas as pd
import requests

BASE_URL = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA,1.1"
REQUEST_TIMEOUT_SECONDS = 120

_COLUMNS = ["REF_AREA", "TIME_PERIOD", "OBS_VALUE", "OBS_STATUS"]


def real_gdp_growth_key(areas: list[str]) -> str:
    return f"Q.Y.{'+'.join(areas)}...B1GQ.....L.GY."


def fetch_real_gdp_growth(areas: list[str], start_period: str = "2012-Q1") -> pd.DataFrame:
    """One row per area per quarter: `REF_AREA`, `TIME_PERIOD` (`yyyy-Qn`), `OBS_VALUE`
    (percent, float), `OBS_STATUS`. Raises if any requested area is absent."""
    response = requests.get(
        f"{BASE_URL}/{real_gdp_growth_key(areas)}",
        params={"startPeriod": start_period, "format": "csvfile"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    raw = pd.read_csv(io.StringIO(response.text), dtype=str)
    absent_columns = [column for column in _COLUMNS if column not in raw.columns]
    if absent_columns:
        raise ValueError(
            f"OECD response is not the expected SDMX CSV: no {absent_columns} column(s). "
            f"Got columns {list(raw.columns)[:6]}"
        )

    df = raw[_COLUMNS].copy()
    df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="raise").astype("float64")

    missing = sorted(set(areas) - set(df["REF_AREA"]))
    if missing:
        raise ValueError(
            f"OECD returned no rows for area(s) {missing}. An unknown REF_AREA is omitted "
            f"silently when requested beside a valid one -- the euro area is 'EA', not "
            f"'EA19'/'EA20'/'EU27_2020'."
        )
    return df.reset_index(drop=True)
```

- [ ] **Step 4: Write the pull**

```python
# pipelines/oecd/pull_gdp.py
"""Pulls real GDP growth (y/y, seasonally adjusted) for the US, China and the euro area
from the OECD's Quarterly National Accounts into ts_long -- the GDP side of the oil-demand
elasticity (core/oil_demand.py).

One source for all three blocks on purpose: a single methodology, and the only free route
that carries quarterly real China GDP at all (FRED does not). The US series equals the
year-on-year change of `fred.gdpc1` already in the lake for every quarter since 2013.

Run by hand: `python -m pipelines.oecd.pull_gdp`. The response is small; re-running is
idempotent through write_ts_long's revision de-dup, and picks up OECD's own revisions.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from core.storage import write_ts_long

from pipelines.oecd.client import fetch_real_gdp_growth

# OECD REF_AREA -> the lake's geo code.
AREA_GEO = {"USA": "US", "CHN": "CN", "EA": "EA"}

START_PERIOD = "2012-Q1"


def to_ts_long(raw: pd.DataFrame, revision_date: datetime) -> pd.DataFrame:
    geo = raw["REF_AREA"].map(AREA_GEO)
    quarter_start = pd.PeriodIndex(raw["TIME_PERIOD"], freq="Q").to_timestamp(how="start")
    return pd.DataFrame(
        {
            "series_id": "oecd.gdp_real_yoy." + geo.str.lower(),
            "source": "oecd",
            "ts": quarter_start,
            "value": raw["OBS_VALUE"].astype("float64").to_numpy(),
            "unit": "% y/y",
            "geo": geo,
            "freq": "Q",
            "revision_date": revision_date,
        }
    )


def main() -> None:
    raw = fetch_real_gdp_growth(list(AREA_GEO), start_period=START_PERIOD)
    df = to_ts_long(raw, datetime.now(UTC))
    write_ts_long(df, source="oecd")
    for series_id, group in df.groupby("series_id"):
        print(
            f"{series_id}: {len(group)} quarters, "
            f"{group['ts'].min().date()} -> {group['ts'].max().date()}",
            flush=True,
        )


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Register the source's freshness threshold**

In `core/freshness.py`, in the monthly group of the threshold dict (beside `"jodi": 35`),
add:

```python
    # Quarterly national accounts, pulled by hand. 120 days is one quarter plus the
    # OECD's own publication lag; tighter would flag a healthy series as stale.
    "oecd": 120,
```

If a test in `tests/test_core_freshness.py` (or whichever file covers that dict) enumerates
the expected keys, add `"oecd"` there too. Run that file and confirm it passes.

- [ ] **Step 6: Record the cassette and run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_oecd_client.py tests/test_oecd_pull.py -v --record-mode=once`
Expected: PASS, and a new `tests/cassettes/test_oecd_client/test_fetch_real_gdp_growth_live_shape.yaml`.
The route has no key, so the cassette can hold no secret; open it anyway and confirm the
request line carries only `startPeriod` and `format`. Then re-run without `--record-mode` and
confirm it still passes from the cassette.

- [ ] **Step 7: Write `pipelines/oecd/CLAUDE.md`**

```markdown
# pipelines/oecd — Claude Code Guide

## Keyless SDMX, CSV out
`https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA,1.1/{key}?format=csvfile`
— the OECD's Quarterly National Accounts. No key. Confirmed live 2026-10-10.

## The one key this pipeline uses
`Q.Y.{areas}...B1GQ.....L.GY.` — quarterly, seasonally adjusted, GDP, chain-linked volume
(real), growth on the same quarter a year earlier, in percent. Join areas with `+`.

## An unknown area is omitted silently — the euro area is `EA`
Alone, an unknown `REF_AREA` returns HTTP 404 `NoRecordsFound`. Beside a valid one it
returns HTTP 200 and simply leaves that area out. `EA19`, `EA20` and `EU27_2020` are all
unknown on this dataflow. A first probe that guessed them concluded the euro area was not
published here. `client.fetch_real_gdp_growth` raises if any requested area is absent —
do not remove that check.

## China has growth rates only
For `CHN` the dataflow carries nominal levels (`PRICE_BASE` `V` and `Q`) and the growth
transformations `G1` and `GY`. There is no chain-linked level. Anything needing a real
China GDP *level* cannot come from here.

## No world aggregate
57 areas, of which `G20` is the widest. It is a proxy for world GDP, not world GDP.

## Verified
`CHN` equals China NBS's own index (preceding year = 100) for 2024-Q3 → 2025-Q4. `USA`
equals the year-on-year change of `fred.gdpc1` for all 54 quarters from 2013-Q1. `EA` was
not cross-checked. History: `CHN` from 1993-Q1, `EA` from 1996-Q1, `USA` from 1948-Q1.
```

- [ ] **Step 8: Run the pull for real, once**

Run: `.venv/Scripts/python.exe -m pipelines.oecd.pull_gdp`
Expected: three lines, each `oecd.gdp_real_yoy.<geo>: 58 quarters, 2012-01-01 -> 2026-04-01`
(the count grows by one each quarter). Writes a new `source=oecd` partition; touches nothing
existing.

- [ ] **Step 9: Commit**

```bash
git add pipelines/oecd core/freshness.py tests/test_oecd_client.py tests/test_oecd_pull.py tests/cassettes/test_oecd_client
git commit -m "feat(oecd): quarterly real GDP growth for the US, China and the euro area"
```

---

### Task 3: `core/oil_demand.py` — the elasticity arithmetic, pure

**Files:**
- Create: `core/oil_demand.py`
- Test: `tests/test_core_oil_demand.py`

**Interfaces:**
- Consumes: pandas, numpy, statsmodels, `core.vecm.structural_break`. **No lake I/O.**
- Produces:
  - `EURO_AREA_BASKET: tuple[str, ...]` (19 codes, no `MT`), `BLOCKS: dict[str, tuple[str, ...]]`
    (`"us"`, `"cn"`, `"ea"`), `BLOCK_LABELS: dict[str, str]`
  - `MIN_OBSERVATIONS: int = 20`, `PANDEMIC_WINDOW: tuple[pd.Timestamp, pd.Timestamp]`, `BENCHMARK: str`
  - `ElasticityFit` (frozen dataclass: `slope`, `intercept`, `slope_se`, `p_value`, `r_squared`, `n`, `start`, `end`)
  - `quarterly_demand(monthly: pd.DataFrame, members: Sequence[str]) -> pd.Series`
  - `yoy_pct(quarterly: pd.Series) -> pd.Series`
  - `align(demand_yoy: pd.Series, gdp_yoy: pd.Series) -> pd.DataFrame` (columns `demand_yoy`, `gdp_yoy`)
  - `drop_window(panel: pd.DataFrame, window: tuple[pd.Timestamp, pd.Timestamp]) -> pd.DataFrame`
  - `fit_elasticity(panel: pd.DataFrame) -> ElasticityFit`
  - `out_of_sample(panel: pd.DataFrame, test_size: int = 8) -> dict[str, Any]`
  - `model_card(panel: pd.DataFrame, as_of: pd.Timestamp, test_size: int = 8) -> dict[str, Any]`
  - `project_demand_yoy(fit: ElasticityFit, gdp_yoy_assumed: pd.Series) -> pd.Series`

This module was run against the real panel on 2026-10-10 before the plan was written; the
code below is what ran.

- [ ] **Step 1: Write the failing tests**

Every figure is synthetic and hand-checkable.

```python
# tests/test_core_oil_demand.py
"""core/oil_demand.py -- the GDP elasticity of oil demand.

Every figure here is SYNTHETIC. The Bloomberg Intelligence workbook this module ports is
licensed, and none of its coefficients or panel values may appear in a tracked file.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from core import oil_demand as od


def _monthly(start: str, periods: int, **columns: float) -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq="MS")
    return pd.DataFrame({name: float(value) for name, value in columns.items()}, index=index)


def _panel(n: int = 40, slope: float = 1.5, intercept: float = -2.0) -> pd.DataFrame:
    """An exact line through varying GDP growth: demand = intercept + slope * gdp."""
    index = pd.date_range("2013-01-01", periods=n, freq="QS")
    gdp = pd.Series(np.linspace(-1.0, 4.0, n), index=index)
    return pd.DataFrame({"demand_yoy": intercept + slope * gdp, "gdp_yoy": gdp})


# --- basket -----------------------------------------------------------------------


def test_the_euro_area_basket_is_nineteen_members_without_malta() -> None:
    """Malta has seven missing months and is 0.29 % of the sum. Kept in, the completeness
    rule discards eight quarters of panel; left out, none. Measured 2026-10-10."""
    assert len(od.EURO_AREA_BASKET) == 19
    assert "MT" not in od.EURO_AREA_BASKET
    assert od.BLOCKS == {"us": ("US",), "cn": ("CN",), "ea": od.EURO_AREA_BASKET}
    assert "ex Malta" in od.BLOCK_LABELS["ea"]


# --- quarterly aggregation --------------------------------------------------------


def test_quarterly_demand_is_the_mean_of_the_summed_members() -> None:
    monthly = _monthly("2025-01-01", 6, AA=100.0, BB=50.0)
    monthly.loc["2025-04-01":, "AA"] = [110.0, 120.0, 130.0]

    quarterly = od.quarterly_demand(monthly, ["AA", "BB"])

    assert quarterly.index.tolist() == [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-04-01")]
    assert quarterly.iloc[0] == pytest.approx(150.0)
    assert quarterly.iloc[1] == pytest.approx(170.0)  # mean(160, 170, 180)


def test_a_quarter_with_any_member_missing_any_month_is_no_observation() -> None:
    """Summing the members that did report gives a smaller number that reads as a fall in
    demand. True of the live data today: the latest month lacks Croatia and Greece."""
    monthly = _monthly("2025-01-01", 6, AA=100.0, BB=50.0)
    monthly.loc["2025-05-01", "BB"] = np.nan

    quarterly = od.quarterly_demand(monthly, ["AA", "BB"])

    assert quarterly.loc["2025-01-01"] == pytest.approx(150.0)
    assert np.isnan(quarterly.loc["2025-04-01"])


def test_a_quarter_still_in_progress_is_no_observation() -> None:
    monthly = _monthly("2025-01-01", 4, AA=100.0)  # January to April: Q2 has one month

    quarterly = od.quarterly_demand(monthly, ["AA"])

    assert quarterly.loc["2025-01-01"] == pytest.approx(100.0)
    assert np.isnan(quarterly.loc["2025-04-01"])


def test_a_month_absent_from_the_index_altogether_counts_as_missing() -> None:
    monthly = _monthly("2025-01-01", 6, AA=100.0).drop(pd.Timestamp("2025-02-01"))

    quarterly = od.quarterly_demand(monthly, ["AA"])

    assert np.isnan(quarterly.loc["2025-01-01"])
    assert quarterly.loc["2025-04-01"] == pytest.approx(100.0)


def test_quarterly_demand_raises_for_a_member_with_no_series_at_all() -> None:
    with pytest.raises(ValueError, match="BB"):
        od.quarterly_demand(_monthly("2025-01-01", 3, AA=100.0), ["AA", "BB"])


def test_quarterly_demand_raises_on_an_empty_frame() -> None:
    with pytest.raises(ValueError, match="empty"):
        od.quarterly_demand(pd.DataFrame({"AA": []}, index=pd.DatetimeIndex([])), ["AA"])


# --- year-on-year -----------------------------------------------------------------


def test_yoy_pct_compares_with_the_same_quarter_a_year_earlier() -> None:
    index = pd.date_range("2024-01-01", periods=8, freq="QS")
    quarterly = pd.Series([100.0, 100.0, 100.0, 100.0, 110.0, 95.0, 100.0, 120.0], index=index)

    yoy = od.yoy_pct(quarterly)

    assert yoy.iloc[:4].isna().all()
    assert yoy.iloc[4:].tolist() == pytest.approx([10.0, -5.0, 0.0, 20.0])


def test_yoy_does_not_compare_across_a_missing_quarter() -> None:
    """With a quarter dropped from the index, a positional shift(4) would compare 2025-Q1
    with 2023-Q4. The gap must poison itself and the quarter a year later, nothing else."""
    index = pd.date_range("2023-01-01", periods=12, freq="QS")
    quarterly = pd.Series(100.0, index=index).drop(pd.Timestamp("2024-01-01"))

    yoy = od.yoy_pct(quarterly)

    assert np.isnan(yoy.loc["2024-01-01"])
    assert np.isnan(yoy.loc["2025-01-01"])
    assert yoy.loc["2025-04-01"] == pytest.approx(0.0)
    assert yoy.loc["2024-04-01"] == pytest.approx(0.0)


# --- the fit ----------------------------------------------------------------------


def test_fit_recovers_an_exact_line() -> None:
    fit = od.fit_elasticity(_panel(n=40, slope=1.5, intercept=-2.0))

    assert fit.slope == pytest.approx(1.5)
    assert fit.intercept == pytest.approx(-2.0)
    assert fit.r_squared == pytest.approx(1.0)
    assert fit.n == 40
    assert fit.start == pd.Timestamp("2013-01-01")
    assert fit.end == pd.Timestamp("2022-10-01")


def test_fit_refuses_a_short_panel() -> None:
    with pytest.raises(ValueError, match="19 overlapping quarters"):
        od.fit_elasticity(_panel(n=19))


def test_fit_refuses_a_regressor_with_no_variation() -> None:
    panel = _panel(n=30)
    panel["gdp_yoy"] = 2.0

    with pytest.raises(ValueError, match="does not vary"):
        od.fit_elasticity(panel)


def test_align_keeps_only_quarters_observed_on_both_sides() -> None:
    index = pd.date_range("2024-01-01", periods=4, freq="QS")
    demand = pd.Series([1.0, np.nan, 3.0, 4.0], index=index)
    gdp = pd.Series([2.0, 2.0, 2.0], index=index[:3])

    panel = od.align(demand, gdp)

    assert panel.index.tolist() == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-07-01")]
    assert list(panel.columns) == ["demand_yoy", "gdp_yoy"]


# --- the pandemic window ----------------------------------------------------------


def test_the_pandemic_window_covers_the_base_effect_year_too() -> None:
    assert od.PANDEMIC_WINDOW == (pd.Timestamp("2020-01-01"), pd.Timestamp("2021-10-01"))


def test_drop_window_removes_both_years_inclusive() -> None:
    panel = _panel(n=40)  # 2013-Q1 .. 2022-Q4

    kept = od.drop_window(panel, od.PANDEMIC_WINDOW)

    assert len(kept) == 32
    assert pd.Timestamp("2019-10-01") in kept.index
    assert pd.Timestamp("2020-01-01") not in kept.index
    assert pd.Timestamp("2021-10-01") not in kept.index
    assert pd.Timestamp("2022-01-01") in kept.index


def test_an_outlier_pair_inside_the_window_moves_the_full_fit_but_not_the_ex_pandemic_one() -> None:
    """The reason the second fit exists: one extreme pair can carry a slope."""
    panel = _panel(n=40, slope=1.0, intercept=0.0)
    panel.loc["2020-04-01"] = {"demand_yoy": -40.0, "gdp_yoy": -8.0}

    full = od.fit_elasticity(panel)
    ex = od.fit_elasticity(od.drop_window(panel, od.PANDEMIC_WINDOW))

    assert full.slope > 2.0
    assert ex.slope == pytest.approx(1.0)


# --- out of sample and the card ---------------------------------------------------


def test_out_of_sample_passes_when_the_relationship_holds_and_growth_moves() -> None:
    rng = np.random.default_rng(7)
    index = pd.date_range("2013-01-01", periods=48, freq="QS")
    gdp = pd.Series(rng.normal(2.0, 2.0, 48), index=index)
    panel = pd.DataFrame({"demand_yoy": 1.0 + 1.5 * gdp + rng.normal(0, 0.1, 48), "gdp_yoy": gdp})

    result = od.out_of_sample(panel, test_size=8)

    assert result["status"] == "pass"
    assert result["rmse_model"] < result["rmse_benchmark"]
    assert result["n_forecasts"] == 8
    assert 0 <= result["exceptions"] <= 8


def test_out_of_sample_fails_when_gdp_explains_nothing() -> None:
    """Demand that barely moves, against GDP that swings: "no change" beats the model."""
    rng = np.random.default_rng(11)
    index = pd.date_range("2013-01-01", periods=48, freq="QS")
    gdp = pd.Series(rng.normal(2.0, 2.0, 48), index=index)
    demand = pd.Series(np.linspace(0.0, 0.5, 48), index=index)
    demand.iloc[:30] += rng.normal(0, 6.0, 30)  # noisy history, calm test window
    panel = pd.DataFrame({"demand_yoy": demand, "gdp_yoy": gdp})

    assert od.out_of_sample(panel, test_size=8)["status"] == "fail"


def test_out_of_sample_refuses_when_it_cannot_hold_out_the_test_window() -> None:
    with pytest.raises(ValueError, match="hold out"):
        od.out_of_sample(_panel(n=27), test_size=8)


def test_model_card_carries_every_field_the_conventions_require() -> None:
    rng = np.random.default_rng(3)
    index = pd.date_range("2013-01-01", periods=54, freq="QS")
    gdp = pd.Series(rng.normal(2.0, 2.0, 54), index=index)
    panel = pd.DataFrame({"demand_yoy": 1.5 * gdp + rng.normal(0, 0.5, 54), "gdp_yoy": gdp})

    card = od.model_card(panel, as_of=pd.Timestamp("2026-10-10"))

    for field in (
        "estimation_start", "estimation_end", "last_refit", "oos_status", "benchmark",
        "exceptions", "break_date", "fit", "fit_ex_pandemic", "pandemic_window",
    ):  # fmt: skip
        assert field in card, field
    assert card["estimation_start"] == pd.Timestamp("2013-01-01")
    assert card["last_refit"] == pd.Timestamp("2026-10-10")
    assert card["benchmark"] == od.BENCHMARK
    assert card["fit"].n == 54
    assert card["fit_ex_pandemic"].n == 46


# --- the scenario -----------------------------------------------------------------


def test_project_demand_yoy_applies_the_fitted_line_to_assumed_growth() -> None:
    fit = od.fit_elasticity(_panel(n=40, slope=1.5, intercept=-2.0))
    assumed = pd.Series([0.0, 2.0], index=pd.to_datetime(["2027-01-01", "2027-04-01"]))

    projected = od.project_demand_yoy(fit, assumed)

    assert projected.tolist() == pytest.approx([-2.0, 1.0])
    assert projected.index.equals(assumed.index)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core_oil_demand.py -v`
Expected: FAIL — `ImportError: cannot import name 'oil_demand' from 'core'`.

- [ ] **Step 3: Write the module**

```python
# core/oil_demand.py
"""GDP elasticity of oil demand -- pure arithmetic, no lake I/O.

Ports the demand half of the Bloomberg Intelligence `oil_demand.xlsx` workbook onto public
data: a changes-on-changes OLS of oil demand against real GDP, one block per region. The
specification here is this repo's own -- year-on-year percentage change on both sides, for
every block -- and is NOT the workbook's, whose USA block regresses on a level change in
US$bn. The two are shown side by side as a diagnostic, never reconciled.

Rest of World is deliberately absent. Russia reports nothing to JODI and no world real GDP
series exists on a free route, so a residual cannot be summed honestly on either side.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm

from core.vecm import structural_break

EURO_AREA_BASKET: tuple[str, ...] = (
    "AT", "BE", "HR", "CY", "EE", "FI", "FR", "DE", "GR", "IE",
    "IT", "LV", "LT", "LU", "NL", "PT", "SK", "SI", "ES",
)  # fmt: skip
"""The euro area's twenty members without Malta. Malta's JODI reporting has seven missing
months (2015-09 -> 2016-01, 2017-05, 2026-07) and it is 0.29 % of the twenty-member sum.
A fixed nineteen-member basket loses no quarter to it; the twenty-member one loses eight.
Measured 2026-10-10. The GDP side is the whole euro area -- a mismatch of that 0.29 %."""

BLOCKS: dict[str, tuple[str, ...]] = {
    "us": ("US",),
    "cn": ("CN",),
    "ea": EURO_AREA_BASKET,
}

BLOCK_LABELS: dict[str, str] = {
    "us": "United States",
    "cn": "China",
    "ea": "Euro area ex Malta",
}

MIN_OBSERVATIONS = 20
"""Below this a changes-on-changes slope is noise. Refuse, do not fit."""

PANDEMIC_WINDOW: tuple[pd.Timestamp, pd.Timestamp] = (
    pd.Timestamp("2020-01-01"),
    pd.Timestamp("2021-10-01"),
)
"""Quarter starts, inclusive. Two years, not one: a year-on-year change for a 2021 quarter
is measured against 2020, so excluding 2020 alone leaves its base effect in the panel --
China's real GDP reads +18.9 % in 2021-Q1 against -6.8 % a year earlier."""

BENCHMARK = "no change in y/y demand growth from the previous quarter"


@dataclass(frozen=True)
class ElasticityFit:
    slope: float
    intercept: float
    slope_se: float
    p_value: float
    r_squared: float
    n: int
    start: pd.Timestamp
    end: pd.Timestamp


def quarterly_demand(monthly: pd.DataFrame, members: Sequence[str]) -> pd.Series:
    """Quarterly mean of the members' summed monthly demand, indexed by quarter start.

    `monthly` is wide: a month-start DatetimeIndex, one column per country, kb/d. A quarter
    is published only when every member reports all three of its months. A sum over the
    members that did report is a smaller number that reads as a fall in demand, so a
    quarter with any gap is NaN -- no observation, never a partial one.
    """
    missing = [member for member in members if member not in monthly.columns]
    if missing:
        raise ValueError(f"no demand series at all for member(s): {missing}")
    if monthly.empty:
        raise ValueError("monthly demand frame is empty")

    months = pd.date_range(monthly.index.min(), monthly.index.max(), freq="MS")
    block = monthly.reindex(months)[list(members)]
    total = block.sum(axis=1, skipna=False)  # NaN if any member is missing that month
    quarter = total.index.to_period("Q")
    mean = total.groupby(quarter).mean()
    complete = total.notna().groupby(quarter).sum() == 3
    out = mean.where(complete)
    out.index = out.index.to_timestamp(how="start")
    out.name = "demand_kbd"
    return out


def yoy_pct(quarterly: pd.Series) -> pd.Series:
    """Percentage change on the same quarter a year earlier.

    Reindexed to an unbroken quarterly range first, so a missing quarter yields NaN for
    itself and for the quarter a year later instead of silently comparing across the gap.
    """
    if quarterly.empty:
        return quarterly.astype("float64")
    full = pd.date_range(quarterly.index.min(), quarterly.index.max(), freq="QS")
    series = quarterly.reindex(full)
    return (series / series.shift(4) - 1.0) * 100.0


def align(demand_yoy: pd.Series, gdp_yoy: pd.Series) -> pd.DataFrame:
    """The regression panel: quarters where both sides are observed."""
    panel = pd.concat({"demand_yoy": demand_yoy, "gdp_yoy": gdp_yoy}, axis=1).dropna()
    return panel.sort_index()


def drop_window(
    panel: pd.DataFrame, window: tuple[pd.Timestamp, pd.Timestamp]
) -> pd.DataFrame:
    start, end = window
    return panel[(panel.index < start) | (panel.index > end)]


def fit_elasticity(panel: pd.DataFrame) -> ElasticityFit:
    """OLS of `demand_yoy` on `gdp_yoy` with an intercept.

    Raises rather than returning a fit that means nothing: too few quarters, or a GDP
    series with no variation, both produce a number that looks like an elasticity.
    """
    if len(panel) < MIN_OBSERVATIONS:
        raise ValueError(
            f"{len(panel)} overlapping quarters; need at least {MIN_OBSERVATIONS} to fit"
        )
    if np.isclose(panel["gdp_yoy"].std(ddof=0), 0.0):
        raise ValueError("GDP growth does not vary over the panel; slope is undefined")

    result = sm.OLS(panel["demand_yoy"], sm.add_constant(panel["gdp_yoy"])).fit()
    return ElasticityFit(
        slope=float(result.params["gdp_yoy"]),
        intercept=float(result.params["const"]),
        slope_se=float(result.bse["gdp_yoy"]),
        p_value=float(result.pvalues["gdp_yoy"]),
        r_squared=float(result.rsquared),
        n=int(result.nobs),
        start=panel.index[0],
        end=panel.index[-1],
    )


def out_of_sample(panel: pd.DataFrame, test_size: int = 8) -> dict[str, Any]:
    """Expanding-window one-quarter-ahead test against `BENCHMARK`.

    For each of the last `test_size` quarters the model is fitted on everything before it
    and asked for that quarter given its GDP growth. An exception is a quarter where the
    model's absolute error exceeded the benchmark's -- "worse than assuming nothing
    changed", the same count `core.vecm.model_card` reports.
    """
    if len(panel) < MIN_OBSERVATIONS + test_size:
        raise ValueError(
            f"{len(panel)} quarters; need {MIN_OBSERVATIONS + test_size} to hold out "
            f"{test_size}"
        )
    errors_model: list[float] = []
    errors_naive: list[float] = []
    for i in range(len(panel) - test_size, len(panel)):
        fit = fit_elasticity(panel.iloc[:i])
        actual = float(panel["demand_yoy"].iloc[i])
        predicted = fit.intercept + fit.slope * float(panel["gdp_yoy"].iloc[i])
        errors_model.append(actual - predicted)
        errors_naive.append(actual - float(panel["demand_yoy"].iloc[i - 1]))

    model = np.asarray(errors_model)
    naive = np.asarray(errors_naive)
    rmse_model = float(np.sqrt(np.mean(model**2)))
    rmse_naive = float(np.sqrt(np.mean(naive**2)))
    return {
        "rmse_model": rmse_model,
        "rmse_benchmark": rmse_naive,
        "exceptions": int(np.sum(np.abs(model) > np.abs(naive))),
        "n_forecasts": test_size,
        "status": "pass" if rmse_model < rmse_naive else "fail",
    }


def model_card(
    panel: pd.DataFrame, as_of: pd.Timestamp, test_size: int = 8
) -> dict[str, Any]:
    """Every field `specs/00_TRADING_CONVENTIONS.md` requires of a model card, for the fit
    on the full panel, with the ex-pandemic fit beside it."""
    full = fit_elasticity(panel)
    ex_pandemic = fit_elasticity(drop_window(panel, PANDEMIC_WINDOW))
    oos = out_of_sample(panel, test_size=test_size)
    brk = structural_break(panel[["demand_yoy", "gdp_yoy"]])
    return {
        "estimation_start": full.start,
        "estimation_end": full.end,
        "last_refit": pd.Timestamp(as_of),
        "oos_status": oos["status"],
        "benchmark": BENCHMARK,
        "exceptions": oos["exceptions"],
        "n_forecasts": oos["n_forecasts"],
        "rmse_model": oos["rmse_model"],
        "rmse_benchmark": oos["rmse_benchmark"],
        "break_date": brk["break_date"],
        "sup_f": brk["sup_f"],
        "sup_f_date": brk["sup_f_date"],
        "fit": full,
        "fit_ex_pandemic": ex_pandemic,
        "pandemic_window": PANDEMIC_WINDOW,
    }


def project_demand_yoy(fit: ElasticityFit, gdp_yoy_assumed: pd.Series) -> pd.Series:
    """Demand growth implied by an ASSUMED GDP growth path. A scenario, never a forecast
    of record: the input is somebody's assumption and the output inherits that status."""
    return fit.intercept + fit.slope * gdp_yoy_assumed.astype("float64")
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core_oil_demand.py -v`
Expected: PASS. If `test_out_of_sample_fails_when_gdp_explains_nothing` passes as a `pass`
on your seed, the fixture is too kind to the model, not the code wrong: raise the GDP
standard deviation in that fixture until "no change" wins, and say so in the commit.

- [ ] **Step 5: Type-check**

Run: `.venv/Scripts/python.exe -m mypy core`
Expected: no issues. `statsmodels` is already imported untyped by `core/vecm.py`; follow
whatever that file does if mypy objects to the import here.

- [ ] **Step 6: Commit**

```bash
git add core/oil_demand.py tests/test_core_oil_demand.py
git commit -m "feat(core): GDP elasticity of oil demand, with and without the pandemic"
```

---

### Task 4: `pipelines/derived/oil_demand.py` — write `derived.oil_demand.*`

**Files:**
- Create: `pipelines/derived/oil_demand.py`, `pipelines/derived/oil_demand/gdp_assumptions.csv`, `pipelines/derived/oil_demand/README.md`
- Modify: `pipelines/derived/CLAUDE.md` (append a section)
- Test: `tests/test_derived_oil_demand.py`

**Interfaces:**
- Consumes: `core.oil_demand` (everything in Task 3's Produces), `core.storage.read_ts_long` / `write_ts_long`,
  lake series `jodi.total_demand.<cc>` (Task 1) and `oecd.gdp_real_yoy.<geo>` (Task 2)
- Produces:
  - `read_monthly_demand() -> pd.DataFrame` (wide: month index, ISO-2 columns)
  - `read_gdp_yoy(block: str) -> pd.Series`
  - `read_assumptions(path: Path) -> pd.DataFrame` (columns `block`, `quarter`, `gdp_yoy_pct`, `author`, `as_of`)
  - `build_panel(block: str, monthly: pd.DataFrame, gdp_yoy: pd.Series) -> pd.DataFrame` — also imported by the page
  - `build_rows(monthly, gdp_by_block, assumptions, revision_date) -> pd.DataFrame`
  - lake series, all `source="derived"`, `freq="Q"`:
    `derived.oil_demand.<block>.level` (`kb/d`), `derived.oil_demand.<block>.yoy` (`% y/y`),
    `derived.oil_demand.<block>.yoy.scenario` (`% y/y`)

**Why the fitted coefficients are not written to the lake:** a slope is a property of a panel
and a date, not a time series. The page recomputes the card from the same lake rows through
`core.oil_demand.model_card`, the way `20_cracks.py` treats its own model. What the lake
needs is the two observed series the fit is made from, and the scenario path.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_derived_oil_demand.py
"""pipelines/derived/oil_demand.py. Every figure is SYNTHETIC -- see
tests/test_core_oil_demand.py for why."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from core import oil_demand as od
from core.schemas import validate_ts_long
from pipelines.derived import oil_demand as derived

REVISION = pd.Timestamp("2026-10-10")


def _monthly(months: int = 15 * 12) -> pd.DataFrame:
    """Every basket member at a flat level, the US growing 2 % a year, China flat."""
    index = pd.date_range("2012-01-01", periods=months, freq="MS")
    frame = pd.DataFrame(100.0, index=index, columns=list(od.EURO_AREA_BASKET))
    frame["MT"] = 1.0
    frame["CN"] = 14000.0
    frame["US"] = 20000.0 * (1.02 ** ((index.year - 2012) + (index.month - 1) / 12))
    return frame


def _gdp(value: float = 2.0, quarters: int = 58) -> pd.Series:
    index = pd.date_range("2012-01-01", periods=quarters, freq="QS")
    return pd.Series(value + np.sin(np.arange(quarters)), index=index)


def _assumptions(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "block": [row[0] for row in rows],
            "quarter": pd.to_datetime([row[1] for row in rows]),
            "gdp_yoy_pct": pd.to_numeric([row[2] for row in rows], errors="coerce"),
            "author": "test",
            "as_of": "2026-10-10",
        }
    )


def _gdp_by_block() -> dict[str, pd.Series]:
    return {block: _gdp() for block in od.BLOCKS}


def test_build_panel_uses_the_blocks_basket_and_ignores_malta() -> None:
    monthly = _monthly()
    monthly.loc["2015-09-01":"2016-01-01", "MT"] = np.nan  # Malta's real gap

    panel = derived.build_panel("ea", monthly, _gdp())

    assert panel.index.min() == pd.Timestamp("2013-01-01")
    assert len(panel) == 54, "Malta's gap must not cost the euro area a single quarter"


def test_build_rows_writes_conformant_level_and_yoy_series_per_block() -> None:
    rows = derived.build_rows(_monthly(), _gdp_by_block(), _assumptions([]), REVISION)

    validate_ts_long(rows)
    assert set(rows["series_id"]) == {
        f"derived.oil_demand.{block}.{kind}" for block in od.BLOCKS for kind in ("level", "yoy")
    }
    assert (rows["source"] == "derived").all()
    assert (rows["freq"] == "Q").all()
    assert rows["value"].notna().all(), "NaN quarters are not written"
    level = rows[rows["series_id"] == "derived.oil_demand.ea.level"]
    assert (level["unit"] == "kb/d").all()
    assert level["value"].iloc[0] == pytest.approx(1900.0)  # 19 members x 100
    assert (level["geo"] == "EA").all()
    yoy = rows[rows["series_id"] == "derived.oil_demand.us.yoy"]
    assert (yoy["unit"] == "% y/y").all()
    assert yoy["value"].iloc[0] == pytest.approx(2.0, abs=0.01)
    assert yoy["ts"].min() == pd.Timestamp("2013-01-01")


def test_an_incomplete_latest_quarter_writes_no_row() -> None:
    """Live today: the latest month is missing Croatia and Greece. The quarter must be
    absent from the lake, not present and understated."""
    monthly = _monthly()
    last_quarter = monthly.index.max() - pd.offsets.QuarterBegin(startingMonth=1)
    monthly.loc[monthly.index.max(), "HR"] = np.nan

    rows = derived.build_rows(monthly, _gdp_by_block(), _assumptions([]), REVISION)

    ea_level = rows[rows["series_id"] == "derived.oil_demand.ea.level"]
    assert ea_level["ts"].max() < last_quarter
    us_level = rows[rows["series_id"] == "derived.oil_demand.us.level"]
    assert us_level["ts"].max() == last_quarter, "one block's gap must not blank another"


def test_assumed_gdp_growth_writes_a_scenario_series_and_nothing_else() -> None:
    assumptions = _assumptions([("us", "2027-01-01", "2.0"), ("us", "2027-04-01", "1.0")])

    rows = derived.build_rows(_monthly(), _gdp_by_block(), assumptions, REVISION)

    scenario = rows[rows["series_id"].str.endswith(".scenario")]
    assert set(scenario["series_id"]) == {"derived.oil_demand.us.yoy.scenario"}
    assert scenario["ts"].tolist() == [pd.Timestamp("2027-01-01"), pd.Timestamp("2027-04-01")]
    observed = rows[rows["series_id"] == "derived.oil_demand.us.yoy"]
    assert observed["ts"].max() < pd.Timestamp("2027-01-01"), (
        "an assumption-driven value must never land under the observed id"
    )


def test_a_blank_assumption_writes_no_scenario_row() -> None:
    assumptions = _assumptions([("us", "2027-01-01", ""), ("us", "2027-04-01", "1.0")])

    rows = derived.build_rows(_monthly(), _gdp_by_block(), assumptions, REVISION)

    scenario = rows[rows["series_id"].str.endswith(".scenario")]
    assert scenario["ts"].tolist() == [pd.Timestamp("2027-04-01")]


def test_an_assumption_for_an_unknown_block_raises() -> None:
    assumptions = _assumptions([("row", "2027-01-01", "3.0")])

    with pytest.raises(ValueError, match="row"):
        derived.build_rows(_monthly(), _gdp_by_block(), assumptions, REVISION)


def test_an_assumption_for_a_quarter_already_observed_raises() -> None:
    """A scenario row dated inside history would sit beside a measurement of the same
    quarter. Refuse it: the file's author meant a future quarter and mistyped."""
    assumptions = _assumptions([("us", "2024-01-01", "2.0")])

    with pytest.raises(ValueError, match="already observed"):
        derived.build_rows(_monthly(), _gdp_by_block(), assumptions, REVISION)


def test_read_assumptions_parses_the_committed_file() -> None:
    frame = derived.read_assumptions(derived.ASSUMPTIONS_PATH)

    assert list(frame.columns) == ["block", "quarter", "gdp_yoy_pct", "author", "as_of"]
    assert set(frame["block"]) <= set(od.BLOCKS)
    assert pd.api.types.is_datetime64_any_dtype(frame["quarter"])


def test_main_reads_and_writes_an_isolated_lake(tmp_path, monkeypatch) -> None:
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")
    monthly = _monthly()
    long = monthly.reset_index(names="ts").melt(id_vars="ts", var_name="geo", value_name="value")
    storage.write_ts_long(
        long.assign(
            series_id="jodi.total_demand." + long["geo"].str.lower(),
            source="jodi", unit="kb/d", freq="M", revision_date=REVISION,
        )[["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]],
        source="jodi",
    )  # fmt: skip
    for geo in ("US", "CN", "EA"):
        gdp = _gdp()
        storage.write_ts_long(
            pd.DataFrame(
                {
                    "series_id": f"oecd.gdp_real_yoy.{geo.lower()}",
                    "source": "oecd", "ts": gdp.index, "value": gdp.to_numpy(),
                    "unit": "% y/y", "geo": geo, "freq": "Q", "revision_date": REVISION,
                }
            ),
            source="oecd",
        )  # fmt: skip

    derived.main()

    written = storage.read_ts_long(series_prefix="derived.oil_demand.", source="derived")
    assert "derived.oil_demand.cn.yoy" in set(written["series_id"])


def test_main_fails_loudly_when_the_demand_series_are_absent(tmp_path, monkeypatch) -> None:
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")

    with pytest.raises(RuntimeError, match="pipelines.jodi.pull_demand"):
        derived.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_derived_oil_demand.py -v`
Expected: FAIL — `ImportError: cannot import name 'oil_demand' from 'pipelines.derived'`.

- [ ] **Step 3: Write the assumptions file and its README**

`pipelines/derived/oil_demand/gdp_assumptions.csv` — header only. It ships empty on purpose:
no scenario exists until the owner writes one.

```csv
block,quarter,gdp_yoy_pct,author,as_of
```

`pipelines/derived/oil_demand/README.md`:

```markdown
# GDP growth assumptions for the oil-demand scenario

`gdp_assumptions.csv` is the forward input to `pipelines/derived/oil_demand.py`. It is the
workbook's "User Input" column: **your** assumed real GDP growth, year on year, per block
per quarter. No connector supplies a GDP forecast and none is implied.

| Column | Meaning |
|---|---|
| `block` | `us`, `cn` or `ea` |
| `quarter` | quarter start, `yyyy-mm-dd` — must be after the last observed quarter |
| `gdp_yoy_pct` | assumed real GDP growth on a year earlier, in percent. Blank = no assumption |
| `author` | who set it |
| `as_of` | the date it was set |

The file ships with a header and no rows. With no rows, no scenario series is written.
Rows here become `derived.oil_demand.<block>.yoy.scenario` in the lake — never the observed
series. After editing, run `python -m pipelines.derived.oil_demand`.

Do not paste Bloomberg Economics' baseline here. It is licensed, and this file is tracked.
```

- [ ] **Step 4: Write the pipeline**

```python
# pipelines/derived/oil_demand.py
"""Writes the observed oil-demand series and the assumption-driven scenario into the lake
as `derived.oil_demand.*`.

Reads `jodi.total_demand.*` and `oecd.gdp_real_yoy.*`, calls core.oil_demand's pure
functions, writes `ts_long` rows back -- the same shape as every other module here.

Three series per block:
- `.level`        quarterly mean demand, kb/d -- observed
- `.yoy`          its change on a year earlier, % -- observed
- `.yoy.scenario` demand growth implied by the owner's ASSUMED GDP growth, % -- a scenario

The fitted coefficients are not written. A slope belongs to a panel and a date, not to a
time axis; the page recomputes the model card from the observed series.

Not registered in infra/run_scheduled.py. Run it by hand after pull_demand, pull_gdp, or an
edit to gdp_assumptions.csv.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from core import oil_demand as od
from core.storage import read_ts_long, write_ts_long

ASSUMPTIONS_PATH = Path(__file__).parent / "oil_demand" / "gdp_assumptions.csv"

BLOCK_GEO = {"us": "US", "cn": "CN", "ea": "EA"}

UNIT_LEVEL = "kb/d"
UNIT_YOY = "% y/y"


def read_monthly_demand() -> pd.DataFrame:
    """Wide monthly demand from the lake: month-start index, one ISO-2 column per country."""
    long = read_ts_long(series_prefix="jodi.total_demand.", source="jodi")
    if long.empty:
        raise RuntimeError(
            "no jodi.total_demand.* series in the lake -- run "
            "`python -m pipelines.jodi.pull_demand` first"
        )
    return long.pivot_table(index="ts", columns="geo", values="value", aggfunc="last")


def read_gdp_yoy(block: str) -> pd.Series:
    series_id = f"oecd.gdp_real_yoy.{block}"
    long = read_ts_long(series_ids=[series_id], source="oecd")
    if long.empty:
        raise RuntimeError(
            f"no {series_id} in the lake -- run `python -m pipelines.oecd.pull_gdp` first"
        )
    return long.set_index("ts")["value"].sort_index()


def read_assumptions(path: Path) -> pd.DataFrame:
    """A blank `gdp_yoy_pct` reads as NaN -- no assumption -- never as 0.0, which would
    assert zero growth."""
    frame = pd.read_csv(path, dtype=str)
    frame["quarter"] = pd.to_datetime(frame["quarter"])
    frame["gdp_yoy_pct"] = pd.to_numeric(frame["gdp_yoy_pct"], errors="coerce")
    return frame[["block", "quarter", "gdp_yoy_pct", "author", "as_of"]]


def build_panel(block: str, monthly: pd.DataFrame, gdp_yoy: pd.Series) -> pd.DataFrame:
    """The regression panel for one block. Shared with the page so both fit the same rows."""
    quarterly = od.quarterly_demand(monthly, od.BLOCKS[block])
    return od.align(od.yoy_pct(quarterly), gdp_yoy)


def _rows(series: pd.Series, series_id: str, unit: str, geo: str) -> pd.DataFrame:
    observed = series.dropna()
    return pd.DataFrame(
        {
            "series_id": series_id,
            "ts": observed.index,
            "value": observed.to_numpy(dtype="float64"),
            "unit": unit,
            "geo": geo,
        }
    )


def build_rows(
    monthly: pd.DataFrame,
    gdp_by_block: dict[str, pd.Series],
    assumptions: pd.DataFrame,
    revision_date: pd.Timestamp | datetime,
) -> pd.DataFrame:
    unknown = sorted(set(assumptions["block"]) - set(od.BLOCKS))
    if unknown:
        raise ValueError(
            f"gdp_assumptions.csv names block(s) {unknown}; known blocks are {sorted(od.BLOCKS)}"
        )

    frames: list[pd.DataFrame] = []
    for block, members in od.BLOCKS.items():
        geo = BLOCK_GEO[block]
        level = od.quarterly_demand(monthly, members)
        yoy = od.yoy_pct(level)
        frames.append(_rows(level, f"derived.oil_demand.{block}.level", UNIT_LEVEL, geo))
        frames.append(_rows(yoy, f"derived.oil_demand.{block}.yoy", UNIT_YOY, geo))

        assumed = assumptions[(assumptions["block"] == block)].dropna(subset=["gdp_yoy_pct"])
        if assumed.empty:
            continue
        last_observed = yoy.dropna().index.max()
        inside = assumed[assumed["quarter"] <= last_observed]
        if not inside.empty:
            raise ValueError(
                f"gdp_assumptions.csv sets {block} growth for "
                f"{[q.date().isoformat() for q in inside['quarter']]}, already observed "
                f"(last observed quarter {last_observed.date()}). A scenario starts after it."
            )
        fit = od.fit_elasticity(od.align(yoy, gdp_by_block[block]))
        path = od.project_demand_yoy(
            fit, assumed.set_index("quarter")["gdp_yoy_pct"].sort_index()
        )
        frames.append(
            _rows(path, f"derived.oil_demand.{block}.yoy.scenario", UNIT_YOY, geo)
        )

    out = pd.concat(frames, ignore_index=True)
    out["source"] = "derived"
    out["freq"] = "Q"
    out["revision_date"] = pd.Timestamp(revision_date)
    return out[["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]]


def main() -> None:
    monthly = read_monthly_demand()
    gdp_by_block = {block: read_gdp_yoy(block) for block in od.BLOCKS}
    assumptions = read_assumptions(ASSUMPTIONS_PATH)
    rows = build_rows(monthly, gdp_by_block, assumptions, datetime.now(UTC))
    write_ts_long(rows, source="derived")
    for series_id, group in rows.groupby("series_id"):
        print(
            f"{series_id}: {len(group)} quarters, "
            f"{group['ts'].min().date()} -> {group['ts'].max().date()}",
            flush=True,
        )
    if not rows["series_id"].str.endswith(".scenario").any():
        print(
            "no scenario written: gdp_assumptions.csv holds no assumption. That is the "
            "shipped state, not an error.",
            flush=True,
        )


if __name__ == "__main__":
    main()
```

Note: `pipelines/derived/oil_demand.py` (module) and `pipelines/derived/oil_demand/`
(data directory, no `__init__.py`) coexist the same way `hormuz.py` and `hormuz/` already
do. Do not add an `__init__.py` to the directory.

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_derived_oil_demand.py -v`
Expected: PASS.

- [ ] **Step 6: Document it in `pipelines/derived/CLAUDE.md`**

Append:

```markdown
## `oil_demand.py` — observed series and a scenario, never mixed

Reads `jodi.total_demand.*` and `oecd.gdp_real_yoy.*`; writes
`derived.oil_demand.<block>.{level,yoy}` (observed) and `.yoy.scenario` (driven by the
owner's GDP assumptions in `oil_demand/gdp_assumptions.csv`, which ships empty). An
assumption dated inside observed history is refused, so a scenario row can never sit beside
a measurement of the same quarter.

The fitted elasticities are **not** in the lake — `apps/dashboard/pages/23_oil_demand.py`
recomputes the model card through `core.oil_demand.model_card` from the same rows.

The euro-area block is nineteen members, without Malta
(`core.oil_demand.EURO_AREA_BASKET`), and a quarter with any basket member missing any month
writes nothing. Expect the latest quarter to be absent for `ea` while present for `us` and
`cn`: smaller members report a month late.

Rest of World is not built. Russia is absent from JODI and no world GDP series exists.
```

- [ ] **Step 7: Run it for real**

Run: `.venv/Scripts/python.exe -m pipelines.derived.oil_demand`
Expected: six lines (three blocks × `level`, `yoy`), `level` from 2012-01-01 and `yoy` from
2013-01-01, then the "no scenario written" line. Writes `source=derived`; adds series,
changes none.

- [ ] **Step 8: Commit**

```bash
git add pipelines/derived/oil_demand.py pipelines/derived/oil_demand pipelines/derived/CLAUDE.md tests/test_derived_oil_demand.py
git commit -m "feat(derived): oil demand by block, observed apart from scenario"
```

---

### Task 5: the dashboard page

**Files:**
- Create: `apps/dashboard/pages/23_oil_demand.py`
- Modify: `apps/dashboard/nav.py` (one `PageSpec`)
- Test: `tests/test_pages_oil_demand.py`

**Interfaces:**
- Consumes: `core.oil_demand.model_card` / `BLOCKS` / `BLOCK_LABELS` / `PANDEMIC_WINDOW` / `MIN_OBSERVATIONS`,
  `pipelines.derived.oil_demand.build_panel` / `read_monthly_demand` / `read_gdp_yoy`,
  `core.storage.read_ts_long`, `components.section`, `core.theme`
- Produces: a page under "Fundamentals". Reads the lake only.

`22_briefing.py` exists on `main` but not on this branch's base; `23` avoids the collision
when the branches meet. Check `ls apps/dashboard/pages` first and take the next free number
if `23` is taken.

**The page's hard requirements**, each asserted by a test:
1. The full-panel and ex-pandemic fits are shown **side by side** for every block. Never one
   without the other.
2. A slope whose p-value is above 0.05 is labelled "not statistically significant" in words,
   on the same row as the number.
3. The euro-area block is labelled "ex Malta".
4. A scenario series, when present, is named as an assumption with its author and date.
5. With no data, a real no-data message naming the command to run — not an empty chart.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pages_oil_demand.py
"""`apps/dashboard/pages/23_oil_demand.py`, driven through AppTest against an isolated
lake -- the same mechanism as tests/test_pages_curve_window.py. All figures synthetic."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from core import oil_demand as od
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).parent.parent
APP_ENTRYPOINT = REPO_ROOT / "apps" / "dashboard" / "app.py"
REVISION = pd.Timestamp("2026-10-10")
_COLUMNS = ["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]


@pytest.fixture
def isolated_lake(tmp_path, monkeypatch):
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")
    return storage


def _seed(storage, china_follows_gdp: bool = True) -> None:
    rng = np.random.default_rng(5)
    quarters = pd.date_range("2012-01-01", periods=58, freq="QS")
    months = pd.date_range("2012-01-01", periods=58 * 3, freq="MS")
    countries = ["US", "CN", *od.EURO_AREA_BASKET]
    for geo in ("US", "CN", "EA"):
        gdp = pd.Series(2.0 + rng.normal(0, 2.0, 58), index=quarters)
        storage.write_ts_long(
            pd.DataFrame(
                {
                    "series_id": f"oecd.gdp_real_yoy.{geo.lower()}", "source": "oecd",
                    "ts": quarters, "value": gdp.to_numpy(), "unit": "% y/y", "geo": geo,
                    "freq": "Q", "revision_date": REVISION,
                }
            )[_COLUMNS],
            source="oecd",
        )  # fmt: skip
        members = [geo] if geo != "EA" else list(od.EURO_AREA_BASKET)
        follows = china_follows_gdp or geo != "CN"
        # Demand level whose y/y growth is 1.5 x GDP growth (or pure noise for China).
        growth = (1.5 * gdp if follows else pd.Series(rng.normal(0, 5.0, 58), index=quarters))
        level = pd.Series(1000.0, index=quarters)
        for i in range(4, 58):
            level.iloc[i] = level.iloc[i - 4] * (1 + growth.iloc[i] / 100)
        monthly = level.reindex(months, method="ffill")
        for member in members:
            storage.write_ts_long(
                pd.DataFrame(
                    {
                        "series_id": f"jodi.total_demand.{member.lower()}", "source": "jodi",
                        "ts": months, "value": monthly.to_numpy(), "unit": "kb/d",
                        "geo": member, "freq": "M", "revision_date": REVISION,
                    }
                )[_COLUMNS],
                source="jodi",
            )  # fmt: skip
    assert set(countries) >= {"US", "CN"}


def _run_page() -> AppTest:
    at = AppTest.from_file(str(APP_ENTRYPOINT)).run(timeout=60)
    at = at.switch_page("pages/23_oil_demand.py").run(timeout=60)
    assert not at.exception, at.exception
    return at


def _said(at: AppTest) -> str:
    parts = [e.value for e in at.caption] + [e.value for e in at.markdown]
    parts += [e.value for e in at.info] + [e.value for e in at.warning]
    for table in at.dataframe:
        parts.append(table.value.to_string())
    return " ".join(str(part) for part in parts)


def test_an_empty_lake_renders_a_no_data_message_naming_the_command(isolated_lake) -> None:
    said = _said(_run_page())

    assert "pipelines.jodi.pull_demand" in said


def test_both_fits_are_shown_side_by_side_for_every_block(isolated_lake) -> None:
    _seed(isolated_lake)

    said = _said(_run_page())

    assert "Full panel" in said
    assert "Ex-pandemic" in said
    for label in od.BLOCK_LABELS.values():
        assert label in said, label
    assert "ex Malta" in said


def test_an_insignificant_slope_is_called_insignificant_in_words(isolated_lake) -> None:
    _seed(isolated_lake, china_follows_gdp=False)

    said = _said(_run_page())

    assert "not statistically significant" in said


def test_a_scenario_series_is_named_as_an_assumption(isolated_lake) -> None:
    _seed(isolated_lake)
    isolated_lake.write_ts_long(
        pd.DataFrame(
            {
                "series_id": "derived.oil_demand.us.yoy.scenario", "source": "derived",
                "ts": [pd.Timestamp("2027-01-01")], "value": [1.2], "unit": "% y/y",
                "geo": "US", "freq": "Q", "revision_date": REVISION,
            }
        )[_COLUMNS],
        source="derived",
    )  # fmt: skip

    said = _said(_run_page())

    assert "assumption" in said.lower()
    assert "not a forecast" in said.lower()


def test_the_model_card_states_the_benchmark_and_the_pandemic_window(isolated_lake) -> None:
    _seed(isolated_lake)

    said = _said(_run_page())

    assert od.BENCHMARK in said
    assert "2020-Q1" in said and "2021-Q4" in said
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pages_oil_demand.py -v`
Expected: FAIL — the page does not exist.

- [ ] **Step 3: Register the page**

In `apps/dashboard/nav.py`, in the `"Fundamentals"` tuple, after the `19_fundamentals.py`
entry:

```python
        PageSpec("23_oil_demand.py", "Oil Demand", "oil_demand"),
```

- [ ] **Step 4: Write the page**

```python
# apps/dashboard/pages/23_oil_demand.py
"""GDP elasticity of oil demand -- the demand half of the `oil_demand.xlsx` port.

What this page must not let a reader miss, each measured on the real panel 2026-10-10:

- **The US fit is mostly the pandemic.** Its R-squared falls by more than two thirds when
  2020-2021 leaves the panel. Both fits are therefore always shown together.
- **China's slope is not statistically significant** on public data, in either panel. It
  is published with its p-value and called what it is.
- **The euro-area block is nineteen members, without Malta**, and its latest quarter is
  usually absent: smaller members report a month late and a partial sum is no observation.
- **Rest of World is not built.** Russia is absent from JODI and no world GDP series exists.

The specification -- year-on-year percentage change on both sides -- is this repo's, not
the workbook's. Its coefficients are a diagnostic to read beside these, not a target.
"""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.section import empty_state, page_header, section, source_note
from core import oil_demand as od
from core.storage import read_ts_long
from core.theme import GREY, NAVY, RED
from pipelines.derived.oil_demand import build_panel, read_gdp_yoy, read_monthly_demand

SIGNIFICANCE = 0.05


def _quarter(ts: pd.Timestamp) -> str:
    return f"{ts.year}-Q{ts.quarter}"


def _fit_row(block: str, panel_name: str, fit: od.ElasticityFit) -> dict[str, object]:
    verdict = (
        "significant at 5 %" if fit.p_value < SIGNIFICANCE else "not statistically significant"
    )
    return {
        "Block": od.BLOCK_LABELS[block],
        "Panel": panel_name,
        "Quarters": fit.n,
        "Window": f"{_quarter(fit.start)} to {_quarter(fit.end)}",
        "Slope": round(fit.slope, 2),
        "Std. error": round(fit.slope_se, 2),
        "p-value": round(fit.p_value, 3),
        "R-squared": round(fit.r_squared, 2),
        "Slope is": verdict,
    }


def _scatter(panel: pd.DataFrame, card: dict[str, object]) -> go.Figure:
    start, end = od.PANDEMIC_WINDOW
    inside = (panel.index >= start) & (panel.index <= end)
    fit: od.ElasticityFit = card["fit"]  # type: ignore[assignment]
    ex: od.ElasticityFit = card["fit_ex_pandemic"]  # type: ignore[assignment]
    xs = [float(panel["gdp_yoy"].min()), float(panel["gdp_yoy"].max())]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=panel.loc[~inside, "gdp_yoy"], y=panel.loc[~inside, "demand_yoy"],
            mode="markers", name="Quarter", marker={"color": NAVY},
        )
    )  # fmt: skip
    fig.add_trace(
        go.Scatter(
            x=panel.loc[inside, "gdp_yoy"], y=panel.loc[inside, "demand_yoy"],
            mode="markers", name="2020-2021", marker={"color": RED},
        )
    )  # fmt: skip
    fig.add_trace(
        go.Scatter(
            x=xs, y=[fit.intercept + fit.slope * x for x in xs],
            mode="lines", name="Full panel", line={"color": NAVY},
        )
    )  # fmt: skip
    fig.add_trace(
        go.Scatter(
            x=xs, y=[ex.intercept + ex.slope * x for x in xs],
            mode="lines", name="Ex-pandemic", line={"color": GREY, "dash": "dash"},
        )
    )  # fmt: skip
    fig.update_layout(template="kardamow")
    fig.update_xaxes(title_text="Real GDP, % y/y")
    fig.update_yaxes(title_text="Oil demand, % y/y")
    return fig


page_header("Oil Demand", freshness="JODI monthly · OECD quarterly")

try:
    monthly = read_monthly_demand()
    gdp_by_block = {block: read_gdp_yoy(block) for block in od.BLOCKS}
except RuntimeError as exc:
    empty_state("jodi / oecd", "monthly / quarterly", None)
    st.info(
        f"{exc}. Then `python -m pipelines.oecd.pull_gdp` and "
        "`python -m pipelines.derived.oil_demand`."
    )
    st.stop()

panels: dict[str, pd.DataFrame] = {}
cards: dict[str, dict[str, object]] = {}
refused: dict[str, str] = {}
for block in od.BLOCKS:
    panel = build_panel(block, monthly, gdp_by_block[block])
    panels[block] = panel
    try:
        cards[block] = od.model_card(panel, as_of=pd.Timestamp.now().normalize())
    except ValueError as exc:
        refused[block] = str(exc)

window_start, window_end = od.PANDEMIC_WINDOW

with section("Elasticity by block"):
    rows: list[dict[str, object]] = []
    for block, card in cards.items():
        rows.append(_fit_row(block, "Full panel", card["fit"]))  # type: ignore[arg-type]
        rows.append(_fit_row(block, "Ex-pandemic", card["fit_ex_pandemic"]))  # type: ignore[arg-type]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True)
    for block, reason in refused.items():
        st.warning(f"{od.BLOCK_LABELS[block]}: no fit. {reason}.")
    source_note(
        "Slope: percentage-point change in oil demand growth per point of real GDP growth, "
        "both year on year. Ex-pandemic drops "
        f"{_quarter(window_start)} to {_quarter(window_end)} — two years, because a 2021 "
        "change is measured against 2020. Demand: JODI secondary table, total products. "
        "GDP: OECD Quarterly National Accounts, seasonally adjusted, chain-linked volume. "
        "Rest of World is not fitted: Russia does not report to JODI and no world GDP "
        "series exists."
    )

for block, card in cards.items():
    label = od.BLOCK_LABELS[block]
    with section(f"{label} — demand growth against GDP growth"):
        st.plotly_chart(_scatter(panels[block], card))
        st.caption(
            f"Model card. Estimation window {_quarter(card['estimation_start'])} to "  # type: ignore[arg-type]
            f"{_quarter(card['estimation_end'])}; "  # type: ignore[arg-type]
            f"last refit {pd.Timestamp(card['last_refit']).date()}; "  # type: ignore[arg-type]
            f"out-of-sample {card['oos_status']} against the benchmark "
            f"“{card['benchmark']}” (RMSE {card['rmse_model']:.2f} vs "
            f"{card['rmse_benchmark']:.2f}, {card['exceptions']} exceptions in "
            f"{card['n_forecasts']} quarters); structural break test dates "
            f"{card['break_date']}."
        )
        if block == "ea":
            source_note(
                "Euro area ex Malta: nineteen members. Malta has gaps in its reporting and "
                "is 0.29 % of the total. A quarter with any member missing is not shown."
            )

scenario = read_ts_long(series_prefix="derived.oil_demand.", source="derived")
scenario = scenario[scenario["series_id"].str.endswith(".scenario")]
if not scenario.empty:
    with section("Scenario — demand growth implied by assumed GDP growth"):
        table = scenario.assign(
            Block=scenario["geo"], Quarter=scenario["ts"].map(_quarter)
        )[["Block", "Quarter", "value"]].rename(columns={"value": "Demand, % y/y"})
        st.dataframe(table, hide_index=True)
        st.caption(
            "An assumption, not a forecast. These rows apply the full-panel fit to the GDP "
            "growth set in pipelines/derived/oil_demand/gdp_assumptions.csv, whose author "
            "and date are recorded in that file. Read each beside its block's p-value above."
        )
```

Three things to check against the real modules rather than trust from this plan:
`components.section.page_header`'s `freshness` wording on neighbouring pages (copy their
style); that `GREY`, `NAVY`, `RED` are importable from `core.theme` (`20_cracks.py` imports
all three); and whether `# type: ignore` comments are needed at all once `model_card`'s
return type is seen by mypy — remove any that mypy reports as unused.

- [ ] **Step 5: Run the tests, then look at the page**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pages_oil_demand.py tests/test_pages_smoke.py -v`
Expected: PASS. Then `streamlit run apps/dashboard/app.py`, open Fundamentals → Oil Demand,
and confirm on the real lake: three blocks, six fit rows, China labelled "not statistically
significant", the US R-squared visibly lower ex-pandemic, and no scenario section.

- [ ] **Step 6: Commit**

```bash
git add apps/dashboard/pages/23_oil_demand.py apps/dashboard/nav.py tests/test_pages_oil_demand.py
git commit -m "feat(dashboard): oil demand elasticity page, both panels side by side"
```

---

### Task 6: read the port against the workbook, and record the comparison

**Files:**
- Modify: `docs/superpowers/specs/2026-10-10-oil-demand-model-mapping.md` (append a section)

**Interfaces:**
- Consumes: the page from Task 5 on the real lake; `~/Desktop/skill-pdfs/oil_demand.xlsx`, sheets `OLS.*` and `For_OLS`
- Produces: a prose section, "Port compared with the workbook". No code.

This task needs the owner's go-ahead to open the licensed workbook. If that has not been
given, stop here and report Tasks 1–5 as complete; nothing above depends on this.

The conventions require a published benchmark beside the repo's estimate with the deviation.
The workbook's coefficients are licensed, so the comparison is recorded **in words and
structure, never as a figure** — the same rule the Hormuz port follows. A sentence such as
"our US slope ex-pandemic is lower than the workbook's" is fine; either number is not, and
neither is a ratio or difference from which the workbook's number can be recovered given
ours, because ours is public on the page.

- [ ] **Step 1: Establish what the workbook actually regressed, per block.** From `For_OLS`:
  is the change quarter-on-quarter or year-on-year; is GDP a percentage or a level (the spec
  already found the USA block uses a level in US$bn); what are the first and last quarters;
  is 2020 in the panel. Write down each as a fact about structure.

- [ ] **Step 2: Compare direction and rank only.** For each block: does our slope have the
  same sign; is it larger or smaller; is our R-squared higher or lower; does the workbook's
  weakest block (China) match ours. For the USA block, state plainly that the two slopes are
  in different units and are not comparable at all.

- [ ] **Step 3: Record the reasons a difference is expected,** in this order of likely
  size: specification (year-on-year percentage here, whatever Step 1 found there); demand
  source (JODI total products against Bloomberg's series); GDP source (OECD against
  Bloomberg Economics); the euro-area basket; the panel's end date.

- [ ] **Step 4: Append the section to the spec** and re-read it for any number that came
  from the workbook. `git diff` the spec and search the diff for digits before committing.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-10-10-oil-demand-model-mapping.md
git commit -m "docs(demand): the port compared with the workbook, in structure not figures"
```

---

## Out of scope, deliberately

- **Rest of World.** Russia reports nothing to JODI and no world real GDP series exists on a
  free route. A G20 proxy covers the GDP side only. Not fitted, and the page says so.
- **The balance itself and the supply side.** Spec sequencing step 4. The supply side's
  analyst overlays are judgement, not data, and need their own design.
- **The Hormuz overlay.** Already ported (`core/hormuz.py`, `pipelines/derived/hormuz.py`).
- **A demand level path.** The scenario is a growth rate. Compounding it onto the last
  observed level is one line, but it would put a kb/d number on a chart whose only input is
  an assumption; wait until the balance needs it.
- **Scheduling.** Neither pull is registered in `infra/run_scheduled.py`. JODI demand
  belongs in the monthly cadence beside `pipelines.jodi.pull_jodi` once the first cached run
  exists; that is a one-line follow-up for the owner to approve.
- **GDP forecasts from the IMF World Economic Outlook.** The owner chose user-set
  assumptions. The legacy IMF SDMX host is dead; a WEO route would need its own spike.
- **Reconciling `freq`.** `core/CLAUDE.md` records that the lake mixes `"M"` and
  `"monthly"`. This plan writes pandas aliases, the majority convention, and changes nothing
  existing.

## Self-review

**Spec coverage.** "What I would build first" step 1 (confirm the consumption route) → done
before the plan, recorded in the spec's "Routes confirmed live" section. Step 2 (Hormuz
overlay) → already built. Step 3 (refit the elasticities with and without 2020, shown beside
the workbook's with the deviation) → Tasks 1–5, and Task 6 for the comparison. Step 4 (the
balance) → out of scope with a reason. The spec's four structural observations: USA units
differ → global constraint and Task 6 Step 2; lost regressor labels → Task 6 Step 1; China's
weak fit belongs on the model card → Task 5 requirement 2; 2020 in the panel → `PANDEMIC_WINDOW`,
widened to cover the base-effect year, which the spec's later section found. The forward-path
decision (user-set assumptions, chosen by the owner) → Task 4. "What cannot be ported" (analyst
overlays) → out of scope.

**Placeholder scan.** Every code step carries real code. Task 3's module is the code that ran
on the real panel on 2026-10-10. Task 6 is a procedure with its traps named, because how the
port compares is not knowable until it is read against the workbook, and the result may not be
written down as a figure.

**Type consistency.** `download_annual_csv(..., table=)` (Task 1) is called with
`table="secondary"` in Task 1 only. `fetch_real_gdp_growth` returns the four columns
`to_ts_long` reads (Task 2). `jodi.total_demand.<cc>` and `oecd.gdp_real_yoy.<geo>` are
written in Tasks 1–2 and read under those exact ids in Task 4; the block keys `us`/`cn`/`ea`
are the lowercase of the `geo` codes Task 2 writes, which is what `read_gdp_yoy` relies on.
`BLOCKS`, `BLOCK_LABELS`, `EURO_AREA_BASKET`, `PANDEMIC_WINDOW`, `BENCHMARK`, `ElasticityFit`
and `model_card` (Task 3) are used with matching names in Tasks 4 and 5. `build_panel`,
`read_monthly_demand` and `read_gdp_yoy` (Task 4) are imported by the page (Task 5) with the
signatures given. The `.scenario` suffix is introduced in Task 4 and asserted in Tasks 4 and 5.

**Review Focus.** All five lines have a named test in the owning task.

**Known soft spots.** (1) Tasks 2 and 5 were not run before the plan was written; only Task
3's arithmetic and the two routes were. Expect small adjustments there — the page's
`# type: ignore` comments and `page_header` wording in particular. (2)
`test_out_of_sample_fails_when_gdp_explains_nothing` depends on a seeded fixture; Step 4 of
Task 3 says what to do if it is too kind. (3) `MIN_OBSERVATIONS = 20` and `test_size = 8` are
judgement, not derived from anything; they are named constants so the owner can change them.
