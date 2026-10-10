"""Serving-shaped tables for the publishing layer, read from the local lake only.

Nothing here connects to Supabase or calls an API (golden rule 2). The shapes mirror
Spec 32's `serving.*` tables so a page, a slide and a worksheet all quote the same rows.
Seasonal bands come from `core.seasonal` (golden rule 4) with an explicit five-year
window -- see `band_years`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Final

import core.storage as storage
import pandas as pd
from core.freshness import staleness_report
from core.seasonal import REFERENCE_YEAR, seasonal_stats
from core.storage import read_flows, read_ts_long
from pipelines.eia.wpsr_lines import WPSR_REPORT_LINES, build_wpsr_lines
from pipelines.futures.publish_curve import curve_settles_frame

BAND_YEARS: Final = 5

SEASONAL_COLUMNS: Final = [
    "series_id",
    "doy",
    "band_min",
    "band_max",
    "median",
    "current",
    "prior",
    "years",
    "unit",
]
FLOW_COLUMNS: Final = ["source", "mode", "corridor", "through", "latest", "year_ago", "unit"]
STORAGE_COLUMNS: Final = ["series_id", "geo", "through", "full_pct", "year_ago_pct"]

_MONTH_CODES: Final = "FGHJKMNQUVXZ"


def use_lake(root: Path) -> None:
    """Point `core.storage` at a lake outside the working directory (a git worktree
    holds the code but not the git-ignored data)."""
    storage.LAKE_ROOT = root
    storage.SANCTIONS_CURRENT_PATH = root / "sanctions" / "current.parquet"


def lake_root() -> Path:
    return Path(storage.LAKE_ROOT)


def _naive(ts: pd.Series) -> pd.Series:
    stamps = pd.to_datetime(ts)
    if stamps.dt.tz is not None:
        stamps = stamps.dt.tz_convert("UTC").dt.tz_localize(None)
    return stamps


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    out = df.dropna(subset=["value"]).copy()
    out["ts"] = _naive(out["ts"])
    return out.sort_values(["series_id", "ts"]).reset_index(drop=True)


def read_series(series_ids: list[str], start: str | None = None) -> pd.DataFrame:
    """`ts_long` rows for `series_ids`, timezone-naive and sorted."""
    since = None if start is None else datetime.fromisoformat(start)
    return _clean(read_ts_long(series_ids=series_ids, start=since))


def read_prefix(prefix: str, source: str) -> pd.DataFrame:
    return _clean(read_ts_long(source=source, series_prefix=prefix))


def pulled_at(dataset: str, source: str) -> datetime | None:
    """When a pipeline last wrote this source: the newest Parquet file's mtime. Used
    where the table itself carries no `revision_date` (flows)."""
    files = list((lake_root() / dataset / f"source={source}").glob("**/*.parquet"))
    if not files:
        return None
    return datetime.fromtimestamp(max(f.stat().st_mtime for f in files))


def band_years(current_year: int) -> range:
    """The five calendar years before `current_year`. `seasonal_stats` still drops 2020,
    so a window touching it is four years wide and `years` in the table says so."""
    return range(current_year - BAND_YEARS, current_year)


def _track(stats: pd.DataFrame, year: int, index: pd.Index) -> pd.Series:
    column = str(year)
    if column not in stats:
        return pd.Series(float("nan"), index=index)
    return stats[column].reindex(index)


def seasonal_table(series: pd.DataFrame, series_id: str) -> pd.DataFrame:
    """`serving.seasonal`-shaped rows: five-year min/max/median by day of year, with the
    current and prior year's tracks. The current track stops at its last observation --
    `seasonal_stats` forward-fills each year to 31 December, which would otherwise draw
    a flat line into dates that have not happened."""
    if series.empty:
        return pd.DataFrame(columns=SEASONAL_COLUMNS)
    series = series.drop_duplicates(subset="ts", keep="last")
    last = pd.Timestamp(series["ts"].max())
    year = int(last.year)
    band = seasonal_stats(series, value_col="value", years=band_years(year))
    tracks = seasonal_stats(series, value_col="value", years=range(year - 1, year + 1), exclude=())
    out = pd.DataFrame(
        {
            "series_id": series_id,
            "doy": band.index.astype(int),
            "band_min": band["lo"].to_numpy(),
            "band_max": band["hi"].to_numpy(),
            "median": band["median"].to_numpy(),
            "current": _track(tracks, year, band.index).to_numpy(),
            "prior": _track(tracks, year - 1, band.index).to_numpy(),
            "years": sum(1 for c in band.columns if c.isdigit()),
            "unit": str(series["unit"].iloc[-1]),
        },
        columns=SEASONAL_COLUMNS,
    )
    leap_safe_day = min(int(last.day), 28) if last.month == 2 else int(last.day)
    last_doy = pd.Timestamp(year=REFERENCE_YEAR, month=int(last.month), day=leap_safe_day).dayofyear
    out.loc[out["doy"] > last_doy, "current"] = float("nan")
    return out


def wpsr_lines() -> pd.DataFrame:
    """`serving.wpsr_lines`, exactly as the WPSR pipeline builds it. Its `vs_median_pct`
    uses the repo's default seasonal window (2018 onwards, 2020 excluded), not the
    five-year band the charts draw."""
    ids = [line.series_id for line in WPSR_REPORT_LINES]
    return build_wpsr_lines(read_series(ids))


def brent_curve() -> pd.DataFrame:
    """`serving.curve_settles` rows for the latest manual Brent curve drop, plus a
    `delivery` month parsed from the contract code."""
    frame = curve_settles_frame(read_prefix("fut.lco.", "manual"))
    if frame.empty:
        return frame.assign(delivery=pd.Series(dtype="datetime64[ns]"))
    frame = frame[frame["trade_date"] == frame["trade_date"].max()].copy()
    frame["delivery"] = [
        pd.Timestamp(year=int(code[-4:]), month=_MONTH_CODES.index(code[-5]) + 1, day=1)
        for code in frame["contract"].astype(str)
    ]
    ordered: pd.DataFrame = frame.sort_values(by="delivery").reset_index(drop=True)
    return ordered


def flows_compare(source: str, mode: str, window_days: int) -> pd.DataFrame:
    """Each corridor's mean over its latest `window_days` against the same window one
    calendar year earlier. Interconnection points feeding a corridor are summed first."""
    df = read_flows(source=source)
    df = df[df["mode"] == mode].copy()
    if df.empty:
        return pd.DataFrame(columns=FLOW_COLUMNS)
    df["ts"] = _naive(df["ts"])
    df["corridor"] = df["from_node"] + " to " + df["to_node"]
    daily = df.groupby(["corridor", "ts"], as_index=False).agg(
        value=("value", "sum"), unit=("unit", "first")
    )
    year = pd.DateOffset(years=1)
    rows: list[dict[str, object]] = []
    for corridor, sub in daily.groupby("corridor"):
        through = sub["ts"].max()
        start = through - pd.Timedelta(days=window_days - 1)
        now = sub.loc[sub["ts"] >= start, "value"]
        prior = sub.loc[(sub["ts"] >= start - year) & (sub["ts"] <= through - year), "value"]
        rows.append(
            {
                "source": source,
                "mode": mode,
                "corridor": corridor,
                "through": through,
                "latest": float(now.mean()),
                "year_ago": float(prior.mean()) if len(prior) else None,
                "unit": str(sub["unit"].iloc[-1]),
            }
        )
    out = pd.DataFrame(rows, columns=FLOW_COLUMNS)
    return out.sort_values(by="latest", ascending=False).reset_index(drop=True)


def _fullness() -> pd.DataFrame:
    df = read_prefix("agsi.", "gie")
    df = df[df["series_id"].str.endswith(".full_pct")].copy()
    df["geo"] = df["series_id"].str.split(".").str[1]
    return df


def storage_by_country() -> pd.DataFrame:
    """Latest AGSI+ fullness per country, with the value a year earlier."""
    rows: list[dict[str, object]] = []
    for series_id, sub in _fullness().groupby("series_id"):
        latest = sub.iloc[-1]
        target = latest["ts"] - pd.Timedelta(days=364)
        # The nearest observation to the target, not merely the last one inside the window.
        distance = (sub["ts"] - target).abs()
        near = distance.idxmin()
        year_ago = float(sub.loc[near, "value"]) if distance[near] <= pd.Timedelta(days=3) else None
        rows.append(
            {
                "series_id": series_id,
                "geo": latest["geo"],
                "through": latest["ts"],
                "full_pct": float(latest["value"]),
                "year_ago_pct": year_ago,
            }
        )
    # Explicit columns so a lake with no AGSI+ rows gives an empty table, not a KeyError.
    out = pd.DataFrame(rows, columns=STORAGE_COLUMNS)
    return out.sort_values(by="full_pct", ascending=False).reset_index(drop=True)


def storage_weekly() -> pd.DataFrame:
    """AGSI+ fullness sampled each Monday plus the latest day, one column per country."""
    wide = _fullness().pivot_table(index="ts", columns="geo", values="value")
    keep = (pd.DatetimeIndex(wide.index).dayofweek == 0) | (wide.index == wide.index.max())
    weekly: pd.DataFrame = wide.loc[keep]
    return weekly


def freshness() -> pd.DataFrame:
    """`core.freshness`'s own report, with each source's pipeline write time added."""
    report = staleness_report().copy()
    report["pulled_at"] = [
        pulled_at(str(d), str(s)) for d, s in zip(report["dataset"], report["source"], strict=True)
    ]
    return report.sort_values(["dataset", "source"]).reset_index(drop=True)
