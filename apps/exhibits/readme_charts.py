"""The README's charts, drawn with matplotlib from the local lake.

    uv run python -m apps.exhibits.readme_charts [--lake data/lake] [--out docs/img]

Five exhibits: a seasonal band (US crude stocks), the week's change in those stocks
against the same week in prior years, weekly positioning (CFTC managed money in WTI),
directional flows (crude between PADDs by mode) and a second seasonal band (EU gas
storage).
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
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import duckdb
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import pandas as pd
from core import paper_style as ps
from core import seasonal
from matplotlib.axes import Axes
from matplotlib.figure import Figure

BAND_SIZE = 5
"""How many prior years make the band, matching the artifacts' design system."""
FORMATS = ("pdf", "png", "tex")
DESK_UNITS = frozenset({"mb", "mb/d", "kb", "kb/d", "contracts", "%"})
"""The unit spellings these exhibits may use (PROJECT-STARTER 7.2 rule 8)."""
# Room on the right for labels at the ends of the lines (inches): left, right, top, bottom.
MARGINS = (0.7, 1.45, 0.2, 0.55)


@contextmanager
def desk_rules() -> Iterator[None]:
    """Hold the exhibits to the desk rules while they are drawn: no legend box, no twin
    axis, no red or green, and only the unit spellings in `DESK_UNITS`. The switches are
    paper_style's module globals, so the previous values are put back on the way out, even
    when a chart fails, and other callers in the process are untouched."""
    previous = ps.STRICT_DESK, ps.UNITS
    ps.STRICT_DESK = True
    ps.UNITS = DESK_UNITS  # type: ignore[assignment]  # paper_style declares it as None
    try:
        yield
    finally:
        ps.STRICT_DESK = previous[0]
        ps.UNITS = previous[1]


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
    this_year = seasonal.current_year_rows(df)
    doy = seasonal.reference_doy(this_year["ts"])
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
        units="mb",
        cadence="weekly",
        source="U.S. EIA, Weekly Petroleum Status Report (series WCESTUS1)",
        licence="Public domain",
        asof=df["ts"].max().date(),
        xlabel="Month of the year",
        ylabel="Commercial crude stocks (mb)",
        margins=MARGINS,
    )
    return fig


def arrow_mb(value: float) -> str:
    """A change in mb as a direction and a size: '\u25b21.0 mb', '\u25bc2.0 mb'."""
    shown = round(value, 1)
    arrow = "\u25b2" if shown > 0 else "\u25bc" if shown < 0 else "\u25cf"
    return f"{arrow}{abs(shown):.1f} mb"


def weekly_change_band(stocks_kb: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The weekly change in stocks (mb) and its seasonal band.

    `stocks_kb` is ts, value in thousand barrels. The change is the first difference, and
    the band is `seasonal.seasonal_stats` on that change over `band_years`: for each day of
    the year, the range and median of the change in the report that held on that day in
    each of the five prior years, 2020 excluded. No new seasonal maths."""
    ordered = stocks_kb.sort_values("ts")
    changes = pd.DataFrame({"ts": ordered["ts"], "value": ordered["value"].diff() / 1000})
    changes = changes.dropna().reset_index(drop=True)
    stats = seasonal.seasonal_stats(changes, "value", years=band_years(changes))
    return changes, stats


def crude_weekly_change(lake: Lake) -> Figure:
    changes, stats = weekly_change_band(lake.series("WCESTUS1", "eia"))
    years = band_years(changes)
    recent = changes.tail(26)
    doy = [seasonal.reference_doy_clamped(t) for t in recent["ts"]]
    lo, hi = stats["lo"].reindex(doy).to_numpy(), stats["hi"].reindex(doy).to_numpy()
    median = stats["median"].reindex(doy).to_numpy()
    x = mdates.date2num(recent["ts"])
    fig, ax = new_figure()
    ax.fill_between(x, lo, hi, color=ps.TOKENS["border"], linewidth=0, step="mid")
    ax.plot(x, median, color=ps.PALETTE[2], linestyle=ps.DASHES[1], linewidth=1.2)
    ax.bar(x, recent["value"], width=5, color=ps.PALETTE[0])
    ax.axhline(0, color=ps.TOKENS["text_muted"], linewidth=0.6)
    last_v, last_t = float(recent["value"].iloc[-1]), recent["ts"].iloc[-1]
    end_label(
        ax, float(x[-1]), last_v, f"Week to {last_t:%b %-d}", f"{ps.signed(last_v)} mb",
        ps.PALETTE[0],
    )
    span = _span(years)
    notes = ((f"{span} range", float(hi[-1]), 4), (f"{span} median", float(median[-1]), -9))
    for text, y, dy in notes:
        ax.annotate(
            text,
            (float(x[-1]), y),
            xytext=(5, dy),
            textcoords="offset points",
            fontsize=7.5,
            color=ps.TOKENS["text_muted"],
            annotation_clip=False,
            path_effects=ps.halo(),
        )
    ps.date_axis(ax)
    median_now = float(median[-1])
    ps.frame(
        fig,
        title=f"US crude stocks {arrow_mb(last_v)} in the week to {last_t:%b %-d}, "
        f"against a {span} median of {arrow_mb(median_now)} for the week",
        subtitle="Weekly change in US commercial crude stocks, excluding the Strategic "
        f"Petroleum Reserve, over the last 26 weeks, against the range and median of the "
        f"same week in {span}, with 2020 excluded by rule",
        units="mb",
        cadence="weekly",
        source="U.S. EIA, Weekly Petroleum Status Report (series WCESTUS1)",
        licence="Public domain",
        asof=last_t.date(),
        xlabel="Week ending",
        ylabel="Weekly change in commercial crude stocks (mb)",
        margins=MARGINS,
    )
    return fig


def positioning_finding(net_last: float, net_max: float, peak: pd.Timestamp) -> str:
    """Sentence 1 of the CFTC caption: managed money's net position in thousand contracts
    against its three-year high of `net_max`, reached in `peak`'s month.

    "Long" or "short" follows the sign of the book and the number is its absolute value.
    The percentage below the high is only meaningful when both are net long (positive);
    otherwise it is the difference in thousand contracts, with the high's own sign
    (PROJECT-STARTER rule 3: direction is a sign, not a colour)."""
    held = round(net_last)
    if held == 0:
        lead = "Managed money is flat"
    else:
        side = "long" if held > 0 else "short"
        lead = f"Managed money is net {side} {abs(net_last):.0f} thousand contracts"
    if net_last == net_max:
        return f"{lead}, at its three-year high"
    if net_last > 0 and net_max > 0:
        below = 100 * (1 - net_last / net_max)
        return f"{lead}, {below:.0f}% below its three-year high of {peak:%B %Y}"
    return (
        f"{lead}, {net_max - net_last:.0f} thousand below its three-year high of "
        f"{ps.signed(net_max, 0)} thousand in {peak:%B %Y}"
    )


def cftc_positioning(lake: Lake) -> Figure:
    long = lake.series("cftc.cl.mm_long", "cftc").set_index("ts")["value"]
    short = lake.series("cftc.cl.mm_short", "cftc").set_index("ts")["value"]
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
        (both["long"].iloc[-1], "long", f"{both['long'].iloc[-1]:,.0f}", ps.PALETTE[0]),
        (net.iloc[-1], "net", f"{net.iloc[-1]:+,.0f}".replace("-", ps.MINUS), ps.PALETTE[3]),
        (-both["short"].iloc[-1], "short", f"{both['short'].iloc[-1]:,.0f}", ps.PALETTE[2]),
    ):
        end_label(ax, x_last, y, name, value, colour)
    ps.date_axis(ax)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: f"{v:,.0f}".replace("-", ps.MINUS))
    )
    peak = net.idxmax()
    ps.frame(
        fig,
        title=positioning_finding(float(net.iloc[-1]) / 1000, float(net.max()) / 1000, peak),
        subtitle="Managed-money positioning in WTI crude futures: long above the axis, short "
        "below, net as the line. Bars, because the book is counted once a week and nothing is "
        "known in between",
        units="contracts",
        cadence="weekly",
        source="CFTC Commitments of Traders, disaggregated futures-only report "
        "(series cftc.cl.mm_long, cftc.cl.mm_short)",
        licence="Public domain",
        asof=last.date(),
        xlabel="Report week",
        ylabel="Managed-money positions (contracts; short below zero)",
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
        units="mb/d",
        cadence="monthly",
        source="U.S. EIA, movements of crude oil between PADDs "
        f"(latest month {wide.index.max():%B %Y})",
        licence="Public domain",
        asof=month_end(wide.index.max()),
        xlabel="Month",
        ylabel="Crude moved between PADDs (mb/d)",
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
        units="%",
        cadence="daily",
        source="GIE AGSI+ (series agsi.EU.full_pct)",
        asof=df["ts"].max().date(),
        xlabel="Month of the year",
        ylabel="EU gas storage, share of working capacity (%)",
        margins=MARGINS,
    )
    return fig


CHARTS: dict[str, Callable[[Lake], Figure]] = {
    "crude_stocks": crude_stocks,
    "crude_weekly_change": crude_weekly_change,
    "cftc_positioning": cftc_positioning,
    "interpadd_flows": interpadd_flows,
    "eu_gas_storage": eu_gas_storage,
}


def build_all(lake_root: Path, out: Path) -> list[Path]:
    """Draw every chart; write `<name>.pdf`, `<name>.png` and `<name>.tex` under `out`."""
    lake = Lake(lake_root)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with desk_rules():
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
