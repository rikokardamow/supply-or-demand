from __future__ import annotations

import pandas as pd
import pytest
from pipelines.derived.cracks import (
    FUT_TENORS,
    FUTURES_CRACK_DEFS,
    build_futures_cracks,
    futures_derived_rows,
    futures_leg_id,
)


def _futures_panel() -> pd.DataFrame:
    """Wide lake panel of EIA futures ranks. `hu` (pre-2006 unleaded) only prints on the
    first date, `rb` (RBOB) only on the second -- the real changeover shape."""
    idx = pd.to_datetime(["2005-11-01", "2006-11-01"])
    return pd.DataFrame(
        {
            "fut.cl.f01.settle": [70.0, 60.0],
            "fut.rb.f01.settle": [float("nan"), 2.00],
            "fut.hu.f01.settle": [2.20, float("nan")],
            "fut.ho.f01.settle": [2.40, 2.10],
        },
        index=idx,
    )


def test_tenor_map_points_at_the_conventions_rank_series() -> None:
    assert FUT_TENORS["m1"] == "f01"
    assert FUT_TENORS["m2"] == "f02"


def test_futures_leg_id_builds_the_conventions_rank_series_id() -> None:
    assert futures_leg_id("cl", "m1") == "fut.cl.f01.settle"
    assert futures_leg_id("ho", "m2") == "fut.ho.f02.settle"


def test_rbob_and_pre_2006_unleaded_cracks_are_separate_definitions() -> None:
    """The two gasoline contracts are not spliced into one crack at this layer -- the
    splice is an explicit downstream decision, flagged by core.cracks.rbob_splice_flag."""
    assert "us321" in FUTURES_CRACK_DEFS
    assert "hu321" in FUTURES_CRACK_DEFS
    assert FUTURES_CRACK_DEFS["us321"].roots == ("cl", "rb", "ho")
    assert FUTURES_CRACK_DEFS["hu321"].roots == ("cl", "hu", "ho")


def test_build_futures_cracks_computes_the_rbob_era_crack() -> None:
    # 2006-11-01: (2*2.00*42 + 2.10*42 - 3*60)/3 = (168 + 88.2 - 180)/3 = 25.40
    cracks = build_futures_cracks(_futures_panel(), "m1")
    assert cracks.loc[pd.Timestamp("2006-11-01"), "us321"] == pytest.approx(25.40, abs=0.01)


def test_build_futures_cracks_computes_the_pre_rbob_era_crack() -> None:
    # 2005-11-01: (2*2.20*42 + 2.40*42 - 3*70)/3 = 25.20
    cracks = build_futures_cracks(_futures_panel(), "m1")
    assert cracks.loc[pd.Timestamp("2005-11-01"), "hu321"] == pytest.approx(25.20, abs=0.01)


def test_the_two_gasoline_eras_do_not_overlap_in_this_fixture() -> None:
    """Each era's crack only exists where its own gasoline contract printed -- neither is
    silently filled from the other."""
    cracks = build_futures_cracks(_futures_panel(), "m1")
    assert cracks["us321"].dropna().index.tolist() == [pd.Timestamp("2006-11-01")]
    assert cracks["hu321"].dropna().index.tolist() == [pd.Timestamp("2005-11-01")]


def test_build_futures_cracks_skips_a_tenor_with_no_legs() -> None:
    """EIA publishes ranks 1-4, so m2 exists, but a panel that lacks those columns must
    produce nothing rather than a frame of NaN."""
    assert build_futures_cracks(_futures_panel(), "m2").empty


def test_futures_derived_rows_use_the_specs_tenor_series_id() -> None:
    """Spec 20's own template is derived.crack.<name>.<tenor> -- with real futures the
    tenor is finally m1/m2 rather than the spot placeholder."""
    cracks = build_futures_cracks(_futures_panel(), "m1")
    rows = futures_derived_rows("us321", "m1", cracks["us321"].dropna(), pd.Timestamp("2026-09-05"))
    assert rows["series_id"].unique().tolist() == ["derived.crack.us321.m1"]
    assert rows["value"].dtype == "float64"
    assert rows["unit"].unique().tolist() == ["USD/bbl"]


def test_futures_derived_rows_are_empty_for_an_empty_series() -> None:
    rows = futures_derived_rows("us321", "m1", pd.Series(dtype=float), pd.Timestamp("2026-09-05"))
    assert rows.empty
