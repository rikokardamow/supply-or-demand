from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pipelines.epa.reference import (
    CATEGORIES,
    load_percentage_standards,
    load_volume_targets,
)

VOL_HEAD = "year,category,billion_rins,basis,status,source,as_of\n"
PCT_HEAD = "year,category,pct,status,source,as_of\n"


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_volume_targets_carry_a_status_and_a_traceable_source() -> None:
    df = load_volume_targets()

    expected = {"year", "category", "billion_rins", "basis", "status", "source", "as_of"}
    assert set(df.columns) == expected
    assert not df.empty
    assert set(df["status"]) <= {"final", "proposed"}
    assert df["source"].str.len().gt(20).all(), "every figure must name the rule it came from"
    assert pd.api.types.is_datetime64_any_dtype(df["as_of"])
    assert df["billion_rins"].between(0.1, 60).all()
    assert not df.duplicated(["year", "category", "basis"]).any()
    assert set(df["category"]) <= set(CATEGORIES)


def test_percentage_standards_carry_a_status_and_a_traceable_source() -> None:
    df = load_percentage_standards()

    assert set(df.columns) == {"year", "category", "pct", "status", "source", "as_of"}
    assert not df.empty
    assert df["source"].str.len().gt(20).all()
    assert df["pct"].between(0.001, 0.5).all()
    assert not df.duplicated(["year", "category"]).any()


@pytest.mark.parametrize("loader", [load_volume_targets, load_percentage_standards])
def test_every_row_has_final_or_proposed_status(loader) -> None:
    df = loader()
    assert df["status"].isin(["final", "proposed"]).all()


def test_total_is_at_least_advanced_and_advanced_at_least_cellulosic() -> None:
    req = load_volume_targets().query("basis == 'requirement'")
    wide = req.pivot(index="year", columns="category", values="billion_rins")
    assert (wide["total"] >= wide["advanced"]).all()
    assert (wide["advanced"] >= wide["cellulosic"]).all()


def test_a_status_outside_the_allowed_pair_is_refused(tmp_path) -> None:
    row = "2025,total,22.33,requirement,assumed,rule x,2026-10-10\n"
    bad = _write(tmp_path, "v.csv", VOL_HEAD + row)
    with pytest.raises(ValueError, match="status"):
        load_volume_targets(bad)


def test_a_percentage_standard_outside_zero_to_one_is_refused(tmp_path) -> None:
    bad = _write(tmp_path, "p.csv", PCT_HEAD + "2025,total,10.47,final,rule x,2026-10-10\n")
    with pytest.raises(ValueError, match="pct"):
        load_percentage_standards(bad)


def test_an_unknown_category_is_refused(tmp_path) -> None:
    bad = _write(tmp_path, "p.csv", PCT_HEAD + "2025,cellulosic_diesel,0.0047,final,r,2026-10-10\n")
    with pytest.raises(ValueError, match="category"):
        load_percentage_standards(bad)


def test_a_missing_column_is_refused(tmp_path) -> None:
    bad = _write(tmp_path, "v.csv", "year,category,billion_rins,basis,source,as_of\n"
                 "2025,total,22.33,requirement,rule x,2026-10-10\n")
    with pytest.raises(ValueError, match="columns"):
        load_volume_targets(bad)


def test_a_duplicate_year_and_category_is_refused(tmp_path) -> None:
    row = "2025,total,22.33,requirement,final,rule x,2026-10-10\n"
    with pytest.raises(ValueError, match="duplicate"):
        load_volume_targets(_write(tmp_path, "v.csv", VOL_HEAD + row + row))


def test_a_non_positive_volume_an_empty_source_and_a_bad_date_are_refused(tmp_path) -> None:
    def load(name: str, row: str) -> pd.DataFrame:
        return load_volume_targets(_write(tmp_path, name, VOL_HEAD + row + chr(10)))

    with pytest.raises(ValueError, match="billion_rins"):
        load("a.csv", "2025,total,0,requirement,final,r,2026-10-10")
    with pytest.raises(ValueError, match="blank cell"):
        load("b.csv", "2025,total,1,requirement,final,,2026-10-10")
    with pytest.raises(ValueError, match="as_of"):
        load("c.csv", "2025,total,1,requirement,final,r,soon")


def test_a_basis_outside_the_allowed_pair_is_refused(tmp_path) -> None:
    bad = _write(tmp_path, "v.csv", VOL_HEAD + "2026,total,26.81,reallocated,final,r,2026-10-10\n")
    with pytest.raises(ValueError, match="basis"):
        load_volume_targets(bad)


def test_the_same_year_and_category_may_appear_once_per_basis(tmp_path) -> None:
    rows = ("2026,total,25.82,requirement,final,r,2026-10-10\n"
            "2026,total,26.81,applicable,final,r,2026-10-10\n")
    assert len(load_volume_targets(_write(tmp_path, "v.csv", VOL_HEAD + rows))) == 2


def test_2026_applicable_volumes_are_at_least_the_requirements() -> None:
    df = load_volume_targets().query("year in (2026, 2027)")
    wide = df.pivot(index=["year", "category"], columns="basis", values="billion_rins")
    assert {"requirement", "applicable"} <= set(wide.columns)
    assert wide["applicable"].notna().all() and wide["requirement"].notna().all()
    assert (wide["applicable"] >= wide["requirement"]).all()
    assert (wide["applicable"] > wide["requirement"]).any(), "reallocation must show as a step"


def test_the_2026_total_standard_is_held_as_a_fraction_not_per_cent() -> None:
    """EPA publishes 15.50 per cent (40 CFR 80.1405(a)); the file must hold 0.155."""
    df = load_percentage_standards()
    row = df[(df["year"] == 2026) & (df["category"] == "total")]
    assert len(row) == 1
    assert row["pct"].iloc[0] == pytest.approx(0.155)
