"""Excel and PowerPoint exports, built from the same `Book` and briefing payload as the
pages.

The workbook holds one sheet per serving-shaped table plus a README sheet; cells carry
real dates and numbers with Excel formats, and nothing is merged. The deck holds one
exhibit per slide with native, editable PowerPoint charts. Two PowerPoint limits shape
it: a chart has one plot type, so a seasonal band is drawn as its minimum and maximum
lines rather than a filled area; and python-pptx has no secondary axis, so a dual-axis
exhibit becomes two stacked charts sharing a date axis.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Final

import pandas as pd
from core import design
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from pptx import Presentation
from pptx.chart.chart import Chart
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.slide import Slide
from pptx.util import Inches, Pt

from .exhibits import Book, Exhibit

WORKBOOK_NAME: Final = "kardamow_data.xlsx"
DECK_NAME: Final = "kardamow_briefing.pptx"
MAX_CHART_POINTS: Final = 160

DATE_FORMAT: Final = "yyyy-mm-dd"
DATETIME_FORMAT: Final = "yyyy-mm-dd hh:mm"
NUMBER_FORMAT: Final = "#,##0.00"
INTEGER_FORMAT: Final = "#,##0"

SHEET_NOTES: Final[dict[str, tuple[str, str, str]]] = {
    "series_long": (
        "Scalar series behind the charts, lake ts_long schema, from 2018 or the chart window",
        "ts_long (all sources used)",
        "per row, column unit",
    ),
    "seasonal": (
        "5-year min, max and median by day of year, with current and prior year",
        "ts_long via core.seasonal",
        "per row, column unit",
    ),
    "wpsr_lines": (
        "Weekly Petroleum Status Report at a glance, latest week",
        "ts_long/eia via pipelines.eia.wpsr_lines",
        "per row, column unit; wow absolute, yoy and vs_median in %",
    ),
    "curve_settles": (
        "Brent forward curve, latest manual drop",
        "ts_long/manual",
        "USD/bbl",
    ),
    "flows": (
        "Corridor means: latest window against one year earlier",
        "flows/entsog, flows/eia",
        "per row, column unit",
    ),
    "storage_by_country": (
        "Gas storage fullness by country, latest against a year earlier",
        "ts_long/gie",
        "% of working gas volume",
    ),
    "freshness": (
        "Last observation and pipeline run per source",
        "core.freshness.staleness_report",
        "days",
    ),
}


def _rgb(hex_colour: str) -> RGBColor:
    colour: RGBColor = RGBColor.from_string(hex_colour.lstrip("#").upper())
    return colour


NAVY: Final = _rgb(design.NAVY)
LIGHT_BLUE: Final = _rgb(design.LIGHT_BLUE)
ORANGE: Final = _rgb(design.ORANGE)
GREY: Final = _rgb(design.GREY)
RED: Final = _rgb(design.RED)
TEXT: Final = _rgb(design.TEXT)
MUTED: Final = _rgb(design.MUTED)
GRID: Final = _rgb(design.GRID)


# -- Excel ---------------------------------------------------------------------------


def _cell(value: Any) -> Any:
    """A value Excel can store natively: naive datetimes, plain numbers, or None."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.tz_localize(None).to_pydatetime() if value.tzinfo else value.to_pydatetime()
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, (date, str, bool, int, float)):
        return value
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def _format(value: Any) -> str | None:
    if isinstance(value, datetime):
        midnight = value.hour == 0 and value.minute == 0 and value.second == 0
        return DATE_FORMAT if midnight else DATETIME_FORMAT
    if isinstance(value, date):
        return DATE_FORMAT
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return INTEGER_FORMAT
    if isinstance(value, float):
        return NUMBER_FORMAT
    return None


def _write_sheet(sheet: Worksheet, frame: pd.DataFrame) -> None:
    sheet.append([str(c) for c in frame.columns])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in frame.itertuples(index=False, name=None):
        values = [_cell(v) for v in row]
        sheet.append(values)
        for column, value in enumerate(values, start=1):
            number_format = _format(value)
            if number_format:
                sheet.cell(row=sheet.max_row, column=column).number_format = number_format
    sheet.freeze_panes = "A2"
    for index, name in enumerate(frame.columns, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = max(
            12, min(48, len(str(name)) + 6)
        )


def workbook_tables(book: Book) -> dict[str, pd.DataFrame]:
    series = pd.concat(book.series_long, ignore_index=True).drop_duplicates(
        subset=["series_id", "ts"], keep="last"
    )
    tables = {
        "series_long": series.sort_values(["series_id", "ts"]).reset_index(drop=True),
        "seasonal": pd.concat(book.seasonal, ignore_index=True),
    }
    for name in ("wpsr_lines", "curve_settles", "flows", "storage_by_country", "freshness"):
        tables[name] = book.sheets[name]
    return tables


def _through(frame: pd.DataFrame) -> Any:
    for column in ("ts", "week_ending", "trade_date", "through", "last_seen"):
        if column in frame and len(frame):
            return _cell(pd.to_datetime(frame[column]).max())
    return None


def _run(frame: pd.DataFrame) -> Any:
    for column in ("revision_date", "pulled_at"):
        if column in frame and frame[column].notna().any():
            return _cell(pd.to_datetime(frame[column]).max())
    return None


def write_workbook(book: Book, meta: dict[str, Any], out_dir: Path) -> Path:
    tables = workbook_tables(book)
    workbook = Workbook()
    readme = workbook.active
    assert readme is not None
    readme.title = "README"
    for line in (
        ["Kardamow data workbook"],
        ["Built", meta["built_at"]],
        ["Newest pipeline run in these tables", meta["newest_run"]],
        ["Oldest source in these tables", meta["oldest_run"]],
        ["Stale exhibits at build", f"{meta['stale']} of {meta['exhibits']}"],
        ["Every figure is read from the local lake (data/lake). Nothing is fetched at build time."],
        [],
    ):
        readme.append(line)
    readme["A1"].font = Font(bold=True, size=14)
    header_row = readme.max_row + 1
    readme.append(["Sheet", "Contents", "Lake source", "Units", "Rows", "Data through", "As-of"])
    for cell in readme[header_row]:
        cell.font = Font(bold=True)
    for name, frame in tables.items():
        contents, source, units = SHEET_NOTES[name]
        readme.append([name, contents, source, units, len(frame), _through(frame), _run(frame)])
        for column in (6, 7):
            cell = readme.cell(row=readme.max_row, column=column)
            if cell.value is not None:
                cell.number_format = _format(cell.value) or DATE_FORMAT
    for index, width in enumerate((22, 70, 40, 44, 10, 16, 18), start=1):
        readme.column_dimensions[get_column_letter(index)].width = width

    for name, frame in tables.items():
        _write_sheet(workbook.create_sheet(name), frame)

    path = out_dir / WORKBOOK_NAME
    workbook.save(path)
    return path


# -- PowerPoint ----------------------------------------------------------------------


def _thin(count: int) -> list[int]:
    """Indices that keep at most `MAX_CHART_POINTS` points, always including the last."""
    step = max(1, -(-count // MAX_CHART_POINTS))
    keep = list(range(0, count, step))
    if keep and keep[-1] != count - 1:
        keep.append(count - 1)
    return keep


def _text(
    slide: Slide,
    lines: list[str],
    top: float,
    height: float,
    *,
    size: int,
    colour: RGBColor = TEXT,
    bold: bool = False,
    font: str = "Segoe UI",
) -> None:
    box = slide.shapes.add_textbox(Inches(0.6), Inches(top), Inches(12.1), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    for index, line in enumerate(lines):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        run = paragraph.add_run()
        run.text = line
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.name = font
        run.font.color.rgb = colour


def _style(chart: Chart, colours: list[RGBColor], widths: list[float], date_format: str) -> None:
    chart.font.size = Pt(11)
    chart.font.name = "Segoe UI"
    chart.font.color.rgb = TEXT
    chart.has_legend = len(colours) > 1
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False
    chart.value_axis.major_gridlines.format.line.color.rgb = GRID
    chart.value_axis.format.line.fill.background()
    chart.category_axis.format.line.color.rgb = GRID
    chart.category_axis.tick_labels.number_format = date_format
    chart.category_axis.tick_labels.number_format_is_linked = False
    for series, colour, width in zip(chart.plots[0].series, colours, widths, strict=True):
        series.smooth = False
        series.format.line.color.rgb = colour
        series.format.line.width = Pt(width)


def _line_chart(
    slide: Slide,
    top: float,
    height: float,
    categories: list[date],
    series: list[tuple[str, list[float | None]]],
    colours: list[RGBColor],
    widths: list[float],
    date_format: str,
) -> Chart:
    data = CategoryChartData()
    data.categories = categories
    for name, values in series:
        data.add_series(name, values)
    frame = slide.shapes.add_chart(
        XL_CHART_TYPE.LINE,
        Inches(0.6),
        Inches(top),
        Inches(12.1),
        Inches(height),
        data,  # type: ignore[arg-type]
    )
    chart: Chart = frame.chart  # type: ignore[attr-defined]
    _style(chart, colours, widths, date_format)
    return chart


def _dates(values: list[str], keep: list[int]) -> list[date]:
    return [date.fromisoformat(values[i]) for i in keep]


def _seasonal(slide: Slide, exhibit: Exhibit, top: float, height: float) -> None:
    keep = list(range(0, len(exhibit["x"]), 7))

    def pick(key: str) -> list[float | None]:
        return [exhibit[key][i] for i in keep]

    chart = _line_chart(
        slide,
        top,
        height,
        _dates(exhibit["x"], keep),
        [
            ("Range low", pick("band_min")),
            ("Range high", pick("band_max")),
            ("Median", pick("median")),
            (str(exhibit["year"] - 1), pick("prior")),
            (str(exhibit["year"]), pick("current")),
        ],
        [GREY, GREY, ORANGE, LIGHT_BLUE, NAVY],
        [1.0, 1.0, 1.5, 1.5, 2.75],
        "mmm",
    )
    chart.plots[0].series[2].format.line.dash_style = MSO_LINE_DASH_STYLE.ROUND_DOT


def _aligned(tracks: list[dict[str, Any]]) -> tuple[list[date], list[list[float | None]]]:
    """Series on different date grids, put on their shared sorted calendar."""
    calendar = sorted({x for t in tracks for x in t["x"]})
    keep = _thin(len(calendar))
    columns = []
    for track in tracks:
        lookup = dict(zip(track["x"], track["y"], strict=True))
        columns.append([lookup.get(calendar[i]) for i in keep])
    return _dates(calendar, keep), columns


def _lines(slide: Slide, exhibit: Exhibit, top: float, height: float) -> None:
    tracks = exhibit["series"]
    categories, columns = _aligned(tracks)
    palette = [NAVY, LIGHT_BLUE, GREY]
    _line_chart(
        slide,
        top,
        height,
        categories,
        [(f"{t['name']}, {t['unit']}", c) for t, c in zip(tracks, columns, strict=True)],
        [palette[i % 3] for i in range(len(tracks))],
        [2.25] + [1.75] * (len(tracks) - 1),
        "mmm yy",
    )


def _dual(slide: Slide, exhibit: Exhibit, top: float, height: float) -> None:
    half = height / len(exhibit["series"])
    for index, track in enumerate(exhibit["series"]):
        categories, columns = _aligned([track])
        chart = _line_chart(
            slide,
            top + index * half,
            half,
            categories,
            [(f"{track['name']}, {track['unit']}", columns[0])],
            [NAVY if index == 0 else LIGHT_BLUE],
            [2.25],
            "mmm yy",
        )
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False


def _bars(slide: Slide, exhibit: Exhibit, top: float, height: float) -> None:
    data = CategoryChartData()
    data.categories = list(reversed(exhibit["categories"]))
    data.add_series(exhibit["compare_name"], list(reversed(exhibit["compare"])))
    data.add_series(exhibit["value_name"], list(reversed(exhibit["values"])))
    frame = slide.shapes.add_chart(
        XL_CHART_TYPE.BAR_CLUSTERED,
        Inches(0.6),
        Inches(top),
        Inches(12.1),
        Inches(height),
        data,  # type: ignore[arg-type]
    )
    chart: Chart = frame.chart  # type: ignore[attr-defined]
    chart.font.size = Pt(11)
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.TOP
    chart.legend.include_in_layout = False
    for series, colour in zip(chart.plots[0].series, (LIGHT_BLUE, NAVY), strict=True):
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = colour


_CHARTS: Final = {"seasonal": _seasonal, "lines": _lines, "dual": _dual, "bars": _bars}


def write_deck(briefing: dict[str, Any], out_dir: Path) -> Path:
    deck = Presentation()
    deck.slide_width = Inches(13.333)
    deck.slide_height = Inches(7.5)
    blank = deck.slide_layouts[6]
    meta = briefing["meta"]

    cover = deck.slides.add_slide(blank)
    _text(
        cover, ["Energy desk briefing"], 2.6, 1.0, size=40, colour=NAVY, bold=True, font="Georgia"
    )
    _text(
        cover,
        [
            f"Pipeline as-of {meta['newest_run']} · oldest source {meta['oldest_run']}",
            f"Built {meta['built_at']} · {meta['stale']} of {meta['exhibits']} exhibits stale",
            "Every figure is read from the local lake; chart data is embedded in each slide.",
        ],
        3.7,
        1.4,
        size=14,
        colour=MUTED,
    )

    for exhibit in briefing["slides"]:
        slide = deck.slides.add_slide(blank)
        _text(slide, [exhibit["title"]], 0.35, 0.7, size=26, colour=NAVY, bold=True, font="Georgia")
        _text(slide, exhibit["takeaway"], 1.05, 0.8, size=14)
        if exhibit["gap"]:
            _text(slide, [exhibit["gap"].upper()], 1.85, 0.3, size=11, colour=RED, bold=True)
        _CHARTS[exhibit["kind"]](slide, exhibit, 2.15, 4.55)
        note = f" · {exhibit['note']}" if exhibit["note"] else ""
        _text(slide, [exhibit["source"] + note], 6.75, 0.6, size=10, colour=MUTED)

    path = out_dir / DECK_NAME
    deck.save(str(path))
    return path
