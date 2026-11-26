"""pipelines/derived/fundamentals.py: the inventory z-score as it reaches the lake (I-17)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from core.storage import read_ts_long, write_ts_long
from pipelines.derived import fundamentals


@pytest.fixture(autouse=True)
def _isolated_lake(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def _seed_stocks() -> None:
    # Weekly (Friday) reports to 30 June. Each year's reports hold one value, so the band
    # years 2022 to 2025 are 398, 402, 400 and 401 on every day and 2026 is 405.
    frames = []
    for year, level in {2022: 398.0, 2023: 402.0, 2024: 400.0, 2025: 401.0, 2026: 405.0}.items():
        ts = pd.date_range(f"{year}-01-01", f"{year}-06-30", freq="W-FRI")
        frames.append(
            pd.DataFrame(
                {
                    "series_id": fundamentals.US_CRUDE_STOCKS_SERIES_ID,
                    "source": "eia",
                    "ts": ts,
                    "value": level,
                    "unit": "mb",
                    "geo": "US",
                    "freq": "W",
                    "revision_date": pd.Timestamp("2026-07-01"),
                }
            )
        )
    write_ts_long(pd.concat(frames, ignore_index=True), source="eia")


def test_the_published_z_score_is_measured_against_the_prior_years_only() -> None:
    _seed_stocks()

    written = fundamentals._pull_inventory_deviation(pd.Timestamp("2026-07-01"))

    rows = read_ts_long(series_ids=["derived.inv.dev_z.uscrude"]).sort_values("ts")
    assert written == len(rows) > 0
    assert set(rows["unit"]) == {"z-score"}
    assert set(rows["source"]) == {"derived"}
    assert rows["ts"].dt.year.eq(2026).all()
    # Hand-worked in tests/test_core_fundamentals.py: 4.75 / sqrt(8.75 / 3) = 2.781.
    assert rows["value"].iloc[-1] == pytest.approx(2.781, abs=1e-3)
