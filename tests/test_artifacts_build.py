"""Publishing-layer build: the guards and the seasonal window, on synthetic data only.

Nothing here reads the real lake -- the exhibits themselves are checked by running the
build against it (see .claude/skills/refresh-artifacts).
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from apps.artifacts import build, exhibits, tables


def _weekly(start: str, end: str, value_for_year: dict[int, float]) -> pd.DataFrame:
    ts = pd.date_range(start, end, freq="W-FRI")
    return pd.DataFrame({"ts": ts, "value": [value_for_year[t.year] for t in ts], "unit": "MBBL"})


def test_band_is_the_five_years_before_the_current_one() -> None:
    levels = {
        2019: 900.0,
        2020: 5000.0,
        2021: 10.0,
        2022: 20.0,
        2023: 30.0,
        2024: 40.0,
        2025: 50.0,
        2026: 77.0,
    }
    table = tables.seasonal_table(_weekly("2019-01-04", "2026-06-26", levels), "X")
    mid = table[table["doy"] == 100].iloc[0]
    # 2019 (outside the window) and 2026 (the year being measured) must not move the band.
    assert (mid["band_min"], mid["band_max"], mid["median"]) == (10.0, 50.0, 30.0)
    assert mid["years"] == 5
    assert (mid["current"], mid["prior"]) == (77.0, 50.0)


def test_2020_stays_excluded_when_the_window_reaches_it() -> None:
    levels = {2019: 10.0, 2020: 5000.0, 2021: 20.0, 2022: 30.0, 2023: 40.0, 2024: 77.0}
    table = tables.seasonal_table(_weekly("2019-01-04", "2024-06-28", levels), "X")
    mid = table[table["doy"] == 100].iloc[0]
    assert mid["band_max"] == 40.0
    assert mid["years"] == 4


def test_current_year_stops_at_its_last_observation() -> None:
    levels = {y: float(y) for y in range(2021, 2027)}
    table = tables.seasonal_table(_weekly("2021-01-01", "2026-06-26", levels), "X")
    last_doy = pd.Timestamp("2001-06-26").dayofyear
    assert table.loc[table["doy"] == last_doy, "current"].notna().all()
    assert table.loc[table["doy"] > last_doy, "current"].isna().all()


def test_stale_flag_names_the_last_observation() -> None:
    assert exhibits.stale_flag("2026-08-28", 7, date(2026, 10, 10)) == "No data since 28 Aug 2026"
    assert exhibits.stale_flag("2026-10-02", 7, date(2026, 10, 10)) is None


def test_env_secrets_skips_comments_and_short_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(build.os, "environ", {})
    env = tmp_path / ".env"
    env.write_text(
        "# NOTE=commented-out-value\nKEY='long-secret-value'\nFLAG=1\n", encoding="utf-8"
    )
    found = build.env_secrets([env, tmp_path / "missing"])
    assert found == {"KEY": build.needles("long-secret-value")}
    assert b"long-secret-value" in found["KEY"]


def test_a_leaked_secret_fails_the_build_and_removes_the_file(tmp_path: Path) -> None:
    page = tmp_path / "page.html"
    page.write_text("<p>token long-secret-value</p>", encoding="utf-8")
    with pytest.raises(build.SecretLeakError, match="KEY") as raised:
        build.assert_no_secrets([page], {"KEY": {b"long-secret-value"}})
    assert "long-secret-value" not in str(raised.value)
    assert not page.exists()


def test_a_secret_inside_an_office_file_is_found(tmp_path: Path) -> None:
    deck = tmp_path / "deck.pptx"
    with zipfile.ZipFile(deck, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/slides/slide1.xml", "<a:t>long-secret-value</a:t>")
    with pytest.raises(build.SecretLeakError):
        build.assert_no_secrets([deck], {"KEY": {b"long-secret-value"}})


def test_clean_outputs_pass(tmp_path: Path) -> None:
    page = tmp_path / "page.html"
    page.write_text("<p>424.5 million barrels</p>", encoding="utf-8")
    build.assert_no_secrets([page], {"KEY": {b"long-secret-value"}})
    assert page.exists()


@pytest.mark.parametrize("page", build.PAGES)
def test_render_inlines_data_without_breaking_out_of_the_script_tag(page: str) -> None:
    payload = {"meta": {}, "title": "</script><script>alert(1)</script>"}
    html = build.render(page, payload)
    assert "/*__DATA__*/" not in html and "/*__CHARTS_JS__*/" not in html
    assert "</script><script>alert(1)" not in html
    embedded = html.split('id="payload">', 1)[1].split("</script>", 1)[0]
    assert json.loads(embedded) == payload


def test_shell_credentials_are_checked_as_well_as_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOME_API_TOKEN", "exported-secret-value")
    monkeypatch.setenv("HOME_DIRECTORY", "not-a-credential-path")
    found = build.env_secrets([])
    assert b"exported-secret-value" in found["SOME_API_TOKEN"]
    assert "HOME_DIRECTORY" not in found


@pytest.mark.parametrize("text", ["=HYPERLINK(1)", "+1", "-2+3", "@SUM(A1)", "\tx"])
def test_formula_like_text_is_stored_as_text(text: str) -> None:
    from apps.artifacts import office

    assert office._cell(text) == "'" + text
    assert office._cell("PADD2 to PADD3") == "PADD2 to PADD3"
    assert office._cell(-4.4) == -4.4


def test_a_stale_dotenv_value_does_not_hide_the_live_shell_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text("EIA_API_KEY=rotated-out-value\n", encoding="utf-8")
    monkeypatch.setattr(build.os, "environ", {"EIA_API_KEY": "live-exported-value"})
    secrets = build.env_secrets([env])
    assert secrets["EIA_API_KEY"] >= {b"rotated-out-value", b"live-exported-value"}
    page = tmp_path / "page.html"
    page.write_text("<p>live-exported-value</p>", encoding="utf-8")
    with pytest.raises(build.SecretLeakError, match="EIA_API_KEY"):
        build.assert_no_secrets([page], secrets)


def test_a_dotenv_with_no_credentials_yields_nothing_to_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text("# keys go here\nDEBUG=1\n", encoding="utf-8")
    monkeypatch.setattr(build.os, "environ", {})
    assert build.env_secrets([env]) == {}


def _daily(start: str, end: str) -> pd.DataFrame:
    ts = pd.date_range(start, end, freq="D")
    return pd.DataFrame({"ts": ts, "value": [float(i) for i in range(len(ts))]})


def _pair(
    book: exhibits.Book, tracks: list[tuple[str, pd.DataFrame, str, int]], **extra: object
) -> None:
    exhibits.pair_exhibit(
        book,
        exhibit_id="x",
        tab="prices",
        title="Pair",
        kind="dual",
        tracks=tracks,
        provider="P",
        table="t",
        note="",
        cadence_days=7,
        **{"run": None, **extra},  # type: ignore[arg-type]
    )


def test_a_pair_is_only_as_fresh_as_its_oldest_series() -> None:
    book = exhibits.Book(today=date(2026, 10, 10))
    stale = ("Net long", _daily("2026-01-01", "2026-03-31"), "contracts", 0)
    live = ("WTI", _daily("2026-01-01", "2026-10-09"), "USD/bbl", 2)
    _pair(book, [stale, live])
    assert book.exhibits[0]["gap"] == "No data since 31 Mar 2026"
    assert "data to 31 Mar 2026" in book.exhibits[0]["source"]


def test_a_forward_dated_series_is_judged_on_its_pipeline_run() -> None:
    forecast = ("Call on crude", _daily("2026-01-01", "2027-10-01"), "mb/d", 2)
    old = exhibits.Book(today=date(2026, 10, 10))
    _pair(old, [forecast], forward_dated=True, run="2026-06-01")
    assert old.exhibits[0]["gap"] == "No data since 1 Jun 2026"
    fresh = exhibits.Book(today=date(2026, 10, 10))
    _pair(fresh, [forecast], forward_dated=True, run="2026-10-05")
    assert fresh.exhibits[0]["gap"] is None


def test_bars_leave_out_a_row_that_stopped_reporting() -> None:
    frame = pd.DataFrame(
        {
            "corridor": ["Dead", "Live"],
            "through": pd.to_datetime(["2024-12-31", "2026-10-08"]),
            "latest": [900.0, 100.0],
            "year_ago": [None, 90.0],
        }
    )
    book = exhibits.Book(today=date(2026, 10, 10))
    exhibits.bars_exhibit(
        book,
        exhibit_id="b",
        tab="flows",
        title="Flows",
        frame=frame,
        category="corridor",
        value="latest",
        compare="year_ago",
        unit="GWh/d",
        value_name="Latest",
        compare_name="Year ago",
        provider="P",
        table="t",
        sheet="flows",
        run=None,
        note="",
        cadence_days=7,
    )
    assert book.exhibits[0]["categories"] == ["Live"]
    assert "Dead (to 31 Dec 2024)" in book.issues[0]


def test_storage_year_ago_is_the_nearest_day_to_the_target(monkeypatch: pytest.MonkeyPatch) -> None:
    daily = _daily("2025-09-01", "2026-09-10").assign(series_id="agsi.DE.full_pct", geo="DE")
    monkeypatch.setattr(tables, "_fullness", lambda: daily)
    row = tables.storage_by_country().iloc[0]
    target = pd.Timestamp("2026-09-10") - pd.Timedelta(days=364)
    assert row["year_ago_pct"] == daily.loc[daily["ts"] == target, "value"].iloc[0]


def test_an_unbuildable_motion_page_fails_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build.tables, "storage_weekly", lambda: pd.DataFrame())
    with pytest.raises(build.NothingToPublishError, match="AGSI"):
        build.motion_payload({}, date(2026, 10, 10))


def test_a_leak_removes_every_output_not_just_the_first(tmp_path: Path) -> None:
    data, page, clean = tmp_path / "p.json", tmp_path / "p.html", tmp_path / "other.html"
    data.write_text('{"k":"long-secret-value"}', encoding="utf-8")
    page.write_text("<p>long-secret-value</p>", encoding="utf-8")
    clean.write_text("<p>nothing</p>", encoding="utf-8")
    with pytest.raises(build.SecretLeakError, match=r"p\.html"):
        build.assert_no_secrets([data, page, clean], {"KEY": {b"long-secret-value"}})
    assert not data.exists() and not page.exists() and not clean.exists()


def test_a_dotenv_value_is_read_without_its_quotes_or_trailing_comment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(build.os, "environ", {})
    env = tmp_path / ".env"
    env.write_text(
        'EIA_API_KEY=plain-secret-value # rotated\nFRED_API_KEY="quoted-secret-value" # note\n',
        encoding="utf-8",
    )
    found = build.env_secrets([env])
    assert b"plain-secret-value" in found["EIA_API_KEY"]
    assert b"quoted-secret-value" in found["FRED_API_KEY"]


@pytest.mark.parametrize(
    "written",
    [
        json.dumps('pa"ss\\word-99'),
        "pa&quot;ss\\word-99",
        "pa%22ss%5Cword-99",
    ],
)
def test_an_escaped_credential_is_still_found(tmp_path: Path, written: str) -> None:
    page = tmp_path / "page.html"
    page.write_text(written, encoding="utf-8")
    with pytest.raises(build.SecretLeakError):
        build.assert_no_secrets([page], {"KEY": build.needles('pa"ss\\word-99')})


def test_a_connection_string_password_is_found_on_its_own(tmp_path: Path) -> None:
    page = tmp_path / "page.html"
    page.write_text("<p>hunter2-hunter2</p>", encoding="utf-8")
    secrets = {
        "SUPABASE_DB_URL": build.needles("postgresql://user:hunter2-hunter2@db.example:5432/x")
    }
    with pytest.raises(build.SecretLeakError, match="SUPABASE_DB_URL"):
        build.assert_no_secrets([page], secrets)


def test_a_secret_in_a_workbook_embedded_in_a_deck_is_found(tmp_path: Path) -> None:
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/sharedStrings.xml", "<t>long-secret-value</t>")
    deck = tmp_path / "deck.pptx"
    with zipfile.ZipFile(deck, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/embeddings/sheet1.xlsx", inner.getvalue())
    with pytest.raises(build.SecretLeakError):
        build.assert_no_secrets([deck], {"KEY": {b"long-secret-value"}})


def test_only_the_projects_own_credentials_arm_the_leak_check() -> None:
    assert "EIA_API_KEY" in build.PROJECT_CREDENTIALS
    assert "CLAUDE_CODE_MESSAGING_TOKEN" not in build.PROJECT_CREDENTIALS


@pytest.mark.parametrize("page", build.PAGES)
def test_render_survives_a_comment_and_script_opener_in_lake_text(page: str) -> None:
    payload = {"meta": {}, "title": "<!--<script>", "unit": "a & b " + chr(0x2028)}
    html = build.render(page, payload)
    embedded = html.split('id="payload">', 1)[1].split("</script>", 1)[0]
    assert "<" not in embedded and "&" not in embedded and chr(0x2028) not in embedded
    assert json.loads(embedded) == payload


@pytest.mark.parametrize(
    "text", ["https://example.com/x", "external:\\\\host\\share\\a.xlsx", "mailto:a@example.com"]
)
def test_link_like_text_is_stored_as_text(text: str) -> None:
    from apps.artifacts import office

    assert office.safe_text(text) == "'" + text


def test_deck_bar_categories_cannot_become_formulas_or_links(tmp_path: Path) -> None:
    from apps.artifacts import office

    exhibit = {
        "id": "b",
        "kind": "bars",
        "title": "Flows",
        "takeaway": ["a", "b"],
        "source": "s",
        "note": "",
        "gap": None,
        "unit": "GWh/d",
        "digits": 1,
        "categories": ['=HYPERLINK("http://example.com")', "https://example.com", "A\x0bB"],
        "values": [1.0, 2.0, 3.0],
        "compare": [1.0, 2.0, 3.0],
        "value_name": "Latest",
        "compare_name": "Year ago",
    }
    meta = {"built_at": "x", "newest_run": None, "oldest_run": None, "stale": 0, "exhibits": 1}
    deck = office.write_deck({"meta": meta, "slides": [exhibit]}, tmp_path)
    with zipfile.ZipFile(deck) as archive:
        for name in archive.namelist():
            if name.startswith("ppt/embeddings/"):
                with zipfile.ZipFile(io.BytesIO(archive.read(name))) as book:
                    sheets = b"".join(
                        book.read(n) for n in book.namelist() if n.startswith("xl/worksheets/")
                    )
                assert sheets and b"<f>" not in sheets and b"<hyperlink" not in sheets


@pytest.mark.parametrize("text", [" =1+1", "{=SUM(1)}", "HTTPS://example.com", "  External:x"])
def test_text_a_looser_reader_would_evaluate_is_also_guarded(text: str) -> None:
    from apps.artifacts import office

    assert office.safe_text(text) == "'" + text


def test_an_output_that_cannot_be_deleted_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = tmp_path / "page.html"
    page.write_text("<p>long-secret-value</p>", encoding="utf-8")

    def locked(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("in use")

    monkeypatch.setattr(Path, "unlink", locked)
    with pytest.raises(build.SecretLeakError, match="COULD NOT DELETE"):
        build.assert_no_secrets([page], {"KEY": {b"long-secret-value"}})


def test_a_weekly_series_is_drawn_through_its_reports_not_as_a_staircase() -> None:
    levels = {y: float(y) for y in range(2021, 2027)}
    series = _weekly("2021-01-01", "2026-06-26", levels)
    band = tables.seasonal_table(series, "X")
    last_doy = int(band.loc[band["current"].notna(), "doy"].iloc[-1])
    drawn = exhibits._drawn(band, series, 2026, last_doy)
    reports = int((series["ts"].dt.year == 2026).sum())
    assert drawn["current"].notna().sum() == reports
    assert 50 <= drawn["median"].notna().sum() <= 55
    assert drawn.loc[drawn["doy"] == last_doy, ["current", "median"]].notna().all(axis=None)
    kept = drawn["current"].dropna()
    assert (kept == band.loc[kept.index, "current"]).all()


def test_a_daily_series_is_drawn_in_full() -> None:
    series = _daily("2021-01-01", "2026-06-26").assign(unit="%")
    band = tables.seasonal_table(series, "X")
    assert exhibits._drawn(band, series, 2026, 100) is band


def test_moving_averages_use_the_whole_history_and_skip_windows_it_cannot_fill() -> None:
    book = exhibits.Book(today=date(2026, 10, 10))
    history = _daily("2026-01-01", "2026-06-29")  # 180 observations, values 0..179
    out = exhibits._overlays(book, "x", history, "2026-06-01", "USD/bbl", 2)
    assert [o["name"] for o in out] == ["MA20", "MA100"]  # no MA200, no five-year average
    ma20 = out[0]
    assert ma20["x"][0] == "2026-06-01"
    assert ma20["y"][-1] == sum(range(160, 180)) / 20
    sheet = pd.concat(book.overlays)
    assert set(sheet["measure"]) == {"MA20", "MA100"} and set(sheet["exhibit_id"]) == {"x"}


def test_the_five_year_average_needs_five_years_of_history() -> None:
    book = exhibits.Book(today=date(2026, 10, 10))
    history = _daily("2020-01-01", "2026-10-09")
    out = exhibits._overlays(book, "x", history, "2026-01-01", "USD/bbl", 2)
    average = out[-1]
    assert average["name"] == "5-year average" and average["style"] == "avg5"
    window = history.loc[history["ts"] > pd.Timestamp("2021-10-09"), "value"]
    assert average["y"] == [round(float(window.mean()), 3)] * 2
    assert average["x"] == ["2026-01-01", "2026-10-09"]
