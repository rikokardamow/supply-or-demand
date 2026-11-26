"""The README charts from a small synthetic lake: paper format, captions, byte-stable."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from apps.exhibits import readme_charts
from core import paper_style as ps


@pytest.fixture(autouse=True)
def _close_figures() -> Iterator[None]:
    yield
    plt.close("all")


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


# --- the README exhibits are held to the desk rules (I-21) ------------------------------

EXPECTED_UNITS = {
    "crude_stocks": "mb",
    "crude_weekly_change": "mb",
    "cftc_positioning": "contracts",
    "interpadd_flows": "mb/d",
    "eu_gas_storage": "%",
}
EXPECTED_YLABELS = {
    "crude_stocks": "Commercial crude stocks (mb)",
    "crude_weekly_change": "Weekly change in commercial crude stocks (mb)",
    "cftc_positioning": "Managed-money positions (contracts; short below zero)",
    "interpadd_flows": "Crude moved between PADDs (mb/d)",
    "eu_gas_storage": "EU gas storage, share of working capacity (%)",
}


def test_the_charts_use_the_house_unit_spellings_and_axis_labels(lake: Path) -> None:
    lk = readme_charts.Lake(lake)
    with readme_charts.desk_rules():
        for name, draw in readme_charts.CHARTS.items():
            fig = draw(lk)
            assert fig._ps_frame["units"] == EXPECTED_UNITS[name], name  # type: ignore[attr-defined]
            assert fig.axes[0].get_ylabel() == EXPECTED_YLABELS[name], name


def test_every_chart_passes_the_lint_under_the_desk_rules(lake: Path) -> None:
    lk = readme_charts.Lake(lake)
    with readme_charts.desk_rules():
        assert ps.STRICT_DESK is True
        for name, draw in readme_charts.CHARTS.items():
            assert ps.lint(draw(lk), axis_labels=True) == [], name


def test_a_red_line_cannot_be_saved_under_the_desk_rules(lake: Path, tmp_path: Path) -> None:
    lk = readme_charts.Lake(lake)
    with readme_charts.desk_rules():
        fig = readme_charts.crude_stocks(lk)
        fig.axes[0].plot([0, 1], [0, 1], color="#C0392B")
        with pytest.raises(ValueError, match="red or green"):
            ps.save(fig, tmp_path / "red", formats=("png",))


def test_a_free_text_unit_is_refused_under_the_desk_rules() -> None:
    _, ax = readme_charts.new_figure()
    fig = ax.figure
    with readme_charts.desk_rules(), pytest.raises(ValueError, match="allowed spelling"):
        ps.frame(
            fig,
            title="Stocks rose 3 mb in the week.",
            units="million barrels",
            cadence="weekly",
            source="s",
            asof="2026-10-02",
            xlabel="x",
            ylabel="y",
            margins=readme_charts.MARGINS,
        )


def test_the_switches_are_put_back_after_build_all(lake: Path, tmp_path: Path) -> None:
    assert ps.STRICT_DESK is False and ps.UNITS is None
    readme_charts.build_all(lake, tmp_path / "out")
    assert ps.STRICT_DESK is False and ps.UNITS is None


def test_the_switches_are_put_back_when_a_chart_fails(
    lake: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_: readme_charts.Lake) -> None:
        raise RuntimeError("no data")

    monkeypatch.setitem(readme_charts.CHARTS, "crude_stocks", boom)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        readme_charts.build_all(lake, tmp_path / "out")
    assert ps.STRICT_DESK is False and ps.UNITS is None


def test_the_positioning_chart_plots_contracts_not_thousands(lake: Path) -> None:
    lk = readme_charts.Lake(lake)
    fig = readme_charts.cftc_positioning(lk)
    top = max(p.get_height() for p in fig.axes[0].patches)
    assert top > 1e4  # the fixture holds 2e5 long: contracts, with a thousands separator
    assert fig.axes[0].yaxis.get_major_formatter()(150000, 0) == "150,000"
    title = ps.field(fig, "title")
    assert "thousand contracts" in title


# --- the weekly change against its own seasonal norm (I-22) -----------------------------

# The change in the week ending on or before 2 October, by year (2 October 2026 is a
# Friday; the week ending on or before it is 1 Oct 2021, 30 Sep 2022, 29 Sep 2023,
# 27 Sep 2024 and 26 Sep 2025). Every other week changes by 0.5 mb.
OCT_2_CHANGES = {2021: 1.0, 2022: -1.0, 2023: 3.0, 2024: 0.0, 2025: 2.0, 2026: -2.0}


def _change_lake(tmp_path: Path) -> Path:
    weeks = pd.date_range("2020-01-03", "2026-10-02", freq="W-FRI")
    change = pd.Series(0.5, index=weeks)
    for year, value in OCT_2_CHANGES.items():
        change[weeks[weeks <= pd.Timestamp(f"{year}-10-02")][-1]] = value
    level_kb = (400_000.0 + 1000.0 * change.cumsum()).to_numpy()
    root = tmp_path / "change_lake"
    _write(
        root,
        "ts_long/source=eia",
        pd.DataFrame(
            {
                "ts": weeks,
                "series_id": "WCESTUS1",
                "value": level_kb,
                "revision_date": weeks.normalize(),
            }
        ),
    )
    return root


def test_the_weekly_change_is_set_against_the_same_week_of_the_five_prior_years(
    tmp_path: Path,
) -> None:
    lk = readme_charts.Lake(_change_lake(tmp_path))
    changes, stats = readme_charts.weekly_change_band(lk.series("WCESTUS1", "eia"))
    assert changes["value"].iloc[-1] == pytest.approx(-2.0)
    from core import seasonal

    doy = seasonal.reference_doy_clamped(pd.Timestamp("2026-10-02"))
    # Hand-worked: +1, -1, +3, 0, +2 sorted are -1, 0, +1, +2, +3: median +1, range -1 to +3.
    assert stats.loc[doy, "median"] == pytest.approx(1.0)
    assert stats.loc[doy, "lo"] == pytest.approx(-1.0)
    assert stats.loc[doy, "hi"] == pytest.approx(3.0)


def test_the_weekly_change_title_states_the_finding_with_arrows(tmp_path: Path) -> None:
    lk = readme_charts.Lake(_change_lake(tmp_path))
    with readme_charts.desk_rules():
        fig = readme_charts.crude_weekly_change(lk)
        assert ps.field(fig, "title") == (
            "US crude stocks \u25bc2.0 mb in the week to Oct 2, against a 2021 to 2025 median "
            "of \u25b21.0 mb for the week"
        )
        assert ps.lint(fig, axis_labels=True) == []
        assert fig._ps_frame["units"] == "mb"  # type: ignore[attr-defined]
        assert "WCESTUS1" in ps.caption(fig) and "Public domain" in ps.caption(fig)


def test_the_weekly_change_is_a_registered_chart_and_byte_stable(tmp_path: Path) -> None:
    assert "crude_weekly_change" in readme_charts.CHARTS
    root = _change_lake(tmp_path)
    only = {"crude_weekly_change": readme_charts.CHARTS["crude_weekly_change"]}
    from unittest import mock

    with mock.patch.dict(readme_charts.CHARTS, only, clear=True):
        first = _hashes(readme_charts.build_all(root, tmp_path / "a"))
        second = _hashes(readme_charts.build_all(root, tmp_path / "b"))
    assert first == second and len(first) == 3


def test_a_week_with_no_change_or_a_build_gets_the_right_arrow() -> None:
    assert readme_charts.arrow_mb(2.0) == "\u25b22.0 mb"
    assert readme_charts.arrow_mb(-2.0) == "\u25bc2.0 mb"
    assert readme_charts.arrow_mb(0.0) == "\u25cf0.0 mb"
