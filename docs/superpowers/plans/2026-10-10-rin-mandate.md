# RIN Mandate Port — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the RIN workbook's implied-mandate arithmetic into Python on confirmed public
data, and check it cell-by-cell against the workbook's own `RVO Billion RINs` block.

**Architecture:** A fourth fetch variant on the existing `EIAClient` for the STEO route (its
facet and field names differ from every other route), an ingest entrypoint that splits STEO's
measured history from its 18-month model output using a boundary read live from EIA's own
monthly actuals, two dated and attributed EPA reference CSVs, pure mandate arithmetic in
`core/rin.py`, and a derived pipeline writing `derived.rin.*`. EPA EMTS — actual RIN
generation — is deliberately out of scope; its route shape is unconfirmed and the mandate half
needs none of it.

**Tech Stack:** Python 3.12, pandas, duckdb, requests, pytest + vcrpy cassettes, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-10-10-rin-model-mapping.md` — read its
"Routes confirmed live, 2026-10-10" section before Task 1. Every series code and field name in
this plan was read from a live response on that date.

## Global Constraints

- Python 3.12. Ask before adding any dependency. Nothing here needs one.
- All scalar series conform to `ts_long(series_id, source, ts, value, unit, geo, freq, revision_date)` — `core/schemas.py`. Do not change the schema.
- Secrets only via `core.settings`. Never print, log or commit an API key. STEO reuses `settings.eia_api_key`; no new key exists or is needed.
- `core/` modules never touch DuckDB. Pipelines write the lake; pages read it.
- **No data is not zero.** An absent input yields NaN and writes no row. A degenerate input fails loudly and visibly.
- **A projection is never an observation.** STEO rows after the confirmed history boundary carry `.projected` in the series id; measured rows carry `.observed`. No row is written under an id that does not say which it is.
- **1 barrel = 42 US gallons** — the workbook's own documented transform. Define it once, in `core/rin.py`.
- The RFS percentage standards apply to **non-renewable** gasoline and distillate. The denominator is `MGTCPUSX_P` + `DFTCPUS_P`, never `MGTCPUSX` + `DFTCPUS`.
- EPA volume targets for 2026 and 2027 are **proposed**, not final. Every reference row carries a `status` of `final` or `proposed`, and nothing downstream may present a proposed figure without that status.
- Every reference CSV carries `source` and `as_of` columns so a figure can be traced.
- British English in all prose, labels and docstrings.
- Charts use `core.theme`; no ad-hoc colours. Pages use `components.section`.
- Licensed workbook figures never enter a tracked file — and note that a *scenario output* inverts to its licensed inputs when the levers are public. See `pipelines/derived/CLAUDE.md`.
- Nothing in this plan is registered in `infra/run_scheduled.py`. Run by hand.
- End green: `ruff check .`, `mypy core pipelines infra apps`, `pytest`.

---

### Task 1: STEO series registry and a fourth client fetch variant

**Files:**
- Create: `pipelines/eia/steo_series.py`
- Modify: `pipelines/eia/client.py` (add alongside `_fetch_facet_rows`)
- Test: `tests/test_eia_steo.py`

**Interfaces:**
- Consumes: `pipelines.eia.client.EIAClient`, `core.settings.settings`
- Produces: `STEO_SERIES: dict[str, SteoMeta]`, `RFS_DENOMINATOR_CODES: tuple[str, str]`, and
  `EIAClient.get_steo_series(codes: list[str], frequency: str) -> pd.DataFrame` returning the
  eight `ts_long` columns with `source="eia_steo"`

**Why a fourth variant and not a widened `get_series`:** `get_series` sends
`facets[series][]` and reads `row["series"]`, `row["units"]`, `row["area-name"]`. STEO takes
`facets[seriesId][]` and returns `seriesId`, `unit`, `seriesDescription`, and no `area-name`
whatsoever. Widening the existing method means a branch in every field access for one route.
The client already has three variants for this exact reason.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eia_steo.py
from __future__ import annotations

import pandas as pd
import pytest


def test_steo_registry_holds_the_confirmed_codes_and_the_petroleum_based_denominators() -> None:
    """The `_P` series are the RFS denominator -- the headline totals include the renewable
    volume already blended in, so using them double-counts. Confirmed live 2026-10-10."""
    from pipelines.eia.steo_series import RFS_DENOMINATOR_CODES, STEO_SERIES

    for code in ("MGTCPUSX", "DFTCPUS", "JFTCPUS", "EOTCPUS", "BDTCPUS_PS",
                 "RDTCPUS_PS", "PATCPUSX", "MGTCPUSX_P", "DFTCPUS_P"):
        assert code in STEO_SERIES, code
        assert STEO_SERIES[code].unit == "million barrels per day"
        assert STEO_SERIES[code].freq == "M"

    # Codes the workbook's own labels imply but EIA does not publish. Confirmed live.
    for absent in ("MGTCPUS", "JKTCPUS", "COTCPUS"):
        assert absent not in STEO_SERIES, f"{absent} is not published by EIA"

    assert RFS_DENOMINATOR_CODES == ("MGTCPUSX_P", "DFTCPUS_P")


@pytest.mark.vcr
def test_get_steo_series_reads_steos_own_field_names() -> None:
    """STEO returns `seriesId`/`unit`/`seriesDescription` and no `area-name`. The existing
    `get_series` reads `series`/`units`/`area-name` and cannot be pointed at this route."""
    from pipelines.eia.client import EIAClient

    df = EIAClient(api_key="dummy").get_steo_series(["MGTCPUSX"], "monthly")

    assert list(df.columns) == [
        "series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"
    ]
    assert (df["source"] == "eia_steo").all(), "source must distinguish an outlook from eia actuals"
    assert (df["series_id"] == "MGTCPUSX").all()
    assert (df["unit"] == "million barrels per day").all()
    assert (df["geo"] == "US").all()
    assert df["value"].notna().all()
    assert pd.api.types.is_datetime64_any_dtype(df["ts"])
    assert df["ts"].max() >= pd.Timestamp("2027-01-01"), "STEO must carry its forward path"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_eia_steo.py -v`
Expected: FAIL — `ModuleNotFoundError: pipelines.eia.steo_series`, then
`AttributeError: 'EIAClient' object has no attribute 'get_steo_series'`.

- [ ] **Step 3: Write the registry**

```python
# pipelines/eia/steo_series.py
"""Hand-maintained STEO series reference table -- same precedent as
pipelines/macro/fred_series.py. Every (unit, freq) pair was read from that code's own live
`/v2/steo/facet/seriesId` + data response on 2026-10-10, never guessed from the code.

Three codes the workbook's labels imply -- MGTCPUS, JKTCPUS, COTCPUS -- are NOT published by
EIA. They are recorded in the spec rather than here, so a future reader does not re-guess them.

The `_P` pair is the one that changes the arithmetic: the RFS percentage standards apply to
non-renewable gasoline and distillate, so `MGTCPUSX_P`/`DFTCPUS_P` are the correct denominator.
`MGTCPUSX`/`DFTCPUS` include the renewable volume already blended in, and using them inflates
the implied mandate invisibly."""

from __future__ import annotations

from typing import NamedTuple


class SteoMeta(NamedTuple):
    unit: str
    freq: str
    geo: str
    description: str


MBD = "million barrels per day"

STEO_SERIES: dict[str, SteoMeta] = {
    "MGTCPUSX": SteoMeta(MBD, "M", "US", "Motor Gasoline Product Supplied"),
    "DFTCPUS": SteoMeta(MBD, "M", "US", "Distillate Fuel Oil Product Supplied"),
    "JFTCPUS": SteoMeta(MBD, "M", "US", "Jet Fuel Product Supplied"),
    "EOTCPUS": SteoMeta(MBD, "M", "US", "Fuel Ethanol Consumption"),
    "BDTCPUS_PS": SteoMeta(MBD, "M", "US", "Biodiesel Product Supplied"),
    "RDTCPUS_PS": SteoMeta(MBD, "M", "US", "Renewable Diesel Product Supplied"),
    "PATCPUSX": SteoMeta(MBD, "M", "US", "Total Petroleum and Other Liquids Product Supplied"),
    # The RFS denominator -- non-renewable only. See the module docstring.
    "MGTCPUSX_P": SteoMeta(MBD, "M", "US", "Petroleum-based Gasoline Consumption"),
    "DFTCPUS_P": SteoMeta(MBD, "M", "US", "Petroleum-based Distillate Consumption"),
}

RFS_DENOMINATOR_CODES: tuple[str, str] = ("MGTCPUSX_P", "DFTCPUS_P")
```

- [ ] **Step 4: Add the client method**

Add to `pipelines/eia/client.py`, beside the existing fetch variants. Reuse `PAGE_SIZE`,
`raise_sanitised` and the existing null-value-skip convention verbatim — EIA returns literal
null values on some early-history rows and `float(None)` crashes a full-history pull.

```python
    def _fetch_steo_rows(self, codes: list[str], frequency: str) -> list[dict[str, Any]]:
        """STEO's facet is `seriesId`, not `series` -- confirmed live 2026-10-10. Its rows
        carry `seriesId`/`unit`/`seriesDescription` and no `area-name`, so `_fetch_rows`
        cannot serve this route."""
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            params: dict[str, Any] = {
                "api_key": self._api_key,
                "frequency": frequency,
                "data[0]": "value",
                "facets[seriesId][]": codes,
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
                "offset": offset,
                "length": PAGE_SIZE,
            }
            response = requests.get(f"{BASE_URL}/steo/data/", params=params, timeout=30)
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

    def get_steo_series(self, codes: list[str], frequency: str) -> pd.DataFrame:
        """`source="eia_steo"`, never plain `"eia"`: STEO is an 18-month model outlook and the
        source field is the only place a reader learns that before looking at the dates.
        `geo` is hardcoded "US" because STEO returns no area field at all -- every code in
        STEO_SERIES is a US national aggregate."""
        rows = self._fetch_steo_rows(codes, frequency)
        raw_rows, rows = rows, [row for row in rows if row.get("value") is not None]
        dropped = len(raw_rows) - len(rows)
        if dropped:
            print(f"steo: dropped {dropped} row(s) with no value", flush=True)
        pulled_at = datetime.now(UTC)
        return pd.DataFrame(
            {
                "series_id": [row["seriesId"] for row in rows],
                "source": "eia_steo",
                "ts": pd.to_datetime([row["period"] for row in rows]),
                "value": [float(row["value"]) for row in rows],
                "unit": [row["unit"] for row in rows],
                "geo": "US",
                "freq": frequency,
                "revision_date": pulled_at,
            }
        )
```

- [ ] **Step 5: Record the cassette and run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_eia_steo.py -v`
Expected: PASS. `tests/conftest.py`'s `filter_query_parameters` already scrubs `api_key` from
recorded cassettes — confirm the recorded cassette under `tests/cassettes/` contains no key
before committing. If it does, stop and fix the filter rather than editing the cassette.

- [ ] **Step 6: Commit**

```bash
git add pipelines/eia/steo_series.py pipelines/eia/client.py tests/test_eia_steo.py tests/cassettes/
git commit -m "feat(eia): STEO series registry and a fourth client fetch variant"
```

---

### Task 2: the observed/projected boundary, read live and never assumed

**Files:**
- Create: `pipelines/eia/steo_boundary.py`
- Test: `tests/test_eia_steo_boundary.py`

**Interfaces:**
- Consumes: `EIAClient.get_series` (for `petroleum/sum/snd`)
- Produces: `history_end(client: EIAClient) -> pd.Timestamp`, and
  `split_observed_projected(df: pd.DataFrame, boundary: pd.Timestamp) -> pd.DataFrame` which
  returns the same frame with each `series_id` suffixed `.observed` or `.projected`

**The problem, stated exactly:** STEO rows carry no forecast flag, the route metadata carries
no vintage, and the only hint anywhere is the description's "18 month projections". A naive
ingest writes model output into the lake indistinguishable from measured history. The boundary
comes instead from an authoritative EIA route: `petroleum/sum/snd`,
`facets[series][]=MGFUPUS1` (US Product Supplied of Finished Motor Gasoline, monthly). Its
last period was **2026-07** on 2026-10-10.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eia_steo_boundary.py
from __future__ import annotations

import pandas as pd
import pytest


def _steo_frame(periods: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": "MGTCPUSX",
            "source": "eia_steo",
            "ts": pd.to_datetime(periods),
            "value": range(len(periods)),
            "unit": "million barrels per day",
            "geo": "US",
            "freq": "monthly",
            "revision_date": pd.Timestamp("2026-10-10"),
        }
    )


def test_rows_at_or_before_the_boundary_are_observed_and_later_rows_are_projected() -> None:
    from pipelines.eia.steo_boundary import split_observed_projected

    df = _steo_frame(["2026-06", "2026-07", "2026-08", "2027-12"])
    out = split_observed_projected(df, pd.Timestamp("2026-07-01"))

    by_ts = dict(zip(out["ts"], out["series_id"], strict=True))
    assert by_ts[pd.Timestamp("2026-06-01")] == "MGTCPUSX.observed"
    assert by_ts[pd.Timestamp("2026-07-01")] == "MGTCPUSX.observed"
    assert by_ts[pd.Timestamp("2026-08-01")] == "MGTCPUSX.projected"
    assert by_ts[pd.Timestamp("2027-12-01")] == "MGTCPUSX.projected"


def test_no_row_keeps_an_unlabelled_series_id() -> None:
    """The whole point. An id that does not say observed or projected must not reach the lake."""
    from pipelines.eia.steo_boundary import split_observed_projected

    out = split_observed_projected(_steo_frame(["2026-06", "2026-08"]), pd.Timestamp("2026-07-01"))
    assert out["series_id"].str.endswith((".observed", ".projected")).all()


def test_a_missing_boundary_is_refused_rather_than_defaulted() -> None:
    """A missing boundary must fail loudly. Defaulting it -- to today, or to the series max --
    silently relabels EIA's model output as measured history, which is the one error this
    module exists to prevent."""
    from pipelines.eia.steo_boundary import split_observed_projected

    with pytest.raises(ValueError, match="boundary"):
        split_observed_projected(_steo_frame(["2026-06"]), None)  # type: ignore[arg-type]


@pytest.mark.vcr
def test_history_end_comes_from_eias_own_monthly_actuals() -> None:
    """Not from today's date, not from the STEO series max. Confirmed live 2026-10-10:
    MGFUPUS1's last monthly period was 2026-07."""
    from pipelines.eia.client import EIAClient
    from pipelines.eia.steo_boundary import history_end

    boundary = history_end(EIAClient(api_key="dummy"))

    assert isinstance(boundary, pd.Timestamp)
    assert boundary >= pd.Timestamp("2026-07-01")
    assert boundary < pd.Timestamp("2027-01-01"), "a boundary inside STEO's forecast is wrong"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_eia_steo_boundary.py -v`
Expected: FAIL — `ModuleNotFoundError: pipelines.eia.steo_boundary`.

- [ ] **Step 3: Write the module**

```python
# pipelines/eia/steo_boundary.py
"""Where STEO's measured history ends and its 18-month model output begins.

STEO rows carry no forecast flag, the route metadata carries no vintage, and the only hint
anywhere is the route description's "Monthly short term (18 month) projections". Writing the
series unlabelled would put EIA's model output into the lake wearing the same clothes as
measured history -- and 2027-12 gasoline demand is not an observation.

The boundary is therefore read from a different, authoritative EIA route: the monthly
supply-and-disposition actuals. Confirmed live 2026-10-10: `MGFUPUS1`'s last monthly period
was 2026-07, so STEO 2026-08 onward is model output.

Deliberately NOT derived from today's date (the STEO vintage lags the calendar by a variable
amount) and NOT from the STEO series maximum (that is the forecast horizon, the opposite end).
"""

from __future__ import annotations

import pandas as pd

from pipelines.eia.client import EIAClient

ACTUALS_ROUTE = "petroleum/sum/snd"
ACTUALS_SERIES = "MGFUPUS1"
"""US Product Supplied of Finished Motor Gasoline, monthly, MBBL. Gasoline is the right
bellwether: it is the largest RFS denominator component and EIA publishes it on the same
monthly cadence as every other product in this pull."""


def history_end(client: EIAClient) -> pd.Timestamp:
    """Last month for which EIA publishes a measured value. Raises if the route returns
    nothing -- a boundary that cannot be established must stop the pull, not be guessed."""
    actuals = client.get_series(ACTUALS_ROUTE, [ACTUALS_SERIES], "monthly")
    if actuals.empty:
        raise ValueError(
            f"{ACTUALS_ROUTE}/{ACTUALS_SERIES} returned no rows, so STEO's history boundary "
            "cannot be established; refusing to label model output as observed"
        )
    return pd.Timestamp(actuals["ts"].max())


def split_observed_projected(df: pd.DataFrame, boundary: pd.Timestamp) -> pd.DataFrame:
    """Suffixes every `series_id` with `.observed` or `.projected`. Every row gets one or the
    other; there is no unlabelled path out of this function."""
    if not isinstance(boundary, pd.Timestamp):
        raise ValueError(
            f"boundary must be a Timestamp, got {type(boundary).__name__} -- defaulting it "
            "would relabel EIA's model output as measured history"
        )
    out = df.copy()
    suffix = out["ts"].le(boundary).map({True: ".observed", False: ".projected"})
    out["series_id"] = out["series_id"].astype(str) + suffix
    return out
```

- [ ] **Step 4: Record the cassette and run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_eia_steo_boundary.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add pipelines/eia/steo_boundary.py tests/test_eia_steo_boundary.py tests/cassettes/
git commit -m "feat(eia): ground STEO's observed/projected boundary in EIA's own actuals"
```

---

### Task 3: the STEO ingest entrypoint

**Files:**
- Create: `pipelines/eia/pull_steo.py`
- Modify: `pipelines/eia/CLAUDE.md` (append a STEO section)
- Test: `tests/test_pull_steo.py`

**Interfaces:**
- Consumes: `STEO_SERIES`, `EIAClient.get_steo_series`, `history_end`,
  `split_observed_projected`, `core.storage.write_ts_long`,
  `core.failures.failure_scope`/`record_failure`
- Produces: `main() -> None`; lake series `steo.<lowercased code>.{observed,projected}`

**Series id shape:** lowercase the EIA code and prefix `steo.`, matching the lake's lowercase
dotted style — `MGTCPUSX_P` becomes `steo.mgtcpusx_p.observed`. The `source` column is
`eia_steo`, which is what distinguishes these rows from `source="eia"` actuals.

**Not scheduled.** STEO releases monthly, but nothing here is registered in
`infra/run_scheduled.py` — run it by hand after a release.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pull_steo.py
from __future__ import annotations

import pandas as pd
import pytest


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": ["MGTCPUSX"] * 3,
            "source": "eia_steo",
            "ts": pd.to_datetime(["2026-06", "2026-07", "2026-08"]),
            "value": [8.1, 8.2, 8.3],
            "unit": "million barrels per day",
            "geo": "US",
            "freq": "monthly",
            "revision_date": pd.Timestamp("2026-10-10"),
        }
    )


def test_main_writes_both_labelled_variants_and_reports_the_boundary(
    tmp_path, monkeypatch, capsys
) -> None:
    """The run log must name the boundary. A reader who cannot see where history ended cannot
    tell which half of the series is a model."""
    from core import storage
    from pipelines.eia import pull_steo

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")

    class FakeClient:
        def get_steo_series(self, codes, frequency):
            return _frame()

        def get_series(self, route, series, frequency):
            return pd.DataFrame({"ts": pd.to_datetime(["2026-07"]), "value": [277320.0]})

    monkeypatch.setattr(pull_steo, "EIAClient", lambda *a, **k: FakeClient())
    pull_steo.main()

    written = storage.read_ts_long(
        series_ids=["steo.mgtcpusx.observed", "steo.mgtcpusx.projected"]
    )
    assert set(written["series_id"]) == {"steo.mgtcpusx.observed", "steo.mgtcpusx.projected"}
    assert len(written[written["series_id"] == "steo.mgtcpusx.observed"]) == 2
    assert len(written[written["series_id"] == "steo.mgtcpusx.projected"]) == 1
    assert (written["source"] == "eia_steo").all()

    assert "2026-07" in capsys.readouterr().out, "the run log must state the history boundary"


def test_main_writes_nothing_when_the_boundary_cannot_be_established(
    tmp_path, monkeypatch
) -> None:
    """A failed boundary lookup must abort BEFORE any fetch or write. Writing the series
    unlabelled, or labelling it against a guessed boundary, is the failure this pipeline
    exists to avoid."""
    from core import storage
    from pipelines.eia import pull_steo

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")

    class NoBoundaryClient:
        def get_steo_series(self, codes, frequency):
            raise AssertionError("STEO must not be fetched before the boundary is known")

        def get_series(self, route, series, frequency):
            return pd.DataFrame(columns=["ts", "value"])

    monkeypatch.setattr(pull_steo, "EIAClient", lambda *a, **k: NoBoundaryClient())

    with pytest.raises(ValueError, match="boundary"):
        pull_steo.main()

    assert storage.read_ts_long(series_ids=["steo.mgtcpusx.observed"]).empty
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pull_steo.py -v`
Expected: FAIL — `ModuleNotFoundError: pipelines.eia.pull_steo`.

- [ ] **Step 3: Write the entrypoint**

Order matters and is asserted by the second test: establish the boundary **first**, then
fetch. Follow `pipelines/futures/pull_ibkr_curve.py` for the `failure_scope`/`record_failure`
shape.

```python
# pipelines/eia/pull_steo.py
"""Ingests the EIA Short-Term Energy Outlook into the lake, labelled.

Writes `steo.<code>.observed` and `steo.<code>.projected` under `source="eia_steo"`. The split
is not cosmetic: STEO is an 18-month model outlook with no per-row forecast flag, so without
it the lake cannot distinguish EIA's projection of 2027 gasoline demand from a measurement of
2026's. See pipelines/eia/steo_boundary.py.

Not scheduled. STEO releases monthly; run this by hand after a release."""

from __future__ import annotations

from core.failures import failure_scope, record_failure
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient
from pipelines.eia.steo_boundary import history_end, split_observed_projected
from pipelines.eia.steo_series import STEO_SERIES

SOURCE = "eia_steo"


def _lake_series_id(code: str) -> str:
    return f"steo.{code.lower()}"


def main() -> None:
    client = EIAClient()

    # Boundary first: if it cannot be established there is nothing safe to write.
    boundary = history_end(client)
    print(f"steo: history ends {boundary.date()}; later periods are model output", flush=True)

    raw = client.get_steo_series(list(STEO_SERIES), "monthly")
    if raw.empty:
        record_failure(SOURCE, "steo returned no rows")
        return

    raw = raw.copy()
    raw["series_id"] = raw["series_id"].map(_lake_series_id)
    labelled = split_observed_projected(raw, boundary)

    with failure_scope(SOURCE):
        write_ts_long(labelled, source=SOURCE)

    counts = labelled["series_id"].str.rsplit(".", n=1).str[-1].value_counts()
    print(
        f"steo: wrote {len(labelled)} rows across {labelled['series_id'].nunique()} series "
        f"({int(counts.get('observed', 0))} observed, "
        f"{int(counts.get('projected', 0))} projected)",
        flush=True,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pull_steo.py -v`
Expected: PASS, 2 tests.

- [ ] **Step 5: Run it for real, once**

Run: `.venv/Scripts/python.exe -m pipelines.eia.pull_steo`
Expected: a printed boundary, then a row count across 18 series (9 codes × 2 labels). Record
the real boundary and counts in the commit message. If the boundary comes back later than
2026-07 that is a newer EIA release and is correct — note it, do not pin it.

- [ ] **Step 6: Append to `pipelines/eia/CLAUDE.md`**

Document: the `seriesId` facet and field-name difference; the three codes EIA does not publish;
the `_P` denominator rule and why the totals are wrong; the boundary mechanism and why neither
today's date nor the series max can serve; and `source="eia_steo"` as the marker that these
rows are an outlook.

- [ ] **Step 7: Commit**

```bash
git add pipelines/eia/pull_steo.py pipelines/eia/CLAUDE.md tests/test_pull_steo.py
git commit -m "feat(eia): ingest STEO with observed/projected rows labelled apart"
```

---

### Task 4: EPA reference files, dated and attributed

**Files:**
- Create: `pipelines/epa/__init__.py`, `pipelines/epa/volume_targets.csv`,
  `pipelines/epa/percentage_standards.csv`, `pipelines/epa/reference.py`,
  `pipelines/epa/README.md`, `pipelines/epa/CLAUDE.md`
- Test: `tests/test_epa_reference.py`

**Interfaces:**
- Produces: `load_volume_targets(path: Path | None = None) -> pd.DataFrame`,
  `load_percentage_standards(path: Path | None = None) -> pd.DataFrame`,
  `CATEGORIES: tuple[str, ...]`, `STATUSES: tuple[str, str]`

**CSV schemas.** Both carry `source` and `as_of` so a figure can be traced, following
`pipelines/opec_momr/quotas.csv` and `pipelines/futures/contract_specs.csv`.

- `volume_targets.csv` — `year,category,billion_rins,status,source,as_of`
- `percentage_standards.csv` — `year,category,pct,source,as_of`

`category` is one of `cellulosic`, `biomass_based_diesel`, `advanced`, `total`. `status` is
`final` or `proposed` — **2026 and 2027 are proposed**, and the workbook's own How-To says so.
The biomass-based diesel step from 2025 into 2026 is roughly 65%, which is a proposal, not a
fact, and must never be presented as one.

Populate from the published EPA rulemakings. Where a figure cannot be sourced to a specific
published rule, leave the row out rather than estimating it — a missing year is a visible gap;
a guessed one is not.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_epa_reference.py
from __future__ import annotations

import pandas as pd
import pytest


def test_volume_targets_carry_a_status_and_a_traceable_source() -> None:
    from pipelines.epa.reference import load_volume_targets

    df = load_volume_targets()

    assert set(df.columns) == {"year", "category", "billion_rins", "status", "source", "as_of"}
    assert set(df["status"]) <= {"final", "proposed"}
    assert df["source"].str.len().gt(0).all(), "every figure must name the rule it came from"
    assert pd.api.types.is_datetime64_any_dtype(df["as_of"])
    assert df["billion_rins"].gt(0).all()


def test_the_2026_and_2027_targets_are_marked_proposed() -> None:
    """EPA had not finalised them. A proposal presented as a final volume is the single most
    misleading thing this file could do -- biomass-based diesel steps ~65% into 2026."""
    from pipelines.epa.reference import load_volume_targets

    forward = load_volume_targets().query("year in (2026, 2027)")

    assert not forward.empty, "the forward targets are the point of the file"
    assert (forward["status"] == "proposed").all()


def test_a_status_outside_the_allowed_pair_is_refused(tmp_path) -> None:
    from pipelines.epa.reference import load_volume_targets

    bad = tmp_path / "volume_targets.csv"
    bad.write_text(
        "year,category,billion_rins,status,source,as_of\n"
        "2025,total,22.33,assumed,EPA 2023 final rule,2026-10-10\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="status"):
        load_volume_targets(bad)


def test_a_percentage_standard_outside_zero_to_one_is_refused(tmp_path) -> None:
    """The standards are fractions. A file holding 10.47 instead of 0.1047 would inflate the
    implied mandate a hundredfold and still look plausible on a chart."""
    from pipelines.epa.reference import load_percentage_standards

    bad = tmp_path / "percentage_standards.csv"
    bad.write_text(
        "year,category,pct,source,as_of\n"
        "2025,total,10.47,EPA 2023 final rule,2026-10-10\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="pct"):
        load_percentage_standards(bad)


def test_an_unknown_category_is_refused(tmp_path) -> None:
    """A typo in a category silently drops that obligation from every join downstream."""
    from pipelines.epa.reference import load_percentage_standards

    bad = tmp_path / "percentage_standards.csv"
    bad.write_text(
        "year,category,pct,source,as_of\n"
        "2025,cellulosic_diesel,0.0047,EPA 2023 final rule,2026-10-10\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="category"):
        load_percentage_standards(bad)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_epa_reference.py -v`
Expected: FAIL — `ModuleNotFoundError: pipelines.epa.reference`.

- [ ] **Step 3: Write the CSVs and the loader**

The loader validates on read and raises `ValueError` naming the offending column — the same
"degenerate input fails loudly" rule the rest of the repo follows. Validate: `status` within
`STATUSES`; `pct` within `[0, 1]`; `billion_rins` strictly positive; `category` within
`CATEGORIES`; `as_of` parseable; `source` non-empty. Default `path=None` resolves to the CSV
beside the module, so tests can pass a fixture file without touching the committed one.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_epa_reference.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 5: Write `pipelines/epa/CLAUDE.md` and `README.md`**

`CLAUDE.md`: that this is the first EPA package; that EMTS is deliberately absent and why (its
pages serve JS tables, route shape unconfirmed as of 2026-10-10); the final-vs-proposed rule;
and that the reference CSVs are rulemaking figures, not a feed, so they change when a rule
changes and not on a clock.

`README.md`: where each figure came from, and how to add a year when EPA finalises one.

- [ ] **Step 6: Commit**

```bash
git add pipelines/epa tests/test_epa_reference.py
git commit -m "feat(epa): EPA volume targets and percentage standards as dated reference files"
```

---

### Task 5: `core/rin.py` — the mandate arithmetic, pure

**Files:**
- Create: `core/rin.py`
- Test: `tests/test_core_rin.py`

**Interfaces:**
- Consumes: pandas only. **No lake I/O** — `core/` never touches DuckDB.
- Produces: `GALLONS_PER_BARREL: Final[int] = 42`,
  `rfs_denominator_gallons(petroleum_gasoline_mbd: float | None, petroleum_distillate_mbd: float | None, days_in_period: int) -> float`,
  `implied_mandate_billion_rins(denominator_gallons: float, pct: float) -> float`

**The arithmetic.** A period's RFS denominator is the non-renewable gasoline plus distillate
volume, in gallons: `(gasoline_mbd + distillate_mbd) * 1e6 * days * 42`. The implied national
mandate for a category is that denominator times the category's percentage standard, expressed
in billions of RINs (one RIN ≈ one ethanol-equivalent gallon).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core_rin.py
"""Every figure here is synthetic and hand-checkable. The workbook's own RVO figures are
licensed; the port is checked against them separately and that comparison is recorded in
pipelines/derived/rin/README.md as prose, per pipelines/derived/CLAUDE.md's rule that a
scenario output in a tracked file inverts to its licensed inputs once the levers are public."""

from __future__ import annotations

import math

import pytest
from core.rin import (
    GALLONS_PER_BARREL,
    implied_mandate_billion_rins,
    rfs_denominator_gallons,
)


def test_a_barrel_is_forty_two_gallons() -> None:
    assert GALLONS_PER_BARREL == 42


def test_the_denominator_is_hand_computable() -> None:
    # 10 mb/d total over 100 days: 10e6 * 100 * 42 = 42.0e9 gallons.
    assert rfs_denominator_gallons(6.0, 4.0, 100) == pytest.approx(42.0e9)


def test_the_mandate_is_the_denominator_times_the_standard() -> None:
    # 42.0e9 gallons at a 10% standard = 4.2e9 RINs = 4.2 billion.
    assert implied_mandate_billion_rins(42.0e9, 0.10) == pytest.approx(4.2)


def test_an_unknown_volume_yields_nan_not_zero() -> None:
    """A missing month is not a month of zero demand. Zero would understate the mandate and
    look like a real, very low reading."""
    assert math.isnan(rfs_denominator_gallons(float("nan"), 4.0, 100))
    assert math.isnan(rfs_denominator_gallons(6.0, None, 100))


def test_a_standard_outside_zero_to_one_is_refused() -> None:
    with pytest.raises(ValueError, match="pct"):
        implied_mandate_billion_rins(42.0e9, 1.4)


def test_a_negative_volume_is_refused() -> None:
    """Product supplied cannot be negative. A sign error upstream must stop here, not
    propagate into a negative mandate."""
    with pytest.raises(ValueError, match="negative"):
        rfs_denominator_gallons(-6.0, 4.0, 100)


def test_the_denominator_excludes_the_renewable_volume_already_blended() -> None:
    """The discriminating test. The RFS standards apply to non-renewable gasoline and
    distillate, so the inputs are MGTCPUSX_P/DFTCPUS_P. Were a caller to pass the headline
    MGTCPUSX/DFTCPUS totals -- which include blended ethanol and renewable diesel -- the
    denominator would be larger and the implied mandate correspondingly inflated. This pins
    the relationship so the inflation is visible as a number rather than as a habit."""
    petroleum_only = rfs_denominator_gallons(6.0, 4.0, 100)
    including_renewables = rfs_denominator_gallons(6.6, 4.2, 100)  # +10% gasoline, +5% diesel

    assert including_renewables > petroleum_only
    assert including_renewables / petroleum_only - 1 == pytest.approx(0.08, abs=1e-9)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core_rin.py -v`
Expected: FAIL — `ModuleNotFoundError: core.rin`.

- [ ] **Step 3: Write the module**

Guards: refuse a negative volume or a `pct` outside `[0, 1]` with a `ValueError` naming the
argument; return NaN for a `None`/NaN volume rather than raising, matching
`core/hormuz.py::scenario_supply`'s own "absent stays absent" treatment.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core_rin.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add core/rin.py tests/test_core_rin.py
git commit -m "feat(core): RFS implied-mandate arithmetic, non-renewable denominator"
```

---

### Task 6: `pipelines/derived/rin.py` — write `derived.rin.*`

**Files:**
- Create: `pipelines/derived/rin.py`, `pipelines/derived/rin/README.md`
- Modify: `pipelines/derived/CLAUDE.md`
- Test: `tests/test_derived_rin.py`

**Interfaces:**
- Consumes: `core.rin`, `pipelines.epa.reference`, `core.storage.read_ts_long`/`write_ts_long`,
  the lake's `steo.mgtcpusx_p.*` and `steo.dftcpus_p.*`
- Produces: `build_mandate_rows(steo: pd.DataFrame, standards: pd.DataFrame, ingested_at: pd.Timestamp) -> pd.DataFrame`; `main() -> None`

**Series ids.** `derived.rin.mandate.<category>.observed` and
`derived.rin.mandate.<category>.projected`. The suffix is inherited from the STEO rows the row
was computed from — a mandate computed on projected demand is itself a projection, and the id
must say so. Never blend the two inside one series.

**Take two inputs, not one directory.** `pipelines/derived/hormuz.py` originally took a single
directory for both its committed levers and its git-ignored baselines; the tests passed and the
real run failed, because the fixture put every file in one tmp directory and so encoded the
wrong design. Pass the STEO frame and the standards frame separately, and include a test
asserting a standards file is not looked for beside the lake.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_derived_rin.py
from __future__ import annotations

import pandas as pd

_STANDARDS = pd.DataFrame(
    {
        "year": [2026, 2026],
        "category": ["total", "advanced"],
        "pct": [0.10, 0.04],
        "source": "synthetic",
        "as_of": pd.Timestamp("2026-10-10"),
    }
)


def _steo(periods: list[str], label: str, code: str, value: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": f"steo.{code}.{label}",
            "source": "eia_steo",
            "ts": pd.to_datetime(periods),
            "value": value,
            "unit": "million barrels per day",
            "geo": "US",
            "freq": "monthly",
            "revision_date": pd.Timestamp("2026-10-10"),
        }
    )


def _both_legs(period: str, label: str) -> pd.DataFrame:
    return pd.concat(
        [
            _steo([period], label, "mgtcpusx_p", 6.0),
            _steo([period], label, "dftcpus_p", 4.0),
        ]
    )


def test_a_mandate_computed_on_projected_demand_is_labelled_projected() -> None:
    """The rule that matters. A mandate is only as measured as the demand under it."""
    from pipelines.derived.rin import build_mandate_rows

    steo = pd.concat([_both_legs("2026-06", "observed"), _both_legs("2026-08", "projected")])
    rows = build_mandate_rows(steo, _STANDARDS, pd.Timestamp("2026-10-10"))

    ids = set(rows["series_id"])
    assert "derived.rin.mandate.total.observed" in ids
    assert "derived.rin.mandate.total.projected" in ids
    for series_id in ids:
        assert series_id.endswith((".observed", ".projected")), series_id


def test_a_month_missing_one_denominator_leg_writes_no_row() -> None:
    """Gasoline without distillate is not a denominator. Using the one leg present would
    publish a mandate roughly 40% too low that looks like a real reading."""
    from pipelines.derived.rin import build_mandate_rows

    steo = _steo(["2026-06"], "observed", "mgtcpusx_p", 6.0)  # no distillate at all
    assert build_mandate_rows(steo, _STANDARDS, pd.Timestamp("2026-10-10")).empty


def test_the_standards_are_not_read_from_beside_the_lake(tmp_path, monkeypatch) -> None:
    """Guards the hormuz lesson: a single-input signature passes a one-directory fixture and
    then fails for real. The standards arrive as an argument, never by path discovery."""
    from core import storage
    from pipelines.derived import rin

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")
    assert not list(tmp_path.rglob("percentage_standards.csv"))

    rows = rin.build_mandate_rows(
        _both_legs("2026-06", "observed"), _STANDARDS, pd.Timestamp("2026-10-10")
    )
    assert not rows.empty, "the passed-in standards must be what is used"


def test_every_row_carries_a_unit_naming_what_it_counts() -> None:
    from pipelines.derived.rin import build_mandate_rows

    rows = build_mandate_rows(
        _both_legs("2026-06", "observed"), _STANDARDS, pd.Timestamp("2026-10-10")
    )

    assert set(rows["unit"]) == {"billion RINs"}
    assert (rows["source"] == "derived").all()


def test_a_standard_with_no_matching_demand_year_writes_no_row() -> None:
    """A 2026 standard against 2025 demand is not a mandate for either year."""
    from pipelines.derived.rin import build_mandate_rows

    rows = build_mandate_rows(
        _both_legs("2025-06", "observed"), _STANDARDS, pd.Timestamp("2026-10-10")
    )
    assert rows.empty
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_derived_rin.py -v`
Expected: FAIL — `ModuleNotFoundError: pipelines.derived.rin`.

- [ ] **Step 3: Write the module**

Join the two denominator legs on `(ts, label)` with an inner join so a month missing either leg
drops out — that is what the second test pins. Join the standards on calendar year, also inner,
which is what the fifth test pins. Days per period come from the period's own calendar month
length, never a 30-day constant. Write via `write_ts_long(..., source="derived")`.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_derived_rin.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 5: Run it for real and record the result**

Run: `.venv/Scripts/python.exe -m pipelines.derived.rin`
Expected: a row count split observed/projected. Record both in the commit message.

- [ ] **Step 6: Commit**

```bash
git add pipelines/derived/rin.py pipelines/derived/rin/README.md pipelines/derived/CLAUDE.md tests/test_derived_rin.py
git commit -m "feat(derived): implied RFS mandate from the STEO baseline"
```

---

### Task 7: check the port against the workbook, and record the comparison

**Files:**
- Modify: `pipelines/derived/rin/README.md`, `pipelines/derived/CLAUDE.md`

**This is the task that earns the port.** The Hormuz port compared 35 cells against the
workbook's own `Scenario` columns and found a real `$H$4` cell-reference error in the source.
Do the same here against the workbook's `RVO Billion RINs` block.

**Licensing — read before writing anything down.** The workbook is licensed and lives in the
git-ignored `data/manual/` drop. Record the comparison as **prose and structure, never as a
table of figures**: per `pipelines/derived/CLAUDE.md`, a scenario output in a tracked file
inverts to its licensed inputs once the levers are public, and the EPA standards here *are*
public. State how many cells matched, where any mismatch falls, and what explains it. Do not
print the workbook's own RVO values.

- [ ] **Step 1: Write a throwaway comparison script in the scratchpad**

Not in the repo. It reads the workbook from `data/manual/`, recomputes via
`pipelines.derived.rin`, and prints a per-cell difference table to the terminal only.

- [ ] **Step 2: Reconcile every mismatch before writing a conclusion**

For each difference, decide which side is right and why. Three real traps, each of which has
already cost this project a wrong conclusion once:
- a units mismatch (gallons vs RINs vs barrels) looks like a model error
- the workbook may use a calendar-year denominator where this port sums months
- a `proposed` target compared against a `final` one is not a mismatch, it is two different
  questions

- [ ] **Step 3: Write the finding into `pipelines/derived/rin/README.md`**

Mirror `pipelines/derived/hormuz/README.md`'s structure: what was compared, how many matched,
where the mismatches fall, and which side is correct. If the port disagrees with the workbook
deliberately, say so and say why — a miss is a visible diagnostic, never a silent pass.

- [ ] **Step 4: Commit**

```bash
git add pipelines/derived/rin/README.md pipelines/derived/CLAUDE.md
git commit -m "docs(rin): the port checked cell-by-cell against the workbook's RVO block"
```

---

### Task 8: the dashboard page

**Files:**
- Create: `apps/dashboard/pages/<next number>_rin.py`
- Test: `tests/test_pages_rin.py`

**Interfaces:**
- Consumes: `core.storage.read_ts_long`, `components.section`, `core.theme`
- Produces: a page reading `derived.rin.mandate.*` and `steo.*`. Reads the lake only — never
  calls an API.

**The page's one hard requirement:** a projected value must be visually and textually
distinguishable from an observed one, on every exhibit. A dashed segment past the boundary, the
boundary date in a caption, and `source_note` naming both the STEO vintage and the `proposed`
status of any forward EPA target. The most recent failure of exactly this kind in this repo was
a page painting a regime state the lake deliberately withheld — see
`core.curve.determined_regime_codes`.

- [ ] **Step 1: Write the failing test**

Drive the real page through `AppTest` against an isolated lake, following
`tests/test_pages_curve_window.py`. Assert: with both observed and projected rows present the
page states the boundary date; with a `proposed` target in the frame the word "proposed"
appears in a caption; and with an empty lake it renders a real no-data message naming
`pipelines/eia/pull_steo.py` rather than an empty chart.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pages_rin.py -v`
Expected: FAIL — the page does not exist.

- [ ] **Step 3: Write the page**

`page_header(...)` then one `section(...)` per chart. No `fig.update_layout(title=...)`; no
`use_container_width`.

- [ ] **Step 4: Run the tests and the app**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pages_rin.py -v`, then
`streamlit run apps/dashboard/app.py` and look at the page.

- [ ] **Step 5: Commit**

```bash
git add apps/dashboard/pages tests/test_pages_rin.py
git commit -m "feat(dashboard): RIN mandate page, projections marked apart from observations"
```

---

## Out of scope, deliberately

- **EPA EMTS actual RIN generation.** Route shape unconfirmed as of 2026-10-10 — the pages
  return 200 but serve JS tables with no direct file link. Needs its own spike. Everything
  above is the mandate side and needs none of it.
- **Small refinery exemptions, the small-refinery capacity list, the RIN Bank, the RD project
  tracker.** All four depend on the balance, which depends on EMTS. The spec's own sequencing
  puts them last.
- **The oil demand model.** Separate plan. Its consumption route (JODI secondary) is confirmed
  live and its US and Euro-area GDP routes are confirmed; China's quarterly real GDP is not
  available on FRED and needs a spike first.

## Self-review

**Spec coverage.** Spec sequencing step 1 (confirm STEO) → done pre-plan, recorded in the
spec's new section. Step 2 (EMTS) → explicitly out of scope with a reason. Step 3 (mandate
arithmetic from baseline × percentage standards, with reference CSVs, tested against the
workbook's RVO block) → Tasks 4-7. Step 4 (RIN Bank, RD tracker) → out of scope, as the spec
itself orders. The spec's "two new pipelines and four reference files" is partially covered by
design: one pipeline (STEO) and two reference files; `pipelines/epa/` exists but holds
reference data only, and the other two files (SREs, refinery capacity) are deferred with the
balance they serve.

**Placeholder scan.** Every code step carries real code. Task 4's CSV *contents* are the one
place figures are not pre-filled — deliberately, because they must be read off published EPA
rules rather than transcribed from the licensed workbook, and the task says so along with the
validation rules that constrain them.

**Type consistency.** `SteoMeta` (Task 1) is consumed only inside `pipelines/eia`.
`history_end`/`split_observed_projected` (Task 2) are consumed by Task 3 with matching
signatures. `load_volume_targets`/`load_percentage_standards` (Task 4) return the frames Task 6
consumes, and Task 6's `_STANDARDS` fixture matches Task 4's `percentage_standards.csv` columns
exactly. `rfs_denominator_gallons`/`implied_mandate_billion_rins` (Task 5) are called by Task 6
only. The `.observed`/`.projected` suffix convention is introduced in Task 2 and asserted in
Tasks 3, 6 and 8. `RFS_DENOMINATOR_CODES` is defined in Task 1 and is what Task 6 reads from
the lake.

**One known soft spot.** Task 7 cannot be fully specified in advance: how many cells match is
not knowable until it runs, and the reconciliation is judgement. It is written as a procedure
with its traps named rather than as an expected result, which is the honest form for that task.
