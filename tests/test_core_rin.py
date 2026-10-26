"""Pure-arithmetic tests for core.rin. Every figure is synthetic and hand-checkable; the
licensed workbook's own figures are deliberately absent (the port is compared against them
separately and recorded as prose, per pipelines/derived/NOTES.md)."""

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
    # (6.0 + 4.0) mb/d = 10e6 bbl/d; x 100 days = 1.0e9 bbl; x 42 gal/bbl = 42.0e9 gal.
    assert rfs_denominator_gallons(6.0, 4.0, 100) == pytest.approx(42.0e9)


def test_one_barrel_per_day_for_one_day_is_exactly_forty_two_gallons() -> None:
    # 1e-6 mb/d = 1 bbl/d; x 1 day = 1 bbl; x 42 = 42 gal. Fails if the 42 is dropped
    # (barrels returned as gallons) or applied twice.
    assert rfs_denominator_gallons(1e-6, 0.0, 1) == pytest.approx(42.0)


def test_the_mandate_is_the_denominator_times_the_standard() -> None:
    # 42.0e9 gal x 0.10 = 4.2e9 RINs = 4.2 billion.
    assert implied_mandate_billion_rins(42.0e9, 0.10) == pytest.approx(4.2)


def test_chain_pins_unit_conversion_denominator_pair_and_fraction_form() -> None:
    """Non-renewable gasoline 8.0 + distillate 4.0 mb/d, 31 days, standard 0.155.

    12e6 bbl/d x 31 d = 372e6 bbl; x 42 = 15.624e9 gal; x 0.155 = 2.42172e9 RINs.
    Each plausible slip lands somewhere else:
      barrels not gallons          -> 372e6 x 0.155 / 1e9      = 0.05766
      headline pair (+10% gas, +5% dist: 8.8 + 4.2 = 13.0)    = 13e6 x 31 x 42 x 0.155 / 1e9
                                                              = 2.62353
      per cent (15.5) as the standard                          -> refused (see next test)
    """
    denominator = rfs_denominator_gallons(8.0, 4.0, 31)
    assert denominator == pytest.approx(15.624e9)
    mandate = implied_mandate_billion_rins(denominator, 0.155)
    assert mandate == pytest.approx(2.42172)
    assert mandate != pytest.approx(0.05766, rel=1e-3)
    assert mandate != pytest.approx(2.62353, rel=1e-3)


def test_the_published_2026_total_standard_is_a_fraction_that_the_function_accepts() -> None:
    from pipelines.epa.reference import load_percentage_standards

    std = load_percentage_standards()
    pct = float(std[(std["year"] == 2026) & (std["category"] == "total")]["pct"].iloc[0])
    assert pct == pytest.approx(0.155)
    # 1.0e9 gal x 0.155 = 0.155 billion RINs.
    assert implied_mandate_billion_rins(1.0e9, pct) == pytest.approx(0.155)


def test_a_per_cent_standard_is_refused_not_silently_scaled() -> None:
    with pytest.raises(ValueError, match="pct"):
        implied_mandate_billion_rins(15.624e9, 15.5)


def test_a_standard_outside_zero_to_one_is_refused() -> None:
    with pytest.raises(ValueError, match="pct"):
        implied_mandate_billion_rins(42.0e9, 1.4)
    with pytest.raises(ValueError, match="pct"):
        implied_mandate_billion_rins(42.0e9, -0.01)


def test_the_standard_bounds_zero_and_one_are_accepted() -> None:
    assert implied_mandate_billion_rins(42.0e9, 0.0) == 0.0
    assert implied_mandate_billion_rins(42.0e9, 1.0) == pytest.approx(42.0)


def test_an_unknown_volume_yields_nan_not_zero() -> None:
    """A missing month is not a month of zero demand."""
    assert math.isnan(rfs_denominator_gallons(float("nan"), 4.0, 100))
    assert math.isnan(rfs_denominator_gallons(6.0, None, 100))
    assert math.isnan(rfs_denominator_gallons(None, None, 100))


def test_an_unknown_denominator_or_standard_yields_nan_not_zero() -> None:
    assert math.isnan(implied_mandate_billion_rins(float("nan"), 0.1))
    assert math.isnan(implied_mandate_billion_rins(42.0e9, float("nan")))


def test_a_negative_volume_is_refused() -> None:
    with pytest.raises(ValueError, match="negative"):
        rfs_denominator_gallons(-6.0, 4.0, 100)
    with pytest.raises(ValueError, match="negative"):
        rfs_denominator_gallons(6.0, -4.0, 100)
    with pytest.raises(ValueError, match="negative"):
        implied_mandate_billion_rins(-1.0, 0.1)


def test_a_non_positive_period_is_refused() -> None:
    with pytest.raises(ValueError, match="days_in_period"):
        rfs_denominator_gallons(6.0, 4.0, 0)
    with pytest.raises(ValueError, match="days_in_period"):
        rfs_denominator_gallons(6.0, 4.0, -31)
