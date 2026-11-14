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
