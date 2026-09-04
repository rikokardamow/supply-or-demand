from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pipelines.manual_physical.reader import physical_to_ts_long, read_physical_csvs


def _write_fixture(tmp_path: Path) -> Path:
    csv_path = tmp_path / "physical_20260101.csv"
    csv_path.write_text(
        "date,series_id,value\n"
        "2026-01-01,manual.platts.brent_dubai_efs,1.20\n"
        "2026-01-01,manual.argus.wcs_diff,-14.50\n"
        "2026-01-01,manual.eia_steo.spare_capacity,3.1\n"
        "2026-01-02,manual.platts.brent_dubai_efs,1.35\n"
    )
    return tmp_path


def test_read_physical_csvs_reads_the_synthetic_fixture(tmp_path: Path) -> None:
    data_dir = _write_fixture(tmp_path)
    df = read_physical_csvs(data_dir)

    assert len(df) == 4
    assert set(df["series_id"]) == {
        "manual.platts.brent_dubai_efs",
        "manual.argus.wcs_diff",
        "manual.eia_steo.spare_capacity",
    }


def test_read_physical_csvs_returns_empty_frame_when_no_files_exist(tmp_path: Path) -> None:
    df = read_physical_csvs(tmp_path)
    assert df.empty
    assert list(df.columns) == ["date", "series_id", "value"]


def test_read_physical_csvs_rejects_unrecognised_series_id(tmp_path: Path) -> None:
    (tmp_path / "bad.csv").write_text(
        "date,series_id,value\n2026-01-01,manual.unknown.series,1.0\n"
    )
    with pytest.raises(ValueError, match="unrecognised series_id"):
        read_physical_csvs(tmp_path)


def test_read_physical_csvs_rejects_duplicate_date_series_rows(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text(
        "date,series_id,value\n2026-01-01,manual.argus.wcs_diff,-14.50\n"
    )
    (tmp_path / "b.csv").write_text(
        "date,series_id,value\n2026-01-01,manual.argus.wcs_diff,-15.00\n"
    )
    with pytest.raises(ValueError, match="duplicate"):
        read_physical_csvs(tmp_path)


def test_physical_to_ts_long_unit_geo_freq_differ_by_series(tmp_path: Path) -> None:
    data_dir = _write_fixture(tmp_path)
    df = read_physical_csvs(data_dir)
    long_df = physical_to_ts_long(df, revision_date=pd.Timestamp("2026-01-03"))

    assert set(long_df.columns) == {
        "series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date",
    }
    assert (long_df["source"] == "manual").all()

    efs = long_df[long_df["series_id"] == "manual.platts.brent_dubai_efs"].iloc[0]
    assert efs["unit"] == "USD/bbl"
    assert efs["geo"] == "GLOBAL"
    assert efs["freq"] == "D"

    spare_cap = long_df[long_df["series_id"] == "manual.eia_steo.spare_capacity"].iloc[0]
    assert spare_cap["unit"] == "mb/d"
    assert spare_cap["freq"] == "M"
