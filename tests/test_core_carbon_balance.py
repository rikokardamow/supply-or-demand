"""core/carbon_balance.py. All figures synthetic."""

from __future__ import annotations

import math

import pandas as pd
import pytest
from core import carbon_balance as cb


def _totals(rows: list[tuple[str, str, str, int, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["metric", "sector", "registry", "year", "value"])


def _year(y: int) -> pd.Timestamp:
    return pd.Timestamp(f"{y}-01-01")


def test_great_britain_and_pre_2013_years_are_out_of_scope() -> None:
    totals = _totals(
        [
            ("verified_emissions", "combustion", "de", 2024, 100.0),
            ("verified_emissions", "combustion", "gb", 2024, 50.0),
            ("verified_emissions", "combustion", "de", 2012, 999.0),
        ]
    )

    ets = cb.annual_ets(totals)

    assert list(ets.index) == [_year(2024)]
    assert ets.loc[_year(2024), "emissions_combustion"] == 100.0


def test_only_the_latest_year_can_be_incomplete() -> None:
    ets = pd.DataFrame(
        {"reporting_combustion": [100.0, 60.0, 59.0, 30.0],
         "reporting_industry": [0.0, 0.0, 0.0, 0.0],
         "reporting_aviation": [0.0, 0.0, 0.0, 0.0]},
        index=[_year(y) for y in (2019, 2020, 2021, 2022)],
    )  # fmt: skip

    complete = cb.complete_years(ets)

    assert list(complete) == [True, True, True, False]  # the 2020 drop is real, not lag


def test_shipping_counts_at_its_phase_in_and_absent_shipping_is_zero() -> None:
    ets = pd.DataFrame(
        {"emissions_combustion": [10.0, 10.0], "emissions_industry": [5.0, 5.0],
         "emissions_aviation": [1.0, 1.0], "emissions_maritime": [float("nan"), 100.0]},
        index=[_year(2023), _year(2024)],
    )  # fmt: skip
    phase = pd.Series({2024: 0.4})

    demand = cb.surrender_demand(ets, phase)

    assert demand[_year(2023)] == 16.0
    assert demand[_year(2024)] == 56.0


def test_shipping_without_a_phase_in_row_is_nan_not_zero() -> None:
    ets = pd.DataFrame(
        {"emissions_combustion": [10.0], "emissions_industry": [5.0], "emissions_aviation": [1.0],
         "emissions_maritime": [100.0]},
        index=[_year(2030)],
    )  # fmt: skip

    assert math.isnan(cb.surrender_demand(ets, pd.Series({2024: 0.4}))[_year(2030)])


def test_auctions_sum_by_year_and_prices_weight_by_volume() -> None:
    auctions = pd.DataFrame(
        {"ts": pd.to_datetime(["2024-01-05", "2024-01-08", "2024-02-01"]),
         "price": [60.0, 80.0, 70.0], "volume": [1.0, 3.0, 4.0]}
    )  # fmt: skip

    assert cb.auctioned_by_year(auctions)[_year(2024)] == 8.0
    monthly, weighted = cb.price_summary(auctions)
    assert monthly[pd.Timestamp("2024-01-01")] == 70.0
    assert weighted[_year(2024)] == pytest.approx((60 + 240 + 280) / 8)


def test_balance_carries_a_cumulative_surplus_forward() -> None:
    ets = pd.DataFrame({"free_allocation": [50.0, 40.0]}, index=[_year(2024), _year(2025)])
    auctioned = pd.Series([60.0, 60.0], index=ets.index)
    demand = pd.Series([100.0, 120.0], index=ets.index)

    out = cb.balance(ets, auctioned, demand, carried=-30.0)

    assert list(out["surplus"]) == [10.0, -20.0]
    assert list(out["cumulative_surplus"]) == [-20.0, -40.0]


def test_msr_rule_reproduces_every_published_intake() -> None:
    from pathlib import Path

    published = pd.read_csv(
        Path(__file__).parent.parent / "pipelines" / "carbon" / "tnac.csv"
    ).dropna(subset=["msr_intake"])

    assert len(published) == 6
    for row in published.itertuples():
        assert cb.msr_intake(row.tnac_year, row.tnac) == pytest.approx(row.msr_intake, abs=1.0)


def test_msr_rule_bands_before_and_after_the_2023_amendment() -> None:
    # 1,000 Mt sits in the 833-1,096 Mt buffer: 24% before the amendment, the excess after.
    assert cb.msr_intake(2022, 1_000_000_000) == pytest.approx(240_000_000)
    assert cb.msr_intake(2023, 1_000_000_000) == pytest.approx(167_000_000)
    assert cb.msr_intake(2023, 1_200_000_000) == pytest.approx(288_000_000)
    assert cb.msr_intake(2023, 800_000_000) == 0.0
    assert cb.msr_intake(2023, 350_000_000) == -100_000_000
    with pytest.raises(ValueError):
        cb.msr_intake(2016, 1_700_000_000)
