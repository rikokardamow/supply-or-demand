"""Exhibit specifications shared by the dashboard, the briefing, the motion page and the
Office exports. Each exhibit is a plain dict the page script and the PowerPoint builder
both render, so a chart, its slide and its worksheet rows cannot drift apart.

Every figure is read from a lake table named in the exhibit's `source` line. The only
arithmetic done here is unit scaling, differences of two lake series, and window means;
each is stated in the exhibit's `note`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Final

import pandas as pd
from core.seasonal import REFERENCE_YEAR

from . import tables

Exhibit = dict[str, Any]

HISTORY_START: Final = "2018-01-01"
# A daily series silent for longer than this has stopped and restarted, not paused.
SERIES_BREAK_DAYS: Final = 90

TABS: Final = [
    ("overview", "Overview"),
    ("us-oil", "US oil"),
    ("gas", "Gas"),
    ("prices", "Prices"),
    ("refining", "Refining"),
    ("positioning", "Positioning"),
    ("supply", "Supply"),
    ("flows", "Flows"),
    ("status", "Data status"),
]

BRIEFING_ORDER: Final = [
    "crude_stocks",
    "cushing",
    "gasoline_stocks",
    "distillate_stocks",
    "production_rigs",
    "eu_storage",
    "us_gas_storage",
    "brent_wti",
    "cracks",
    "positioning",
    "hormuz",
]

# Outputs that exist in the specs but hold nothing chartable. Listed on the status tab.
KNOWN_GAPS: Final = [
    ("AIS vessel positions", "Spec 11 not built; serving.vessel_latest is empty."),
    ("Geopolitical risk premium", "Spec 28 not built; serving.grp_* are empty."),
    ("Flights", "Spec 12 not built."),
    ("Manual physical differentials and OSPs", "Pipeline built, no files dropped yet."),
    ("Brent forward curve history", "One trade date only (manual Barchart drop)."),
    ("ENTSO-E power", "Three days of history; too short to chart."),
    ("Adanos and self-hosted sentiment", "Single-day snapshots; too short to chart."),
    ("Crack VECM", "One model card; the model fails out-of-sample (Theil U above 1)."),
]


@dataclass
class Book:
    """Everything one build produces: exhibits for the pages, tables for the workbook."""

    today: date
    exhibits: list[Exhibit] = field(default_factory=list)
    series_long: list[pd.DataFrame] = field(default_factory=list)
    seasonal: list[pd.DataFrame] = field(default_factory=list)
    sheets: dict[str, pd.DataFrame] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)


def day(ts: Any) -> str:
    stamp = pd.Timestamp(ts)
    return f"{stamp.day} {stamp:%b %Y}"


def _iso(ts: Any) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def _num(value: Any, digits: int = 3) -> float | None:
    return None if pd.isna(value) else round(float(value), digits)


def _values(series: pd.Series, digits: int = 3) -> list[float | None]:
    return [_num(v, digits) for v in series]


def _f(value: Any) -> float:
    return float(value)


def _fmt(value: float, digits: int) -> str:
    return f"{value:,.{digits}f}"


def _signed(value: float, digits: int) -> str:
    return f"{value:+,.{digits}f}"


def stale_flag(through: Any, cadence_days: int, today: date) -> str | None:
    """`No data since <date>` once the last observation is more than two release cycles old."""
    age = (pd.Timestamp(today) - pd.Timestamp(through)).days
    return f"No data since {day(through)}" if age > cadence_days * 2 else None


def _run(frame: pd.DataFrame) -> str | None:
    """The pipeline run that last wrote these rows (`ts_long.revision_date`)."""
    if "revision_date" not in frame or frame["revision_date"].isna().all():
        return None
    return _iso(pd.to_datetime(frame["revision_date"]).max())


def _source(provider: str, table: str, through: Any, run: str | None) -> str:
    stamp = f"pipeline run {day(run)}" if run else "pipeline run not recorded"
    return f"Source: {provider} · lake table {table} · data to {day(through)} · {stamp}"


def _track(name: str, frame: pd.DataFrame, unit: str, digits: int = 2) -> dict[str, Any]:
    return {
        "name": name,
        "unit": unit,
        "digits": digits,
        "x": [_iso(t) for t in frame["ts"]],
        "y": _values(frame["value"], digits + 1),
    }


def _turning_points(frame: pd.DataFrame, digits: int, axis: str = "y") -> list[dict[str, Any]]:
    """The window's high and low, labelled with their dates."""
    if len(frame) < 3:
        return []
    out = []
    for label, idx in (("High", frame["value"].idxmax()), ("Low", frame["value"].idxmin())):
        row = frame.loc[idx]
        out.append(
            {
                "x": _iso(row["ts"]),
                "y": _num(row["value"]),
                "axis": axis,
                "text": f"{label} {_fmt(_f(row['value']), digits)} · {day(row['ts'])}",
            }
        )
    return out


def _prior_value(frame: pd.DataFrame, days: int) -> float | None:
    cutoff = frame["ts"].iloc[-1] - pd.Timedelta(days=days)
    earlier = frame.loc[frame["ts"] <= cutoff, "value"]
    return float(earlier.iloc[-1]) if len(earlier) else None


def _reference_doy(ts: pd.Series) -> pd.Series:
    """Day of year in the non-leap reference year, 29 February folded into the 28th."""
    day_of_month = ts.dt.day.where(~((ts.dt.month == 2) & (ts.dt.day == 29)), 28)
    stamps = pd.to_datetime({"year": REFERENCE_YEAR, "month": ts.dt.month, "day": day_of_month})
    return stamps.dt.dayofyear


def _drawn(band: pd.DataFrame, series: pd.DataFrame, year: int, last_doy: int) -> pd.DataFrame:
    """The band as it is drawn. `core.seasonal` carries each report forward to the next,
    which plots a weekly series as a staircase. For the chart the year tracks keep only
    the days a report landed and the band one day a week, and the renderers join those
    points. No value is changed or invented; the workbook keeps the full daily table."""
    if pd.Timedelta(series["ts"].diff().median()) <= pd.Timedelta(days=2):
        return band
    drawn = band.copy()
    ends = drawn.index.isin([drawn.index[0], drawn.index[-1]])
    weekly = ((drawn["doy"] - last_doy) % 7 == 0) | ends
    drawn.loc[~weekly, ["band_min", "band_max", "median"]] = float("nan")
    for column, which in (("current", year), ("prior", year - 1)):
        reported = set(_reference_doy(series.loc[series["ts"].dt.year == which, "ts"]))
        drawn.loc[~drawn["doy"].isin(reported), column] = float("nan")
    return drawn


def seasonal_exhibit(
    book: Book,
    *,
    exhibit_id: str,
    tab: str,
    title: str,
    series_id: str,
    provider: str,
    source: str,
    unit: str,
    scale: float = 1.0,
    digits: int = 1,
    cadence_days: int = 7,
) -> None:
    raw = tables.read_series([series_id])
    series = raw[["ts", "value", "unit", "revision_date"]]
    if series.empty:
        book.issues.append(f"{title}: series {series_id} is missing from the lake.")
        return
    band = tables.seasonal_table(series, series_id)
    if band.empty or band["current"].isna().all() or band["median"].isna().all():
        book.issues.append(f"{title}: {series_id} has too little history for a seasonal band.")
        return
    book.seasonal.append(band)
    book.series_long.append(raw[raw["ts"] >= HISTORY_START])

    latest_ts = series["ts"].iloc[-1]
    year = latest_ts.year
    latest = float(series["value"].iloc[-1]) * scale
    prior = _prior_value(series, 7)
    change = None if prior is None else latest - prior * scale
    at_doy = band.loc[band["current"].notna()].iloc[-1]
    drawn = _drawn(band, series, year, int(at_doy["doy"]))
    median = float(at_doy["median"]) * scale
    low, high = float(at_doy["band_min"]) * scale, float(at_doy["band_max"]) * scale
    # A share is compared in percentage points; a percentage of a percentage misleads.
    is_share = unit.startswith("%")
    vs_median = latest - median if is_share else (latest / median - 1.0) * 100.0
    vs_text = f"{_signed(vs_median, 1)}{' pts' if is_share else '%'}"
    if latest > high:
        position = "above"
    elif latest < low:
        position = "below"
    else:
        position = "inside"
    n_years = int(band["years"].iloc[0])
    first_year = year - tables.BAND_YEARS
    window = f"{first_year}–{year - 1}" + (" ex-2020" if first_year <= 2020 <= year - 1 else "")

    x = [
        _iso(pd.Timestamp(year=REFERENCE_YEAR, month=1, day=1) + pd.Timedelta(days=int(d) - 1))
        for d in band["doy"]
    ]
    this_year = series[series["ts"].dt.year == year].assign(value=lambda d: d["value"] * scale)
    annotations = [
        {
            "x": x[list(band["doy"]).index(at_doy["doy"])],
            "y": _num(latest),
            "axis": "y",
            "text": f"Latest {_fmt(latest, digits)} · {vs_text} vs median",
            "latest": True,
        }
    ]
    for point in _turning_points(this_year, digits):
        if point["y"] != _num(latest):
            stamp = pd.Timestamp(point["x"])
            leap_day = stamp.month == 2 and stamp.day == 29
            point["x"] = _iso(stamp.replace(year=REFERENCE_YEAR, day=28 if leap_day else stamp.day))
            annotations.append(point)

    change_text = "" if change is None else f", {_signed(change, digits)} on the week"
    book.exhibits.append(
        {
            "id": exhibit_id,
            "tab": tab,
            "title": title,
            "kind": "seasonal",
            "unit": unit,
            "digits": digits,
            "year": year,
            "band_label": f"{n_years}-year range ({window})",
            "x": x,
            "band_min": _values(drawn["band_min"] * scale),
            "band_max": _values(drawn["band_max"] * scale),
            "median": _values(drawn["median"] * scale),
            "prior": _values(drawn["prior"] * scale),
            "current": _values(drawn["current"] * scale),
            "annotations": annotations,
            "takeaway": [
                f"{_fmt(latest, digits)} {unit} on {day(latest_ts)}{change_text}.",
                f"{vs_text} against the {n_years}-year median and {position} the {window} range.",
            ],
            "stat": {
                "label": title,
                "value": _fmt(latest, digits),
                "unit": unit,
                "delta": None if change is None else _signed(change, digits),
                "delta_label": "on the week",
                "date": day(latest_ts),
            },
            "source": _source(provider, f"ts_long/{source} ({series_id})", latest_ts, _run(raw)),
            "note": (f"Lake unit {series['unit'].iloc[-1]} × {scale:g}. " if scale != 1.0 else "")
            + "Band from core.seasonal. Lines join the reports themselves; the band is sampled "
            "once a week.",
            "gap": stale_flag(latest_ts, cadence_days, book.today),
            "sheets": ["seasonal", "series_long"],
        }
    )


def pair_exhibit(
    book: Book,
    *,
    exhibit_id: str,
    tab: str,
    title: str,
    kind: str,
    tracks: list[tuple[str, pd.DataFrame, str, int]],
    provider: str,
    table: str,
    run: str | None,
    note: str,
    cadence_days: int,
    forward_dated: bool = False,
) -> None:
    """A one- or two-series chart: `dual` when the units differ, `lines` when they share one.

    The exhibit is only as fresh as its oldest series, so that one sets the stale flag and
    the source line's date. A `forward_dated` series (forecast or scenario quarters) says
    nothing about freshness through its last timestamp; its pipeline run is judged instead.
    """
    tracks = [t for t in tracks if not t[1].empty]
    if not tracks:
        book.issues.append(f"{title}: no rows in the lake for this exhibit.")
        return
    through = min(t[1]["ts"].iloc[-1] for t in tracks)
    if not forward_dated:
        gap = stale_flag(through, cadence_days, book.today)
    elif run is None:
        gap = "No pipeline run recorded"
    else:
        gap = stale_flag(run, cadence_days, book.today)
    lines = []
    for name, frame, unit, digits in tracks:
        last = frame.iloc[-1]
        lines.append(f"{name} {_fmt(float(last['value']), digits)} {unit} on {day(last['ts'])}")
    lead_name, lead, lead_unit, lead_digits = tracks[0]
    first, last_value = float(lead["value"].iloc[0]), float(lead["value"].iloc[-1])
    peak = lead.loc[lead["value"].idxmax()]
    book.exhibits.append(
        {
            "id": exhibit_id,
            "tab": tab,
            "title": title,
            "kind": kind,
            "series": [_track(n, f, u, d) for n, f, u, d in tracks],
            "annotations": _turning_points(lead, lead_digits),
            "takeaway": [
                "; ".join(lines) + ".",
                f"{lead_name} {_signed(last_value - first, lead_digits)} {lead_unit} since "
                f"{day(lead['ts'].iloc[0])}; window high {_fmt(_f(peak['value']), lead_digits)} "
                f"on {day(peak['ts'])}.",
            ],
            "stat": {
                "label": lead_name,
                "value": _fmt(last_value, lead_digits),
                "unit": lead_unit,
                "delta": None,
                "delta_label": "",
                "date": day(lead["ts"].iloc[-1]),
            },
            "source": _source(provider, table, through, run),
            "note": note,
            "gap": gap,
            "sheets": ["series_long"],
        }
    )


def bars_exhibit(
    book: Book,
    *,
    exhibit_id: str,
    tab: str,
    title: str,
    frame: pd.DataFrame,
    category: str,
    value: str,
    compare: str,
    unit: str,
    value_name: str,
    compare_name: str,
    provider: str,
    table: str,
    sheet: str,
    run: str | None,
    note: str,
    cadence_days: int,
    digits: int = 1,
) -> None:
    if frame.empty:
        book.issues.append(f"{title}: no rows in the lake for this exhibit.")
        return
    through = frame["through"].max()
    # A row that stopped reporting is not "latest": ranked beside live rows it would hide
    # its own gap, so it is left out of the chart and listed instead.
    dead = frame["through"] < through - pd.Timedelta(days=cadence_days * 2)
    if dead.any():
        names = ", ".join(
            f"{row[category]} (to {day(row['through'])})" for _, row in frame[dead].iterrows()
        )
        book.issues.append(f"{title}: left out, no data in the latest window: {names}.")
        frame = frame[~dead].reset_index(drop=True)
    top, bottom = frame.iloc[0], frame.iloc[-1]
    movers = frame.dropna(subset=[compare]).assign(delta=lambda d: d[value] - d[compare])
    second = "No year-ago comparison available."
    if not movers.empty:
        up = movers.loc[movers["delta"].idxmax()]
        down = movers.loc[movers["delta"].idxmin()]
        second = (
            f"Largest rise on the year {up[category]} ({_signed(_f(up['delta']), digits)}); "
            f"largest fall {down[category]} ({_signed(_f(down['delta']), digits)})."
        )
    book.exhibits.append(
        {
            "id": exhibit_id,
            "tab": tab,
            "title": title,
            "kind": "bars",
            "unit": unit,
            "digits": digits,
            "categories": [str(c) for c in frame[category]],
            "values": _values(frame[value]),
            "compare": _values(frame[compare]),
            "value_name": value_name,
            "compare_name": compare_name,
            "annotations": [],
            "takeaway": [
                f"Highest {top[category]} at {_fmt(float(top[value]), digits)} {unit}; lowest "
                f"{bottom[category]} at {_fmt(float(bottom[value]), digits)} {unit}.",
                second,
            ],
            "source": _source(provider, table, through, run),
            "note": note,
            "gap": stale_flag(through, cadence_days, book.today),
            "sheets": [sheet],
        }
    )


def _window(frame: pd.DataFrame, series_id: str, start: str, scale: float = 1.0) -> pd.DataFrame:
    out = frame.loc[
        (frame["series_id"] == series_id) & (frame["ts"] >= start), ["ts", "value"]
    ].copy()
    out["value"] = out["value"] * scale
    return out.reset_index(drop=True)


def _mtime(dataset: str, source: str) -> str | None:
    stamp: datetime | None = tables.pulled_at(dataset, source)
    return None if stamp is None else _iso(stamp)


def _us_oil(book: Book) -> None:
    stocks = [
        ("crude_stocks", "US crude stocks excluding SPR", "WCESTUS1"),
        ("cushing", "Crude stocks at Cushing, Oklahoma", "W_EPC0_SAX_YCUOK_MBBL"),
        ("gasoline_stocks", "US total motor gasoline stocks", "WGTSTUS1"),
        ("distillate_stocks", "US distillate fuel oil stocks", "WDISTUS1"),
    ]
    for exhibit_id, title, series_id in stocks:
        seasonal_exhibit(
            book,
            exhibit_id=exhibit_id,
            tab="us-oil",
            title=title,
            series_id=series_id,
            provider="EIA Weekly Petroleum Status Report",
            source="eia",
            unit="million barrels",
            scale=0.001,
        )
    weekly = tables.read_series(["WCRFPUS2", "bh.rigs.united_states.oil"], start="2024-01-01")
    book.series_long.append(weekly)
    pair_exhibit(
        book,
        exhibit_id="production_rigs",
        tab="us-oil",
        title="US crude production against the oil rig count",
        kind="dual",
        tracks=[
            ("Crude production", _window(weekly, "WCRFPUS2", "2024-01-01", 0.001), "mb/d", 2),
            ("Oil rigs", _window(weekly, "bh.rigs.united_states.oil", "2024-01-01"), "rigs", 0),
        ],
        provider="EIA WPSR; Baker Hughes rig count",
        table="ts_long/eia (WCRFPUS2), ts_long/baker_hughes (bh.rigs.united_states.oil)",
        run=_run(weekly),
        note="Production: lake unit MBBL/D × 0.001.",
        cadence_days=7,
    )


def _gas(book: Book) -> None:
    seasonal_exhibit(
        book,
        exhibit_id="eu_storage",
        tab="gas",
        title="EU gas storage, share of capacity filled",
        series_id="agsi.EU.full_pct",
        provider="GIE AGSI+",
        source="gie",
        unit="% full",
        cadence_days=2,
    )
    seasonal_exhibit(
        book,
        exhibit_id="us_gas_storage",
        tab="gas",
        title="US Lower 48 working gas in storage",
        series_id="NW2_EPG0_SWO_R48_BCF",
        provider="EIA Weekly Natural Gas Storage Report",
        source="eia",
        unit="Bcf",
        digits=0,
    )
    countries = tables.storage_by_country()
    countries = countries[countries["geo"] != "EU"].reset_index(drop=True)
    book.sheets["storage_by_country"] = countries
    bars_exhibit(
        book,
        exhibit_id="eu_storage_countries",
        tab="gas",
        title="Gas storage fullness by country",
        frame=countries,
        category="geo",
        value="full_pct",
        compare="year_ago_pct",
        unit="% full",
        value_name="Latest",
        compare_name="A year earlier",
        provider="GIE AGSI+",
        table="ts_long/gie (agsi.<country>.full_pct)",
        sheet="storage_by_country",
        run=_mtime("ts_long", "gie"),
        note="Year-earlier value is the observation 364 days before, within 3 days.",
        cadence_days=2,
    )


def _prices(book: Book) -> None:
    prices = tables.read_series(["fut.lco.f01.close", "fut.cl.f01.close"], start="2024-01-01")
    book.series_long.append(prices)
    brent = _window(prices, "fut.lco.f01.close", "2024-01-01")
    wti = _window(prices, "fut.cl.f01.close", "2024-01-01")
    spread = brent.merge(wti, on="ts", suffixes=("", "_wti"))
    spread["value"] = spread["value"] - spread["value_wti"]
    pair_exhibit(
        book,
        exhibit_id="brent_wti",
        tab="prices",
        title="Brent front month and the Brent–WTI spread",
        kind="dual",
        tracks=[
            ("Brent front month", brent, "USD/bbl", 2),
            ("Brent minus WTI", spread.loc[:, ["ts", "value"]], "USD/bbl", 2),
        ],
        provider="Yahoo Finance front-month closes",
        table="ts_long/yfinance (fut.lco.f01.close, fut.cl.f01.close)",
        run=_run(prices),
        note="Spread = Brent close minus WTI close on days both traded.",
        cadence_days=4,
    )

    curve = tables.brent_curve()
    book.sheets["curve_settles"] = curve
    if curve.empty:
        book.issues.append("Brent forward curve: no manual curve drop in the lake.")
    else:
        trade_date = curve["trade_date"].iloc[0]
        shape = curve.rename(columns={"delivery": "ts", "settle": "value"}).loc[:, ["ts", "value"]]
        front, back = shape.iloc[0], shape.iloc[min(12, len(shape) - 1)]
        slope = float(front["value"]) - float(back["value"])
        far = f"{pd.Timestamp(back['ts']):%b %Y}"
        book.exhibits.append(
            {
                "id": "brent_curve",
                "tab": "prices",
                "title": f"Brent forward curve, settles of {day(trade_date)}",
                "kind": "lines",
                "series": [_track("Brent settle", shape, "USD/bbl", 2)],
                "annotations": [],
                "x_title": "Delivery month",
                "takeaway": [
                    f"Front contract {_fmt(float(front['value']), 2)} USD/bbl; "
                    f"{far} delivery {_fmt(float(back['value']), 2)} USD/bbl.",
                    f"Front minus {far}: {_signed(slope, 2)} USD/bbl "
                    f"({'backwardation' if slope > 0 else 'contango'}). One trade date only.",
                ],
                "source": _source(
                    "Barchart spreads export (manual drop)",
                    "ts_long/manual (fut.lco.<contract>.settle)",
                    trade_date,
                    _mtime("ts_long", "manual"),
                ),
                "note": "A single trade date; the lake has no curve history to compare against.",
                "gap": stale_flag(trade_date, 2, book.today),
                "sheets": ["curve_settles"],
            }
        )

    series_id = "derived.spread.cl.s12"
    stored = tables.read_series([series_id], start="2021-01-01")
    book.series_long.append(stored)
    spread = _window(stored, series_id, "2021-01-01")
    # The id holds two measures: EIA's rank-based settlements to 5 Apr 2024, then the
    # contract panel's closes. Joining them draws a move that never happened, so only
    # the run after the last long break is charted.
    breaks = spread.index[spread["ts"].diff() > pd.Timedelta(days=SERIES_BREAK_DAYS)]
    if len(breaks):
        before = spread.loc[: breaks[-1] - 1, "ts"].iloc[-1]
        spread = spread.loc[breaks[-1] :].reset_index(drop=True)
        provider = "Futures closes, contract panel (pipelines.derived.curve)"
        note = (
            f"Shown from {day(spread['ts'].iloc[0])}. The same series id holds EIA's rank-based "
            f"spread to {day(before)}, a different measure, which is not joined to this one. "
            "Legs are daily closes, not exchange settlements."
        )
    else:
        provider = "EIA NYMEX futures ranks 1–4 (route discontinued by EIA)"
        note = "EIA stopped publishing this route on 5 Apr 2024."
    pair_exhibit(
        book,
        exhibit_id="wti_prompt_spread",
        tab="prices",
        title="WTI prompt spread, first minus second month",
        kind="lines",
        tracks=[("WTI M1–M2", spread, "USD/bbl", 2)],
        provider=provider,
        table=f"ts_long/derived ({series_id})",
        run=_run(stored),
        note=note,
        cadence_days=4,
    )


def _refining(book: Book) -> None:
    us, gulf = "derived.crack.us321.spot", "derived.crack.gulf321.spot"
    cracks = tables.read_series([us, gulf], start="2024-01-01")
    book.series_long.append(cracks)
    pair_exhibit(
        book,
        exhibit_id="cracks",
        tab="refining",
        title="3-2-1 crack spreads, spot",
        kind="lines",
        tracks=[
            ("US 3-2-1", _window(cracks, us, "2024-01-01"), "USD/bbl", 2),
            ("Gulf Coast 3-2-1", _window(cracks, gulf, "2024-01-01"), "USD/bbl", 2),
        ],
        provider="FRED spot legs, combined by pipelines.derived.cracks",
        table=f"ts_long/derived ({us}, {gulf})",
        run=_run(cracks),
        note="Spot legs, not futures; see Spec 20.",
        cadence_days=7,
    )
    seasonal_exhibit(
        book,
        exhibit_id="refinery_inputs",
        tab="refining",
        title="US gross inputs to refineries",
        series_id="WGIRIUS2",
        provider="EIA Weekly Petroleum Status Report",
        source="eia",
        unit="mb/d",
        scale=0.001,
        digits=2,
    )


def _positioning(book: Book) -> None:
    cot = tables.read_series(["cftc.cl.mm_long", "cftc.cl.mm_short"], start="2023-01-01")
    book.series_long.append(cot)
    net = _window(cot, "cftc.cl.mm_long", "2023-01-01").merge(
        _window(cot, "cftc.cl.mm_short", "2023-01-01"), on="ts", suffixes=("", "_short")
    )
    net["value"] = (net["value"] - net["value_short"]) / 1000.0
    wti = tables.read_series(["fut.cl.f01.close"], start="2023-01-01")
    pair_exhibit(
        book,
        exhibit_id="positioning",
        tab="positioning",
        title="Managed-money net length in WTI against the price",
        kind="dual",
        tracks=[
            ("Managed-money net long", net.loc[:, ["ts", "value"]], "thousand contracts", 1),
            ("WTI front month", _window(wti, "fut.cl.f01.close", "2023-01-01"), "USD/bbl", 2),
        ],
        provider="CFTC Commitments of Traders; Yahoo Finance",
        table="ts_long/cftc (cftc.cl.mm_long, cftc.cl.mm_short), ts_long/yfinance",
        run=_run(cot),
        note="Net long = mm_long minus mm_short, contracts ÷ 1,000.",
        cadence_days=7,
    )


def _supply(book: Book) -> None:
    call_id = "momr.demand_balance.memo_items.a_b.quarterly"
    doc_id = "momr.demand_balance.nondoc_liquids_production.doc_crude_oil_production.quarterly"
    momr = tables.read_series([call_id, doc_id])
    book.series_long.append(momr)
    pair_exhibit(
        book,
        exhibit_id="opec_call",
        tab="supply",
        title="Call on DoC crude against DoC crude production",
        kind="lines",
        tracks=[
            ("Call on DoC crude (a − b)", _window(momr, call_id, "2025-01-01"), "mb/d", 2),
            ("DoC crude production", _window(momr, doc_id, "2025-01-01"), "mb/d", 2),
        ],
        provider="OPEC Monthly Oil Market Report, Table 10-1",
        table="ts_long/opec_momr (momr.demand_balance.*.quarterly)",
        run=_run(momr),
        note="Quarterly, dated at quarter start; forecast quarters included as OPEC publishes "
        "them. Latest vintage in the lake is the August 2026 report.",
        cadence_days=31,
        forward_dated=True,
    )

    share_id = "derived.hormuz.scenario.open_share"
    scenario = tables.read_prefix("derived.hormuz.scenario.", "derived")
    book.series_long.append(scenario)
    gulf = _window(scenario, "derived.hormuz.scenario.gulf_total.supply", "2000-01-01")
    share = _window(scenario, share_id, "2000-01-01", 100.0)
    pair_exhibit(
        book,
        exhibit_id="hormuz",
        tab="supply",
        title="Hormuz closure scenario: Gulf supply and the share of the strait open",
        kind="dual",
        tracks=[("Gulf supply", gulf, "mb/d", 2), ("Strait open", share, "% open", 0)],
        provider="Scenario model, pipelines.derived.hormuz (assumption-driven, not observed)",
        table="ts_long/derived (derived.hormuz.scenario.*)",
        run=_run(scenario),
        note="A scenario, not a forecast; quarters dated at quarter start. "
        "open_share is stored as a fraction and shown × 100.",
        cadence_days=120,
        forward_dated=True,
    )
    stored = scenario.loc[scenario["series_id"] == share_id]
    if not stored.empty and stored["unit"].iloc[0] == "%" and float(stored["value"].max()) <= 1.0:
        book.issues.append(
            f"{share_id} carries unit '%' but holds fractions (0 to 1). "
            "Shown × 100 here; the lake rows are unchanged."
        )


def _flows(book: Book) -> None:
    gas_flows = tables.flows_compare("entsog", "pipeline", 7)
    padd_flows = tables.flows_compare("eia", "pipeline", 1)
    book.sheets["flows"] = pd.concat([gas_flows, padd_flows], ignore_index=True)
    bars_exhibit(
        book,
        exhibit_id="entsog_flows",
        tab="flows",
        title="European gas import corridors, 7-day mean",
        frame=gas_flows,
        category="corridor",
        value="latest",
        compare="year_ago",
        unit="GWh/d",
        value_name="Latest 7 days",
        compare_name="Same 7 days a year earlier",
        provider="ENTSOG Transparency Platform, physical flows",
        table="flows/entsog (mode = pipeline)",
        sheet="flows",
        run=_mtime("flows", "entsog"),
        note="Interconnection points feeding one corridor are summed, then averaged over 7 days.",
        cadence_days=2,
        digits=0,
    )
    bars_exhibit(
        book,
        exhibit_id="padd_flows",
        tab="flows",
        title="Inter-PADD crude movements by pipeline, latest month",
        frame=padd_flows,
        category="corridor",
        value="latest",
        compare="year_ago",
        unit="thousand barrels",
        value_name="Latest month",
        compare_name="Same month a year earlier",
        provider="EIA petroleum movements",
        table="flows/eia (mode = pipeline)",
        sheet="flows",
        run=_mtime("flows", "eia"),
        note="Monthly totals in the lake's own unit (MBBL).",
        cadence_days=45,
        digits=0,
    )


def build(today: date) -> Book:
    book = Book(today=today)
    for section in (_us_oil, _gas, _prices, _refining, _positioning, _supply, _flows):
        section(book)
    book.sheets["wpsr_lines"] = tables.wpsr_lines()
    book.sheets["freshness"] = tables.freshness()
    return book
