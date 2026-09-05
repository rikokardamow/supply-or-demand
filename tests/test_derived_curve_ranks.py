from __future__ import annotations

import pandas as pd
from pipelines.derived.curve_ranks import (
    ADJUSTED_SUFFIX,
    RANK_ROOTS,
    derived_rows_for_root,
    rank_panel_for,
)


def _lake_rows() -> pd.DataFrame:
    """ts_long-shaped rows for one root's four EIA ranks."""
    index = pd.bdate_range("2026-01-01", periods=12)
    base = {"f01": 70.0, "f02": 71.0, "f03": 72.0, "f04": 73.0}
    frames = []
    for rank, level in base.items():
        frames.append(
            pd.DataFrame(
                {
                    "series_id": f"fut.cl.{rank}.settle",
                    "source": "eia",
                    "ts": index,
                    "value": [level + i * 0.1 for i in range(len(index))],
                    "unit": "USD/bbl",
                    "geo": "US",
                    "freq": "D",
                    "revision_date": pd.Timestamp("2026-09-05"),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def test_rank_roots_are_the_eia_published_ones() -> None:
    """EIA publishes NYMEX ranks for crude, RBOB, heating oil and pre-2006 unleaded --
    not Brent, gasoil or TTF."""
    assert set(RANK_ROOTS) == {"cl", "rb", "ho", "hu"}


def test_rank_panel_pivots_the_lake_rows_into_rank_columns() -> None:
    panel = rank_panel_for(_lake_rows(), "cl")
    assert list(panel.columns) == ["f01", "f02", "f03", "f04"]
    assert len(panel) == 12


def test_rank_panel_is_empty_for_a_root_with_no_rows() -> None:
    assert rank_panel_for(_lake_rows(), "rb").empty


def test_derived_rows_include_the_spreads_computable_from_four_ranks() -> None:
    """s12/s13/s23 need ranks 1-3; s16 and s1_12 need ranks 6 and 12, which EIA does not
    publish, so they must be absent rather than wrong."""
    rows = derived_rows_for_root(_lake_rows(), "cl", pd.Timestamp("2026-09-05"))
    ids = set(rows["series_id"])
    assert "derived.spread.cl.s12" in ids
    assert "derived.spread.cl.s13" in ids
    assert "derived.spread.cl.s16" not in ids
    assert "derived.spread.cl.s1_12" not in ids


def test_derived_rows_include_convexity_and_regime() -> None:
    ids = set(derived_rows_for_root(_lake_rows(), "cl", pd.Timestamp("2026-09-05"))["series_id"])
    assert "derived.curve.cl.cv123" in ids
    assert "derived.curve.cl.regime" in ids


def test_derived_rows_include_the_back_adjusted_front_month() -> None:
    """The series Spec 21's momentum, value and return signals need, which nothing in the
    lake provided before."""
    ids = set(derived_rows_for_root(_lake_rows(), "cl", pd.Timestamp("2026-09-05"))["series_id"])
    assert f"derived.curve.cl.{ADJUSTED_SUFFIX}" in ids


def test_spreads_are_computed_from_the_unadjusted_ranks() -> None:
    """The conventions forbid deriving a spread from a back-adjusted series."""
    rows = derived_rows_for_root(_lake_rows(), "cl", pd.Timestamp("2026-09-05"))
    s12 = rows[rows["series_id"] == "derived.spread.cl.s12"].set_index("ts")["value"]
    # f01 - f02 is a flat -1.0 by construction in this fixture
    assert s12.dropna().round(6).eq(-1.0).all()


def test_derived_rows_are_float64_and_tagged_derived() -> None:
    rows = derived_rows_for_root(_lake_rows(), "cl", pd.Timestamp("2026-09-05"))
    assert rows["value"].dtype == "float64"
    assert rows["source"].unique().tolist() == ["derived"]


def test_a_root_with_no_data_produces_no_rows() -> None:
    assert derived_rows_for_root(_lake_rows(), "ho", pd.Timestamp("2026-09-05")).empty
