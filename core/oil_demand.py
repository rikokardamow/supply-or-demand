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
    quarter_start = months.to_period("Q").to_timestamp(how="start")
    mean = total.groupby(quarter_start).mean()
    complete = total.notna().groupby(quarter_start).sum() == 3
    out = mean.where(complete)
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
