"""The README charts from a small synthetic lake: paper format, captions, byte-stable."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from apps.exhibits import readme_charts
from core import paper_style as ps


def _write(root: Path, rel: str, df: pd.DataFrame) -> None:
    path = root / rel
    path.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path / "part.parquet", index=False)


def _series(
    series_id: str, start: str, end: str, freq: str, base: float, amp: float
) -> pd.DataFrame:
    ts = pd.date_range(start, end, freq=freq)
    doy = ts.day_of_year.to_numpy()
    value = base + amp * np.sin(doy / 365 * 2 * np.pi) + 0.01 * np.arange(len(ts))
    return pd.DataFrame(
        {"ts": ts, "series_id": series_id, "value": value, "revision_date": ts.normalize()}
    )


@pytest.fixture
def lake(tmp_path: Path) -> Path:
    root = tmp_path / "lake"
    eia = _series("WCESTUS1", "2020-01-03", "2026-10-02", "7D", 4.2e5, 2e4)
    gie = _series("agsi.EU.full_pct", "2020-01-01", "2026-10-08", "D", 60, 30)
    _write(root, "ts_long/source=eia", eia)
    _write(root, "ts_long/source=gie", gie)
    cftc = pd.concat(
        [
            _series("cftc.cl.mm_long", "2023-01-03", "2026-10-06", "7D", 2e5, 5e4),
            _series("cftc.cl.mm_short", "2023-01-03", "2026-10-06", "7D", 8e4, 3e4),
        ]
    )
    _write(root, "ts_long/source=cftc", cftc)
    months = pd.date_range("2009-01-01", "2026-07-01", freq="MS")
    flows = pd.concat(
        [
            pd.DataFrame(
                {
                    "ts": months,
                    "mode": mode,
                    "unit": "MBBL",
                    "value": base * 30 + 1e3 * np.arange(len(months)),
                }
            )
            for mode, base in (("pipeline", 3e3), ("rail", 5e2), ("tanker_barge", 3e2))
        ]
    )
    _write(root, "flows/source=eia", flows)
    return root


def _hashes(paths: list[Path]) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def test_every_chart_is_written_as_pdf_png_and_caption(lake: Path, tmp_path: Path) -> None:
    written = readme_charts.build_all(lake, tmp_path / "out")
    names = {p.name for p in written}
    for chart in readme_charts.CHARTS:
        assert {f"{chart}.pdf", f"{chart}.png", f"{chart}.tex"} <= names
    for tex in (p for p in written if p.suffix == ".tex"):
        text = tex.read_text()
        assert text.startswith("% Written by paper_style.save")
        for needle in ("Units:", "Source:", "as of"):
            assert needle in text, (tex.name, needle)


def test_the_png_is_the_printed_size_at_300_dpi(lake: Path, tmp_path: Path) -> None:
    from PIL import Image

    for png in (p for p in readme_charts.build_all(lake, tmp_path / "out") if p.suffix == ".png"):
        with Image.open(png) as im:
            assert abs(im.width - 7.0 * ps.DPI) <= 1, png.name


def test_pdfs_embed_type_42_fonts_and_no_type_3(lake: Path, tmp_path: Path) -> None:
    for pdf in (p for p in readme_charts.build_all(lake, tmp_path / "out") if p.suffix == ".pdf"):
        raw = pdf.read_bytes()
        assert b"/FontFile2" in raw and b"/Subtype /Type3" not in raw, pdf.name


def test_drawing_twice_gives_identical_bytes(lake: Path, tmp_path: Path) -> None:
    first = _hashes(readme_charts.build_all(lake, tmp_path / "a"))
    second = _hashes(readme_charts.build_all(lake, tmp_path / "b"))
    assert first == second


def test_the_finding_is_computed_from_the_data_and_kept_off_the_image(
    lake: Path, tmp_path: Path
) -> None:
    lk = readme_charts.Lake(lake)
    fig = readme_charts.crude_stocks(lk)
    title = ps.field(fig, "title")
    assert title.startswith("US commercial crude stocks are ") and "% " in title
    assert "2026-10-02" in ps.caption(fig)
    assert not ps.lint(fig, axis_labels=True)
    assert all(t.get_text() != title for t in fig.findobj(lambda a: hasattr(a, "get_text")))


# --- the band years follow the data (I-04) --------------------------------------------


def _lake_ending(tmp_path: Path, eia_end: str, gie_end: str) -> Path:
    root = tmp_path / "lake_ending"
    _write(
        root,
        "ts_long/source=eia",
        _series("WCESTUS1", "2019-01-04", eia_end, "7D", 4.2e5, 2e4),
    )
    _write(
        root,
        "ts_long/source=gie",
        _series("agsi.EU.full_pct", "2019-01-01", gie_end, "D", 60, 30),
    )
    return root


def _ts(*dates: str) -> pd.DataFrame:
    return pd.DataFrame({"ts": pd.to_datetime(list(dates)), "value": 1.0})


def test_band_years_are_the_five_years_before_the_latest_observation() -> None:
    # Hand-worked: the latest observation is in 2026, so the band is 2021, 2022, 2023,
    # 2024 and 2025, which is what the constant used to say. A date in 2027 moves it to
    # 2022 through 2026: five years ending the year before.
    assert readme_charts.band_years(_ts("2026-10-02")) == range(2021, 2026)
    assert readme_charts.band_years(_ts("2027-03-05")) == range(2022, 2027)
    assert readme_charts.band_years(_ts("2027-03-05", "2026-12-30")) == range(2022, 2027)


def test_the_band_years_come_from_the_data_not_the_clock() -> None:
    # An old frame keeps its own band however late it is run.
    assert readme_charts.band_years(_ts("2024-06-07")) == range(2019, 2024)


def test_the_2027_charts_compare_against_the_band_of_2022_to_2026(tmp_path: Path) -> None:
    lk = readme_charts.Lake(_lake_ending(tmp_path, "2027-03-05", "2027-03-05"))
    for chart in (readme_charts.crude_stocks, readme_charts.eu_gas_storage):
        text = ps.caption(chart(lk))
        assert "2022 to 2026" in text, chart.__name__
        assert "2021 to 2025" not in text, chart.__name__


def test_the_2026_charts_keep_the_band_of_2021_to_2025(tmp_path: Path) -> None:
    lk = readme_charts.Lake(_lake_ending(tmp_path, "2026-10-02", "2026-10-08"))
    for chart in (readme_charts.crude_stocks, readme_charts.eu_gas_storage):
        assert "2021 to 2025" in ps.caption(chart(lk)), chart.__name__


def test_2020_is_left_out_of_the_band_whatever_the_year() -> None:
    from core import seasonal

    # A latest observation in 2025 puts 2020 inside the five-year window; the shared
    # seasonal module still leaves it out (golden rule 4).
    df = _series("x", "2019-01-04", "2025-06-06", "7D", 100, 10)
    years = readme_charts.band_years(df)
    assert 2020 in years
    stats = seasonal.seasonal_stats(df, "value", years=years)
    assert "2020" not in stats.columns
    assert {"2021", "2022", "2023", "2024"} <= set(stats.columns)


def test_the_crude_panel_is_drawn_on_the_first_report_of_a_year() -> None:
    # 2027-01-01 is a Friday: the week ending 1 January is 2027's first report, and its
    # band years first reported on Jan 7, 6, 5, 3 and 2. Day 1 used to be missing from the
    # band and the panel raised KeyError (I-16). Every value in year y is y - 2000, so the
    # latest is 27.0 and the day-1 median of 2022 to 2026 (carried from 21 to 25) is 23.0.
    ts = pd.date_range("2021-01-01", "2027-01-01", freq="W-FRI")
    df = pd.DataFrame({"ts": ts, "value": (ts.year - 2000).astype(float)})
    _, ax = readme_charts.new_figure()
    latest, median = readme_charts.seasonal_panel(ax, df, lambda v, t: (f"{v:.0f}", f"{t:%b %-d}"))
    assert (latest, median) == (27.0, 23.0)


# --- the positioning finding follows the sign of the book (I-20) -----------------------

OCT_2023 = pd.Timestamp("2023-10-03")


def test_a_net_long_book_below_its_high_gives_the_percentage_form() -> None:
    # 100 * (1 - 54 / 257) = 78.99, so 79%: the caption as committed in docs/img.
    assert readme_charts.positioning_finding(54.0, 257.0, OCT_2023) == (
        "Managed money is net long 54 thousand contracts, 79% below its three-year high of "
        "October 2023"
    )


def test_a_net_short_book_below_a_positive_high_gives_a_difference_not_a_percentage() -> None:
    # -10 against +50: 60 thousand below; "120% below" was the old output.
    assert readme_charts.positioning_finding(-10.0, 50.0, OCT_2023) == (
        "Managed money is net short 10 thousand contracts, 60 thousand below its "
        "three-year high of +50 thousand in October 2023"
    )


def test_a_net_short_book_below_a_negative_high_keeps_the_sign_of_the_high() -> None:
    # -10 against -5: 5 thousand below, and the high itself is a net short of 5 thousand.
    assert readme_charts.positioning_finding(-10.0, -5.0, pd.Timestamp("2025-03-04")) == (
        "Managed money is net short 10 thousand contracts, 5 thousand below its "
        f"three-year high of {ps.MINUS}5 thousand in March 2025"
    )


def test_a_book_at_its_high_says_so() -> None:
    assert readme_charts.positioning_finding(60.0, 60.0, pd.Timestamp("2026-10-06")) == (
        "Managed money is net long 60 thousand contracts, at its three-year high"
    )
    assert readme_charts.positioning_finding(-5.0, -5.0, pd.Timestamp("2026-10-06")) == (
        "Managed money is net short 5 thousand contracts, at its three-year high"
    )


def test_a_flat_book_is_neither_long_nor_short() -> None:
    assert readme_charts.positioning_finding(0.0, 40.0, OCT_2023) == (
        "Managed money is flat, 40 thousand below its three-year high of +40 thousand in "
        "October 2023"
    )


def test_the_chart_title_says_net_short_when_the_fixture_book_is_net_short(
    tmp_path: Path,
) -> None:
    root = tmp_path / "short_lake"
    _write(
        root,
        "ts_long/source=cftc",
        pd.concat(
            [
                _series("cftc.cl.mm_long", "2023-01-03", "2026-10-06", "7D", 5e4, 1e4),
                _series("cftc.cl.mm_short", "2023-01-03", "2026-10-06", "7D", 2e5, 1e4),
            ]
        ),
    )
    title = ps.field(readme_charts.cftc_positioning(readme_charts.Lake(root)), "title")
    assert title.startswith("Managed money is net short ")
    assert "net long" not in title and "short -" not in title and "%" not in title
