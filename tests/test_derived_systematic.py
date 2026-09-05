from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest
from core.strategies import REGISTRY
from pipelines.derived.systematic import (
    POSITION_ROOTS,
    inputs_for_root,
    position_rows,
    rows_for_root,
)


def _lake(n: int = 900) -> pd.DataFrame:
    """ts_long rows for one root: four ranks, the adjusted front month, and both
    conditioners."""
    idx = pd.bdate_range("2015-01-01", periods=n)
    rng = np.random.default_rng(0)
    base = 70 + np.cumsum(rng.normal(0, 0.5, n))
    frames = []

    def add(series_id: str, values: np.ndarray) -> None:
        frames.append(
            pd.DataFrame(
                {
                    "series_id": series_id,
                    "source": "eia",
                    "ts": idx,
                    "value": values,
                    "unit": "USD/bbl",
                    "geo": "US",
                    "freq": "D",
                    "revision_date": pd.Timestamp("2026-09-05"),
                }
            )
        )

    for r in (1, 2, 3, 4):
        add(f"fut.cl.f{r:02d}.settle", base - 0.4 * (r - 1))
    add("derived.curve.cl.f01_adj", base)
    add("derived.cushing.util_decile", rng.integers(0, 10, n).astype(float))
    add("derived.cot.cl.mm_pct_3y", rng.uniform(0, 1, n))
    return pd.concat(frames, ignore_index=True)


def _lake_without_f01_adj(n: int = 900) -> pd.DataFrame:
    """Same as `_lake()` but with `derived.curve.cl.f01_adj` missing entirely -- reproduces
    `derived_curve_ranks` having failed (or not yet run) for this root while the raw settle
    legs it doesn't touch already exist in the lake."""
    idx = pd.bdate_range("2015-01-01", periods=n)
    rng = np.random.default_rng(0)
    base = 70 + np.cumsum(rng.normal(0, 0.5, n))
    frames = []

    def add(series_id: str, values: np.ndarray) -> None:
        frames.append(
            pd.DataFrame(
                {
                    "series_id": series_id,
                    "source": "eia",
                    "ts": idx,
                    "value": values,
                    "unit": "USD/bbl",
                    "geo": "US",
                    "freq": "D",
                    "revision_date": pd.Timestamp("2026-09-05"),
                }
            )
        )

    for r in (1, 2, 3, 4):
        add(f"fut.cl.f{r:02d}.settle", base - 0.4 * (r - 1))
    add("derived.cushing.util_decile", rng.integers(0, 10, n).astype(float))
    add("derived.cot.cl.mm_pct_3y", rng.uniform(0, 1, n))
    return pd.concat(frames, ignore_index=True)


def test_position_roots_are_the_ones_with_rank_data() -> None:
    assert set(POSITION_ROOTS) == {"cl", "rb", "ho", "hu"}


def test_inputs_for_root_assembles_every_leg() -> None:
    data = inputs_for_root(_lake(), "cl")
    assert list(data.unadj.columns) == ["f01", "f02", "f03", "f04"]
    assert len(data.f01_adj) == 900
    assert data.util_decile is not None
    assert data.cot_pct is not None


def test_inputs_for_a_root_with_no_data_is_none() -> None:
    assert inputs_for_root(_lake(), "rb") is None


def test_position_rows_use_the_conventions_series_id() -> None:
    """specs/00_TRADING_CONVENTIONS.md: positions are derived.pos.<strategy>.<root>."""
    pos = pd.Series(0.5, index=pd.bdate_range("2020-01-01", periods=3))
    rows = position_rows("MOM_100", "cl", pos, pd.Timestamp("2026-09-05"))
    assert rows["series_id"].unique().tolist() == ["derived.pos.MOM_100.cl"]
    assert rows["value"].dtype == "float64"
    assert rows["source"].unique().tolist() == ["derived"]
    assert rows["unit"].unique().tolist() == ["position"]


def test_position_rows_are_empty_for_an_empty_series() -> None:
    assert position_rows("MOM_100", "cl", pd.Series(dtype=float), pd.Timestamp("2026-09-05")).empty


def test_rows_for_root_skips_the_strategies_that_need_deferred_ranks() -> None:
    """CARRY_1_13 and FWD_SPREAD_MR need ranks 13 and 7; EIA publishes 1-4. They must be
    absent from the output, not written as flat positions."""
    rows, skipped = rows_for_root(_lake(), "cl", pd.Timestamp("2026-09-05"))
    written = {sid.split(".")[2] for sid in rows["series_id"].unique()}
    assert "CARRY_1_13" not in written
    assert "FWD_SPREAD_MR" not in written
    assert {"CARRY_1_13", "FWD_SPREAD_MR"} <= set(skipped)


def test_rows_for_root_writes_the_strategies_that_do_work() -> None:
    rows, _ = rows_for_root(_lake(), "cl", pd.Timestamp("2026-09-05"))
    written = {sid.split(".")[2] for sid in rows["series_id"].unique()}
    assert {"MOM_100", "CONVEX_SPREAD", "SHORT_SPREAD_STATIC", "CARRY_REACT"} <= written


def test_skipped_strategies_carry_a_reason() -> None:
    """A skip with no reason is indistinguishable from a bug."""
    _, skipped = rows_for_root(_lake(), "cl", pd.Timestamp("2026-09-05"))
    assert all(reason for reason in skipped.values())
    assert "f13" in skipped["CARRY_1_13"]


def test_a_root_with_no_data_produces_nothing() -> None:
    rows, skipped = rows_for_root(_lake(), "ho", pd.Timestamp("2026-09-05"))
    assert rows.empty
    assert skipped == {}


# --- a missing adjusted front month must never fall back to the raw rank ----------


def test_inputs_for_root_leaves_f01_adj_nan_when_the_adjusted_series_is_absent() -> None:
    """derived.curve.cl.f01_adj missing must not silently fall back to the raw f01 rank --
    core/systematic.py is explicit that a raw rank series scores the roll step as momentum."""
    data = inputs_for_root(_lake_without_f01_adj(), "cl")
    assert data is not None
    assert data.f01_adj.isna().all()
    assert not data.f01_adj.equals(data.unadj["f01"])


def test_rows_for_root_skips_outright_strategies_when_the_adjusted_series_is_absent() -> None:
    """Every strategy that actually consumes f01_adj must be reported as skipped, not
    silently compute an all-NaN position and vanish from the written frame with no trace."""
    rows, skipped = rows_for_root(_lake_without_f01_adj(), "cl", pd.Timestamp("2026-09-05"))
    written = {sid.split(".")[2] for sid in rows["series_id"].unique()} if not rows.empty else set()
    for name in ("MOM_100", "CARRY_MOM", "CARRY_REACT", "VALUE_OVERLAY"):
        assert name not in written, name
        assert "f01_adj" in skipped.get(name, ""), name


def test_rows_for_root_still_writes_spread_strategies_when_the_adjusted_series_is_absent() -> None:
    """CONVEX_SPREAD and SHORT_SPREAD_STATIC trade the unadjusted rank spread directly and
    never touch f01_adj, so a missing adjusted series must not take them down too."""
    rows, _ = rows_for_root(_lake_without_f01_adj(), "cl", pd.Timestamp("2026-09-05"))
    written = {sid.split(".")[2] for sid in rows["series_id"].unique()}
    assert {"CONVEX_SPREAD", "SHORT_SPREAD_STATIC"} <= written


# --- a real bug must propagate, not be folded into the skip channel ---------------


def test_rows_for_root_lets_a_non_key_error_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    """A genuine programming error inside a strategy's build function (anything other than
    the documented KeyError for an absent rank) must propagate, not be swallowed into the
    same `skipped` channel as CARRY_1_13's legitimate "needs rank 13"."""

    def _broken(data: object) -> pd.Series:
        raise TypeError("boom")

    broken = dataclasses.replace(REGISTRY["MOM_100"], build=_broken)
    monkeypatch.setitem(REGISTRY, "MOM_100", broken)

    with pytest.raises(TypeError, match="boom"):
        rows_for_root(_lake(), "cl", pd.Timestamp("2026-09-05"))
