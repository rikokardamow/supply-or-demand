"""Renewable Fuel Standard mandate arithmetic: pure functions, no I/O.

The RFS obligation is a percentage of the non-renewable gasoline plus distillate a country
supplies. This module turns that denominator and EPA's percentage standard into an implied
mandate in billions of RINs (one RIN is about one ethanol-equivalent gallon). It reads no
file, lake or network; callers pass numbers in.

Units
-----
* Demand arrives as **million barrels per day** (the unit of the EIA STEO series).
* The single conversion ``1 barrel = 42 US gallons`` is applied once, in
  :func:`rfs_denominator_gallons`, via :data:`GALLONS_PER_BARREL`. Everything downstream
  is in gallons.
* The percentage standard is a **fraction of 1** (the 2026 total standard is ``0.155``, not
  ``15.5``), the form ``pipelines.epa.reference.load_percentage_standards`` returns. A value
  above 1 is refused rather than rescaled.

Missing data
------------
No data is not zero. A ``None`` or NaN input yields NaN, never 0. A degenerate input
(negative volume, standard outside [0, 1], non-positive period) raises ``ValueError``.

This arithmetic needs no EPA volume, so the ``requirement`` versus ``applicable`` basis of
``load_volume_targets`` does not arise here; a caller that compares the implied mandate with
a published volume chooses that basis itself.
"""

from __future__ import annotations

import math
from typing import Final

GALLONS_PER_BARREL: Final[int] = 42
_BARRELS_PER_MILLION: Final[float] = 1e6
_RINS_PER_BILLION: Final[float] = 1e9


def _is_missing(value: float | None) -> bool:
    return value is None or math.isnan(value)


def rfs_denominator_gallons(
    petroleum_gasoline_mbd: float | None,
    petroleum_distillate_mbd: float | None,
    days_in_period: int,
) -> float:
    """Non-renewable gasoline plus distillate for one period, in US gallons.

    ``petroleum_*_mbd`` are million barrels per day of *non-renewable* product supplied
    (STEO ``MGTCPUSX_P`` and ``DFTCPUS_P``). The headline totals ``MGTCPUSX`` and
    ``DFTCPUS`` include blended renewables and are the wrong inputs; supplying them is the
    caller's responsibility and cannot be detected here. ``days_in_period`` is the calendar
    length of the period (for example 31 for January), never a 30-day constant.

    Returns ``(gasoline + distillate) * 1e6 * days * 42``; NaN if either volume is
    ``None`` or NaN. Raises ``ValueError`` for a negative volume or ``days_in_period < 1``.
    """
    if days_in_period < 1:
        raise ValueError(f"days_in_period must be at least 1, got {days_in_period}")
    for name, mbd in (
        ("petroleum_gasoline_mbd", petroleum_gasoline_mbd),
        ("petroleum_distillate_mbd", petroleum_distillate_mbd),
    ):
        if mbd is not None and not math.isnan(mbd) and mbd < 0:
            raise ValueError(f"{name} must not be negative, got {mbd}")
    if _is_missing(petroleum_gasoline_mbd) or _is_missing(petroleum_distillate_mbd):
        return math.nan
    assert petroleum_gasoline_mbd is not None and petroleum_distillate_mbd is not None
    barrels = (
        (petroleum_gasoline_mbd + petroleum_distillate_mbd) * _BARRELS_PER_MILLION * days_in_period
    )
    return barrels * GALLONS_PER_BARREL


def implied_mandate_billion_rins(denominator_gallons: float, pct: float) -> float:
    """Implied national mandate in billions of RINs: gallons times the percentage standard.

    ``denominator_gallons`` is US gallons (from :func:`rfs_denominator_gallons`). ``pct`` is a
    FRACTION of 1, as ``load_percentage_standards`` returns it (0.155, not 15.5); a value
    outside [0, 1] raises ``ValueError``. NaN in either argument yields NaN; a negative
    denominator raises.
    """
    if not math.isnan(pct) and not 0.0 <= pct <= 1.0:
        raise ValueError(f"pct must be a fraction in [0, 1] (0.155, not 15.5), got {pct}")
    if not math.isnan(denominator_gallons) and denominator_gallons < 0:
        raise ValueError(f"denominator_gallons must not be negative, got {denominator_gallons}")
    if math.isnan(denominator_gallons) or math.isnan(pct):
        return math.nan
    return denominator_gallons * pct / _RINS_PER_BILLION
