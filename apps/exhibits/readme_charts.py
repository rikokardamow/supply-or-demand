"""The README's charts, drawn with matplotlib from the local lake.

    uv run python -m apps.exhibits.readme_charts [--lake data/lake] [--out docs/img]

Four exhibits, one per kind of data the lake holds: a seasonal band (US crude
stocks), weekly positioning (CFTC managed money in WTI), directional flows
(crude between PADDs by mode) and a second seasonal band (EU gas storage).
Every number is read from the lake, never typed in; the seasonal maths is
core.seasonal, with 2020 excluded by rule.

Paper format (core/paper_style.py, docs/FIGURES.md): each chart is drawn at its printed
width (7.0 in) in a grey sans-serif between 6 and 9 pt, with an axis label and unit on both
axes, no box (a light baseline and faint horizontal gridlines) and haloed direct labels.
Nothing about the finding is drawn on the image: the title, units, cadence, source and
as-of date, all computed from the data, go to a LaTeX caption written beside the figure.
Each chart is written as a vector PDF (Type 42 fonts), a 300 dpi PNG (what the README
shows) and a `.tex` caption, all under the same name, byte-identical between runs.
Series are labelled where they are drawn, one unit per axis.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import date
from pathlib import Path

import duckdb
import matplotlib.dates as mdates
import pandas as pd
from core import paper_style as ps
from core import seasonal
from matplotlib.axes import Axes
from matplotlib.figure import Figure

BAND_SIZE = 5
"""How many prior years make the band, matching the artifacts' design system."""
FORMATS = ("pdf", "png", "tex")
# Room on the right for labels at the ends of the lines (inches): left, right, top, bottom.
MARGINS = (0.7, 1.45, 0.2, 0.55)


def end_label(ax: Axes, x: float, y: float, name: str, value: str, colour: str) -> None:
    """A dot in the series colour and a label in body colour: grey and orange are too
    pale for 7.5 pt text, so the colour sits in the dot and the words stay dark."""
    ps.end_label(ax, x, y, name, value, color=colour)
    ax.texts[-1].set_color(ps.TOKENS["text"])


def new_figure() -> tuple[Figure, Axes]:
    """A 7.0 in wide figure with one panel."""
    fig, axes = ps.figure()
    return fig, axes[0][0]


def month_ticks(ax: Axes) -> None:
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))


def month_end(ts: pd.Timestamp) -> date:
    return (ts + pd.offsets.MonthEnd(0)).date()


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


def band_years(df: pd.DataFrame) -> range:
    """The years the band is drawn from: the five before the latest observation's year.

    Read from the data, not frozen. This was the literal `range(2021, 2026)`, correct only
    until the first observation of 2027 arrived, after which every chart would have set the
    new year against a band that stopped a year short, with no error (the failure
    `core.seasonal.default_years` documents). 2020 can fall inside the window in a frame
    ending in 2025 or earlier; `seasonal.seasonal_stats` leaves it out by default.
    """
    last_year = int(df["ts"].max().year)
    return range(last_year - BAND_SIZE, last_year)


def _span(years: range) -> str:
    return f"{years.start} to {years.stop - 1}"


def seasonal_panel(
    ax: Axes,
    df: pd.DataFrame,
    label: Callable[[float, pd.Timestamp], tuple[str, str]],
) -> tuple[float, float]:
    """The current year against the band of `band_years(df)`. Returns the latest value
    and the median for the same day."""
    years = band_years(df)
    stats = seasonal.seasonal_stats(df, "value", years=years)
    this_year = df[df["ts"].dt.year == df["ts"].max().year]
    doy = seasonal._normalised_doy(this_year["ts"])
    jan1 = date(seasonal.REFERENCE_YEAR, 1, 1)
    x = mdates.date2num([jan1 + pd.Timedelta(days=int(d) - 1) for d in stats.index])
    xs = mdates.date2num([jan1 + pd.Timedelta(days=int(d) - 1) for d in doy])
    ax.fill_between(x, stats["lo"], stats["hi"], color=ps.TOKENS["border"], linewidth=0)
    ax.plot(x, stats["median"], color=ps.PALETTE[2], linestyle=ps.DASHES[1], linewidth=1.2)
    ax.plot(xs, this_year["value"], color=ps.PALETTE[0], linewidth=1.2)
    last_v, last_t = float(this_year["value"].iloc[-1]), this_year["ts"].iloc[-1]
    end_label(ax, float(xs[-1]), last_v, *label(last_v, last_t), colour=ps.PALETTE[0])
    # The band and the median are named at the right-hand end of the year.
    span = _span(years)
    end_label_x = float(x[-1])
    ax.annotate(
        f"{span} range",
        (end_label_x, float(stats["hi"].iloc[-1])),
        xytext=(5, 4),
        textcoords="offset points",
        fontsize=7.5,
        color=ps.TOKENS["text_muted"],
        annotation_clip=False,
        path_effects=ps.halo(),
    )
    ax.annotate(
        f"{span} median",
        (end_label_x, float(stats["median"].iloc[-1])),
        xytext=(5, -9),
        textcoords="offset points",
        fontsize=7.5,
        color=ps.TOKENS["text_muted"],
        annotation_clip=False,
        path_effects=ps.halo(),
    )
    ax.set_xlim(float(x[0]), float(x[-1]))
    month_ticks(ax)
    median_now = float(stats["median"].loc[int(doy.iloc[-1])])
    return last_v, median_now


def crude_stocks(lake: Lake) -> Figure:
    df = lake.series("WCESTUS1", "eia")
    df["value"] = df["value"] / 1000  # thousand barrels -> million barrels
    fig, ax = new_figure()
    v, m = seasonal_panel(ax, df, lambda v, t: (f"{v:,.0f} mb", f"{t:%b %-d}"))
    pct = 100 * (v - m) / m
    ps.frame(
        fig,
        title=f"US commercial crude stocks are {abs(pct):.1f}% "
        f"{'below' if pct < 0 else 'above'} the median for the date",
        subtitle=f"US commercial crude stocks against the same date in recent years, excluding "
        f"the Strategic Petroleum Reserve: {df['ts'].max().year} against the range and median "
        f"of {_span(band_years(df))}, with 2020 excluded by rule",
        units="million barrels",
        cadence="weekly",
        source="U.S. EIA, Weekly Petroleum Status Report (series WCESTUS1)",
        licence="Public domain",
        asof=df["ts"].max().date(),
        xlabel="Month of the year",
        ylabel="Crude stocks (million barrels)",
        margins=MARGINS,
    )
    return fig


def cftc_positioning(lake: Lake) -> Figure:
    long = lake.series("cftc.cl.mm_long", "cftc").set_index("ts")["value"] / 1000
    short = lake.series("cftc.cl.mm_short", "cftc").set_index("ts")["value"] / 1000
    both = pd.DataFrame({"long": long, "short": short}).dropna()
    both = both[both.index >= both.index.max() - pd.Timedelta(days=3 * 365)]
    net = both["long"] - both["short"]
    fig, ax = new_figure()
    ax.bar(both.index, both["long"], width=5, color=ps.PALETTE[0])
    ax.bar(both.index, -both["short"], width=5, color=ps.PALETTE[2])
    ax.plot(net.index, net, color=ps.PALETTE[3], linewidth=1.2)
    ax.axhline(0, color=ps.TOKENS["text_muted"], linewidth=0.6)
    last = net.index[-1]
    x_last = float(mdates.date2num(last))
    for y, name, value, colour in (
        (both["long"].iloc[-1], "long", f"{both['long'].iloc[-1]:.0f}k", ps.PALETTE[0]),
        (net.iloc[-1], "net", f"{ps.signed(net.iloc[-1], 0)}k", ps.PALETTE[3]),
        (-both["short"].iloc[-1], "short", f"{both['short'].iloc[-1]:.0f}k", ps.PALETTE[2]),
    ):
        end_label(ax, x_last, y, name, value, colour)
    ps.date_axis(ax)
    peak = net.idxmax()
    ps.frame(
        fig,
        title=f"Managed money is net long {net.iloc[-1]:.0f} thousand contracts, "
        f"{100 * (1 - net.iloc[-1] / net.max()):.0f}% below its three-year high of "
        f"{peak:%B %Y}",
        subtitle="Managed-money positioning in WTI crude futures: long above the axis, short "
        "below, net as the line. Bars, because the book is counted once a week and nothing is "
        "known in between",
        units="thousand contracts",
        cadence="weekly",
        source="CFTC Commitments of Traders, disaggregated futures-only report "
        "(series cftc.cl.mm_long, cftc.cl.mm_short)",
        licence="Public domain",
        asof=last.date(),
        xlabel="Report week",
        ylabel="Contracts (thousand; short below zero)",
        margins=MARGINS,
    )
    return fig


def interpadd_flows(lake: Lake) -> Figure:
    df = lake.crude_flows_by_mode()
    df = df[df["ts"] >= "2010-01-01"]
    df["mbd"] = df["value"] / 1000 / df["ts"].dt.days_in_month  # kb per month -> mb/d
    wide = df.pivot(index="ts", columns="mode", values="mbd")
    fig, ax = new_figure()
    names = {"pipeline": "Pipeline", "rail": "Rail", "tanker_barge": "Tanker and barge"}
    for i, (mode, name) in enumerate(names.items()):
        s = wide[mode].dropna()
        style = ps.series_style(i)
        ax.plot(s.index, s, **style)
        end_label(
            ax, float(mdates.date2num(s.index[-1])), s.iloc[-1], name, f"{s.iloc[-1]:.2f}",
            style["color"],
        )
    rail = wide["rail"].dropna()
    ax.set_ylim(bottom=0)
    ps.date_axis(ax)
    ps.frame(
        fig,
        title=f"Rail peaked at {rail.max():.2f} mb/d in {rail.idxmax():%B %Y} and carries "
        f"{rail.iloc[-1]:.2f} now; pipelines carry {wide['pipeline'].dropna().iloc[-1]:.1f}",
        subtitle="Crude oil moved between US regions, by mode of transport, all PADD pairs "
        "summed",
        units="million barrels a day",
        cadence="monthly",
        source="U.S. EIA, movements of crude oil between PADDs "
        f"(latest month {wide.index.max():%B %Y})",
        licence="Public domain",
        asof=month_end(wide.index.max()),
        xlabel="Month",
        ylabel="Crude moved (million barrels a day)",
        margins=MARGINS,
    )
    return fig


def eu_gas_storage(lake: Lake) -> Figure:
    df = lake.series("agsi.EU.full_pct", "gie")
    fig, ax = new_figure()
    v, m = seasonal_panel(ax, df, lambda v, t: (f"{v:.1f} %", f"{t:%b %-d}"))
    ps.frame(
        fig,
        title=f"EU gas storage is {v:.1f}% full, {abs(v - m):.1f} points "
        f"{'below' if v < m else 'above'} the median for the date",
        subtitle=f"EU gas storage against the same date in recent years, EU aggregate: "
        f"{df['ts'].max().year} against the range and median of {_span(band_years(df))}",
        units="% of working capacity",
        cadence="daily",
        source="GIE AGSI+ (series agsi.EU.full_pct)",
        asof=df["ts"].max().date(),
        xlabel="Month of the year",
        ylabel="Storage (% of working capacity)",
        margins=MARGINS,
    )
    return fig


CHARTS: dict[str, Callable[[Lake], Figure]] = {
    "crude_stocks": crude_stocks,
    "cftc_positioning": cftc_positioning,
    "interpadd_flows": interpadd_flows,
    "eu_gas_storage": eu_gas_storage,
}


def build_all(lake_root: Path, out: Path) -> list[Path]:
    """Draw every chart; write `<name>.pdf`, `<name>.png` and `<name>.tex` under `out`."""
    lake = Lake(lake_root)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, draw in CHARTS.items():
        written.extend(Path(p) for p in ps.save(draw(lake), out / name, formats=FORMATS))
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
