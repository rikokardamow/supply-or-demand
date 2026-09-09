"""The WPSR at-a-glance table: one row per headline report line (Spec 32 §2).

`serving.wpsr_lines` is what the UI's Balances screen reads through `wpsr_latest_v` --
the weekly table an analyst scans first: level, week-on-week change, year-on-year, and
where the level sits against its own seasonal norm.

Every number here is computed in Python and published as a row. Spec 32 §1 is explicit
that the serving layer holds no maths beyond filtering and joining, so nothing downstream
recomputes a delta from the raw series.

Conventions, all deliberate:

* `wow` is an **absolute** change in the line's own unit, matching how EIA and every
  trade report quote a weekly stock build or draw ("crude drew 2.1 million barrels").
* `yoy_pct` and `vs_median_pct` are **percentages**, because a level's distance from last
  year or from its seasonal norm is only meaningful relative to its own size -- 5 million
  barrels means something different for crude stocks than for jet fuel supplied.
* `vs_median_pct` compares against `core.seasonal`'s median for this day-of-year, so 2020
  is excluded from the benchmark (golden rule 4).
* Any comparison whose counterpart is missing is `None`, never 0.0 -- a line with no
  year-ago observation has no year-on-year change, and publishing zero would read as
  "unchanged" on the screen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, cast

import pandas as pd
from core.publish import seasonal_rows

WPSR_LINES_COLUMNS: Final = [
    "week_ending",
    "line",
    "label",
    "unit",
    "value",
    "wow",
    "yoy_pct",
    "vs_median_pct",
    "line_order",
]

# A WPSR week is 7 days, and EIA's own release dates drift by a day around holidays, so
# the year-ago comparison is the observation nearest 52 weeks back rather than an exact
# date match, within this tolerance.
YEAR_AGO_DAYS: Final = 364
YEAR_AGO_TOLERANCE_DAYS: Final = 10


@dataclass(frozen=True)
class WPSRLine:
    """One headline line of the report: a lake series, and how it is presented."""

    line: str
    series_id: str
    label: str


# The national headline lines, in the order an analyst reads them: stocks first (the
# number the market trades), then the refinery run picture, then demand and trade. Series
# ids are the EIA codes `pull_wpsr.py` already pulls -- see pipelines/eia/CLAUDE.md for
# what each one is. PADD-level breakdowns are deliberately excluded: this is the
# at-a-glance table, not the full report.
WPSR_REPORT_LINES: Final[tuple[WPSRLine, ...]] = (
    WPSRLine("crude_ex_spr", "WCESTUS1", "Crude oil, excluding SPR"),
    WPSRLine("cushing", "W_EPC0_SAX_YCUOK_MBBL", "Crude oil at Cushing, Oklahoma"),
    WPSRLine("spr", "WCSSTUS1", "Strategic Petroleum Reserve"),
    WPSRLine("gasoline", "WGTSTUS1", "Total motor gasoline"),
    WPSRLine("distillate", "WDISTUS1", "Distillate fuel oil"),
    WPSRLine("total_ex_spr", "WTESTUS1", "Total stocks, excluding SPR"),
    WPSRLine("refinery_utilisation", "WPULEUS3", "Refinery utilisation"),
    WPSRLine("gross_inputs", "WGIRIUS2", "Refinery gross inputs"),
    WPSRLine("crude_runs", "WCRRIUS2", "Refiner net input of crude oil"),
    WPSRLine("product_supplied", "WRPUPUS2", "Total products supplied"),
    WPSRLine("gasoline_supplied", "WGFUPUS2", "Motor gasoline supplied"),
    WPSRLine("distillate_supplied", "WDIUPUS2", "Distillate supplied"),
    WPSRLine("crude_production", "WCRFPUS2", "Crude oil production"),
    WPSRLine("crude_imports", "WCEIMUS2", "Crude oil imports"),
    WPSRLine("crude_exports", "WCREXUS2", "Crude oil exports"),
)


def _nearest_value(series: pd.DataFrame, target: pd.Timestamp, tolerance_days: int) -> float | None:
    """The observation closest to `target`, or None if none falls within tolerance."""
    if series.empty:
        return None
    gap = (series["ts"] - target).abs()
    closest = gap.idxmin()
    if gap.loc[closest] > pd.Timedelta(days=tolerance_days):
        return None
    value = series.loc[closest, "value"]
    return None if pd.isna(value) else float(cast(float, value))


def _pct_change(value: float, reference: float | None) -> float | None:
    """Percentage change against `reference`, or None when it cannot be expressed.

    A zero reference has no percentage change -- dividing would raise or produce an
    infinity that reads as a real number on the screen.
    """
    if reference is None or reference == 0:
        return None
    return (value / reference - 1.0) * 100.0


def _median_at(series: pd.DataFrame, line: WPSRLine, week_ending: pd.Timestamp) -> float | None:
    """`core.seasonal`'s median for this line at `week_ending`'s day-of-year."""
    bands = seasonal_rows(series, series_id=line.series_id)
    if bands.empty:
        return None
    # core.seasonal normalises every date onto a non-leap reference year, and drops 29
    # February entirely -- so a week ending on the 29th has no day-of-year of its own.
    day = week_ending.day
    month = week_ending.month
    if (month, day) == (2, 29):
        day = 28
    doy = pd.Timestamp(year=2001, month=month, day=day).dayofyear
    match = bands.loc[bands["doy"] == doy, "median"]
    if match.empty or pd.isna(match.iloc[0]):
        return None
    return float(match.iloc[0])


def build_wpsr_lines(df: pd.DataFrame) -> pd.DataFrame:
    """`serving.wpsr_lines` rows for the latest week in `df`.

    `df` is a `ts_long`-shaped frame carrying the full history of the WPSR series -- the
    history is what the year-ago and seasonal-median comparisons are drawn from, so a
    trailing-window frame would silently produce a table of nulls.
    """
    rows: list[dict[str, object]] = []
    for order, line in enumerate(WPSR_REPORT_LINES, start=1):
        series = df.loc[df["series_id"] == line.series_id, ["ts", "value", "unit"]]
        series = series.dropna(subset=["value"]).sort_values("ts")
        if series.empty:
            continue

        latest = series.iloc[-1]
        week_ending = pd.Timestamp(latest["ts"])
        value = float(latest["value"])

        prior = series.iloc[-2] if len(series) >= 2 else None
        wow = None if prior is None else value - float(prior["value"])

        year_ago = _nearest_value(
            series.iloc[:-1],
            week_ending - pd.Timedelta(days=YEAR_AGO_DAYS),
            YEAR_AGO_TOLERANCE_DAYS,
        )

        rows.append(
            {
                "week_ending": week_ending.date(),
                "line": line.line,
                "label": line.label,
                "unit": str(latest["unit"]),
                "value": value,
                "wow": wow,
                "yoy_pct": _pct_change(value, year_ago),
                # `series`, not `df`: the median must come from this line's own history.
                # Passing the whole multi-series frame compared crude stocks against a
                # median blended with refinery utilisation and daily rates -- caught on
                # real data, +11,462% for crude before the fix.
                "vs_median_pct": _pct_change(value, _median_at(series, line, week_ending)),
                "line_order": order,
            }
        )

    return pd.DataFrame(rows, columns=WPSR_LINES_COLUMNS)
