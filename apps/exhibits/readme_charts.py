"""The README's charts, drawn with matplotlib from the local lake.

    uv run python -m apps.exhibits.readme_charts [--lake data/lake] [--out docs/img]

Four exhibits, one per kind of data the lake holds: a seasonal band (US crude
stocks), weekly positioning (CFTC managed money in WTI), directional flows
(crude between PADDs by mode) and a second seasonal band (EU gas storage).
Every number is read from the lake, never typed in; the seasonal maths is
core.seasonal, with 2020 excluded by rule.

House style: the title states the finding and is computed from the data, the
subtitle gives the units, one muted footer names the source and the as-of date,
series are labelled where they are drawn, one unit per axis.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import date
from pathlib import Path
from textwrap import fill

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from core import design, seasonal
from matplotlib.axes import Axes
from matplotlib.figure import Figure

NAVY, BLUE, GREY = design.NAVY, design.LIGHT_BLUE, design.GREY
TEXT, MUTED, BAND = "#0B1F3A", "#5B6878", "#DCE3EC"
BAND_YEARS = range(2021, 2026)

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Inter", "Helvetica Neue", "Helvetica", "DejaVu Sans"],
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": BAND,
        "axes.labelcolor": MUTED,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": BAND,
        "grid.linewidth": 0.6,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "text.color": TEXT,
        "font.size": 10,
        "lines.linewidth": 2,
    }
)


def frame(fig: Figure, title: str, subtitle: str, footer: str) -> None:
    """Title, subtitle and footer wrapped to the figure's width; the axes' top and
    bottom margins follow from how many lines they take."""
    w, h = fig.get_size_inches()
    tw, sw, fw = fill(title, int(w * 9)), fill(subtitle, int(w * 13.5)), fill(footer, int(w * 17))
    y = 1 - 0.1 / h
    fig.text(
        0.01,
        y,
        tw,
        ha="left",
        va="top",
        fontsize=14,
        fontweight="bold",
        color=TEXT,
        linespacing=1.25,
    )
    y -= (0.27 * (tw.count("\n") + 1) + 0.1) / h
    fig.text(0.01, y, sw, ha="left", va="top", fontsize=10, color=MUTED, linespacing=1.4)
    y -= (0.2 * (sw.count("\n") + 1) + 0.3) / h
    fig.text(0.01, 0.08 / h, fw, ha="left", va="bottom", fontsize=8.5, color=MUTED, linespacing=1.4)
    fig.subplots_adjust(top=y, bottom=(0.08 + 0.17 * (fw.count("\n") + 1) + 0.4) / h)


def plain_dates(ax: Axes) -> None:
    loc = mdates.AutoDateLocator()
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
    ax.tick_params(length=0)


def signed(v: float, digits: int = 1) -> str:
    return f"{v:+.{digits}f}".replace("-", "−")


class Lake:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.con = duckdb.connect()

    def series(self, series_id: str, source: str) -> pd.DataFrame:
        """ts, value for one series, newest revision of each timestamp."""
        glob = str(self.root / "ts_long" / f"source={source}" / "**" / "*.parquet")
        df: pd.DataFrame = self.con.execute(
            "select ts, arg_max(value, revision_date) as value "
            "from read_parquet(?, hive_partitioning=true) where series_id = ? "
            "group by ts order by ts",
            [glob, series_id],
        ).df()
        df["ts"] = pd.to_datetime(df["ts"])
        return df

    def crude_flows_by_mode(self) -> pd.DataFrame:
        """Monthly crude moved between PADDs, thousand barrels, by mode."""
        glob = str(self.root / "flows" / "source=eia" / "**" / "*.parquet")
        df: pd.DataFrame = self.con.execute(
            "select ts, mode, sum(value) as value from read_parquet(?, hive_partitioning=true) "
            "where mode in ('pipeline', 'rail', 'tanker_barge') and unit = 'MBBL' "
            "group by ts, mode order by ts",
            [glob],
        ).df()
        df["ts"] = pd.to_datetime(df["ts"])
        return df


def seasonal_panel(
    ax: Axes, df: pd.DataFrame, unit: str, label: Callable[[float, pd.Timestamp], str]
) -> tuple[float, float]:
    """The current year against the band of BAND_YEARS. Returns the latest value
    and the median for the same day."""
    stats = seasonal.seasonal_stats(df, "value", years=BAND_YEARS)
    this_year = df[df["ts"].dt.year == df["ts"].max().year]
    doy = seasonal._normalised_doy(this_year["ts"])
    jan1 = date(seasonal.REFERENCE_YEAR, 1, 1)
    x = mdates.date2num([jan1 + pd.Timedelta(days=int(d) - 1) for d in stats.index])
    xs = mdates.date2num([jan1 + pd.Timedelta(days=int(d) - 1) for d in doy])
    ax.fill_between(x, stats["lo"], stats["hi"], color=BAND, linewidth=0)
    ax.plot(x, stats["median"], color=GREY, linestyle="--", linewidth=1.5)
    ax.plot(xs, this_year["value"], color=NAVY)
    last_v, last_t = float(this_year["value"].iloc[-1]), this_year["ts"].iloc[-1]
    ax.plot([xs[-1]], [last_v], marker="o", markersize=7, color=NAVY)
    ax.annotate(
        label(last_v, last_t),
        (xs[-1], last_v),
        xytext=(8, 0),
        textcoords="offset points",
        va="center",
        fontsize=9,
        color=TEXT,
    )
    mid = len(stats) // 2
    ax.annotate(
        f"{BAND_YEARS.start}–{BAND_YEARS.stop - 1} median",
        (x[mid], stats["median"].iloc[mid]),
        xytext=(0, 7),
        textcoords="offset points",
        ha="center",
        fontsize=8.5,
        color=MUTED,
    )
    ax.text(
        x[mid], stats["hi"].iloc[mid], "range", ha="center", va="bottom", fontsize=8.5, color=MUTED
    )
    ax.set_ylabel(unit)
    ax.set_xlim(float(x[0]), float(x[-1]) + 40)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.tick_params(length=0)
    median_now = float(stats["median"].loc[int(doy.iloc[-1])])
    return last_v, median_now


def crude_stocks(lake: Lake) -> Figure:
    df = lake.series("WCESTUS1", "eia")
    df["value"] = df["value"] / 1000  # thousand barrels -> million barrels
    fig, ax = plt.subplots(figsize=(10, 4.8))
    fig.subplots_adjust(left=0.07, right=0.9)
    v, m = seasonal_panel(ax, df, "million barrels", lambda v, t: f"{v:,.0f} mb · {t:%b %-d}")
    pct = 100 * (v - m) / m
    frame(
        fig,
        f"US commercial crude stocks are {abs(pct):.1f} % {'below' if pct < 0 else 'above'} "
        f"the {BAND_YEARS.start}–{BAND_YEARS.stop - 1} median for the date",
        f"Weekly stocks excluding the Strategic Petroleum Reserve, million barrels; "
        f"{df['ts'].max().year} against the range and median of {BAND_YEARS.start}–"
        f"{BAND_YEARS.stop - 1} (our band, 2020 excluded by rule)",
        f"Source: U.S. EIA, Weekly Petroleum Status Report (WCESTUS1) · Public domain · "
        f"As of {df['ts'].max():%Y-%m-%d}",
    )
    return fig


def cftc_positioning(lake: Lake) -> Figure:
    long = lake.series("cftc.cl.mm_long", "cftc").set_index("ts")["value"] / 1000
    short = lake.series("cftc.cl.mm_short", "cftc").set_index("ts")["value"] / 1000
    both = pd.DataFrame({"long": long, "short": short}).dropna()
    both = both[both.index >= both.index.max() - pd.Timedelta(days=3 * 365)]
    net = both["long"] - both["short"]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    fig.subplots_adjust(left=0.07, right=0.84)
    ax.bar(both.index, both["long"], width=5, color=NAVY)
    ax.bar(both.index, -both["short"], width=5, color=GREY)
    ax.plot(net.index, net, color=BLUE, linewidth=1.8)
    ax.axhline(0, color=MUTED, linewidth=0.8)
    last = net.index[-1]
    for y, text, colour in (
        (both["long"].iloc[-1], f"long {both['long'].iloc[-1]:.0f}k", NAVY),
        (net.iloc[-1], f"net {signed(net.iloc[-1], 0)}k", BLUE),
        (-both["short"].iloc[-1], f"short {both['short'].iloc[-1]:.0f}k", GREY),
    ):
        ax.annotate(
            text,
            (last, y),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=colour,
            fontweight="bold",
        )
    ax.set_ylabel("thousand contracts (short below the axis)")
    plain_dates(ax)
    peak = net.idxmax()
    frame(
        fig,
        f"Managed money is net long {net.iloc[-1]:.0f} thousand WTI contracts, "
        f"{100 * (1 - net.iloc[-1] / net.max()):.0f} % below its three-year high of "
        f"{peak:%b %Y}",
        "CFTC Commitments of Traders, NYMEX WTI: managed-money long (above the axis), short "
        "(below) and net (line), thousand contracts, weekly. Bars, because the book is counted "
        "once a week and nothing is known in between.",
        f"Source: CFTC disaggregated futures-only report · Public domain · As of {last:%Y-%m-%d}",
    )
    return fig


def interpadd_flows(lake: Lake) -> Figure:
    df = lake.crude_flows_by_mode()
    df = df[df["ts"] >= "2010-01-01"]
    df["mbd"] = df["value"] / 1000 / df["ts"].dt.days_in_month  # kb per month -> mb/d
    wide = df.pivot(index="ts", columns="mode", values="mbd")
    fig, ax = plt.subplots(figsize=(10, 4.8))
    fig.subplots_adjust(left=0.07, right=0.84)
    names = {
        "pipeline": ("Pipeline", NAVY),
        "tanker_barge": ("Tanker and barge", GREY),
        "rail": ("Rail", BLUE),
    }
    for mode, (name, colour) in names.items():
        s = wide[mode].dropna()
        ax.plot(s.index, s, color=colour)
        ax.annotate(
            f"{name}  {s.iloc[-1]:.2f}",
            (s.index[-1], s.iloc[-1]),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=colour,
            fontweight="bold",
        )
    rail = wide["rail"].dropna()
    ax.set_ylabel("million barrels a day")
    ax.set_ylim(bottom=0)
    plain_dates(ax)
    frame(
        fig,
        f"Rail moved {rail.max():.2f} mb/d of crude between US regions at its "
        f"{rail.idxmax():%B %Y} peak and {rail.iloc[-1]:.2f} mb/d now; pipelines carry "
        f"{wide['pipeline'].dropna().iloc[-1]:.1f}",
        "Crude oil moved between PADDs by mode, million barrels a day, monthly, all region pairs "
        "summed. Modes are kept apart because the mode is usually the story.",
        f"Source: U.S. EIA, movements of crude oil between PADDs · Public domain · "
        f"As of {wide.index.max():%Y-%m}",
    )
    return fig


def eu_gas_storage(lake: Lake) -> Figure:
    df = lake.series("agsi.EU.full_pct", "gie")
    fig, ax = plt.subplots(figsize=(10, 4.8))
    fig.subplots_adjust(left=0.07, right=0.9)
    v, m = seasonal_panel(ax, df, "% of working capacity", lambda v, t: f"{v:.1f} % · {t:%b %-d}")
    frame(
        fig,
        f"EU gas storage is {abs(v - m):.1f} points {'below' if v < m else 'above'} the "
        f"{BAND_YEARS.start}–{BAND_YEARS.stop - 1} median for the date, at {v:.1f} % full",
        f"Gas in storage as a share of working capacity, EU aggregate, daily; "
        f"{df['ts'].max().year} against the range and median of {BAND_YEARS.start}–"
        f"{BAND_YEARS.stop - 1}",
        f"Source: GIE AGSI+ · As of {df['ts'].max():%Y-%m-%d}",
    )
    return fig


CHARTS: dict[str, Callable[[Lake], Figure]] = {
    "crude_stocks": crude_stocks,
    "cftc_positioning": cftc_positioning,
    "interpadd_flows": interpadd_flows,
    "eu_gas_storage": eu_gas_storage,
}


def build_all(lake_root: Path, out: Path) -> list[Path]:
    lake = Lake(lake_root)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, draw in CHARTS.items():
        fig = draw(lake)
        path = out / f"{name}.png"
        fig.savefig(path, dpi=150, facecolor="white")
        plt.close(fig)
        written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--lake", type=Path, default=Path("data/lake"))
    parser.add_argument("--out", type=Path, default=Path("docs/img"))
    args = parser.parse_args()
    if not (args.lake / "ts_long").is_dir():
        raise SystemExit(f"no lake at {args.lake}; run the pipelines first")
    for path in build_all(args.lake.resolve(), args.out):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
