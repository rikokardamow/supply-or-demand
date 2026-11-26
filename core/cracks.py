"""Refining economics: crack-spread boards (Spec 20 Session A).

Pure maths only -- never touches DuckDB (root NOTES.md rule 2). Callers
(`pipelines/derived/cracks.py`, `apps/dashboard/pages/20_cracks.py`) read the lake, call
these functions, and write or render the results.

**Deviation from the spec's own signature, recorded deliberately.** Spec 20 writes
`crack_board(as_of)`, which would have to read the lake itself. That contradicts the
"pure analytics modules never touch DuckDB" rule in `specs/00_TRADING_CONVENTIONS.md`,
so the board takes its already-loaded crack panel as an argument instead, matching
`core/fundamentals.py::inventory_deviation`'s own precedent.

**Legs are spot, not futures, today.** Spec 18 has never ingested a real settlement, so
the lake holds no `fut.*` rows at all -- the crack legs come from Spec 10's FRED spot
series (`fred.dcoilwtico`, `fred.dgasnyh`, `fred.dhoilnyh`, ...). The board's m1/m2/m6
tenor columns are therefore NaN ("no data isn't zero", the sanctions/Adanos precedent)
until a futures panel is passed in.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.seasonal import reference_doy_clamped, seasonal_stats

GAL_PER_BBL = 42.0
"""US barrel = 42 US gallons. RBOB and heating oil settle in $/gal."""

GASOIL_BBL_PER_TONNE = 7.45
"""ICE gasoil settles in $/tonne; the standard gasoil conversion is 7.45 bbl/tonne."""

RBOB_SPLICE_DATE = pd.Timestamp("2006-01-01")
"""NYMEX unleaded gasoline (HU) was replaced by RBOB from the 2006 contract year. A
gasoline crack spanning this date is spliced across two different contracts."""

BOARD_COLUMNS = ["crack", "spot", "m1", "m2", "m6", "seasonal_5y_mean", "pct_rank_5y"]

_TENORS = ("m1", "m2", "m6")
_SEASONAL_YEARS = 5

Leg = float | pd.Series


# --- unit conversions -------------------------------------------------------------


def gal_to_bbl(price_per_gal: Leg) -> Leg:
    """$/gal -> $/bbl."""
    return price_per_gal * GAL_PER_BBL


def tonne_to_bbl_gasoil(price_per_tonne: Leg) -> Leg:
    """ICE gasoil $/tonne -> $/bbl."""
    return price_per_tonne / GASOIL_BBL_PER_TONNE


# --- crack formulae ---------------------------------------------------------------


def _align(*legs: Leg) -> tuple[Leg, ...]:
    """Intersect the index of every Series leg, leaving scalars untouched.

    The crude and product legs genuinely have ragged right-hand ends in the real lake
    (FRED publishes WTI/Brent a few days behind the product spots), so a crack must be
    computed only on dates where every leg actually printed.
    """
    series = [leg for leg in legs if isinstance(leg, pd.Series)]
    if not series:
        return legs

    index = series[0].index
    for other in series[1:]:
        index = index.intersection(other.index)
    return tuple(leg.reindex(index) if isinstance(leg, pd.Series) else leg for leg in legs)


def _finalise(result: Leg) -> Leg:
    """Drop dates where any leg was missing within its own index (exchange holidays
    print as NaN on FRED rather than being absent)."""
    if isinstance(result, pd.Series):
        return result.dropna()
    return result


def crack_321(cl: Leg, rb: Leg, ho: Leg) -> Leg:
    """3:2:1 crack in $/bbl: two barrels of gasoline and one of distillate per three of
    crude. `rb`/`ho` in $/gal, `cl` in $/bbl."""
    cl, rb, ho = _align(cl, rb, ho)
    return _finalise((2 * gal_to_bbl(rb) + gal_to_bbl(ho) - 3 * cl) / 3)


def crack_211(cl: Leg, rb: Leg, ho: Leg) -> Leg:
    """2:1:1 crack in $/bbl -- gasoline and distillate weighted equally."""
    cl, rb, ho = _align(cl, rb, ho)
    return _finalise((gal_to_bbl(rb) + gal_to_bbl(ho) - 2 * cl) / 2)


def crack_rbob(cl: Leg, rb: Leg) -> Leg:
    """Single-product gasoline crack in $/bbl."""
    cl, rb = _align(cl, rb)
    return _finalise(gal_to_bbl(rb) - cl)


def crack_ho(cl: Leg, ho: Leg) -> Leg:
    """Single-product heating-oil/distillate crack in $/bbl."""
    cl, ho = _align(cl, ho)
    return _finalise(gal_to_bbl(ho) - cl)


def crack_gasoil_nwe(lco: Leg, g: Leg) -> Leg:
    """North-west European gasoil crack in $/bbl: ICE gasoil ($/tonne) less Brent."""
    lco, g = _align(lco, g)
    return _finalise(tonne_to_bbl_gasoil(g) - lco)


def crack_sg_go(dubai: Leg, sg_go: Leg) -> Leg:
    """Singapore gasoil crack in $/bbl. Both legs arrive from the manual physical drop
    already in $/bbl -- no unit conversion here, unlike every other crack above."""
    dubai, sg_go = _align(dubai, sg_go)
    return _finalise(sg_go - dubai)


def rbob_splice_flag(ts: pd.DatetimeIndex | pd.Series) -> pd.Series:
    """True for observations that predate the unleaded -> RBOB contract change."""
    index = pd.DatetimeIndex(ts)
    return pd.Series(index < RBOB_SPLICE_DATE, index=index)


# --- board ------------------------------------------------------------------------


def _reference_doy(ts: pd.Timestamp) -> int:
    """Day-of-year on core.seasonal's own non-leap reference year, so the board looks up
    the same row seasonal_stats indexed by (29 February is taken as the 28th)."""
    return reference_doy_clamped(ts)


def _seasonal_mean(series: pd.Series, as_of: pd.Timestamp) -> float:
    """Mean of the crack at `as_of`'s day-of-year across the trailing five calendar
    years, 2020 excluded (root NOTES.md rule 4 -- via core.seasonal, not reimplemented)."""
    if series.empty:
        return float("nan")

    df = pd.DataFrame({"ts": series.index, "value": series.to_numpy(dtype=float)})
    years = range(as_of.year - (_SEASONAL_YEARS - 1), as_of.year + 1)
    stats = seasonal_stats(df, "value", years=years)

    year_columns = [c for c in stats.columns if c not in ("lo", "hi", "median")]
    doy = _reference_doy(as_of)
    if not year_columns or doy not in stats.index:
        return float("nan")
    # Mean across the included years at that day-of-year, skipping years with no print
    # there -- dropped explicitly rather than relying on a propagating numpy mean.
    row = pd.Series(stats.loc[doy, year_columns], dtype="float64").to_numpy()
    present = row[~np.isnan(row)]
    if present.size == 0:
        return float("nan")
    return float(present.mean())


def _pct_rank(series: pd.Series, as_of: pd.Timestamp, spot: float) -> float:
    """Percentile rank of the latest print within the trailing five years, 0-100."""
    if np.isnan(spot):
        return float("nan")
    window = series.loc[series.index > as_of - pd.DateOffset(years=_SEASONAL_YEARS)]
    if window.empty:
        return float("nan")
    hits = int((window <= spot).to_numpy().sum())
    return hits / len(window) * 100.0


def _tenor(tenors: pd.DataFrame | None, name: str, column: str) -> float:
    if tenors is None or name not in tenors.index or column not in tenors.columns:
        return float("nan")
    return float(tenors.loc[[name], column].to_numpy(dtype="float64")[0])


def crack_board(
    cracks: pd.DataFrame,
    tenors: pd.DataFrame | None = None,
    as_of: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """One row per crack: latest spot, forward tenors, seasonal mean and 5y percentile.

    `cracks` is a wide panel indexed by timestamp, one $/bbl column per crack.
    `tenors` is optional, indexed by crack name with m1/m2/m6 columns -- absent (the
    situation today, with no futures in the lake) those columns read NaN, never 0.
    Nothing after `as_of` is ever consulted, so a board struck mid-sample cannot see
    the future.
    """
    frame = cracks.sort_index()
    if as_of is None:
        as_of = pd.Timestamp(frame.index.max())
    as_of = pd.Timestamp(as_of)
    frame = frame.loc[frame.index <= as_of]

    rows = []
    for name in cracks.columns:
        series = frame[name].dropna()
        spot = float(series.iloc[-1]) if not series.empty else float("nan")
        row = {
            "crack": name,
            "spot": spot,
            "seasonal_5y_mean": _seasonal_mean(series, as_of),
            "pct_rank_5y": _pct_rank(series, as_of, spot),
        }
        for tenor in _TENORS:
            row[tenor] = _tenor(tenors, name, tenor)
        rows.append(row)

    return pd.DataFrame(rows, columns=BOARD_COLUMNS)


def crack_seasonal_heatmap(crack: pd.Series) -> pd.DataFrame:
    """Monthly mean of one crack, years down and months across.

    Unlike the seasonal *statistics*, this is a descriptive picture of what actually
    happened, so 2020 stays on it -- visible as the outlier it was rather than silently
    dropped.
    """
    series = crack.dropna()
    if series.empty:
        return pd.DataFrame()

    index = pd.DatetimeIndex(series.index)
    grouped = series.groupby([index.year, index.month]).mean().unstack()
    grouped.index.name = "year"
    grouped.columns.name = "month"
    return grouped
