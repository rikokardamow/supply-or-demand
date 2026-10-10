"""Publishing-layer build: the guards and the seasonal window, on synthetic data only.

Nothing here reads the real lake -- the exhibits themselves are checked by running the
build against it (see .claude/skills/refresh-artifacts).
"""

from __future__ import annotations

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
    assert build.env_secrets([env, tmp_path / "missing"]) == {"KEY": b"long-secret-value"}


def test_a_leaked_secret_fails_the_build_and_removes_the_file(tmp_path: Path) -> None:
    page = tmp_path / "page.html"
    page.write_text("<p>token long-secret-value</p>", encoding="utf-8")
    with pytest.raises(build.SecretLeakError, match="KEY") as raised:
        build.assert_no_secrets([page], {"KEY": b"long-secret-value"})
    assert "long-secret-value" not in str(raised.value)
    assert not page.exists()


def test_a_secret_inside_an_office_file_is_found(tmp_path: Path) -> None:
    deck = tmp_path / "deck.pptx"
    with zipfile.ZipFile(deck, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/slides/slide1.xml", "<a:t>long-secret-value</a:t>")
    with pytest.raises(build.SecretLeakError):
        build.assert_no_secrets([deck], {"KEY": b"long-secret-value"})


def test_clean_outputs_pass(tmp_path: Path) -> None:
    page = tmp_path / "page.html"
    page.write_text("<p>424.5 million barrels</p>", encoding="utf-8")
    build.assert_no_secrets([page], {"KEY": b"long-secret-value"})
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
    assert found["SOME_API_TOKEN"] == b"exported-secret-value"
    assert "HOME_DIRECTORY" not in found


@pytest.mark.parametrize("text", ["=HYPERLINK(1)", "+1", "-2+3", "@SUM(A1)", "\tx"])
def test_formula_like_text_is_stored_as_text(text: str) -> None:
    from apps.artifacts import office

    assert office._cell(text) == "'" + text
    assert office._cell("PADD2 to PADD3") == "PADD2 to PADD3"
    assert office._cell(-4.4) == -4.4
