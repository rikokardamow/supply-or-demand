# IBKR Curve Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put a real, current, multi-contract futures curve for `cl` and `lco` into the lake from the IBKR MCP connector, honestly labelled `.close`, with illiquid stale prints rejected rather than ingested.

**Architecture:** The connector is an MCP tool, not a Python library, so the fetch cannot run headless. An agent-side capture archives raw responses verbatim under `data/raw/ibkr/`; an ordinary Python pipeline parses that archive and writes the lake. Pure functions live in `pipelines/futures/ibkr_curve.py`; the entrypoint is `pipelines/futures/pull_ibkr_curve.py`. One existing function, `contract_panel_for`, becomes suffix-aware so the derived curve chain can read `.close`.

**Tech Stack:** Python 3.12, pandas, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-10-ibkr-curve-design.md` — read it first; this plan argues from it.

## Global Constraints

- Secrets only via `core.settings`. Never print, log or commit a key. The connector needs none.
- **IBKR calls are read-only.** `search_contracts`, `search_futures`, `get_price_history`, `get_price_snapshot` only. Never an order, alert or watchlist tool.
- Series are `fut.<root>.<contract>.close`, never `.settle`. The response's price source is `Last`.
- `source="ibkr"`, passed explicitly through every write — never hardcoded in a shared transform.
- Contract codes use a **four-digit year** (`z2026`). A code matching `f01`–`f36` is rejected.
- Values written as `float64`. `write_ts_long` already coerces; the regression test still asserts it.
- Open interest is **never** written. It is absent from the responses; absent is not `0.0`.
- British English in all prose, labels and docstrings.
- No new package tree. Both new modules are siblings inside `pipelines/futures/`.
- Lake only. No Supabase publish, no scheduler entry, no changes to `apps/dashboard/`.
- Every task ends green: `pytest`, `ruff check .`, `mypy core pipelines infra`.

---

### Task 0: Confirm the daily-bar history limit

The spec's one open question. No code; the deliverable is a recorded fact that fixes the backfill shape.

**Files:**
- Modify: `pipelines/futures/CLAUDE.md` (append a section)

**Interfaces:**
- Consumes: nothing.
- Produces: the confirmed maximum `period` for `step="ONE_DAY"` on a FUT contract, used by Task 7's capture.

- [ ] **Step 1: Probe one contract at increasing periods**

In a Claude session with the IBKR connector, call `get_price_history` four times against CL Dec 2026 (`contract_id` 296574787, `exchange` `"NYMEX"`, `security_type="FUT"`, `step="ONE_DAY"`, `outside_rth=false`), once each with `period` `"ONE_MONTH"`, `"SIX_MONTHS"`, `"ONE_YEAR"`, `"TWO_YEARS"`, `"FIVE_YEARS"`. Record for each: whether it succeeded, the returned `chart_start`, and the number of bars.

Stop at the first period that errors or silently returns the same span as the one below it. A period that returns fewer bars than a shorter period asked for is a finding, not a retry.

- [ ] **Step 2: Record the result**

Append to `pipelines/futures/CLAUDE.md`:

```markdown
## IBKR MCP connector — daily-bar history limit, confirmed live 2026-10-10

`get_price_history(step="ONE_DAY")` on a FUT contract accepts up to `period="<X>"`,
returning `<N>` bars from `<chart_start>`. `<the next period up>` <errored / returned the
same span>. The capture in
`docs/superpowers/plans/2026-10-10-ibkr-curve.md` uses `<X>` for that reason.

Not the same as the monthly-bar limit: `step="ONE_MONTH", period="FIVE_YEARS"` on CLZ7
returned bars back to 2021-10-11 (confirmed 2026-10-10).
```

- [ ] **Step 3: Commit**

```bash
git add pipelines/futures/CLAUDE.md
git commit -m "docs(futures): record the IBKR connector's daily-bar history limit"
```

---

### Task 1: Contract-code derivation

**Files:**
- Create: `pipelines/futures/ibkr_curve.py`
- Test: `tests/test_ibkr_curve.py`

**Interfaces:**
- Consumes: `pipelines.futures.client.looks_like_rank_code(contract: str) -> bool`.
- Produces: `MONTH_CODES: dict[int, str]`; `contract_code_from_month(contract_month: str) -> str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ibkr_curve.py`:

```python
"""IBKR MCP curve parsing. No cassettes exist for this source and none can: vcrpy records
HTTP made from Python, and this data arrives through an MCP tool, never through Python's
HTTP stack. The fixture under tests/fixtures/futures/ is a trimmed real response instead."""

from __future__ import annotations

import pytest

from pipelines.futures.client import looks_like_rank_code
from pipelines.futures.ibkr_curve import contract_code_from_month


def test_contract_code_from_month_covers_every_month_letter() -> None:
    codes = [contract_code_from_month(f"2026{month:02d}") for month in range(1, 13)]
    assert codes == [
        "f2026", "g2026", "h2026", "j2026", "k2026", "m2026",
        "n2026", "q2026", "u2026", "v2026", "x2026", "z2026",
    ]


def test_every_derived_code_clears_the_rank_namespace_guard() -> None:
    """A two-digit year would collide: January is "f", so f27 reads as rank 27. Eight such
    series were live in the lake before that was caught."""
    for year in (2026, 2027, 2030, 2036):
        for month in range(1, 13):
            code = contract_code_from_month(f"{year}{month:02d}")
            assert not looks_like_rank_code(code), code


def test_contract_code_rejects_a_malformed_month() -> None:
    with pytest.raises(ValueError, match="contract_month"):
        contract_code_from_month("2026-12")


def test_contract_code_rejects_an_impossible_month() -> None:
    with pytest.raises(ValueError, match="contract_month"):
        contract_code_from_month("202613")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest.exe tests/test_ibkr_curve.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipelines.futures.ibkr_curve'`

- [ ] **Step 3: Write the minimal implementation**

Create `pipelines/futures/ibkr_curve.py`:

```python
"""Parse an archived IBKR MCP curve capture into lake rows.

The connector is an MCP tool, not a Python library, so nothing here fetches anything:
the capture is archived by an agent session under data/raw/ibkr/ and this module parses
it. See docs/superpowers/specs/2026-10-10-ibkr-curve-design.md.

Prices from this source are LAST TRADE, not exchange settlement -- the response reports
its own price source as "Last". Series are therefore `.close`, never `.settle`. See
pipelines/futures/CLAUDE.md for what that difference is worth, measured.
"""

from __future__ import annotations

import re
from typing import Final

MONTH_CODES: Final[dict[int, str]] = {
    1: "f", 2: "g", 3: "h", 4: "j", 5: "k", 6: "m",
    7: "n", 8: "q", 9: "u", 10: "v", 11: "x", 12: "z",
}
"""Standard exchange delivery-month letters, January to December."""

_MONTH_RE: Final = re.compile(r"\d{6}")


def contract_code_from_month(contract_month: str) -> str:
    """IBKR's `contract_month` ("202612") -> this lake's contract code ("z2026").

    The year is deliberately four digits. A two-digit year collides with the nearby-rank
    namespace (January is "f", so "f27" is indistinguishable from rank 27) -- see
    client.looks_like_rank_code, which this module's callers assert against.
    """
    if not _MONTH_RE.fullmatch(contract_month):
        raise ValueError(f"contract_month must be YYYYMM, got {contract_month!r}")
    year = int(contract_month[:4])
    month = int(contract_month[4:])
    if month not in MONTH_CODES:
        raise ValueError(f"contract_month names no real month: {contract_month!r}")
    return f"{MONTH_CODES[month]}{year}"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest.exe tests/test_ibkr_curve.py -v`
Expected: PASS, 4 tests

- [ ] **Step 5: Lint, type-check and commit**

```bash
.venv/Scripts/ruff.exe check .
.venv/Scripts/mypy.exe core pipelines infra
git add pipelines/futures/ibkr_curve.py tests/test_ibkr_curve.py
git commit -m "feat(futures): derive lake contract codes from IBKR contract_month"
```

---

### Task 2: Bars from a history response, and the liquidity gate

The correctness core of the whole plan.

**Files:**
- Modify: `pipelines/futures/ibkr_curve.py`
- Test: `tests/test_ibkr_curve.py`

**Interfaces:**
- Consumes: Task 1's module.
- Produces: `REJECTION_REASONS: tuple[str, ...]`; `bars_from_history(history: dict) -> pd.DataFrame` (columns `ts, open, high, low, close, volume`, `ts` naive-UTC midnight); `liquid_bars(bars: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ibkr_curve.py`:

```python
import pandas as pd

from pipelines.futures.ibkr_curve import REJECTION_REASONS, bars_from_history, liquid_bars


def test_bars_from_history_reads_the_parallel_arrays_and_normalises_to_dates() -> None:
    history = {
        "time": ["2026-09-10T13:30:00Z", "2026-09-11T13:30:00Z"],
        "open": [92.39, 90.76],
        "high": [94.87, 91.81],
        "low": [91.04, 90.66],
        "close": [93.93, 91.43],
        "volume": [34571, 21699],
    }
    bars = bars_from_history(history)
    assert list(bars.columns) == ["ts", "open", "high", "low", "close", "volume"]
    # A daily bar is stamped 13:30Z by the API; the lake's daily convention is the date.
    assert list(bars["ts"]) == [pd.Timestamp("2026-09-10"), pd.Timestamp("2026-09-11")]
    assert bars["close"].dtype == "float64"


def test_bars_from_history_tolerates_an_empty_response() -> None:
    bars = bars_from_history({})
    assert bars.empty
    assert list(bars.columns) == ["ts", "open", "high", "low", "close", "volume"]


def test_liquid_bars_rejects_the_real_zero_volume_stale_print() -> None:
    """CLZ7's 2021-12 bar is 57.31 four times on volume 0 -- a carried reference price,
    not a market. Confirmed live 2026-10-10."""
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2021-12-01", "2026-10-01"]),
            "open": [57.31, 75.17],
            "high": [57.31, 77.89],
            "low": [57.31, 74.45],
            "close": [57.31, 77.39],
            "volume": [0.0, 98071.0],
        }
    )
    kept, rejected = liquid_bars(bars)
    assert list(kept["ts"]) == [pd.Timestamp("2026-10-01")]
    assert rejected["stale_print"] == 1
    assert rejected["zero_volume"] == 0  # counted once, under the more specific reason


def test_liquid_bars_counts_a_plain_zero_volume_bar_separately() -> None:
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2022-01-03"]),
            "open": [59.12], "high": [62.25], "low": [59.07], "close": [61.95],
            "volume": [0.0],
        }
    )
    kept, rejected = liquid_bars(bars)
    assert kept.empty
    assert rejected["zero_volume"] == 1
    assert rejected["stale_print"] == 0


def test_liquid_bars_left_trims_rather_than_dropping_the_contract() -> None:
    """A far-dated contract runs illiquid then liquid as it approaches the front. Keep the
    liquid tail; drop the dead beginning."""
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2021-11-01", "2021-12-01", "2026-09-01", "2026-10-01"]),
            "open": [56.5, 57.31, 71.16, 75.17],
            "high": [59.95, 57.31, 75.80, 77.89],
            "low": [56.5, 57.31, 70.10, 74.45],
            "close": [60.13, 57.31, 75.44, 77.39],
            "volume": [2.0, 0.0, 223836.0, 98071.0],
        }
    )
    kept, _ = liquid_bars(bars)
    assert len(kept) == 3
    assert kept["ts"].min() == pd.Timestamp("2021-11-01")


def test_liquid_bars_rejects_a_missing_or_non_positive_close() -> None:
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-05"]),
            "open": [75.17, 75.00, 0.0],
            "high": [77.89, 76.00, 76.00],
            "low": [74.45, 74.00, 74.00],
            "close": [None, -1.0, 75.50],
            "volume": [98071.0, 98071.0, 98071.0],
        }
    )
    kept, rejected = liquid_bars(bars)
    assert list(kept["ts"]) == [pd.Timestamp("2026-10-05")]
    assert rejected["no_close"] == 1
    assert rejected["non_positive_close"] == 1


def test_every_rejection_reason_is_reported_even_when_zero() -> None:
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2026-10-01"]),
            "open": [75.17], "high": [77.89], "low": [74.45], "close": [77.39],
            "volume": [98071.0],
        }
    )
    _, rejected = liquid_bars(bars)
    assert set(rejected) == set(REJECTION_REASONS)
    assert sum(rejected.values()) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest.exe tests/test_ibkr_curve.py -v`
Expected: FAIL — `ImportError: cannot import name 'bars_from_history'`

- [ ] **Step 3: Write the implementation**

Append to `pipelines/futures/ibkr_curve.py` (add `import pandas as pd` to the imports):

```python
_BAR_COLUMNS: Final = ["ts", "open", "high", "low", "close", "volume"]

REJECTION_REASONS: Final[tuple[str, ...]] = (
    "no_close",
    "non_positive_close",
    "stale_print",
    "zero_volume",
)
"""Why a bar was refused, in the precedence it is tested in -- most specific first, so a
rejected bar is counted exactly once. A zero-volume bar whose open, high, low and close are
all equal is a `stale_print`, which is the more informative of the two reasons."""


def bars_from_history(history: dict) -> pd.DataFrame:
    """A get_price_history response's parallel arrays -> one row per bar.

    `time` is stamped at the session open (13:30Z for NYMEX daily bars); the lake's daily
    convention is the plain date, so it is normalised to midnight. Every other daily series
    in this project does the same.
    """
    times = history.get("time") or []
    if not times:
        return pd.DataFrame({column: pd.Series(dtype="float64") for column in _BAR_COLUMNS}).assign(
            ts=pd.Series(dtype="datetime64[ns]")
        )[_BAR_COLUMNS]

    frame = pd.DataFrame(
        {
            "ts": pd.to_datetime(times, utc=True).tz_localize(None).normalize(),
            "open": pd.to_numeric(history.get("open"), errors="coerce"),
            "high": pd.to_numeric(history.get("high"), errors="coerce"),
            "low": pd.to_numeric(history.get("low"), errors="coerce"),
            "close": pd.to_numeric(history.get("close"), errors="coerce"),
            "volume": pd.to_numeric(history.get("volume"), errors="coerce"),
        }
    )
    return frame.astype({column: "float64" for column in _BAR_COLUMNS if column != "ts"})


def liquid_bars(bars: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Keep only bars that record a real trade; count and return the rest by reason.

    A bar with no volume is a carried reference price, not a market. Once in the lake it is
    indistinguishable from a real observation, and every spread, convexity and regime value
    downstream inherits it while every test still passes. 00_TRADING_CONVENTIONS.md's
    "degenerate inputs fail loudly" rule: reject, count, report -- never fill, never zero.
    """
    rejected = dict.fromkeys(REJECTION_REASONS, 0)
    if bars.empty:
        return bars, rejected

    no_close = bars["close"].isna()
    non_positive = ~no_close & (bars["close"] <= 0)
    flat = (
        bars[["open", "high", "low", "close"]].nunique(axis=1).eq(1) & bars["volume"].eq(0)
    )
    stale = ~no_close & ~non_positive & flat
    zero_volume = ~no_close & ~non_positive & ~stale & bars["volume"].eq(0)

    rejected["no_close"] = int(no_close.sum())
    rejected["non_positive_close"] = int(non_positive.sum())
    rejected["stale_print"] = int(stale.sum())
    rejected["zero_volume"] = int(zero_volume.sum())

    keep = ~(no_close | non_positive | stale | zero_volume)
    return bars[keep].reset_index(drop=True), rejected
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest.exe tests/test_ibkr_curve.py -v`
Expected: PASS, 11 tests

- [ ] **Step 5: Lint, type-check and commit**

```bash
.venv/Scripts/ruff.exe check .
.venv/Scripts/mypy.exe core pipelines infra
git add pipelines/futures/ibkr_curve.py tests/test_ibkr_curve.py
git commit -m "feat(futures): reject zero-volume stale prints from IBKR daily bars"
```

---

### Task 3: Lake rows for the closes

**Files:**
- Modify: `pipelines/futures/ibkr_curve.py`
- Test: `tests/test_ibkr_curve.py`

**Interfaces:**
- Consumes: Task 2's `liquid_bars`; `pipelines.futures.client.ContractMeta` (fields `root`, `contract`, `expiry: date`, `tick_size: float`, `contract_unit: str`, `currency: str`).
- Produces: `closes_to_ts_long(bars_by_contract: dict[str, pd.DataFrame], root: str, revision_date: pd.Timestamp, contracts: list[ContractMeta], source: str) -> pd.DataFrame`.

This mirrors `to_ts_long.settles_to_ts_long` rather than reusing it: that function's `_METRICS` is `("settle", "oi", "volume")` and its settle column is load-bearing for three other callers. A sibling keeps this source's metric names honest without editing a shared transform.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ibkr_curve.py`:

```python
from datetime import date

from pipelines.futures.client import ContractMeta
from pipelines.futures.ibkr_curve import closes_to_ts_long

_CL_Z2026 = ContractMeta(
    root="cl", contract="z2026", expiry=date(2026, 11, 20),
    tick_size=0.01, contract_unit="1000 bbl", currency="USD",
)


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": pd.to_datetime(["2026-10-08", "2026-10-09"]),
            "open": [90.78, 89.87], "high": [92.14, 91.22],
            "low": [89.50, 89.79], "close": [90.75, 91.01],
            "volume": [54091.0, 36647.0],
        }
    )


def test_closes_to_ts_long_writes_close_and_volume_but_never_oi() -> None:
    rows = closes_to_ts_long(
        {"z2026": _bars()}, root="cl",
        revision_date=pd.Timestamp("2026-10-10"), contracts=[_CL_Z2026], source="ibkr",
    )
    suffixes = {series_id.rsplit(".", 1)[1] for series_id in rows["series_id"]}
    assert suffixes == {"close", "volume"}
    assert not any(series_id.endswith(".oi") for series_id in rows["series_id"])
    assert not any(series_id.endswith(".settle") for series_id in rows["series_id"])


def test_closes_to_ts_long_uses_the_projects_unit_convention() -> None:
    rows = closes_to_ts_long(
        {"z2026": _bars()}, root="cl",
        revision_date=pd.Timestamp("2026-10-10"), contracts=[_CL_Z2026], source="ibkr",
    )
    close_rows = rows[rows["series_id"] == "fut.cl.z2026.close"]
    assert set(close_rows["unit"]) == {"USD/1000 bbl"}
    volume_rows = rows[rows["series_id"] == "fut.cl.z2026.volume"]
    assert set(volume_rows["unit"]) == {"contracts"}


def test_closes_to_ts_long_carries_the_source_through_the_frame() -> None:
    """A reused transform that hardcodes its source column silently misclassifies rows on
    read-back -- the gotcha pipelines/weather/degree_days.py hit for real."""
    rows = closes_to_ts_long(
        {"z2026": _bars()}, root="cl",
        revision_date=pd.Timestamp("2026-10-10"), contracts=[_CL_Z2026], source="ibkr",
    )
    assert set(rows["source"]) == {"ibkr"}
    assert set(rows["geo"]) == {"CL"}
    assert set(rows["freq"]) == {"D"}
    assert rows["value"].dtype == "float64"


def test_closes_to_ts_long_rejects_a_contract_code_that_looks_like_a_rank() -> None:
    bad = ContractMeta(
        root="cl", contract="f27", expiry=date(2027, 1, 20),
        tick_size=0.01, contract_unit="1000 bbl", currency="USD",
    )
    with pytest.raises(ValueError, match="f01..f36"):
        closes_to_ts_long(
            {"f27": _bars()}, root="cl",
            revision_date=pd.Timestamp("2026-10-10"), contracts=[bad], source="ibkr",
        )


def test_a_sub_dollar_value_survives_the_round_trip(tmp_path, monkeypatch) -> None:
    """The v0.11 lesson: a 0.35 spread must not read back as 0. Written alongside a
    deliberately int64-typed sibling source, reproducing the original bug's conditions."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)

    sibling = tmp_path / "ts_long" / "source=rigs" / "year=2026"
    sibling.mkdir(parents=True)
    pq.write_table(
        pa.table(
            {
                "series_id": ["rigs.us.total"], "source": ["rigs"],
                "ts": [pd.Timestamp("2026-10-09")], "value": pa.array([588], type=pa.int64()),
                "unit": ["rigs"], "geo": ["US"], "freq": ["W"],
                "revision_date": [pd.Timestamp("2026-10-10")],
            }
        ),
        sibling / "part-0.parquet",
    )

    bars = _bars()
    bars.loc[:, "close"] = [0.35, 0.35]
    rows = closes_to_ts_long(
        {"z2026": bars}, root="cl",
        revision_date=pd.Timestamp("2026-10-10"), contracts=[_CL_Z2026], source="ibkr",
    )
    storage.write_ts_long(rows, source="ibkr")

    back = storage.read_ts_long(series_ids=["fut.cl.z2026.close"])
    assert set(back["value"]) == {0.35}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest.exe tests/test_ibkr_curve.py -v`
Expected: FAIL — `ImportError: cannot import name 'closes_to_ts_long'`

- [ ] **Step 3: Write the implementation**

Append to `pipelines/futures/ibkr_curve.py`:

```python
from pipelines.futures.client import ContractMeta, looks_like_rank_code

_METRICS: Final[tuple[str, ...]] = ("close", "volume")
"""No `oi`. The connector was asked for `future_open_interest` on three contracts and
returned it on none; absent is not zero."""


def closes_to_ts_long(
    bars_by_contract: dict[str, pd.DataFrame],
    root: str,
    revision_date: pd.Timestamp,
    contracts: list[ContractMeta],
    source: str,
) -> pd.DataFrame:
    """Per-contract liquid bars -> `ts_long` rows at `fut.<root>.<contract>.close/.volume`.

    `source` is passed explicitly, never hardcoded: the DataFrame's own `source` column is a
    real parquet value that every read filters on, and a shared transform that hardcodes it
    misclassifies rows on read-back.
    """
    ambiguous = sorted(code for code in bars_by_contract if looks_like_rank_code(code))
    if ambiguous:
        raise ValueError(
            f"contract codes collide with the nearby-rank namespace f01..f36: {ambiguous}. "
            f"Use a four-digit year (e.g. 'f2027', not 'f27')."
        )

    unit_by_contract = {
        meta.contract: f"{meta.currency}/{meta.contract_unit}" for meta in contracts
    }

    frames: list[pd.DataFrame] = []
    for contract, bars in sorted(bars_by_contract.items()):
        if bars.empty:
            continue
        for metric in _METRICS:
            values = pd.to_numeric(bars[metric], errors="coerce").dropna()
            if values.empty:
                continue
            frames.append(
                pd.DataFrame(
                    {
                        "series_id": f"fut.{root}.{contract}.{metric}",
                        "source": source,
                        "ts": bars.loc[values.index, "ts"],
                        "value": values.astype("float64"),
                        "unit": (
                            unit_by_contract.get(contract, "unknown")
                            if metric == "close"
                            else "contracts"
                        ),
                        "geo": root.upper(),
                        "freq": "D",
                        "revision_date": revision_date,
                    }
                )
            )

    if not frames:
        return pd.DataFrame(columns=list(TS_LONG_COLUMNS))
    return pd.concat(frames, ignore_index=True)
```

Import `TS_LONG_COLUMNS` from `core.schemas` if it exists under that name; if the project exposes the empty frame differently, build the empty frame the way `core/storage.py::_read` does — `TS_LONG_SCHEMA.empty_table().to_pandas()`. Confirm by reading `core/schemas.py` rather than guessing.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest.exe tests/test_ibkr_curve.py -v`
Expected: PASS, 16 tests

- [ ] **Step 5: Lint, type-check and commit**

```bash
.venv/Scripts/ruff.exe check .
.venv/Scripts/mypy.exe core pipelines infra
git add pipelines/futures/ibkr_curve.py tests/test_ibkr_curve.py
git commit -m "feat(futures): turn IBKR daily bars into fut.<root>.<contract>.close rows"
```

---

### Task 4: Contract metadata and the whole-envelope parse

**Files:**
- Modify: `pipelines/futures/ibkr_curve.py`
- Test: `tests/test_ibkr_curve.py`

**Interfaces:**
- Consumes: Tasks 1–3; `pipelines.futures.client.load_contract_specs(path=CONTRACT_SPECS_PATH) -> pd.DataFrame`; `pipelines.futures.series_meta.ROLL_RULE`.
- Produces: `contracts_from_ladder(ladder: list[dict], root: str, specs: pd.DataFrame) -> list[ContractMeta]`; `series_meta_rows(contracts: list[ContractMeta], source: str) -> pd.DataFrame`; `parse_envelope(envelope: dict, specs: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict[str, int]]]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ibkr_curve.py`:

```python
from pipelines.futures.client import load_contract_specs
from pipelines.futures.ibkr_curve import (
    contracts_from_ladder,
    parse_envelope,
    series_meta_rows,
)

_LADDER = [
    {"contract_id": 296574787, "contract_month": "202612", "last_trading_date": "20261120"},
    {"contract_id": 304037396, "contract_month": "202701", "last_trading_date": "20261221"},
]


def test_contracts_from_ladder_derives_codes_and_real_expiries() -> None:
    contracts = contracts_from_ladder(_LADDER, root="cl", specs=load_contract_specs())
    assert [meta.contract for meta in contracts] == ["z2026", "f2027"]
    assert [meta.expiry for meta in contracts] == [date(2026, 11, 20), date(2026, 12, 21)]
    assert all(meta.root == "cl" for meta in contracts)
    assert all(meta.currency for meta in contracts)


def test_series_meta_rows_carry_every_column_the_manifest_requires() -> None:
    from pipelines.futures.series_meta import ROLL_RULE

    contracts = contracts_from_ladder(_LADDER, root="cl", specs=load_contract_specs())
    rows = series_meta_rows(contracts, source="ibkr")
    required = {
        "root", "contract", "expiry", "tick_size",
        "contract_unit", "currency", "roll_rule", "source",
    }
    assert required <= set(rows.columns)
    assert set(rows["source"]) == {"ibkr"}
    assert set(rows["roll_rule"]) == {ROLL_RULE}


def test_parse_envelope_maps_contract_ids_to_codes_and_reports_rejections() -> None:
    envelope = {
        "captured_at": "2026-10-10T10:39:00Z",
        "root": "cl",
        "exchange": "NYMEX",
        "ladder": _LADDER,
        "history": {
            "296574787": {
                "time": ["2026-10-08T13:30:00Z", "2026-10-09T13:30:00Z"],
                "open": [90.78, 89.87], "high": [92.14, 91.22],
                "low": [89.50, 89.79], "close": [90.75, 91.01],
                "volume": [54091, 36647],
            },
            "304037396": {
                "time": ["2026-10-09T13:30:00Z"],
                "open": [57.31], "high": [57.31], "low": [57.31], "close": [57.31],
                "volume": [0],
            },
        },
    }
    rows, meta, rejections = parse_envelope(envelope, specs=load_contract_specs())

    assert set(rows["series_id"]) == {"fut.cl.z2026.close", "fut.cl.z2026.volume"}
    assert set(rows["revision_date"]) == {pd.Timestamp("2026-10-10 10:39:00")}
    assert rejections["f2027"]["stale_print"] == 1
    assert rejections["z2026"]["stale_print"] == 0
    # series_meta lists every laddered contract, even one with no liquid bars.
    assert set(meta["contract"]) == {"z2026", "f2027"}


def test_parse_envelope_records_a_contract_with_no_history_as_a_skip() -> None:
    envelope = {
        "captured_at": "2026-10-10T10:39:00Z",
        "root": "cl",
        "exchange": "NYMEX",
        "ladder": _LADDER[:1],
        "history": {"296574787": {}},
    }
    rows, meta, rejections = parse_envelope(envelope, specs=load_contract_specs())
    assert rows.empty
    assert set(meta["contract"]) == {"z2026"}
    assert rejections["z2026"] == dict.fromkeys(REJECTION_REASONS, 0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest.exe tests/test_ibkr_curve.py -v`
Expected: FAIL — `ImportError: cannot import name 'contracts_from_ladder'`

- [ ] **Step 3: Write the implementation**

Append to `pipelines/futures/ibkr_curve.py`:

```python
from datetime import date, datetime

from pipelines.futures.series_meta import ROLL_RULE


def contracts_from_ladder(
    ladder: list[dict], root: str, specs: pd.DataFrame
) -> list[ContractMeta]:
    """A capture's ladder rows -> ContractMeta, sorted by delivery month.

    `symbol` is deliberately ignored: the connector's own documentation says it must not be
    surfaced, and the contract code is derived from `contract_month` instead.
    """
    spec = specs[specs["root"] == root]
    if spec.empty:
        raise ValueError(f"no contract_specs.csv row for root {root!r}")
    row = spec.iloc[0]

    contracts = [
        ContractMeta(
            root=root,
            contract=contract_code_from_month(str(entry["contract_month"])),
            expiry=datetime.strptime(str(entry["last_trading_date"]), "%Y%m%d").date(),
            tick_size=float(row["tick_size"]),
            contract_unit=str(row["contract_unit"]),
            currency=str(row["currency"]),
        )
        for entry in ladder
    ]
    return sorted(contracts, key=lambda meta: meta.expiry)


def series_meta_rows(contracts: list[ContractMeta], source: str) -> pd.DataFrame:
    """ContractMeta -> rows for series_meta.parquet. Its de-dup key is (root, contract)
    without source, so a real exchange expiry here replaces an earlier NULL one."""
    return pd.DataFrame(
        {
            "root": [meta.root for meta in contracts],
            "contract": [meta.contract for meta in contracts],
            "expiry": [meta.expiry for meta in contracts],
            "tick_size": [meta.tick_size for meta in contracts],
            "contract_unit": [meta.contract_unit for meta in contracts],
            "currency": [meta.currency for meta in contracts],
            "roll_rule": ROLL_RULE,
            "source": source,
        }
    )


def parse_envelope(
    envelope: dict, specs: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict[str, int]]]:
    """An archived capture -> (ts_long rows, series_meta rows, rejections by contract).

    `revision_date` is the capture's own `captured_at`, so re-parsing the same archive is
    idempotent under write_ts_long's (series_id, ts) de-dup and a later capture supersedes
    an earlier one.
    """
    root = str(envelope["root"])
    revision_date = pd.Timestamp(str(envelope["captured_at"])).tz_localize(None)
    ladder = list(envelope.get("ladder") or [])
    contracts = contracts_from_ladder(ladder, root=root, specs=specs)

    code_by_id = {
        str(entry["contract_id"]): contract_code_from_month(str(entry["contract_month"]))
        for entry in ladder
    }

    bars_by_contract: dict[str, pd.DataFrame] = {}
    rejections: dict[str, dict[str, int]] = {}
    for contract_id, history in (envelope.get("history") or {}).items():
        code = code_by_id.get(str(contract_id))
        if code is None:
            raise ValueError(f"history carries contract_id {contract_id!r} absent from the ladder")
        kept, rejected = liquid_bars(bars_from_history(history or {}))
        rejections[code] = rejected
        if not kept.empty:
            bars_by_contract[code] = kept

    rows = closes_to_ts_long(
        bars_by_contract,
        root=root,
        revision_date=revision_date,
        contracts=contracts,
        source="ibkr",
    )
    return rows, series_meta_rows(contracts, source="ibkr"), rejections
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest.exe tests/test_ibkr_curve.py -v`
Expected: PASS, 20 tests

- [ ] **Step 5: Lint, type-check and commit**

```bash
.venv/Scripts/ruff.exe check .
.venv/Scripts/mypy.exe core pipelines infra
git add pipelines/futures/ibkr_curve.py tests/test_ibkr_curve.py
git commit -m "feat(futures): parse a whole IBKR capture into lake rows and series_meta"
```

---

### Task 5: The committed fixture and the entrypoint

**Files:**
- Create: `tests/fixtures/futures/ibkr_curve_cl_20261010.json`
- Create: `pipelines/futures/pull_ibkr_curve.py`
- Modify: `tests/test_ibkr_curve.py`

**Interfaces:**
- Consumes: Task 4's `parse_envelope`; `core.failures.failure_scope`, `core.failures.record_failure`; `core.storage.write_ts_long`; `pipelines.futures.series_meta.write_series_meta`.
- Produces: `ARCHIVE_DIR: Path`; `load_envelope(path: Path) -> dict`; `main() -> None`.

- [ ] **Step 1: Build the fixture from a real capture**

Capture `cl` for real (Task 0's confirmed period), then trim to three contracts and at most eight bars each, **keeping one genuine zero-volume stale print**. Save to `tests/fixtures/futures/ibkr_curve_cl_20261010.json` with the envelope shape from the spec. The fixture is committed deliberately — it is small, it is not licensed vendor data, and it is the only way to test a source that cannot be recorded with vcrpy.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_ibkr_curve.py`:

```python
from pathlib import Path

from pipelines.futures.pull_ibkr_curve import load_envelope

_FIXTURE = Path("tests/fixtures/futures/ibkr_curve_cl_20261010.json")


def test_the_real_fixture_parses_and_its_stale_print_is_refused() -> None:
    envelope = load_envelope(_FIXTURE)
    rows, meta, rejections = parse_envelope(envelope, specs=load_contract_specs())

    assert not rows.empty
    assert set(rows["source"]) == {"ibkr"}
    assert all(sid.endswith((".close", ".volume")) for sid in rows["series_id"])
    assert not meta.empty
    # The fixture deliberately retains a real zero-volume bar.
    assert sum(counts["stale_print"] + counts["zero_volume"] for counts in rejections.values()) >= 1


def test_parsing_the_fixture_twice_is_idempotent(tmp_path, monkeypatch) -> None:
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)
    envelope = load_envelope(_FIXTURE)

    for _ in range(2):
        rows, _, _ = parse_envelope(envelope, specs=load_contract_specs())
        storage.write_ts_long(rows, source="ibkr")

    first_pass = len(parse_envelope(envelope, specs=load_contract_specs())[0])
    assert len(storage.read_ts_long()) == first_pass
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `.venv/Scripts/pytest.exe tests/test_ibkr_curve.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipelines.futures.pull_ibkr_curve'`

- [ ] **Step 4: Write the entrypoint**

Create `pipelines/futures/pull_ibkr_curve.py`:

```python
"""Ingest archived IBKR MCP curve captures into the lake.

Deliberately NOT registered in infra/run_scheduled.py. The fetch half is an MCP tool that
only exists inside a Claude session, so this cannot run headless; registering the parser
alone would rewrite identical rows from an unchanged archive. pipelines/manual_physical and
pipelines/ais are unscheduled for the same kind of reason.

Capture ritual: see docs/superpowers/plans/2026-10-10-ibkr-curve.md.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.failures import failure_scope, record_failure
from core.storage import write_ts_long
from pipelines.futures.client import load_contract_specs
from pipelines.futures.ibkr_curve import parse_envelope
from pipelines.futures.series_meta import write_series_meta

ARCHIVE_DIR = Path("data/raw/ibkr")


def load_envelope(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not hold a capture envelope")
    return payload


def main() -> None:
    envelopes = sorted(ARCHIVE_DIR.glob("*.json"))
    if not envelopes:
        print(f"no captures under {ARCHIVE_DIR} -- nothing to ingest", flush=True)
        return

    specs = load_contract_specs()
    with failure_scope("futures.pull_ibkr_curve"):
        for path in envelopes:
            try:
                rows, meta, rejections = parse_envelope(load_envelope(path), specs=specs)
            except Exception as exc:  # noqa: BLE001 -- one bad capture must not cost the rest
                record_failure(path.name, exc)
                continue

            if not meta.empty:
                write_series_meta(meta)
            if not rows.empty:
                write_ts_long(rows, source="ibkr")

            refused = {
                contract: {reason: n for reason, n in counts.items() if n}
                for contract, counts in rejections.items()
                if any(counts.values())
            }
            print(f"{path.name}: wrote {len(rows)} rows across {len(meta)} contracts", flush=True)
            for contract, counts in sorted(refused.items()):
                print(f"  {contract}: refused {counts}", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest.exe tests/test_ibkr_curve.py -v`
Expected: PASS, 22 tests

- [ ] **Step 6: Lint, type-check and commit**

```bash
.venv/Scripts/ruff.exe check .
.venv/Scripts/mypy.exe core pipelines infra
git add tests/fixtures/futures/ibkr_curve_cl_20261010.json pipelines/futures/pull_ibkr_curve.py tests/test_ibkr_curve.py
git commit -m "feat(futures): entrypoint ingesting archived IBKR captures into the lake"
```

---

### Task 6: Make `contract_panel_for` suffix-aware

The one change to existing code. It feeds page 18 and every `derived.*` curve series, so it is isolated in its own task and its own commit.

**Files:**
- Modify: `pipelines/derived/curve.py:30-51`
- Test: `tests/test_derived_curve.py`

**Interfaces:**
- Consumes: `core.storage.read_ts_long`.
- Produces: `contract_panel_for(root, meta, return_provenance=False)` — unchanged two-tuple by default, so `apps/dashboard/pages/18_curve.py` needs no edit.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_derived_curve.py`:

```python
def test_contract_panel_for_reads_close_when_no_settle_exists(tmp_path, monkeypatch) -> None:
    """IBKR supplies .close, not .settle. Without this the whole derived curve chain sees
    nothing for a root that only has IBKR data."""
    from core import storage
    from pipelines.derived.curve import contract_panel_for

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)
    storage.write_ts_long(
        pd.DataFrame(
            {
                "series_id": ["fut.lco.z2026.close", "fut.lco.f2027.close"],
                "source": "ibkr",
                "ts": [pd.Timestamp("2026-10-09")] * 2,
                "value": [104.43, 103.80],
                "unit": "USD/1000 bbl", "geo": "LCO", "freq": "D",
                "revision_date": pd.Timestamp("2026-10-10"),
            }
        ),
        source="ibkr",
    )
    meta = pd.DataFrame(
        {
            "root": ["lco", "lco"],
            "contract": ["z2026", "f2027"],
            "expiry": [pd.Timestamp("2026-10-30"), pd.Timestamp("2026-11-30")],
        }
    )
    panel, expiries = contract_panel_for("lco", meta)
    assert sorted(panel.columns) == ["f2027", "z2026"]
    assert len(expiries) == 2


def test_contract_panel_for_prefers_settle_and_does_not_blend_within_a_contract(
    tmp_path, monkeypatch
) -> None:
    """A settlement and a last trade are different quantities. Mixing them inside one
    column is how a function silently stops measuring what it claims to."""
    from core import storage
    from pipelines.derived.curve import contract_panel_for

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)
    for series_id, value, source in (
        ("fut.cl.z2026.settle", 90.80, "manual"),
        ("fut.cl.z2026.close", 90.75, "ibkr"),
    ):
        storage.write_ts_long(
            pd.DataFrame(
                {
                    "series_id": [series_id], "source": [source],
                    "ts": [pd.Timestamp("2026-10-09")], "value": [value],
                    "unit": "USD/1000 bbl", "geo": "CL", "freq": "D",
                    "revision_date": [pd.Timestamp("2026-10-10")],
                }
            ),
            source=source,
        )
    meta = pd.DataFrame(
        {"root": ["cl"], "contract": ["z2026"], "expiry": [pd.Timestamp("2026-11-20")]}
    )
    panel, _, provenance = contract_panel_for("cl", meta, return_provenance=True)
    assert panel.loc[pd.Timestamp("2026-10-09"), "z2026"] == 90.80
    assert provenance["z2026"] == "settle"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest.exe tests/test_derived_curve.py -v`
Expected: FAIL — the close-only panel is empty, and `return_provenance` is an unexpected keyword argument.

- [ ] **Step 3: Replace `contract_panel_for`**

In `pipelines/derived/curve.py`, replace the function with:

```python
_METRICS_BY_PREFERENCE: Final[tuple[str, ...]] = ("settle", "close")
"""Settle first: an exchange settlement is the better number where one exists. `.close` is
last-trade data, from sources like the IBKR MCP connector -- see
pipelines/futures/CLAUDE.md for the measured difference between the two."""


def contract_panel_for(
    root: str, meta: pd.DataFrame, return_provenance: bool = False
) -> tuple[pd.DataFrame, pd.Series] | tuple[pd.DataFrame, pd.Series, dict[str, str]]:
    """Public (not module-private) so apps/dashboard/pages/18_curve.py can reuse this same
    pivot logic directly, matching pipelines/eia/transforms.py's own "page imports a
    pipeline's transform helper" precedent.

    Reads both `.settle` and `.close` and picks ONE metric per contract -- settle if that
    contract has any settle rows, close otherwise. Per contract, never per row: a settlement
    and a last trade are different quantities, and blending them inside one column would
    leave every spread downstream measuring something nobody chose.
    """
    root_meta = meta[meta["root"] == root]
    empty: tuple[pd.DataFrame, pd.Series] = (
        pd.DataFrame(),
        pd.Series(dtype="datetime64[ns]"),
    )
    if root_meta.empty:
        return (*empty, {}) if return_provenance else empty

    contracts = root_meta["contract"].tolist()
    series_ids = [
        f"fut.{root}.{contract}.{metric}"
        for contract in contracts
        for metric in _METRICS_BY_PREFERENCE
    ]
    long_df = read_ts_long(series_ids=series_ids)
    if long_df.empty:
        return (*empty, {}) if return_provenance else empty

    long_df = long_df.copy()
    parts = long_df["series_id"].str.split(".")
    long_df["contract"] = parts.str[2]
    long_df["metric"] = parts.str[3]

    available = long_df.groupby("contract")["metric"].agg(set)
    chosen = {
        contract: next(m for m in _METRICS_BY_PREFERENCE if m in metrics)
        for contract, metrics in available.items()
    }
    picked = long_df[
        [chosen.get(c) == m for c, m in zip(long_df["contract"], long_df["metric"], strict=True)]
    ]

    contract_panel = picked.pivot_table(index="ts", columns="contract", values="value")
    expiries = root_meta.set_index("contract")["expiry"]
    # Only contracts that actually have rows in the lake -- series_meta can list a contract
    # before any real price data for it has landed.
    expiries = expiries.loc[expiries.index.intersection(contract_panel.columns)]
    if return_provenance:
        return contract_panel, expiries, chosen
    return contract_panel, expiries
```

- [ ] **Step 4: Run the full suite — this function has existing callers**

Run: `.venv/Scripts/pytest.exe -v`
Expected: PASS. Pay particular attention to `tests/test_derived_curve.py`, `tests/test_pages_smoke.py::test_page_loads_without_raising[18_curve.py]` and any `publish_curve` test.

Note: `tests/test_pages_smoke.py::test_page_loads_without_raising[02_gas_storage.py]` was already failing before this plan (`KeyError: 'deviation'` in `pipelines/gie/transforms.py`, a known GIE seasonal-median bug). Confirm it fails identically on `main` before attributing it here.

- [ ] **Step 5: Lint, type-check and commit**

```bash
.venv/Scripts/ruff.exe check .
.venv/Scripts/mypy.exe core pipelines infra
git add pipelines/derived/curve.py tests/test_derived_curve.py
git commit -m "feat(derived): let contract_panel_for read .close as well as .settle"
```

---

### Task 7: Real capture, real pull, cross-checks and the gate

**Files:**
- Create: `data/raw/ibkr/cl-20261010.json`, `data/raw/ibkr/lco-20261010.json` (git-ignored)
- Modify: `pipelines/futures/CLAUDE.md`, `pipelines/futures/barchart_curve.py` (docstring pointer only), `CHANGELOG.md`, `specs/00_INDEX.md`

**Interfaces:**
- Consumes: everything above.
- Produces: real `fut.cl.*.close` and `fut.lco.*.close` rows in the lake, and real `derived.*` curve series for both roots.

- [ ] **Step 1: Capture both roots for real**

In a session with the IBKR connector, read-only calls only. For each root in `cl` (underlying 17340715) and `lco` (underlying 45631501):

1. `search_futures(underlying_contract_id)`.
2. Sort the returned contracts by `contract_month` ascending; drop any whose `last_trading_date` is in the past; keep the first 36.
3. For each kept contract, `get_price_history(contract_id, security_type="FUT", exchange="NYMEX", step="ONE_DAY", period=<Task 0's confirmed maximum>, outside_rth=false)`.
4. Write `data/raw/ibkr/<root>-20261010.json` in the spec's envelope shape, storing responses verbatim and carrying `captured_at`, `exchange`, `delayed_seconds`, `top_status` and `price_source`.

Do not store the ladder's `symbol` field.

- [ ] **Step 2: Ingest**

Run: `.venv/Scripts/python.exe -m pipelines.futures.pull_ibkr_curve`
Expected: exit 0, a row count per capture, and a refusal count per contract. Record both.

- [ ] **Step 3: Confirm the lake, then build the derived curve**

```bash
.venv/Scripts/python.exe -c "from core.storage import read_ts_long; d=read_ts_long(); d=d[d['source']=='ibkr']; print(len(d), d['series_id'].nunique()); print(sorted(d['series_id'].unique())[:5])"
.venv/Scripts/python.exe -m pipelines.derived.curve
```

Expected: no `.oi` series, no `.settle` series under `source="ibkr"`, and `derived.spread.lco.s12` existing for the first time.

- [ ] **Step 4: Cross-check one — IBKR against yfinance front month**

```bash
.venv/Scripts/python.exe -c "
from core.storage import read_ts_long
import pandas as pd
y = read_ts_long(series_ids=['fut.cl.f01.close']).set_index('ts')['value']
d = read_ts_long(); d = d[(d['source']=='ibkr') & d['series_id'].str.endswith('.close')]
front = d[d['series_id']==sorted(d['series_id'].unique())[0]].set_index('ts')['value']
j = pd.concat({'yf': y, 'ibkr': front}, axis=1).dropna()
print(len(j), (j.yf-j.ibkr).abs().max(), ((j.yf-j.ibkr).abs()<=0.01).mean())
"
```

Both are last-trade, so expect close agreement. Record the overlap count, maximum absolute difference and share within a cent. A material divergence is a finding to write down, not to smooth over.

- [ ] **Step 5: Cross-check two — the Brent–WTI December spread**

Compare December `lco` against December `cl` from the lake, and check the difference against an independent public quote for the same two contracts and date. The capture on 2026-10-10 implied **$13.63** (BZ Dec 104.43 against CL Dec 90.80), which is wide against the usual few dollars. Record the verdict either way.

Label it correctly: `BZ` is **NYMEX Brent Last Day**, not ICE Brent — see `pipelines/cftc/CLAUDE.md`'s corrected section and the volumes (26,251 lots against WTI's 202,301).

- [ ] **Step 6: Record what happened**

Append a section to `pipelines/futures/CLAUDE.md` covering: the connector as a non-Gateway path and why `ibkr_preflight.py`'s port check says nothing about it; the resolved underlying contract ids; `FROZEN_DELAYED` with a 600-second delay and a `Last` price source, hence `.close`; the liquidity gate and the real refusal counts; and both cross-check results.

Add one line to `barchart_curve.py`'s module docstring pointing at this source as the forward path. Do not delete the module or its rows.

Add a `CHANGELOG.md` entry and update Spec 18's status line in `specs/00_INDEX.md` to record that a real multi-contract curve now exists for `cl` and `lco`, and that ranks beyond 4 remain unwritten by design.

- [ ] **Step 7: The full gate**

```bash
.venv/Scripts/pytest.exe
.venv/Scripts/ruff.exe check .
.venv/Scripts/mypy.exe core pipelines infra
```

Then, per the owner's standing rule, run `/code-review high` and `/security-review` on the branch diff before calling it done.

- [ ] **Step 8: Commit**

```bash
git add pipelines/futures/CLAUDE.md pipelines/futures/barchart_curve.py CHANGELOG.md specs/00_INDEX.md
git commit -m "docs(futures): record the real IBKR curve capture and its cross-checks"
```

---

## Self-review

**Spec coverage.** Capture ritual → Task 7 Step 1. Envelope → Tasks 4, 5, 7. `.close` not `.settle` → Tasks 3, 6. Contract codes and the rank guard → Tasks 1, 3. Unit convention → Task 3. `revision_date` → Task 4. No `.oi` → Task 3. Liquidity gate → Task 2. `contract_panel_for` → Task 6. `core.failures` → Task 5. Unscheduled → Task 5 docstring. Fixture and no cassettes → Task 5. Float64 regression → Task 3. Both cross-checks → Task 7 Steps 4–5. Task 0's open question → Task 0. Barchart retirement and yfinance untouched → Task 7 Step 6.

**Gap found and closed:** the spec's Definition of Done requires rejection counts reported per contract; that is Task 5's entrypoint output, asserted structurally by Task 2's `test_every_rejection_reason_is_reported_even_when_zero`.

**One deliberate unknown left in the plan:** Task 3 Step 3 says to confirm how `core/schemas.py` exposes an empty `ts_long` frame rather than assuming a `TS_LONG_COLUMNS` constant exists. That is a lookup an implementer must perform, not a placeholder — guessing it is the failure mode this project's notes repeatedly warn against.

**Type consistency.** `contract_code_from_month` returns `str` throughout. `liquid_bars` returns `tuple[pd.DataFrame, dict[str, int]]` in Tasks 2, 4. `parse_envelope` returns the same three-tuple in Tasks 4, 5. `ContractMeta` fields match `client.py`'s real dataclass. `contract_panel_for`'s default two-tuple return is preserved for `18_curve.py`.
