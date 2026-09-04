from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from core.fundamentals import (
    cot_percentiles,
    days_of_cover,
    inventory_deviation,
    spare_cap_regime,
    spare_capacity,
)


def _synthetic_stocks_df() -> pd.DataFrame:
    """Years 2022-2026 hover around 400 (a fixed daily value per year, mildly
    year-to-year varying); 2020 is a wild outlier (1000) that inventory_deviation must
    never let leak into mean/dev/dev_z once excluded."""
    yearly_base = {2020: 1000.0, 2022: 398.0, 2023: 402.0, 2024: 400.0, 2025: 401.0, 2026: 405.0}
    frames = []
    for year, base in yearly_base.items():
        dates = pd.date_range(f"{year}-01-01", f"{year}-06-30", freq="D")
        frames.append(pd.DataFrame({"ts": dates, "value": base}))
    return pd.concat(frames, ignore_index=True)


def test_inventory_deviation_excludes_2020_from_mean_and_dev() -> None:
    df = _synthetic_stocks_df()
    result = inventory_deviation(df, years=5, exclude=(2020,))

    # Non-2020 years hover around 398-405; if 2020's 1000 leaked in, mean would be far
    # higher (roughly (1000+398+402+400+401)/5 = 520 vs the real ~401.2 excluding 2020).
    some_doy = result.index[100]
    assert result.loc[some_doy, "mean"] == pytest.approx(401.2, abs=1.0)
    assert result.loc[some_doy, "max"] < 1000.0


def test_inventory_deviation_dev_z_is_nan_when_std_is_zero() -> None:
    # Every included year has the exact same constant value -> std=0 -> dev_z must be NaN,
    # never a divide-by-zero crash or a fabricated number.
    frames = []
    for year in (2023, 2024, 2025, 2026):
        dates = pd.date_range(f"{year}-01-01", f"{year}-03-31", freq="D")
        frames.append(pd.DataFrame({"ts": dates, "value": 100.0}))
    df = pd.concat(frames, ignore_index=True)

    result = inventory_deviation(df, years=4, exclude=(2020,))
    assert result["dev_z"].isna().all()


def test_days_of_cover_spec_worked_example() -> None:
    result = days_of_cover(pd.Series([420000.0]), pd.Series([16000.0]))
    assert result.iloc[0] == pytest.approx(26.25)


def test_spare_capacity_never_silently_averages() -> None:
    idx = pd.date_range("2026-01-01", periods=3, freq="MS")
    eia = pd.Series([3.0, 3.5, 4.0], index=idx)
    iea = pd.Series([2.0, 2.5, 3.0], index=idx)

    result = spare_capacity(eia, iea)
    assert list(result["eia"]) == [3.0, 3.5, 4.0]
    assert list(result["iea"]) == [2.0, 2.5, 3.0]
    assert list(result["avg"]) == pytest.approx([2.5, 3.0, 3.5])
    assert list(result["disagreement"]) == pytest.approx([1.0, 1.0, 1.0])


@pytest.mark.parametrize(
    "spare,expected",
    [(1.5, "tight"), (3.0, "balanced"), (4.5, "ample")],
)
def test_spare_cap_regime_worked_examples(spare: float, expected: str) -> None:
    result = spare_cap_regime(pd.Series([spare]))
    assert result.iloc[0] == expected


def test_cot_percentiles_pct_rank_always_in_unit_interval() -> None:
    dates = pd.date_range("2020-01-07", periods=250, freq="W")
    rng = np.random.default_rng(3)
    long = pd.Series(rng.uniform(50_000, 150_000, size=len(dates)), index=dates)
    short = pd.Series(rng.uniform(50_000, 150_000, size=len(dates)), index=dates)
    oi = pd.Series(rng.uniform(200_000, 400_000, size=len(dates)), index=dates)

    result = cot_percentiles(long, short, oi, window=52)
    valid = result["pct_rank_3y"].dropna()
    assert not valid.empty
    assert (valid >= 0).all()
    assert (valid <= 1).all()


def test_cot_percentiles_net_matches_long_minus_short() -> None:
    dates = pd.date_range("2026-01-06", periods=5, freq="W")
    long = pd.Series([100.0, 110.0, 120.0, 130.0, 140.0], index=dates)
    short = pd.Series([40.0, 45.0, 50.0, 55.0, 60.0], index=dates)
    oi = pd.Series([500.0, 510.0, 520.0, 530.0, 540.0], index=dates)

    result = cot_percentiles(long, short, oi, window=3)
    assert list(result["net"]) == pytest.approx([60.0, 65.0, 70.0, 75.0, 80.0])
