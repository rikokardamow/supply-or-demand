from __future__ import annotations

import pandas as pd
import pytest
from core.macro import align_freq, deflate, index_to, to_currency, year_over_year, zscore


def test_deflate_toy_series_hand_checked() -> None:
    # 2018=100 base -- CPI rises 5% then a further ~4.76% (110 -> back to a round
    # number is awkward by design, forcing a real division rather than a value that
    # happens to simplify).
    nominal = pd.Series(
        [100.0, 110.0, 120.0],
        index=pd.to_datetime(["2018-01-01", "2019-01-01", "2020-01-01"]),
    )
    cpi = pd.Series(
        [100.0, 105.0, 110.0],
        index=pd.to_datetime(["2018-01-01", "2019-01-01", "2020-01-01"]),
    )

    real = deflate(nominal, cpi, base_period="2018-01-01")

    assert real.iloc[0] == pytest.approx(100.0)
    assert real.iloc[1] == pytest.approx(110.0 * 100.0 / 105.0)  # 104.7619...
    assert real.iloc[2] == pytest.approx(120.0 * 100.0 / 110.0)  # 109.0909...


def test_deflate_forward_fills_cpi_onto_series_dates() -> None:
    # series has a date CPI doesn't (a daily price against a monthly CPI print).
    nominal = pd.Series([100.0], index=pd.to_datetime(["2019-06-15"]))
    cpi = pd.Series(
        [100.0, 106.0], index=pd.to_datetime(["2018-01-01", "2019-06-01"])
    )

    real = deflate(nominal, cpi, base_period="2018-01-01")

    assert real.iloc[0] == pytest.approx(100.0 * 100.0 / 106.0)


def test_to_currency_forward_fills_fx_onto_series_dates() -> None:
    usd = pd.Series([100.0, 200.0], index=pd.to_datetime(["2026-01-01", "2026-01-05"]))
    fx = pd.Series(
        [0.90, 0.91, 0.92],
        index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
    )

    eur = to_currency(usd, fx, target="EUR")

    assert eur.iloc[0] == pytest.approx(100.0 * 0.90)
    # 2026-01-05 has no FX quote of its own -- ffilled from 2026-01-03's 0.92.
    assert eur.iloc[1] == pytest.approx(200.0 * 0.92)


def test_align_freq_resamples_the_finer_series_to_the_coarser_ones_frequency() -> None:
    # Daily coverage spans both months the monthly series has a point for -- a daily
    # series that *doesn't* fully cover the coarser series' own range is a different,
    # real scenario (the aligned intersection correctly drops the uncovered month),
    # not what this test is checking.
    daily = pd.Series(
        [10.0] * 31 + [20.0] * 28,  # January all 10s, February all 20s
        index=pd.date_range("2026-01-01", periods=59, freq="D"),
    )
    monthly = pd.Series([100.0, 110.0], index=pd.to_datetime(["2026-01-01", "2026-02-01"]))

    daily_aligned, monthly_aligned = align_freq(daily, monthly, how="mean")

    assert list(monthly_aligned.index) == list(monthly.index)
    assert daily_aligned.loc["2026-01-01"] == pytest.approx(10.0)
    assert daily_aligned.loc["2026-02-01"] == pytest.approx(20.0)


def test_year_over_year_hand_checked() -> None:
    series = pd.Series(
        [float(v) for v in range(100, 113)],
        index=pd.date_range("2025-01-01", periods=13, freq="MS"),
    )

    yoy = year_over_year(series, periods=12)

    assert yoy.iloc[:12].isna().all()
    assert yoy.iloc[12] == pytest.approx((112.0 / 100.0 - 1) * 100)  # 12.0


def test_zscore_hand_checked() -> None:
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])

    z = zscore(series)

    # mean=3, sample std (ddof=1) = sqrt(2.5) = 1.5811388...
    assert z.iloc[0] == pytest.approx((1.0 - 3.0) / (2.5**0.5))
    assert z.iloc[2] == pytest.approx(0.0)


def test_index_to_hand_checked() -> None:
    series = pd.Series(
        [80.0, 100.0, 120.0],
        index=pd.to_datetime(["2018-01-01", "2019-01-01", "2020-01-01"]),
    )

    indexed = index_to(series, base_period="2019-01-01")

    assert indexed.iloc[0] == pytest.approx(80.0)  # 80/100*100
    assert indexed.iloc[1] == pytest.approx(100.0)  # base period itself is exactly 100
    assert indexed.iloc[2] == pytest.approx(120.0)  # 120/100*100
